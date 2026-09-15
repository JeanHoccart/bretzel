"""Render-context middleware — the central piece.

Builds a fresh :class:`RenderContext` per request, populates it from
what the upstream middleware (session / auth) parsed, binds it as the
active context-var, and applies the resolved cookies / headers on the
way out.

This is also the point where we run the registered cleanup callbacks
in LIFO order — anything that needs to happen after the response
went through the middleware stack but before the connection closes.

Form data (V3 wire) : when the inbound request is form-typed, the
middleware buffers the body — **borné et déversé sur disque au-delà d'un
seuil**, cf. ``_buffer_body`` —, parses it ONCE, and splits the namespaced
client-state fields (``Class.key.field=value``, injected by the
runtime bridge on every HTMX request) from the regular handler args
via :func:`bretzel.runtime.envelope.parse_client_payload`. The handler
args land on ``ctx.form_data``, the client-state slice feeds the
:class:`StateRegistry` hydration. Downstream consumers that still call
``request.body()`` / ``.form()`` get the buffered bytes via a replay
receive callable.
"""

from __future__ import annotations

import logging
import secrets
import tempfile
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Any
from urllib.parse import parse_qsl

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bretzel.render.context import RenderContext, use_context
from bretzel.render.lang import resolve_language
from bretzel.runtime.envelope import parse_client_payload
from bretzel.runtime.protocol import (
    HEADER_PAGE_ID,
    HEADER_TAB,
    HEADER_ZONES,
    LANG_COOKIE,
)
from bretzel.server.middleware._state import ensure_state, read_header
from bretzel.server.middleware.csrf import csrf_token_for
from bretzel.state.registry import StateRegistry

if TYPE_CHECKING:
    from bretzel.render.types import BretzelApp


_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})

_log = logging.getLogger("bretzel.server.request")

#: Le plafond du CORPS entier. Il n'en existait aucun : ``_read_full_body``
#: concaténait ce qui arrivait jusqu'à ce que le client s'arrête, donc un
#: seul POST suffisait à faire allouer au worker autant de RAM que
#: l'expéditeur voulait. ``_MAX_PART_BYTES`` ne protégeait pas de ça — il
#: s'applique à une PART, et seulement après que le corps entier est déjà
#: en mémoire.
#:
#: 32 Mio, la même valeur que le plafond d'une part : une part ne peut de
#: toute façon pas dépasser le corps qui la contient. Au-delà, la réponse
#: est un 413 — et c'est une amélioration franche par rapport à avant, où
#: un corps trop gros passait le tampon puis échouait au parse, ce que le
#: ``except`` transformait en formulaire vide, silencieusement.
_MAX_BODY_BYTES = 32 * 1024 * 1024

#: Au-delà de quoi le tampon part sur DISQUE.
#:
#: ``SpooledTemporaryFile`` garde tout en mémoire sous ce seuil et bascule
#: sur un fichier au premier octet qui le dépasse. Le chemin chaud — une
#: action, quelques centaines d'octets — ne touche donc jamais le disque,
#: et un dépôt de 30 Mio coûte 1 Mio de RAM au lieu de 30. Sans ça, le
#: déversement que Starlette fait déjà pour les parts fichier était
#: annulé d'avance : on avait tout matérialisé avant qu'il ne le voie.
_SPOOL_THRESHOLD_BYTES = 1024 * 1024

#: La taille d'un morceau relu du tampon. Le corps repart en PLUSIEURS
#: messages ASGI quand il est gros — ce qui est aussi plus fidèle au
#: protocole que l'unique message d'avant.
_REPLAY_CHUNK_BYTES = 64 * 1024

_TOO_LARGE = (
    f"le corps de la requête dépasse {_MAX_BODY_BYTES // (1024 * 1024)} Mio."
)


@dataclass(slots=True)
class _BufferedBody:
    """Le corps de la requête, relisible autant de fois qu'il faut.

    ``too_large`` dit que la lecture s'est arrêtée sur le plafond : le
    contenu est alors tronqué et ne doit pas être parsé. On ne draine pas
    le reste — répondre 413 sans finir d'écouter est le comportement
    normal, et continuer à lire serait précisément ce qu'on refuse.
    """

    spool: IO[bytes]
    size: int
    too_large: bool = False

    def read_all(self) -> bytes:
        self.spool.seek(0)
        return self.spool.read()

    def close(self) -> None:
        self.spool.close()


def _zones_declared_by(request: Any) -> frozenset[str] | None:
    """Les zones que le navigateur dit porter, ou ``None`` s'il se tait.

    ``None`` et l'ensemble vide ne veulent PAS dire la même chose : le
    premier est « je ne sais pas » et laisse le drain se comporter comme
    avant, le second serait « aucune zone » et les ferait toutes taire.
    Le runtime n'envoie jamais l'en-tête vide, donc une valeur vide ou
    blanche est traitée comme un silence.

    Cf. :data:`~bretzel.runtime.protocol.HEADER_ZONES` pour la mesure qui
    justifie l'en-tête.
    """
    brut = request.headers.get(HEADER_ZONES)
    if not brut:
        return None
    # Chaque entrée est ``id`` ou ``id:empreinte`` — l'empreinte est lue
    # par :func:`_zone_hashes_of`, ici on ne garde que l'identité.
    ids = frozenset(
        p.split(":", 1)[0]
        for p in (m.strip() for m in brut.split(",")) if p
    )
    return ids or None


def _zone_hashes_of(request: Any) -> dict[str, str]:
    """``{id: empreinte}`` de ce que le navigateur AFFICHE déjà.

    Vide quand le client se tait ou n'envoie que des identités — un
    runtime plus ancien, ou le tout premier POST après un chargement
    complet, qui n'a encore reçu aucune empreinte.
    """
    brut = request.headers.get(HEADER_ZONES)
    if not brut:
        return {}
    connus: dict[str, str] = {}
    for morceau in (m.strip() for m in brut.split(",")):
        if ":" in morceau:
            zone_id, empreinte = morceau.split(":", 1)
            if zone_id and empreinte:
                connus[zone_id] = empreinte
    return connus


class RenderContextMiddleware:
    """Construct a per-request :class:`RenderContext` and apply its
    accumulated cookies / headers to the outgoing response."""

    def __init__(self, app: ASGIApp, *, bretzel_app: BretzelApp) -> None:
        self.app = app
        self._bretzel_app = bretzel_app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = ensure_state(scope)
        session_id = getattr(state, "session_id", None) or secrets.token_hex(16)
        user_id = getattr(state, "user_id", None)

        raw_form, replay_receive, form_error, buffered = await _collect_form(
            scope, receive
        )
        if buffered is not None and buffered.too_large:
            # Refus AVANT de construire quoi que ce soit : ni contexte,
            # ni registre, ni route. Le corps est tronqué, il n'y a rien
            # à en tirer, et 413 est la réponse que le client attend.
            buffered.close()
            await Response(_TOO_LARGE, status_code=413)(scope, receive, send)
            return
        # V3 wire : split the bridge-injected client-state fields from
        # the regular handler args. The registry hydrates from the
        # former ; the action route / handlers only ever see the latter.
        by_instance, form_data = parse_client_payload(raw_form)
        client_state_payload = {
            f"{cls}.{key}": fields for (cls, key), fields in by_instance.items()
        }

        request = Request(scope, replay_receive)

        # CSRF token is deterministic on (session_id, csrf_key) — same
        # value every render of the same session, picked up by the
        # runtime envelope and echoed in the ``X-Bretzel-CSRF`` header
        # on non-safe-method requests (the :class:`CSRFMiddleware`
        # validates it on the way in).
        csrf_key = getattr(self._bretzel_app.config, "_csrf_key", b"")
        csrf_token = csrf_token_for(session_id, csrf_key) if csrf_key else ""

        cfg = self._bretzel_app.config
        resolved_lang = resolve_language(
            cookie=request.cookies.get(LANG_COOKIE),
            header=request.headers.get("accept-language"),
            available=cfg.languages,
            default=cfg.lang,
        )
        ctx = RenderContext(
            app=self._bretzel_app,
            request=request,
            state_registry=None,
            client_state_payload=client_state_payload,
            form_data=form_data,
            form_error=form_error,
            user_id=user_id,
            session_id=session_id,
            csrf_token=csrf_token,
            live_zones=_zones_declared_by(request),
            zone_hashes=_zone_hashes_of(request),
            tab_id=(request.headers.get(HEADER_TAB) or "").strip()[:64],
            # La langue et les mots du framework voyagent PAR VALEUR
            # jusqu'ici : un composant en couche 5 ne peut pas remonter
            # lire la config en couche 7, et ``ui.text()`` doit marcher
            # sans app complète (toute la suite unitaire).
            lang=resolved_lang,
            texts=cfg.text_tables.for_language(resolved_lang),
        )

        page_id = read_header(scope, HEADER_PAGE_ID) or ctx.page_uuid
        url_params = _addressable_params(scope)

        backend = getattr(self._bretzel_app, "_state_backend", None)
        if backend is not None:
            ctx.state_registry = StateRegistry(
                backend=backend,
                client_payload=client_state_payload,
                form_data=form_data,
                session_id=session_id,
                user_id=user_id,
                page_id=page_id,
                url_params=url_params,
            )

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                _apply_ctx_cookies_and_headers(ctx, message)
            await send(message)

        with use_context(ctx):
            try:
                await self.app(scope, replay_receive, wrapped_send)
            finally:
                ctx.run_cleanups()
                # Le tampon peut être un FICHIER : ne pas le fermer
                # laisserait un temporaire par dépôt un peu gros, et le
                # ramasse-miettes ne s'en occupe qu'à sa main.
                if buffered is not None:
                    buffered.close()


# ───────────────────────────────────────────────────────────────────────────
# Form body buffering + parsing
# ───────────────────────────────────────────────────────────────────────────


async def _collect_form(
    scope: Scope, receive: Receive
) -> tuple[dict[str, Any], Receive, str | None, _BufferedBody | None]:
    """``(form_data, receive aval, erreur éventuelle, tampon à fermer)``.

    Non-form-typed methods pass through with an empty form and the
    original ``receive``. Form-typed POSTs buffer the body so we can
    parse once here and replay it for any consumer that re-reads.

    Le troisième élément est la RAISON d'un formulaire vide quand il y en
    a une. Elle remonte jusqu'au dispatcher d'action, qui refuse plutôt
    que de faire tourner un handler sur du vide — un formulaire illisible
    valait sinon une saisie de champs blancs, écrite dans l'état.

    Le quatrième est le tampon : l'appelant DOIT le fermer, sinon un
    dépôt un peu gros laisse un fichier temporaire derrière lui.
    """
    method = scope.get("method", "").upper()
    if method not in _BODY_METHODS:
        return {}, receive, None, None

    ct = read_header(scope, "content-type") or ""
    is_urlencoded = "application/x-www-form-urlencoded" in ct
    is_multipart = "multipart/form-data" in ct
    if not (is_urlencoded or is_multipart):
        return {}, receive, None, None

    buffered = await _buffer_body(receive)
    if buffered.too_large:
        # Le corps est tronqué : rien à parser, et l'appelant répond 413.
        return {}, _replay_receive(buffered), _TOO_LARGE, buffered
    replay = _replay_receive(buffered)
    if not buffered.size:
        return {}, replay, None, buffered
    if is_urlencoded:
        # parse_qsl is ~10× faster than spinning up a Starlette
        # MultiPartParser for the common case (every action POST).
        body = buffered.read_all()
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            return (
                {},
                replay,
                "le corps du formulaire n'est pas de l'UTF-8 valide.",
                buffered,
            )
        return (
            dict(parse_qsl(decoded, keep_blank_values=True)),
            replay,
            None,
            buffered,
        )
    # multipart : delegate to Starlette so we inherit every quirk
    # (boundary handling, file uploads, charset detection).
    #
    # ``max_part_size`` relevé : le défaut de Starlette (1 Mo) s'applique à
    # CHAQUE part, y compris celles qui ne sont pas des fichiers, et une
    # part trop grosse lève — ce que le ``except`` ci-dessous transforme en
    # formulaire VIDE, silencieusement. Un formulaire n'arrive ici que
    # depuis août 2026, quand il contient un fichier (``ui.form`` dérive
    # alors son ``hx-encoding``) ; avant, ces corps passaient par
    # ``parse_qsl``, qui n'a aucune limite de champ. Sans ce relèvement, la
    # réparation du dépôt de fichier aurait introduit une falaise à 1 Mo
    # sur le CHAMP TEXTE voisin — un ``ui.signature_pad`` (data-URL base64)
    # ou une longue zone de texte suffit à la franchir, et le handler
    # recevrait un formulaire vide sans un mot.
    request = Request(scope, _replay_receive(buffered))
    try:
        raw_form = await request.form(max_part_size=_MAX_PART_BYTES)
        return {k: raw_form[k] for k in raw_form}, replay, None, buffered
    except Exception as exc:
        # ⚠️ Ce ``except`` rendait un formulaire VIDE et se taisait. Le
        # handler tournait alors sur des champs blancs et les écrivait
        # dans l'état : la panne se lisait comme une saisie, ce qui est
        # le pire des deux. On garde le passage — un ``raise`` ici
        # casserait aussi les routes tierces qui lisent le corps
        # elles-mêmes — mais la raison remonte, et le dispatcher refuse.
        _log.exception("Formulaire multipart illisible")
        return (
            {},
            replay,
            f"le formulaire multipart n'a pas pu être lu : {exc}",
            buffered,
        )


#: Le plafond d'une part multipart. 32 Mo : assez pour qu'un champ texte
#: ne le rencontre jamais, et assez bas pour rester une borne. Le défaut de
#: Starlette (1 Mo) vaut pour un champ ; il est trop bas dès qu'un
#: formulaire porte un fichier, ce qui est le seul cas où on arrive ici.
_MAX_PART_BYTES = 32 * 1024 * 1024


async def _buffer_body(receive: Receive) -> _BufferedBody:
    """Draine ``receive`` dans un tampon BORNÉ et déversable sur disque.

    Deux différences avec la version d'avant, et la première est une
    faille fermée : on s'arrête au plafond au lieu d'allouer ce que
    l'expéditeur veut, et on écrit dans un ``SpooledTemporaryFile`` au
    lieu d'une liste d'octets — donc sous le seuil, c'est toujours de la
    mémoire, et au-dessus, c'est un fichier.

    On cesse de lire dès le plafond franchi : finir d'écouter un corps
    qu'on va refuser reviendrait à le laisser coûter ce qu'il voulait.
    """
    # Pas de gestionnaire de contexte (SIM115) : le tampon vit plus
    # longtemps que cette fonction — il doit survivre au parse ET au
    # passage de la requête dans toute la pile. Sa fermeture est dans le
    # ``finally`` du middleware, et
    # ``test_the_buffer_is_closed_after_the_request`` la garde.
    spool: IO[bytes] = tempfile.SpooledTemporaryFile(  # noqa: SIM115
        max_size=_SPOOL_THRESHOLD_BYTES
    )
    size = 0
    while True:
        msg = await receive()
        if msg["type"] != "http.request":
            break
        chunk = msg.get("body", b"")
        if size + len(chunk) > _MAX_BODY_BYTES:
            _log.warning(
                "Corps de requête refusé : plus de %d octets.", _MAX_BODY_BYTES
            )
            return _BufferedBody(spool=spool, size=size, too_large=True)
        spool.write(chunk)
        size += len(chunk)
        if not msg.get("more_body", False):
            break
    return _BufferedBody(spool=spool, size=size)


def _replay_receive(buffered: _BufferedBody) -> Receive:
    """Rejouer le corps depuis le tampon, par morceaux.

    Chaque appel rend un ``Receive`` INDÉPENDANT : il porte sa propre
    position et repositionne le tampon avant chaque lecture, donc deux
    consommateurs (le parse ici, puis la route en aval) le relisent tous
    les deux depuis le début. Un curseur partagé donnerait un corps vide
    au second, ce qui est exactement le bug qu'un tampon existe pour
    éviter.
    """
    position = 0
    done = False

    async def replay() -> Message:
        nonlocal position, done
        if done:
            return {"type": "http.disconnect"}
        buffered.spool.seek(position)
        chunk = buffered.spool.read(_REPLAY_CHUNK_BYTES)
        position = buffered.spool.tell()
        more = position < buffered.size
        done = not more
        return {"type": "http.request", "body": chunk, "more_body": more}

    return replay


# ───────────────────────────────────────────────────────────────────────────
# Response splicing — cookies + headers from RenderContext
# ───────────────────────────────────────────────────────────────────────────


def _apply_ctx_cookies_and_headers(ctx: RenderContext, message: Message) -> None:
    """Splice ``ctx`` cookies + headers onto an ``http.response.start`` message.

    Cookie formatting is delegated to a throwaway Starlette Response
    so every option (``samesite``, ``domain``, ``expires``,
    ``max_age``, …) matches what ``Response.set_cookie`` /
    ``.delete_cookie`` would have written — same formatter as
    ``session.py`` uses, no drift between the two paths.
    """
    headers = MutableHeaders(scope=message)

    for name, value in ctx.response_headers.items():
        headers[name] = value

    if ctx.new_cookies or ctx.deleted_cookies:
        dummy = Response()
        for name, opts in ctx.new_cookies.items():
            opts_copy = dict(opts)
            value = opts_copy.pop("value")
            dummy.set_cookie(name, value, **opts_copy)
        for name in ctx.deleted_cookies:
            dummy.delete_cookie(name)
        for k, v in dummy.raw_headers:
            if k == b"set-cookie":
                headers.append("set-cookie", v.decode("latin-1"))


def _addressable_params(scope: Scope) -> dict[str, str]:
    """Les paramètres de l'URL que le NAVIGATEUR affiche.

    Deux sources, et les confondre casse un des deux chemins :

    - **une navigation** (GET, boostée ou non) porte sa query dans sa
      propre URL. ``HX-Current-URL`` y désigne la page qu'on QUITTE —
      s'en servir sèmerait l'état de la page précédente ;
    - **une action** POSTe sur ``/_bretzel/action/<id>``, qui n'a aucune
      query. Là, ``HX-Current-URL`` est la seule source, et c'est
      justement ce qui rend l'URL autoritaire : même si le ``page_id``
      est perdu, l'état se reconstruit depuis l'adresse affichée.
    """
    if scope.get("method", "GET").upper() == "GET":
        raw = scope.get("query_string", b"").decode("latin-1")
    else:
        current = read_header(scope, "HX-Current-URL") or ""
        raw = current.partition("?")[2]
    return dict(parse_qsl(raw, keep_blank_values=True)) if raw else {}

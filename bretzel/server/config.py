"""Resolved app configuration — populated once at :class:`Bretzel` init.

Frozen dataclass so app code can't mutate the resolved view at runtime.
Validation happens in :py:meth:`__post_init__` ; clear errors at boot
beat opaque crashes mid-request.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from bretzel.render import LanguageTables
from bretzel.server.crypto import (
    PURPOSE_ACTION,
    PURPOSE_AUTH,
    PURPOSE_CSRF,
    derive_key,
)

#: Le sous-ensemble de BCP-47 qu'une app déclare en pratique : une
#: langue, éventuellement une écriture, éventuellement une région —
#: ``fr``, ``zh-Hant``, ``pt-BR``, ``zh-Hant-TW``. Les extensions
#: (``-u-ca-buddhist``) et les tags privés sont hors de ce que
#: ``<html lang>`` demande, et les accepter reviendrait à ne rien valider.
_BCP47 = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z]{4})?(-([A-Za-z]{2}|\d{3}))?")


class ConfigError(ValueError):
    """Raised at :class:`BretzelConfig` construction when a required
    setting is missing or malformed."""


@dataclass(frozen=True, slots=True)
class BretzelConfig:
    """The resolved, validated configuration of a :class:`Bretzel` app.

    Construction goes through :py:meth:`from_kwargs` so we can apply
    env-var fallbacks consistently. Direct ``BretzelConfig(...)`` use
    is supported in tests but skips the env lookup.
    """

    # ── Identification ────────────────────────────────────────────────
    title: str = "Bretzel App"
    # ``description`` flows into the document head as the global
    # ``<meta name="description">`` fallback when a page doesn't set
    # its own via ``@page(description=...)``.
    description: str | None = None

    # ── Security primitives ───────────────────────────────────────────
    secret_key: str = ""  # mandatory — validated below
    # CSRF protection is always-on. The ``/_bretzel/action/*`` route is
    # protected by per-call HMAC on ``action_id + bound_args`` ; every
    # other non-safe method (POST/PUT/PATCH/DELETE) goes through the
    # :class:`CSRFMiddleware`, which verifies a session-bound token in
    # the ``X-Bretzel-CSRF`` header (echoed from the page envelope) and
    # checks the request ``Origin`` against ``trusted_hosts`` (or the
    # request ``Host`` when none configured).
    #
    # Each surface uses its OWN derived key
    # (:func:`bretzel.server.crypto.derive_key`) — compromising the
    # action signing key doesn't compromise the auth cookie or vice
    # versa. The derivation happens once at config construction ; the
    # three keys live in ``_action_key`` / ``_auth_key`` / ``_csrf_key``
    # below and are addressed by name from the relevant call sites.
    _action_key: bytes = field(init=False, repr=False, compare=False, default=b"")
    _auth_key: bytes = field(init=False, repr=False, compare=False, default=b"")
    _csrf_key: bytes = field(init=False, repr=False, compare=False, default=b"")

    # ── Persistence + scaling ─────────────────────────────────────────
    redis_url: str | None = None
    workers: int = 1

    # ── Sessions / auth ───────────────────────────────────────────────
    # Bretzel auth is intentionally MINIMAL : just the 4 helpers
    # (``login`` / ``logout`` / ``user_id`` / ``is_authenticated``) + the
    # signed cookie. Login pages, password verification, post-auth
    # redirects — all of that is the user app's responsibility, not the
    # framework's.
    session_max_age_days: int = 30

    # ── Static / build ────────────────────────────────────────────────
    # Quand il est posé, le dossier est monté sur ``/static`` (constante
    # ``ROUTE_STATIC_DIR``) par ``_mount_static_dir`` au démarrage — utile
    # pour les assets utilisateur (favicon, logos, fichiers à télécharger).
    # Un chemin qui ne pointe pas un dossier existant LÈVE au démarrage.
    static_dir: str | None = None

    # ── Icône ─────────────────────────────────────────────────────────
    # Trois valeurs, et la troisième n'est pas cosmétique :
    #
    #   ``None``   (défaut) la marque Bretzel, servie depuis
    #              ``bretzel/static/`` par ``ROUTE_FAVICON`` ;
    #   ``"/…"``   l'icône de l'app, à l'URL qu'elle donne — c'est à elle
    #              de la servir (``static_dir=`` fait ça) ;
    #   ``False``  aucune. Le head émet quand même un ``<link>`` vide
    #              (``href="data:,"``) : sans AUCUN ``<link rel=icon>``
    #              le navigateur va chercher ``/favicon.ico`` tout seul,
    #              donc retirer notre marque coûterait un 404 par page.
    #
    # Le troisième cas existe parce que quelqu'un qui livre un vrai
    # produit doit pouvoir enlever notre marque AVANT d'avoir la sienne.
    favicon: str | bool | None = None

    # ── Security middleware shortcuts ─────────────────────────────────
    cors_origins: tuple[str, ...] = ()
    trusted_hosts: tuple[str, ...] = ()
    # Anti-replay window (HMAC v2, opt-in) : reject a signed action whose
    # render timestamp is older than this many seconds. ``None`` = valid
    # forever (pre-v2). A stale action 403s → the client reloads the page.
    action_max_age: int | None = None

    # Les trois en-têtes qui ne dépendent de rien (``nosniff``,
    # ``Referrer-Policy``, ``X-Frame-Options``). Par défaut parce qu'ils
    # ne peuvent casser aucune app ; le réglage existe pour l'app qui
    # les pose elle-même en amont, derrière son proxy.
    security_headers: bool = True

    # La CSP, sur DEUX axes volontairement séparés — le mode ici, les
    # sources dans ``csp_sources`` en dessous. Les mélanger (un dict qui
    # voudrait dire « active ET étends ») ferait deux façons d'écrire la
    # même chose.
    #
    # ``False`` par défaut, et c'est le partage : Bretzel ne peut pas
    # deviner les polices, CDN et iframes de l'app, donc c'est elle qui
    # décide. ``"report-only"`` est le premier barreau — le navigateur
    # évalue la politique et signale ce qui aurait sauté SANS rien
    # bloquer. On regarde ce qui remonte, on complète ``csp_sources``,
    # puis on passe à ``True``. Ce mode existe exactement pour ne pas
    # découvrir en production qu'il manquait une origine.
    csp: bool | Literal["report-only"] = False

    # Ce que l'APP ajoute — Bretzel calcule déjà ce qu'il se doit à
    # lui-même (ses empreintes de scripts inline, ``'unsafe-eval'``, les
    # hôtes d'API d'icônes, les origines de ses assets selon que le
    # rapatriement vendor a eu lieu ou non).
    #
    #     Bretzel(csp=True, csp_sources={
    #         "font-src": ["https://fonts.gstatic.com"],
    #         "frame-src": ["https://www.youtube.com"],
    #     })
    #
    # On peut élargir, jamais rétrécir : rétrécir se ferait en silence
    # et casserait le framework chez celui qui l'a écrit.
    csp_sources: Mapping[str, Sequence[str]] = field(
        default_factory=dict, compare=False
    )

    # ── Langue ────────────────────────────────────────────────────────
    # La langue du document, en BCP-47 (``"fr"``, ``"fr-CA"``, ``"pt-BR"``).
    # Elle fait DEUX choses, et pas une de plus :
    #
    #   1. ``<html lang="…">``, qui est l'attribut standard — un lecteur
    #      d'écran choisit sa voix dessus, et le navigateur sa coupure de
    #      mots. Le paramètre existait dans ``render/shell.py`` depuis le
    #      début et **personne ne le passait** : toute page Bretzel
    #      expédiait ``lang="en"`` en dur, y compris les apps françaises.
    #   2. Elle voyage jusqu'aux composants, qui la donnent à ``Intl``
    #      (navigateur) ou à leur formateur (serveur) pour tout ce qui se
    #      DÉRIVE : noms de mois et de jours, axes temporels, séparateurs
    #      de nombres, devise.
    #
    # Ce n'est PAS de l'i18n (hors périmètre v2.0, cf. le charter) : aucun
    # catalogue, aucune règle de pluriel, aucune extraction de messages.
    # Les phrases que le framework a écrites lui-même — « Clear filters »,
    # « No results » — ne se dérivent d'aucune langue ; elles se
    # remplacent une par une via :attr:`texts`.
    lang: str = "en"
    # Les mots du framework, surchargeables. Clés dans
    # :data:`bretzel.render.texts.DEFAULT_TEXTS` ; une clé inconnue LÈVE
    # au démarrage plutôt que d'être ignorée en silence — une faute de
    # frappe dans un dict ne se voit nulle part ailleurs.
    texts: Mapping[str, Any] = field(default_factory=dict, compare=False)
    # Les langues que l'app sait rendre. VIDE = monolingue, et c'est le
    # défaut : rien ne change pour une app qui ne déclare rien.
    #
    # Non vide, la langue est résolue PAR REQUÊTE — cookie ``bz_lang``,
    # puis ``Accept-Language``, puis ``lang``. C'est l'ordre de Django,
    # de Rails et de next-intl, et il n'est pas arbitraire : l'en-tête
    # est un défaut de première visite, jamais une autorité, sinon un
    # sélecteur de langue devient inécrivable et deux personnes ouvrant
    # la même URL voient deux pages.
    #
    # ``lang`` doit y figurer : c'est le repli, et un repli hors de la
    # liste rendrait une langue que l'app dit ne pas savoir rendre.
    languages: tuple[str, ...] = ()
    #: DÉRIVÉ (``__post_init__``) : les tables de mots par langue. Pas un
    #: réglage — on ne le passe pas à ``Bretzel(...)``.
    text_tables: Any = field(init=False, repr=False, compare=False, default=None)

    # ── Responsive nav ────────────────────────────────────────────────
    # Single viewport threshold (CSS px) below which ``Screen().is_mobile``
    # is true. Read only by the pre-paint boot script (interpolated
    # server-side into the FOUC-style inline script — never hardcoded in
    # runtime.js, anti-rule 3). There is no live resize listener (the device
    # doesn't change mid-session). 768 = Tailwind's ``md``. Cf.
    # screen-responsive-nav.md.
    mobile_breakpoint: int = 768

    # Barre de progression de NAVIGATION, allumée par défaut. Sur une
    # page qui met 800 ms à revenir, on clique et rien ne bouge — donc
    # on reclique. C'est le seul témoin de chargement que le framework
    # allume sans qu'on le demande, et la raison est qu'il n'a AUCUNE
    # décision de placement à poser : une bande en bord d'écran, une
    # par app, jamais dans le flux. (Un témoin d'action en vol, lui,
    # doit dire OÙ il s'affiche — d'où ``ui.pending()``, explicite.)
    #
    # L'éteindre est un choix esthétique légitime : une app qui a son
    # propre chrome de chargement en aurait deux.
    nav_progress: bool = True

    # ── PWA ───────────────────────────────────────────────────────────
    #: La déclaration d'installabilité. ``None`` → aucune route de
    #: manifeste, aucun ``<link>`` : une app qui ne demande rien n'a
    #: pas à porter le vocabulaire.
    pwa: Any = None

    @property
    def _manifest_url(self) -> str | None:
        """L'URL du manifeste, ou ``None`` — lue par le pipeline.

        Une PROPRIÉTÉ et pas un champ : elle se dérive de ``pwa``,
        donc les deux ne peuvent pas diverger. Un champ aurait pu
        rester posé après qu'on ait retiré le ``pwa``, et la tête du
        document aurait alors lié un manifeste servi par personne.
        """
        if self.pwa is None:
            return None
        from bretzel.server.pwa import MANIFEST_ROUTE
        return MANIFEST_ROUTE

    # ── Transport ─────────────────────────────────────────────────────
    # ``Secure`` sur les cookies. ``None`` = déduit du scheme de la
    # requête (cf. ``auth.resolve_cookie_secure``) — c'est une question de
    # transport, pas d'environnement. Forcer n'est utile que derrière un
    # proxy qui termine le TLS sans que uvicorn tourne avec
    # ``proxy_headers=True`` : l'app voit alors ``http`` et sous-estimerait.
    secure_cookies: bool | None = None

    # ── Préréglage ────────────────────────────────────────────────────
    # ``mode`` ne fait QUE poser les défauts des réglages ci-dessous, plus
    # gouverner l'axe assets / cache (pipeline CSS, en-têtes, cache-bust)
    # via :attr:`is_dev`. Il ne décide plus rien d'autre tout seul : un
    # booléen unique qui gouvernait à la fois la verbosité, l'exposition
    # des erreurs ET la sécurité des cookies a coûté un bug de session en
    # production (cf. ``auth.resolve_cookie_secure``).
    mode: Literal["dev", "prod"] = "prod"

    # ── Pipeline CSS ──────────────────────────────────────────────────
    # Quel chemin produit le CSS servi au navigateur. C'est le SEUL axe
    # qui change ce qui est RENDU, d'où un réglage nommé plutôt qu'une
    # implication du mode :
    #
    # - ``"build"``   : compile ``style.css`` au démarrage, servi en
    #   ``<link>`` render-blocking. Le CSS est là au premier paint.
    # - ``"browser"`` : le compilateur ``@tailwindcss/browser`` compile
    #   dans la page. Zéro binaire à installer, mais le CSS arrive APRÈS
    #   le premier paint — cf. traps.md, toute propriété sous
    #   ``transition`` anime alors depuis sa valeur non-stylée.
    # - ``"auto"``    : ``build`` en prod, ``browser`` en dev. Repli sur
    #   ``browser`` avec avertissement si aucun binaire n'est trouvable.
    #
    # ``css="build"`` en dev donne une parité exacte avec la prod, au
    # prix d'une compilation (~3 s) à chaque démarrage.
    css: Literal["auto", "build", "browser"] = "auto"

    # ── Axes indépendants (défaut : suit le préréglage) ────────────────
    # Exposition — le détail des exceptions part-il dans la réponse, et
    # laisse-t-on la page de traceback de FastAPI remonter ? C'est une
    # décision de sécurité liée au fait d'être public ou non.
    expose_errors: bool = False
    # Diagnostics — le framework doit-il être bavard ? Warnings de drift
    # de features, ``each()`` sans clé stable, IDs générés lisibles. C'est
    # le SEUL sens de « debug » : il ne gouverne ni le transport, ni
    # l'exposition, ni les assets.
    debug: bool = False

    @property
    def is_dev(self) -> bool:
        """Préréglage de développement — axe assets / cache uniquement."""
        return self.mode == "dev"

    @property
    def css_pipeline(self) -> Literal["build", "browser"]:
        """Le pipeline CSS effectif, ``"auto"`` résolu.

        ``auto`` garde le compromis historique : la prod compile (le CSS
        doit être là au premier paint), le dev laisse le compilateur
        navigateur pour ne pas exiger de binaire ni payer ~3 s à chaque
        redémarrage. La différence est désormais NOMMÉE : ``css="build"``
        en dev donne la parité exacte avec la prod.
        """
        if self.css != "auto":
            return self.css
        return "browser" if self.is_dev else "build"

    # ── Validation ────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if not self.secret_key:
            raise ConfigError(
                "secret_key is required — pass it to Bretzel(secret_key=...) "
                "or set the BRETZEL_SECRET_KEY environment variable."
            )
        if len(self.secret_key) < 16:
            raise ConfigError(
                "secret_key must be at least 16 characters long. "
                "Use ``secrets.token_hex(32)`` to generate a strong one."
            )
        if self.workers < 1:
            raise ConfigError(
                f"workers must be >= 1, got {self.workers}."
            )
        if self.workers > 1 and self.redis_url is None:
            raise ConfigError(
                "Multi-worker deployments need redis_url configured "
                "(state + SSE broker need a shared backend across workers)."
            )
        if self.session_max_age_days < 1:
            raise ConfigError(
                f"session_max_age_days must be >= 1, got {self.session_max_age_days}."
            )
        # BCP-47, la forme que ``<html lang>`` et ``Intl`` attendent tous
        # les deux. On valide la FORME, pas l'existence : refuser "fr-CA"
        # parce qu'il n'est pas dans une liste ferait mentir le framework
        # sur ce qu'il connaît. Un tag mal formé, lui, ne se voit nulle
        # part — ``Intl`` lève dans le navigateur, donc en silence côté
        # serveur, et l'attribut HTML est simplement ignoré.
        if not _BCP47.fullmatch(self.lang):
            raise ConfigError(
                f"lang doit être une étiquette BCP-47 (ex. 'fr', 'fr-CA', "
                f"'pt-BR'), reçu {self.lang!r}."
            )
        # Résolue une fois au démarrage : la fusion et la validation des
        # clés n'ont aucune raison de se rejouer à chaque requête, et une
        # clé inconnue doit lever AU BOOT — pas sur la page qui l'affiche.
        for code in self.languages:
            if not _BCP47.fullmatch(code):
                raise ConfigError(
                    f"languages contient {code!r}, qui n'est pas une étiquette "
                    f"BCP-47 (ex. 'fr', 'fr-CA')."
                )
        if self.languages and self.lang not in self.languages:
            raise ConfigError(
                f"lang={self.lang!r} n'est pas dans languages="
                f"{list(self.languages)}. C'est le repli de la négociation : "
                f"hors de la liste, il rendrait une langue que l'app déclare "
                f"ne pas savoir rendre."
            )
        # ``languages`` NORMALISÉ : une app monolingue déclare ``(lang,)``,
        # pas ``()``. Deux représentations du même état obligeaient trois
        # modules à tester le vide séparément, et « une seule langue » est
        # déjà le cas dégénéré du général.
        object.__setattr__(
            self, "languages", tuple(dict.fromkeys([self.lang, *self.languages]))
        )
        # ``texts`` reste CE QUE L'UTILISATEUR A ÉCRIT — un réglage. Les
        # tables résolues sont un objet à part, qu'on INTERROGE : une
        # langue sans table y retombe sur le défaut au lieu de lever une
        # ``KeyError`` sur chaque requête.
        object.__setattr__(
            self,
            "text_tables",
            LanguageTables(self.texts, languages=self.languages, default=self.lang),
        )
        if self.mobile_breakpoint < 1:
            raise ConfigError(
                f"mobile_breakpoint must be >= 1 (CSS px), got {self.mobile_breakpoint}."
            )
        # ``csp=True`` / ``False`` / ``"report-only"``, et rien d'autre.
        # Une faute de frappe (``csp="report"``) serait sinon traitée
        # comme un vrai par le middleware et poserait un en-tête
        # BLOQUANT là où le dev croyait n'observer que.
        if self.csp not in (True, False, "report-only"):
            raise ConfigError(
                f"csp doit valoir True, False ou 'report-only' — reçu "
                f"{self.csp!r}. 'report-only' fait évaluer la politique "
                f"par le navigateur SANS rien bloquer : c'est par là "
                f"qu'on commence."
            )
        if self.csp_sources and self.csp is False:
            raise ConfigError(
                "csp_sources est fourni mais csp=False : les sources ne "
                "seraient posées nulle part. Ajoute csp='report-only' "
                "(observation) ou csp=True (blocage)."
            )
        # Les clés sont validées ici plutôt qu'au premier rendu : une
        # directive mal orthographiée ne fait RIEN dans un navigateur,
        # la ressource est juste bloquée sans message.
        if self.csp_sources:
            from bretzel.server.security import CSP_DIRECTIVES

            for nom in self.csp_sources:
                if nom not in CSP_DIRECTIVES:
                    raise ConfigError(
                        f"csp_sources : directive inconnue {nom!r}. "
                        f"Les directives acceptées sont : "
                        f"{', '.join(sorted(CSP_DIRECTIVES))}."
                    )
        if "*" in self.cors_origins:
            # The framework wires CORS with ``allow_credentials=True``
            # (cf. lifecycle.py), so a wildcard origin makes Starlette
            # reflect ANY Origin back with credentials — any site could
            # then send a signed action request with the user's cookies.
            # That is a CSRF hole on the whole action surface. Force the
            # app to list explicit origins.
            raise ConfigError(
                "cors_origins=['*'] is unsafe: CORS is wired with "
                "allow_credentials=True, so a wildcard origin lets any "
                "site send credentialed requests (including signed "
                "actions) — a CSRF hole. List explicit origins instead, "
                "e.g. cors_origins=['https://app.example.com']."
            )

        # Derive per-purpose keys once the master secret has been
        # validated. ``object.__setattr__`` because the dataclass is
        # frozen — these are computed fields, not user-supplied.
        object.__setattr__(self, "_action_key", derive_key(self.secret_key, PURPOSE_ACTION))
        object.__setattr__(self, "_auth_key", derive_key(self.secret_key, PURPOSE_AUTH))
        object.__setattr__(self, "_csrf_key", derive_key(self.secret_key, PURPOSE_CSRF))

    # ── Helpers ───────────────────────────────────────────────────────

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> BretzelConfig:
        """Resolve config from kwargs + env-var fallbacks.

        ``secret_key`` falls through to ``$BRETZEL_SECRET_KEY`` if not
        passed explicitly ; ``mode`` falls through to ``$BRETZEL_MODE``
        ("dev" / anything else, unset → prod).

        C'est ici que le préréglage devient des valeurs concrètes :
        ``debug`` et ``expose_errors`` non fournis (ou ``None``) prennent
        la valeur du mode. Chacun reste surchargeable indépendamment —
        c'est tout l'intérêt : ``mode="prod", debug=True`` donne une prod
        bavarde sans exposer les erreurs, et ``mode="dev",
        expose_errors=False`` permet de tester les vraies pages d'erreur
        en local.
        """
        if not kwargs.get("secret_key"):
            kwargs["secret_key"] = os.environ.get("BRETZEL_SECRET_KEY", "")
        if kwargs.get("mode") is None:
            kwargs["mode"] = (
                "dev"
                if os.environ.get("BRETZEL_MODE", "prod").strip().lower() == "dev"
                else "prod"
            )
        is_dev = kwargs["mode"] == "dev"
        for axis in ("debug", "expose_errors"):
            if kwargs.get(axis) is None:
                kwargs[axis] = is_dev
        if kwargs.get("css") is None:
            kwargs["css"] = "auto"
        # Coerce iterables to tuples so the frozen dataclass works.
        if "cors_origins" in kwargs and kwargs["cors_origins"] is not None:
            kwargs["cors_origins"] = tuple(kwargs["cors_origins"])
        if "trusted_hosts" in kwargs and kwargs["trusted_hosts"] is not None:
            kwargs["trusted_hosts"] = tuple(kwargs["trusted_hosts"])
        return cls(**kwargs)

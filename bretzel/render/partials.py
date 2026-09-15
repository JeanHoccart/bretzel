"""Partial rendering — single ``@refreshable`` section + state delta.

Triggered by :

- A zone enqueued during an action — by a ``deps=`` state change or the
  free :func:`refresh` — the pipeline drains
  :attr:`RenderContext.refresh_queue` at end-of-action and emits each
  section as an out-of-band swap.
- An SSE-driven refetch (``GET /_bretzel/refetch/<state>/<zone>``) from
  the client (manual refresh or an SSE dep-change fan-out).

The output is **not** a full HTML5 document — just the inner content
of the swap target plus a ``<bz-patch>`` tag carrying the
post-action client-state patches. Layer 6 wraps it in a Starlette
``HTMLResponse`` ; we stop at the bytes.

"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from bretzel.core import call_without_blocking
from bretzel.core.escape import escape_attr, escape_html
from bretzel.core.serialize import serialize
from bretzel.core.tree import Element, Node
from bretzel.render.context import RenderContext, use_context
from bretzel.render.decorators.refreshable import (
    RefreshableHandle,
    drain_pending_async_zones,
    zone_attrs,
)
from bretzel.render.fusion import BZ_ID_ATTR, fuse_or_wrap
from bretzel.render.types import BretzelApp
from bretzel.runtime.envelope import serialize_patch
from bretzel.runtime.protocol import HEADER_ZONE_HASHES
from bretzel.state.scopes.client import ClientState, rendering_scope

#: Le ``<template>`` dont le runtime projette le contenu sous
#: ``<body>``. Écrit ici plutôt qu'importé de ``components`` :
#: ``render`` ne remonte pas la pile au chargement (principe 5).
TELEPORT_ATTR = "bz-teleport"

# ───────────────────────────────────────────────────────────────────────────
# Result type
# ───────────────────────────────────────────────────────────────────────────


_log = logging.getLogger("bretzel.render.partials")


@dataclass(slots=True)
class RenderResult:
    """The output of a render call ready for Layer 6 to wrap.

    Carries everything the server needs to assemble a Starlette
    ``Response`` — the body, the response headers, the status code,
    and the cookie ops collected on the way.
    """

    body: str
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    new_cookies: dict[str, dict[str, Any]] = field(default_factory=dict)
    deleted_cookies: set[str] = field(default_factory=set)


# ───────────────────────────────────────────────────────────────────────────
# Public entry — render_partial
# ───────────────────────────────────────────────────────────────────────────


async def render_partial(
    app: BretzelApp,
    handle: RefreshableHandle,
    *,
    ctx: RenderContext,
    extra_handles: Iterable[RefreshableHandle] = (),
) -> RenderResult:
    """Render one or more refreshable sections + the client-state delta.

    Single-section call : pass ``handle`` only — the response body is
    that section's HTML wrapped via :func:`fuse_or_wrap` with
    ``bz-id=handle.id``.

    Multi-section call (typical post-action) : pass ``handle`` for the
    primary one and ``extra_handles`` for the others. Every section
    after the first is emitted as an HTMX out-of-band fragment
    (``hx-swap-oob="morph:innerHTML"``) so a single response updates
    every dependent zone atomically.

    The state delta script is appended last — the runtime applies it
    on ``htmx:afterSwap`` — donc APRÈS le morph, pas avant (le bridge,
    ``05_bridge.js`` ; ``02_morph_hook.js`` n'existe plus), so DOM
    bindings re-evaluate against the new client-state.
    """
    ctx.is_partial = True

    # Every refreshable rides as an OOB fragment. The dispatcher
    # (il n'y a PAS de dispatcher custom : ``05_bridge.js`` enrichit les
    # en-têtes d'un POST htmx natif) issues the action POST with
    # ``swap: 'none'`` — the response body is never swapped into the
    # trigger, only ``hx-swap-oob`` fragments find their target by id.
    # If we emitted the primary without ``hx-swap-oob``, it would be
    # silently dropped. (V1 made the same call : every refresh emits as
    # OOB, swap-by-id, no trigger-vs-target distinction.)
    # ── Une zone imbriquée n'expédie qu'UNE fois ──────────────────
    # Le parent rend son sous-arbre, enfant compris ; si l'enfant est
    # AUSSI dans la file, son fragment part une seconde fois et le morph
    # en jette un. Mesuré : deux zones sur le même état, 200 lignes dans
    # l'enfant → 19,7 Ko dont la moitié inutile ; à trois niveaux,
    # l'intérieur part TROIS fois.
    #
    # L'imbrication ne se sait pas plus tôt : ``enqueue_deps`` ne voit
    # que des déclarations, et « parent appelle enfant » est un fait de
    # RENDU, conditionnel de surcroît. Elle se découvre donc ici, une
    # fois l'arbre construit, et elle ne coûte rien de plus — l'arbre est
    # déjà là.
    #
    # Deux sens, parce que l'ordre de la file est celui des décorations :
    # une zone déjà couverte n'est pas rendue DU TOUT (on épargne aussi
    # le travail serveur), et si l'enfant est passé le premier, son
    # fragment est retiré quand le parent le recouvre.
    ordered: list[RefreshableHandle] = []
    seen: set[str] = set()
    for h in (handle, *extra_handles):
        if h.id not in seen:
            seen.add(h.id)
            ordered.append(h)

    emitted: dict[str, str] = {}
    covered: set[str] = set()
    #: Ce que cette réponse expédie, par zone — renvoyé au client, qui
    #: nous le représentera à la requête suivante.
    empreintes: dict[str, str] = {}
    for h in ordered:
        if h.id in covered:
            continue
        try:
            html, root = await _render_one(app, h, ctx, oob=True)
        except Exception as exc:  # large à dessein — voir la docstring d'à côté
            emitted[h.id] = _zone_failure_fragment(app, h, exc)
            continue
        for zone_id in _zone_ids_inside(root, among=seen):
            covered.add(zone_id)
            emitted.pop(zone_id, None)
            empreintes.pop(zone_id, None)
        # ── Une zone dont le rendu n'a pas bougé ne part pas ──────────
        #
        # Le rendu est déjà payé ici — c'est l'expédition, le gzip et le
        # morph qu'on épargne. Mesuré sur ``examples/messagerie`` le
        # 2026-09-08 : re-cliquer un fil déjà ouvert coûtait 9 461
        # octets et 50 ms ; 300 octets et 10 ms une fois les trois zones
        # tues. Un clic qui change vraiment quelque chose paie toujours
        # son plein tarif, et c'est normal.
        #
        # Le serveur ne garde RIEN : l'empreinte de référence vient du
        # client, qui porte le HTML en question. Une empreinte absente,
        # périmée ou mensongère ne peut donc que faire ré-expédier —
        # jamais taire à tort. C'est ce qui rend l'optimisation sûre par
        # construction plutôt que par prudence, et
        # ``test_an_unchanged_zone_is_not_shipped`` garde les deux sens.
        empreinte = _empreinte(html)
        empreintes[h.id] = empreinte
        if ctx.zone_hashes.get(h.id) == empreinte:
            emitted.pop(h.id, None)
            continue
        emitted[h.id] = html

    if empreintes:
        ctx.response_headers[HEADER_ZONE_HASHES] = ",".join(
            f"{zone_id}:{e}" for zone_id, e in empreintes.items()
        )

    pieces: list[str] = list(emitted.values())

    # Append the delta script tag if any client state mutated.
    delta_html = _render_delta(ctx)
    if delta_html:
        pieces.append(delta_html)

    # Drain the toast queue : ``ui.notification(...)`` calls during the
    # action collected dicts on ``ctx.notifications``. They ride ONE
    # ``<bz-patch>`` under the reserved ``_notifications`` key ; the
    # bridge forwards them to ``$bz.notify`` and the auto-mounted
    # toaster shows them. (Il n'y a pas de ``NotificationContainer`` —
    # ce nom, et l'ancien ``<script>`` inline, datent de la V2.)
    from bretzel.components.feedback.notification import serialise_pending

    notif_html = serialise_pending(ctx.notifications)
    if notif_html:
        pieces.append(notif_html)

    body = "\n".join(pieces)
    return RenderResult(
        body=body,
        status_code=200,
        headers=dict(ctx.response_headers),
        new_cookies=dict(ctx.new_cookies),
        deleted_cookies=set(ctx.deleted_cookies),
    )


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


def _lower(ctx: RenderContext) -> list[Node]:
    """Rabattre les enfants de racine en Nodes, une seule passe.

    ``is_rendering=True`` pour la marche : un Component construit
    *pendant* un ``render()`` (un ``ui.badge`` bâti dans le ``render=``
    d'une cellule) est alors traité en sous-composant et saute
    l'enregistrement racine. Sans ce garde, ils fuiraient en frères de
    la racine de section et ressortiraient en doublons dans le swap OOB.
    """
    produced: list[Node] = []
    previous_is_rendering = ctx.is_rendering
    ctx.is_rendering = True
    try:
        for child in ctx.root_children:
            rendered = child.render() if hasattr(child, "render") else child
            if isinstance(rendered, Node):
                produced.append(rendered)
    finally:
        ctx.is_rendering = previous_is_rendering
    return produced


def _zone_identity(handle: RefreshableHandle) -> dict[str, str]:
    """Les attributs d'identité d'une zone, tels que son rendu les pose.

    Passe par :func:`~bretzel.render.decorators.refreshable.zone_attrs`,
    la source unique — un fragment qui les recopierait dériverait, et
    c'est déjà arrivé (cf. ``_zone_failure_fragment``).

    Les attributs de souscription sont recalculés depuis la poignée
    plutôt que devinés : une zone ``broadcast=[State]`` qui les perdrait en
    tombant perdrait aussi son ``EventSource``, donc son temps réel, en
    plus de son rafraîchissement.
    """
    etats = handle._broadcast_qualnames()
    return zone_attrs(
        handle.id,
        subscribe_state_qualname=" ".join(etats) if etats else None,
        subscribe_url=handle._subscribe_url(etats) if etats else None,
    )


def _zone_failure_fragment(
    app: BretzelApp,
    handle: RefreshableHandle,
    exc: BaseException,
) -> str:
    """Le fragment qui remplace une zone dont le rendu a levé.

    **Pourquoi isoler plutôt que laisser remonter.** Une zone qui lève
    pendant le drain emportait la réponse entière en 500, et trois choses
    se perdaient d'un coup : les autres zones — valides, parfois déjà
    rendues — n'atteignaient jamais le navigateur ; htmx ne swappe pas
    sur un non-2xx, donc l'utilisateur voyait sa page ne rien faire ; et
    comme ``commit()`` vient APRÈS le drain, les mutations du handler
    étaient annulées. Mesuré le 2026-09-05 : un bug d'AFFICHAGE dans une
    zone annulait l'enregistrement demandé, sans un mot.

    Isoler règle les trois : le drain va au bout, donc le commit
    s'exécute, donc l'action de l'utilisateur tient.

    **Pourquoi une erreur VISIBLE et non la zone laissée telle quelle.**
    Une zone muette afficherait des données périmées dans une page qui a
    l'air correcte — le mensonge silencieux, précisément ce que ce dépôt
    refuse ailleurs. Mieux vaut dire où ça casse.

    **Le détail suit ``expose_errors``**, jamais ``debug`` : c'est déjà
    la ligne de partage du framework pour les pages d'erreur
    (``server/routing/errors.py``) — une décision d'exposition, pas de
    verbosité. Une seule politique, pas deux.

    ⚠️ Ne concerne QUE le drain (réponse d'action, refetch SSE, swap
    OOB). Une zone qui lève pendant le rendu d'une PAGE fait toujours
    remonter l'exception, où ``@error_page`` l'attend : là, il n'y a pas
    d'autre contenu valide à sauver.
    """
    _log.exception(
        "zone %s failed to render — isolated so the rest of the response "
        "survives", handle.id,
    )
    cfg = getattr(app, "config", None)
    if bool(getattr(cfg, "expose_errors", False)):
        message = f"{type(exc).__name__}: {exc}"
    else:
        message = "Cette zone n'a pas pu s'afficher."

    # On compose avec ``ui.alert`` plutôt que d'écrire le balisage à la
    # main : c'est le composant du dépôt pour dire ça, et une seconde
    # version divergerait de son thème au premier changement.
    from bretzel.components.feedback.alert import Alert  # cycle : render → components

    try:
        node: Node = Alert(message=message, color="error").render()
    except Exception:  # le secours du secours
        # Si même l'alerte casse, on ne relance pas : on rend du texte
        # nu. Une exception ici ferait exactement ce qu'on répare.
        _log.exception("zone %s : l'alerte de secours a levé aussi", handle.id)
        node = Element("span", {}, [message])

    # ⚠️ Le MÊME emballage que le rendu nominal, pas un ``<div>`` écrit à
    # la main. Le fragment a été composé en f-string pendant une journée,
    # et il omettait ``DATA_ZONE`` : après une erreur, la zone sortait de
    # l'énumération du navigateur, l'en-tête ``X-Bretzel-Zones`` ne la
    # portait plus, ``enqueue_deps`` la filtrait — elle ne se
    # rafraîchissait PLUS JAMAIS, jusqu'au rechargement complet et sans
    # un mot. Il perdait aussi le ``class="contents"`` de ``fuse_or_wrap``,
    # donc la zone en échec reprenait une boîte de disposition que sa
    # jumelle saine n'a pas.
    return serialize(
        fuse_or_wrap(
            [node],
            bz_id=handle.id,
            extra_attrs={**_zone_identity(handle), "hx-swap-oob": "morph"},
        )
    )


def _empreinte(html: str) -> str:
    """L'empreinte courte d'un fragment de zone.

    ``blake2s`` sur huit octets : on compare des chaînes rendues par le
    même processus à quelques millisecondes d'intervalle, pas des
    fichiers signés — la résistance aux collisions adverses n'est pas le
    sujet, la brièveté de l'en-tête si.
    """
    return hashlib.blake2s(html.encode("utf-8"), digest_size=8).hexdigest()


async def _render_one(
    app: BretzelApp,
    handle: RefreshableHandle,
    ctx: RenderContext,
    *,
    oob: bool,
) -> tuple[str, Node]:
    """Run ``handle.fn`` and return ``(HTML sérialisé, nœud racine)``.

    Le nœud est rendu en plus des octets pour que l'appelant sache ce
    que ce fragment CONTIENT — c'est ce qui lui permet de ne pas
    réexpédier une zone imbriquée. Le lire depuis le HTML marcherait
    aussi, mais chercher une sous-chaîne dans du balisage est une
    devinette là où l'arbre est une réponse.

    Drains ``ctx.root_children`` written by the function (the
    component-tree path), or accepts a directly-returned :class:`Node`
    as a convenience for tests / handler-level code that doesn't
    construct components.
    """
    # Snapshot the existing root children so we can isolate this
    # call's contribution and restore the outer scope after.
    saved_root = ctx.root_children
    ctx.root_children = []
    saved_parent_stack = ctx.parent_stack
    ctx.parent_stack = []

    # Render under the registry / context already set up by the caller.
    #
    # Go through ``handle()`` (not ``handle.fn()``) so the
    # :class:`RefreshableHandle.__call__` path runs : it creates a
    # ``_RefreshableSection``, pushes it onto ``parent_stack`` via
    # ``with section:``, and the user function's components register
    # as the section's children. Without this, the partial branch
    # bypassed the section, ``parent_stack`` stayed empty, and every
    # child's ``Component.__init__`` fell back to the literal "root"
    # ID prefix — producing IDs incompatible with what the initial
    # full-page render emitted under ``refresh_<hash>_*``. Idiomorph
    # keys morphs by id ; the mismatch silently downgraded to subtree
    # REPLACEMENT, destroying every ``bz-data`` scope on the swapped
    # subtree (Select / Switch / Checkbox / Input ``bz-model`` /
    # ``bz-attr`` bindings re-installed against fresh DOM nodes,
    # leaving any external scope reference dangling).
    #
    # Cf. probe ``probe_variant_roundtrip_consistent`` for the original
    # repro.
    with use_context(ctx), rendering_scope():
        # ``handle()`` runs through ``RefreshableHandle.__call__`` which
        # creates a ``_RefreshableSection``, pushes it on parent_stack,
        # and runs the user fn. Any value the fn returns directly is
        # attached to the section's children by __call__ ; nothing for
        # us to capture here.
        # Le corps SYNCHRONE d'une zone rendue seule — SSE ou OOB — part
        # sur le threadpool : sans ça une zone temps réel qui lit une
        # base bloquante gèlerait la boucle une fois par signal ET par
        # client abonné.
        #
        # ``is_async`` d'abord, parce que ``__call__`` est synchrone dans
        # les DEUX cas : pour un corps ``async`` il ne fait que poser la
        # section et ranger la coroutine (du bookkeeping de framework,
        # rien qui puisse bloquer), et le drain juste en dessous l'attend
        # sur la boucle. Le déléguer coûterait un saut de thread pour
        # rien.
        if handle.is_async:
            handle()
        else:
            await call_without_blocking(handle)
        # Une zone ``async`` n'a posé que sa section ; son corps attend
        # dans ``ctx.pending_async_zones``. Ce chemin-ci est celui du
        # rafraîchissement (OOB ou refetch SSE) : ne pas drainer ici
        # rendrait la zone pleine au premier affichage et VIDE à chaque
        # refresh — la moitié la plus difficile à voir.
        await drain_pending_async_zones(ctx)

    # Drain the section (now the single root child) — its ``render``
    # produces an Element whose ``bz-id`` already matches handle.id,
    # so we don't need to ``fuse_or_wrap`` here ; doing so would
    # double-wrap. We just merge the ``hx-swap-oob`` extra attr when
    # appropriate.
    #
    #
    # Le rabattage est DÉLESTÉ, comme le corps : ``render()`` rappelle du
    # code d'app (le ``rows=`` d'un ``ui.datatable``, le ``render=`` d'une
    # colonne), et le framework EXIGE que ce ``rows=`` soit un ``def`` —
    # il refuse une coroutine. Le laisser ici le ferait tourner sur la
    # boucle, une fois par signal SSE et par client abonné.
    produced = await call_without_blocking(_lower, ctx)

    # Restore caller's scope.
    ctx.root_children = saved_root
    ctx.parent_stack = saved_parent_stack

    extra: dict[str, Any] | None = None
    if oob:
        # Morph OOB swap via Idiomorph (loaded as an htmx-2 extension —
        # ``hx-ext="morph"`` is wired on ``<body>`` in the shell so
        # every swap goes through it). The morph matches by ``id``,
        # preserves the existing wrapper element + its descendants
        # whose ids match, and only updates attributes / content
        # where they differ. Critical consequence : ``bz-data``
        # scopes on the swapped subtree (accordion, popover, tabs,
        # drawer, …) survive intact — the user's locally-collapsed
        # buckets, open popovers, selected tab indicator, etc. don't
        # reset on every refresh the way a plain outerHTML swap did.
        extra = {"hx-swap-oob": "morph"}

    # Common case after the ``handle()`` fix : ``produced`` is a single
    # Element whose ``bz-id`` is already ``handle.id`` (the
    # ``_RefreshableSection`` rendered correctly). Just merge the
    # extra OOB attr — no fuse_or_wrap pass needed.
    if (
        len(produced) == 1
        and isinstance(produced[0], Element)
        and produced[0].attrs.get(BZ_ID_ATTR) == handle.id
    ):
        section_el = produced[0]
        if extra:
            merged = {**section_el.attrs, **extra}
            section_el = Element(
                tag=section_el.tag,
                attrs=merged,
                children=section_el.children,
            )
        return serialize(section_el), section_el

    # Fallback (defensive — shouldn't fire after the ``handle()`` fix
    # unless the user did something unusual). Stamp via fuse_or_wrap
    # like before.
    fused = fuse_or_wrap(
        produced,
        bz_id=handle.id,
        extra_attrs=extra,
    )
    return serialize(fused), fused


def _zone_ids_inside(root: Node, *, among: set[str]) -> set[str]:
    """Les zones de ``among`` que ce fragment porte DÉJÀ, racine exclue.

    ``among`` est la file de rafraîchissement : on ne cherche pas « les
    zones » mais « celles qu'on allait aussi expédier ». C'est ce qui
    rend le filtre sûr malgré un ``bz-id`` qui n'appartient pas qu'aux
    zones — tout composant que le runtime doit retrouver en porte un
    (``Component.emit_attrs``). Un id de composant ne peut pas se
    trouver dans la file, donc l'intersection tranche.

    Le parcours s'ARRÊTE sous un ``bz-teleport`` : le runtime déplace le
    contenu de ce ``<template>`` sous ``<body>`` (les panneaux d'overlay
    ancrés — Tooltip, Popover, Dropdown). Une zone qui vit là-dedans
    n'est plus, dans le DOM vivant, un descendant de l'ancêtre qui la
    porte dans le SSR : morpher l'ancêtre ne l'atteindrait pas, et lui
    retirer son fragment la figerait. C'est une DÉCLARATION lue dans
    l'arbre, pas une devinette sur la mise en page.

    ⚠️ Un descendant caché dans un nœud :class:`Html` (du balisage brut)
    ne serait pas vu. Aucun chemin ne produit ça aujourd'hui — une zone
    rend un :class:`Element` — et la table d'abstentions de la gate le
    déclare plutôt que de faire semblant de le couvrir.
    """
    found: set[str] = set()
    stack: list[Node] = list(getattr(root, "children", ()) or ())
    while stack:
        node = stack.pop()
        if isinstance(node, Element):
            if TELEPORT_ATTR in node.attrs:
                continue
            zone_id = node.attrs.get(BZ_ID_ATTR)
            if zone_id in among:
                found.add(zone_id)
        stack.extend(getattr(node, "children", ()) or ())
    return found


def _render_delta(ctx: RenderContext, *, include_unchanged: bool = False) -> str:
    """Build the ``<bz-patch>`` tag for the response (V3 wire format).

    Default mode walks the registry's *dirty* :class:`ClientState`
    instances and serialises their patches — the action-response flow,
    where the runtime already has fresh state for every instance and
    only the changed ones need patching.

    ``include_unchanged=True`` switches to the partial-nav flow : every
    instance the registry knows about is emitted, dirty or not. Used
    when a partial response lands on the runtime for the first time
    (htmx swap of the outlet) and the new page references ClientStates
    the runtime has never seen.

    Returns an empty string when nothing needs sending (callers can
    decide not to append anything).
    """
    if ctx.state_registry is None:
        return ""
    clients = [
        inst
        for inst in ctx.state_registry._instances.values()
        if isinstance(inst, ClientState) and (include_unchanged or inst._dirty)
    ]
    if not clients:
        return ""
    return serialize_patch(clients, include_unchanged=include_unchanged)


# ───────────────────────────────────────────────────────────────────────────
# Convenience for tests / Layer 6
# ───────────────────────────────────────────────────────────────────────────


async def drain_refresh_queue(
    app: BretzelApp,
    ctx: RenderContext,
) -> RenderResult | None:
    """Render every queued refreshable in one OOB-batched response.

    Returns ``None`` when there's nothing to send back at all : no
    refreshables, no client-state delta, no pending toasts. Layer 6
    can then send an empty 204 / no-op response without burning bytes.
    """
    if not ctx.refresh_queue:
        # No refreshable to render — but the response may still need
        # to carry a client-state delta and / or pending toasts. Build
        # the body from those alone.
        from bretzel.components.feedback.notification import serialise_pending

        pieces: list[str] = []
        delta_html = _render_delta(ctx)
        if delta_html:
            pieces.append(delta_html)
        notif_html = serialise_pending(ctx.notifications)
        if notif_html:
            pieces.append(notif_html)
        if not pieces:
            return None
        return RenderResult(
            body="\n".join(pieces),
            status_code=200,
            headers=dict(ctx.response_headers),
            new_cookies=dict(ctx.new_cookies),
            deleted_cookies=set(ctx.deleted_cookies),
        )

    primary = ctx.refresh_queue[0]
    extras = ctx.refresh_queue[1:]
    return await render_partial(app, primary, ctx=ctx, extra_handles=extras)

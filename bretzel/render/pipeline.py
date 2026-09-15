"""Full-page render orchestration — turns a ``@page`` function into HTML bytes.

This is the conductor : it constructs a :class:`RenderContext`, runs
the page function under the right state / rendering scopes, fuses the
produced node tree, builds the bootstrap envelope from the registry,
and lets :func:`default_shell` assemble the document.

The function is async so layered concerns (state hydration from
backend, custom middleware that wants to ``await``) can run without
fighting the framework. Layer 6 (server) is the only caller in
production ; for unit tests the function is invoked directly with a
hand-built :class:`RenderContext`.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any
from urllib.parse import parse_qsl, urlencode

from bretzel.core import call_without_blocking
from bretzel.core.serialize import serialize
from bretzel.core.tree import Node
from bretzel.render.context import (
    RenderContext,
    page_scope_of,
    use_context,
)
from bretzel.render.decorators.page import PageMeta
from bretzel.render.decorators.refreshable import drain_pending_async_zones
from bretzel.render.partials import RenderResult
from bretzel.render.shell import default_shell
from bretzel.render.types import BretzelApp
from bretzel.runtime.envelope import serialize_envelope
from bretzel.runtime.protocol import outlet_id_for
from bretzel.state.registry import use_registry
from bretzel.state.scopes.client import ClientState, rendering_scope

# ───────────────────────────────────────────────────────────────────────────
# Public entry — render_page
# ───────────────────────────────────────────────────────────────────────────


async def render_page(
    app: BretzelApp,
    page_fn: Callable[..., Any],
    *,
    ctx: RenderContext,
    path_params: dict[str, Any] | None = None,
) -> RenderResult:
    """Render a full HTML5 document for ``page_fn``.

    Caller responsibility : ``ctx`` must already carry the request
    references (state registry, parsed client payload, session id,
    csrf token, …). Layer 6's ``RenderContextMiddleware`` populates
    those before calling here.

    Returns a :class:`RenderResult` ready to wrap in a Starlette
    HTML response — body, status, headers, cookie deltas.
    """
    meta = _meta_of(page_fn)
    path_params = path_params or {}
    ctx.page_scope = page_scope_of(ctx)

    # ── 1. Run the page function under the active scopes ─────────────────
    #
    # Two scopes compose : the state registry binds for ``MyState()``
    # cache lookups, and the rendering scope flips the flag that makes
    # ``ClientState`` field reads return ``ClientBinding`` wrappers.
    registry_cm = (
        use_registry(ctx.state_registry)
        if ctx.state_registry is not None
        else nullcontext()
    )

    with use_context(ctx), registry_cm, rendering_scope():
        produced = await _invoke_page(page_fn, meta, path_params, ctx)

    # ── 2. Commit dirty server-state to backend ─────────────────────────
    #
    # We do NOT add a page-level ``bz-id`` wrapper here — the
    # ``bz-page-<uuid>`` wrapper added by the shell already gives
    # idiomorph the per-render identity it needs (cf. CR-3). Fusion is
    # for refreshable sub-trees, not the page envelope itself.
    if ctx.state_registry is not None:
        await ctx.state_registry.commit()

    body_html = "".join(serialize(node) for node in produced)

    # ── Partial-nav short-circuit ──────────────────────────────────────
    # When ``ctx.is_partial`` was flipped by the route handler (htmx
    # internal link with an HX-Target matching the layout's outlet),
    # the layout was already skipped in ``_invoke_page`` ; here we
    # also skip the shell + envelope. The body bytes are dropped
    # straight into the outlet via ``hx-swap=morph:innerHTML``.
    if ctx.is_partial:
        # ``ui.title("…")`` in the page body writes ``ctx.head_title``
        # and supersedes the decorator's ``title=``. Same precedence
        # on the full-doc branch below.
        title = ctx.head_title or meta.title or "Bretzel"
        # Push a small ``HX-Trigger`` so the client can update its
        # ``<title>`` (the partial response doesn't touch <head>).
        headers = dict(ctx.response_headers)
        try:
            import json as _json
            headers["HX-Trigger"] = _json.dumps({"bretzel:title": title})
        except Exception:
            pass
        # First-time partial nav : the runtime has never seen the
        # ClientStates this page references. Without seeding them via
        # un ``<bz-patch>``, ``bz-*`` bindings like ``$bz.state.X.default.f``
        # throw "Cannot read properties of undefined". The shared
        # ``_render_delta`` helper builds the script tag for us ;
        # ``include_unchanged=True`` widens the filter from dirty-only
        # (action flow) to every-registered (partial-nav flow).
        from bretzel.render.partials import _render_delta
        body_html = _render_delta(ctx, include_unchanged=True) + body_html
        return RenderResult(
            body=body_html,
            status_code=200,
            headers=headers,
            new_cookies=dict(ctx.new_cookies),
            deleted_cookies=set(ctx.deleted_cookies),
        )

    # ── 3. Build the bootstrap envelope from the registry + theme ───────
    envelope_json = _build_envelope_json(app, ctx)

    # ── 4. Assemble the document via the configured shell ───────────────
    shell_fn = meta.shell or default_shell
    # ``ui.title("…")`` in the page body writes ``ctx.head_title`` ;
    # it supersedes the decorator's ``title=`` so the deepest call
    # wins. Falls back to the decorator value, then to ``"Bretzel"``.
    title = ctx.head_title or meta.title or "Bretzel"

    cfg = getattr(app, "config", None)
    # Axe assets / cache (pipeline CSS, cache-bust, no-store), pas
    # l'axe diagnostics : ``config.debug`` ne gouverne que la
    # verbosité depuis la séparation des axes.
    dev = getattr(cfg, "is_dev", False)
    # Le pipeline CSS effectif — ``browser`` inline le compilateur
    # navigateur, ``build`` lie le style.css compilé. C'est le SEUL
    # réglage qui change ce qui est rendu, d'où sa lecture explicite.
    # ``_css_browser_fallback`` est posé au démarrage : il vaut le
    # pipeline demandé, OU ``True`` si la compilation a échoué et qu'on
    # est retombé sur le navigateur.
    browser_css = getattr(
        app, "_css_browser_fallback",
        getattr(cfg, "css_pipeline", "browser") == "browser",
    )
    # Cache-busting : in dev, we already set ``Cache-Control: no-store``
    # on runtime.js / theme.css, but a browser that previously cached
    # those URLs as ``immutable`` (the old default) will refuse to
    # refetch even on hard reload. Appending the process-start
    # timestamp to the asset URL forces the browser to treat them as
    # NEW resources and bypasses the stale ``immutable`` entry.
    cache_bust = (
        getattr(app, "_cache_bust", None) if dev else None
    )

    document = shell_fn(
        body_html,
        envelope_json,
        page_uuid=ctx.page_uuid,
        title=title,
        description=meta.description,
        # ``default_shell`` porte ce paramètre depuis toujours et
        # PERSONNE ne le passait : toute page Bretzel expédiait
        # ``<html lang="en">``, y compris les apps françaises — un
        # lecteur d'écran y choisit sa voix, et le navigateur sa
        # coupure de mots.
        lang=ctx.lang,
        head_extras=ctx.head_extras,
        browser_css=browser_css,
        # Variante SANS la safelist : ce bloc n'est lu que par le
        # compilateur navigateur, qui scanne le DOM. Cf. ``_resolve_theme``.
        theme_css_content=getattr(app, "_theme_css_inline", "") or "",
        cache_bust=cache_bust,
        # ``None`` = la marque du framework. Le ``getattr`` couvre les
        # coques de test qui passent un faux ``app`` sans config.
        favicon=getattr(cfg, "favicon", None),
        mobile_breakpoint=getattr(cfg, "mobile_breakpoint", 768),
        nav_progress=getattr(cfg, "nav_progress", True),
        # Le pipeline ne connaît PAS ``PWA`` (il est dans ``server``,
        # au-dessus de ``render`` dans le DAG) : il reçoit deux
        # chaînes, ce qui suffit et garde les couches séparées.
        manifest_url=getattr(cfg, "_manifest_url", None),
        theme_color=getattr(getattr(cfg, "pwa", None), "theme_color", None),
    )

    headers = dict(ctx.response_headers)
    # Dev : never let the browser cache the full document. Every
    # page carries baked-in IDs / signatures / cache-bust hashes
    # that drift across server restarts ; a cached HTML paired
    # with a fresh ``runtime.js`` (which IS ``no-store``) makes
    # actions 400-out half the time on stale signature mismatch.
    # Prod can opt in to caching via custom headers.
    if dev and "cache-control" not in {k.lower() for k in headers}:
        headers["Cache-Control"] = "no-store"

    return RenderResult(
        body=document,
        status_code=200,
        headers=headers,
        new_cookies=dict(ctx.new_cookies),
        deleted_cookies=set(ctx.deleted_cookies),
    )


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


def _meta_of(page_fn: Callable[..., Any]) -> PageMeta:
    """Extract the ``PageMeta`` attached by the ``@page`` decorator.

    Tests sometimes pass an undecorated function ; we fabricate a
    minimal meta in that case so the pipeline stays usable in
    isolation without re-implementing the decorator.
    """
    meta: PageMeta | None = getattr(page_fn, "_bz_page", None)
    if meta is None:
        meta = PageMeta(
            path="",
            layout=None,
            title=None,
            description=None,
            shell=None,
            methods=("GET",),
            signature=inspect.signature(page_fn),
        )
    return meta


async def _invoke_page(
    page_fn: Callable[..., Any],
    meta: PageMeta,
    path_params: dict[str, Any],
    ctx: RenderContext,
) -> list[Node]:
    """Call the page function with the right kwargs, drain ``root_children``.

    Path-template parameters (``/users/{id}``) flow in via
    ``path_params``. Anything else the signature mentions is bound
    only if a name match is available — state injection by parameter
    type is deferred to a later iteration (handlers can still call
    ``MyState()`` inside, which goes through the registry).

    When ``meta.layout`` is set, the page runs **inside** the layout's
    outlet : the layout function builds the frame (sidebar, header,
    …) and calls ``ui.outlet()`` once, the page's top-level
    ``ui.*()`` calls attach to that outlet instead of the page root.
    Nested layouts (``@layout(parent=app_layout)``) chain
    outer→inner — page lands in the innermost outlet.

    When ``ctx.is_partial`` is set, the layout chain is **sliced** to
    drop everything outside the layout whose outlet matches
    ``ctx.partial_target``. What remains renders into the targeted
    outlet — typically the innermost match (intra-section nav → empty
    chain → page-only render), but cross-section nav lands further out
    (e.g. a sidebar in the outer ``shell`` jumping between sibling
    sub-layouts) and the chain keeps the sub-layouts that need to be
    re-rendered fresh.
    """
    kwargs: dict[str, Any] = {}
    for name in meta.signature.parameters:
        if name in path_params:
            kwargs[name] = path_params[name]

    full_chain = _resolve_layout_chain(meta.layout)
    if ctx.is_partial:
        layout_chain = _slice_chain_for_partial(full_chain, ctx.partial_target)
    else:
        layout_chain = full_chain

    # ── L'identité ne dépend pas du chemin d'arrivée ──────────────────
    #
    # Un rendu partiel ne rend PAS les layouts extérieurs : ils sont déjà
    # dans le navigateur. Sans rien sur ``parent_stack``, les composants
    # de la page repartaient donc du littéral ``"root"``
    # (``component.py``) au lieu de descendre de l'outlet visé — le même
    # accordéon rendait ``outlet_shell_…_accordion_0`` au chargement
    # direct et ``root_…_accordion_0`` après une navigation boostée.
    #
    # ``bz-id`` est la clé de DEUX mécanismes : l'appariement idiomorph
    # et la résolution de scope. Un id qui change selon le chemin
    # d'arrivée fait donc dégrader chaque navigation en REMPLACEMENT de
    # sous-arbre — tout ``bz-data`` de la région échangée est détruit
    # puis reconstruit au lieu d'être fusionné.
    #
    # ⚠️ C'est une RÉCIDIVE : ``render/partials.py`` documente le même
    # défaut, trouvé et réparé pour les partials de ``@refreshable``
    # (« every child's ``Component.__init__`` fell back to the literal
    # "root" ID prefix »). Le chemin de la NAVIGATION ne l'avait jamais
    # reçu.
    #
    # Le remède est le même : semer la pile avec un parent portant l'id
    # de la cible. Le routeur l'a déjà résolue
    # (``server/routing/pages.py`` pose ``ctx.partial_target`` depuis
    # l'en-tête ``HX-Target``), donc on ne devine rien.
    seed = (
        _PartialRoot(ctx.partial_target, page_scope=ctx.child_scope_root)
        if ctx.is_partial and ctx.partial_target
        else None
    )
    if seed is not None:
        ctx.parent_stack.append(seed)

    try:
        if not layout_chain:
            # No layout — page builds the tree at root. Capture the
            # return value so a function that yields a single Node (vs.
            # registering children via ``with`` / ui.*) still works.
            page_result = await _call(page_fn, kwargs)
            # Les zones ``async`` posées par le corps ont laissé leur
            # section dans l'arbre et leur coroutine en attente : c'est
            # ici qu'on les attend, avant de descendre l'arbre en Nodes.
            await drain_pending_async_zones(ctx)
            # Le rabattage est DÉLESTÉ lui aussi : ``render()`` rappelle
            # du code d'app (le ``rows=`` d'un ``ui.datatable``, le
            # ``render=`` d'une colonne) et le framework EXIGE que ce
            # ``rows=`` soit un ``def`` — il REFUSE une coroutine. Le
            # laisser sur la boucle rendait donc bloquant, par
            # construction, le cas le plus courant d'une vraie app.
            return await call_without_blocking(
                _drain, ctx, roots=_roots(ctx, seed), trailing=page_result
            )
        return await _render_chain(
            ctx, page_fn, kwargs, layout_chain, seed=seed
        )
    finally:
        if seed is not None and ctx.parent_stack and ctx.parent_stack[-1] is seed:
            ctx.parent_stack.pop()


class _PartialRoot:
    """Le parent d'id que le rendu partiel n'a pas rendu.

    Il **n'apparaît jamais dans la sortie** : htmx morphe l'``innerHTML``
    de l'outlet, donc le fragment doit contenir ses ENFANTS, pas lui.
    C'est ce qui le distingue de ``_RefreshableSection``, le stand-in
    jumeau côté ``@refreshable``, qui doit se rendre parce que le swap
    OOB vise son id à lui.

    Le protocole d'un parent, lu dans ``component.py`` : ``id`` et
    ``add_child`` pour l'enregistrement, **et ``_children``** — que
    ``_detach_from_parent`` fouille pour retirer un composant adopté
    comme slot. Ce troisième membre ne se voyait pas en cherchant
    ``parent_stack[-1]`` : le détachement itère la pile ENTIÈRE. Sans
    lui, toute page contenant un ``icon=``/``prefix=`` levait un
    ``AttributeError`` au premier rendu partiel.

    D'où un objet nu plutôt qu'un ``Component`` : construire un vrai
    composant ici l'enregistrerait comme enfant de racine et le ferait
    rendre — or ce parent-ci ne doit produire aucun octet.
    """

    __slots__ = ("_children", "child_scope_id", "id")

    def __init__(self, outlet_id: str, *, page_scope: str = "") -> None:
        self.id = outlet_id
        # ⚠️ Doit reproduire EXACTEMENT ce que ``Outlet.child_scope_id``
        # calcule sur le chemin complet : c'est la condition pour que les
        # deux chemins d'arrivée — chargement direct et navigation boostée
        # — produisent les mêmes ``bz-id``, ce que
        # ``test_partial_nav_keeps_identity`` garde.
        self.child_scope_id = f"{outlet_id}{page_scope}"
        self._children: list[Any] = []

    @property
    def children(self) -> list[Any]:
        """Alias lisible pour le drain — même liste, pas une copie."""
        return self._children

    def add_child(self, child: Any) -> None:
        self._children.append(child)


def _roots(ctx: RenderContext, seed: _PartialRoot | None) -> list[Any]:
    """Où les enfants de premier niveau ont atterri.

    Avec une graine, tout ce que la page enregistre passe par son
    ``add_child`` et ``ctx.root_children`` reste vide — le drain doit
    donc lire la graine, sinon le fragment part vide.
    """
    return seed.children if seed is not None else ctx.root_children


async def _render_chain(
    ctx: RenderContext,
    page_fn: Callable[..., Any],
    kwargs: dict[str, Any],
    layout_chain: list[Callable[..., Any]],
    *,
    seed: _PartialRoot | None,
) -> list[Node]:
    """Rendre une chaîne de layouts non vide, puis la page dedans.

    Extrait de :func:`_invoke_page` le 2026-08-13, quand la
    graine d'identité a rendu son corps conditionnel : la fonction
    portait deux chemins de retour et un ``try`` de plus, et les
    imbriquer aurait rendu illisible quel ``finally`` dépile quoi.
    """
    # Layout chain : outermost first. We run them one by one ; each
    # layout's ``ui.outlet()`` appears in the active parent_stack at
    # render time (its constructor pushes to the topmost parent).
    # After running the outermost layout, we locate the deepest
    # outlet and continue inside it with the next layout (or the
    # page, when we've exhausted the chain).
    saved_layout_stack = list(ctx.layout_stack)
    try:
        # Step into the outermost layout. ``ctx.layout_stack`` carries
        # the layout names so Outlet (and SidebarItem) can derive
        # their ids / hx-targets correctly while the layout body
        # runs.
        first = layout_chain[0]
        ctx.layout_stack.append(first.__name__)
        await _call(first, {})

        # Inner layouts (and finally the page) all need to land
        # inside the most recently rendered Outlet. We locate it
        # once, attach successive bodies to it, then move to its
        # own Outlet (if it spawned one) for the next iteration.
        #
        # ``_roots`` et non ``ctx.root_children`` : sous une graine
        # d'identité, le layout le plus extérieur s'est enregistré chez
        # ELLE, et chercher l'outlet à la racine ne trouverait rien —
        # « Layout 'x' did not call ui.outlet() » sur un layout qui l'a
        # parfaitement appelé.
        current_outlet = _find_deepest_outlet(_roots(ctx, seed))
        if current_outlet is None:
            raise RuntimeError(
                f"Layout '{first.__name__}' did not call ui.outlet() — "
                "every layout must declare exactly one outlet."
            )

        for inner in layout_chain[1:]:
            ctx.layout_stack.append(inner.__name__)
            # Run the inner layout with the outer's outlet as the
            # active parent so its components attach there.
            ctx.parent_stack.append(current_outlet)
            try:
                await _call(inner, {})
            finally:
                ctx.parent_stack.pop()
            next_outlet = _find_deepest_outlet(current_outlet._children)
            if next_outlet is None:
                raise RuntimeError(
                    f"Layout '{inner.__name__}' did not call ui.outlet() — "
                    "nested layouts must each declare exactly one outlet."
                )
            current_outlet = next_outlet

        # Run the page inside the innermost outlet.
        ctx.parent_stack.append(current_outlet)
        try:
            page_result = await _call(page_fn, kwargs)
        finally:
            ctx.parent_stack.pop()

        # Attach a bare-Node / Component return value to the outlet
        # too — same fallback the no-layout path supports.
        if isinstance(page_result, Node) or (page_result is not None and hasattr(page_result, "render")):
            current_outlet.add_child(page_result)

        # DANS le ``try``, donc avant que le ``finally`` ne restaure
        # ``layout_stack`` : un corps de zone construit des composants, et
        # certains (Outlet, SidebarItem) dérivent leur id de cette pile.
        # La drainer dehors leur donnerait des ids d'une autre profondeur.
        await drain_pending_async_zones(ctx)

    finally:
        # Pop everything we pushed, restore the original stack so
        # an exception doesn't leave the context in a half-state.
        ctx.layout_stack = saved_layout_stack

    return await call_without_blocking(_drain, ctx, roots=_roots(ctx, seed))


async def _call(
    fn: Callable[..., Any], kwargs: dict[str, Any]
) -> Any:
    """Invoke ``fn(**kwargs)`` — awaited if async, délesté si sync.

    Un corps de page ou de layout SYNCHRONE part sur le threadpool (cf.
    ``core/invoke``), sinon un ``def home()`` qui lit une base bloquante
    gèle la boucle.

    Un saut par CORPS, pas un par rendu : la chaîne de layouts passe ici
    une fois chacun, la page une fois, et le rabattage une fois encore.
    Les zones ``@refreshable``, elles, sont gratuites — leur ``__call__``
    est synchrone par contrat, donc elles tournent dans le thread de
    celui qui les appelle.
    """
    return await call_without_blocking(fn, **kwargs)


def _drain(
    ctx: RenderContext,
    *,
    roots: list[Any] | None = None,
    trailing: Any = None,
) -> list[Node]:
    """Walk the top-level children once and lower everything to Nodes.

    ``roots`` défaut à ``ctx.root_children``. Il est explicite quand un
    rendu partiel a semé un parent d'identité : les enfants sont alors
    passés par ``add_child`` de la graine, et la racine est vide.

    ``trailing`` is the page function's return value — pages that
    return a Node / Component directly (vs. registering children
    through ``with`` blocks) flow it in here so it lands in the
    final tree.

    ``is_rendering=True`` for the walk : Components that nested
    helpers build inline (e.g. a ``ui.badge`` returned from a table's
    ``render=`` cell callback) must skip root-children registration
    so they don't appear twice. Restore the previous value on the
    way out so an outer pipeline pass isn't poisoned.
    """
    # L'arbre de composants est complet ICI, et pas avant : le corps de
    # la page a fini, les zones ``async`` sont drainées, et la chaîne de
    # layouts est refermée sur l'outlet. C'est donc le seul point d'où
    # une question de PLACEMENT se répond juste — une barre ``sticky``
    # ne peut pas savoir à sa construction qu'un ``ui.viewport`` va
    # venir, ni quel est son vrai parent de disposition.
    #
    # Le test tient en un ``if`` sur une liste vide : rien ne s'inscrit
    # tant qu'une page n'a ni ``ui.bottom_bar`` ni ``ui.navbar(sticky=)``.
    # Import différé — ``render`` ne remonte vers ``components`` qu'ici,
    # au point d'usage (cf. principe 5 du charter).
    if ctx.sticky_bars:
        from bretzel.components.base._wiring import (
            check_sticky_bar_placement,
        )

        bars, ctx.sticky_bars = ctx.sticky_bars, []
        check_sticky_bar_placement(
            ctx.root_children if roots is None else roots, bars
        )

    # Meme etage, meme raison : « a quelle barre ce declencheur
    # parle-t-il ? » et « cette barre a-t-elle un moyen de revenir ? »
    # ne se repondent qu'une fois la page batie. Resoudre d'abord —
    # c'est la resolution qui rend une barre atteignable.
    if ctx.sidebars or ctx.sidebar_triggers:
        from bretzel.components.base._wiring import (
            check_sidebars_are_reachable,
            wire_sidebar_triggers,
        )

        triggers, ctx.sidebar_triggers = ctx.sidebar_triggers, []
        sidebars, ctx.sidebars = ctx.sidebars, []
        wire_sidebar_triggers(triggers, sidebars)
        check_sidebars_are_reachable(sidebars)

    produced: list[Node] = []
    previous_is_rendering = ctx.is_rendering
    ctx.is_rendering = True
    try:
        for child in (ctx.root_children if roots is None else roots):
            rendered = child.render() if hasattr(child, "render") else child
            if isinstance(rendered, Node):
                produced.append(rendered)
        if isinstance(trailing, Node):
            produced.append(trailing)
        elif trailing is not None and hasattr(trailing, "render"):
            rendered = trailing.render()
            if isinstance(rendered, Node):
                produced.append(rendered)
    finally:
        ctx.is_rendering = previous_is_rendering
    return produced


def _resolve_layout_chain(
    layout: Callable[..., Any] | None,
) -> list[Callable[..., Any]]:
    """Walk the layout decorator's ``parent=`` chain, outermost first.

    The :func:`layout` decorator stamps a ``_bz_layout`` meta
    on each layout function ; ``parent`` is the enclosing layout
    (or ``None`` for the root). We follow this chain and return the
    list in render order — outer-most first, innermost last. ``None``
    input returns an empty list (no layout at all).
    """
    if layout is None:
        return []
    chain: list[Callable[..., Any]] = []
    seen: set[Callable[..., Any]] = set()
    current: Callable[..., Any] | None = layout
    while current is not None:
        if current in seen:
            raise RuntimeError(
                f"Layout cycle detected through '{current.__name__}'."
            )
        seen.add(current)
        chain.append(current)
        meta = getattr(current, "_bz_layout", None)
        current = getattr(meta, "parent", None) if meta else None
    chain.reverse()
    return chain


def _slice_chain_for_partial(
    full_chain: list[Callable[..., Any]],
    partial_target: str | None,
) -> list[Callable[..., Any]]:
    """Return the sub-chain to render for a partial nav.

    ``full_chain`` is outermost-first ; ``partial_target`` is the
    ``HX-Target`` value the browser sent (typically
    ``outlet_<layout>``). We slice off everything up to and including
    the matched layout — what remains are the inner sub-layouts (plus
    the page) that need to render INTO the targeted outlet.

    Three common cases :

    - **Intra-section nav** : target is the innermost layout's outlet
      → match at the last index → slice returns ``[]`` (page-only
      render lands directly in the targeted outlet).
    - **Cross-section nav** : target is an ancestor (e.g. a sidebar
      in the outer ``shell`` jumping between ``admin_shell`` and
      ``billing_shell`` siblings) → slice returns the inner sub-chain
      so the sub-layout re-renders fresh under the shared outlet.
    - **No match / empty target** : returns ``[]`` so the pipeline
      degrades gracefully to a page-only render rather than 500ing.
    """
    if not partial_target:
        return []
    for i, fn in enumerate(full_chain):
        if partial_target == outlet_id_for(fn.__name__):
            return full_chain[i + 1:]
    return []


def _find_deepest_outlet(children: list[Any]) -> Any | None:
    """Depth-first walk to find the deepest :class:`Outlet` instance.

    Layouts call ``ui.outlet()`` exactly once at the position where
    the next layer should render. When layouts nest, the inner one
    is invoked inside the outer outlet — so the deepest outlet in
    the current tree is always the target for the next body.
    """
    from bretzel.components.meta.outlet.outlet import Outlet

    deepest: Outlet | None = None

    def walk(node: Any) -> None:
        nonlocal deepest
        if isinstance(node, Outlet):
            deepest = node
        kids = getattr(node, "_children", None)
        if kids:
            for child in kids:
                walk(child)

    for child in children:
        walk(child)
    return deepest


def _build_envelope_json(app: BretzelApp, ctx: RenderContext) -> str:
    """Build the ``<bz-envelope>`` JSON payload.

    Pulls every :class:`ClientState` instance out of the active registry.
    The runtime hydrate depuis ça au boot — il n'y lit que
    ``client_state`` / ``csrf`` / ``endpoints`` (``00_index.js``).

    ⚠️ Cette fonction extrayait aussi la ``palette`` du thème et la
    poussait dans l'envelope : 2 197 octets par page que rien ne lisait.
    Retiré le 2026-08-01 — cf. le commentaire du champ dans
    ``runtime/envelope.py``.
    """
    clients: list[ClientState] = []
    if ctx.state_registry is not None:
        clients = [
            inst
            for inst in ctx.state_registry._instances.values()
            if isinstance(inst, ClientState)
        ]

    return serialize_envelope(
        clients, ctx.csrf_token, page_id=ctx.page_uuid,
        address=_corrected_address(ctx),
    )


def _corrected_address(ctx: RenderContext) -> str:
    """L'adresse JUSTE quand celle du navigateur est incomplète, sinon ``""``.

    Le cas : un état de portée ``session`` se souvient d'un tri ou d'un
    filtre par-delà les navigations. Revenir sur ``/comptes`` nu rend
    alors une vue triée sous une adresse qui n'en dit rien — et le lien
    copié montre autre chose chez qui le reçoit. Deux personnes « sur la
    même page », rien qui le signale.

    On est APRÈS le rendu du corps, donc tout état que la page a monté
    est déjà résolu : c'est ce qui rend le calcul possible ici et nulle
    part avant.

    ⚠️ Rien n'est corrigé quand l'adresse est déjà juste — ni entrée
    d'historique, ni écriture. Et rien du tout pour une app qui n'a
    déclaré aucun champ adressable, ce qui est le défaut.
    """
    registry = ctx.state_registry
    request = getattr(ctx, "request", None)
    if registry is None or request is None:
        return ""
    try:
        declared = registry.addressable_param_names()
    except Exception:
        # Une déclaration invalide lèvera au rendu, là où le message est
        # utile — pas ici, où elle casserait la page entière pour une
        # correction d'adresse.
        return ""
    if not declared:
        return ""

    current = dict(parse_qsl(
        getattr(getattr(request, "url", None), "query", "") or "",
        keep_blank_values=True,
    ))
    wanted = dict(current)
    for name in declared:
        wanted.pop(name, None)
    wanted.update(registry.addressable_params())
    if wanted == current:
        return ""

    path = getattr(getattr(request, "url", None), "path", "") or ""
    query = urlencode(wanted)
    return f"{path}?{query}" if query else path

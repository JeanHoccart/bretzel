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
    # Assets / cache axis (CSS pipeline, cache-bust, no-store), not the
    # diagnostics axis: ``config.debug`` governs only verbosity since the
    # axes were separated.
    dev = getattr(cfg, "is_dev", False)
    # The effective CSS pipeline — ``browser`` inlines the browser
    # compiler, ``build`` links the compiled style.css. It is the ONLY
    # setting that changes what is rendered, hence its explicit read.
    # ``_css_browser_fallback`` is set at startup: it holds the requested
    # pipeline, OR ``True`` if compilation failed and we fell back on the
    # browser.
    browser_css = getattr(
        app, "_css_browser_fallback",
        getattr(cfg, "css_pipeline", "browser") == "browser",
    )
    # Cache-busting is required in BOTH modes.  Production deliberately
    # serves the framework bundle as immutable, so an unversioned URL would
    # otherwise let a CDN pair fresh HTML with an old style.css/runtime.js
    # after every deployment.  The process-start token makes each release a
    # distinct resource while still allowing it to be cached indefinitely.
    cache_bust = getattr(app, "_cache_bust", None)

    document = shell_fn(
        body_html,
        envelope_json,
        page_uuid=ctx.page_uuid,
        title=title,
        description=meta.description,
        # ``default_shell`` has carried this parameter forever and
        # NOBODY passed it: every Bretzel page shipped
        # ``<html lang="en">``, French apps included — a screen reader
        # picks its voice from it, and the browser its hyphenation.
        lang=ctx.lang,
        head_extras=ctx.head_extras,
        browser_css=browser_css,
        # Variant WITHOUT the safelist: this block is only read by the
        # browser compiler, which scans the DOM. Cf. ``_resolve_theme``.
        theme_css_content=getattr(app, "_theme_css_inline", "") or "",
        cache_bust=cache_bust,
        # ``None`` = the framework's mark. The ``getattr`` covers test
        # shells passing a fake ``app`` with no config.
        favicon=getattr(cfg, "favicon", None),
        mobile_breakpoint=getattr(cfg, "mobile_breakpoint", 768),
        nav_progress=getattr(cfg, "nav_progress", True),
        # The pipeline does NOT know ``PWA`` (it is in ``server``, above
        # ``render`` in the DAG): it receives two strings, which is
        # enough and keeps the layers apart.
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

    # ── Identity does not depend on the arrival path ──────────────────
    #
    # A partial render does NOT render the outer layouts: they are
    # already in the browser. With nothing on ``parent_stack``, the
    # page's components therefore started again from the literal
    # ``"root"`` (``component.py``) instead of descending from the
    # targeted outlet — the same accordion rendered
    # ``outlet_shell_…_accordion_0`` on a direct load and
    # ``root_…_accordion_0`` after a boosted navigation.
    #
    # ``bz-id`` is the key of TWO mechanisms: idiomorph pairing and scope
    # resolution. An id that changes with the arrival path therefore
    # degrades every navigation into a subtree REPLACEMENT — every
    # ``bz-data`` in the swapped region is destroyed then rebuilt instead
    # of being merged.
    #
    # ⚠️ It is a RELAPSE: ``render/partials.py`` documents the same flaw,
    # found and fixed for ``@refreshable`` partials ("every child's
    # ``Component.__init__`` fell back to the literal "root" ID prefix").
    # The NAVIGATION path had never received it.
    #
    # The remedy is the same: seed the stack with a parent carrying the
    # target's id. The router has already resolved it
    # (``server/routing/pages.py`` sets ``ctx.partial_target`` from the
    # ``HX-Target`` header), so nothing is guessed.
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
            # The ``async`` zones set down by the body left their
            # section in the tree and their coroutine pending: this is
            # where we await them, before lowering the tree to Nodes.
            await drain_pending_async_zones(ctx)
            # The flattening is OFFLOADED too: ``render()`` calls app
            # code back (a ``ui.datatable``'s ``rows=``, a column's
            # ``render=``) and the framework REQUIRES that ``rows=`` to
            # be a ``def`` — it REFUSES a coroutine. Leaving it on the
            # loop therefore made the most common case of a real app
            # blocking, by construction.
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
    """The id parent the partial render did not render.

    It **never appears in the output**: htmx morphs the outlet's
    ``innerHTML``, so the fragment must contain its CHILDREN, not it.
    That is what distinguishes it from ``_RefreshableSection``, the twin
    stand-in on the ``@refreshable`` side, which must render because the
    OOB swap targets its own id.

    A parent's protocol, read in ``component.py``: ``id`` and
    ``add_child`` for registration, **and ``_children``** — which
    ``_detach_from_parent`` searches to remove a component adopted as a
    slot. That third member did not show when looking at
    ``parent_stack[-1]``: detachment iterates the WHOLE stack. Without
    it, every page containing an ``icon=``/``prefix=`` raised an
    ``AttributeError`` on the first partial render.

    Hence a bare object rather than a ``Component``: building a real
    component here would register it as a root child and make it render —
    and this parent must produce no bytes.
    """

    __slots__ = ("_children", "child_scope_id", "id")

    def __init__(self, outlet_id: str, *, page_scope: str = "") -> None:
        self.id = outlet_id
        # ⚠️ Must reproduce EXACTLY what ``Outlet.child_scope_id``
        # computes on the full path: that is the condition for both
        # arrival paths — direct load and boosted navigation — to produce
        # the same ``bz-id``, which
        # ``test_partial_nav_keeps_identity`` guards.
        self.child_scope_id = f"{outlet_id}{page_scope}"
        self._children: list[Any] = []

    @property
    def children(self) -> list[Any]:
        """A readable alias for the drain — the same list, not a copy."""
        return self._children

    def add_child(self, child: Any) -> None:
        self._children.append(child)


def _roots(ctx: RenderContext, seed: _PartialRoot | None) -> list[Any]:
    """Where the top-level children landed.

    With a seed, everything the page registers goes through its
    ``add_child`` and ``ctx.root_children`` stays empty — so the drain
    must read the seed, otherwise the fragment goes out empty.
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
    """Render a non-empty layout chain, then the page inside it.

    Extracted from :func:`_invoke_page` on 2026-08-13, when the identity
    seed made its body conditional: the function carried two return paths
    and one more ``try``, and nesting them would have made it unreadable
    which ``finally`` pops what.
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
        # ``_roots`` and not ``ctx.root_children``: under an identity
        # seed, the outermost layout registered with IT, and looking for
        # the outlet at the root would find nothing — "Layout 'x' did not
        # call ui.outlet()" on a layout that called it perfectly.
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

        # INSIDE the ``try``, so before the ``finally`` restores
        # ``layout_stack``: a zone body builds components, and some
        # (Outlet, SidebarItem) derive their id from that stack. Draining
        # it outside would give them ids from another depth.
        await drain_pending_async_zones(ctx)

    finally:
        # Pop everything we pushed, restore the original stack so
        # an exception doesn't leave the context in a half-state.
        ctx.layout_stack = saved_layout_stack

    return await call_without_blocking(_drain, ctx, roots=_roots(ctx, seed))


async def _call(
    fn: Callable[..., Any], kwargs: dict[str, Any]
) -> Any:
    """Invoke ``fn(**kwargs)`` — awaited if async, offloaded if sync.

    A SYNCHRONOUS page or layout body goes to the threadpool (cf.
    ``core/invoke``), otherwise a ``def home()`` reading a blocking
    database freezes the loop.

    One hop per BODY, not one per render: the layout chain passes through
    here once each, the page once, and the flattening once more. The
    ``@refreshable`` zones are free — their ``__call__`` is synchronous
    by contract, so they run in the thread of whoever calls them.
    """
    return await call_without_blocking(fn, **kwargs)


def _drain(
    ctx: RenderContext,
    *,
    roots: list[Any] | None = None,
    trailing: Any = None,
) -> list[Node]:
    """Walk the top-level children once and lower everything to Nodes.

    ``roots`` defaults to ``ctx.root_children``. It is explicit when a
    partial render has seeded an identity parent: the children then went
    through the seed's ``add_child``, and the root is empty.

    ``trailing`` is the page function's return value — pages that
    return a Node / Component directly (vs. registering children
    through ``with`` blocks) flow it in here so it lands in the
    final tree.

    ``is_rendering=True`` for the walk: Components that nested
    helpers build inline (e.g. a ``ui.badge`` returned from a table's
    ``render=`` cell callback) must skip root-children registration
    so they don't appear twice. Restore the previous value on the
    way out so an outer pipeline pass isn't poisoned.
    """
    # The component tree is complete HERE, and not before: the page body
    # has finished, the ``async`` zones are drained, and the layout chain
    # is closed onto the outlet. It is therefore the only point from
    # which a PLACEMENT question is answered correctly — a ``sticky`` bar
    # cannot know at construction time that a ``ui.viewport`` is coming,
    # nor what its real layout parent is.
    #
    # The test is an ``if`` on an empty list: nothing registers as long
    # as a page has neither ``ui.bottom_bar`` nor
    # ``ui.navbar(sticky=)``. Deferred import — ``render`` only reaches
    # up to ``components`` here, at the point of use (cf. charter
    # principle 5).
    if ctx.sticky_bars:
        from bretzel.components.base._wiring import (
            check_sticky_bar_placement,
        )

        bars, ctx.sticky_bars = ctx.sticky_bars, []
        check_sticky_bar_placement(
            ctx.root_children if roots is None else roots, bars
        )

    # Same floor, same reason: "which bar is this trigger speaking to?"
    # and "does this bar have a way back?" are only answered once the
    # page is built. Resolve first — it is the resolution that makes a
    # bar reachable.
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

    ``full_chain`` is outermost-first; ``partial_target`` is the
    ``HX-Target`` value the browser sent (typically
    ``outlet_<layout>``). We slice off everything up to and including
    the matched layout — what remains are the inner sub-layouts (plus
    the page) that need to render INTO the targeted outlet.

    Three common cases:

    - **Intra-section nav**: target is the innermost layout's outlet
      → match at the last index → slice returns ``[]`` (page-only
      render lands directly in the targeted outlet).
    - **Cross-section nav**: target is an ancestor (e.g. a sidebar
      in the outer ``shell`` jumping between ``admin_shell`` and
      ``billing_shell`` siblings) → slice returns the inner sub-chain
      so the sub-layout re-renders fresh under the shared outlet.
    - **No match / empty target**: returns ``[]`` so the pipeline
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
    The runtime hydrates from it at boot — it reads only
    ``client_state`` / ``csrf`` / ``endpoints`` (``00_index.js``).

    ⚠️ This function also used to pull the theme's ``palette`` and push
    it into the envelope: 2 197 bytes per page that nothing read. Removed
    on 2026-08-01 — cf. the field's comment in ``runtime/envelope.py``.
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
    """The RIGHT address when the browser's is incomplete, else ``""``.

    The case: a ``session``-scoped state remembers a sort or a filter
    across navigations. Coming back to a bare ``/accounts`` then returns
    a sorted view under an address that says nothing of it — and the
    copied link shows something else to whoever receives it. Two people
    "on the same page", with nothing to signal it.

    We are AFTER the body's render, so every state the page mounted is
    already resolved: that is what makes the computation possible here
    and nowhere earlier.

    ⚠️ Nothing is corrected when the address is already right — no
    history entry, no write. And nothing at all for an app that declared
    no addressable field, which is the default.
    """
    registry = ctx.state_registry
    request = getattr(ctx, "request", None)
    if registry is None or request is None:
        return ""
    try:
        declared = registry.addressable_param_names()
    except Exception:
        # An invalid declaration will raise at render time, where the
        # message is useful — not here, where it would break the whole
        # page for an address correction.
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

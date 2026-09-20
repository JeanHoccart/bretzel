"""Per-request :class:`RenderContext` + :class:`~contextvars.ContextVar` binding.

One ``RenderContext`` is constructed per request by the render
middleware and bound on the active asyncio task. Components, state
helpers and the runtime envelope all read from it via
:func:`current_context` — no thread-local globals, no manual plumbing.

"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from bretzel.core.identity import IdGenerator
from bretzel.render.texts import DEFAULT_TEXTS

if TYPE_CHECKING:
    from bretzel.render.types import BretzelApp
    from bretzel.state.registry import StateRegistry


# ───────────────────────────────────────────────────────────────────────────
# Cookie option payload
# ───────────────────────────────────────────────────────────────────────────


# Keep the schema permissive on purpose : rendering / auth code passes
# whatever Starlette's ``Response.set_cookie`` accepts, so we don't need
# a strict TypedDict here.
CookieOptions = dict[str, Any]


# ───────────────────────────────────────────────────────────────────────────
# RenderContext
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class RenderContext:
    """The per-request scope object.

    Assembled by ``server/middleware/render_context.py`` (Layer 6) and
    consumed everywhere downstream. Direct construction is also
    supported for tests — most fields have sensible defaults.
    """

    # ── Request reference ────────────────────────────────────────────────
    # ``app`` is typed via the Protocol so render stays free of any
    # import from the server layer (CR-2 fix from the spec review).
    app: BretzelApp
    # ``Any`` rather than ``fastapi.Request`` so the unit suite can
    # exercise this layer without spinning up FastAPI ; production code
    # will receive the real thing from the middleware.
    request: Any

    # ── Identity / page wrapper ──────────────────────────────────────────
    page_uuid: str = field(
        default_factory=lambda: uuid.uuid4().hex
    )
    # Render timestamp (unix seconds, as a string) — set once per request,
    # signed into every action HMAC and baked as ``data-bz-ts``. Bounds how
    # long a captured request stays valid (``config.action_max_age``) and is
    # the idempotency key for ``@idempotent`` handlers.
    render_ts: str = field(default_factory=lambda: str(int(time.time())))
    id_generator: IdGenerator = field(default_factory=IdGenerator)
    parent_stack: list[Any] = field(default_factory=list)
    root_children: list[Any] = field(default_factory=list)
    is_rendering: bool = False  # set during the tree-walk render phase

    # ── Language and framework words ─────────────────────────────────────
    #: Copied from the config when the context is mounted rather than
    #: read through ``ctx.app``: a component needing the language is in
    #: layer 5, the config in layer 7, and half the test benches build a
    #: ``RenderContext`` without a complete app. The defaults below are
    #: therefore what a component mounted outside a request sees.
    lang: str = "en"
    texts: Mapping[str, str] = field(default_factory=lambda: DEFAULT_TEXTS)

    # ── State + reactivity ───────────────────────────────────────────────
    # Concrete StateRegistry comes from Layer 1 ; we keep the type loose
    # to avoid a hard dependency from this dataclass header.
    state_registry: StateRegistry | None = None

    # ── Hydration payloads pre-parsed by the middleware ──────────────────
    client_state_payload: dict[str, dict[str, Any]] = field(default_factory=dict)
    form_data: dict[str, Any] = field(default_factory=dict)
    #: Why ``form_data`` is empty although the request carried a form —
    #: ``None`` when everything went well.
    #:
    #: Without this field, an unreadable multipart body (a part too
    #: large, a connection cut mid-upload) returned an EMPTY form and the
    #: handler ran anyway: it read `""` everywhere and wrote that into
    #: the state. The failure was therefore not an error, it was an
    #: INPUT — a form that clears itself. The action dispatcher refuses
    #: when this field is set.
    form_error: str | None = None

    # ── Auth ─────────────────────────────────────────────────────────────
    user_id: str | None = None
    session_id: str = ""
    csrf_token: str = ""

    #: The ``@refreshable`` zones the BROWSER really carries, or
    #: ``None`` when we do not know.
    #:
    #: The distinction is the whole mechanism: ``None`` means "I do not
    #: have the information" — a cached runtime, a third-party client, a
    #: test POSTing by hand — and the drain then filters nothing, exactly
    #: as before. An EMPTY set would mean "this document carries no
    #: zone", which the runtime never sends (it omits the header in that
    #: case). Confusing the two would silence every zone for the first
    #: client that does not speak the latest version of the protocol,
    #: without an error.
    live_zones: frozenset[str] | None = None

    #: ``{zone id: fingerprint}`` the browser says it is DISPLAYING, read
    #: from the same header as :attr:`live_zones`. Used to silence a zone
    #: whose fresh render is identical. Empty when the client says
    #: nothing — so the default behaviour is to ship.
    zone_hashes: dict[str, str] = field(default_factory=dict)

    #: The tab that issued the current request, or ``""`` when it says
    #: nothing (an older runtime, a call outside a browser). Used to
    #: avoid re-broadcasting to it what it has just received — cf.
    #: :data:`~bretzel.runtime.protocol.HEADER_TAB`.
    tab_id: str = ""

    # ── Pipeline state ───────────────────────────────────────────────────
    layout: Callable[..., Any] | None = None
    # Stack of active layout function names. Pushed when the pipeline
    # invokes a layout, popped on the way out. Nested layouts (parent=)
    # appear in outer→inner order ; ``Outlet.__init__`` reads the
    # tail to derive its ``outlet_<layout>`` id, ``SidebarItem.__init__``
    # reads the same to plumb ``hx-target=#outlet_<layout>``.
    layout_stack: list[str] = field(default_factory=list)
    #: The ``ui.sidebar`` built during THIS render. Serves two questions
    #: that can only be answered once the page is built: resolving WHICH
    #: bar a ``ui.sidebar_trigger`` with no argument speaks to, and
    #: checking that a collapsible bar does have a way of being reopened
    #: — otherwise navigation is unreachable, silently (measured on
    #: 2026-08-24: aside at x=-256, ZERO clickable element on screen,
    #: page at 200).
    sidebars: list[Any] = field(default_factory=list)
    #: The ``ui.sidebar_trigger`` built during THIS render. Resolved by
    #: ``base/_wiring.wire_sidebar_triggers`` once the tree is built, not
    #: at construction: otherwise a trigger written BEFORE the bar — a
    #: shell that sets down its top bar first — would find nothing, and
    #: the reachability guard would take that for an absence. Same lesson
    #: as the ``sticky`` bars: writing order must not change the
    #: verdict.
    sidebar_triggers: list[Any] = field(default_factory=list)
    #: The ``sticky`` bars built during THIS render, each with its call
    #: name and the file:line that wrote it. Filled by
    #: ``base/_wiring.register_sticky_bar``, emptied by the
    #: ``render/pipeline._drain`` pass.
    #:
    #: **Why a list and not a check at construction time**: "am I well
    #: placed?" is a question asked of the TREE, and the tree does not
    #: exist yet when the bar is built. Two flaws measured on 2026-08-24
    #: prove it — a bar written BEFORE the ``ui.viewport`` cannot know a
    #: frame is coming, and a bar wrapped in a ``ui.fragment`` does not
    #: have its real LAYOUT parent on ``parent_stack``. Both rendered a
    #: broken page silently.
    #:
    #: Empty on the vast majority of renders: only ``ui.bottom_bar`` and
    #: ``ui.navbar(sticky=True)`` register here, so the pass does not
    #: even start.
    sticky_bars: list[Any] = field(default_factory=list)
    #: ``{state class: {modified fields}}`` for THIS request, set by the
    #: action route from ``StateRegistry.diff_and_notify``. **Empty means
    #: "we do not know"**, not "nothing changed": a full page render and
    #: an SSE refetch both leave it empty, and must therefore re-render
    #: everything. Every reader must treat empty as the conservative
    #: case.
    changed_fields: dict = field(default_factory=dict)
    is_partial: bool = False
    # Two distinct flows flip ``is_partial`` :
    #
    # - **Partial nav** (``server/routing/pages.py``) : an htmx-boosted
    #   internal link sends ``HX-Request: true`` + ``HX-Target: outlet_X``
    #   matching a layout in the page's chain. Sets ``partial_target =
    #   "outlet_X"`` so the pipeline can slice the layout chain at the
    #   right depth (``_slice_chain_for_partial``).
    # - **Refreshable / action OOB drain** (``render/partials.py``) :
    #   flipped to skip the shell + envelope when emitting refreshable
    #   OOB fragments. ``partial_target`` stays ``None`` — the pipeline
    #   only renders what the action-driven refresh queue produced, no
    #   layout walk involved.
    #
    # So ``partial_target`` is set ONLY in the partial-nav flow ; the
    # action-drain flow leaves it ``None`` and that's expected.
    partial_target: str | None = None
    is_action: bool = False
    refreshable_target: str | None = None

    #: The token that makes the page's ``bz-id`` UNIQUE TO THIS PAGE.
    #:
    #: The flaw it closes, measured on 2026-08-13: the runtime's scope
    #: store is a ``Map`` indexed by the ``bz-id`` **string**
    #: (``03_scope.js``), and an ``hx-boost`` does not reload the
    #: runtime. But a ``bz-id`` describes a POSITION in the tree
    #: (``outlet_shell_container_0_…_accordion_0``) and says nothing
    #: about the page. Two pages of the same shape therefore produced the
    #: same key: across the playground's 68 pages, **13 collisions**
    #: outside the shell — one tooltip on 13 pages, one dialog on 7.
    #: After a navigation, the previous page's scope was found by its id
    #: and its values won over the server's fresh literal (open the
    #: accordion on ``/accordion``, go to ``/markdown``, and it arrives
    #: open; an F5 renders it correctly).
    #:
    #: ⚠️ It qualifies the id the outlet gives its CHILDREN, never the id
    #: the outlet RENDERS: htmx sends the latter back as ``HX-Target``,
    #: so moving it would break partial rendering on the next
    #: navigation.
    #:
    #: The PATH and not the route: ``/contacts/5`` and ``/contacts/9``
    #: are two pages for the user, and sharing their state would leak one
    #: contact's accordion into another's. The query is excluded from it
    #: — ``/issues?sort=date`` is the same page as ``/issues``.
    page_scope: str = ""

    @property
    def child_scope_root(self) -> str:
        """The suffix to append to a parent id to make it page-unique.

        Empty when ``page_scope`` is — outside a request (benches, unit
        tests) ids keep exactly their previous form, which leaves intact
        the inventories and snapshots that cite them.
        """
        return f"__{self.page_scope}" if self.page_scope else ""


    # ── Outgoing — applied to the response by the middleware ─────────────
    new_cookies: dict[str, CookieOptions] = field(default_factory=dict)
    deleted_cookies: set[str] = field(default_factory=set)
    response_headers: dict[str, str] = field(default_factory=dict)
    head_extras: list[Any] = field(default_factory=list)
    # Page-level title override — ``ui.title("…")`` writes here. When
    # set, supersedes the ``@page(title=…)`` decorator value in
    # the pipeline (last call wins, so the deepest ``ui.title()`` in
    # the render scope is the one that ships).
    head_title: str | None = None

    # Pending refreshable handles whose ``.refresh()`` was called during
    # this request — drained by the partial-renderer at end-of-action
    # to emit OOB swap fragments.
    refresh_queue: list[Any] = field(default_factory=list)

    # ASYNC ``@refreshable`` zones whose body is still to be awaited.
    #
    # A zone is called ``zone()``, with no ``await``, including when its
    # body is a coroutine: that is the framework's calling convention,
    # and it does not change because a read becomes asynchronous.
    # ``RefreshableHandle.__call__`` therefore sets the SECTION down in
    # the tree immediately — the zone's place in the page is decided at
    # call time, not when its data arrives — then pushes
    # ``(section, coroutine)`` here. The pipeline drains the queue once
    # the page body has finished.
    #
    # A list, not a ``gather``: zones are awaited in SERIES because they
    # share ``parent_stack`` — two concurrent bodies would register with
    # each other. Concurrency, if it is ever wanted, is taken INSIDE a
    # zone body (``asyncio.gather`` over its requests), not between
    # zones.
    #
    # Drained in a LOOP: an async zone can call another, which is added
    # here while we await the first.
    pending_async_zones: list[Any] = field(default_factory=list)

    # Toast notifications queued by ``ui.notification(...)`` during the
    # request. Drained by the partial-renderer at end-of-action: they go
    # out in a ``<bz-patch>`` under the reserved ``_notifications`` key,
    # which the bridge forwards to ``$bz.notify``. The toaster mounts
    # itself on the first toast (no container to mount).
    notifications: list[dict[str, Any]] = field(default_factory=list)

    # Components register their callable event handlers here at render
    # time — the action-route handler in Layer 6 reads this map (or
    # the encoded ``module::qualname`` form) to dispatch incoming
    # requests. Closure / lambda handlers are rejected at registration
    # time (see :py:meth:`register_action`).
    action_registry: dict[str, Callable[..., Any]] = field(default_factory=dict)

    # ── End-of-request hooks ─────────────────────────────────────────────
    cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)

    # ── Helper methods ───────────────────────────────────────────────────

    def set_cookie(self, name: str, value: str, **opts: Any) -> None:
        """Schedule ``Set-Cookie`` to be emitted on the response.

        Cancels any pending ``delete_cookie`` for the same name — the
        last write wins, just like Starlette's own behaviour.
        """
        self.new_cookies[name] = {"value": value, **opts}
        self.deleted_cookies.discard(name)

    def delete_cookie(self, name: str) -> None:
        """Schedule the cookie to be cleared on the response."""
        self.deleted_cookies.add(name)
        self.new_cookies.pop(name, None)

    def set_header(self, name: str, value: str) -> None:
        """Set a custom response header (``HX-Trigger``, ``Cache-Control``, …)."""
        self.response_headers[name] = value

    def register_action(
        self,
        handler: Callable[..., Any],
        component_id: str,
        event: str,
    ) -> tuple[str, str, str]:
        """Register a component event handler ; return its wire triplet.

        Returns ``(action_id, args_blob, sig)`` — the component layer
        turns it into the V3 HTMX attribute set via
        :func:`bretzel.components.base.events.action_attrs`
        (``hx-post`` + ``hx-vals`` + ``data-bz-sig``). The action route
        verifies the sig (forwarded as ``X-Bz-Sig`` by the runtime
        bridge) before resolving the callable.
        """
        from bretzel.components.base.events import encode_handler_id
        from bretzel.server.handlers import encode_args, sign_action

        action_id = encode_handler_id(handler)
        # Multiple components binding the same module-level handler
        # share the same id — the registry stores it once. For a
        # ``functools.partial``, the underlying ``handler.func`` is
        # what the server will resolve through ``sys.modules`` ; the
        # bound args ride separately via the ``_args`` form field.
        self.action_registry.setdefault(action_id, handler)

        # Bound args (from a ``partial``) → base64-JSON blob. Empty
        # string for plain callables.
        args_blob = encode_args(handler)

        # Pre-sign the (id, args_blob) pair at render time. No key
        # available (test rigs, plain ``RenderContext`` with no app
        # attached) → empty sig ; the call won't verify but unit tests
        # don't go through the route either.
        action_key = self._action_key()
        sig = (
            sign_action(action_key, action_id, args_blob, ts=self.render_ts)
            if action_key
            else ""
        )
        return action_id, args_blob, sig

    def _action_key(self) -> bytes:
        """Pull the derived action key from ``app.config``, else empty bytes."""
        config = getattr(self.app, "config", None)
        return getattr(config, "_action_key", b"") if config is not None else b""

    def add_cleanup(self, callback: Callable[[], None]) -> None:
        """Register a cleanup ; callbacks fire in LIFO order at request end."""
        self.cleanup_callbacks.append(callback)

    def run_cleanups(self) -> None:
        """Drain :attr:`cleanup_callbacks` in LIFO order.

        Each callback runs with its own ``try/except`` so a misbehaving
        one doesn't poison the rest. Errors are logged but never
        re-raised — the response has already been sent at this point.
        """
        while self.cleanup_callbacks:
            cb = self.cleanup_callbacks.pop()
            try:
                cb()
            except Exception as exc:
                # Stdlib logging avoids dragging an extra dep in the
                # render layer's import surface.
                import logging
                logging.getLogger("bretzel.render").exception(
                    "render cleanup callback failed", exc_info=exc
                )


# ───────────────────────────────────────────────────────────────────────────
# Context-var binding
# ───────────────────────────────────────────────────────────────────────────


_CURRENT: ContextVar[RenderContext | None] = ContextVar(
    "bretzel_render_context", default=None
)


def current_context() -> RenderContext:
    """Return the active context. Raises if called outside a render scope.

    Components and state helpers rely on this to discover their
    surrounding request without explicit plumbing.
    """
    ctx = _CURRENT.get()
    if ctx is None:
        raise RuntimeError(
            "No render context is active. This function must be called "
            "from within a request — typically from a @page handler, a "
            "@refreshable scope, or a component's render() method."
        )
    return ctx


def maybe_current_context() -> RenderContext | None:
    """Variant that returns ``None`` outside a render scope (no raise)."""
    return _CURRENT.get()


_UNSAFE_IN_ID = re.compile(r"[^A-Za-z0-9]+")


def page_scope_of(ctx: RenderContext) -> str:
    """The page token, derived from the request PATH.

    The same for a full load and for a boosted navigation of the same
    URL — that is the condition for ``test_partial_nav_keeps_identity``
    to keep holding: both arrival paths must produce the SAME ids.

    Returns ``""`` outside a request (benches, ``render_isolated``), and
    ids then keep their previous form.
    """
    url = getattr(getattr(ctx, "request", None), "url", None)
    path = getattr(url, "path", None)
    if not isinstance(path, str) or not path:
        return ""
    return _UNSAFE_IN_ID.sub("_", path).strip("_") or "root"


@contextmanager
def use_context(ctx: RenderContext) -> Iterator[None]:
    """Bind ``ctx`` as the active context for the duration of the block.

    Used by the pipeline once per request. Nested calls compose : on
    exit, the previously-bound context (if any) is restored, so unit
    tests can spin up a temporary context without disturbing the outer
    scope.
    """
    token = _CURRENT.set(ctx)
    try:
        yield
    finally:
        _CURRENT.reset(token)

"""``@refreshable`` — mark a function as a partial swap target.

The decorated function is wrapped in a :class:`RefreshableHandle`. The
handle is callable like the original function (so it slots into a page
render naturally). A zone re-renders declaratively when a state in its
``deps=`` changes ; :func:`refresh` (the free function) forces one
imperatively from anywhere.

"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Iterable, Sequence
from functools import partial
from typing import Any, ClassVar

from bretzel.core import hash_segment
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import (
    DATA_SUBSCRIBE_STATE,
    DATA_SUBSCRIBE_URL,
    DATA_ZONE,
    ROUTE_REFETCH,
    SSE_EVENT_ZONE_ROWS,
    WIRE_ID_SEP,
)


def _resolve_broadcast(
    broadcast: Sequence[type], zone: str
) -> tuple[type, ...]:
    """``broadcast=`` → the states the zone listens to over SSE.

    **Orthogonal to ``deps``**, and that is the whole model:

    ==============  ====================================================
    who changes     where you write it
    ==============  ====================================================
    **me**          ``deps`` — the zone is re-rendered IN the action's
                    response. One round trip, one swap.
    **the others**  ``broadcast`` — an SSE signal, then a refetch. Two
                    round trips, but the tab that did nothing follows.
    **both**        both lists. That is not redundancy: it says
                    "instant for me, pushed to the others".
    ==============  ====================================================

    A ``broadcast=[X]`` on its OWN is therefore legitimate — the "I never
    change this state myself" case (a background job, another user).
    There is no inclusion rule: the two lists only overlap if the author
    wants them to.

    Booleans are refused: deriving the broadcast states from ``deps``
    would couple the two lists. The caller explicitly names the states it
    wants to observe on other clients.
    """
    if broadcast is True or broadcast is False:
        raise TypeError(
            f"@refreshable({zone}): broadcast= takes a LIST of states, "
            f"no longer a boolean (removed on 2026-08-23). `deps` says "
            f"what re-renders me in MY action's response, `broadcast` what "
            f"I listen to from OTHER clients — those are two questions. "
            f"Write `broadcast=[MyState]`, and keep it in `deps` too if "
            f"your own action is what changes it (otherwise you pay one "
            f"more round trip for the tab that clicked)."
        )
    return tuple(broadcast)


#: The two variadic forms. They are NOT refused: nothing in a signature
#: says what a ``**kwargs`` carries, so refusing them would amount to
#: judging by the name. One bench in the repository uses them
#: (``tests/unit/components/data/test_datatable.py``) to build a real
#: zone around a parameterised component.
_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


def _reject_parameters(fn: Callable[..., Any], zone: str) -> None:
    """A zone takes no parameter — refused at DECORATION time.

    The refresh path calls the handle **bare**
    (``render/partials.py``, ``handle()``), whereas the page render goes
    through ``__call__(*args, **kwargs)``. The two paths therefore do not
    see the same signature, and the divergence is invisible:

    ``def zone(x)``
        The page renders perfectly. Then the first action touching a
        ``deps`` raises ``TypeError`` — **a 500 on the re-render, not on
        the page**, so in the place nobody looks. That is the case that
        motivated this refusal (2026-09-04).

    ``def zone(x=0)``
        Worse, because mute: the page renders ``zone(3)``, and every
        refresh renders ``zone(0)``. Nothing raises, the screen changes
        content by itself. Refused for the same reason, and that is the
        half the original statement missed.

    The root of it: a zone is re-rendered **outside its caller**, so
    everything it needs must be reachable from it — that is to say, a
    state. A parameter is data the refresh cannot find again. Two pages
    calling the same zone with two arguments would share a unique ``id``
    and ``name`` anyway: the model has nowhere to put the difference.

    Remedy: read the state in the body, or keep an ordinary
    (parameterisable) function that the zone calls.
    """
    offenders = [
        p.name
        for p in inspect.signature(fn).parameters.values()
        if p.kind not in _VARIADIC
    ]
    if not offenders:
        return
    raise TypeError(
        f"@refreshable({zone}): a zone takes no parameter, and this one "
        f"declares {', '.join(offenders)}. The refresh calls it WITHOUT "
        f"arguments — a required parameter raises a 500 on the first "
        f"action touching a `deps` (never on page load), a parameter with "
        f"a default raises nothing and simply re-renders something else. "
        f"Read a state in the zone's body, or keep an ordinary "
        f"parameterisable function that the zone calls."
    )


def state_qualname(state_class: type) -> str:
    """Return the stable wire identifier for a state class."""
    return f"{state_class.__module__}{WIRE_ID_SEP}{state_class.__qualname__}"


# Registry of every refreshable zone by its ``name`` (default = the
# module-qualified zone name). Lets the free ``refresh("name")`` resolve a
# zone from ANYWHERE without importing the zone function (a cron, a webhook,
# another feature). Populated at decoration time — import order applies, the
# same caveat as action handlers.
_ZONE_BY_NAME: dict[str, RefreshableHandle] = {}

# Reverse index : State class → the zones that declared it in ``deps``. The
# action pipeline uses it to enqueue exactly the zones affected by a state
# change (see :func:`enqueue_deps`).
_ZONES_BY_DEP: dict[type, list[RefreshableHandle]] = {}

#: ``State → zones listening to it over SSE``. An index SEPARATE from
#: ``_ZONES_BY_DEP``, and not a filter on it: the two lists have been
#: orthogonal since 2026-08-23, so a zone can be here without being
#: there ("I never change this state myself"). Merging them would make
#: the LOCAL re-render sensitive to a channel, which is exactly the
#: confusion we have just undone.
_ZONES_BY_CHANNEL: dict[type, list[RefreshableHandle]] = {}


def zone_attrs(
    refresh_id: str,
    *,
    subscribe_state_qualname: str | None = None,
    subscribe_url: str | None = None,
) -> dict[str, str]:
    """The attributes a zone sets IN ADDITION to its ``bz-id``.

    At module level and not on the section, because **three** paths need
    them: the render (``_RefreshableSection.render``), recomposition by a
    parent (``_rewrap``), and the fallback fragment of a zone that raised
    (``render/partials._zone_failure_fragment``).

    The third was hand-written for a day, and it cost exactly what this
    function exists to prevent: it omitted ``DATA_ZONE``, so after an
    error the zone dropped out of the browser's enumeration, so the
    ``X-Bretzel-Zones`` header no longer carried it, so ``enqueue_deps``
    filtered it out — **it never refreshed again** until a full reload,
    without a word. Two gates covered it, each on its own side; neither
    saw the crossing.

    ``DATA_ZONE`` is EMPTY: the identifier is already on the same element
    as ``bz-id``. The marker says "I am a zone", ``bz-id`` says which
    one. A dedicated attribute rather than an ``id`` prefix guessed in JS
    — ``refresh_`` is a ``_stable_id`` convention, and copying it
    client-side would make a mirror that drifts.
    """
    attrs = {DATA_ZONE: ""}
    if subscribe_state_qualname and subscribe_url:
        attrs[DATA_SUBSCRIBE_STATE] = subscribe_state_qualname
        attrs[DATA_SUBSCRIBE_URL] = subscribe_url
    return attrs


def _stable_id(fn: Callable[..., Any]) -> str:
    """Hash ``module.qualname`` to a short stable id.

    The id is used as the ``bz-id`` of the wrapping element, so it must
    survive code reloads but stay readable in DevTools. We keep the
    last 8 hex chars — collision risk is negligible at this scale.
    """
    qual = f"{fn.__module__}.{fn.__qualname__}"
    return f"refresh_{hash_segment(qual)}"


_section_cls_cache: type | None = None


def _section_cls() -> type:
    """Lazy-build the ``_RefreshableSection`` Component class.

    ``bretzel.components.base`` imports from us indirectly via
    ``Component.__init__`` reaching the render context, so a top-level
    ``from bretzel.components.base import Component`` would close a
    cycle. Building the class on first ``__call__`` postpones the
    import until both modules are fully loaded.
    """
    global _section_cls_cache
    if _section_cls_cache is not None:
        return _section_cls_cache

    from bretzel.components.base import Component
    from bretzel.render.fusion import fuse_or_wrap

    class _RefreshableSection(Component):
        """Wraps the children of a ``@refreshable`` call.

        Carries the section's ``bz-id`` on the rendered Element so the
        INITIAL page ships a target HTMX can find later via
        ``hx-swap-oob``. Without this wrapper, OOB swaps had no
        matching id and were silently dropped — buttons fired, server
        responded, DOM never updated.

        Pure framework concern : never instantiated by user code.

        When the wrapping handle is a ``@refreshable(deps=[State], broadcast=[State])`` zone,
        ``subscribe_state_qualname`` + ``subscribe_url`` are emitted
        as ``data-bz-subscribe-*`` attributes the runtime parses on
        DOMContentLoaded to wire the EventSource + refetch URL.
        """

        THEME_KEY: ClassVar[str] = "_refreshable"
        DEFAULT_TAG: ClassVar[str] = "div"
        IS_CONTAINER: ClassVar[bool] = True
        #: "I am not here." A parent sorting its children BY THEIR TYPE
        #: must see through me to find what I carry, then give me back my
        #: ``bz-id`` on the node it composed — otherwise the tab is
        #: correct and never refreshes again. Cf.
        #: ``base/_wiring.unwrap_transparent``.
        IS_TRANSPARENT_WRAPPER: ClassVar[bool] = True

        def __init__(
            self,
            *,
            refresh_id: str,
            subscribe_state_qualname: str | None = None,
            subscribe_url: str | None = None,
            **kwargs: Any,
        ) -> None:
            # The handle's stable id wins over auto-generated so
            # initial render and partial rerender share one target.
            kwargs.setdefault("id", refresh_id)
            super().__init__(**kwargs)
            self._refresh_id = refresh_id
            self._subscribe_state_qualname = subscribe_state_qualname
            self._subscribe_url = subscribe_url

        def _rewrap(self, node: Any) -> Any:
            """Set the zone's identity back on a node composed ELSEWHERE.

            The parent (``ui.tabs`` and company) needs the bare child to
            compose it its own way; the zone needs its ``bz-id`` to be on
            the result. Both go through the same ``fuse_or_wrap`` as
            ``render``, so the shape is identical — one single
            wrap-or-fuse rule in the repository.
            """
            return fuse_or_wrap([node], bz_id=self._refresh_id,
                                extra_attrs=self._zone_attrs())

        def _zone_attrs(self) -> dict[str, str]:
            """Delegates to :func:`zone_attrs` — the single source for
            the three paths (render, recomposition, fallback fragment)."""
            return zone_attrs(
                self._refresh_id,
                subscribe_state_qualname=self._subscribe_state_qualname,
                subscribe_url=self._subscribe_url,
            )

        def render(self) -> Any:
            children_nodes = self._render_children()
            extra_attrs = self._zone_attrs()
            return fuse_or_wrap(
                children_nodes,
                bz_id=self._refresh_id,
                extra_attrs=extra_attrs,
            )

    _section_cls_cache = _RefreshableSection
    return _section_cls_cache


async def drain_pending_async_zones(ctx: Any) -> None:
    """Await the bodies of the ``async`` zones set down during this render.

    Called by BOTH render paths — the full page
    (``render/pipeline.py``) and the fragment (``render/partials.py``) —
    because a zone renders through both, and a queue drained on one side
    only would give the zone back empty on the other.

    Three properties, and each repairs one way of getting it wrong:

    - **in a loop**, not in one pass: an async zone can call another,
      which is added to the queue while we await the first;
    - **in SERIES**, not in a ``gather``: the bodies share
      ``ctx.parent_stack``, so two concurrent bodies would register their
      children with each other. Concurrency is taken INSIDE a body (an
      ``asyncio.gather`` over its requests), where it does not cross the
      stack;
    - **under ``with section``**: the section was set down in the tree at
      call time, but the stack has kept living since. Pushing it back is
      what makes the children land in THE zone and not at the root.
    """
    while ctx.pending_async_zones:
        section, coro = ctx.pending_async_zones.pop(0)
        with section:
            result = await coro
            RefreshableHandle._attach_direct_return(section, result)


class RefreshableHandle:
    """Callable wrapper carrying refresh metadata.

    Behaviour :

    - Calling the handle (during a render) wraps the underlying
      function's output in a ``_RefreshableSection`` carrying the
      stable ``bz-id``. Initial render and partial re-render produce
      the SAME target shape so HTMX OOB swaps land cleanly.
    - A change to any state in ``deps=`` enqueues the zone for a partial
      re-render at end-of-action ; the free :func:`refresh` forces one
      imperatively.
    - When the zone declares ``broadcast=[State]`` its ``deps`` are the
      SSE channels : the call path (a) emits ``data-bz-subscribe-*``
      attrs (a space-separated list of the deps' wire qualnames + a
      refetch URL) so the runtime refetches on any matching signal ;
      (b) records the session against each dep on the app's SSE broker
      so a future dep-change fan-out knows which sessions to ping.
    """

    __slots__ = (
        "broadcast",
        "deps",
        "fn",
        "id",
        "is_async",
        "name",
        "zone_qualname",
    )

    def __init__(
        self,
        fn: Callable[..., Any],
        id: str,
        *,
        deps: Sequence[type] = (),
        broadcast: Sequence[type] = (),
        name: str | None = None,
    ) -> None:
        self.fn = fn
        self.id = id
        # Before anything else: a parameterised signature does not
        # survive the refresh, which calls bare. Here rather than in
        # ``_wrap`` so that it is STRUCTURAL — no handle can exist around
        # a parameterised function, whatever the construction path.
        _reject_parameters(fn, f"{fn.__module__}.{fn.__qualname__}")
        # Read ONCE at decoration time: ``iscoroutinefunction`` unwraps
        # ``functools.wraps``/``partial`` and costs an introspection we
        # do not want to pay on every zone render.
        self.is_async: bool = inspect.iscoroutinefunction(fn)
        # Wire identifier for the zone function — ``module::qualname``,
        # same scheme as action handlers. Used by the realtime route
        # to resolve the fn back through ``sys.modules`` and re-render.
        self.zone_qualname = f"{fn.__module__}{WIRE_ID_SEP}{fn.__qualname__}"
        # ── Declarative reactivity (target model) ──────────────────────
        # ``deps``: the State classes this zone reads. A change to ANY of
        # them re-renders the zone (wired in the action pipeline, Phase 3).
        # ``broadcast``: ALSO pushes the change to other clients over SSE.
        # ``name``: stable string address for ``refresh("name")``;
        # defaults to the module-qualified zone name.
        self.deps: tuple[type, ...] = tuple(deps)
        #: **The states this zone listens to over SSE.** Orthogonal to
        #: ``deps``: the two lists only overlap if the author wants them
        #: to. Empty = a purely local zone.
        #:
        #: Until 2026-08-23, ``broadcast`` was a boolean and ``deps``
        #: served TWO roles in the same word: "what re-renders me" and
        #: "what I broadcast on". Consequence, measured on
        #: `examples/crm`: a real-time zone could not declare a PERSONAL
        #: dependency — putting management's portfolio preference in it
        #: would have made the whole world refetch as soon as a single
        #: user changed THEIR setting. The real-time screen therefore did
        #: not follow the portfolio change, for want of being able to
        #: write it.
        self.broadcast: tuple[type, ...] = _resolve_broadcast(
            broadcast, self.zone_qualname
        )
        self.name: str = name or self.zone_qualname
        _ZONE_BY_NAME[self.name] = self
        for dep in self.deps:
            _ZONES_BY_DEP.setdefault(dep, []).append(self)
        for channel in self.broadcast:
            _ZONES_BY_CHANNEL.setdefault(channel, []).append(self)

    def _broadcast_qualnames(self) -> list[str]:
        """Wire qualnames of the states this zone broadcasts on.

        Empty for a local zone. Otherwise exactly the states declared in
        ``broadcast`` — which may be a strict subset of ``deps``.
        Computed on demand (deps are few), so the handle keeps no derived
        cache to maintain.
        """
        return [state_qualname(dep) for dep in self.broadcast]

    def _subscribe_url(self, states: list[str]) -> str:
        """Refetch URL for this zone. The state segment is any of the
        zone's deps (the realtime route validates membership, not exact
        match, so one URL serves a multi-dep zone). Built server-side so
        the runtime never hardcodes a framework route."""
        return f"{ROUTE_REFETCH}/{states[0]}/{self.zone_qualname}"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        ctx = maybe_current_context()

        # No active context → straight passthrough (test rigs that
        # don't go through a page render).
        if ctx is None:
            return self.fn(*args, **kwargs)

        # Broadcast zones : notify the broker that this session now
        # renders a zone for each dep State, so a future dep-change
        # fan-out knows to push to its queue. The wire attrs flow
        # through ``_RefreshableSection.render()`` and land on the
        # rendered Element for the runtime to discover.
        broadcast_states = self._broadcast_qualnames()
        subscribe_state_attr: str | None = None
        subscribe_url: str | None = None
        if broadcast_states:
            for qualname in broadcast_states:
                self._register_subscription(ctx, qualname)
            subscribe_state_attr = " ".join(broadcast_states)
            subscribe_url = self._subscribe_url(broadcast_states)

        # Push the section as the current parent, run the function, pop.
        # Children registered inside fn() (``ui.text(...)``, …) attach to
        # the section. The section renders to a single Element whose
        # ``bz-id`` matches what the partial-rerender response will
        # target via ``hx-swap-oob``.
        #
        # Returns the function's return value so the partial-render
        # path (``partials._render_one``) can pick up a directly-
        # returned Node (the test-rig idiom where ``fn`` returns a
        # ``ui.text(...).render()`` instead of registering via
        # ``parent_stack``). The full-page flow continues to ignore
        # the return.
        section = _section_cls()(
            refresh_id=self.id,
            subscribe_state_qualname=subscribe_state_attr,
            subscribe_url=subscribe_url,
        )
        # ── ASYNC body: the section is set down, the body is deferred ──
        #
        # The zone keeps its calling convention — ``zone()``, never
        # ``await zone()``. An ``await`` to write would be an ``await`` to
        # FORGET, and forgetting it would give back exactly the failure
        # this path repairs: a coroutine never awaited, hence an EMPTY
        # zone, with no error (finding [1], 2026-08-21).
        #
        # The section enters the tree NOW because the zone's place in the
        # page is decided here — at the call site — and not when its data
        # arrives. The pipeline will await the body afterwards, pushing
        # that section back onto ``parent_stack``, so the children land
        # in the right place.
        if self.is_async:
            ctx.pending_async_zones.append(
                (section, self.fn(*args, **kwargs))
            )
            return None

        with section:
            result = self.fn(*args, **kwargs)
            self._attach_direct_return(section, result)
        return result

    @staticmethod
    def _attach_direct_return(section: Any, result: Any) -> None:
        """Attach a value RENDERED directly by the body.

        The bench idiom where ``fn`` returns a ``ui.text(...).render()``
        instead of registering through ``parent_stack``. Without this
        branch, the partial path — which goes through ``__call__`` —
        would drop it.
        """
        if result is not None and (
            hasattr(result, "tag") or hasattr(result, "render")
        ):
            section.add_child(result)

    @staticmethod
    def _register_subscription(ctx: Any, state_qualname: str) -> None:
        """Notify the broker that this session now renders this zone.

        ``ctx`` is the active render context — passed in by the
        caller so we don't pay the ContextVar lookup twice per call.
        Silently no-ops in setups where the broker isn't wired (test
        rigs that bypass lifecycle).
        """
        broker = ctx.app.sse_broker
        if broker is None:
            return
        session_id = ctx.session_id
        if not session_id:
            return
        broker.subscribe(session_id, state_qualname)

    def __repr__(self) -> str:
        return f"RefreshableHandle({self.fn.__qualname__}, id={self.id!r})"


def zone_ids_watching(state_cls: type) -> frozenset[str]:
    """Return refreshable region ids that watch ``state_cls``."""
    return frozenset(
        zone.id
        for zone in (
            *_ZONES_BY_DEP.get(state_cls, ()),
            *_ZONES_BY_CHANNEL.get(state_cls, ()),
        )
    )


def enqueue_deps(ctx: Any, changed_classes: set[type]) -> None:
    """Enqueue every zone whose ``deps`` include a changed State class for
    the end-of-action refresh drain.

    Called by the action pipeline right after
    :meth:`~bretzel.state.registry.StateRegistry.diff_and_notify`. Dedup is
    by handle identity (a zone hit by several changed deps enqueues once) —
    the same ``if self not in queue`` guard an explicit refresh uses. This is
    the LOCAL auto-refresh; the cross-client broadcast for ``broadcast=[State]``
    zones is wired separately (Phase 5).

    **Only what the browser has in front of it is enqueued.**
    ``_ZONES_BY_DEP`` is indexed by state CLASS, not by page: a class
    shared by several screens drags all their zones, and without a filter
    the server rendered the other pages' zones for nothing — the browser
    threw them away for want of a target, with no error anywhere.
    Measured on 2026-09-05 on ``examples/mad``: an action from
    ``/patients`` also rendered the dashboard's zone, **8.4 ms** against
    9.6 ms for the useful one. On ``examples/crm``, ``ViewerPrefs`` drags
    14 zones across 8 modules for 4 at most per page.

    ⚠️ ``ctx.live_zones is None`` means "the client did not say" and
    **filters nothing** — not "no zone". A cached runtime, a third-party
    client or a test POSTing by hand therefore falls back on the old
    behaviour. Confusing the two would silence every zone of the first
    client that does not speak the latest version of the protocol, and
    the symptom would be a page that stops updating without anything
    raising.
    """
    if not changed_classes:
        return
    live = ctx.live_zones
    for cls in changed_classes:
        for zone in _ZONES_BY_DEP.get(cls, ()):
            if live is not None and zone.id not in live:
                continue
            enqueue(ctx, zone)


#: More row keys than this refresh the zone whole: a row patch that large
#: would cost about as much as the zone.
MAX_ROWS = 200


def row_keys(rows: Iterable[Any]) -> set[str]:
    """Row keys as the table compares them: strings, at most
    :data:`MAX_ROWS` (beyond, ``enqueue`` takes the zone whole)."""
    return {str(key) for key in rows}


def enqueue(ctx: Any, zone: RefreshableHandle, *, rows: set[str] | None = None) -> None:
    """Queue ``zone`` for the drain — whole, or for some rows. The one rule:
    a whole refresh wins over rows, and rows add up."""
    queued = zone in ctx.refresh_queue
    if not queued:
        ctx.refresh_queue.append(zone)
    if rows is None or len(rows) > MAX_ROWS:
        ctx.zone_rows.pop(zone.id, None)
    elif not queued:
        ctx.zone_rows[zone.id] = set(rows)
    elif zone.id in ctx.zone_rows:
        ctx.zone_rows[zone.id] |= rows
        if len(ctx.zone_rows[zone.id]) > MAX_ROWS:
            ctx.zone_rows.pop(zone.id)


def _publish_broadcast(
    ctx: Any, states: Iterable[type], *, rows: tuple[str, list[str]] | None = None
) -> None:
    """Push an SSE ``state-dirty`` for each state to every subscribed
    connection (tab). No-op when no broker is wired (test rigs bypassing
    the lifecycle).

    A ``SessionState`` reaches only the tabs of the session that changed
    it (``only_session``): it is that session's own data, so the other
    sessions have nothing to refetch. The other scopes reach every
    subscribed session — an ``AppState`` is shared by design, and the
    broker does not know which sessions belong to one user.

    ⚠️ **The tab that has just written is EXCLUDED** since 2026-09-09. It
    already received its zones in its action's response; its re-read
    therefore returned exactly what it was displaying — one round trip
    PER ZONE, for an identical render that idiomorph diffed to a no-op.
    Measured on ``examples/kanban``: ticking a subtask cost **five
    requests and 354 KB**, of which 177 KB were re-reads.

    This line long said the exclusion "needs a per-tab id threaded
    through the action; that optimization is deferred". That is exactly
    what was done: the browser draws an identity per page load, carries
    it in the stream's URL and in a header on every action, and the
    broker skips that connection.

    We exclude the TAB, not the session — two tabs of the same person
    must keep seeing each other. A mute client (an older runtime, a call
    outside a browser) falls back on the old behaviour: it receives its
    own broadcast, which is correct, just more expensive.
    """
    broker = getattr(ctx.app, "sse_broker", None)
    if broker is None:
        return
    emitter = getattr(ctx, "tab_id", "") or ""
    session = getattr(ctx, "session_id", "") or ""
    for cls in states:
        scoped = getattr(cls, "__scope__", None) == "session"
        qualname = state_qualname(cls)
        # A ``refresh(zone, rows=…)``: a ``zone-rows`` event naming the
        # zone and its keys. Passed only then — a broker that predates it
        # keeps working for every other signal.
        extra = {"event": SSE_EVENT_ZONE_ROWS, "data": json.dumps(
            {"state": qualname, "zone": rows[0], "rows": rows[1]})} if rows else {}
        send = partial(broker.publish, qualname, except_tab=emitter,
                       only_session=session if scoped else "", **extra)
        deferred = getattr(ctx, "deferred_broadcasts", None)
        if deferred is not None:
            deferred.append(send)  # after the commit (``RenderContext``)
        else:
            send()


def broadcast_deps(ctx: Any, changed_classes: set[type]) -> None:
    """Fan out ``state-dirty`` for every changed state that a
    ``broadcast=[State]`` zone depends on, so OTHER clients refetch it.

    Called by the action pipeline right after :func:`enqueue_deps`. No-op
    when no changed state feeds a broadcast zone — the common case, so the
    ``any(...)`` scan short-circuits cheaply.
    """
    if not changed_classes:
        return
    # The CHANNEL index, not the deps one — this is where the
    # 2026-08-23 fix plays out. A zone broadcasting on ``Deals`` and
    # ALSO reading a personal preference publishes nothing when it is the
    # preference that moves: the preference is not in this index.
    to_publish = [cls for cls in changed_classes if _ZONES_BY_CHANNEL.get(cls)]
    if to_publish:
        _publish_broadcast(ctx, to_publish)


def refreshable(
    fn: Callable[..., Any] | None = None,
    *,
    deps: Sequence[type] = (),
    broadcast: Sequence[type] = (),
    name: str | None = None,
) -> Any:
    """Wrap ``fn`` as a refreshable page region.

    The region redraws itself when a typed state named in ``deps`` changes
    (``@refreshable(deps=[MyState])``). Data kept elsewhere — a database —
    is redrawn by calling ``refresh(region)`` after writing it.
    ``broadcast`` names the states whose change must also reach the other
    open windows.
    """

    def _wrap(f: Callable[..., Any]) -> RefreshableHandle:
        return RefreshableHandle(
            fn=f,
            id=_stable_id(f),
            deps=tuple(deps),
            broadcast=broadcast,
            name=name,
        )

    # Bare ``@refreshable`` → decorate now ; ``@refreshable(...)`` → return
    # the decorator for Python to apply.
    return _wrap(fn) if fn is not None else _wrap


def refresh(
    zone_or_name: RefreshableHandle | str, *, rows: Iterable[Any] | None = None
) -> None:
    """Force a refresh of a zone — the single imperative trigger.

    ``rows=[key, …]`` refreshes only those rows of the zone's keyed
    ``ui.table`` (its ``row_key`` values): the zone runs again, but the
    table renders and ships those rows alone, and a row no longer in the
    list is removed. Whatever the framework cannot do row by row — a new
    row, a new order, a client copy it does not know — ships the zone
    whole. A whole refresh of the same zone in the same action wins.
    The contract: a row's render depends on its data, and on what
    already refreshes the table whole (filters, search, selection).

    Accepts the zone **handle** (``refresh(my_zone)`` — type-safe,
    refactor-safe) or its ``name`` **string** (``refresh("my_zone")`` —
    usable from anywhere without importing the zone, e.g. a cron or webhook).
    Enqueues it for the end-of-action OOB drain with the same identity dedup
    as the declarative ``deps=`` path. Raises loudly on an unknown name
    (never a silent no-op). Reach follows the zone's ``broadcast`` flag — the
    cross-client push for ``broadcast=[State]`` is wired separately (Phase 5).
    """
    if isinstance(zone_or_name, str):
        zone = _ZONE_BY_NAME.get(zone_or_name)
        if zone is None:
            raise ValueError(
                f"refresh(): no refreshable zone named {zone_or_name!r}. "
                f"Known zones: {sorted(_ZONE_BY_NAME)}."
            )
    else:
        zone = zone_or_name
    ctx = maybe_current_context()
    if ctx is None:
        # Out of any request (cron / webhook) : there is no response to
        # attach a local OOB swap to, and no context to reach the broker
        # through. A global broker handle for cron-driven broadcast is a
        # deferred follow-up ; no-op here.
        return
    if isinstance(rows, (str, bytes)):
        raise TypeError(
            f"refresh({zone.name}, rows=…) takes a list of row keys, not a "
            f"string: rows=[{rows!r}]."
        )
    keys = row_keys(rows) if rows is not None else None
    if keys is not None and not keys:
        return
    # Rows of a zone this page does not show: nothing to render here (the
    # whole render would be wasted, the client presenting no fingerprint),
    # only the other tabs to tell — as ``enqueue_deps`` filters its zones.
    live = ctx.live_zones
    if keys is None or live is None or zone.id in live:
        enqueue(ctx, zone, rows=keys)
    # A broadcast zone forced via refresh(x) also fans out to every
    # subscribed tab ; the acting tab additionally gets the local OOB
    # swap enqueued just above.
    if zone.broadcast:
        _publish_broadcast(ctx, zone.broadcast,
                           rows=(zone.id, sorted(keys)) if keys else None)

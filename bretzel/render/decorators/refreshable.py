"""``@refreshable`` — mark a function as a partial swap target.

The decorated function is wrapped in a :class:`RefreshableHandle`. The
handle is callable like the original function (so it slots into a page
render naturally). A zone re-renders when a field it read during its
render changes — every ``MyState()`` call made while it renders, directly
or through any helper, is recorded, and :class:`~bretzel.state.Topic`
adds what is not a state. The redraw reaches every open tab showing the
zone, as far as the scope of what changed allows; :func:`refresh` (the
free function) forces one imperatively.

"""

from __future__ import annotations

import functools
import inspect
import sys
import warnings
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from functools import partial
from types import ModuleType
from typing import Any, ClassVar

from bretzel.core import TRACKER, hash_segment
from bretzel.core.base_path import with_base
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import (
    DATA_SUBSCRIBE_STATE,
    DATA_SUBSCRIBE_URL,
    DATA_ZONE,
    DATA_ZONE_READS,
    REFETCH_SIG_PARAM,
    ROUTE_REFETCH,
    WIRE_ID_SEP,
)
from bretzel.state.scopes import SHARED_SCOPES
from bretzel.state.topic import Topic

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
        state it reads raises ``TypeError`` — **a 500 on the re-render, not on
        the page**, so in the place nobody looks. That is the case that
        motivates this refusal.

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
        f"action touching its state (never on page load), a parameter with "
        f"a default raises nothing and simply re-renders something else. "
        f"Read a state in the zone's body, or keep an ordinary "
        f"parameterisable function that the zone calls."
    )


def state_qualname(state_class: type) -> str:
    """Return the stable wire identifier for a state class."""
    return f"{state_class.__module__}{WIRE_ID_SEP}{state_class.__qualname__}"


def shared_states(classes: Iterable[type]) -> list[type]:
    """The states among ``classes`` that another tab can change. Who among
    the other tabs hears of it is the scope's business
    (:func:`_publish_broadcast`)."""
    return [cls for cls in classes if getattr(cls, "__scope__", None) in SHARED_SCOPES]


class ZoneRegistry:
    """The zones of one application, owned by it (``Bretzel.zones``).

    Filled at startup with every zone the app can reach
    (:func:`zones_reachable_from`), and by a zone's first render for a
    module imported later. Two indexes:

    - ``by_name``: refuses two zones under one name;
    - ``by_id``: the action pipeline walks it to enqueue the zones a state
      change reaches (:func:`enqueue_readers`);
    """

    __slots__ = ("by_id", "by_name")

    def __init__(self) -> None:
        self.by_name: dict[str, RefreshableHandle] = {}
        self.by_id: dict[str, RefreshableHandle] = {}

    def add(self, zone: RefreshableHandle) -> None:
        """Enter a zone; adding it again is a no-op.

        A second function under a name already taken is refused: one of
        the two would never refresh. The same function decorated again (a
        reloaded module) replaces its former self.
        """
        known = self.by_name.get(zone.name)
        if known is zone:
            return
        if known is not None and known.zone_qualname != zone.zone_qualname:
            raise ValueError(
                f"Two refreshable zones are named {zone.name!r}: "
                f"{known.zone_qualname} and {zone.zone_qualname}. "
                f"A name addresses one zone: give each its own."
            )
        self.by_name[zone.name] = zone
        self.by_id[zone.id] = zone


def zones_reachable_from(declarations: Iterable[Any]) -> Iterator[RefreshableHandle]:
    """Every zone bound to a module name in the app's own modules.

    Starts from the modules that define ``declarations`` (the pages, the
    features) and follows what those modules import: a zone must be a
    module attribute to be resolved at all, so walking them finds it,
    whichever helper module it lives in.
    """
    pending = [sys.modules[owner] for owner in
               {getattr(value, "__module__", None) for value in declarations}
               if owner in sys.modules]
    seen: set[ModuleType] = set()
    while pending:
        module = pending.pop()
        if module in seen or not _is_app_module(module):
            continue
        seen.add(module)
        for value in tuple(vars(module).values()):
            if isinstance(value, RefreshableHandle):
                yield value
            elif isinstance(value, ModuleType):
                pending.append(value)
            elif (owner := getattr(value, "__module__", None)) in sys.modules:
                pending.append(sys.modules[owner])


def _is_app_module(module: ModuleType) -> bool:
    """Is this module the app's code — not the framework, the standard
    library or an installed package?"""
    package = module.__name__.partition(".")[0]
    if package == "bretzel" or package in sys.stdlib_module_names:
        return False
    source = getattr(module, "__file__", None)
    return bool(source) and "site-packages" not in source


def zone_attrs(
    refresh_id: str,
    *,
    reads: str | None = None,
    subscription: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The attributes a zone sets IN ADDITION to its ``bz-id``.

    At module level and not on the section, because **three** paths need
    them: the render (``_RefreshableSection.render``), recomposition by a
    parent (``_rewrap``), and the fallback fragment of a zone that raised
    (``render/partials._zone_failure_fragment``).

    A hand-written third path is what this function exists to prevent:
    without ``DATA_ZONE``, after an error the zone would drop out of the
    browser's enumeration, so the ``X-Bretzel-Zones`` header would not
    carry it, so ``enqueue_readers`` would filter it out — **it would
    never refresh again** until a full reload, without a word.

    ``reads`` is what this render read (:data:`DATA_ZONE_READS`). The
    fallback fragment of a zone that raised has nothing to say and omits
    it: the server then falls back on what it learned. ``subscription`` is
    :meth:`RefreshableHandle.subscription` — empty when nothing the zone
    read can change in another tab.

    ``DATA_ZONE`` is EMPTY: the identifier is already on the same element
    as ``bz-id``. The marker says "I am a zone", ``bz-id`` says which
    one. A dedicated attribute rather than an ``id`` prefix guessed in JS
    — ``refresh_`` is a ``_stable_id`` convention, and copying it
    client-side would make a mirror that drifts.
    """
    attrs = {DATA_ZONE: ""}
    if reads is not None:
        attrs[DATA_ZONE_READS] = reads
    attrs.update(subscription or {})
    return attrs


def _stable_id(fn: Callable[..., Any], name: str | None = None) -> str:
    """Hash the zone's ``name=``, else its ``module.qualname``, to a short
    stable id.

    The id is used as the ``bz-id`` of the wrapping element, so it must
    survive code reloads but stay readable in DevTools. We keep the
    last 8 hex chars — collision risk is negligible at this scale.

    ``name=`` wins because a NAMED zone's identity is its name, unique in
    the app. Without that, zones built by a factory (``def make(s):
    @refreshable def zone(): …``) all share ``make.<locals>.zone``: one id
    on N elements — the refresh of one morphs the first — and one entry
    in the id registry, the last zone's. A factory names each zone.
    """
    qual = name or f"{fn.__module__}.{fn.__qualname__}"
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

        When this render read a state another tab can change, the section
        carries ``data-bz-subscribe-*`` (those states + a refetch URL): the
        runtime opens its EventSource for it and refetches the zone on a
        matching signal. Derived from what was read, never declared.
        """

        THEME_KEY: ClassVar[str] = "_refreshable"
        DEFAULT_TAG: ClassVar[str] = "div"
        IS_CONTAINER: ClassVar[bool] = True
        #: "I am not here." A parent sorting its children BY THEIR TYPE
        #: must see through me to find what I carry, then give me back my
        #: ``bz-id`` on the node it composed — otherwise the tab is
        #: correct and never refreshes again. Cf.
        #: ``base/composition.unwrap_transparent``.
        IS_TRANSPARENT_WRAPPER: ClassVar[bool] = True
        #: Its children's reads are this zone's, wherever they render
        #: (``base/composition.zone_of_children``).
        IS_ZONE: ClassVar[bool] = True

        def __init__(
            self,
            *,
            refresh_id: str,
            handle: RefreshableHandle,
            **kwargs: Any,
        ) -> None:
            # The handle's stable id wins over auto-generated so
            # initial render and partial rerender share one target.
            kwargs.setdefault("id", refresh_id)
            super().__init__(**kwargs)
            self._refresh_id = refresh_id
            self._handle = handle
            #: What THIS render read, as the ids the browser will hold.
            self._read: set[str] = set()
            #: The states THIS render read that another tab can change:
            #: what the browser listens to for this zone.
            self._shared: set[type] = set()

        @contextmanager
        def learning(self) -> Iterator[None]:
            """Record what the block reads for this render and its zone.

            The ONE place a render teaches its zone — the body, the async
            body, the flattening, and a child a container recomposes
            elsewhere (``base/composition.render_in_its_zone``) all go through it; a
            path that skipped it would freeze the zone without a word.
            """
            with TRACKER.recording(owner=self) as recorded:
                yield
            learned = _what_was_read(recorded)
            self._read |= _ids_of(learned)
            self._handle.learn(learned)
            new = set(shared_states(learned)) - self._shared
            if new:
                self._shared |= new
                _subscribe(new)

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
                reads=".".join(sorted(self._read)),
                subscription=self._handle.subscription(self._shared),
            )

        def render(self) -> Any:
            # Flattening calls app code back (a ``ui.datatable``'s
            # ``rows=``, a column's ``render=``): what it reaches belongs
            # to the zone as much as what its body read.
            with self.learning():
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
        with section, section.learning():
            result = await coro
            RefreshableHandle._attach_direct_return(section, result)


class RefreshableHandle:
    """Callable wrapper carrying refresh metadata.

    Behaviour :

    - Calling the handle (during a render) wraps the underlying
      function's output in a ``_RefreshableSection`` carrying the
      stable ``bz-id``. Initial render and partial re-render produce
      the SAME target shape so HTMX OOB swaps land cleanly.
    - Every field the zone reads while it renders is recorded in
      ``reads``; a change to any of them enqueues the zone for a
      partial re-render at end-of-action. The free :func:`refresh`
      forces one imperatively.
    - What it read that another tab can change (a session, user or app
      state, a ``Topic``) is its SSE subscription: the render (a) emits
      ``data-bz-subscribe-*`` attrs (their wire qualnames + a refetch URL)
      so the runtime refetches on a matching signal; (b) records the
      session against each on the app's SSE broker, so a change knows
      which sessions to ping.
    """

    __slots__ = (
        "fn",
        "id",
        "is_async",
        "name",
        "reads",
        "zone_qualname",
    )

    def __init__(
        self,
        fn: Callable[..., Any],
        id: str,
        *,
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
        #: **What this zone has read** in a render of this process: for
        #: each state class it obtained (``MyState()`` in its body or its
        #: flattening, through any helper), the fields it read — all of
        #: them when it read the class whole (a bulk read, a
        #: ``@computed``, ``@reads``, or obtained without reading a
        #: field). A UNION, never replaced — the FALLBACK for a client
        #: that does not say what its version read, and the guess of what
        #: the other clients show; a client that says
        #: decides for itself (``data-bz-r``). ``None`` = never rendered
        #: here (a restart, another worker): :func:`enqueue_readers` then
        #: re-renders it, the safe side.
        self.reads: dict[type, frozenset[str]] | None = None
        self.name: str = name or self.zone_qualname

    def subscription(self, states: Iterable[type]) -> dict[str, str]:
        """The subscription attributes for a version of this zone that read
        ``states`` — none when nothing it read can change in another tab.

        The refetch URL is built server-side, so the runtime never
        hardcodes a framework route, and signed for the session that
        renders it, which the route requires.
        """
        names = sorted(state_qualname(cls) for cls in shared_states(states))
        if not names:
            return {}
        ctx = maybe_current_context()
        sig = ctx.refetch_signature(self.zone_qualname) if ctx is not None else ""
        url = with_base(f"{ROUTE_REFETCH}/{self.zone_qualname}") + (
            f"?{REFETCH_SIG_PARAM}={sig}" if sig else "")
        return {DATA_SUBSCRIBE_STATE: " ".join(names), DATA_SUBSCRIBE_URL: url}

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        ctx = maybe_current_context()

        # No active context → straight passthrough (test rigs that
        # don't go through a page render).
        if ctx is None:
            return self.fn(*args, **kwargs)

        ctx.app.zones.add(self)

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
        section = _section_cls()(refresh_id=self.id, handle=self)
        # ── ASYNC body: the section is set down, the body is deferred ──
        #
        # The zone keeps its calling convention — ``zone()``, never
        # ``await zone()``. An ``await`` to write would be an ``await`` to
        # FORGET, and forgetting it would give back exactly the failure
        # this path repairs: a coroutine never awaited, hence an EMPTY
        # zone, with no error.
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

        with section, section.learning():
            result = self.fn(*args, **kwargs)
            self._attach_direct_return(section, result)
        return result

    def learn(self, learned: dict[type, frozenset[str]]) -> None:
        """Add what a render read to what this process knows the zone reads
        — the fallback for a client that does not say, and the guess for
        what the other clients show. Nothing is written once known:
        renders run in threadpool threads, and a map rebuilt on every
        render could lose a concurrent addition."""
        known = self.reads or {}
        merged = dict(known)
        for cls, fields in learned.items():
            merged[cls] = known.get(cls, frozenset()) | fields
        if merged != self.reads:
            self.reads = merged

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

    def __repr__(self) -> str:
        return f"RefreshableHandle({self.fn.__qualname__}, id={self.id!r})"


def _subscribe(states: Iterable[type]) -> None:
    """Tell the broker this session now shows zones reading ``states``, so
    a change to one of them knows to ping it. No-op without a request or a
    broker (test rigs that bypass the lifecycle)."""
    ctx = maybe_current_context()
    broker = getattr(getattr(ctx, "app", None), "sse_broker", None)
    session_id = getattr(ctx, "session_id", "")
    if broker is None or not session_id:
        return
    for cls in states:
        broker.subscribe(session_id, state_qualname(cls))


def _what_was_read(recorded: Any) -> dict[type, frozenset[str]]:
    """A recording, as a zone keeps it: each class → the fields it read.

    Every declared field when the class was read whole (a bulk read,
    ``@reads``), or obtained without a field read through a descriptor
    — it may have been handed to code that reads it otherwise. A name
    that is not a field (a ``@computed``'s own) is dropped: what the
    computed read was replayed with it.
    """
    out: dict[type, frozenset[str]] = {}
    for cls in recorded.fields.keys() | recorded.whole:
        declared = cls._all_fields().keys()
        names = recorded.fields.get(cls, set()) & declared
        whole = cls in recorded.whole or not names
        out[cls] = frozenset(declared if whole else names)
    return out


@functools.lru_cache(maxsize=4096)
def field_id(cls: type, name: str) -> str:
    """The short wire identifier of a state field — derived from the code,
    so the same on every worker. Two fields sharing one (16M values) cost
    a re-render too many, never one too few."""
    return hash_segment(f"{state_qualname(cls)}.{name}")[:6]


def _ids_of(read: dict[type, frozenset[str]]) -> set[str]:
    return {field_id(cls, name) for cls, names in read.items() for name in names}


def _changed_ids(changes: dict[type, set[str]]) -> set[str]:
    """The changes as field ids — every field of a class whose changed
    fields are unknown."""
    return {
        field_id(cls, name)
        for cls, moved in changes.items()
        for name in (moved or cls._all_fields())
    }


def _reads_field(reads: dict[type, frozenset[str]], cls: type, moved: set[str]) -> bool:
    """Did this change of ``cls`` touch a field the zone read? Changed
    fields unknown (an empty set) count as the whole class — the safe
    side."""
    read = reads.get(cls)
    return read is not None and (not moved or not read.isdisjoint(moved))


def _reads_a_change(
    reads: dict[type, frozenset[str]], changes: dict[type, set[str]]
) -> bool:
    """Did one of these changes touch a field the zone read?"""
    return any(_reads_field(reads, cls, moved) for cls, moved in changes.items())


def enqueue_readers(ctx: Any, changes: dict[type, set[str]]) -> None:
    """Enqueue every zone that read a changed field for the end-of-action
    refresh drain.

    ``changes`` is the registry's ``changed_fields``
    — each changed class → the names of its fields that moved — read by
    the action pipeline right after
    :meth:`~bretzel.state.registry.StateRegistry.diff_and_notify`. Dedup is
    by handle identity (a zone hit by several changed states enqueues
    once) — the same ``if self not in queue`` guard an explicit refresh
    uses. This is the acting tab's redraw; the other tabs hear of it
    through :func:`broadcast_changes`.

    **Only what the browser has in front of it is enqueued.** A state
    shared by several screens reaches all their zones, and without a
    filter the server would render the other pages' zones for nothing —
    the browser would throw them away for want of a target, with no error
    anywhere.

    **By field, per client.** A zone that read ``View.q`` is not
    re-rendered when only ``View.ticket`` moved. What it read is what THIS
    browser's version of the zone read: the zone carries it
    (``data-bz-r``) and the browser sends it back with the zone's id, so
    the answer is exact per client and the same on every worker. A zone
    the browser does not describe (an older runtime, a fallback fragment)
    falls back on what this process learned; one this process never
    rendered is re-rendered, which also teaches it.

    ⚠️ ``ctx.live_zones is None`` means "the client did not say" and
    **filters nothing** — not "no zone". A cached runtime, a third-party
    client or a test POSTing by hand therefore gets every zone that
    read the change. Confusing the two would silence every zone of the
    first client that does not speak the latest version of the protocol.
    """
    if not changes:
        return
    live = ctx.live_zones
    shown = ctx.zone_reads
    changed = _changed_ids(changes) if shown else set()
    # A snapshot: a lazy import in another thread may decorate a zone.
    for zone in tuple(ctx.app.zones.by_id.values()):
        if live is not None and zone.id not in live:
            continue
        held = shown.get(zone.id)
        if held is not None:
            if not held.isdisjoint(changed):
                enqueue(ctx, zone)
        elif zone.reads is None:
            if live is not None:
                enqueue(ctx, zone)
        elif _reads_a_change(zone.reads, changes):
            enqueue(ctx, zone)


def enqueue(ctx: Any, zone: RefreshableHandle) -> None:
    """Queue ``zone`` for the drain, once."""
    if zone not in ctx.refresh_queue:
        ctx.refresh_queue.append(zone)


def _publish_broadcast(ctx: Any, states: Iterable[type]) -> None:
    """Push an SSE ``state-dirty`` for each state to every subscribed
    connection (tab). No-op when no broker is wired (test rigs bypassing
    the lifecycle).

    A ``SessionState`` reaches only the tabs of the session that changed
    it (``only_session``), a ``UserState`` only the tabs of the user who
    changed it, on any of their devices (``only_user``): their own data —
    the signal would otherwise tell everybody else WHEN they act. An
    ``AppState`` is shared by design and reaches every subscribed tab.

    ⚠️ **The tab that has just written is EXCLUDED.** It already received
    its zones in its action's response; its re-read would return exactly
    what it is displaying — one round trip PER ZONE, for an identical
    render that idiomorph diffs to a no-op.

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
    user = getattr(ctx, "user_id", "") or ""
    for cls in states:
        scope = getattr(cls, "__scope__", None)
        qualname = state_qualname(cls)
        if scope == "user" and not user:
            # No one to address: ``only_user=""`` filters nothing, and the
            # signal would reach every session.
            continue
        extra = {"only_user": user} if scope == "user" else {}
        send = partial(broker.publish, qualname, except_tab=emitter,
                       only_session=session if scope == "session" else "", **extra)
        deferred = getattr(ctx, "deferred_broadcasts", None)
        if deferred is not None:
            deferred.append(send)  # after the commit (``RenderContext``)
        else:
            send()


def broadcast_changes(ctx: Any, changes: dict[type, set[str]]) -> None:
    """Fan out ``state-dirty`` for every changed state another tab can see
    and some zone shows, so the OTHER tabs showing it refetch it.

    Called by the action pipeline right after :func:`enqueue_readers`,
    with the same ``changes``. A ``PageState`` never leaves its tab. A
    state publishes only when a field some zone read moved: a ``Tables``
    channel stays quiet when the write touched a table no zone shows. A
    zone this process never rendered counts as reading everything — the
    safe side. Who receives the signal is the scope's business
    (:func:`_publish_broadcast`), and only the sessions that rendered a
    zone reading the state are subscribed to it.
    """
    zones = tuple(ctx.app.zones.by_id.values())
    to_publish = [
        cls for cls in shared_states(changes)
        if any(zone.reads is None or _reads_field(zone.reads, cls, changes[cls])
               for zone in zones)
    ]
    if to_publish:
        _publish_broadcast(ctx, to_publish)


def refreshable(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Wrap ``fn`` as a refreshable page region.

    The region redraws itself when a typed state it reads changes —
    every ``MyState()`` it calls while it renders, directly or through a
    helper. Data kept elsewhere — a database, the clock — is followed
    through a :class:`~bretzel.state.Topic`. The redraw reaches every open
    tab showing the region, as far as the scope of what changed allows: a
    ``PageState`` stays in its tab, a ``SessionState`` in its session, a
    ``UserState`` with its user, an ``AppState`` and a ``Topic`` go to all.
    """

    def _wrap(f: Callable[..., Any]) -> RefreshableHandle:
        return RefreshableHandle(
            fn=f,
            id=_stable_id(f, name),
            name=name,
        )

    # Bare ``@refreshable`` → decorate now ; ``@refreshable(...)`` → return
    # the decorator for Python to apply.
    return _wrap(fn) if fn is not None else _wrap


def refresh(target: RefreshableHandle | Topic) -> None:
    """Force a refresh of a zone — the single imperative trigger.

    Takes the zone itself (``refresh(my_zone)``). Enqueues it for the
    end-of-action OOB drain with the same identity dedup as the automatic
    path, in THIS tab: nothing tells the others what was not written.

    A :class:`~bretzel.state.Topic` redraws every zone reading it, in
    every tab showing one.

    It works DURING a request (an action, a page). Outside one — a cron,
    a webhook's background task — there is no response to carry the zone
    and no connection to reach: it does nothing, and WARNS
    (``RuntimeWarning``).
    """
    if isinstance(target, str):
        raise TypeError(
            f"refresh({target!r}): pass the zone itself, `refresh(my_zone)`, "
            f"or a Topic to redraw every zone reading it."
        )
    if isinstance(target, Topic):
        target._ring()
    ctx = maybe_current_context()
    if ctx is None:
        # Out of any request (cron / webhook): no response to attach the
        # zone to, no context to reach the broker through. Silence here
        # was the bug — the call LOOKED like it worked. A warning and not
        # a raise: code shared between an action and a start-up must not
        # crash on it.
        label = target.__name__ if isinstance(target, Topic) else target.name
        warnings.warn(
            f"refresh({label!r}) outside a request reaches no screen: "
            f"there is no response to carry the zone and no open "
            f"connection to tell. Call it from an action or a page; a zone "
            f"refreshed from a background task is not supported yet.",
            RuntimeWarning, stacklevel=2,
        )
        return
    if isinstance(target, Topic):
        return
    enqueue(ctx, target)

"""``Component`` — the single base class apps and component authors subclass.

The class is intentionally **flat** (no Element → InteractiveElement →
BaseComponent inheritance chain from v1) ; behaviour is composed
through the ``base/*`` helper modules instead. Subclasses set a few
class-level constants, declare reactive props, and override
:py:meth:`render`.

"""

from __future__ import annotations

import typing
from typing import Any, ClassVar

from bretzel.components.base.attrs import (
    EVENT_PATTERN,
    ComponentUsageError,
    normalize_attr_name,
    reject_dead_alpine_attr,
    split_kwargs,
)
from bretzel.components.base.callbacks import _BUILT_IN_CALLBACK
from bretzel.components.base.class_composition import ClassComposition
from bretzel.components.base.client_wiring import ClientWiring
from bretzel.components.base.composition import (
    parent_to_name_under,
    zone_of_children,
)
from bretzel.components.base.events import (
    HandlerError,
    action_attrs,
    auto_busy,
    carrier_attrs,
    client_event_attr,
)
from bretzel.components.base.focus import accept_autofocus
from bretzel.components.base.metaclass import _ComponentMeta
from bretzel.components.base.nodes import merge_attr
from bretzel.components.base.reactive_prop import (
    ReactivePropDescriptor,
    fill_defaults,
)
from bretzel.components.base.responsive import reject_stray_breakpoints
from bretzel.components.base.scope_wiring import own_field
from bretzel.components.base.universals import _reject_unknown_slot_keys, statically_hidden
from bretzel.core.tree import Element, Node, TextNode
from bretzel.render.context import current_context, maybe_current_context
from bretzel.render.iteration import current_iteration_key
from bretzel.runtime.protocol import (
    BZ_ATTR_PREFIX,
    BZ_ID_ATTR,
)
from bretzel.state.scopes.client import ClientBinding, ClientExpression

# ───────────────────────────────────────────────────────────────────────────
# Metaclass
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# Component
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# THE attribute precedence — one contract, written once
# ───────────────────────────────────────────────────────────────────────────


class Component(ClassComposition, ClientWiring, metaclass=_ComponentMeta):
    """Base class for every Bretzel component.

    Subclass contract (each is opt-in, sensible defaults provided) :

    - ``THEME`` : the per-component theme dict (typically imported from
      the sibling ``theme.py``). The framework's ``app.theme`` walks
      ``THEME_KEY`` to pull a possibly-merged version at render time.
    - ``THEME_KEY`` : key under ``app.theme.components`` ; empty by
      default (the component will then use its class-level ``THEME``
      directly with no user-override merge).
    - ``DEFAULT_TAG`` : the HTML tag the default :py:meth:`render`
      emits when the subclass doesn't override it.
    - ``IS_CONTAINER`` : ``True`` (default) for components that accept
      children via ``with`` blocks ; ``False`` for leaves like
      :class:`TextNode` or :class:`Icon`.
    - ``NAMED_SLOTS`` : tuple of typed-slot kwargs (``("icon", "icon_right")``
      on a Button) — populates ``self._slot_components`` at construction.
    - ``EVENTS`` : tuple of supported event names (``("click", "focus")``).
      The metaclass cross-checks this against ``__init__`` parameters
      named ``on_<event>``.
    - Reactive props : declared as class attributes via
      :func:`reactive_prop` — picked up automatically by the metaclass.
    """

    # ── Class-level configuration (overridden by subclasses) ────────────

    THEME: ClassVar[dict[str, Any]] = {}
    THEME_KEY: ClassVar[str] = ""
    DEFAULT_TAG: ClassVar[str] = "div"
    IS_CONTAINER: ClassVar[bool] = True
    #: "I am not here": a parent sorting its children by type looks
    #: through this wrapper (``composition.unwrap_transparent``).
    IS_TRANSPARENT_WRAPPER: ClassVar[bool] = False
    #: Its children's reads belong to this ``@refreshable`` zone
    #: (``composition.zone_of_children``).
    IS_ZONE: ClassVar[bool] = False
    #: "The screen is me": the frame of a frozen document
    #: (``page_checks``).
    IS_FROZEN_FRAME: ClassVar[bool] = False
    #: It draws its children its own way, so none of them can be a zone
    #: that redraws alone (``composition.unwrap_transparent``).
    _COMPOSES_CHILDREN: ClassVar[bool] = False
    #: ``False`` when the colour paints a teleported panel only and the
    #: root wraps a foreign trigger (``theme_values.root_color_bridge``).
    _COLOR_ON_ROOT: ClassVar[bool] = True
    #: **Who owns the loop**, for a component rendering a COLLECTION —
    #: it is what decides its API, and it is not a matter of taste. Four
    #: values, four forced consequences:
    #:
    #: - ``"author"`` — the author writes their own ``for``. The
    #:   component MUST accept children (``IS_CONTAINER = True``),
    #:   otherwise the author has nowhere to put their markup. A data
    #:   parameter (``options=``) is still welcome as a shortcut for the
    #:   simple case — that is ``toggle_group``'s shape, and the two
    #:   tiers of the "two-tier API" memory.
    #: - ``"component"`` — the component owns the loop and the author
    #:   CANNOT write it: ``datatable`` searches, filters, sorts and
    #:   paginates. It MUST therefore expose a content callback
    #:   (``render=``), the only possible entry point for markup.
    #: - ``"client"`` — it is the BROWSER that re-renders the list at
    #:   runtime (``combobox``: "built once server-side so the JS filter
    #:   only does a…"). Neither children nor a Python callback reach it;
    #:   it needs a mechanism of its own, and the docstring must say
    #:   which.
    #: - ``"data"`` — the items have NO markup to carry: they are
    #:   attributes. ``ui.video(tracks=[…])`` renders one ``<track>`` per
    #:   track, five attributes and nothing else. Neither children nor a
    #:   content callback would have a recipient, so the component stays
    #:   a leaf and exposes no callback — both consequences are checked
    #:   by the gate, so that the box does not become the one where one
    #:   files what one did not want to decide.
    #:
    #: ``None`` = this component renders no collection. The
    #: ``test_collection_owner_decides_the_api`` gate DETECTS collections
    #: (does the render grow when the data grows?) and requires the
    #: declaration — written here rather than guessed, because an AI
    #: reading the catalogue copies the first pattern it meets: that is
    #: exactly how ``breadcrumb`` got a ``render=`` when its 10 peers
    #: take children.
    COLLECTION_OWNER: ClassVar[str | None] = None
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ()
    # Subset of ``NAMED_SLOTS`` whose values should accept a string
    # shortcut and get auto-wrapped in ``ui.icon(name)``. Lets callers
    # write ``ui.button("Save", icon_left="save")`` for the common case
    # without the verbose ``icon=ui.icon("save")`` boilerplate. The
    # full Component form still flows through unchanged — strings are
    # the only special case here.
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ()
    # Reactive props declared on the class but which the ``__init__``
    # REFUSES at the call site. The typical case is a shortcut whose axis
    # is its very identity: ``HStack`` declares ``direction`` (inherited
    # from ``Flex``, pinned to ``"row"``) and raises if it is passed.
    #
    # Without this declaration, the only way to know the actually
    # accepted set would be to read the ``__init__``'s BODY — which no
    # introspection does. ``bretzel.introspect`` therefore subtracts them
    # from the card: listing them would announce a parameter that raises,
    # which is the same fault as hiding one that works. Guarded in both
    # directions by
    # ``tests/consistency/test_introspect_sees_inherited_props.py``: a
    # sealed prop must REALLY be refused, otherwise the declaration would
    # become a convenient way of silencing the gate.
    SEALED_PROPS: ClassVar[tuple[str, ...]] = ()

    # The ``THEME`` keys whose values can come back PREFIXED by a
    # breakpoint, because a graded prop goes through them via
    # :func:`responsive_classes` (``gap={"base": "sm", "md": "lg"}`` →
    # ``gap-2 md:gap-6``).
    #
    # It is a DECLARATION, not introspection: the prefixing is decided in
    # ``render()``, which the safelist cannot execute. Without it,
    # ``md:gap-6`` exists literally in no file — so it never reaches the
    # compiled ``style.css``, so the gap disappears in PRODUCTION while
    # being correct in dev (the browser compiler scans the live DOM).
    #
    # Same mechanics as the colour templates, same bridge: it is
    # ``components`` that declares and ``theme`` that closes (cf.
    # ``components/color_shapes.py`` and the import-linter contract).
    # The values that do NOT come from a theme table but from an f-string
    # over a scalar (``grid-cols-N``) stay in
    # ``_LAYOUT_CLASSES`` — their domain is not enumerable here.
    #
    # Gated by ``tests/consistency/test_responsive_classes_are_safelisted.py``.
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = ()

    #: The props that accept a step dict ``{"base": …, "md": …}``.
    #:
    #: ⚠️ Not to be confused with ``RESPONSIVE_THEME_KEYS`` just above,
    #: which names THEME tables and serves the safelist. This one names
    #: PROPS and serves the refusal: a step dict on a prop absent from
    #: here is a usage error, and the base layer says so —
    #: :func:`~bretzel.components.base.responsive.reject_stray_breakpoints`,
    #: called by this constructor.
    #:
    #: Empty by default, and that is the right default: five props out of
    #: ~600 are graded (``flex.direction``/``gap``, ``grid.cols``/``gap``,
    #: ``resizable.gap``, ``carousel.per_view``). Everything else is a
    #: STRUCTURAL choice belonging to ``if Screen().is_mobile:`` in the
    #: layout, not to a prop — cf. the header of ``base/responsive.py``.
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = frozenset()

    # One server handler PER EVENT: the first in ``EVENTS`` order rides
    # the root (one ``hx-post``), each further one a hidden carrier
    # listening FROM the root (``events.carrier_attrs`` / ``with_carriers``).
    # The class decides which, not the call: the message box's submit
    # must be the form's own request, however its handlers are written.
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = True
    #: A declared event the DOM knows under another name (``month_change``
    #: is the calendar's ``month-change``): what a carrier listens to.
    DOM_EVENTS: ClassVar[dict[str, str]] = {}

    # Autoname : when set, ``emit_attrs`` derives the HTML ``name``
    # attribute from the ClientBinding stored under this reactive
    # prop. Typically ``"value"`` for text inputs / select / radio,
    # ``"checked"`` for checkbox / switch. ``None`` (default) opts
    # the component out — buttons, layouts, primitives, etc.
    AUTONAME_FROM: ClassVar[str | None] = None

    # Whitelist of reactive_props + slot kwargs that accept a
    # ``ClientBinding`` / ``ClientExpression``. The contract is:
    #
    # - **Default = ``()``** → no binding accepted. A component that
    #   forgets to declare therefore refuses EVERY ``ClientBinding``,
    #   loudly, on the first use.
    # - **Declared as a tuple** → only the listed props/slots accept
    #   ``ClientBinding``; everything else raises ``ComponentUsageError``
    #   at ``__init__``.
    # - Subclasses declare the curated set of props that genuinely
    #   need to update at runtime (typically: the data field, the
    #   disabled flag, the loading flag, the open flag for overlays).
    # - Visual configuration (variant / size / color / type, etc.)
    #   stays out — set once at design time. Conditional server-side
    #   render covers the rare dynamic case
    #   (``ui.badge(color="error" if state.failed else "success")``).
    # - Universal modifiers (``visible``, ``tooltip``, ``classes``,
    #   ``style``) are bindable on every component — they are popped
    #   before the check and not subject to it.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    # The props the CLIENT WRITES — the user types, ticks, opens, picks.
    # A subset of ``BINDABLE_PROPS``: their client path is the
    # ASSIGNMENT TARGET in the JS emitted (``bz-model`` compiles
    # ``<path> = $value``; the overlays emit ``<path> = false``; the rich
    # scopes have a ``_write(v) { <path> = v }``).
    #
    # Direct consequence: a ``ClientExpression`` is structurally invalid
    # there — ``(a || b) = $value`` is a SyntaxError, raised by the
    # browser **at bind time**, not on the first click. The constructor
    # therefore rejects it early, with a message explaining what to do.
    #
    # ⚠️ This is NOT ``AUTONAME_FROM``. ``AUTONAME_FROM`` answers "where
    # do I derive my HTML name= from"; this answers "what does the client
    # write". Borrowing one for the other couples server-sync to form
    # naming.
    #
    # ``AUTONAME_FROM`` is a conceptual subset: some components write a
    # value without taking part in a form submission. The server can only
    # re-adopt what the client writes.
    TWO_WAY_PROPS: ClassVar[tuple[str, ...]] = ()

    # Names of the write-only imperative methods this component exposes
    # (in addition to ``ClientBinding``). Some are plain class methods
    # (``def set`` on inputs) ; some are assigned per-instance in
    # ``__init__`` (the non-data-descriptor trick on overlays / Accordion,
    # where the method name would otherwise shadow a reactive_prop like
    # ``open``). Declaring them here gives a single, class-level,
    # introspectable source of truth for the imperative surface — read by
    # the docs catalogue and guarded by ``test_imperative_classvar``.
    # Empty tuple = no imperative API (buttons, layouts, primitives, …).
    IMPERATIVE: ClassVar[tuple[str, ...]] = ()

    # Where this component takes the focus, ``None``: nowhere (``autofocus=``
    # refused). Read by ``autofocus=`` and ``.focus()`` — cf. ``base/focus.py``.
    FOCUS_TARGET: ClassVar[tuple[str, ...] | None] = None

    # Populated by the metaclass.
    __reactive_props__: ClassVar[dict[str, ReactivePropDescriptor]] = {}
    # prop → ``bz-data`` scope keys (derived from ``reactive_prop(
    # scope_keys=)`` by the metaclass; default ``(prop,)``).
    __scope_keys__: ClassVar[dict[str, tuple[str, ...]]] = {}

    # ── Construction ───────────────────────────────────────────────────

    def __init__(self, *_args: Any, **kwargs: Any) -> None:
        ctx = current_context()

        # Pop reserved framework kwargs first so they don't pollute the
        # bucket split below.
        # ``classes=`` and ``style=`` accept either a literal string or
        # a ``ClientBinding`` / ``ClientExpression``. The binding form
        # takes a reactive path : ``classes`` binding concatenates onto
        # the static composition via an inline client expression ;
        # ``style`` binding becomes a ``bz-attr:style`` binding. We
        # capture both forms up here so the bool-coercion trap in
        # ClientBinding doesn't fire when downstream code tests
        # truthiness of the literal slot.
        raw_classes = kwargs.pop("classes", None)
        if isinstance(raw_classes, ClientBinding):
            self._classes_binding: ClientBinding | None = raw_classes
            self._classes = None
        else:
            self._classes_binding = None
            self._classes = raw_classes
        raw_style = kwargs.pop("style", None)
        if isinstance(raw_style, ClientBinding):
            self._style_binding: ClientBinding | None = raw_style
            self._style: Any = None
        else:
            self._style_binding = None
            self._style = raw_style
        self._user_slots = kwargs.pop("slots", None)
        self._key = kwargs.pop("key", None)
        explicit_id = kwargs.pop("id", None)
        # Track whether the caller wired an ``id=`` explicitly — without
        # this flag, ``emit_attrs`` only emits the framework-generated
        # ``id`` when ``_needs_identity()`` is True (i.e. the runtime
        # needs to track the element). A user-supplied ``id=`` is an
        # explicit intent and must reach the DOM regardless.
        self._user_provided_id: bool = explicit_id is not None
        explicit_tag = kwargs.pop("tag", None)
        # ``attrs={...}`` is the universal escape hatch for arbitrary
        # HTML attributes (``data-*``, ``aria-*``, ``role``, ``name``,
        # ``form``, …) that don't have a dedicated kwarg on the
        # component. We pop here so the dict doesn't land in
        # ``raw_html`` as a single ``attrs="..."`` literal — instead
        # we merge its key/value pairs into the raw-attrs bag below.
        # ``None`` or empty dict → no-op.
        # ``outlet=<layout>`` — WHICH region this link replaces. The
        # primitive lives in ``_wiring``: that is where the others are,
        # and it is the only place in the base layer allowed to write
        # ``hx-``.
        _outlet = kwargs.pop("outlet", None)
        if _outlet is not None:
            from bretzel.components.base.scope_wiring import outlet_target_attrs

            kwargs["attrs"] = {
                **(kwargs.get("attrs") or {}),
                **outlet_target_attrs(type(self).__name__, _outlet),
            }
        explicit_attrs = kwargs.pop("attrs", None)
        if explicit_attrs is not None and not isinstance(explicit_attrs, dict):
            raise ComponentUsageError(
                f"{type(self).__name__}(attrs=…) expects a dict, got "
                f"{type(explicit_attrs).__name__}. Use ``attrs={{'data-x': "
                "'y'}}`` to pass arbitrary HTML attributes."
            )
        if explicit_attrs:
            # Same refusal as in ``split_kwargs``: ``attrs=``
            # short-circuits the dispatcher, so without this check an
            # ``@click`` refused in ``**kwargs`` would pass silently
            # through ``attrs={...}``. An Alpine attribute is as inert by
            # one route as by the other.
            for _attr_name in explicit_attrs:
                reject_dead_alpine_attr(type(self).__name__, str(_attr_name))
        # ``visible`` and ``tooltip`` are universal modifiers applied
        # post-render by the metaclass wrap (cf. ``_ComponentMeta`` +
        # ``_apply_universal_modifiers``). Every Component subclass
        # gets them for free — no per-component plumbing needed.
        self._visible: Any = kwargs.pop("visible", None)
        self._tooltip: Any = kwargs.pop("tooltip", None)
        # ``debounce=`` / ``throttle=`` (milliseconds) gate how often a
        # SERVER event fires — emitted as HTMX trigger modifiers
        # (``delay:`` / ``throttle:``). E.g. search-as-you-type :
        # ``ui.input(on_input=search, debounce=300)``. Mutually exclusive ;
        # a no-op on a purely client-side handler (these are htmx-only).
        _debounce = kwargs.pop("debounce", None)
        _throttle = kwargs.pop("throttle", None)
        if _debounce is not None and _throttle is not None:
            raise ComponentUsageError(
                f"{type(self).__name__}: pass debounce= OR throttle=, not both."
            )
        self._trigger_modifier: str | None = (
            f"delay:{int(_debounce)}ms"
            if _debounce is not None
            else f"throttle:{int(_throttle)}ms"
            if _throttle is not None
            else None
        )
        self._autofocus: bool = accept_autofocus(self, kwargs.pop("autofocus", False))
        # ``loading=False``: no automatic busy state (``events.auto_busy``).
        _own = "loading" in type(self).__reactive_props__
        _loading = kwargs.get("loading") if _own else kwargs.pop("loading", None)
        self._auto_busy: bool = auto_busy(type(self).__name__, _loading, declared=_own)
        # The Tooltip wrapper instance must be built HERE — the render
        # context is live in ``__init__`` (id allocation, parent-stack
        # auto-attach + adopt_slot detach), but may be torn down by the
        # time ``render()`` runs (unit-test convention). Tooltip itself
        # bypasses this — wrapping a tooltip in a tooltip is nonsense
        # and would recurse through its own super().__init__.
        # The empty-string check is deliberately ``isinstance(str)``
        # gated — ``ClientBinding`` raises ``ReactivityError`` when
        # compared with ``!=`` (forbidden bool coercion), so guard the
        # comparison to literal strings.
        self._tooltip_wrapper: Component | None = None
        _tt = self._tooltip
        _tt_is_empty_str = isinstance(_tt, str) and _tt == ""
        if _tt is not None and not _tt_is_empty_str and type(self).__name__ != "Tooltip":
            from bretzel.components.overlay.tooltip import Tooltip

            self._tooltip_wrapper = Component.adopt_slot(Tooltip(_tt))

        # ── List-valued event handlers: compose server + client ───────
        #
        # ``on_<event>=[…]`` lets a caller chain handlers on a single
        # event without dropping into client-expression string territory. Items
        # in the list can be:
        #
        # - a callable → routed as the server action (native ``hx-post`` +
        #   HMAC stamp, only one allowed per event — cf. ``action_attrs``)
        # - a string   → a client-side expression to fire alongside,
        #   joined with ``;`` and emitted as ``bz-on:<event>``
        #
        # Use case: optimistic close on a dialog confirm button —
        # ``on_click=[delete_account, dlg.close()]`` runs the server
        # action AND closes the dialog client-side in one click.
        # The type test FIRST, the regex afterwards: we only look here
        # for LIST-valued events, and almost no kwarg is a list. Testing
        # ``isinstance`` (C, immediate) before ``EVENT_PATTERN.match``
        # avoids running the regex over each instance's kwargs — and
        # ``split_kwargs`` will re-match them right afterwards anyway.
        for ev_key in [
            k for k, v in kwargs.items() if isinstance(v, (list, tuple)) and EVENT_PATTERN.match(k)
        ]:
            value = kwargs[ev_key]
            callables = [x for x in value if callable(x) and not isinstance(x, str)]
            strings = [str(x) for x in value if isinstance(x, str)]
            if len(callables) > 1:
                raise ComponentUsageError(
                    f"{type(self).__name__}: only one server callable "
                    f"is allowed in {ev_key} (got {len(callables)})."
                )
            kwargs.pop(ev_key)
            if callables:
                kwargs[ev_key] = callables[0]
            if strings:
                event_name = ev_key[3:]  # drop ``on_``
                # Joined with `;` so each client expression runs in
                # order. Existing ``bz-on:<event>`` from the caller
                # would be a duplicate kwarg and is forbidden by
                # Python — we don't merge silently to avoid surprising
                # behaviour.
                kwargs[f"bz-on:{event_name}"] = "; ".join(strings)

        cls = type(self)
        reactive, slots, events, passthrough, raw_html = split_kwargs(cls, kwargs)

        # Validate slot names against the declared NAMED_SLOTS.
        for slot_name in slots:
            if slot_name not in cls.NAMED_SLOTS:
                raise ComponentUsageError(
                    f"{cls.__name__} doesn't declare a {slot_name!r} slot "
                    f"(NAMED_SLOTS = {cls.NAMED_SLOTS!r})."
                )

        # Same geste for the theming ``slots={…}`` kwarg (a different
        # concept from NAMED_SLOTS above : theme slots, not child slots).
        # Here rather than post-render so it croaks at the construction
        # site like every other ``ComponentUsageError`` — a component
        # built but never rendered would otherwise never report the typo.
        if self._user_slots:
            _reject_unknown_slot_keys(self, self._user_slots)
        # Validated → ``_resolved_theme`` can now merge them into the
        # slots, which makes them visible to the 164 manual reads of
        # ``theme["slots"][X]``. Before validation, merging would make
        # every typo "known" and the refusal would never raise.
        self._user_slots_validated: bool = True

        # ── Bindable-props gate ─────────────────────────────────────────
        # Held in ``owning_init``
        # (``base/arguments.refuse_an_undeclared_binding``): it sees EVERY
        # argument, where this place sees only reactive props and slots.

        # ── Two-way props: an expression is not assignable ────────────────
        # These props' client path is the ASSIGNMENT TARGET in the JS
        # emitted. A ClientExpression compiles there to
        # ``(a || b) = $value`` → a SyntaxError raised by the browser AT
        # BIND TIME (``compile(expr, "set")``, directives.js), so the
        # component is dead before any interaction. We refuse at
        # construction, with the way out.
        if cls.TWO_WAY_PROPS:
            two_way = set(cls.TWO_WAY_PROPS)
            for kw_name, kw_value in reactive.items():
                if kw_name not in two_way:
                    continue
                if isinstance(kw_value, ClientExpression):
                    raise ComponentUsageError(
                        f"{cls.__name__}.{kw_name} is a two-way prop: the "
                        f"client writes into it, so it requires an "
                        f"assignable ClientState field — a computed "
                        f"expression ({kw_value.binding_path()!r}) is not a "
                        f"valid assignment target. Pass the field directly "
                        f"({kw_name}=state.field) and compute the expression "
                        f"where you READ it (visible=, disabled=, tooltip=…)."
                    )
                # ── …and an assignable target that does not TRAVEL BACK ───
                # Same family as above: the prop is written by the client,
                # so its value exists ONLY in the browser. On a
                # ``send_to_server=False`` state it is never posted — the
                # user types, the handler reads the class default, and
                # nothing reports anything. It is the only silent data
                # loss the setting makes possible, and it is decidable
                # here: the binding carries its class's flag (cf.
                # ``ClientBinding.sends_to_server``).
                if isinstance(kw_value, ClientBinding) and not kw_value.sends_to_server:
                    raise ComponentUsageError(
                        f"{cls.__name__}.{kw_name} is a two-way prop — the "
                        f"client writes its value — but "
                        f"{kw_value.class_name} is declared "
                        f"``send_to_server=False``, so that value would "
                        f"never travel back: the handler would read "
                        f"``{kw_value.field_name}``'s class default.\n\n"
                        f"``send_to_server=False`` is meant for DOWNWARD "
                        f"state (the server writes, the client displays). "
                        f"When both directions coexist, split into two "
                        f"states rather than arbitrating — they are two "
                        f"flows, not a compromise. Cf. ``ClientState``'s "
                        f"docstring."
                    )

        # ── Reactive prop storage : split static / binding ──────────────────

        self._reactive_values: dict[str, Any] = {}
        self._binding_metadata: dict[str, ClientBinding] = {}

        for name, value in reactive.items():
            if value is None:
                # ``prop=None`` means "not supplied" — we keep the
                # descriptor's default (filled below). It is EXACTLY what
                # the ``forwarded`` dict / the ``if x is not None`` guard
                # of every ``__init__`` did by hand (in 50+ components).
                # Centralised here: a component can now forward its
                # kwargs directly (``super().__init__(size=size, …)``)
                # without retyping the guard. A ``ClientBinding`` /
                # ``ClientExpression`` is never ``None`` — only the None
                # literal is treated as absent. Guarded by
                # test_none_kwarg_keeps_default.py.
                continue
            if isinstance(value, ClientBinding):
                self._binding_metadata[name] = value
                from bretzel.components.base.binding_discipline import (
                    validate_scalar_binding,
                )

                descriptor = type(self).__reactive_props__.get(name)
                if descriptor is not None:
                    validate_scalar_binding(
                        name,
                        declared_type=descriptor.declared_type,
                        binding=value,
                        owner=type(self).__name__,
                    )
                # Keep the underlying Python value too so the SSR
                # output ships a sensible default before the runtime
                # binds reactively. A ClientExpression, by contrast, has
                # NO server value (it is computed by the runtime from
                # other fields) → ``None``; ``emit_attrs`` skips
                # ``None`` values.
                self._reactive_values[name] = (
                    None if isinstance(value, ClientExpression) else value.value
                )
            else:
                # ⚠️ A ``str`` is DATA, whatever it looks like: code is a
                # ``ClientBinding`` above or a hand-written ``bz-attr:x``.
                # Guessing is a hole: ``ui.avatar(name="0||alert(1)")``
                # would run its script (cf. ``reactive_prop.py``,
                # test_a_string_is_never_code).
                # A Component here was already taken out of its parent, or
                # refused, by the constructor (``adopt_owned_arguments``).
                # Otherwise the dict dies on ``unhashable type: 'dict'``,
                # three frames down. The guard lives in ``responsive``.
                reject_stray_breakpoints(cls.__name__, name, value,
                                         self.RESPONSIVE_PROPS)
                self._reactive_values[name] = value

        # Fill in defaults for any reactive prop the caller didn't pass.
        fill_defaults(self._reactive_values, cls)

        # ── Slots / raw attrs ──────────────────────────────────────────
        #
        # Strings landing in a slot listed in ``ICON_SLOTS`` get wrapped
        # via ``ui.icon(name)`` so callers can write
        # ``ui.button("Save", icon_left="save")``; a Component already
        # flows through unchanged (the constructor took it out of its
        # parent — ``adopt_owned_arguments``). ``adopt_slot`` also wraps a
        # ``ClientBinding`` into a reactive Icon.
        self._slot_components: dict[str, Any] = {}
        for slot_name, slot_value in slots.items():
            self._slot_components[slot_name] = Component.adopt_slot(
                slot_value,
                icon_shortcut=slot_name in cls.ICON_SLOTS,
            )

        self._raw_attrs: dict[str, Any] = dict(raw_html)
        # Merge the explicit ``attrs={...}`` escape hatch into the raw
        # attrs bag — each key/value pair becomes its own HTML attribute.
        # Caller-supplied keys win over anything that landed in
        # ``raw_html`` via the catch-all branch of ``split_kwargs`` so
        # ``attrs={"data-x": ...}`` always reaches the DOM verbatim.
        if explicit_attrs:
            for key, value in explicit_attrs.items():
                self._raw_attrs[normalize_attr_name(str(key))] = value
        self._passthrough_attrs: dict[str, Any] = dict(passthrough)

        # ── Tag override (rarely used) ─────────────────────────────────
        self._tag: str = explicit_tag or cls.DEFAULT_TAG

        # ── ID assignment ──────────────────────────────────────────────

        if explicit_id is not None:
            self.id: str = str(explicit_id)
        else:
            # ⚠️ ``child_scope_id`` and not ``id``: the outlet RENDERS a
            # stable id (htmx sends it back as ``HX-Target``) but GIVES
            # its children a page-qualified id. Cf. ``page_scope``.
            _p = parent_to_name_under(ctx)
            parent_id = "root" if _p is None else (
                getattr(_p, "child_scope_id", None) or _p.id
            )
            kind = cls.THEME_KEY or cls.__name__.lower()
            # If no explicit ``key=`` was passed, fall back to the
            # active iteration key so loops produce stable IDs even
            # when the dev forgot to pass ``key=`` per item.
            effective_key = self._key
            if effective_key is None:
                effective_key = current_iteration_key()
            self.id = ctx.id_generator.next(parent_id, kind, key=effective_key)

        # ── Event handler resolution ───────────────────────────────────
        #
        # Resolved eagerly so :
        # 1. Lambdas / closures fail HERE (clear traceback at the call
        #    site) instead of at first render.
        # 2. ``emit_attrs`` doesn't need a live render context — it
        #    just reads this pre-computed dict.
        # Done after ID assignment so ``register_action`` can pass
        # ``self.id`` through to the registry.
        self._event_attrs: dict[str, str] = {}
        # Hidden HTMX carriers for EXTRA server handlers (overlays only —
        # see ``ALLOW_MULTI_SERVER_EVENTS``). Each entry is the carrier's
        # full attribute dict ; the component renders them via
        # :meth:`_event_carrier_nodes`. Empty for the common single-handler
        # case, so non-overlay components emit byte-identical HTML.
        self._event_carriers: list[dict[str, Any]] = []
        server_event: str | None = None
        # In the class's order, not the call's: an ``on_<event>=[…]`` list
        # is unwrapped above and lands LAST in ``kwargs`` — with
        # ``on_submit=[busy.set(True), send], on_stop=stop`` the stop would
        # ride the message box's form and the submit a carrier, so the box
        # would never see its own request and would keep the text.
        declared = type(self).EVENTS
        for kwarg, handler in sorted(events.items(),
                                     key=lambda item: declared.index(item[0][3:])):
            event = kwarg[3:]  # strip ``on_``
            if handler is None:
                continue
            if isinstance(handler, str):
                # Client-only JS expression — V3 runtime evaluates it.
                self._event_attrs[client_event_attr(event)] = handler
                continue
            # Server handler — native hx-post + HMAC stamp (V3 wire).
            # A root element hosts ONE hx-post, so the first server event
            # rides the root and any extra is relocated onto a hidden
            # carrier (only when the component opted into multi-handlers).
            if server_event is not None and not type(self).ALLOW_MULTI_SERVER_EVENTS:
                raise HandlerError(
                    f"{type(self).__name__} got server handlers for both "
                    f"'{server_event}' and '{event}' — an element carries "
                    "ONE hx-post. Route the second event onto a child "
                    "element or handle it client-side (string expression)."
                )
            action_id, args_blob, sig = ctx.register_action(handler, self.id, event, own_field(self))
            if server_event is None:
                # First server handler → on the root element itself.
                server_event = event
                self._event_attrs.update(
                    action_attrs(event, action_id, args_blob, sig, modifier=self._trigger_modifier)
                )
            else:
                # Extra server handler → a hidden carrier (``carrier_attrs``).
                self._event_carriers.append(carrier_attrs(
                    event, action_id, args_blob, sig, root_id=self.id,
                    dom_event=type(self).DOM_EVENTS.get(event),
                    modifier=self._trigger_modifier,
                ))

        # ── Tree registration ──────────────────────────────────────────
        #
        # Default mode (no render in progress) : auto-attach to the
        # current ``with`` parent, or to the request's root children
        # if no ``with`` is open. This is what builds the tree as the
        # page handler runs top-to-bottom.
        #
        # Render mode (set by :meth:`_render_children`) : we're walking
        # the already-built tree to emit HTML. Components constructed
        # at this point come from ``render=`` cell callbacks, custom
        # render() methods, etc. Two sub-cases :
        #
        # - No ``with`` block currently open at this scope → drop
        #   registration. The caller will return the component from
        #   the callback, the wrapping primitive (e.g. ``Table``)
        #   adopts it directly.
        # - A ``with`` block IS open at this scope (e.g. ``with
        #   ui.tooltip(name): ui.avatar(...)`` inside a cell render
        #   callback) → attach to that ``with`` parent so children
        #   compose into a tree instead of being silently dropped.
        in_render = bool(getattr(ctx, "is_rendering", False))
        self._is_subcomponent: bool = in_render and not ctx.parent_stack
        if self._is_subcomponent and (built := _BUILT_IN_CALLBACK.get()) is not None:
            built.append(type(self).__name__)  # cf. ``call_render``
        if not self._is_subcomponent and not statically_hidden(self):
            if ctx.parent_stack:
                ctx.parent_stack[-1].add_child(self)
            else:
                ctx.root_children.append(self)

        # Children container — leaves stay empty forever.
        # ``IS_CONTAINER`` is read by ``__enter__`` / ``add_child`` to
        # refuse a ``with`` block on a leaf.
        self._children: list[Any] = []

    # ── Context-manager protocol (with-block children) ──────────────────

    def __enter__(self) -> Component:
        if not type(self).IS_CONTAINER:
            raise ComponentUsageError(
                f"{type(self).__name__} is a leaf component and doesn't "
                "support `with` blocks. Drop the `with` and call it directly."
            )
        ctx = current_context()
        ctx.parent_stack.append(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ctx = current_context()
        if ctx.parent_stack and ctx.parent_stack[-1] is self:
            ctx.parent_stack.pop()

    @staticmethod
    def adopt_slot(
        value: Any, *, icon_shortcut: bool = False, icon_size: str | None = None,
    ) -> Any:
        """Normalise a slot value before storing it on a component.

        A Component passed to a parameter that renders it is already out
        of its parent (the constructor does it, cf.
        ``base/arguments.adopt_owned_arguments``), so a plain slot needs no
        call at all. This one is for the two cases the constructor cannot
        see :

        - ``icon_shortcut=True`` and a string: wrap it in
          ``ui.icon(value)`` so callers can write ``icon_left="search"``
          — an Icon built HERE, which registered with the open parent;
        - a Component the component builds ITSELF (the ``Tooltip`` of a
          ``tooltip=``): nobody passed it, so nothing detached it.

        Either way the Component is detached from whatever parent it
        auto-registered into — the slot is the new owner.

        Returns ``None`` for ``None``, the converted/detached value
        otherwise. Strings without ``icon_shortcut`` flow through
        unchanged (e.g. plain prefix text).

        ``icon_size`` sizes the Icon the shortcut BUILDS — a name or a
        binding —, so a component whose ``sizes`` table carries an
        ``icon_size`` per step (Badge, EmptyState, Input) passes it here
        instead of building the Icon itself. An Icon the caller built is
        left alone: its size is an explicit choice.
        """
        sized = {"size": icon_size} if icon_size else {}
        if value is None:
            return None
        if isinstance(value, str) and icon_shortcut:
            from bretzel.components.primitives.icon import Icon

            value = Icon(value, **sized)
        if icon_shortcut and isinstance(value, ClientBinding):
            # Reactive icon : let Icon own the binding → :icon plumbing
            # (cf. primitives/icon/icon.py Task 7). Without this, the
            # raw ClientBinding flows through and crashes the
            # downstream .render() call. Inline import : primitives.icon
            # imports Component via base, so a top-level import here
            # would be a circular dep. ``Icon`` accepts a binding via
            # the reactive_prop machinery — the typed ``name: str | None``
            # signature is the static surface ; cast-via-Any silences
            # the diagnostic without changing runtime behaviour.
            from bretzel.components.primitives.icon import Icon

            value = Icon(typing.cast(Any, value), **sized)
        if isinstance(value, Component):
            Component._detach_from_parent(value)
        return value

    @staticmethod
    def _detach_from_parent(child: Component) -> None:
        """Remove ``child`` from whatever list it auto-registered into.

        Components register themselves with the active parent (or
        ``ctx.root_children``) in their own ``__init__`` — they have
        no other signal of who owns them. When the consumer then
        adopts the component as a SLOT (``icon=`` / ``prefix=`` /
        …), the side-effect registration becomes a duplicate : the
        component would render once standalone in the parent's flow
        AND once inside the consumer's slot. This helper undoes the
        registration so the slot is the only owner.
        """
        from bretzel.render.context import maybe_current_context

        ctx = maybe_current_context()
        if ctx is None:
            return
        for parent in ctx.parent_stack:
            if child in parent._children:
                parent._children.remove(child)
                return
        if child in ctx.root_children:
            ctx.root_children.remove(child)

    @staticmethod
    def render_detached(child: Component) -> Any:
        """Detach *child* from its auto-registered parent, then render it.

        The one place that pairs the two halves. A Component built
        **inside** ``render()`` (a themed ``Icon`` for a × button, a
        chevron glyph, …) auto-registers with the active parent just like
        any other — so when the owning component is itself detached
        (``serialize_html``, an inspection snapshot, any extracted
        subtree), that inner child has no immediate parent and leaks onto
        ``root_children``, rendering a second time as an orphan. Calling
        ``child.render()`` without :meth:`_detach_from_parent` first is
        the bug ; this helper makes forgetting impossible. Gated by
        ``tests/consistency/test_render_never_orphans.py``.
        """
        Component._detach_from_parent(child)
        return child.render()

    _zone: Any = None  # its ``@refreshable`` render — ``base/``

    def add_child(self, child: Any) -> None:
        if not type(self).IS_CONTAINER:
            raise ComponentUsageError(f"{type(self).__name__} is a leaf, can't add children.")
        self._children.append(child)
        if isinstance(child, Component):
            child._zone = zone_of_children(self)

    # ── Rendering helpers ──────────────────────────────────────────────


    def emit_attrs(self) -> dict[str, Any]:
        """Build the HTML attribute dict for this component's root.

        Framework attrs (``id`` / ``bz-id``) are emitted **conditionally** —
        only when the component carries something the
        runtime actually needs to track: a reactive binding, a client
        expression, an event handler, or a raw ``bz-*`` directive the
        user wired by hand. Pure static nodes (``ui.text("Hello")`` with
        no props) stay anonymous. The rule keeps the DOM clean for the
        nodes that don't need identity.
        """
        attrs: dict[str, Any] = {}

        descriptors = type(self).__reactive_props__

        for name, value in self._reactive_values.items():
            descriptor = descriptors.get(name)
            cosmetic = descriptor is not None and not getattr(descriptor, "emit_attr", True)

            # ⚠️ The exit PRECEDES ``normalize_attr_name``, and that is
            # the point: a cosmetic prop never reaches the DOM through
            # this loop, neither by its binding nor by its literal.
            # Normalising first would throw the result away for most of a
            # page's reactive props.
            if cosmetic:
                continue

            attr_name = normalize_attr_name(name)

            # 1. ClientBinding — emit ``bz-attr:<attr>="<expression>"``
            #    (V3 one-way reactive attribute bind). The expression is
            #    the full ``$bz.state.<path>`` form — the V3 evaluator
            #    takes plain JS, no implicit prefixing.
            if name in self._binding_metadata:
                if cosmetic:  # bound AND cosmetic: nothing is emitted
                    continue
                attrs[f"{BZ_ATTR_PREFIX}{attr_name}"] = self.path_of(
                    self._binding_metadata[name]
                )
                # Fall through to the literal-value path below so the SSR
                # HTML carries the binding's resolved value as a static
                # attr (``checked``, ``value="x"``, …). Without this, the
                # browser paints the element's *default* state (unchecked /
                # empty) before the runtime boots and applies the binding —
                # visible flash. ``_reactive_values[name]`` holds
                # ``binding.value``, so the loop's ``value`` variable
                # carries the right SSR snapshot.

            # 2. Static literal. The ``cosmetic`` guard that lived here
            #    has become UNREACHABLE (exit at the head of the loop,
            #    except for a client expression, which ``continue`` in
            #    branch 2) — and a dead guard reads as a protection.
            if value is None or value is False:
                continue
            if value is True:
                attrs[attr_name] = True
                continue
            # _BoundBool from ServerState._stamp: an int subclass
            # that carries field_name for autoname but doesn't pass
            # the identity checks above (it's not the True/False
            # singleton). Treat it as a boolean HTML attribute.
            if getattr(value, "_is_bound_bool", False):
                if value:
                    attrs[attr_name] = True
                continue
            attrs[attr_name] = value

        # Event handlers — resolved at __init__ time so we don't need
        # the render context here.
        attrs.update(self._event_attrs)

        # ── Framework identity attrs — only when something needs them ──
        # Two distinct triggers :
        # - ``_needs_identity()`` : the runtime / HTMX needs to find
        #   the element again (binding, expression, event, raw ``bz-*``
        #   directive). Emits ``id`` + ``bz-id`` — ``bz-id`` is
        #   load-bearing : it keys the bz-data scope store so component
        #   state survives idiomorph swaps. The scope Map makes
        #   morph-guards unnecessary.
        # - ``_user_provided_id`` : the caller wired ``id=`` explicitly.
        #   We honour the intent and emit just the ``id`` attribute,
        #   without the framework's ``bz-*`` overhead.
        needs_identity = self._needs_identity()
        if needs_identity:
            attrs["id"] = self.id
            attrs[BZ_ID_ATTR] = self.id
        elif self._user_provided_id:
            attrs["id"] = self.id

        # ── Raw attrs, set per THE precedence contract ─────────────────
        # ``merge_attr`` and not ``attrs.update``: the update overwrote,
        # so an ``attrs={"class": …}`` erased what was already there and
        # an ``attrs={"id": …}`` beat the named ``id=`` kwarg. Cf.
        # ``merge_attr`` for the table of the four diverging resolutions
        # that produced.
        for _name, _value in self._raw_attrs.items():
            # ``id`` is the only case where the NAMED kwarg wins over
            # ``attrs=``: the explicit API beats the raw escape hatch.
            # For everything else ``attrs=`` stays the last word, that is
            # its reason to exist.
            if _name == "id" and self._user_provided_id:
                continue
            # ``class`` does NOT go through here: a component that
            # rebuilds its ``class=`` in ``render()``
            # (``attrs["class"] = …``) would overwrite it. It is set
            # post-render by the metaclass wrap, in the same place as
            # ``slots={"root"}`` and ``classes=``. Cf. ``_raw_class_str``.
            if _name == "class":
                continue
            merge_attr(attrs, _name, _value)

        # Raw pass-through / HTMX attrs (kept verbatim — no rename).
        for _name, _value in self._passthrough_attrs.items():
            merge_attr(attrs, _name, _value)

        # ── Autoname ─────────────────────────────────────────────────
        # When a form-bound prop carries a ClientBinding AND the user
        # hasn't passed an explicit ``name=``, derive the HTML ``name``
        # from the binding's field name. Lets app code stay clean :
        #
        #   ui.input(value=state.email)
        #   # → name="email" auto-derived ; form data carries
        #   # ``email=<value>`` ; signature-injection finds
        #   # ``def handler(email)`` automatically.
        #
        # Opt-in per component via ``AUTONAME_FROM`` (the reactive prop
        # whose binding drives the name — typically ``"value"`` for
        # text-like inputs, ``"checked"`` for checkbox / switch).
        autoname_prop = type(self).AUTONAME_FROM
        if autoname_prop and "name" not in attrs:
            # Same two-source derivation the carrier components use — shared
            # via ``_derive_field_name``. Here the root IS the form control,
            # so the name lands on the root attrs directly.
            field_name = self._derive_field_name()
            if field_name:
                attrs["name"] = field_name

        # What the tag cannot carry (``type`` on an ``<a>``…). Deferred
        # import — ``component`` depends on ``_wiring``.
        from bretzel.components.base.composition import drop_tag_bound_attrs

        drop_tag_bound_attrs(self._tag, attrs, spare=self._author_written_attrs())

        return attrs

    def _author_written_attrs(self) -> set[str]:
        """The attribute names the CALLER wrote themselves."""
        return self._raw_attrs.keys() | self._passthrough_attrs.keys()


    # ── Class composition helper ────────────────────────────────────────


    def emit_text_slot(
        self,
        value: Any,
    ) -> Node | None:
        """Render a textual slot — literal string, binding, or absent.

        Returns:

        - ``None`` when the slot is empty (``None`` or ``""``). The
          caller skips appending it to the children list and the slot
          contributes no markup.
        - A :class:`TextNode` node when the slot carries a literal string —
          identical to the pre-Phase-3 behaviour, no wrapper.
        - A ``<span bz-text="$bz.state.X.Y"></span>`` :class:`Element`
          when the slot carries a :class:`ClientBinding`. the runtime
          substitutes the live value on every signal mutation, no
          server round-trip.

        Why a wrapper ``<span>`` for the reactive form rather than
        mutating the text node directly: the runtime's ``bz-text`` directive
        binds against elements, not raw DOM text nodes (browser API
        limitation). The wrap is ``display: inline`` by default so it
        doesn't shift layout. V1 used the same trick.

        The TWO legitimate ways of handling the ``None``
        ------------------------------------------------
        ``serialize`` **raises** on a ``None`` in ``children`` ("Cannot
        serialize unknown Node type: NoneType"), so every caller must
        deal with it. There are two strategies, and they are not
        interchangeable:

        1. **keep the RESULT** — ``node = emit_text_slot(v)`` then
           ``if node is not None:``. This can **guard the construction
           of a wrapper** (`<h3>`, `<div class="title">`,
           `<span class="label">`…) and not merely the append: without
           the guard, the component would emit an EMPTY wrapper, that is
           to say a visible hole in a ``flex gap-*`` row;
        2. **keep the VALUE upstream** — ``if v:`` before even building
           the wrapper, the call then never happening on an empty slot.

        Three legitimate variants complete the picture: the mandatory
        wrapper whose CONTENT alone is optional (``date_range_picker``:
        the ``<span>`` separates two fields and must exist),
        ``tooltip``'s ``or TextNode("")`` (the panel always exists), and
        ``link``'s prefix.

        ⚠️ **The trap**: keeping the raw value with ``is not None``.
        ``""`` passes it, the wrapper is built, the call returns ``None``
        and ``serialize`` raises. The safe form on the raw value is the
        truth test (``if v:``); ``is not None`` only holds on the RESULT.

        The class is guarded by
        ``tests/consistency/test_text_slot_contract_universal.py``, whose
        population is DERIVED: it replays every textual parameter of the
        catalogue with ``""``, so a new site that forgets its guard turns
        red with nothing to register anywhere.

        **Why the ``None`` is not filtered in ``Element``**: a filter in
        ``Element.__post_init__`` would make only some guards redundant,
        and would silently break the others, since they guard the
        wrapper, not the append.
        """
        # ``path_of`` covers both subtypes: a ClientExpression already
        # carries the ``$bz.state.`` prefix in its expression, a
        # ClientBinding carries only a short path. Re-prefixing it by
        # hand produces ``$bz.state.($bz.state.…``.
        if isinstance(value, ClientBinding):
            return Element(
                tag="span",
                attrs={"bz-text": Component.path_of(value)},
                children=(),
            )
        # Component as a text slot — render in place. Universal contract
        # says every slot accepts ``str | ClientBinding | Component``.
        # Without this branch the value falls through to ``str(value)``
        # below and ships the Python ``__repr__`` ("<bretzel...object
        # at 0x…>") to the browser. The constructor took the component
        # out of its auto-attached parent (``adopt_owned_arguments``) ;
        # otherwise it would render twice — standalone in the parent
        # and again here.
        if isinstance(value, Component):
            return value.render()
        # Empty / absent slot ; the caller skips the append. Order
        # matters : the equality check below would invoke
        # ``ClientBinding.__eq__`` (which returns a ClientExpression
        # whose ``__bool__`` raises ReactivityError) — so the binding
        # branches above MUST run first.
        if value is None or value == "":
            return None
        return TextNode(str(value))


    def _needs_identity(self) -> bool:
        """Should this component carry ``id`` / ``bz-id``?

        Mirrors the v1 rule (``V1/bretzel/ui/core/component.py:176``):
        emit identity only when the runtime or HTMX actually
        needs to find this element again. Static nodes stay anonymous.

        Triggers:
        - any reactive prop carries a :class:`ClientBinding` (the
          runtime has to patch the resolved attribute on this element
          when the bound state changes),
        - any reactive prop is a client expression string (the runtime
          rebinds ``bz-attr:`` directives by element identity),
        - any DOM event handler is wired (the dispatcher sends the
          source element; identity is harmless but useful for tooling),
        - the user attached raw ``bz-*`` directives (caller knows
          what they're doing),
        - **the component exposes the imperative API** (``IMPERATIVE``
          non-empty): ``.open()`` / ``.set()`` / … target by
          ``getElementById(self.id)`` — with no rendered id the dispatch
          finds ``null`` and fails **silently** (cf. traps.md §
          "Une API impérative exige une identité"). That behaviour is derived from
          ``IMPERATIVE`` and guarded by
          ``test_imperative_component_needs_identity``.

        ``fuse_or_wrap`` adds the ``bz-id`` of a refreshable section
        on its OWN wrapper; nodes nested inside don't need their own.
        """
        if type(self).IMPERATIVE:
            return True
        if self._binding_metadata:
            return True
        if self._event_attrs:
            return True
        for raw_name in self._passthrough_attrs:
            if raw_name.startswith(("bz-", "x-", "@", ":")):
                return True
        return False

    # ── Default render ─────────────────────────────────────────────────

    def render(self) -> Node:
        """Default render : single :class:`Element` carrying framework
        attrs + the user-supplied ``classes`` string.

        Subclasses override this and own their theme composition via
        their own ``_compose_classes`` helper ; the default exists so
        a bare ``Component`` instance is still useful for tests.
        """
        children_nodes = self._render_children()
        attrs = self.emit_attrs()
        if self._classes:
            attrs = {**attrs, "class": str(self._classes)}
        return Element(tag=self._tag, attrs=attrs, children=children_nodes)

    # ── Render-time iteration over children ────────────────────────────

    def _render_children(self) -> tuple[Node, ...]:
        """Walk ``self._children`` and produce the corresponding Node tuple.

        Components recursively call ``.render()`` ; raw :class:`Node`
        instances pass through ; bare strings get auto-wrapped in
        :class:`TextNode` for safety. Anything else raises so we don't
        silently emit garbage.

        The ``is_rendering`` flag is set on the active render context
        for the duration of this walk so sub-components constructed
        inside a parent's ``render()`` skip parent-stack registration.
        We restore the previous value on the way out — without this,
        a second render in the same request would see the flag stuck
        on True from the first one and treat its top-level components
        as sub-components.
        """
        ctx = maybe_current_context()
        previous = ctx.is_rendering if ctx is not None else None
        if ctx is not None:
            ctx.is_rendering = True
        try:
            out: list[Node] = []
            for child in self._children:
                node = self._render_one(child)
                if node is not None:
                    out.append(node)
            return tuple(out)
        finally:
            if ctx is not None:
                ctx.is_rendering = bool(previous)

    def _event_carrier_nodes(self) -> list[Node]:
        """Hidden HTMX carrier elements for EXTRA server-handled events.

        A root element hosts a single ``hx-post`` ; when a component opts
        into :data:`ALLOW_MULTI_SERVER_EVENTS` and takes more than one
        server ``on_<event>`` handler, every extra handler is relocated
        here. Each carrier is an empty, ``hidden`` ``<div>`` whose
        ``hx-trigger="<event> from:#<root>"`` makes HTMX listen for the
        event on the overlay ROOT (where ``$dispatch`` fires it) and POST
        to that handler's own action route — full HMAC, no shared state.

        Returns an empty list for the common single-handler case, so a
        component that always appends ``*self._event_carrier_nodes()``
        emits byte-identical HTML when no second handler is wired.
        """
        return [
            Element(tag="span", attrs=dict(carrier), children=())
            for carrier in self._event_carriers
        ]

    @staticmethod
    def _render_one(child: Any) -> Node | None:
        if child is None:
            return None
        if isinstance(child, Component):
            return child.render()
        if isinstance(child, Node):
            return child
        if isinstance(child, str):
            return TextNode(child)
        raise ComponentUsageError(
            f"Unsupported child type {type(child).__name__} — "
            "components accept Component / Node / str instances."
        )


# ───────────────────────────────────────────────────────────────────────────
# Universal modifiers — applied to every component's render() via the
# ``_ComponentMeta`` wrap. Two kwargs are recognised here:
#
#   visible=False                  → ``FragmentNode(())`` (skip render entirely)
#   visible=True / None            → no-op (default)
#   visible=ClientBinding          → ``bz-show="$bz.state.<path>"`` +
#                                     prestamped ``display:none`` (V3 has
#                                     no ``x-cloak`` any more) on the root;
#                                     SSR fallback
#                                     honours the binding's current value.
#
#   tooltip=str                    → wrap the rendered node in a Tooltip
#   tooltip=ClientBinding          → wrap, panel text is bz-text reactive
#   tooltip=None / ""              → no-op
#
# The wrap is idempotent (a marker on the wrapped function prevents
# double-wrap when a subclass inherits a render that was already wrapped
# at a parent class). Subclasses that don't override ``render()`` just
# inherit the wrapped version from their parent; subclasses that DO
# override get their own wrap on top.
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# Convenience re-exports
# ───────────────────────────────────────────────────────────────────────────



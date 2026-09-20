"""``Component`` — the single base class apps and component authors subclass.

The class is intentionally **flat** (no Element → InteractiveElement →
BaseComponent inheritance chain from v1) ; behaviour is composed
through the ``base/*`` helper modules instead. Subclasses set a few
class-level constants, declare reactive props, and override
:py:meth:`render`.

"""

from __future__ import annotations

import re
import typing
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar, Final

from bretzel.components.base.attrs import (
    EVENT_PATTERN,
    ComponentDefinitionError,
    ComponentUsageError,
    normalize_attr_name,
    reject_dead_alpine_attr,
    split_kwargs,
)
from bretzel.components.base.events import (
    HandlerError,
    action_attrs,
    client_event_attr,
    cross_check_events,
)
from bretzel.components.base.reactive_prop import (
    MISSING,
    ReactivePropDescriptor,
    reads_as_client_expr,
)
from bretzel.components.base.responsive import reject_stray_breakpoints
from bretzel.core.tree import Element, FragmentNode, Node, TextNode
from bretzel.render.context import current_context, maybe_current_context
from bretzel.render.iteration import current_iteration_key
from bretzel.runtime.protocol import (
    BZ_ATTR_PREFIX,
    BZ_CLASS_PREFIX,
    BZ_ID_ATTR,
    BZ_MODEL_PREFIX,
    BZ_SHOW_PREFIX,
)
from bretzel.state.scopes.client import ClientBinding, ClientExpression, _to_js

#: The kwargs EVERY component accepts, removed by
#: :meth:`Component.__init__` **before** ``split_kwargs`` — they are
#: never in a signature (the "no universal kwargs in an API signature"
#: rule).
#:
#: This list existed in **five** copies until 2026-08-16: the
#: ``kwargs.pop`` below, ``split_kwargs``'s prose, two gates in
#: ``tests/consistency/`` and ``bretzel.introspect``. Two had already
#: drifted — one had lost ``key``, the other had added ``slots`` a year
#: too late, after making correct code turn red. This is the source, and
#: ``test_reserved_kwargs_match_the_socle`` checks by AST that it matches
#: the real ``pop``: the ``pop`` stay heterogeneous (each does a
#: different job with its value), so one cannot loop over them — but one
#: can refuse that they diverge from a declaration.
RESERVED_KWARGS: Final[tuple[str, ...]] = (
    "classes",
    "style",
    "slots",
    "key",
    "id",
    "tag",
    "attrs",
    "visible",
    "tooltip",
    "debounce",
    "throttle",
    "outlet",
)

# ───────────────────────────────────────────────────────────────────────────
# Metaclass
# ───────────────────────────────────────────────────────────────────────────


class _ComponentMeta(type):
    """Collect reactive props + cross-check events at class creation.

    The work is small but absolutely needs to run *once per class*,
    not on every instance — hence a metaclass rather than __init_subclass__
    (which would also work but reads less obviously when paired with
    introspection).
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> type:
        cls = super().__new__(mcs, name, bases, namespace)

        # Walk the MRO so subclasses inherit parent props.
        collected: dict[str, ReactivePropDescriptor] = {}
        for base in reversed(cls.__mro__):
            for attr_name, attr in base.__dict__.items():
                if isinstance(attr, ReactivePropDescriptor):
                    collected[attr_name] = attr
        cls.__reactive_props__ = collected  # type: ignore[attr-defined]

        # Walk MRO annotations the same way the prop collection does
        # so subclass overrides win. Each descriptor learns its declared
        # type so future discipline checks (binding_discipline.py) can
        # validate scalar-vs-collection mismatches at __init__ time.
        # ``from __future__ import annotations`` (PEP 563) and PEP 649
        # both make annotations show up as strings on the class — resolve
        # them through ``typing.get_type_hints`` so descriptors carry the
        # actual ``type`` objects (cf. ``state/base.py`` for precedent).
        try:
            annotations: dict[str, Any] = typing.get_type_hints(cls)
        except (NameError, TypeError):
            annotations = {}
            for base in reversed(cls.__mro__):
                annotations.update(getattr(base, "__annotations__", {}) or {})
        for prop_name, descriptor in collected.items():
            ann = annotations.get(prop_name)
            if ann is not None:
                descriptor.declared_type = ann

        # ── Derived TWO_WAY_PROPS + the scope-key map ─────────────────
        # "What the client does with this prop" lives ON the prop
        # (``reactive_prop(writes=, scope_keys=)``), not in a ClassVar to
        # keep in phase. The metaclass derives from it:
        #   - ``TWO_WAY_PROPS`` = the ``writes=True`` props (when at least
        #     one exists; otherwise an explicit ClassVar is respected —
        #     coexistence for the duration of the migration);
        #   - ``__scope_keys__`` = prop → scope keys (default ``(prop,)``,
        #     overridden when the key differs from the name: Tabs value→active).
        writes_props = tuple(n for n, d in collected.items() if getattr(d, "writes", False))
        # UNCONDITIONAL assignment. There used to be an
        # ``if writes_props:`` here — the coexistence scaffolding during
        # the migration, which let a hand-written ClassVar survive beside
        # the derivation. Two ways of declaring the same fact is the
        # charter's principle 4 going away. The migration being over, the
        # branch disappears and a manual declaration raises (below).
        cls.TWO_WAY_PROPS = writes_props  # type: ignore[attr-defined]

        # A hand declaration of either derived ClassVar can no longer
        # coexist with the derivation: it is refused at CLASS CREATION,
        # so at import, with the replacement named.
        for _derived, _param in (
            ("TWO_WAY_PROPS", "writes=True"),
            ("AUTONAME_FROM", "names_field=True"),
        ):
            if name != "Component" and _derived in namespace:
                raise ComponentDefinitionError(
                    f"{name} declares ``{_derived}`` by hand. That "
                    f"ClassVar is DERIVED from the props: set ``{_param}`` "
                    f"on the prop concerned (``reactive_prop(...)``) and "
                    f"remove the line. Two places for one fact is the "
                    f"drift the derivation exists to prevent."
                )
        cls.__scope_keys__ = {  # type: ignore[attr-defined]
            n: (d.scope_keys or (n,)) for n, d in collected.items() if getattr(d, "writes", False)
        }

        # ── Derived AUTONAME_FROM ──────────────────────────────────────
        # The third fact to leave the ClassVar for the prop, same pattern
        # as ``writes=`` / ``scope_keys=``. The ClassVar REMAINS the
        # reading surface (``type(self).AUTONAME_FROM``) — only the
        # declaration moves, so no reader and no test has to change.
        naming = tuple(n for n, d in collected.items() if getattr(d, "names_field", False))
        if len(naming) > 1:
            raise ComponentDefinitionError(
                f"{name} : {len(naming)} props portent ``names_field=True`` "
                f"({naming}). A component has only ONE HTML ``name=`` — "
                f"only one prop can name it."
            )
        if naming:
            prop = naming[0]
            # ``names_field`` implies ``writes``: a field whose value
            # the client does not write has no ``name=`` to derive. It is
            # the AUTONAME ⊆ TWO_WAY inclusion the ``test_two_way_props``
            # gate imposed after the fact; here it becomes impossible to
            # violate.
            if not getattr(collected[prop], "writes", False):
                raise ComponentDefinitionError(
                    f"{name}.{prop} carries ``names_field=True`` without "
                    f"``writes=True``. A form field whose value the client "
                    f"does not write has no ``name=`` to derive — add "
                    f"``writes=True``."
                )
            declared = namespace.get("AUTONAME_FROM")
            if declared is not None and declared != prop:
                raise ComponentDefinitionError(
                    f"{name} declares ``AUTONAME_FROM = {declared!r}`` "
                    f"while ``{prop}`` carries ``names_field=True``. The "
                    f"two tell two stories — remove the ClassVar, the "
                    f"declaration lives on the prop."
                )
            cls.AUTONAME_FROM = prop  # type: ignore[attr-defined]

        # Cross-check declared EVENTS vs ``on_<event>`` parameters in
        # ``__init__``. Skip the abstract base itself (it has no
        # EVENTS and a permissive ``**kwargs`` ctor).
        if name != "Component":
            cross_check_events(cls)

        # Wrap ``render()`` so the universal ``visible`` / ``tooltip``
        # modifiers are applied to every component automatically. The
        # wrap is idempotent : if a subclass inherits an already-wrapped
        # render, the marker stops a second wrap. The base Component's
        # own ``render`` skips the wrap (nothing to apply — universals
        # only kick in when set on an instance, and the base is
        # abstract anyway).
        original_render = namespace.get("render")
        if (
            original_render is not None
            and name != "Component"
            and not getattr(original_render, "_bz_universals_wrapped", False)
        ):

            def wrapped_render(self, _orig=original_render):
                return finish_render(self, _orig(self))

            wrapped_render._bz_universals_wrapped = True  # type: ignore[attr-defined]
            cls.render = wrapped_render  # type: ignore[assignment]

        return cls


# ───────────────────────────────────────────────────────────────────────────
# Component
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# THE attribute precedence — one contract, written once
# ───────────────────────────────────────────────────────────────────────────

# Attributes whose several sources COMPOSE instead of overwriting. They
# have list semantics: two classes is both classes; two style
# declarations is both.
_COMPOSABLE_ATTRS: Final[dict[str, str]] = {"class": " ", "style": "; "}


def merge_attr(attrs: dict[str, Any], name: str, value: Any) -> None:
    """Set ``value`` on ``attrs[name]`` **per the precedence contract**.

    The contract, in one sentence: *nothing the user writes disappears
    silently*.

    - ``class`` / ``style`` **compose** — each source is added to the
      previous one, in application order (theme, then raw attrs, then the
      universal layer, which therefore comes last and wins a Tailwind
      conflict).
    - everything else **overwrites** — an element has only one ``id``,
      one ``role``, one ``name``.

    Why it exists (base layer audit, item 6). There were **four**
    different resolutions for the same collision, a product of the order
    of the ``attrs.update`` and never stated as a contract. Measured
    before the fix, on a
    ``ui.card(id=…, classes=…, class_=…, attrs={…}, style=…)``:

    ===========================  ====================================
    collision                    result
    ===========================  ====================================
    ``id=`` + ``attrs["id"]``    ``attrs`` won, the named kwarg
                                 disappeared
    ``classes=`` + ``attrs``     one of the two disappeared
    ``classes=`` + ``class_=``   ``class_`` disappeared
    ``style=`` + ``attrs``       both survived (the only correct case)
    ===========================  ====================================

    Three user inputs lost, without a word. ``kwarg-routing.md``
    documented each bucket's *storage*, never the *application order*.
    """
    if value is None:
        return
    sep = _COMPOSABLE_ATTRS.get(name)
    existing = attrs.get(name)
    if sep is None or not existing or not isinstance(existing, str) or not isinstance(value, str):
        attrs[name] = value
        return
    # Composable AND both sides are strings: we concatenate, without
    # duplicating a value already present (a component recomposing its
    # slot must not make ``class=`` swell).
    if value in existing.split(sep.strip() or None):
        return
    attrs[name] = f"{existing}{sep}{value}"


class Component(metaclass=_ComponentMeta):
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
    #:   files what one did not want to decide. Added on 2026-08-31:
    #:   ``tracks=`` is the catalogue's first case none of the other
    #:   three described without lying.
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
    # Measured on 2026-08-08: a graded ``ui.flex(direction=…)`` did not
    # change axis in compiled mode, and the carousel's dots stayed
    # visible where ``per_view`` goes up.
    #
    # Same mechanics as the colour templates, same bridge: it is
    # ``components`` that declares and ``theme`` that closes (cf.
    # ``components/color_shapes.py`` and the import-linter contract).
    # The values that do NOT come from a theme table but from an f-string
    # over a scalar (``grid-cols-N``, ``basis-1/N``) stay in
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

    # A root element hosts a SINGLE ``hx-post`` (one server handler).
    # When ``True`` the component may take MORE than one server-side
    # ``on_<event>`` handler : the first rides the root as usual, each
    # extra is relocated onto a hidden HTMX carrier element that listens
    # for its event FROM the root (``hx-trigger="<event> from:#<root>"``).
    # The component is then responsible for rendering those carriers via
    # :meth:`_event_carrier_nodes`. Opted in by the overlays (Dialog /
    # Drawer / Popover / Dropdown), whose ``open`` + ``close`` both fire
    # on the same root, so a single overlay can wire ``on_open`` AND
    # ``on_close`` to the server. Default ``False`` keeps the strict
    # one-handler rule (a stray second handler is a usage error) for
    # every other component, where two server handlers makes no sense.
    ALLOW_MULTI_SERVER_EVENTS: ClassVar[bool] = False

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
    # write". Borrowing one for the other is precisely what coupled
    # server-sync to form naming (cf. todo.md § A3).
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

    # Declarative mapping ``{prop: bz-ref of carrier element}`` that
    # tells the base where each bindable prop's HTML attribute
    # actually does something. The metaclass-installed render wrap
    # walks the rendered tree and forwards ``bz-attr:<prop>`` from
    # the root onto the element carrying ``bz-ref="<value>"``.
    #
    # Use case (the "wrapper-vs-carrier" trap, cf. ``traps.md``) —
    # FileUpload, **the repository's only declarer**:
    # ``{"disabled": "nativeInput"}`` → the directive lands on the inner
    # ``<input type="file">``, where ``disabled`` really disables the
    # picker, and not on the wrapper ``<div>`` where it would be a no-op.
    #
    # Declaring this map AND adding ``bz-ref="<value>"`` to the carrier
    # element in ``render()`` is enough — no manual ``forward_binding``
    # call needed. The base handles it post-render.
    #
    # When the carrier element isn't found (selector typo / dropped
    # render branch), the base leaves the root's auto-emitted
    # directive in place as fallback and the carrier-landing audit
    # surfaces the mismatch.
    #
    # ── Choosing the mechanism for moving a binding ────────────────────
    #
    # Three mechanisms bring a binding onto an element other than the
    # root. The choice rule is centralised here.
    #
    #   1. ``BINDABLE_CARRIERS``  — declarative, 1 prop → 1 carrier.
    #      When: the carrier is UNIQUE, its ``bz-ref`` is free, and the
    #      attribute keeps its name. The base layer does the rest
    #      post-render.
    #
    #   2. ``forward_binding``    — imperative, called in ``render()``.
    #      When: 1 prop → **N** carriers, or the attribute must be
    #      RENAMED (``disabled`` on a ``<button>`` but ``aria-disabled``
    #      on a ``<div>``, which ignores ``disabled``), or the forward is
    #      CONDITIONAL.
    #
    #   3. ``release_root_attr``  — remove without setting elsewhere.
    #
    # These are NOT three competing routes for one job, and that is what
    # the measurement showed: ``date_picker`` calls
    # ``forward_binding("disabled", …)`` **three times** — visible field,
    # clear button, trigger. A ``1 prop → 1 ref`` map structurally cannot
    # express that.
    #
    # The base layer's audit suggested removing (1): "107 lines of base
    # layer for 1 declarer". The ratio is real, the conclusion is not —
    # low adoption is not an adoption failure, it is the size of the
    # eligible population. Only one component in the repository today has
    # a unique carrier with a preserved name. Removing (1) would also
    # lose its post-render net: the base layer reports that a DECLARED
    # carrier cannot be found, which an imperative call cannot signal.
    BINDABLE_CARRIERS: ClassVar[Mapping[str, str] | None] = None

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
            from bretzel.components.base._wiring import outlet_target_attrs

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
        # avoids running the regex over each instance's ~5 kwargs — and
        # ``split_kwargs`` will re-match them right afterwards anyway.
        # Measured on a render of /tabs: 0.50 ms → 0.05 ms.
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
        # Reject ``ClientBinding`` on props/slots absent from
        # ``BINDABLE_PROPS``. Kills the "silently frozen SSR" class of bug
        # and makes the reactive surface explicit at definition time.
        #
        # The default is the empty tuple: a component that forgets to
        # declare its surface refuses every binding on the first use.
        #
        # Universal modifiers (visible/tooltip/classes/style) are
        # popped before split_kwargs and not subject to this check.
        bindable = set(cls.BINDABLE_PROPS)
        for kw_name, kw_value in (*reactive.items(), *slots.items()):
            if isinstance(kw_value, ClientBinding) and kw_name not in bindable:
                allowed = (
                    sorted(bindable) or "(none — this component does not expose any bindable prop)"
                )
                raise ComponentUsageError(
                    f"{cls.__name__}.{kw_name} is not bindable. "
                    f"Bindable props on {cls.__name__} : {allowed}. "
                    f"To make {kw_name} change at runtime, mutate "
                    f"the value on the server and rely on "
                    f"@refreshable to re-render — the framework "
                    f"rebuilds the component with the new value, "
                    f"no client-side binding needed."
                )

        # ── Two-way props: an expression is not assignable ────────────────
        # These props' client path is the ASSIGNMENT TARGET in the JS
        # emitted. A ClientExpression compiles there to
        # ``(a || b) = $value`` → a SyntaxError raised by the browser AT
        # BIND TIME (``compile(expr, "set")``, 02_directives.js), so the
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

        # ── Reactive prop storage : split static / binding / client-expr ────

        self._reactive_values: dict[str, Any] = {}
        self._binding_metadata: dict[str, ClientBinding] = {}
        self._client_expressions: dict[str, str] = {}

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
                # other fields) → ``None``, exactly the contract already
                # established for a client-expr string just below.
                # ``emit_attrs`` skips ``None`` values.
                self._reactive_values[name] = (
                    None if isinstance(value, ClientExpression) else value.value
                )
            elif reads_as_client_expr(value, type(self), name):
                self._client_expressions[name] = value
                # Store ``None`` for SSR — the runtime will compute
                # the real attribute value once the runtime evaluates.
                self._reactive_values[name] = None
            else:
                # A Component passed as a PROP value (``icon=ui.icon(...)``,
                # ``avatar=ui.avatar(...)``, …) auto-registered itself as a
                # child of the active parent the moment it was constructed.
                # The receiving component OWNS it (it renders it, or reads
                # its props), so detach it from the parent stack — otherwise
                # it ALSO renders standalone (the recurring "double
                # icon/avatar" bug). NAMED_SLOTS already get this via
                # ``adopt_slot`` ; this closes the reactive-prop path so the
                # whole framework behaves uniformly, once, here.
                if isinstance(value, Component):
                    Component._detach_from_parent(value)
                # Otherwise the dict dies on ``unhashable type: 'dict'``,
                # three frames down. The guard lives in ``responsive``.
                reject_stray_breakpoints(cls.__name__, name, value,
                                         self.RESPONSIVE_PROPS)
                self._reactive_values[name] = value

        # Fill in defaults for any reactive prop the caller didn't pass.
        for name, descriptor in cls.__reactive_props__.items():
            if name not in self._reactive_values:
                self._reactive_values[name] = descriptor.resolve_default()

        # ── Slots / raw attrs ──────────────────────────────────────────
        #
        # Two side effects on the slot dict :
        # 1. Strings landing in a slot listed in ``ICON_SLOTS`` get
        #    auto-wrapped via ``ui.icon(name)`` so callers can write
        #    ``ui.button("Save", icon_left="save")`` instead of the verbose
        #    component form. The full ``icon=ui.icon(name, size=…)``
        #    form keeps working — anything already a Component flows
        #    through unchanged.
        # 2. Component values get DETACHED from the active parent's
        #    children list. They auto-registered themselves there
        #    during their own ``__init__`` (the only signal a fresh
        #    component has about who its parent is) ; now that we know
        #    they're a slot of THIS component, they shouldn't ALSO
        #    appear as a sibling. Without this step, ``ui.button(icon
        #    =ui.icon("trash"))`` rendered the icon twice — once
        #    standalone in the row, once inside the button.
        # NAMED_SLOTS plumbing : route each slot value through adopt_slot,
        # which centralises the string→Icon wrap (for ICON_SLOTS), the
        # ClientBinding→Icon wrap (Phase 3 cleanup), and the parent-detach
        # step. Pre-Phase-3, this loop did the first wrap inline but
        # missed the binding case ; now both paths converge.
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
            _p = ctx.parent_stack[-1] if ctx.parent_stack else None
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
        for kwarg, handler in events.items():
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
            action_id, args_blob, sig = ctx.register_action(handler, self.id, event)
            if server_event is None:
                # First server handler → on the root element itself.
                server_event = event
                self._event_attrs.update(
                    action_attrs(event, action_id, args_blob, sig, modifier=self._trigger_modifier)
                )
            else:
                # Extra server handler → hidden carrier that listens for
                # the event FROM the root (HTMX ``from:`` clause). A stable
                # id keeps idiomorph matching it across refreshes.
                carrier = action_attrs(
                    event,
                    action_id,
                    args_blob,
                    sig,
                    modifier=self._trigger_modifier,
                    from_id=self.id,
                )
                carrier["id"] = f"{self.id}__on{event}"
                carrier["hidden"] = True
                self._event_carriers.append(carrier)

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
        if not self._is_subcomponent:
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
            raise TypeError(
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
    def adopt_slot(value: Any, *, icon_shortcut: bool = False) -> Any:
        """Normalise a slot value before storing it on a component.

        Used by components that handle their own slot kwargs outside
        the ``NAMED_SLOTS`` pipeline (Input has ``icon_left``,
        ``icon_right``, ``prefix``, ``suffix`` it juggles manually).
        Two side effects :

        - When ``icon_shortcut=True`` and ``value`` is a string, wrap
          it in ``ui.icon(value)`` so callers can write
          ``icon_left="search"`` instead of the verbose component
          form.
        - When ``value`` is a Component, detach it from whatever
          parent it auto-registered into during its own
          ``__init__`` — the slot is the new owner, no double render.

        Returns ``None`` for ``None``, the converted/detached value
        otherwise. Strings without ``icon_shortcut`` flow through
        unchanged (e.g. plain prefix text).
        """
        if value is None:
            return None
        if isinstance(value, str) and icon_shortcut:
            from bretzel.components.primitives.icon import Icon

            value = Icon(value)
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

            value = Icon(typing.cast(Any, value))
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

    def add_child(self, child: Any) -> None:
        if not type(self).IS_CONTAINER:
            raise TypeError(f"{type(self).__name__} is a leaf, can't add children.")
        self._children.append(child)

    # ── Rendering helpers ──────────────────────────────────────────────

    def _scope_keys(self, prop: str = "value") -> tuple[str, ...]:
        """The key(s) under which ``prop`` lives in the ``bz-data``.

        Derived from ``reactive_prop(scope_keys=)`` by the metaclass;
        default ``(prop,)`` when the scope key IS the prop's name. It is
        the information that was missing and hard-coded in every
        ``server_sync_marker("active"/"picked"/…, …)`` — the naming
        divergence (value/picked/active/expanded/sel) that caused 5 of
        the 8 missed ``_serverSync``. Now declared in the same place as
        the prop. Cf. todo.md § "the underlying mechanism".
        """
        return type(self).__scope_keys__.get(prop, (prop,))

    def _value_server_backed(self, prop: str = "value") -> bool:
        """Does ``prop`` hold a value coming from the SERVER, in local mode?

        It is the condition — and the ONLY one — for emitting
        ``_serverSync`` (cf. ``base/_wiring.server_sync_marker``): on the
        next swap, the bridge will re-adopt that scope signal from the
        freshly morphed attribute, because the server is authoritative.

        Three cases, in order:

        1. **Client-binding mode** → ``False``. The value lives in
           ``$bz._store``, which the envelope already patches: nothing to
           re-adopt, and rewriting the signal would overwrite the
           client's edit.
        2. **Stamped scalar or list** (``_BoundStr`` / ``_BoundInt`` /
           ``_BoundList``… set by ``state/scopes/server._stamp``) →
           ``True``.
        3. **``[state.field]``** — a literal list one of whose ITEMS
           carries the stamp (a multi fed by a scalar server pick, the
           playground's pattern) → ``True``.

        ⚠️ **This is NOT ``_derive_field_name``**, and the confusion is
        expensive. That helper answers "where do I derive my HTML
        ``name=`` from"; this one answers "where does my value come
        from". They coincide on form inputs, hence the temptation to
        reuse one for the other — ``select.py`` did ("reuse it rather
        than re-reading the value"), and it produced TWO flaws: case 3
        was lost (a multi fed by ``[state.field]`` did not re-adopt), and
        the server-sync died silently if ``AUTONAME_FROM`` was removed. A
        component with no ``name=`` (Tabs, Accordion, Tree, the overlays)
        still has a server value.

        Before this helper, the decision was retyped in 5 diverging
        dialects across 12 call sites — the mechanical cause of the 8
        missed ``_serverSync``. Cf. todo.md § A3 and traps.md § "A
        server-bound input does NOT reflect a value changed by the
        SERVER".
        """
        if self._binding_metadata.get(prop) is not None:
            return False
        raw = self._reactive_values.get(prop)
        if getattr(raw, "field_name", None) is not None:
            return True
        if isinstance(raw, (list, tuple)):
            return any(getattr(v, "field_name", None) is not None for v in raw)
        return False

    def _derive_field_name(self) -> str | None:
        """Autoname field name from the bound / server-stamped ``AUTONAME_FROM`` prop.

        Two sources, in order : (1) a ``ClientBinding`` passed as
        ``value=state.foo`` (its ``field_name``), (2) a server-state scalar
        stamped by :func:`bretzel.state.scopes.server._stamp` (a ``_Bound*``
        carrying ``field_name``). Returns ``None`` when neither is present.

        Placement-agnostic : returns only the string. The base
        :meth:`emit_attrs` lands it on the root ``name`` ; composite inputs
        (root is a ``<div>`` / ``<label>`` / custom element) layer their own
        explicit-``name=`` and fallback around it and stamp the hidden
        ``<input>`` carrier themselves. Single source for the derivation the
        ~12 carrier components used to each re-implement.
        """
        prop = type(self).AUTONAME_FROM
        if not prop:
            return None
        binding = self._binding_metadata.get(prop)
        field_name = getattr(binding, "field_name", None)
        if not field_name:
            raw = self._reactive_values.get(prop)
            field_name = getattr(raw, "field_name", None)
        return field_name

    def emit_attrs(self) -> dict[str, Any]:
        """Build the HTML attribute dict for this component's root.

        Framework attrs (``id`` / ``bz-id`` — **not** ``bz-version``, dead
        in V3, cf. the branch comment 100 lines below) are emitted
        **conditionally** — only when the component carries something the
        runtime actually needs to track: a reactive binding, a client
        expression, an event handler, or a raw ``bz-*`` directive the
        user wired by hand. Pure static nodes (``ui.text("Hello")`` with
        no props) stay anonymous, exactly like in v1. The rule keeps the
        DOM clean and skips the per-instance version hash for the 90 % of
        nodes that don't need identity.
        """
        attrs: dict[str, Any] = {}

        descriptors = type(self).__reactive_props__

        for name, value in self._reactive_values.items():
            descriptor = descriptors.get(name)
            cosmetic = descriptor is not None and not getattr(descriptor, "emit_attr", True)

            # ⚠️ The exit PRECEDES ``normalize_attr_name``, and that is
            # the point: a cosmetic prop only reaches the DOM through a
            # client expression (branch 2), never through its binding nor
            # its literal. Normalising first meant throwing the result
            # away for 80 to 89 % of a page's reactive props (measured).
            if cosmetic and name not in self._client_expressions:
                continue

            attr_name = normalize_attr_name(name)

            # 1. ClientBinding — emit ``bz-attr:<attr>="<expression>"``
            #    (V3 one-way reactive attribute bind). The expression is
            #    the full ``$bz.state.<path>`` form — the V3 evaluator
            #    takes plain JS, no implicit prefixing.
            #
            #    ServerBinding is intentionally not reactive client-
            #    side — the SSR'd value is the truth until the next
            #    refresh. We just emit the literal ``value`` attr
            #    below (skipping the reactive branch).
            if name in self._binding_metadata:
                if cosmetic:  # bound AND cosmetic: nothing is emitted
                    continue
                binding = self._binding_metadata[name]
                if isinstance(binding, ClientBinding):
                    attrs[f"{BZ_ATTR_PREFIX}{attr_name}"] = self.path_of(binding)
                    # Fall through to the literal-value path below so
                    # the SSR HTML carries the binding's resolved value
                    # as a static attr (``checked``, ``value="x"``, …).
                    # Without this, the browser paints the element's
                    # *default* state (unchecked / empty) before the
                    # runtime boots and applies the binding — visible
                    # flash. ``_reactive_values[name]`` was already set
                    # to ``binding.value`` at __init__ time so the
                    # loop's ``value`` variable carries the right SSR
                    # snapshot.
                else:
                    # ServerBinding falls through to the literal-value
                    # path below — emit the resolved value as a static
                    # HTML attr.
                    value = binding.value

            # 2. Client JS expression string — emit ``bz-attr:<attr>``
            #    with the raw expression. Same reasoning as above.
            if name in self._client_expressions:
                attrs[f"{BZ_ATTR_PREFIX}{attr_name}"] = self._client_expressions[name]
                continue

            # 3. Static literal. The ``cosmetic`` guard that lived here
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
        #   directive). Emits ``id`` + ``bz-id`` — in V3, ``bz-id`` is
        #   load-bearing : it keys the bz-data scope store so component
        #   state survives idiomorph swaps. No ``bz-version`` (dead in
        #   V3 — the scope Map makes morph-guards unnecessary).
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

        # ``style=`` kwarg → ``style="..."`` (literal) or
        # ``bz-attr:style="..."`` (the old ``:style`` is dead Alpine
        # dialect; and the literal is NOT set here but post-render)
        # (ClientBinding) on the root attrs. Every component that uses
        # ``emit_attrs()`` to build its root dict gets the user's
        # ``style=`` for free — without this, the kwarg was silently
        # dropped on every component except Button / IconButton (which
        # called ``apply_class_attrs`` manually).
        self.apply_style_attr(attrs)

        # What the tag cannot carry (``type`` on an ``<a>``…). Deferred
        # import — ``component`` depends on ``_wiring``.
        from bretzel.components.base._wiring import drop_tag_bound_attrs

        drop_tag_bound_attrs(self._tag, attrs, spare=self._author_written_attrs())

        return attrs

    def _author_written_attrs(self) -> set[str]:
        """The attribute names the CALLER wrote themselves."""
        return self._raw_attrs.keys() | self._passthrough_attrs.keys()

    def slot_class(self, slot: str, *extra: str) -> str:
        """Compose classes for a non-root slot and optional extra fragments."""
        return " ".join(
            part
            for part in (
                self.compose_class(slot, apply_variant_size_modifiers=False),
                *extra,
            )
            if part
        )

    def compose_class(
        self,
        slot: str = "root",
        *,
        apply_variant_size_modifiers: bool = True,
    ) -> str:
        """Compose the Tailwind class string for one of this component's slots.

        Reads the resolved theme dict (with app-level overrides applied
        when a render context is active), pulls the slot template,
        applies variant / size / modifier lookups when relevant. The
        user-supplied ``classes=`` are NOT added
        here — they land on the true root later, in
        ``_apply_universal_modifiers`` (the metaclass render wrap), so
        cosmetic overrides still win in source order (see step 5 below).

        Parameters:
        - ``slot``: key in ``theme["slots"]``. Defaults to ``"root"``.
          Multi-slot components (checkbox with root/input/label,
          dropdown with backdrop/panel/item, …) call this once per
          slot they want to compose.
        The colour is carried by the bridge class set on the rendered
        root (cf. :mod:`bretzel.theme.bridges`); composing the slot
        therefore does not depend directly on the colour.
        - ``apply_variant_size_modifiers``: when True (default),
          appends ``theme["variants"][<variant>]`` +
          ``theme["sizes"][<size>]`` + every truthy modifier from
          ``theme["modifiers"]``. Set to False on non-root slots
          where these don't apply (the user's ``classes=`` and
          variants belong to root only).

        ~85 % of components fit this template; complex composites
        (datatable cells, dropdown items inheriting from parent
        context) override or skip it.
        """
        theme = self._resolved_theme()
        parts: list[str] = []

        # 1. The slot template itself.
        slot_template = theme.get("slots", {}).get(slot)
        if slot_template:
            parts.append(slot_template)

        if apply_variant_size_modifiers and slot == "root":
            # 2. Variant.
            variant_value = self._reactive_values.get("variant")
            if variant_value is not None:
                variant_template = theme.get("variants", {}).get(variant_value)
                if variant_template:
                    parts.append(variant_template)

            # 3. Size. Components with flat sizes (Button, TextNode, Flex)
            # store ``sizes[<key>]`` as a single class string ; the
            # composer appends it. Components with multi-slot sizes
            # (Checkbox, Switch, Input) store a dict per size and
            # resolve it themselves in ``render()`` — we silently
            # skip in that case rather than croaking on
            # ``str.join(dict)``.
            size_value = self._reactive_values.get("size")
            if size_value is not None:
                size_classes = theme.get("sizes", {}).get(size_value)
                if isinstance(size_classes, str) and size_classes:
                    parts.append(size_classes)

            # 4. Modifiers — boolean reactive props that map to a class
            #    when truthy. Looked up under ``theme["modifiers"]``.
            for mod_name, mod_class in theme.get("modifiers", {}).items():
                if self._reactive_values.get(mod_name):
                    parts.append(mod_class)

        # 5. User classes — NOT appended here. They land on the
        # component's true root in ``_apply_universal_modifiers`` (the
        # metaclass render wrap), so every component honours ``classes=``
        # uniformly regardless of which slot composes its root. See
        # ``_user_classes_str``.

        # 6. Slot override via ``slots={"<slot>": "..."}`` kwarg — NON-root
        # slots only. The ``"root"`` override lands on the component's TRUE
        # root in ``_apply_universal_modifiers``, for the same reason
        # ``classes=`` and ``style=`` moved there : a component whose root is
        # composed by another slot (or which reads ``theme["slots"]["root"]``
        # by hand) never reached this line, and dropped the user's override
        # without a word. Non-root slots stay here — the socle patches the
        # rendered ROOT node, it cannot know which deep descendant carries a
        # component's "panel" or "item" slot.
        #
        # ⚠️ Which means a component that composes a non-root slot WITHOUT
        # calling this method still drops the override in silence — measured
        # on ``ToggleGroup(slots={"item": …})``, which reads
        # ``theme["slots"]["item"]`` directly. Same class of defect as the
        # root one this step used to have, one slot over ; not closed yet.
        if slot != "root" and (user_slot := (self._user_slots or {}).get(slot)):
            parts.append(str(user_slot))

        return " ".join(p for p in parts if p).strip()

    @property
    def _raw_class_str(self) -> str:
        """The ``class`` written as raw HTML — ``class_="x"`` or
        ``attrs={"class": "x"}``, which ``split_kwargs`` normalises to the
        same key and which therefore both land in ``_raw_attrs``.

        Read by the metaclass wrap, NOT by ``emit_attrs``: a component
        that rebuilds its ``class=`` in ``render()`` would overwrite what
        ``emit_attrs`` had set there. It is the same reason that moved
        ``classes=`` and ``slots={"root"}`` up to the wrap.
        """
        raw = self._raw_attrs.get("class")
        return raw if isinstance(raw, str) else ""

    def _user_classes_str(self) -> str:
        """The literal ``classes=`` flattened to a string ('' when unset
        or when it's a ``ClientBinding``).

        Single source for appending the user's ``classes=`` onto a
        component's TRUE root. ``compose_class`` uses it for the canonical
        "root" slot ; components whose root is composed via another slot
        (Input's bare/affix paths, Slider) call it directly so ``classes=``
        is never silently dropped."""
        if not self._classes:
            return ""
        if isinstance(self._classes, str):
            return self._classes
        return " ".join(str(v) for v in self._classes if v)

    # ── Class composition helper ────────────────────────────────────────

    def apply_class_attrs(
        self,
        attrs: dict[str, Any],
        slot: str = "root",
    ) -> None:
        """Set the composed ``class=`` on ``attrs``.

        The user's ``classes=`` — literal **as well as** binding — is NOT
        this helper's business: ``_apply_universal_modifiers`` (the
        metaclass wrap) sets it on every component's true root, so all 55
        benefit and not only those that call here. This helper only
        composes the theme's slot.

        (History: the reactive branch lived here and emitted
        ``:class="…"`` — Alpine syntax, dead in V3 — dropping the static
        ``class=`` on the way. Two components called it, so they rendered
        with no class at all as soon as they were passed a
        ``classes=binding``. Cf. the
        ``tests/consistency/test_reactive_classes_universal.py`` gate.)

        Note: reactive variant/size/color axes are NOT supported.
        Those are design-time configuration per the ``BINDABLE_PROPS``
        contract — if a use case for dynamic theme axes appears,
        server-side conditional render at the call site covers it
        (``ui.button(label, color="error" if state.failed else
        "success")``).

        ``style=`` is NOT handled here; it's materialised by
        :meth:`emit_attrs` so every component gets it for free, not
        just the ones that call this helper.

        """
        cls_string = self.compose_class(slot)
        if cls_string:
            # ``merge_attr`` and not ``attrs["class"] = …``: a
            # ``class_=`` or an ``attrs={"class": …}`` already set by
            # ``emit_attrs`` must SURVIVE the theme's composition, not be
            # replaced by it.
            merge_attr(attrs, "class", cls_string)

    @staticmethod
    def with_slot_class(node: Node, slot_class: str, **extra_attrs: Any) -> Node:
        """Clone ``node`` with ``slot_class`` PREPENDED to its ``class``.

        The gesture: a component receives a subcomponent as a slot (a nav
        item's icon, an Input's affix, a Breadcrumb's separator, a
        Sidebar's badge), renders it, then must set its slot class on it
        **without** overwriting the one the child composed for itself.
        ``Element`` being immutable, that means cloning.

        Prepended, not appended: the child's classes stay last, so they
        win at equal Tailwind specificity — the slot dresses, the child
        decides.

        ``extra_attrs`` covers the Breadcrumb case, which sets an
        ``aria-hidden`` on the same clone (otherwise two would be
        needed).

        A ``node`` that is not an ``Element`` (FragmentNode, TextNode)
        comes back as-is: it has no attributes to set the class on.

        Four components carried this clone-and-merge inline (audit F56),
        of which only one handled the "empty existing class" branch
        properly.
        """
        if not isinstance(node, Element):
            return node
        existing = str(node.attrs.get("class", "")).strip()
        merged = f"{slot_class} {existing}".strip() if existing else slot_class
        import dataclasses as _dc

        return _dc.replace(node, attrs={**node.attrs, "class": merged, **extra_attrs})

    def apply_style_attr(self, attrs: dict[str, Any]) -> None:
        """Set ``bz-attr:style=`` (reactive) from the user's ``style=``
        kwarg.

        A :class:`ClientBinding` on ``style=`` becomes the runtime's
        ``bz-attr:style`` directive (:meth:`path_of` resolves the
        binding-vs-expression prefix in one place). A LITERAL ``style=``
        string is NOT stamped here — it's applied to the component's true
        root in :func:`_apply_universal_modifiers` (the render wrap), so
        peer-input components don't bury it on their hidden ``<input>``.
        """
        binding = self._style_binding
        if binding is not None:
            attrs[f"{BZ_ATTR_PREFIX}style"] = self.path_of(binding)
            return
        # Literal style= is applied to the component's TRUE root in
        # ``_apply_universal_modifiers`` (the render wrap), so peer-input
        # components don't bury it on their hidden <input>. Not stamped
        # here, to avoid doubling.

    @staticmethod
    def _cloak_show(elem: Node, expr: str, *, initial: bool = False) -> Element:
        """Wrap ``elem`` with ``bz-show`` for a mutex branch (V3).

        Used by every component that emits BOTH branches of a reactive
        structural toggle in the DOM and lets the runtime pick which to
        show via ``bz-show`` (Button.loading spinner ↔ icon, IconButton
        same). ⚠️ NOT Alert: it never calls ``_cloak_show``, and
        ``dismissible`` is in no ``BINDABLE_PROPS`` (the only two callers
        are Button and ``actions/_wiring``). FOUC strategy (spec
        .claude/bretzel/runtime.md): the server pre-stamps ``style="display:none"``
        on the branch whose ``initial`` evaluation is falsy, so nothing
        flashes before the runtime's first effect takes over.

        Static-only renders don't call this — the helper is purely for
        the binding-aware structural-mutex pattern.

        ``elem`` is typed ``Node`` because callers pass the result of
        ``component.render()`` (whose base signature is ``-> Node``).
        At runtime every mutex branch must be an :class:`Element` —
        the assertion documents that contract and surfaces violations
        loudly instead of silently dropping ``bz-show`` on a TextNode node.
        """
        assert isinstance(elem, Element), (
            f"bz-show mutex requires an Element wrapper (got {type(elem).__name__})"
        )
        attrs = {**elem.attrs, BZ_SHOW_PREFIX: expr}
        if not initial:
            stamp_display_none(attrs)
        return Element(
            tag=elem.tag,
            attrs=attrs,
            children=elem.children,
        )

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
        interchangeable — census of 2026-08-19 over the catalogue's **37
        calls**:

        1. **keep the RESULT** — ``node = emit_text_slot(v)`` then
           ``if node is not None:`` (20 sites). Of these, **10 guard the
           construction of a wrapper** (`<h3>`, `<div class="title">`,
           `<span class="label">`…) and not merely the append: without
           the guard, the component would emit an EMPTY wrapper, that is
           to say a visible hole in a ``flex gap-*`` row;
        2. **keep the VALUE upstream** — ``if v:`` before even building
           the wrapper (12 sites), the call then never happening on an
           empty slot.

        Three legitimate variants complete the picture: the mandatory
        wrapper whose CONTENT alone is optional (``date_range_picker``:
        the ``<span>`` separates two fields and must exist),
        ``tooltip``'s ``or TextNode("")`` (the panel always exists), and
        ``link``'s prefix.

        ⚠️ **The trap**: keeping the raw value with ``is not None``.
        ``""`` passes it, the wrapper is built, the call returns ``None``
        and ``serialize`` raises. That is what broke ``toggle_button``.
        The safe form on the raw value is the truth test (``if v:``);
        ``is not None`` only holds on the RESULT. Measured: zero
        occurrences of the trap today.

        The class is guarded by
        ``tests/consistency/test_text_slot_contract_universal.py``, whose
        population is DERIVED: it replays every textual parameter of the
        catalogue with ``""``, so a new site that forgets its guard turns
        red with nothing to register anywhere.

        **Why the ``None`` is not filtered in ``Element``** (idea set
        aside on 2026-08-19, after measurement): a filter in
        ``Element.__post_init__`` would remove 9 guards out of 20 — and
        would break the other 10 silently, since they guard the wrapper,
        not the append. For 479 ``Element`` construction sites touched.
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
        # at 0x…>") to the browser. The caller must already have
        # detached the component from its auto-attached parent (via
        # ``adopt_slot`` in their ``__init__``) ; otherwise the same
        # instance ends up rendered twice — standalone in the parent
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

    def _dispatch_command(
        self,
        event_name: str,
        *,
        value: Any = MISSING,
    ) -> str:
        """Build the client-expr source for dispatching a command event.

        Used by the write-only imperative API (`.open()` / `.close()` /
        `.toggle()` and value-bearing methods `.set(value)` /
        `.clear()`) when no :class:`ClientBinding` is in play for the
        target prop. Returns a client expression string, same return
        shape as ``ClientBinding.set/toggle`` — so the result is
        consumable by ``on_click=`` and any other ``on_*`` slot.

        The dispatched CustomEvent bubbles, so the component's root
        can listen via a single ``@<event_name>`` directive without
        worrying about which descendant the original click landed on.

        Pass ``value=`` to attach a payload that the component's
        listener can read via ``$event.detail.value``. Used by
        ``.set(value)`` style methods on Checkbox / Switch / Input /
        Select where the new value has to travel with the event.
        Skipping ``value=`` emits the event with no detail (for
        valueless commands like ``.open()`` / ``.close()`` /
        ``.toggle()``).

        Convention : framework-internal commands are prefixed ``bz-``
        (``bz-open``, ``bz-close``, ``bz-toggle``, ``bz-set``,
        ``bz-step``, etc.) so they never collide with user-defined
        custom events. See `imperative-api.md`.
        """
        if value is MISSING:
            return (
                f"document.getElementById('{self.id}').dispatchEvent("
                f"new CustomEvent('{event_name}', {{bubbles: true}}))"
            )
        return (
            f"document.getElementById('{self.id}').dispatchEvent("
            f"new CustomEvent('{event_name}', "
            f"{{bubbles: true, detail: {{value: {_to_js(value)}}}}}))"
        )

    def _value_command(
        self,
        value: Any,
        *,
        prop: str = "value",
        event: str = "bz-set",
    ) -> str:
        """The body of ``.set(value)``: write-through, otherwise dispatch.

        An imperative method carrying a value has exactly two paths —
        writing into the :class:`ClientBinding` passed at construction
        (the single source of truth), or, failing that, dispatching a DOM
        command the component's root catches. It is the same switch that
        :func:`base._wiring.install_open_close_toggle` factors out for
        the overlay family.

        It was copied as-is into **eleven** components (audit F11, F12):
        Input, Textarea, NumberInput, Slider, Calendar, Radio, Select,
        Combobox, ToggleGroup (on ``value``), Checkbox and Switch (on
        ``checked``, with boolean coercion). A change to the contract — a
        new binding subtype, another event name — therefore had to be
        replicated eleven times.

        What stays per-component, rightly: ``.clear()`` (the reset value
        is semantic — ``""``, ``[]``, ``min``, ``None``) and ``.focus()``
        / ``.blur()`` (the focusable surface differs).
        """
        binding = self._binding_metadata.get(prop)
        if binding is not None:
            return binding.set(value)
        return self._dispatch_command(event, value=value)

    def _toggle_command(
        self,
        *,
        prop: str = "checked",
        event: str = "bz-toggle",
    ) -> str:
        """The body of ``.toggle()`` — same switch as
        :meth:`_value_command`, with ``binding.toggle()`` on the binding
        side.

        Copied identically into Checkbox and Switch.
        """
        binding = self._binding_metadata.get(prop)
        if binding is not None:
            return binding.toggle()
        return self._dispatch_command(event)

    @staticmethod
    def path_of(binding: ClientBinding) -> str:
        """Canonical client-side path for ``binding``, whatever its
        concrete subclass.

        - :class:`ClientBinding` → ``$bz.state.Class.key.field`` (the
          full form, ready to interpolate into a client expression
          like ``bz-attr:disabled="…"`` or ``bz-on:click="… = …"`` — the
          ``:``/``@`` forms are dead Alpine dialect).
        - :class:`ClientExpression` → the verbatim JS expression the
          builder accumulated (no ``$bz.state.`` prefix is added —
          the expression already contains the path fragments).

        This unifies the if/else ladder that lived in every component
        rendering a bz-attr binding manually: ``isinstance(b,
        ClientExpression) ? b.binding_path() : f"$bz.state.{b.serialize_path()}"``.
        The forms are equivalent because :py:meth:`ClientExpression.binding_path`
        returns the same string as :py:meth:`ClientExpression.serialize_path`
        (the raw expression), and ``binding_path`` on a plain binding
        prepends ``$bz.state.`` itself. Funneling through this helper
        kills a recurring source of divergence between components.
        """
        return binding.binding_path()

    def release_root_attr(
        self,
        prop: str,
        root_attrs: dict[str, Any],
    ) -> None:
        """Strip the literal AND reactive directives for ``prop`` from
        the component's root attrs.

        Use when a binding-bearing prop is wired to an INNER element
        (via :py:meth:`forward_binding`) OR when the component manages
        the value via custom client wiring (date pickers' ``$watch``
        pair on the wrapper). Leaving the wrapper-level directive
        emitted means the runtime writes a useless ``X=""`` on the wrapper
        every reactive tick and the carrier-landing audit flags it.

        Pops both the literal ``<prop>="…"`` and the reactive
        ``bz-attr:<prop>="…"`` so neither survives.
        """
        attr_name = normalize_attr_name(prop)
        root_attrs.pop(attr_name, None)
        root_attrs.pop(f"{BZ_ATTR_PREFIX}{attr_name}", None)

    def forward_binding(
        self,
        prop: str,
        target_attrs: dict[str, Any],
        *,
        as_attr: str | None = None,
        root_attrs: dict[str, Any] | None = None,
    ) -> ClientBinding | None:
        """Forward ``prop``'s :class:`ClientBinding` onto a carrier
        element's attrs.

        Solves the wrapper-vs-carrier trap : :py:meth:`emit_attrs`
        lands ``bz-attr:<prop>`` on the component's ROOT, but many
        HTML attributes only do something on a specific tag —
        ``disabled`` / ``multiple`` / ``accept`` / ``required`` on
        form controls ; ``src`` / ``srcset`` on media ; ``value`` on
        the form-data carrier. Writing them on the wrapper ``<div>``
        / ``<span>`` is a no-op the runtime silently performs every
        reactive tick, and the unit tests don't notice because the
        SSR HTML "looks right".

        This method :

        - Adds ``bz-attr:<as_attr or prop>="$bz.state.<path>"`` to
          ``target_attrs`` (the inner carrier's attrs dict).
        - When ``root_attrs`` is passed, pops the duplicate
          ``bz-attr:<as_attr or prop>`` AND its literal-value
          equivalent (``as_attr or prop``) from the wrapper so the
          binding lives on the carrier alone — exactly one writer
          per attribute, no runtime tick wasted patching a div.

        Returns the resolved binding (or ``None`` when ``prop`` had
        no binding) so callers can branch on the static-value
        fallback path without re-reading ``_binding_metadata``.

        Use this in every component whose render emits a nested
        carrier element distinct from the root. Cf.
        ``.claude/bretzel/traps.md`` § "wrapper-vs-carrier" for the
        bug class this primitive eliminates.
        """
        binding = self._binding_metadata.get(prop)
        if not isinstance(binding, ClientBinding):
            return None
        attr = as_attr or prop
        attr_name = normalize_attr_name(attr)
        # ⚠️ ARIA wants the STRING "true"/"false", not the semantics of
        # native boolean attributes. ``bz-attr`` treats a boolean the way
        # HTML wants — ``true`` → EMPTY attribute, ``false`` → attribute
        # removed (02_directives.js) — which is correct for ``disabled``
        # / ``checked``, and WRONG for ``aria-*``: the Tailwind
        # ``aria-disabled:`` variant compiles to
        # ``[aria-disabled="true"]``, which an empty attribute does not
        # match, and a screen reader reads nothing. The ternary was
        # written by hand in nav/_wiring and calendar, with the comment
        # each time; select and combobox slipped through. Derived here,
        # it can no longer be forgotten.
        from bretzel.components.base._wiring import bool_attr

        path = self.path_of(binding)
        value = bool_attr(path) if attr_name.startswith("aria-") else path
        target_attrs[f"{BZ_ATTR_PREFIX}{attr_name}"] = value
        if root_attrs is not None:
            self.release_root_attr(attr, root_attrs)
        return binding

    def _bind_x_model(
        self,
        attrs: dict[str, Any],
        prop: str = "value",
        *,
        binding: ClientBinding | None = None,
    ) -> ClientBinding | None:
        """Wire ``bz-model`` two-way binding for ``prop`` on ``attrs``.

        Form-input components call this with the dict that will
        become the real ``<input>`` attrs. When a :class:`ClientBinding`
        is in play for ``prop`` (typically ``"value"`` for text inputs /
        select, ``"checked"`` for checkbox / switch), we drop the
        read-only ``bz-attr:<prop>`` directive that
        :py:meth:`emit_attrs` set and replace it with
        ``bz-model="$bz.state.<path>"``, which the runtime propagates
        in BOTH directions.

        By default the binding is read from ``self._binding_metadata``.
        Composite inputs whose binding lives on an enclosing parent
        (Radio inherits the group's ``value=binding`` ; date-range
        pickers split a single binding across two child inputs) pass
        ``binding=...`` explicitly to override the lookup.

        Returns the resolved binding (or ``None`` when none was found)
        so callers can branch on the literal-value fallback — Textarea
        uses it to suppress the ``initial_text`` emission, Radio to
        compute ``checked`` from a static value comparison.

        Reading the binding from ``_binding_metadata`` is mandatory :
        the matching entry in ``_reactive_values`` carries the
        binding's underlying SSR value, not the binding object itself,
        so an ``isinstance(_reactive_values[prop], ClientBinding)``
        check is always False at runtime (cf. ``traps.md``).
        """
        if binding is None:
            binding = self._binding_metadata.get(prop)
        if binding is None:
            return None
        attr_name = normalize_attr_name(prop)
        attrs.pop(f"{BZ_ATTR_PREFIX}{attr_name}", None)
        attrs[BZ_MODEL_PREFIX] = f"$bz.state.{binding.serialize_path()}"
        return binding

    def _resolved_theme(
        self,
        key: str | None = None,
        shipped: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge the user's app-level override onto ``cls.THEME``.

        ``key`` / ``shipped`` default to its own. Passing them resolves
        ANOTHER component's theme — a real case: Combobox and Select
        compose their pills from ``BADGE_THEME`` (they render the pills
        in a client ``bz-for`` template, so they cannot instantiate real
        ``ui.badge``). Reading the module constant directly would bypass
        the user's override: a ``Theme(components={"badge": …})`` would
        not touch the pills.

        ``Theme.merged_component_theme(name, shipped)`` deep-merges the
        user override (``Theme(components={<THEME_KEY>: {...}})``) onto
        the component-shipped default, memoized per THEME_KEY — the
        merge inputs are immutable after boot, and ``compose_class``
        calls this once PER SLOT. Dict levels merge key-by-key so
        overriding one slot never drops the sibling slots, variants or
        sizes; a string leaf REDEFINES that entry wholesale (full
        template — unlike the per-instance ``slots=`` kwarg, which
        appends). Falls back to the bare ``cls.THEME`` when no render
        context is active (typical in unit tests) or when no override
        exists.
        """
        from bretzel.render.context import maybe_current_context

        name = key if key is not None else self.THEME_KEY
        default = shipped if shipped is not None else type(self).THEME

        ctx = maybe_current_context()
        resolved = default
        if ctx is not None:
            theme_obj = getattr(ctx.app, "theme", None)
            getter = getattr(theme_obj, "merged_component_theme", None) if theme_obj else None
            if callable(getter):
                resolved = getter(name, default)
        # ``slots={"panel": …}`` — the per-instance override, for
        # NON-root slots — is added here, at the point where the 164
        # reads of ``theme["slots"][X]`` already draw from.
        #
        # Why here and not in ``compose_class``: only 35 files compose
        # through ``compose_class``; the other 164 reads are done by hand
        # (``slots.get("item")``). An override set in the composer would
        # therefore not reach them, and
        # ``ui.toggle_group(slots={"item": …})`` was measured **lost
        # silently**. The base layer cannot patch a deep descendant after
        # the fact — but it can hand it the right theme BEFORE.
        #
        # ⚠️ ``root`` is EXCLUDED: it is applied post-render by the
        # metaclass wrap (the only one that knows the true root whatever
        # slot composed it). Adding it here would double it.
        #
        # Semantics preserved: the per-instance kwarg ADDS, the app-level
        # ``Theme(components=…)`` override REPLACES.
        # ``_user_slots_validated``: set by ``_reject_unknown_slot_keys``
        # once the keys are checked. Without that guard, the validator —
        # which reads this very theme — would see its own keys injected
        # and would declare any typo KNOWN. Circularity caught by
        # ``test_unknown_slot_key_croaks_at_construction``.
        user_slots = (
            getattr(self, "_user_slots", None)
            if getattr(self, "_user_slots_validated", False)
            else None
        )
        if user_slots and key is None:
            extra = {k: v for k, v in user_slots.items() if k != "root"}
            if extra:
                slots = dict(resolved.get("slots", {}))
                for slot_name, addition in extra.items():
                    base = slots.get(slot_name, "")
                    slots[slot_name] = f"{base} {addition}".strip() if base else str(addition)
                resolved = {**resolved, "slots": slots}
        return resolved

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
          "imperative API with no id"). That behaviour is derived from
          ``IMPERATIVE`` and guarded by
          ``test_imperative_component_needs_identity``.

        ``fuse_or_wrap`` adds the ``bz-id`` of a refreshable section
        on its OWN wrapper; nodes nested inside don't need their own.
        """
        if type(self).IMPERATIVE:
            return True
        if self._binding_metadata or self._client_expressions:
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
            Element(tag="div", attrs=dict(carrier), children=()) for carrier in self._event_carriers
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
        raise TypeError(
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


def _find_x_ref(node: Node, ref_value: str) -> tuple[Element, list[tuple[Element, int]]] | None:
    """Locate the descendant Element with ``bz-ref="<ref_value>"``.

    The name is kept for the stability of internal calls; the marker
    looked for is ``bz-ref``.

    Returns ``(found, path)`` where ``path`` is the list of
    ``(ancestor, child_index)`` pairs from the root to (but not
    including) ``found`` — used by the carrier walker to rebuild the
    immutable Element tree with the carrier's attrs updated.

    Returns ``None`` when no descendant matches. Skips :class:`TextNode` /
    :class:`HtmlNode` / :class:`FragmentNode` leaves and recurses only into
    Element children — FragmentNode's children are flattened by the
    caller before this function would run.
    """
    if not isinstance(node, Element):
        return None
    if node.attrs.get("bz-ref") == ref_value:
        return (node, [])

    def _recur(el: Element) -> tuple[Element, list[tuple[Element, int]]] | None:
        for idx, child in enumerate(el.children):
            if not isinstance(child, Element):
                continue
            if child.attrs.get("bz-ref") == ref_value:
                return (child, [(el, idx)])
            deeper = _recur(child)
            if deeper is not None:
                found, path = deeper
                return (found, [(el, idx), *path])
        return None

    return _recur(node)


def _apply_bindable_carriers(
    component: Component,
    node: Node,
    carriers: Mapping[str, str],
) -> Node:
    """Forward each ``ClientBinding`` declared in ``BINDABLE_CARRIERS``
    onto its target carrier element, rebuilding the immutable tree
    around the change.

    The mapping is ``{prop_name: bz_ref_value}`` — the walker locates
    the descendant Element whose ``bz-ref`` attribute matches the
    declared value, adds ``bz-attr:<prop>="<binding.serialize_path()>"``
    to its attrs, AND pops the duplicate directive from the root
    (so a single writer owns the attribute).

    Skips silently when :
    - The prop has no ClientBinding bound (literal-only call site).
    - The carrier element can't be found (logged via the carrier-
      landing audit — surfaces as a fail there with the actionable
      "bz-ref X not found" message rather than a silent miss here).

    Pure functional : returns a possibly-new Element ; the input
    tree is left untouched.
    """
    if not isinstance(node, Element):
        return node
    new_root = node
    for prop, ref_value in carriers.items():
        binding = component._binding_metadata.get(prop)
        if not isinstance(binding, ClientBinding):
            continue
        located = _find_x_ref(new_root, ref_value)
        if located is None:
            # No carrier found — leave the root's auto-emitted
            # directive in place as fallback. The carrier-landing
            # audit will flag the mismatch with a precise selector
            # so the maintainer knows where to fix.
            continue
        found, path = located
        # Mutate the carrier's attrs with the forwarded directive.
        attr_name = normalize_attr_name(prop)
        new_attrs = {
            **found.attrs,
            f"{BZ_ATTR_PREFIX}{attr_name}": Component.path_of(binding),
        }
        # ``dataclasses.replace`` is the canonical "modify a frozen
        # dataclass" idiom — preserves identity semantics for
        # downstream serialization while producing a new instance.
        import dataclasses as _dc

        new_carrier: Element = _dc.replace(found, attrs=new_attrs)
        # Rebuild ancestors back to the root with the new carrier in
        # place. Walking bottom-up : each level swaps its children
        # tuple to point at the rebuilt subtree.
        current: Element = new_carrier
        for ancestor, idx in reversed(path):
            new_children = list(ancestor.children)
            new_children[idx] = current
            current = _dc.replace(ancestor, children=tuple(new_children))
        new_root = current
        # Strip the root's duplicate directive (the wrapper-level
        # auto-emit) — ``release_root_attr`` would mutate, but we
        # need an immutable variant since Element is frozen.
        if f"{BZ_ATTR_PREFIX}{attr_name}" in new_root.attrs or attr_name in new_root.attrs:
            root_attrs = {**new_root.attrs}
            root_attrs.pop(f"{BZ_ATTR_PREFIX}{attr_name}", None)
            root_attrs.pop(attr_name, None)
            import dataclasses as _dc

            new_root = _dc.replace(new_root, attrs=root_attrs)
    return new_root


def stamp_display_none(attrs: dict[str, Any]) -> None:
    """Append ``display:none`` to an attrs dict's inline ``style``.

    The V3 FOUC strategy (.claude/bretzel/runtime.md) : the server pre-stamps
    the hidden state of every ``bz-show`` whose initial evaluation is
    falsy, so nothing flashes before the runtime's first effect takes
    over. Appending (rather than replacing) preserves any style the
    component already emitted. Public — every component port that
    emits a ``bz-show`` branch uses it.
    """
    existing = str(attrs.get("style", "")).rstrip().rstrip(";")
    attrs["style"] = f"{existing}; display:none" if existing else "display:none"


def coerce_children(rendered: Any) -> tuple[Node, ...]:
    """Normalise what a `render=` escape hatch returned, into children.

    The other end of the contract for components rendering a COLLECTION:
    the component owns the wrapper (a cell's ``<td>``, a breadcrumb's
    ``<a href>``, its ``aria-current``), the author fills the BODY. This
    function is the crossing from one to the other, and it accepts the
    four shapes a callback can return:

    - ``None`` → no children. The component keeps its wrapper empty
      rather than displaying ``"None"``.
    - a :class:`Component` → **detached then rendered**, through
      :meth:`Component.render_detached`. It is the half of the contract
      one forgets: a Component built in the callback's body registers
      itself with the active parent, so without the detachment it renders
      TWICE — once here, once as a sibling. Gated by
      ``test_render_never_orphans``.
    - an already-built :class:`Node` → passed through as-is.
    - everything else → ``str()`` inside a :class:`TextNode`.

    This shared behaviour lives in ``base/`` so that components from
    several families can use it without a cross-cutting import.
    """
    if rendered is None:
        return ()
    if isinstance(rendered, Component):
        return (Component.render_detached(rendered),)
    if isinstance(rendered, Node):
        return (rendered,)
    return (TextNode(str(rendered)),)


def reject_component(
    value: Any,
    *,
    owner: str,
    prop: str,
    because: str,
    instead: str,
) -> None:
    """Refuse a Component on a parameter that is NOT a slot.

    The other half of the contract :meth:`Component.emit_text_slot`
    carries just above: a textual slot accepts ``str | ClientBinding |
    Component``, but not every textual parameter is a slot. A source to
    parse (``markdown.text``), a markup string (``ui.html.content``),
    data serialised as JSON (``file_upload.accept``), or a text that
    **doubles as an HTML attribute** — an ``aria-label`` carries only a
    string, so a Component there would be announced to the screen reader
    under its Python ``repr``.

    The refusal is a **legitimate** state of the contract, on one
    condition: that it be said. Before this function, those parameters
    fell into a ``str(value)`` and shipped ``<bretzel…object at 0x…>``
    into the page, or crashed deep in ``escape_html`` on ``'TextNode'
    object has no attribute 'replace'`` — an error with no visible
    relation to what the author had written.

    ``because`` says what the parameter really is, ``instead`` says what
    to compose with in its place. Both are mandatory: a refusal that does
    not explain reads as a framework bug, and the
    ``test_text_slot_contract_universal`` gate requires the message to
    name the parameter and justify.

    Raised at CONSTRUCTION, never at render — that is
    :class:`ComponentUsageError`'s contract ("raised at instantiation
    time") and the only way a component built then dropped by a
    conditional branch still surfaces the fault.

    The function lives next to :class:`Component`, available in lexical
    scope, and does not depend on the discipline proper to bindings.
    """
    if not isinstance(value, Component):
        return
    raise ComponentUsageError(
        f"{owner} does not accept a Component for ``{prop}=`` — {because} "
        f"It is not a content slot: pass a string. {instead}"
    )


def _ensure_scope_identity(component: Component, node: Node) -> Node:
    """Stamp a STABLE ``id`` / ``bz-id`` on a rendered root that carries a
    ``bz-data`` scope but no id yet.

    Overlays (Tooltip / Select / Dropdown / Popover / …) build their
    ``bz-data`` inside ``render()`` — *after* ``emit_attrs`` ran, so
    ``_needs_identity`` (which runs during ``emit_attrs``) never saw the
    scope and emitted no id. The runtime then assigns a counter-based
    ``bz-id`` that CHANGES on every re-render. Inside a ``@refreshable``
    that re-keys the scope Map each refresh : the element's reused signals
    are dropped, and any teleported panel (still subscribed to the old
    signal) decouples — a tooltip stops showing / hiding after the first
    swap (cf. ``traps.md``).

    ``component.id`` is allocated in ``__init__`` and is position-stable
    across re-renders, so stamping it keeps the scope continuous and lets
    idiomorph match the element. No-op when an id is already present.
    """
    if not isinstance(node, Element):
        return node
    if node.attrs.get("id") or "bz-data" not in node.attrs:
        return node
    cid = component.id
    if not cid:
        return node
    return Element(
        tag=node.tag,
        attrs={**node.attrs, "id": cid, "bz-id": cid},
        children=node.children,
    )


#: A WIDTH utility, variants included.
#:
#: The variant prefix (``md:``, ``dark:hover:``…) is captured so that
#: only two declarations of the SAME scope conflict: an ``md:w-1/2``
#: passed by the caller must not erase the theme's base ``w-full``,
#: otherwise the component would lose its width below the breakpoint.
#:
#: ``max-w-`` / ``min-w-`` are excluded **naturally**: with the variants
#: removed, their base starts with ``max-w-`` / ``min-w-``, not ``w-``.
#: That is the right behaviour and not a happy accident — they are other
#: CSS properties, which compose with ``width`` instead of contradicting
#: it.
_WIDTH_UTILITY = re.compile(r"^(?P<variants>(?:[^\s:]+:)*)!?w-")


def _width_scopes(classes: str) -> set[str]:
    """The variant scopes for which ``classes`` sets a width."""
    scopes: set[str] = set()
    for token in classes.split():
        match = _WIDTH_UTILITY.match(token)
        if match:
            scopes.add(match.group("variants"))
    return scopes


def _drop_widths(existing: str, scopes: set[str]) -> str:
    """Remove from ``existing`` the widths redeclared in ``scopes``."""
    if not scopes:
        return existing
    kept = [
        token
        for token in existing.split()
        if not ((match := _WIDTH_UTILITY.match(token)) and match.group("variants") in scopes)
    ]
    return " ".join(kept)


def _append_attr(node: Element, key: str, value: str) -> Element:
    """Clone ``node`` with ``value`` appended to its ``key`` attribute.

    Append, not prepend — the caller's value lands AFTER whatever the theme
    composed. (That's why this isn't ``Component.with_slot_class``, which
    prepends by contract so a child's own classes stay last.) ``Element``
    is immutable, hence the clone.

    **The order inside the ``class`` attribute decides nothing.** What
    settles two competing Tailwind utilities is their order in the
    generated sheet. When the incoming value declares a width, those of
    the same scope are REMOVED from the existing one. The conflict is
    resolved in the HTML, where we control it, instead of being delegated
    to a sheet order we do not control. The rule holds for ``class``
    only — the other attributes are concatenated as-is.
    """
    existing = str(node.attrs.get(key, ""))
    if key == "class" and existing:
        existing = _drop_widths(existing, _width_scopes(value))
    return Element(
        tag=node.tag,
        attrs={**node.attrs, key: f"{existing} {value}" if existing else value},
        children=node.children,
    )


def _reject_unknown_slot_keys(component: Component, user_slots: Mapping[str, Any]) -> None:
    """Croak on a ``slots={…}`` key this component has no slot for.

    ``"root"`` is always valid — ``_apply_universal_modifiers`` applies it
    to the true root whatever the component does. Any other key only means
    something if the component's resolved theme declares that slot ; a key
    outside that set can never reach the DOM, so accepting it silently is
    the same class of defect this whole item closes. Typos
    (``slots={"pannel": …}``) and wrong-component copy-paste both land here.

    Reads the RESOLVED theme (not ``cls.THEME``) so an app-level
    ``Theme(components=…)`` override that renames slots is honoured rather
    than fought — safe to call from ``__init__``, it falls back to
    ``cls.THEME`` when no render context is active.

    ⚠️ Being a KNOWN slot is not the same as being HONOURED : a component
    that composes a non-root slot by hand can still drop the override in
    silence (measured on ``ToggleGroup(slots={"item": …})``). This function
    only rules out keys that could never mean anything."""
    known = set(component._resolved_theme().get("slots", {}))
    unknown = [k for k in user_slots if k != "root" and k not in known]
    if not unknown:
        return
    name = type(component).__name__
    available = ", ".join(sorted(known)) or "(none — root only)"
    raise ComponentUsageError(
        f"{name}(slots=…) got {unknown!r}, which {name} has no slot for, "
        f"so the override would silently do nothing. Available slots : "
        f"{available}. Use slots={{'root': '…'}} to restyle the outer "
        f"element, or classes='…' to append cosmetic classes to it."
    )


def finish_render(component: Component, node: Node) -> Node:
    """The three passes EVERY component node must undergo after its
    ``render()``, in order.

    1. **``BINDABLE_CARRIERS``** — when the subclass declares a
       ``{prop: bz-ref}`` map, the base layer walks the rendered tree,
       locates the carrier and transfers the ``bz-attr:<attr>`` onto it.
       The duplicate directive on the root is removed once the carrier is
       found, so there is one writer per attribute. Carrier not found →
       the root's directive stays (safe fallback) and the carrier-landing
       audit reports it.
    2. **``_ensure_scope_identity``** — ``id`` / ``bz-id`` when a
       ``bz-data`` scope must survive the morph.
    3. **``_apply_universal_modifiers``** — ``classes=``, ``style=``,
       ``visible=``, ``tooltip=``, ``slots={"root"}`` and the raw
       classes, on the TRUE root whatever slot composed it.

    Why it is a function and no longer the closure's body
    -----------------------------------------------------
    A parent that **rebuilds** its children instead of calling their
    ``render()`` bypasses the metaclass wrap — and therefore the three
    passes. Measured: ``ui.toggle_button(..., classes=…, style=…,
    slots={"root": …})`` inside a ``ui.toggle_group`` lost **all three**,
    because ``ToggleGroup`` calls ``child._render_button(...)``.

    By extracting it, the "I rebuild my child" path can end at the same
    obligatory crossing as the normal path. There is ONE place that
    describes what "rendering a component" means, and both paths go
    through it.
    """
    # ⚠️ HERE, and not in `compose_class`. First attempt: the
    # validation lived in the class composer — and it covered only 17
    # components out of 57, because those whose steps are multi-slot
    # dicts resolve their size themselves and never go through that
    # branch. A partial validation is WORSE than none: it makes the
    # behaviour depend on the component. `finish_render` is the only
    # point every render goes through.
    from bretzel.components.base._wiring import refuse_a_value_off_the_table

    refuse_a_value_off_the_table(component)

    carriers = getattr(type(component), "BINDABLE_CARRIERS", None)
    if carriers:
        node = _apply_bindable_carriers(component, node, carriers)
    node = _ensure_scope_identity(component, node)
    return _apply_universal_modifiers(component, node)


def _apply_universal_modifiers(component: Component, node: Node) -> Node:
    """Apply ``classes`` / ``visible`` / ``tooltip`` modifiers to a
    freshly-rendered component node. Called by the metaclass wrap around
    every concrete component's ``render()``. Returns the (possibly
    transformed) node ; most components carry none of these so this is a
    fast no-op."""

    visible = component._visible

    # ── visible = literal False : skip the entire render ──────────────
    if visible is False:
        return FragmentNode(children=())

    # ── The colour BRIDGE: bz-c-<colour> on the true root ─────────────
    # Here and not in ``compose_class`` for the reason that already moved
    # ``classes=`` and ``slots={"root"}`` up: a component whose root is
    # composed by ANOTHER slot, or which builds its ``class=`` by hand,
    # does not go through the composer.
    from bretzel.components.base._wiring import color_bridge_class

    if (bridge := color_bridge_class(component, node)) is not None:
        node = _append_attr(node, "class", bridge)

    # ── Universal slots={"root": …} : land on the component's TRUE root ─
    # Same story as ``classes=`` below, and the last of the three to be
    # migrated here. ``slots=`` is absorbed as a universal kwarg but used
    # to be read by a SINGLE path — ``compose_class`` step 6 — so any
    # component whose root is composed by another slot, or which reads
    # ``theme["slots"]["root"]`` by hand (ToggleGroup does), dropped the
    # user's override in silence. Measured before the fix : honoured by
    # Button / Alert / Select / Tabs / Combobox, LOST by Card, TextNode, Badge,
    # Input, Heading, Divider, Sidebar, Navbar — for a mechanism that
    # ``.claude/bretzel/theme.md`` documents as public (step 5 of the
    # composition). Applied here, it reaches all of them.
    #
    # Order : the theme's own composition is already in ``class=``, the
    # override goes on top of it, and ``classes=`` goes last — so the
    # user's cosmetic classes still win, as documented. (Unknown keys are
    # rejected at ``__init__``, not here.)
    root_slot = (component._user_slots or {}).get("root")
    if root_slot and isinstance(node, Element):
        node = _append_attr(node, "class", str(root_slot))

    # ── Raw classes (``class_=`` / ``attrs={"class": …}``) ────────────
    # Same reason to be here as ``slots={"root"}`` just above: a
    # component that builds its ``class=`` by hand in ``render()`` —
    # ``attrs["class"] = " ".join(parts)``, which Card does — OVERWRITES
    # everything ``emit_attrs`` had set. Measured before this fix: a
    # ``ui.card(class_="c2", attrs={"class": "c3"})`` lost both without a
    # word.
    #
    # Applied post-render, so no component can overwrite it any more, and
    # BEFORE ``classes=``: the documented order stays "theme, then raw,
    # then the user's cosmetic classes last".
    raw_cls = component._raw_class_str
    if raw_cls and isinstance(node, Element):
        node = _append_attr(node, "class", raw_cls)

    # ── Universal classes= : land on the component's TRUE root ────────
    # The user's extra classes belong on whatever element render() chose
    # as its root, regardless of the theme slot that composed it. Applied
    # here (post-render) so EVERY component honours ``classes=`` — not
    # only those that compose their root via the "root" slot. (The static
    # ``compose_class`` no longer appends them, so there's no doubling ;
    # the reactive ``classes=ClientBinding`` path stays in
    # ``apply_class_attrs`` and leaves ``_classes`` None, so this no-ops.)
    user_cls = component._user_classes_str()
    if user_cls and isinstance(node, Element):
        node = _append_attr(node, "class", user_cls)

    # ── Universal classes=ClientBinding: same root, reactive ─────────
    # ``bz-class`` accepts a plain string and — by contract — NEVER
    # touches the statically-emitted ``class=`` (it tracks the classes it
    # adds, per bind). So the theme composition survives and the binding
    # simply layers on top.
    #
    # This lives HERE, at the universal choke point, and not in
    # ``apply_class_attrs``: only 2 of ~55 components ever called that
    # helper, so the documented "bindable on every component" contract
    # held nowhere. The old emission was ``:class="…"`` — Alpine
    # syntax the V3 runtime doesn't read at all — and it dropped the
    # static ``class=`` on the way out, leaving those 2 components
    # completely unstyled. Cf. gate
    # ``tests/consistency/test_reactive_classes_universal.py``.
    if component._classes_binding is not None and isinstance(node, Element):
        node = Element(
            tag=node.tag,
            attrs={
                **node.attrs,
                BZ_CLASS_PREFIX: Component.path_of(component._classes_binding),
            },
            children=node.children,
        )

    # ── Universal literal style= : land on the component's TRUE root ──
    # Same story as classes= : without this, the peer-input family
    # (Switch / Checkbox / Radio — emit_attrs lands on their hidden
    # ``sr-only`` <input>) buries the user's inline ``style=`` on the
    # invisible element, so it does nothing visually. ``apply_style_attr``
    # no longer stamps the literal (only the reactive ``style=ClientBinding``
    # → ``bz-attr:style``), so there's no doubling.
    user_style = component._style
    if user_style and isinstance(node, Element):
        prior = str(node.attrs.get("style", "")).rstrip().rstrip(";")
        merged_style = f"{prior}; {user_style}" if prior else str(user_style)
        node = Element(
            tag=node.tag,
            attrs={**node.attrs, "style": merged_style},
            children=node.children,
        )

    # ── visible = ClientBinding | ClientExpression : bz-show (V3) ─────
    # ``ClientExpression`` inherits from ``ClientBinding`` so a single
    # ``isinstance`` would treat compound expressions the same as a bare
    # field reference and double-prefix the JS with ``$bz.state.``,
    # corrupting the directive. Detect the expression case first and
    # emit its already-complete JS verbatim ; only the bare field path
    # gets the ``$bz.state.`` prefix. FOUC : when the binding's SSR
    # value is falsy, pre-stamp ``display:none`` so nothing flashes
    # before the runtime's first effect (.claude/bretzel/runtime.md).
    if isinstance(visible, ClientBinding):
        if isinstance(node, Element):
            new_attrs = {**node.attrs}
            new_attrs[BZ_SHOW_PREFIX] = Component.path_of(visible)
            # ``getattr(…, "value", True)`` — defensive ON PURPOSE: a
            # ClientExpression has no ``.value`` (nothing to evaluate
            # server-side), so no FOUC guard for it. An accepted limit,
            # not an oversight: there is no correct SSR value for an
            # expression computed on the client.
            if not getattr(visible, "value", True):
                stamp_display_none(new_attrs)
            node = Element(tag=node.tag, attrs=new_attrs, children=node.children)
        # FragmentNode / TextNode root : no place to hang a directive, silently
        # ignore. Rare in practice — primitive leaves like ``TextNode`` rarely
        # get a ``visible=binding`` ; users wrap them in a parent.

    # ── tooltip wrap : the wrapper was pre-built at __init__ time ─────
    # (when the render context was alive — Tooltip needs id allocation
    # there). At render-time we just inject the freshly-rendered node
    # as its trigger child and call ``.render()``. The base
    # ``_render_one`` dispatcher accepts a raw ``Node`` so the
    # pre-rendered Element drops in cleanly.
    wrapper = component._tooltip_wrapper
    if wrapper is not None:
        wrapper._children = [node]
        node = wrapper.render()

    return node


# ───────────────────────────────────────────────────────────────────────────
# Convenience re-exports
# ───────────────────────────────────────────────────────────────────────────


def el(tag: str, attrs: dict[str, Any] | None = None, children: Iterable[Any] = ()) -> Element:
    """Tiny ergonomic wrapper around :class:`bretzel.core.tree.Element`.

    Components don't have to use it — building :class:`Element` directly
    is just as good — but the helper accepts a loose iterable for
    children and auto-wraps bare strings in :class:`TextNode`, which is
    what most ``render()`` bodies want anyway.
    """
    coerced: list[Node] = []
    for c in children:
        if c is None:
            continue
        if isinstance(c, Node):
            coerced.append(c)
        elif isinstance(c, Component):
            coerced.append(c.render())
        elif isinstance(c, str):
            coerced.append(TextNode(c))
        else:
            raise TypeError(f"el(): unsupported child type {type(c).__name__}")
    return Element(tag=tag, attrs=attrs or {}, children=tuple(coerced))

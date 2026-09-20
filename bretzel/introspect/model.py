"""The introspection dataclasses — **and nothing else**.

This module contains **no logic**, deliberately. It is the *contract*: a
third-party consumer (the living documentation, a generator, an MCP
server) imports these types **in process** rather than parsing text, and
the emitters in :mod:`bretzel.introspect.emit` are only projections of
these objects. Two intended consequences:

- **text and JSON cannot diverge** — they read the same data;
- adding a field here makes it available to both at once, and
  :data:`SCHEMA_VERSION` tells the consumer that the shape has moved.

:data:`SCHEMA_VERSION` follows semantic versioning **of the dataclasses'
shape**, not the framework's: a field added → minor, a field removed or
renamed → major.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "3.0"

# How a parameter reaches the component. The distinction is
# *load-bearing*, not cosmetic: see ``_component_params`` — a component
# can remove a prop from its ``__init__`` while inheriting it as a
# reactive prop, and the call stays valid.
SOURCE_SIGNATURE = "signature"
SOURCE_REACTIVE_PROP = "reactive prop"

#: The category of a symbol nobody has classified. It exists so that
#: nothing is *lost* — the view shows the symbol anyway — while
#: ``tests/consistency/test_docs_coverage.py`` turns red, which forces a
#: maintainer to classify it **on purpose**. That is the ratchet: a
#: public surface is not widened without saying what it is for.
CATEGORY_UNCLASSIFIED = "other"


@dataclass(frozen=True)
class ParamInfo:
    """A parameter acceptable at the call site."""

    name: str
    kind: str  # "positionnel" | "keyword-only" | "*args" | "**kwargs"
    type_label: str
    default_label: str  # repr de la valeur, ou "— (requis)"
    source: str = SOURCE_SIGNATURE  # SOURCE_* ci-dessus


@dataclass(frozen=True)
class CallableInfo:
    """Any callable read from its live signature."""

    name: str
    params: tuple[ParamInfo, ...]
    doc: str | None


@dataclass(frozen=True)
class ComponentInfo:
    """A ``ui.*`` entry that is a ``Component`` subclass."""

    ui_name: str  # "button" — l'attribut sur ``ui``
    class_name: str  # "Button"
    family: str  # "actions"
    tag: str  # DEFAULT_TAG
    is_container: bool
    doc: str | None
    params: tuple[ParamInfo, ...]
    bindable: tuple[str, ...]  # BINDABLE_PROPS
    bindable_audited: bool  # False when BINDABLE_PROPS is None
    #: The subset of ``bindable`` the CLIENT writes
    #: (``reactive_prop(writes=True)`` → ``TWO_WAY_PROPS``). The funnel's
    #: matrix noted that direction by hand with ``⇄`` / ``→``; it is
    #: derivable, so it does not have to be copied.
    two_way: tuple[str, ...]
    events: tuple[str, ...]  # EVENTS (without the ``on_`` prefix)
    #: The ``on_<event>=`` actually accepted at the call site. **This is
    #: not ``events`` prefixed.** ``cross_check_events`` guarantees at
    #: class-definition time that every ``EVENTS`` has its parameter, so
    #: ``events`` ⊆ this; the reverse inclusion is FALSE.
    #:
    #: ⚠️ The example that lived here — "``table``, ``datatable``,
    #: ``bar_chart`` and ``pie_chart`` accept a click without declaring it
    #: in ``EVENTS``" — was true on 2026-08-16 and no longer is. It was
    #: not an introspection nuance but a HOLE: undeclared, those ``on_*``
    #: accepted only a callable, where every framework ``on_*`` also
    #: accepts a client expression or a list of both. Three of the four
    #: declare it since 2026-09-06 (cf. ``test_a_wired_event_is_declared``),
    #: and the fourth, ``datatable``, remains the case that justifies this
    #: field: it accepts ``on_item_click=`` without appearing in its
    #: ``EVENTS``. A consumer reading ``events`` alone would get the wrong
    #: answer, hence this field: it is computed ONCE, here.
    handler_kwargs: tuple[str, ...]
    named_slots: tuple[str, ...]  # NAMED_SLOTS
    imperative: tuple[str, ...]  # IMPERATIVE
    autoname_from: str | None  # AUTONAME_FROM
    #: The key ``Theme(components={…})`` addresses this component under —
    #: ``THEME_KEY``, **not** ``ui_name``. Eight components differ, and
    #: three of them target ANOTHER's theme: ``sidebar_section`` and
    #: ``sidebar_title`` both write under ``"sidebar"``. A consumer
    #: deriving the key from the ``ui.*`` name would be wrong about those
    #: eight. Empty when the component has no addressable theme
    #: (``fragment``, ``outlet``, ``interval``, ``meta_tag``).
    theme_key: str
    #: The theme's **vocabulary**: ``(group, keys)``, sorted. The values
    #: — the 102 components' Tailwind class strings — are NOT  count:components
    #: in it: what a reader and a lint rule need to know is which names
    #: exist, not what they render (the code is there for that).
    #:
    #: An empty ``keys`` distinguishes a **scalar** group from a table
    #: group: some groups carry a single value and not a dict
    #: (``hoverable``, ``sticky``, ``wrap``, ``palette``, ``icon_size``…).
    #: Confusing them would make one look for keys where there are none —
    #: hence invent false positives.
    #:
    #: Pairs rather than a ``dict``: everything else in this model is
    #: tuples, and a dict in a ``frozen`` dataclass stays mutable —
    #: immutability would be announced without being held.
    #: ``dict(info.theme)`` at the point of consumption.
    theme: tuple[tuple[str, tuple[str, ...]], ...]
    #: The values ``size=`` **really** accepts, nested tables absorbed.
    #: This is NOT ``dict(theme)["sizes"]``: most of the catalogue's
    #: tables nest their keys, and two opposite nestings coexist —
    #: ``Checkbox`` indexes by size (``{"sm": {<slot>}}``),
    #: ``DatePicker`` by slot (``{"input_field": {"sm"}}``). A consumer
    #: reading the raw keys would conclude that
    #: ``ui.date_picker(size="sm")`` is wrong. Resolved by
    #: ``bretzel.components.base.size_vocabulary``.
    #:
    #: Empty = "we do not know" and **never** "nothing is valid":
    #: ``radio_group`` accepts ``size=`` with no table, its ``render``
    #: makes something else of it.
    size_values: tuple[str, ...]


@dataclass(frozen=True)
class FieldInfo:
    """A field of a state class."""

    name: str
    type_label: str
    default_label: str  # "0" / "''" / "list() (factory)" / "— (required)"
    validators: tuple[str, ...]  # the @validator set on THIS field


@dataclass(frozen=True)
class StateInfo:
    """A state class — server (4 scopes) or client."""

    name: str
    family: str  # "ServerState" | "ClientState"
    scope: str  # "page/session/user/app" | persistence label
    persist: str | None
    doc: str | None
    fields: tuple[FieldInfo, ...]
    computed: tuple[str, ...]
    whole_validators: int  # how many @validator at instance level
    #: ``(field, parameter name)`` — what REALLY goes into the address.
    url_params: tuple[tuple[str, str], ...] = ()
    #: The fields the framework has NAMED, lit or not. The difference
    #: from the field above IS the information: a ``DatatableState`` names
    #: five fields and publishes none until a subclass has written
    #: ``addressable=True``.
    url_named: tuple[tuple[str, str], ...] = ()
    #: The message of a refused ``URL`` declaration. A card that kept
    #: silent about the error would read as "this state publishes
    #: nothing", which is the same output as an absent declaration.
    url_error: str | None = None


@dataclass(frozen=True)
class MethodInfo:
    """A public method read on a class."""

    name: str
    params: tuple[ParamInfo, ...]  # ``self`` dropped
    returns_label: str
    doc: str | None


@dataclass(frozen=True)
class AlgebraOp:
    """An operation of the client binding algebra, with the JS it
    **really** emits — captured by a probe, not copied."""

    name: str
    category: str  # comparison/arithmetic/logic/list/mutation/unclassified
    python: str  # how it is written — "x > y"
    js: str | None  # the emitted JS, captured at run time
    returns_label: str
    doc: str | None


@dataclass(frozen=True)
class ModuleSection:
    """The public surface of ONE framework module, classified by need.

    ``covered`` says whether the section has a written classification
    table. An uncovered module is not *absent* from the model — it is
    present and declared uncovered, which is the only honest form: a
    silently missing section reads as "this does not exist".
    """

    name: str  # "bretzel.state"
    doc: str | None
    symbols: tuple[SurfaceSymbol, ...]
    covered: bool = True


@dataclass(frozen=True)
class SurfaceSymbol:
    """A name from ``bretzel.__all__``, classified by the need it covers."""

    name: str
    category: str
    kind: str  # "class" / "function" / "decorator" / "module" / "value"
    #: The index line. **``summary`` and not ``doc``**: for a constant,
    #: it is its VALUE and not prose — ``inspect.getdoc`` returned its
    #: type's docstring there, and 46 lines of the index displayed
    #: ``str(object='') -> str``. The field was called ``doc`` when it
    #: carried only prose; changing its content without changing its name
    #: would have let a consumer read a ``repr`` as a sentence.
    summary: str | None


@dataclass(frozen=True)
class SymbolDetail:
    """The card of a public symbol that is **not** a ``ui.*``.

    :class:`ComponentInfo` answered for the components; everything else —
    ``@page``, ``PageState``, ``ClientBinding``, ``ROUTE_ACTION`` — had
    only an index line truncated at 62 characters, with no signature. An
    AI read there that ``@page`` exists, never how it is called.

    The optional fields are filled **according to the symbol's nature**,
    and their absence is information: a ``value`` has no signature, a
    function has no methods. None of them is a "to do".
    """

    name: str
    #: The module it is imported from first — the order of
    #: :data:`~bretzel.introspect.modules.SECTIONS`, so ``bretzel`` first:
    #: that is what the call site really writes.
    module: str
    #: Every module exporting it. ``page`` comes out of ``bretzel`` AND
    #: of ``bretzel.render`` — the SAME object re-exported. Keeping quiet
    #: about it would suggest two symbols, or a single legal import path.
    exported_by: tuple[str, ...]
    #: The OTHER surfaces carrying this name. ``text`` is the only case:
    #: the ``ui.text`` component and ``bretzel.render.text``, the
    #: framework's word. A field and not a note glued to the rendering —
    #: otherwise the component's card would say it and the symbol's would
    #: not, and the JSON would carry it in neither direction.
    also_known_as: tuple[str, ...]
    category: str  # the need it covers, cf. ``SurfaceSymbol``
    kind: str  # "class" / "function" / "decorator" / "value"
    doc: str | None  # the WHOLE docstring, not its first line
    #: The live signature. For a class, it is its constructor's — the
    #: card reads like the call site.
    signature: CallableInfo | None
    methods: tuple[MethodInfo, ...]  # classes only
    #: A constant's value. It IS its documentation: ``ROUTE_ACTION`` only
    #: makes sense once one reads ``'/_bz/action'``, and
    #: ``inspect.getdoc`` returned only ``str``'s docstring there.
    value_repr: str | None
    #: The Python→JS algebra, for the classes that **are** their operator
    #: surface (:class:`~bretzel.state.ClientBinding` and its children).
    #: ``describe_method_surface`` would return the same names there
    #: without the Python form nor the JS emitted, which is the useless
    #: half of the answer.
    algebra: tuple[AlgebraOp, ...]
    #: The scope and the fields, for a state class. On the five base
    #: classes it is the scope that carries the information — the only
    #: thing one wants to know about ``PageState``.
    state: StateInfo | None


@dataclass(frozen=True)
class HelperInfo:
    """A ``ui.*`` entry that is **not** a component.

    The ``ui`` namespace is deliberately heterogeneous: a keyed-iteration
    generator (``ui.each``) and a toast helper (``ui.notification``) sit
    next to ``ui.button``. We classify them by nature and read them
    honestly — a helper has neither props, nor events, nor slots, and we
    do not pretend otherwise.
    """

    ui_name: str
    kind: str  # cf. _HELPER_KINDS
    params: tuple[ParamInfo, ...]
    doc: str | None

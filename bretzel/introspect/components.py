"""The ``ui.*`` catalogue — read live, never copied.

It is the catalogue's anti-rust column: adding a prop, wiring an event,
shipping an imperative method is reflected here on the next call, with no
edit. A hand-copied API catalogue doubles ``bretzel describe``'s output,
so it drifts faster than it serves — that is the lesson of the
``bretzel-api`` skill, deleted on 2026-08-01 for naming two non-existent
components and omitting six shipped ones.

⚠️ **A component's source of truth is ``__reactive_props__`` minus
``SEALED_PROPS``, never ``inspect.signature(__init__)``.** See
:func:`_component_params`: the two possible faults — hiding a prop that
works, announcing a prop that raises — send the same reader into the
wall, and this module committed both of them on the same day.
"""

from __future__ import annotations

import inspect
from functools import cache

from bretzel.components.base import size_vocabulary
from bretzel.components.base.component import RESERVED_KWARGS
from bretzel.introspect._signature import (
    REQUIRED_LABEL,
    default_label,
    describe_callable,
    type_label,
)
from bretzel.introspect.model import (
    SOURCE_REACTIVE_PROP,
    ComponentInfo,
    HelperInfo,
    ParamInfo,
)

# ``RESERVED_KWARGS`` is a RE-EXPORT, not a copy. This list existed in
# five copies until 2026-08-16 and two had drifted; the source is now
# single, in the base layer. The universal kwargs are deliberately absent
# from the cards — repeating them on 104 entries would be noise, and the
# rule is "no universal kwargs in an API signature" (the
# ``feedback_no_universal_kwargs_in_signature`` memory). The text emitter
# announces them **once**, at the head of the index.
__all__ = ("RESERVED_KWARGS",)

# The nature of a ``ui.*`` symbol that is NOT a component.
#
# ⚠️ It was a hand-copied table of 8 names until 2026-08-16, and it had
# ALREADY drifted at birth: ``drag_each`` was missing (classified as a
# "helper" although it is in the same family as the five listed) and
# ``abort`` was a dead key (there is no ``ui.abort`` — ``abort`` lives in
# ``bretzel.server.errors``). In the module whose docstring cites the
# skill deleted for "two non-existent names, six omitted". The iteration
# family is now DERIVED from its ``__all__``.
_ITERATION_KIND = "iteration"

_DECLARED_HELPER_KINDS: dict[str, str] = {
    "notification": "fire-and-forget",
    "column": "descripteur",
}

HELPER_FALLBACK_KIND = "helper"


def helper_kind(ui_name: str) -> str:
    """The nature of a ``ui.*`` symbol that is not a component."""
    from bretzel.components.meta import iteration

    if ui_name in iteration.__all__:
        return _ITERATION_KIND
    return _DECLARED_HELPER_KINDS.get(ui_name, HELPER_FALLBACK_KIND)


def ui_symbol_names() -> tuple[str, ...]:
    """Every public ``ui.<name>`` symbol, in declaration order."""
    from bretzel.components import ui

    return tuple(n for n in vars(type(ui)) if not n.startswith("_"))


@cache
def ui_name_of_class() -> dict[type, str]:
    """Component class → its ``ui.*`` call name.

    Read from the ``ui`` namespace itself, so by IDENTITY. The
    spelling-based version (``cls.__name__.lower() == ui_name``) lived an
    hour and missed **37 names out of 48**: it recognised ``Button`` →
    ``button`` and missed ``AccordionItem`` → ``accordion_item``,
    ``DatePicker`` → ``date_picker``, everything carrying an underscore.
    A map covering only single-word names is worse than no map: it
    verifies perfectly on the example one has in mind.
    """
    from bretzel.components import ui

    return {
        value: name
        for name in ui_symbol_names()
        for value in [getattr(ui, name, None)]
        if isinstance(value, type)
    }


def _reactive_param(descriptor: object) -> ParamInfo:
    """Translate a ``ReactivePropDescriptor`` into a call parameter.

    ``kind="keyword-only"`` is exact and not approximate: the prop
    arrives through ``**kwargs`` then is routed by ``split_kwargs`` into
    the reactive-props bucket — it is never positional.

    The default is NOT read through ``resolve_default()``: that one
    *calls* the factory, and a card has no business running application
    code to display itself. The three cases therefore stay explicit.
    """
    from bretzel.components.base.reactive_prop import MISSING

    if getattr(descriptor, "default_factory", None) is not None:
        default = "<factory>"
    elif getattr(descriptor, "default", MISSING) is not MISSING:
        default = default_label(descriptor.default)
    else:
        default = REQUIRED_LABEL

    return ParamInfo(
        name=descriptor.name,
        kind="keyword-only",
        type_label=type_label(getattr(descriptor, "declared_type", None)),
        default_label=default,
        source=SOURCE_REACTIVE_PROP,
    )


def _component_params(cls: type) -> tuple[ParamInfo, ...]:
    """Everything passable at the call site, minus the universal kwargs.

    Two sources, in this order:

    1. the ``__init__``'s **explicit** parameters — they carry the
       annotation and the default the author chose, so they win;
    2. the class's **reactive props**, minus its ``SEALED_PROPS``.

    (2) is not a safety net, it is the heart of the fix. ``HStack``
    removes ``justify``/``wrap`` from its ``__init__`` to offer a reduced
    API **but inherits them from ``Flex`` as reactive props** — so
    ``ui.hstack(justify="between")`` works. Reading only the ``__init__``
    declared it unavailable, and a reader fell back on
    ``classes="justify-between"``: a workaround, exactly what this module
    exists to prevent.

    ⚠️ **Subtracting ``SEALED_PROPS`` is as load-bearing as the union.**
    The first version of this fix had only the union and committed the
    fault with the opposite sign: it announced
    ``ui.hstack(direction="col")``, which **raises** (the axis is the
    shortcut's identity). A card promising a refused parameter is as
    false as a card hiding one that works. Both directions are guarded by
    ``tests/consistency/test_introspect_sees_inherited_props.py``, which
    **additionally** checks that a sealed prop is really refused —
    otherwise ``SEALED_PROPS`` would become the shortest way of silencing
    the gate.
    """
    try:
        info = describe_callable(cls.__init__)
    except (ValueError, TypeError):
        signature_params: tuple[ParamInfo, ...] = ()
    else:
        signature_params = tuple(p for p in info.params if p.kind != "**kwargs")

    seen = {p.name for p in signature_params}
    seen.update(getattr(cls, "SEALED_PROPS", ()))
    reactive = getattr(cls, "__reactive_props__", None) or {}
    from_props = tuple(
        _reactive_param(descriptor)
        for name, descriptor in sorted(reactive.items())
        if name not in seen
    )
    return signature_params + from_props


def _handler_kwargs(params: tuple[ParamInfo, ...], events: tuple[str, ...]) -> tuple[str, ...]:
    """The ``on_<event>=`` actually accepted — cf. ``ComponentInfo``.

    The union is written in THIS direction (params first) because
    ``cross_check_events`` already guarantees ``events`` ⊆ params, at
    class-definition time: the second half should never add anything. We
    keep it anyway — it costs one line, and it is what will surface the
    day the base layer loses that guarantee, rather than losing events
    silently.
    """
    from_params = [p.name for p in params if p.name.startswith("on_")]
    return tuple(dict.fromkeys(from_params + [f"on_{e}" for e in events]))


@cache
def _theme_vocabulary(cls: type) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The names ``Theme(components={<key>: …})`` accepts for ``cls``.

    The **fifth** introspectable contract, and the last to arrive: the
    other four (``BINDABLE_PROPS``, ``EVENTS``, ``NAMED_SLOTS``,
    ``IMPERATIVE``) had been read here from the start, the theme had not
    — hence the impossibility, until 2026-08-16, of writing any rule
    saying "``crad`` is not a component" or "``rooot`` is not a slot".

    A group whose value is not a dict is **scalar** (16 measured cases):
    it is listed with zero keys, which distinguishes it from an empty
    table and avoids looking for keys where there are none.
    """
    theme = getattr(cls, "THEME", None)
    if not isinstance(theme, dict):
        return ()
    return tuple(
        # ``str(k)`` and not ``k``: a group key is not always a string.
        # ``Heading.THEME["level_sizes"]`` is indexed by the INTEGERS
        # 1..6 (``level=`` is an int, cf. ``bretzel describe``: "accepts
        # int, NOT string"). Without the coercion, this field announced
        # ``tuple[str, ...]`` while carrying ints, and
        # ``bretzel describe heading`` raised a ``TypeError`` at the
        # ``", ".join`` — shipped broken on 2026-08-16, caught the same
        # day by the gate that renders all 104 cards.
        (group, tuple(sorted(map(str, value))) if isinstance(value, dict) else ())
        for group, value in sorted(theme.items())
    )


#: The props the BASE LAYER resolves by their value, in a theme table
#: (``compose_class``). Two, no more: the other 24 table groups are read
#: by each component's ``render``, with its own prop → group
#: correspondence, which no general rule recomposes.
_VALUE_ADDRESSED: tuple[str, ...] = ("variant", "size")


def prop_vocabulary() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``variant`` / ``size`` → accepted values.

    The counterpart of :func:`theme_vocabulary`, but indexed by **prop**
    and not by theme group — because the two do not coincide: ``variant``
    does read the keys of ``variants``, whereas ``size`` requires
    resolving both nestings (cf. :attr:`ComponentInfo.size_values`).

    An empty set means "no table, we do not judge" — three components
    accept ``variant=`` with no table (``bar_chart``, ``file_upload``,
    ``pie_chart``) and ``radio_group`` does the same for ``size=``.
    """
    out: dict[str, dict[str, frozenset[str]]] = {}
    for info in describe_components():
        if not isinstance(info, ComponentInfo) or not info.theme_key:
            continue
        entry = out.setdefault(info.theme_key, {})
        variants = dict(info.theme).get("variants", ())
        entry["variant"] = entry.get("variant", frozenset()) | frozenset(variants)
        entry["size"] = entry.get("size", frozenset()) | frozenset(info.size_values)
    return out


def theme_vocabulary() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``group`` → keys — what ``Theme(components={…})``
    can name.

    Three consumers, one single derivation: the lint rule judging the
    vocabulary, the one judging ``variant=``'s values, and the startup
    validation that RAISES. The two rules each built it on their own side
    before 2026-08-16 — two copies of the same loop, hence two ways of
    ending up no longer saying what the runtime says, and it is the lint
    one would have believed.

    Indexed by ``THEME_KEY`` and not by the ``ui.*`` name: eight
    components differ, and three write under ANOTHER's key
    (``sidebar_section`` → ``sidebar``). The classes sharing a key share
    the same ``THEME`` object, so the union is unambiguous.
    """
    out: dict[str, dict[str, frozenset[str]]] = {}
    for info in describe_components():
        if not isinstance(info, ComponentInfo) or not info.theme_key:
            continue
        groups = out.setdefault(info.theme_key, {})
        for group, keys in info.theme:
            groups[group] = frozenset(keys)
    return out


def theme_shapes() -> dict[str, dict[str, dict[str, str]]]:
    """``THEME_KEY`` → group → key → ``"str"`` or ``"dict"`` — the SHAPE
    the SHIPPED theme gives each entry.

    The counterpart of :func:`theme_vocabulary`, which returns the
    *names*: here we return what those names are worth, reduced to what
    is statically decidable. An override that keeps the name and changes
    the shape is not a theme extension, it is a fault — and it is exactly
    the hole it goes through today, since ``unknown-theme-vocabulary``
    deliberately exempts the groups addressed by a value (adding a key
    there is the supported way of declaring one's own variant).

    What the shape decides, measured on 2026-09-10 on ``ui.button``:

    - writing a **dict** where the theme ships a **string** makes ALL the
      step's tokens disappear (``h-10 px-4 text-sm gap-2`` → nothing).
      The component renders bare, in 200, with valid HTML;
    - writing a **string** where it ships a **dict** raises
      ``AttributeError: 'str' object has no attribute 'get'`` at render
      time — a raise that names neither the theme, nor the component, nor
      the key.

    Only the groups that ARE tables are described: a scalar group (16
    cases, cf. :func:`_theme_vocabulary`) has no entries, hence no shape
    to compare, and it is absent rather than empty.

    ⚠️ ``str(k)`` on the keys, for the same reason as opposite:
    ``Heading.THEME["level_sizes"]`` is indexed by the INTEGERS 1..6.
    """
    from bretzel.components import ui

    out: dict[str, dict[str, dict[str, str]]] = {}
    for ui_name in sorted(ui_symbol_names()):
        cls = getattr(ui, ui_name)
        if not isinstance(cls, type):
            continue
        theme_key = getattr(cls, "THEME_KEY", "") or ""
        theme = getattr(cls, "THEME", None)
        if not theme_key or not isinstance(theme, dict):
            continue
        groups = out.setdefault(theme_key, {})
        for group, table in theme.items():
            if not isinstance(table, dict):
                continue
            entries = groups.setdefault(str(group), {})
            for key, value in table.items():
                entries[str(key)] = "dict" if isinstance(value, dict) else "str"
    return out


def describe_component(ui_name: str, cls: type) -> ComponentInfo:
    """Read a ``Component`` subclass: family, tag, parameters, and the
    FIVE introspectable contracts (``BINDABLE_PROPS`` / ``EVENTS`` /
    ``NAMED_SLOTS`` / ``IMPERATIVE`` / ``THEME``'s vocabulary) plus
    ``AUTONAME_FROM`` and ``THEME_KEY``."""
    module = getattr(cls, "__module__", "") or ""
    parts = module.split(".")
    family = parts[2] if len(parts) > 2 and parts[1] == "components" else "?"

    raw_bindable = getattr(cls, "BINDABLE_PROPS", None)
    params = _component_params(cls)
    events = tuple(getattr(cls, "EVENTS", ()) or ())

    return ComponentInfo(
        ui_name=ui_name,
        class_name=cls.__name__,
        family=family,
        tag=getattr(cls, "DEFAULT_TAG", "div"),
        is_container=bool(getattr(cls, "IS_CONTAINER", True)),
        doc=inspect.getdoc(cls),
        params=params,
        bindable=tuple(raw_bindable or ()),
        bindable_audited=raw_bindable is not None,
        two_way=tuple(getattr(cls, "TWO_WAY_PROPS", ()) or ()),
        events=events,
        handler_kwargs=_handler_kwargs(params, events),
        named_slots=tuple(getattr(cls, "NAMED_SLOTS", ()) or ()),
        imperative=tuple(getattr(cls, "IMPERATIVE", ()) or ()),
        autoname_from=getattr(cls, "AUTONAME_FROM", None),
        theme_key=getattr(cls, "THEME_KEY", "") or "",
        theme=_theme_vocabulary(cls),
        size_values=tuple(sorted(size_vocabulary(getattr(cls, "THEME", None)))),
    )


def describe_ui_symbol(ui_name: str) -> ComponentInfo | HelperInfo:
    """Classify a ``ui.<name>`` symbol and read it live.

    The components get the complete contract card; the helpers
    (each / notification / column…) a signature + docstring card.
    """
    from bretzel.components import ui
    from bretzel.components.base.component import Component

    value = getattr(ui, ui_name)
    if isinstance(value, type) and issubclass(value, Component):
        return describe_component(ui_name, value)

    try:
        info = describe_callable(value)
        params, doc = info.params, info.doc
    except (TypeError, ValueError):
        params, doc = (), None
    return HelperInfo(
        ui_name=ui_name,
        kind=helper_kind(ui_name),
        params=params,
        doc=doc,
    )


def describe_components() -> tuple[ComponentInfo | HelperInfo, ...]:
    """The whole ``ui.*`` catalogue, sorted by name."""
    return tuple(describe_ui_symbol(n) for n in sorted(ui_symbol_names()))

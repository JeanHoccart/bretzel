"""Closed values and theme lookups: a value off its table is refused, a colour reaches the root."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.core.tree import Element, Node

#: What a theme writes when it reads a STEP rather than a template.
_READS_A_STEP = "(--bz-"


#: The props read from a theme table on EVERY component, and that table —
#: even where the shipped theme has none (an app's ``Theme`` may add one,
#: and ``radio_group.size`` refuses through its children). Without ``gap``,
#: ``padding`` and ``width`` here, ``ui.grid(gap="huge")`` and its like
#: would render an invented value as the empty class, in silence.
_TABLE_AXES: tuple[tuple[str, str], ...] = (
    ("size", "sizes"), ("variant", "variants"),
    ("gap", "gaps"), ("padding", "paddings"), ("width", "widths"),
)


#: ``cls → its (prop, table) pairs``, derived once per class.
_AXES_OF: dict[type, tuple[tuple[str, str], ...]] = {}


def _plurals(prop: str) -> tuple[str, ...]:
    """The names a table of ``prop``'s values goes by: ``ratio`` →
    ``ratios``, ``status`` → ``statuses``, ``opacity`` → ``opacities``,
    ``align`` → ``aligns`` and ``alignments``: a theme key belongs to the
    ``Theme(components=…)`` API, so both spellings stay and both are read."""
    names = (prop + "s", prop + "es", prop + "ments")
    return (*names, prop[:-1] + "ies") if prop.endswith("y") else names


def table_axes(cls: type) -> tuple[tuple[str, str], ...]:
    """The (prop, table key) pairs whose value must be in a table.

    The five of ``_TABLE_AXES``, and — **derived, not listed** — every
    reactive prop whose shipped theme carries a table named after it.
    A list alone would let a new closed table slip past, and its props
    render an invented value in silence — ``ui.image(ratio="cinema")``
    would reserve no room. ``color`` is left out: its names are the palette's,
    checked by :func:`refuse_unknown_color`, and a ``colors`` group is a
    partial table of overrides, not the list of legal colours.

    A prop that declares ``reactive_prop(steps=)`` is an axis too, table or
    not: its steps ARE the table, and the key named for it goes unread.
    """
    known = _AXES_OF.get(cls)
    if known is None:
        theme = getattr(cls, "THEME", None) or {}
        derived: list[tuple[str, str]] = []
        for prop, descriptor in getattr(cls, "__reactive_props__", {}).items():
            if prop == "color" or any(prop == p for p, _ in _TABLE_AXES):
                continue
            keys = [k for k in _plurals(prop) if isinstance(theme.get(k), Mapping)]
            if not keys and getattr(descriptor, "steps", None):
                keys = [_plurals(prop)[0]]
            derived.extend((prop, key) for key in keys)
        known = _AXES_OF[cls] = (*_TABLE_AXES, *derived)
    return known


def refuse_a_value_off_the_table(component: Any) -> None:
    """``size=`` / ``variant=`` outside the table: raise, instead of
    keeping quiet.

    Without this refusal, an invented value renders anyway, and not in
    the same way on every component —

        ui.button(size="zzz")  → loses h-10, px-4, gap-2, text-sm
                                  (the button renders WITH NO SIZE)
        ui.badge(size="zzz")   → falls back on `sm`, one size lower

    A typo would not raise, would not show, and could not be seen in review.

    Yet the repository already applies this rule and writes it:
    ``bretzel describe`` says of ``ui.flex``'s ``grow=`` that the "table
    is CLOSED, and a value outside it RAISES: it would render the empty
    string, so a dead kwarg". It is the same sentence, applied to the
    catalogue's two most frequent props.

    Two abstentions, each deliberate: we only raise if the legal values
    are KNOWABLE (cf. below), and a non-``str`` value — a step dict, a
    binding — leaves here without a sound, except where ``steps=`` is the
    whole vocabulary (a list or a dict there is a fault).

    **``reactive_prop(steps=)`` comes before the table.** The theme's
    table cannot answer for everyone: ``bar_chart.variant`` and
    ``pie_chart.variant`` name a plotting mode (no table),
    ``radio_group.size`` forwards to the children (empty table), and
    ``radio.size`` does have a table but a ``None`` default — and it is
    the default that serves as the anchor for reading a nested table.
    """
    descriptors = type(component).__reactive_props__
    theme: dict[str, Any] | None = None
    for prop, table_key in table_axes(type(component)):
        value = component._reactive_values.get(prop)
        descriptor = descriptors.get(prop)
        declared = getattr(descriptor, "steps", None)
        if not isinstance(value, str):
            # A ``steps=`` list is the whole vocabulary: a list or a dict
            # there is a fault, not a graded value to pass on.
            if (declared and value is not None
                    and prop not in component._binding_metadata):
                raise ComponentUsageError(
                    f"ui.{_ui_name_for_error(component)}: {prop}={value!r} "
                    f"is not one of its values. Known values: "
                    f"{', '.join(sorted(declared))}."
                )
            continue
        if declared:
            steps = frozenset(declared)
        else:
            # The descriptor's default is the anchor ``declared_steps``
            # reads the table from, so it is in the table or the table
            # is unreadable: either way it is never refused. Most
            # instances carry their default, and resolving the theme for
            # each would weigh on the render of a long table.
            anchor = getattr(descriptor, "default", None)
            if value == anchor:
                continue
            if theme is None:
                theme = component._resolved_theme()
            steps = _steps_of(theme.get(table_key, {}), anchor)
        if not steps or value in steps:
            continue
        raise ComponentUsageError(
            f"ui.{_ui_name_for_error(component)}: {prop}={value!r} is not "
            f"one of its values. Known values: "
            f"{', '.join(sorted(steps))}.\n"
            f"  A value outside the table would not raise by itself: it "
            f"would render the empty string, so a dead kwarg — the "
            f"component would lose that step without a word. For styling "
            f"that no step covers, that is `classes=`."
        )


#: ``id(table) → (table, anchor, steps)``. Theme tables live as long as
#: the process (module constants, or ``Theme``'s memoized merges), and a
#: page reads the same few dozen, so they are computed once. The table is
#: kept in the entry so a recycled ``id`` cannot match.
_STEPS: dict[int, tuple[Mapping[str, Any], str | None, frozenset[str]]] = {}


def _steps_of(table: Mapping[str, Any], anchor: str | None) -> frozenset[str]:
    known = _STEPS.get(id(table))
    if known is not None and known[0] is table and known[1] == anchor:
        return known[2]
    steps = declared_steps(table, anchor=anchor)
    _STEPS[id(table)] = (table, anchor, steps)
    return steps


def declared_steps(
    table: Mapping[str, Any], *, anchor: str | None
) -> frozenset[str]:
    """The steps of a ``sizes`` / ``variants`` table, THREE shapes.

    The catalogue nests the table **both ways round**, and nothing in its
    structure says which: some tables are flat, and the nested ones share
    the two orders ::

        sizes = {"sm": "h-8", "md": "h-10"}                    # flat
        sizes = {"input_frame": {"md": "h-10"}}                # date_picker
        sizes = {"md": {"root": "h-10", "close": "size-4"}}    # badge

    Hence the anchor: the component's DEFAULT step, read on its
    descriptor. It is valid by construction, so the level that contains
    it is the level of the steps. No hard-coded vocabulary — otherwise a
    component that invented a step would make the list lie.

    The order cannot be guessed: read as flat, a table keyed by slot
    takes ``input_frame`` for a step and refuses the real ones.

    With no readable anchor — no declared default, or a default that
    neither level carries — we return the empty set, and the refusal
    abstains: better to say nothing than to refuse a correct value.
    """
    if not table:
        return frozenset()
    outer = frozenset(table)
    inner = frozenset(
        step
        for slot in table.values()
        if isinstance(slot, Mapping)
        for step in slot
    )
    if not inner or anchor in outer:
        return outer
    return inner if anchor in inner else frozenset()


def _ui_name_for_error(component: Any) -> str:
    """The component's ``ui.*`` name, or its class failing that."""
    key = getattr(type(component), "THEME_KEY", "") or ""
    return key or type(component).__name__


def theme_context(
component: Any, *, size_default: str = "md", color_default: str = "primary"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    """``(theme, slots, sizes, size, color)`` — render()'s preamble.

A FUNCTION and not a base-layer method: `component.py` is the crossing
point of 96 components, and `test_the_choke_point_only_shrinks` refuses
that it grow without a decision. Its place is here, beside the other
shared render primitives.

    **Twenty-six components opened their ``render()`` on the same four
    or five lines**, and they split 13 against 11 on the ORDER of two of
    them (``size`` before ``color``, or the other way round). That split
    is the proof it was copy-paste: nobody knowingly writes the same
    block in two orders. And it is what made the duplication invisible —
    two blocks that differ only in order look alike to no tool.

    The repository had already treated this pathology once, but by
    FAMILY (``overlay/_modal``, ``inputs/_picker_field``…). This preamble
    is universal, so no family covered it.

    The defaults are parameterised because they genuinely differ:
    ``ui.icon`` starts on ``color="current"``, a few components on
    another base size. Passing them explicitly keeps the behaviour
    identical to the byte.
    """
    theme = component._resolved_theme()
    return (
        theme,
        theme.get("slots", {}),
        theme.get("sizes", {}),
        component._reactive_values.get("size") or size_default,
        component._reactive_values.get("color") or color_default,
    )


def color_bridge_class(component: Any, node: Node) -> str | None:
    """The bridge class to set on the root, or ``None``.

    A coloured component carries ``bz-c-<colour>``, which installs the
    eleven steps on its subtree (cf. :mod:`bretzel.theme.bridges`). That
    is what replaces the ``{bg_color}`` substitution: the theme writes
    ``bg-(--bz-bg)``, a COMPLETE class the compiler sees, and the bridge
    says which colour it is.

    Three refusals, each for a reason:

    1. **A bridge class already set by the user.** Two ``bz-c-*`` on the
       same element are settled by the order of the SHEET and not by the
       order of the classes, so the ``classes="bz-c-error"`` escape hatch
       would win or lose at random. We leave it the floor.
    2. **A colour that is not a string** — a step dict, a binding.
       Without this refusal the base layer stringifies and sets
       ``bz-c-{'md': 'primary'}`` in the DOM.
    3. **No colour at all** — the component is not coloured.

    ⚠️ Case 2 **raises** when the theme reads a step. Not setting the
    bridge would render the component WITH NO STYLE — undefined steps, so
    invalid properties — with no error and no trace. The step dict on
    ``color`` already broke at render before the migration (cf.
    ``tests/consistency/_not_graded.txt``): raising keeps the noise where
    it was, instead of trading it for silence.
    """
    if not isinstance(node, Element):
        return None
    color = component._reactive_values.get("color")
    if color is None:
        return None

    from bretzel.theme.bridges import BRIDGE_CLASS_PREFIX, bridge_class

    root_class = str(node.attrs.get("class", ""))
    user_written = component._user_classes_str() + " " + component._raw_class_str
    if BRIDGE_CLASS_PREFIX in root_class + " " + user_written:
        return None

    if isinstance(color, str):
        refuse_unknown_color(component, color)

    if not isinstance(color, str):
        if _READS_A_STEP in root_class:
            raise ComponentUsageError(
                f"{type(component).__name__}(color={color!r}): the colour "
                "must be a name, not a "
                f"{type(color).__name__}.\n"
                "  This component paints itself with STEPS "
                "(``bg-(--bz-bg)``…), which are set by its colour's bridge "
                "class. With no colour name there is no bridge, so no "
                "steps, so a component rendered WITH NO STYLE.\n"
                "  ``color=`` does not take breakpoint steps: one colour "
                "per breakpoint makes no sense here."
            )
        return None
    return bridge_class(color)


def root_color_bridge(component: Any, node: Any) -> str | None:
    """The bridge class for the component's ROOT, or ``None``.

    A component whose colour belongs to its teleported panel alone says so
    with ``_COLOR_ON_ROOT = False``: the Tooltip's root encloses a FOREIGN
    trigger, and its ``bz-c-text`` there would turn a selected toggle
    button black instead of its group's primary. The panel still gets the
    bridge, from ``teleport_to_body(panel, owner)``.
    """
    if not getattr(component, "_COLOR_ON_ROOT", True):
        return None
    return color_bridge_class(component, node)


def refuse_unknown_color(component: Any, color: str) -> None:
    """Raise if ``color`` has no bridge — so no steps.

    ⚠️ Without this refusal, ``ui.badge(color="neutral")`` builds, renders
    and ``bretzel check`` says nothing: ``bz-c-neutral`` is a class with
    no rule, so the twelve steps are undefined, so every declaration that
    reads them is invalid. The component renders bare, with no error. The
    refusal lives here because this is where the colour name is consumed.

    Outside a render context (a bench, a unit test) we cannot read the
    palette: we keep quiet rather than refuse wrongly.
    """
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    theme = getattr(getattr(ctx, "app", None), "theme", None)
    getter = getattr(theme, "get_palette", None)
    if not callable(getter):
        return

    from bretzel.theme.bridges import bridged_color_names

    known = bridged_color_names(getter())
    if color in known:
        return
    raise ComponentUsageError(
        f"{type(component).__name__}(color={color!r}): unknown colour.\n"
        f"  The available colours are {sorted(known)}.\n"
        "  A colour outside that list has no bridge class, so no steps: "
        "the component would render WITH NO STYLE, with no error and no "
        "trace — and only in production, because the dev compiler scans "
        "the live DOM.\n"
        "  To add a brand colour: "
        '``Theme(palette={"brand": "#..."})``.'
    )

"""``Flex`` — generic CSS-flex container (Archetype 2).

The component is intentionally light : it owns the *axis-agnostic* API
(direction / align / justify / gap / wrap / grow) ; the convenience subclasses
(:class:`VStack`, :class:`HStack`) bake one direction in and expose a
smaller surface for the most common cases.

``direction`` and ``gap`` are **graded** props, so they take the same
``{breakpoint: value}`` dict as :class:`Grid`'s ``cols`` ::

    ui.flex(direction={"base": "col", "md": "row"}, gap={"base": "sm", "md": "lg"})

which is THE canonical "side by side on desktop, stacked on mobile".
``align`` / ``justify`` / ``wrap`` stay scalar — they are not graded, and
a second way to express a binary choice would duplicate ``Screen``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
    responsive_classes,
)
from bretzel.components.layout.flex.theme import FLEX_THEME
from bretzel.core.tree import Element

# Props whose value may be a ``{breakpoint: value}`` dict. Graded only :
# more than two useful steps. Cf. ``base/responsive.py``.
RESPONSIVE_PROPS = frozenset({"direction", "gap"})



class Flex(Component):
    """A flex container with the full Tailwind axis API exposed.

    Children are added via the ordinary ``with`` block ; layout props
    map 1-to-1 onto Tailwind utilities through the theme dict.
    """

    THEME: ClassVar[dict[str, Any]] = FLEX_THEME
    THEME_KEY: ClassVar[str] = "flex"
    # Inherited by VStack / HStack via MRO.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    #: Prop → theme group, for the family's six props.
    #:
    #: Written once and READ by the render, rather than repeated in every
    #: place that needs it. What made it necessary: ``ui.pane`` and
    #: ``ui.viewport`` each have their own ``THEME``, self-sufficient by
    #: the repository's convention — so a group forgotten in one of the
    #: copies renders the empty string, and the prop becomes a DEAD kwarg
    #: on that component only. No error, no trace: it is exactly the
    #: repository's dominant failure mode.
    #:
    #: The ``test_a_flex_family_declares_every_table`` gate reads this
    #: table and requires the group in every theme of the family, unless
    #: the prop is in ``SEALED_PROPS`` (``ui.pane`` seals ``wrap``).
    THEME_TABLES: ClassVar[dict[str, str]] = {
        "direction": "directions",
        "align": "alignments",
        "justify": "justifies",
        "gap": "gaps",
        "wrap": "wrap",
        "grow": "grows",
    }

    #: The tables ``RESPONSIVE_PROPS`` goes through — so those whose
    #: classes can come out prefixed (``md:flex-row``, ``md:gap-6``),
    #: which the safelist must cover.
    #:
    #: DERIVED since 2026-08-25. It was written by hand, with the reason
    #: that "the prop → table correspondence lives in
    #: ``_compose_classes``'s tuple, which is not readable from the
    #: safelist" — that tuple no longer exists, it is ``THEME_TABLES``,
    #: and it is readable. Sorted so the order does not depend on a
    #: ``frozenset``'s.
    #: ⚠️ ``map`` and not a generator: in a CLASS BODY, a comprehension
    #: opens its own scope and does not see the class's names there —
    #: ``THEME_TABLES`` would raise a ``NameError``. ``map``'s arguments,
    #: for their part, are evaluated in the class's scope.
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = tuple(
        sorted(map(THEME_TABLES.__getitem__, RESPONSIVE_PROPS))
    )
    #: The SAME list, seen as prop names — it is the one the base layer
    #: reads to refuse a step dict elsewhere. The module owns it (the
    #: render uses it at line 308); the class exposes it.
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = RESPONSIVE_PROPS

    # Pure layout cosmetic props — kept off the DOM via emit_attr=False.
    # ``direction`` / ``gap`` are ``Any`` because they also take a
    # breakpoint dict ; the scalar-only ones keep their narrow annotation.
    direction: Any = reactive_prop(default="row", emit_attr=False)
    align: str = reactive_prop(default="stretch", emit_attr=False)
    justify: str = reactive_prop(default="start", emit_attr=False)
    gap: Any = reactive_prop(default="md", emit_attr=False)
    wrap: bool = reactive_prop(default=False, emit_attr=False)
    #: How the direct children share the MAIN axis — the width in a row,
    #: the height in a column. ``None`` by default, and it is
    #: load-bearing: a stack that asks for nothing emits no extra class.
    #:
    #: The gap it closes (finding [30]): every control's root carries
    #: ``w-full``, and it is the right convention — a field fills its
    #: column. But in a ``wrap=True``, an item whose basis is 100 % can
    #: **never** share its line, so the bar becomes a STACK. Measured in
    #: Chromium on 2026-08-25, two fields in 860 px: 860 px each and a
    #: 148 px bar, against 422 px each and 66 px with ``grow="16rem"``.
    #: Three apps carried the same patch at the call site
    #: (``BAR_FIELD = "basis-64 grow"``).
    #:
    #: It is the PARENT that distributes, through the ``*:`` variant
    #: ("direct children"): none of the 99 components needs to know it is
    #: inside one, so it works with the 46 that declare no width.
    #:
    #: ``*:`` and not the bracketed form ``ui.pane`` writes
    #: (``[&>*]:shrink-0``): both say the same thing, but this one
    #: escapes in the HTML (``[&amp;&gt;*]:``), so 18 characters on the
    #: wire instead of 10 — and it is a NAMED Tailwind variant, not an
    #: arbitrary one, so the simplest case for the scanner. The pane
    #: keeps the other spelling for now: it is cited by a documentation
    #: gate and by three benches (cf. ``work/todo.md``).
    grow: Any = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        direction: str | dict | None = None,
        align: str | None = None,
        justify: str | None = None,
        gap: str | dict | None = None,
        wrap: bool | None = None,
        grow: bool | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive ``None`` kwargs
        # (keeps the descriptor's default). Load-bearing case preserved:
        # VStack/HStack do NOT pass ``direction`` → it arrives ``None``
        # here → the base layer drops it → their CLASS default (``col`` /
        # ``row``) wins, exactly what the old ``if direction is not
        # None`` guard protected.
        super().__init__(
            direction=direction,
            align=align,
            justify=justify,
            gap=gap,
            wrap=wrap,
            grow=grow,
            **kwargs,
        )
        # ``grow=`` is validated HERE, not at render, and it is
        # measurable: a raise from ``_compose_classes`` gives a stack
        # with NO frame of the caller (``wrapped_render → render →
        # _compose_classes``), so it names the accepted values without
        # saying which of the page's N ``grow=`` is at fault. The base
        # layer says it in black and white (``ComponentUsageError``:
        # *raised at instantiation time*), 18 refusals in the catalogue
        # do it, and ``_reject_unknown_slot_keys`` solves the same
        # problem the same way — ``_resolved_theme()`` is readable from
        # ``__init__``.
        #
        # After ``super()`` necessarily: it is what fills
        # ``_reactive_values``. Same constraint, same comment, as
        # ``Resizable.__init__`` for its ``orientation``.
        resolved = self._reactive_values.get("grow")
        if resolved:
            # Result thrown away: we only want the raise. The render
            # will redo the lookup — a dict `.get`, and it can no longer
            # fail.
            self._grow_class(resolved, self._grow_table())

        # ⚠️ ``grow``'s FIVE SISTERS, aligned on 2026-08-29.
        #
        # They did ``table.get(value, "")``: ``align="stretchy"``
        # rendered an EMPTY class, with no error, no warning, and
        # perfectly valid HTML. That is the dead kwarg, this
        # repository's dominant failure mode — and ``grow`` already
        # refused, which left TWO mechanisms for one class of error in a
        # single method (charter principle 4).
        #
        # Preliminary sweep, 2026-08-29: **2,366 literal passes** in
        # `bretzel/`, `examples/` and `tests/`, and **2 out-of-table
        # values**, both the ``gap="2xs"`` of
        # `examples/playground/features/dnd.py` — a step that never
        # existed, so two stacks with no gutter since day one. Fixed in
        # the same commit. The behaviour change breaks nothing else.
        for prop in ("direction", "align", "justify", "gap"):
            value = self._reactive_values.get(prop)
            if value:
                self._table_class(prop, value, self._table_of(prop))

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        cls_string = self._compose_classes()
        attrs = self.emit_attrs()
        if cls_string:
            attrs = {**attrs, "class": cls_string}
        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )

    # ── Class composition ──────────────────────────────────────────────

    def _table_of(self, prop: str) -> dict[str, str]:
        """``prop``'s theme table, user override included.

        Same reason as :meth:`_grow_table`: ``__init__`` validates and
        ``_compose_classes`` resolves, and the two must look at exactly
        the same table — otherwise a ``Theme(components=…)`` would make
        validation pass and render something else.
        """
        return self._resolved_theme().get(self.THEME_TABLES[prop], {})

    @staticmethod
    def _table_class(prop: str, value: Any, table: dict[str, str]) -> str:
        """``prop``'s class, or a raise that NAMES the values.

        A breakpoint dict is validated step by step: it is each entry's
        VALUE that must be in the table, not the key (which is a
        breakpoint name, ``responsive_classes``'s responsibility).
        """
        if isinstance(value, dict):
            for breakpoint_value in value.values():
                Flex._table_class(prop, breakpoint_value, table)
            return ""
        entry = table.get(value)
        if entry is None:
            accepted = ", ".join(repr(k) for k in table)
            raise ComponentUsageError(
                f"{prop}={value!r} is not a known value. Accepted "
                f"values: {accepted}.\n"
                f"  Without this refusal, the call would render an EMPTY "
                f"class — valid HTML, no error, and the property simply "
                f"absent. For a value outside the table, write it at the "
                f"call site with ``classes=``."
            )
        return entry

    def _grow_table(self) -> dict[str, str]:
        """THIS component's ``grows`` table, user override included.

        One method and not two reads: ``__init__`` validates and
        ``_compose_classes`` resolves, and the two must look at exactly
        the same table — otherwise a ``Theme(components=…)`` would make
        validation pass and render something else.
        """
        return self._resolved_theme().get(self.THEME_TABLES["grow"], {})

    @staticmethod
    def _grow_class(grow: Any, table: dict[str, str]) -> str:
        """``grow=``'s class, or a raise that NAMES the values.

        A value outside the table would render the empty string — so a
        call that does nothing, with valid HTML and a bar that stays
        stacked. It is the repository's dominant failure mode (the dead
        kwarg), and there is no reason to carry it over onto a new prop.

        ``True`` is an alias of ``"equal"`` and not a fifth key: the
        table would otherwise be indexed by mixed types, and
        ``bretzel describe flex`` would show ``True`` among three
        lengths.
        """
        # No refusal of the dict here: the base layer did it at
        # construction (``reject_stray_breakpoints``), and its message
        # names the component in addition to the prop.
        key = "equal" if grow is True else grow
        entry = table.get(key)
        if entry is None:
            accepted = ", ".join(repr(k) for k in table)
            raise ComponentUsageError(
                f"grow={key!r} is not a known basis. Accepted values: "
                f"{accepted} (``grow=True`` means 'equal'). The table is "
                f"closed so that every class is WHOLE, hence visible to the "
                f"production Tailwind compiler; for another basis, write it "
                f"at the call site with classes=."
            )
        return entry

    def _compose_classes(self) -> str:
        """Six props, six theme groups (``THEME_TABLES``) — all too
        axis-specific for the base layer's variant/size path. We pull the
        theme and the user classes through the base layer's helpers, and
        apply Flex's own lookups in between.

        Four go through the loop. ``wrap`` is a boolean (its group is a
        string, not a table) and ``grow`` refuses an out-of-table value
        instead of rendering the empty string: two separate branches, for
        two different reasons.
        """
        theme = self._resolved_theme()
        parts: list[str] = []

        root = theme.get("slots", {}).get("root")
        if root:
            parts.append(root)

        for prop in ("direction", "align", "justify", "gap"):
            table_key = self.THEME_TABLES[prop]
            value = self._reactive_values.get(prop)
            if not value:
                continue
            table = theme.get(table_key, {})
            if prop in RESPONSIVE_PROPS:
                # ``_t=table`` binds this iteration's table — a bare closure
                # would read the loop variable after it moved on.
                entry = responsive_classes(value, lambda v, _t=table: _t.get(v, ""))
            else:
                # No refusal here: the base layer already did it at
                # construction, with the component's name in addition.
                entry = table.get(value, "")
            if entry:
                parts.append(entry)

        if self._reactive_values.get("wrap"):
            wrap_class = theme.get(self.THEME_TABLES["wrap"])
            if wrap_class:
                parts.append(wrap_class)

        grow = self._reactive_values.get("grow")
        if grow:
            # Can no longer raise: ``__init__`` has already refused the
            # unknown.
            parts.append(self._grow_class(grow, self._grow_table()))

        # User classes set by the ``_apply_universal_modifiers`` wrap on
        # the real root — do not re-append here (a "X X" duplicate,
        # inherited by VStack/HStack). Guarded by
        # test_no_manual_user_class_append.py.

        return " ".join(p for p in parts if p).strip()

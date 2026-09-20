"""``Resizable`` — panels separated by handles you drag.

Usage ::

    with ui.resizable():
        with ui.resizable_panel(min_size=15):
            ui.sidebar_nav()
        with ui.resizable_panel():
            ui.datatable(...)

    # The sizes live wherever the app wants them to live:
    class Layout(ClientState, persist="local"):
        split: list = field(default_factory=lambda: [25, 75])

    with ui.resizable(sizes=layout.split, orientation="vertical"):
        ...

**A single component under this name, and it is the split pane.** The
ecosystem's other "resizable" — a box with a corner grip, freely resized
in pixels — is not here: the browser does it natively with ``resize:
both``, so a component would add nothing but an API to maintain
(decision 2026-08-13, cf. the roadmap).

**Every direct child IS a panel**, as every direct child of a
:class:`Carousel` is a slide. ``ui.resizable_panel`` is not a toll gate:
it is the opt-in that lets you constrain one with ``min_size``. A bare
child gets the same box, with a minimum of zero — so a ``@refreshable``
or a ``ui.fragment`` composes without ceremony.

**The split lives in ``sizes``, a list of weights.** One weight per
panel, in render order; the browser shares them pro rata, so ``[1, 3]``
and ``[25, 75]`` give the same thing. The list is **normalised to 100 on
both sides** — and that is not cosmetic: ``min_size`` is in percentage
points, so raw weights on one side and percentage minimums on the other
freeze the handle without reporting anything. The two normalisations are
gated against each other by
``tests/runtime_js/test_resizable_mirrors_python.py``.

**There is no ``default_size=`` on the panel**, and that is a choice:
``sizes=`` on the group already says the initial split, and two ways of
stating it would contradict each other as soon as you write both
(charter principle 4). The panel carries **CONSTRAINTS**, not a value —
``min_size``, ``max_size``, ``collapsible``: an orthogonal axis, so no
overlap.

**``gap=`` belongs to the GROUP**, and it is the only possible place. A
padding set on an ancestor does reach the group — measured on 2026-08-23
on the CRM shell, parent at ``p-8``: the panel started at x=32, not at 0.
But no ancestor padding can create space **inside**, between a panel and
the handle; only the panels' parent knows where it is. The scale is that
of ``ui.flex`` / ``ui.hstack`` / ``ui.grid``, step for step, and the
agreement of the tables is gated by
``test_a_flex_container_spaces_its_children``.

The gutter is **transparent to the gesture**: the pixel → weight
conversion sums PANEL widths (``totalPx``) and never assumed they filled
the container. Measured: +100 px of mouse give +100 px of panel, with
gutter and without.

**Persistence: nothing to declare here.** ``sizes`` accepts a
:class:`ClientBinding`, so a ``ClientState(persist="local")`` makes the
split survive F5 without one more prop. And there is **no flash** to
correct: the root carries a ``bz-data``, so it stays
``visibility:hidden`` until ``html.bz-ready`` (``render/shell.py``
§ ``_ANTI_FLASH_STYLE``), and the runtime's boot hydrates the store from
localStorage BEFORE the scan that sets the sizes — measured in
``00_index.js`` (register → scan → ``.bz-ready``). A pre-paint script
like ``ColorScheme``'s would be a second mechanism for a problem the
first already solves.

**The gesture** is Pointer Events with capture, like :class:`Slider` —
the *pointer-drag* family, not node-DnD (the roadmap insists: the two get
confused and it costs). It redistributes only the PAIR flanking the
dragged handle, so the other panels do not move. The keyboard does the
same work in steps of 2 points (the ARIA *window splitter* pattern): a
handle that only obeys the pointer is unusable without a mouse.

Nothing is published during the gesture — only on release. Publishing
every frame would send one ``change`` per pixel to the server and write
localStorage a hundred times a second.

**Collapsing a panel**: ``ui.resizable_panel(collapsible=True)``, then
double-click on the handle — or ``Enter`` when it has focus, because a
mouse gesture with no keyboard twin does not exist for half the people.
The collapse **overrides ``min_size``**: the minimum says "do not shrink
me by dragging", the collapse says "put it away". Without that way out, a
minimum would make collapsing impossible and a second vocabulary would be
needed for the same intent. Replaying the gesture restores the previous
size.

It is declarative and not imperative, unlike the overlays: collapsing
comes down to writing ``sizes``, so it goes through the channel that
already carries the value. A ``.collapse()`` would have been a second way
of changing the same thing (principle 4).

Imperative API : ``.set([30, 70])`` / ``.reset()`` (back to an equal
split).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    hidden_carrier_attrs,
    pop_change_handler,
    server_sync_marker,
    unwrap_transparent,
)
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.responsive import responsive_classes
from bretzel.components.layout.resizable.theme import (
    RESIZABLE_PANEL_THEME,
    RESIZABLE_THEME,
)
from bretzel.core.tree import Element, Node
from bretzel.render import text

#: A group's two axes. ``horizontal`` = panels side by side.
ORIENTATIONS: tuple[str, ...] = ("horizontal", "vertical")


def normalize_weights(raw: Any, count: int) -> list[float]:
    """Raw ``sizes`` → ``count`` percentages summing to 100.

    ⚠️ **The mirror of ``_weights()`` in ``_src/20_resizable.js``**, and
    the two must agree: the server sets the first paint's styles, the
    runtime sets them again on every tick. A divergence would show as a
    layout jump at hydration, without any render test failing.

    A list of the WRONG length does not raise, it is completed in equal
    parts. That is deliberate: when the panels come from data (``for x in
    items:``), their number changes without the value persisted in
    localStorage knowing it — raising would crash the page on a state
    three days old.

    An absurd entry (negative, ``None``, non-numeric) also falls back to
    an equal part, panel by panel: that is what guarantees a panel never
    DISAPPEARS because of a broken value.
    """
    if count <= 0:
        return []
    share = 100.0 / count
    # The shape test is hoisted OUT of the loop: it does not depend on
    # the index, and a string is a ``Sequence`` — hence the explicit
    # exclusion, without which ``sizes="50,50"`` would be read character
    # by character instead of being rejected to the fallback.
    seq: Sequence[Any] = (
        raw
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
        else ()
    )
    values: list[float] = []
    for index in range(count):
        candidate: Any = seq[index] if index < len(seq) else None
        try:
            weight = float(candidate)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            weight = share
        values.append(weight if weight >= 0 else share)

    total = sum(values)
    if total <= 0:
        return [round(share, 2) for _ in range(count)]
    return [round(value * 100.0 / total, 2) for value in values]


def _num(value: float) -> str:
    """A weight → its shortest form (``25`` and not ``25.0``).

    ``json.dumps`` renders ``25.0`` for every integral float, and that
    ``.0`` goes into the ``bz-data`` AND into EVERY panel's ``style``. It
    is not wrong — just unreadable in the inspector, which is precisely
    where one goes to read these values when something is off.
    """
    return str(int(value)) if float(value).is_integer() else str(value)


def _num_list(values: Sequence[float]) -> str:
    """The JSON list of weights, without the ``.0``."""
    return "[" + ", ".join(_num(v) for v in values) + "]"


class ResizablePanel(Component):
    """Render one panel inside a resizable group."""

    THEME: ClassVar[dict[str, Any]] = RESIZABLE_PANEL_THEME
    THEME_KEY: ClassVar[str] = "resizable_panel"
    # ``min_size`` is a design constraint: it only changes on a server
    # re-render, so no client-side driver (cf.
    # client-reactive-surface.md § The rule).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    min_size: float = reactive_prop(default=0.0, emit_attr=False)
    #: ``100`` means "no ceiling" — the neutral value, not a sentinel: a
    #: panel that can take 100 % is not bounded.
    max_size: float = reactive_prop(default=100.0, emit_attr=False)
    collapsible: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        min_size: float | None = None,
        max_size: float | None = None,
        collapsible: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            min_size=min_size,
            max_size=max_size,
            collapsible=collapsible,
            **kwargs,
        )

    def render(self) -> Element:
        attrs = self.emit_attrs()
        return Element(
            tag=self._tag, attrs=attrs, children=tuple(self._render_children())
        )

    def _render_in_group(self, chrome: dict[str, Any]) -> Element:
        """Render itself WITH the box the group imposes on it.

        It is the panel that composes its own node, not the group that
        rewrites after the fact the one it has just received. Five
        precedents in the repository (``Step._render_in_stepper``,
        ``StepPanel._render_panel``, ``Tab._render_button``,
        ``TabPanel._render_panel``, ``ToggleButton._render_button``): the
        parent composes the classes, the child builds the Element.

        The post-render surgery that was written here before carried a
        real defect, not merely a matter of taste: it indexed a list of
        ``id`` by the loop rank while only filling it for the children
        actually rendered, so a skipped child shifted every following
        ``aria-controls``.
        """
        attrs = self.emit_attrs()
        own_class = attrs.get("class")
        own_id = attrs.get("id")
        attrs.update(chrome)
        # An explicit ``id=`` from the caller beats the one the group
        # offers: it is THEIR identifier, they may have written it to
        # address it from elsewhere.
        if own_id:
            attrs["id"] = own_id
        # The GROUP's class first, the user's second — not because the
        # order of the string would decide anything (Tailwind orders
        # canonically in the sheet, cf. components.md), but to read it
        # the way it is written: the imposed box, then what the caller
        # added.
        if own_class:
            attrs["class"] = f"{chrome['class']} {own_class}"
        return Element(
            tag=self._tag, attrs=attrs, children=tuple(self._render_children())
        )


class Resizable(Component):
    """Render a group of panels separated by resize handles."""

    THEME: ClassVar[dict[str, Any]] = RESIZABLE_THEME
    THEME_KEY: ClassVar[str] = "resizable"
    #: The group's only graded prop, and the table it goes through — so
    #: the only one whose classes can come out as ``md:gap-6``. Written
    #: and not inferred: the prop → table correspondence is what the
    #: production safelist must know.
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = frozenset({"gap"})
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = ("gaps",)
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("sizes",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "reset")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    sizes: Any = reactive_prop(
        default=None,
        emit_attr=False,
        writes=True,
        names_field=True,
    )
    orientation: str = reactive_prop(default="horizontal", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    #: ``Any`` and not ``str``: as with :class:`~bretzel.components.layout.flex.Flex`,
    #: the value accepts a breakpoint dict
    #: (``gap={"base": "sm", "md": "lg"}``). A ``gap`` that looked like
    #: the others without having their graded shape would be a
    #: second-class citizen — exactly the inconsistency the prop removes.
    gap: Any = reactive_prop(default="none", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        sizes: Any = None,
        orientation: str | None = None,
        gap: str | dict | None = None,
        disabled: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs.
        super().__init__(
            sizes=sizes,
            orientation=orientation,
            gap=gap,
            disabled=disabled,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )
        # ⚠️ AFTER ``super()``, never before. Testing ``orientation not
        # in ORIENTATIONS`` on the RAW kwarg evaluates a
        # ``ClientBinding`` in a boolean context if the caller passes one
        # — and that raises a ``ReactivityError`` about reactivity
        # instead of the "non-bindable prop" ``ComponentUsageError`` the
        # universal contract promises. The base layer does that check; we
        # then read the value it resolved, which is necessarily a
        # literal.
        resolved = self._reactive_values.get("orientation")
        if resolved not in ORIENTATIONS:
            raise ComponentUsageError(
                f"ui.resizable(orientation={resolved!r}) — attendu "
                f"{' ou '.join(repr(o) for o in ORIENTATIONS)}."
            )

    # ── Imperative API ─────────────────────────────────────────────────

    def set(self, sizes: Sequence[float]) -> str:
        """Impose a split. Write-through binding if there is one."""
        return self._value_command(
            [float(w) for w in sizes], prop="sizes", event="bz-set"
        )

    def reset(self) -> str:
        """Back to the equal split.

        Always the dispatch, binding or not: the equal share depends on
        the NUMBER of live panels, which the server no longer knows after
        a morph that added some (same reason as ``Carousel.next()``,
        whose destination depends on the geometry of the moment).
        """
        return self._dispatch_command("bz-reset")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        size_table = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = size_table.get(size_key, size_table.get("md", {}))
        orientation = self._reactive_values.get("orientation") or "horizontal"
        vertical = orientation == "vertical"
        axis = "v" if vertical else "h"
        disabled = bool(self._reactive_values.get("disabled"))

        # ── Binding de ``sizes`` ─────────────────────────────────────
        sizes_binding = self._binding_metadata.get("sizes")
        scope_key = self._scope_keys("sizes")[0]
        binding_path = (
            self.path_of(sizes_binding) if sizes_binding is not None else None
        )
        sizes_expr = binding_path or scope_key

        # ── The panels ───────────────────────────────────────────────
        # **Every direct child IS a panel**, as every direct child of a
        # Carousel is a slide. ``ui.resizable_panel`` is not a toll gate:
        # it is the opt-in that lets you give one of them a
        # ``min_size``. A bare child gets the same box, with a minimum of
        # zero.
        #
        # The version that RAISED on a foreign child was removed the same
        # day, measured: it made ``ui.resizable`` incompatible with
        # ``@refreshable`` and ``ui.fragment``, whose nodes attach to the
        # current parent like any component. The error message then cited
        # ``_RefreshableSection``, an internal class the caller never
        # typed. No other container in the repository refuses its
        # children (Tabs, Stepper, Accordion, ToggleGroup, Sidebar all
        # let them through) — and once the box is set by the group, the
        # objection falls by itself: a wrapped child IS a ``basis-0``.
        # ``unwrap_transparent``: a WRAPPED panel — a ``@refreshable``
        # zone, a ``ui.fragment`` — is not an instance of
        # ``ResizablePanel``, so it lost its THREE constraints in
        # silence. Measured on 2026-08-23: ``_mins`` went from ``[25, 0]``
        # to ``[0, 0]``, and ``max_size`` / ``collapsible`` with it.
        unwrapped = [unwrap_transparent(c) for c in self._children]
        panels = [c for c, _ in unwrapped]
        rewraps = [r for _, r in unwrapped]
        weights = normalize_weights(
            self._reactive_values.get("sizes"), len(panels)
        )
        # The three constraints, read panel by panel. A bare child (not
        # a ``ResizablePanel``) gets the neutral values: that is what
        # lets a ``@refreshable`` or a ``ui.fragment`` compose without
        # ceremony, cf. the group's docstring.
        mins = [
            max(0.0, float(p._reactive_values.get("min_size") or 0.0))
            if isinstance(p, ResizablePanel)
            else 0.0
            for p in panels
        ]
        maxs = [
            min(100.0, float(p._reactive_values.get("max_size") or 100.0))
            if isinstance(p, ResizablePanel)
            else 100.0
            for p in panels
        ]
        foldable = [
            bool(p._reactive_values.get("collapsible"))
            if isinstance(p, ResizablePanel)
            else False
            for p in panels
        ]
        for index, (lo, hi) in enumerate(zip(mins, maxs, strict=True)):
            if lo > hi:
                raise ComponentUsageError(
                    f"ui.resizable_panel n°{index + 1} : min_size={lo} > "
                    f"max_size={hi}. The panel could take no size at "
                    f"all, and the handle would freeze without reporting "
                    f"anything."
                )

        # The three class strings are composed ONCE: nothing in
        # ``handle``/``grip`` depends on the index, and each
        # ``slot_class`` is a full theme resolution (contextvar + palette
        # substitution). Composed inside the loop, a five-panel group
        # resolved sixteen where four are enough — it is the same hoist
        # as ``panel_class``, which already had it.
        panel_class = self.slot_class("panel")
        handle_class = self.slot_class(
            "handle",
            self.slot_class(f"handle_{axis}"),
            self.slot_class(
                "handle_locked" if disabled else "handle_active"
            ),
            size_cfg.get(f"bar_{axis}", ""),
        )
        grip_class = self.slot_class("grip", size_cfg.get(f"grip_{axis}", ""))
        children: list[Node] = []

        for index, panel in enumerate(panels):
            # The ARIA "window splitter" pattern wants the handle to
            # DESIGNATE the panel it resizes. A panel only emits an
            # ``id`` if it needs one otherwise, so the group offers it
            # one — derived from its own, so stable from one render to
            # the next and unique by construction. An explicit ``id=``
            # from the caller wins (``setdefault`` on the panel side).
            panel_id = f"{self.id}_panel_{index}"
            # THE box, composed once and served to both paths: a
            # ``resizable_panel`` receives it and renders WITH it (it can
            # add its own attributes), a foreign child is WRAPPED in it.
            # A single dict, so the two paths cannot diverge.
            chrome: dict[str, Any] = {
                "class": panel_class,
                "data-bz-rz-panel": "",
                "id": panel_id,
                # The weight as an inline style, from the SSR onwards:
                # the layout is right at the first paint, before the
                # runtime takes over. A continuous value cannot go
                # through a class (none would exist in the compiled CSS —
                # memory ``project_assembled_tailwind_class_dev_only``).
                "style": f"flex-grow:{_num(weights[index])}",
            }
            if isinstance(panel, ResizablePanel):
                node = panel._render_in_group(chrome)
            else:
                node = Element(
                    tag="div",
                    attrs=chrome,
                    children=(self._render_one(panel),),
                )
            # The zone takes its ``bz-id`` back on the composed node:
            # without that the panel would display and never refresh.
            node = rewraps[index](node)
            children.append(node)
            # The ``id`` is RE-READ on the rendered node, not assumed: a
            # panel the caller passed an ``id=`` to keeps its own, and
            # ``aria-controls`` must designate the one that exists.
            # Inferring it on both sides is how the pair falls out of
            # step.
            panel_id = str(node.attrs.get("id") or panel_id)

            if index < len(panels) - 1:
                children.append(
                    self._handle(
                        index=index,
                        handle_class=handle_class,
                        grip_class=grip_class,
                        disabled=disabled,
                        value=weights[index],
                        controls=panel_id,
                        vertical=vertical,
                        # The handle puts away the collapsible panel it
                        # touches. The LEFT one wins when both are: it is
                        # the one its ``aria-controls`` already
                        # designates, so the gesture and the
                        # announcement speak of the same panel.
                        fold_target=(
                            index
                            if foldable[index]
                            else index + 1
                            if foldable[index + 1]
                            else None
                        ),
                    )
                )

        # ── Hidden input — form data + source of the ``change`` ──────
        root_attrs = self.emit_attrs()
        relocated = pop_change_handler(root_attrs)
        # ``JSON.stringify`` and not the bare list: an input's value is
        # a string, and that is also what ``change_emit_effect`` compares
        # to decide that something changed (the ``Accordion`` multiple
        # idiom).
        carrier_expr = f"JSON.stringify({sizes_expr} || [])"
        field_name = self._reactive_values.get("name") or self._derive_field_name()
        if field_name or relocated:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(carrier_expr, initial=_num_list(weights)),
            }
            if field_name:
                hidden_attrs["name"] = str(field_name)
            hidden_attrs.update(relocated)
            children.append(Element(tag="input", attrs=hidden_attrs, children=()))

        # ── Assembly ─────────────────────────────────────────────────
        # The GUTTER, between each panel and its handle. It is an
        # ordinary flex ``gap``, so the gesture is insensitive to it: the
        # drag maths sums PANEL WIDTHS (``totalPx``) and never assumed
        # they filled the container. Measurement of 2026-08-23: +100 px
        # of mouse => +100 px of panel, with gutter and without, to the
        # unit.
        gap_table = theme.get("gaps", {})
        gap_class = responsive_classes(
            self._reactive_values.get("gap") or "none",
            lambda v, _t=gap_table: _t.get(v, ""),
        )
        root_attrs["class"] = self.slot_class(
            "root",
            self.slot_class("vertical" if vertical else "horizontal"),
            gap_class,
        )
        root_attrs["bz-data"] = self._build_bz_data(
            scope_key=scope_key,
            has_local_value=sizes_binding is None,
            weights=weights,
            mins=mins,
            maxs=maxs,
            foldable=foldable,
            binding_path=binding_path,
            server_synced=self._value_server_backed("sizes"),
            vertical=vertical,
        )
        # A scope method has no ``$el`` — it is here, in directive
        # context, that we capture the group into the scope.
        root_attrs["bz-init"] = "_group = $el"
        root_attrs["bz-effect"] = "_apply()"
        root_attrs["bz-on:bz-set"] = "set($event.detail.value)"
        root_attrs["bz-on:bz-reset"] = "reset()"

        return Element(tag=self._tag, attrs=root_attrs, children=tuple(children))

    # ── Morceaux ───────────────────────────────────────────────────────

    @staticmethod
    def _handle(
        *,
        index: int,
        handle_class: str,
        grip_class: str,
        disabled: bool,
        value: float,
        controls: str,
        vertical: bool,
        fold_target: int | None,
    ) -> Element:
        """The handle between panel ``index`` and the next one.

        It is DERIVED, never declared: there is exactly one fewer of them
        than panels, so making the caller write them would only add an
        occasion to get it wrong (same reasoning as the Carousel's
        controls).

        The two class strings arrive COMPOSED: nothing in them depends on
        the index, so recomposing them here would redo an identical theme
        resolution N times.
        """
        attrs: dict[str, Any] = {
            "class": handle_class,
            "data-bz-rz-handle": "",
            # ``separator`` with ``aria-valuenow`` = the ARIA "window
            # splitter" pattern. The declared orientation is the BAR's,
            # so the INVERSE of the group's: panels side by side are
            # separated by a vertical bar. It is the pattern's classic
            # confusion, hence the line.
            "role": "separator",
            "aria-orientation": "horizontal" if vertical else "vertical",
            "aria-valuemin": "0",
            "aria-valuemax": "100",
            "aria-valuenow": str(round(value)),
            "aria-label": text("resizable.resize_panel", n=index + 1),
        }
        # Always set: the group guarantees an ``id`` to the preceding
        # panel, so the "no id" branch does not exist.
        attrs["aria-controls"] = controls
        if disabled:
            attrs["aria-disabled"] = "true"
        else:
            # Focusable: that is what makes the keyboard possible, and
            # the keyboard is the only way without a pointer.
            attrs["tabindex"] = "0"
            attrs["bz-on:pointerdown"] = f"_start($event, {index})"
            attrs["bz-on:pointermove"] = "_move($event)"
            attrs["bz-on:pointerup"] = "_end($event)"
            attrs["bz-on:pointercancel"] = "_end($event)"
            # The collapse, if there is a collapsible panel on either
            # side. Double-click AND ``Enter``: a mouse gesture with no
            # keyboard twin does not exist for half the people, and the
            # handle is already focusable for the arrows.
            #
            # The PAIR travels, not only the target: collapsing means
            # giving your place to the neighbour opposite, and which one
            # that is depends on which side of the handle the collapsible
            # panel sits.
            if fold_target is None:
                fold = "null"
            else:
                partner = index + 1 if fold_target == index else index
                fold = f"[{fold_target}, {partner}]"
                attrs["bz-on:dblclick"] = f"_fold({fold_target}, {partner})"
            attrs["bz-on:keydown"] = f"_key($event, {index}, {fold})"

        grip = Element(
            tag="div",
            attrs={"class": grip_class, "aria-hidden": "true"},
            children=(),
        )
        return Element(tag="div", attrs=attrs, children=(grip,))

    @staticmethod
    def _build_bz_data(
        *,
        scope_key: str,
        has_local_value: bool,
        weights: list[float],
        mins: list[float],
        maxs: list[float],
        foldable: list[bool],
        binding_path: str | None,
        server_synced: bool,
        vertical: bool,
    ) -> str:
        """The instance's ``bz-data``: **data, not code**.

        The methods (geometry, gesture, keyboard, imperative) live once
        in ``$bz.resizable.scope``.

        ``_group`` is declared ``null`` then filled by the root's
        ``bz-init``: a scope method has no access to ``$el``, only
        directives do (same constraint and same remedy as Slider and
        Carousel).

        ``_mins`` / ``_maxs`` / ``_foldable`` travel as data rather than
        being re-read from the DOM: they are design constraints, they
        only change on a re-render, and writing them on each panel would
        force the runtime to re-parse them on every frame of the gesture.

        ``_folded`` starts empty and lives on the client: it is the
        memory of "what size did this panel have before we put it away".
        It has no meaning on the server, which does not know what the
        user collapsed three seconds ago.
        """
        if has_local_value:
            sync = server_sync_marker(scope_key, enabled=server_synced)
            state = f"{scope_key}: {_num_list(weights)},{sync} "
            target = f"this.{scope_key}"
        else:
            assert binding_path is not None
            state = ""
            target = binding_path

        return (
            "{...$bz.resizable.scope,"
            + state
            + f"_mins: {_num_list(mins)},"
            + f"_maxs: {_num_list(maxs)},"
            + f"_foldable: {json.dumps(foldable)},"
            + "_folded: {},"
            + f"_vertical: {json.dumps(vertical)},"
            + "_group: null,"
            + "_drag: null,"
            + f"_read() {{ return {target}; }},"
            + f"_write(v) {{ {target} = v; }}"
            + "}"
        )


__all__ = ["Resizable", "ResizablePanel", "normalize_weights"]

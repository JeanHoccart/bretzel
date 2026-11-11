"""``Tooltip`` — text panel shown on hover / focus of a wrapped trigger.

Usage as a context manager wrapping the trigger ::

    with ui.tooltip("Reclaim 30% of your quota"):
        ui.button("Free up space", on_click=...)

The panel is the page's ONE ``#bz-tip`` (:func:`tooltip_host`), under
``<body>`` — no ancestor's ``overflow-hidden`` (accordion body clip,
sticky page header, table cell, …) can clip it — and ``tip.js``
shows it for the trigger hovered or focused. Positioning rides
``$bz.helpers.floating`` (``position: fixed`` ; its side, the
opposite, then the others ; both axes clamped), so the panel follows
the trigger across scrolls and reflows.

Works on hover AND keyboard focus so the affordance is keyboard-
accessible. The panel is ``pointer-events-none`` so it never
intercepts clicks meant for the trigger or siblings underneath.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, stamp_display_none
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.overlay_wiring import (
    FLOATING_POSITIONS,
    expand_fit_wrapper,
    trigger_is_full_width,
)
from bretzel.components.overlay.tooltip.theme import TOOLTIP_THEME
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding
from bretzel.theme.bridges import bridge_class


class Tooltip(Component):
    """Hover-/focus-revealed text panel."""

    THEME: ClassVar[dict[str, Any]] = TOOLTIP_THEME
    THEME_KEY: ClassVar[str] = "tooltip"
    #: Retired names, refused with the new one (``attrs.split_kwargs``).
    RENAMED_PROPS: ClassVar[dict[str, str]] = {
        "enabled": "write ``disabled=`` with the opposite value — "
                   "``enabled=x`` is ``disabled=~x`` for a binding, "
                   "``disabled=not x`` for a literal.",
    }
    # hints, dynamic descriptions). Position/delay/color are
    # design-time. The text is passed as the first positional arg.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)

    # Default ``auto`` = best-fit : ``$bz.helpers.floating`` picks the
    # roomiest side that fits (preference bottom → top → right → left)
    # and the arrow follows via ``data-side``. Apps can still pin a side
    # per-tooltip (``position="right"`` for a sidebar rail item that must
    # open away from the rail, etc.) — the pinned side then flips to its
    # opposite only when it lacks room.
    position: str = reactive_prop(default="auto", emit_attr=False, steps=FLOATING_POSITIONS)
    #: The TOTAL budget, from hover to readable text. That is the
    #: number that is felt — not the delay alone.
    #:
    #: The tooltip is the family's ONLY member to pay two waits that ADD
    #: UP: this delay, THEN the enter fade. Writing the whole budget in
    #: ``delay`` would overshoot it by the fade, and a hover that takes
    #: half a second to answer reads as a failure, not as an anti-trigger
    #: guard.
    REVEAL_BUDGET_MS: ClassVar[int] = 300

    #: The fade's duration, mirroring the theme's ``duration-75``.
    #: ⚠️ The two MUST stay in agreement — the budget is split between
    #: them, so changing the class without changing this number would
    #: lengthen the total in silence. Guarded by
    #: ``test_the_tooltip_budget_matches_its_fade``.
    FADE_MS: ClassVar[int] = 75

    #: What we wait BEFORE starting to paint: the budget minus the
    #: fade. Derived, never copied — it is the subtraction done in one's
    #: head that re-drifts.
    DEFAULT_DELAY_MS: ClassVar[int] = REVEAL_BUDGET_MS - FADE_MS

    delay: int = reactive_prop(default=DEFAULT_DELAY_MS, emit_attr=False)
    # ``color="text"`` = neutral dark default ; any theme color works
    # (semantic info/success/warning/error or palette primary/muted/...).
    color: str = reactive_prop(default="text", emit_attr=False)
    # The colour paints the panel only: the root wraps the trigger, which
    # keeps its own (cf. ``base/theme_values.root_color_bridge``).
    _COLOR_ON_ROOT: ClassVar[bool] = False

    def __init__(
        self,
        text: str | Component | ClientBinding | None = None,
        *,
        position: str | None = None,
        delay: int | None = None,
        color: str | None = None,
        disabled: bool | ClientBinding | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            position=position,
            delay=delay,
            color=color,
            **kwargs,
        )
        # ``disabled`` keeps hover/focus from revealing the panel (R4 of
        # the API rules).
        # ``None`` (default) → always on. Accepts a literal ``bool`` or a
        # ``ClientBinding`` / ``ClientExpression`` — a raw guard is
        # ``ClientExpression("window.innerWidth < 600")``. Evaluated at
        # hover against the trigger (``$el``), so it can read ancestors
        # via ``$el.closest``.
        #
        # ⚠️ A plain ``str`` is refused, by the rule « a string given to a
        # component is data » (test_a_string_is_never_code): code says it
        # is code.
        if isinstance(disabled, str):
            raise ComponentUsageError(
                f"ui.tooltip(disabled={disabled!r}): a string is data, not code. "
                f"A client condition is written ClientExpression({disabled!r}) "
                f"(from bretzel.state), or a binding of a ClientState field."
            )
        self._disabled: bool | ClientBinding | None = disabled
        # ``text`` accepts a literal string, a ``ClientBinding`` (reactive
        # panel content), or a Component. ``ClientBinding.__bool__``
        # RAISES, so the ``or ""`` is reserved for the non-binding case.
        adopted = text
        if isinstance(adopted, (ClientBinding, Component)):
            self._text: str | ClientBinding | Component = adopted
        else:
            self._text = adopted or ""

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        """The wrapper around the trigger, and what it says — nothing more.

        A client scope, four listeners and a teleported panel per tooltip
        would be a heavy way to say « Edit ». The panel is the page's ONE
        ``#bz-tip`` (:func:`tooltip_host`, rendered by the page pipeline
        with the app's merged theme) and ``tip.js`` shows it: the wrapper
        carries the text and the settings that differ from the default, as
        ``data-bz-tip*`` attributes.
        """
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        root_slot = slots.get("root", "")
        if trigger_is_full_width(self._children):
            # A full-width trigger must expand the ``w-fit`` wrapper or it
            # collapses to content width. Shared with Popover / Dropdown.
            root_slot = expand_fit_wrapper(root_slot)
        attrs = self.emit_attrs()
        # ``classes=`` set by the metaclass wrap — not here (duplicate).
        attrs["class"] = root_slot
        attrs["data-bz-tip-root"] = ""

        children = list(self._render_children())
        text = self._text
        if isinstance(text, Component):
            # Rich content: rendered here, inert until the runtime clones
            # it into the panel at show time.
            rendered = self.emit_text_slot(text)
            children.append(Element(
                tag="template",
                attrs={"data-bz-tip-content": ""},
                children=(rendered,) if rendered is not None else (),
            ))
        elif isinstance(text, ClientBinding):
            # A bound text: the attribute follows the store, and the
            # runtime follows the attribute while the panel shows.
            attrs["bz-attr:data-bz-tip"] = self.path_of(text)
        else:
            attrs["data-bz-tip"] = str(text or "")

        position = self._reactive_values.get("position") or "auto"
        if position != "auto":
            attrs["data-bz-tip-position"] = position
        delay = int(self._reactive_values.get("delay") or self.DEFAULT_DELAY_MS)
        if delay != self.DEFAULT_DELAY_MS:
            attrs["data-bz-tip-delay"] = str(delay)
        color = self._reactive_values.get("color") or "text"
        if color != "text":
            attrs["data-bz-tip-color"] = color
        # ``slots={"panel": …}`` on ONE tooltip: the shared panel wears it
        # for that show only — the escape hatch stays open.
        extra = _extra_classes(slots.get("panel", ""), _host_slots().get("panel", ""))
        if extra:
            attrs["data-bz-tip-class"] = extra
        off = self._off_expr()
        if off is not None:
            attrs["data-bz-tip-off"] = off

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))

    def _off_expr(self) -> str | None:
        """``disabled`` as the JS expression the runtime reads at HOVER time
        (``$el`` = the trigger), or ``None`` when it is never off.

        A :class:`ClientBinding` reads the store path, a
        ``ClientExpression`` its expression, verbatim — a DOM or
        media-query guard, which must be re-read on every hover and never
        frozen at mount (the bug of 2026-07, when it rode a ``bz-data``
        field).
        """
        disabled = self._disabled
        if disabled is None:
            return None
        if isinstance(disabled, ClientBinding):
            # ``path_of`` already unifies the ClientBinding /
            # ClientExpression resolution (the latter is a subclass and
            # must NOT get a second ``$bz.state.`` prefix).
            return self.path_of(disabled)
        # ⚠️ A SERVER-BACKED value is not a ``bool`` in the ``isinstance``
        # sense: ``ServerState`` stamps it as a ``_BoundBool``, an ``int``
        # subclass. Emitting ``str()`` of it would write the PYTHON literal
        # ``True`` into JavaScript — a ``ReferenceError`` on the first
        # hover. Hence the truthiness.
        return "true" if disabled else None


def _host_slots() -> dict[str, str]:
    """The tooltip theme's slots, merged with the app's override when a
    render context is active — what the shared panel wears."""
    from bretzel.render.context import maybe_current_context

    theme = TOOLTIP_THEME
    ctx = maybe_current_context()
    getter = getattr(getattr(getattr(ctx, "app", None), "theme", None), "merged_component_theme", None)
    if callable(getter):
        theme = getter("tooltip", TOOLTIP_THEME)
    return theme.get("slots", {})


def _extra_classes(own: str, shared: str) -> str:
    """The classes ONE tooltip's panel adds to the shared one."""
    base = set(shared.split())
    return " ".join(c for c in own.split() if c not in base)


def tooltip_host() -> Element:
    """The page's ONE tooltip panel, ``#bz-tip`` — shown by ``tip.js``.

    Rendered by the page pipeline, inside the render context, so it wears
    the app's MERGED tooltip theme: ``Theme(components={"tooltip": …})``
    reaches every tooltip of the page at once. ``fixed`` and not
    ``absolute``: it lives under ``<body>``, outside every clipping
    ancestor, and ``$bz.helpers.floating`` sets its coordinates. ``group``
    lets the arrow's ``group-data-[side=…]`` variants read the side that
    ``floating`` writes. Hidden until a trigger asks (no flash on load).
    """
    slots = _host_slots()
    panel_class = slots.get("panel", "").replace("absolute", "fixed") + " group"
    attrs: dict[str, Any] = {
        "id": "bz-tip",
        "role": "tooltip",
        "class": f"{panel_class} {bridge_class('text')}",
        "data-side": "bottom",
        # The reveal delay lives in Python (the budget is split with the
        # fade — ``REVEAL_BUDGET_MS``); a trigger overrides it on its own.
        "data-bz-tip-delay": str(Tooltip.DEFAULT_DELAY_MS),
    }
    stamp_display_none(attrs)
    return Element(tag="div", attrs=attrs, children=(
        Element(tag="span", attrs={"data-bz-tip-body": ""}, children=()),
        Element(tag="div", attrs={"class": slots.get("arrow", ""), "aria-hidden": "true"}, children=()),
    ))

"""``Tooltip`` — text panel shown on hover / focus of a wrapped trigger.

Usage as a context manager wrapping the trigger ::

    with ui.tooltip("Reclaim 30% of your quota"):
        ui.button("Free up space", on_click=...)

The panel **teleports to ``<body>`` via ``bz-teleport``** at init —
no ancestor's ``overflow-hidden`` (accordion body clip, sticky page
header, table cell, …) can clip it because the panel isn't a
descendant of any of them at the DOM level. Positioning rides
``$bz.helpers.floating`` (``position: fixed``, main-axis flip +
cross-axis clamp), so the panel follows the trigger across scrolls
and reflows.

Works on hover AND keyboard focus so the affordance is keyboard-
accessible. The panel is ``pointer-events-none`` so it never
intercepts clicks meant for the trigger or siblings underneath.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, stamp_display_none
from bretzel.components.base._wiring import (
    anchored_panel_effect,
    expand_fit_wrapper,
    server_sync_marker,
    teleport_to_body,
    trigger_is_full_width,
)
from bretzel.components.overlay.tooltip.theme import TOOLTIP_THEME
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.state.scopes.client import ClientBinding


class Tooltip(Component):
    """Hover-/focus-revealed text panel."""

    THEME: ClassVar[dict[str, Any]] = TOOLTIP_THEME
    THEME_KEY: ClassVar[str] = "tooltip"
    # hints, dynamic descriptions). Position/delay/color are
    # design-time. The text is passed as the first positional arg.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("text",)

    # Default ``auto`` = best-fit : ``$bz.helpers.floating`` picks the
    # roomiest side that fits (preference bottom → top → right → left)
    # and the arrow follows via ``data-side``. Apps can still pin a side
    # per-tooltip (``position="right"`` for a sidebar rail item that must
    # open away from the rail, etc.) — the pinned side then flips to its
    # opposite only when it lacks room.
    position: str = reactive_prop(default="auto", emit_attr=False)
    #: The TOTAL budget, from hover to readable text. That is the
    #: number that is felt — not the delay alone.
    #:
    #: The tooltip is the family's ONLY member to pay two waits that ADD
    #: UP: this delay, THEN the enter fade. Writing 300 in ``delay``
    #: therefore gave 450 on screen, and a hover that takes half a second
    #: to answer reads as a failure, not as an anti-trigger guard.
    #: Reported from use on 2026-09-04.
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

    def __init__(
        self,
        text: str | ClientBinding | None = None,
        *,
        position: str | None = None,
        delay: int | None = None,
        color: str | None = None,
        enabled: bool | ClientBinding | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            position=position,
            delay=delay,
            color=color,
            **kwargs,
        )
        # ``enabled`` gates whether hover/focus actually reveals the panel.
        # ``None`` (default) → always on. Accepts a literal ``bool``, a
        # ``ClientBinding`` (reactive server-driven flag), or a raw client
        # expression string (escape hatch — e.g. a DOM/media-query guard
        # like the Sidebar's "only in the collapsed rail"). Evaluated in
        # ``_show()`` against the tooltip root's scope (``$el`` = the
        # trigger wrapper), so it can read ancestors via ``$el.closest``.
        self._enabled: bool | ClientBinding | str | None = enabled
        # ``text`` accepts a literal string, a ``ClientBinding`` (reactive
        # panel content), or a Component. ``adopt_slot`` detaches a
        # Component (otherwise rendered twice) and lets string /
        # ClientBinding through intact. ``ClientBinding.__bool__``
        # RAISES, so the ``or ""`` is reserved for the non-binding case.
        adopted = Component.adopt_slot(text)
        if isinstance(adopted, (ClientBinding, Component)):
            self._text: str | ClientBinding | Component = adopted
        else:
            self._text = adopted or ""

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        position = self._reactive_values.get("position") or "auto"
        delay = int(
            self._reactive_values.get("delay") or self.DEFAULT_DELAY_MS
        )
        # Pre-JS default side for the arrow (``floating`` overwrites
        # ``data-side`` on the first open) : the pinned side if any, a
        # sensible ``bottom`` for the ``auto`` case.
        initial_side = "bottom" if position == "auto" else position

        # ── Panel : the floating tooltip ─────────────────────────────
        # ``fixed`` (not ``absolute``) because the panel is teleported
        # to ``<body>`` — ancestor positioned containers no longer
        # exist for it. Coordinates are JS-set on every show from the
        # trigger's ``getBoundingClientRect()``.
        # ``group`` names the panel so the arrow's ``group-data-[side=…]``
        # variants can read the ``data-side`` that ``floating`` writes.
        panel_class = self.compose_class(
            "panel",
            apply_variant_size_modifiers=False,
        ).replace("absolute", "fixed") + " group"

        # ``emit_text_slot`` handles the 4 shapes of a textual slot
        # (string / ClientBinding → span+bz-text through ``path_of`` /
        # Component → rendered in place / empty → None). The ``or
        # TextNode("")`` covers the empty slot (the panel always exists,
        # with no text).
        text_node: Node = self.emit_text_slot(self._text) or TextNode("")
        # Arrow stays absolute-positioned RELATIVE TO THE PANEL. Its
        # per-side anchor lives in the ``arrow`` slot as four
        # ``group-data-[side=…]`` variants — the one matching the panel's
        # runtime ``data-side`` applies. No SSR side lookup : the arrow
        # follows the flip / best-fit. Always present (no arrowless mode).
        panel_children: list[Node] = [text_node]
        arrow_class = self.compose_class(
            "arrow",
            apply_variant_size_modifiers=False,
        )
        panel_children.append(
            Element(
                tag="div",
                attrs={"class": arrow_class, "aria-hidden": "true"},
                children=(),
            )
        )
        panel_attrs: dict[str, Any] = {
            "class": panel_class,
            "role": "tooltip",
            "bz-ref": "bzpanel",
            # Initial arrow side before ``floating`` runs (it overwrites
            # ``data-side`` on the first open with the resolved side).
            "data-side": initial_side,
            # display toggle + floating attach against the trigger
            # root (anchored on its firstElementChild, the real
            # trigger box). Anchored on ``bzroot`` (the tooltip root).
            "bz-effect": anchored_panel_effect(
                "open", position, trigger_ref="bzroot"
            ),
        }
        # FOUC : pre-stamp hidden (tooltip starts closed).
        stamp_display_none(panel_attrs)
        panel = Element(
            tag="div",
            attrs=panel_attrs,
            children=tuple(panel_children),
        )
        # Teleport the panel under ``<body>`` (shared helper) : ancestor
        # ``overflow`` / stacking traps lose power over it, while it stays
        # bound to this tooltip's origin scope.
        teleport = teleport_to_body(panel, self)

        # ── Root wrapper : the trigger lives inside as children ──────
        # Carries the open flag + show/hide/position methods.
        root_slot = slots.get("root", "")
        if trigger_is_full_width(self._children):
            # A full-width trigger must expand the ``w-fit`` wrapper or it
            # collapses to content width. Shared with Popover / Dropdown.
            root_slot = expand_fit_wrapper(root_slot)
        attrs = self.emit_attrs()
        # ``classes=`` set by the metaclass wrap — not here (duplicate).
        attrs["class"] = root_slot
        attrs["bz-data"] = _build_bzdata(delay, self._enabled_expr())
        attrs["bz-ref"] = "bzroot"
        attrs["bz-on:mouseenter"] = "_show()"
        attrs["bz-on:mouseleave"] = "_hide()"
        # Keyboard a11y : focusing inside (e.g. tabbing onto the
        # button) reveals the tooltip without delay.
        attrs["bz-on:focusin"] = "_show()"
        attrs["bz-on:focusout"] = "_hide()"

        children = list(self._render_children())
        children.append(teleport)
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))

    def _enabled_expr(self) -> str:
        """Resolve ``enabled`` to a JS predicate for ``_show()``'s guard.

        ``None`` → ``"true"`` (always reveal). A literal ``bool`` bakes
        ``"true"``/``"false"``. A :class:`ClientBinding` reads the reactive
        store path. A raw string is used verbatim (caller owns the
        expression — it's evaluated in the tooltip root's scope).
        """
        enabled = self._enabled
        if enabled is None:
            return "true"
        if isinstance(enabled, bool):
            return "true" if enabled else "false"
        if isinstance(enabled, ClientBinding):
            # ``path_of`` already unifies the ClientBinding /
            # ClientExpression resolution (the latter is a subclass and
            # must NOT get a second ``$bz.state.`` prefix) — reuse it
            # instead of hand-rolling the path here.
            return self.path_of(enabled)
        if not isinstance(enabled, str):
            # ⚠️ A SERVER-BACKED value is not a ``bool`` in the
            # ``isinstance`` sense: ``ServerState`` stamps it as a
            # ``_BoundBool``, an ``int`` subclass carrying its
            # ``field_name``. The ``isinstance(enabled, bool)`` test
            # above therefore misses it, and the final ``str()`` emitted
            # the PYTHON literal ``True`` into JavaScript — hence a
            # ``ReferenceError: True is not defined`` on the first hover,
            # which killed the effect.
            #
            # Found in the browser on 2026-07-29, on the playground's
            # tooltip page (``enabled=state.enabled``). A bug PREDATING
            # the switch to ``$bz.tooltip.scope``: the old builder
            # interpolated the same expression into ``if (!(True))
            # return;``. The 9,400 Python tests were green — only a real
            # browser could see it.
            return "true" if enabled else "false"
        return str(enabled)

    # ── Full-width detection ───────────────────────────────────────────

    # NB : ``_build_bzdata`` lives at module scope below ; it composes
    # the ``bz-data`` body that holds the open flag + the hover
    # debounce timer. Positioning is owned by the panel's
    # ``anchored_panel_effect`` (``$bz.helpers.floating``).

# ── bz-data builder ─────────────────────────────────────────────────────────


def _build_bzdata(delay_ms: int, enabled_expr: str = "true") -> str:
    """Compose the ``bz-data`` object literal for the tooltip root.

    - ``open`` (bool) : drives the panel's display + floating effect.
    - ``_t`` (timer handle) : pending hover debounce.
    - ``_show()`` : bails when ``enabled_expr`` is falsy ; otherwise
      starts the debounce ; on fire flips ``open`` (the panel's
      ``bz-effect`` then shows + positions it via floating).
    - ``_hide()`` : clears the debounce + closes.

    ``enabled_expr`` is a JS predicate evaluated on each hover/focus
    (``"true"`` by default). It's checked at SHOW time, not mount time,
    so a live condition (collapse state, media query) is honoured as it
    changes. Positioning is owned by ``$bz.helpers.floating`` (engaged by
    the panel's ``anchored_panel_effect``).
    """
    # ``_show`` / ``_hide`` live once in ``$bz.tooltip.scope``
    # (``bretzel/runtime/_src/16_accordion.js``). This builder serialised
    # them per instance while BAKING the configuration into them — the
    # body contained ``if (!(true)) return;`` and the delay as a literal,
    # so two tooltips with different delays produced two different CODES.
    #
    # ``_enabled`` must stay an EXPRESSION re-read on every hover — a
    # live condition (a collapsed state, a media query, a ClientBinding)
    # must be honoured as it changes. The "config as data" switch had
    # nevertheless emitted it as a FIELD (``_enabled: <expr>``), which
    # produces exactly the opposite: a field is evaluated once, outside
    # any effect, and ``absorb`` wraps its snapshot in a signal decoupled
    # from the store. The comment promised the hover, the code froze at
    # mount. Only a method body is re-read — hence the override of the
    # slab's ``_enabled()`` constant. ``_delay`` stays a field: it is a
    # server-side literal, so real data.
    enabled_override = (
        f"_enabled() {{ return !!({enabled_expr}); }},"
        if enabled_expr != "true"
        else ""
    )
    # ``_delay`` is CONFIG (server-owned) → re-seeded unconditionally.
    # ``open`` and ``_t`` are NOT: client state (the open panel, the
    # in-flight timer). Re-seeding them would close a displayed tooltip
    # on every neighbouring swap.
    return (
        "{...$bz.tooltip.scope,"
        "open: false,"
        "_t: null,"
        f"{enabled_override}"
        f"_delay: {delay_ms},"
        f"{server_sync_marker('_delay', enabled=True).strip()}"
        "}"
    )

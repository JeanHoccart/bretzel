"""``BottomBar`` / ``BottomBarItem`` — bottom-of-screen tab bar (mobile).

API ::

    # The mobile shell — the tab bar AT THE BOTTOM, the content above.
    # The responsive part stays server-driven: it is the layout that
    # branches on ``Screen().is_mobile``
    # (cf. ``.claude/bretzel/screen-responsive-nav.md``).
    if Screen().is_mobile:
        with ui.vstack():
            ui.outlet()
            with ui.bottom_bar():
                ui.bottom_bar_item("Home",   icon="home",   href="/")
                ui.bottom_bar_item("Search", icon="search", href="/search")
                ui.bottom_bar_item("Alerts", icon="bell",   href="/alerts",
                                   badge=3)
                ui.bottom_bar_item("Profile", icon="user",  href="/me")
    else:
        with ui.hstack():
            ui.sidebar(...)
            ui.outlet()

Two pieces, not three — **there is no ``bottom_bar_section``.** A tab bar
is a row of equal-width tabs (``flex-1``); ``NavbarSection``'s left /
centre / right grouping makes no sense there, and that is precisely what
sets it apart from a navbar.

The framework **imposes no mobile nav** (settled decision, cf.
``todo.md`` § A): ``ui.sidebar`` no longer has a built-in drawer, and
this component is never mounted on its own. It is the dev who writes
their ``if``, and who chooses the bottom bar rather than a horizontal
navbar — which remains a poor compromise on a phone (targets too small,
out of the thumb's reach).

Why ``sticky`` and not ``fixed``
--------------------------------

A ``position: fixed`` bar leaves the flow: it masks the bottom of the
page, and one has to compensate — either a ``padding-bottom`` written by
hand in the app code (which the funnel's hard rule no. 1 refuses), or a
"spacer" node emitted beside the bar. That second route **breaks the
universal kwargs**: ``_apply_universal_modifiers`` only knows how to set
``classes=`` / ``style=`` / ``visible=binding`` / ``tooltip=`` on a root
``Element``, so a ``Fragment(spacer, bar)`` would lose them in silence,
and a wrapper would set them on the invisible spacer.

``position: sticky`` gives both properties in **a single node**: it stays
in the flow (so it reserves its own height, no content masked) and
sticks to the bottom of the viewport during the scroll. It is exactly
``ui.navbar(sticky=True)``'s mechanism, flipped.

⚠️ Two corollaries inherited from sticky, and there is **no prop to work
around them** (cf. ``_CUT``):

- an ancestor with ``overflow: hidden`` or ``overflow: auto`` moves the
  anchoring — the bar sticks to the bottom of THAT container, not of the
  viewport. Same fragility as ``ui.navbar(sticky=True)``.
- a sticky element cannot leave its containing block. Mounting several
  bars on one page (a bench, a preview) therefore makes them pin in
  turn; giving each its own container at ITS height immobilises them. It
  is what the ``/bottom-bar`` page does.

In a "frozen document" shell, the bar RAISES if it is misplaced
-----------------------------------------------------------------
A page that writes ``ui.viewport`` chooses the frozen document model,
and the frame is ``fixed inset-0`` — it leaves the flow. Two natural
placements then render a page that looks built, and
``check_sticky_bar_placement`` (``base/_wiring``, called by the pipeline
once the tree is built) refuses both, with the gesture to write:

- **outside the frame** — the placement "stuck to the bottom of the
  screen" suggests. Measured: the bar renders at **y = 0**;
- **direct child of a row frame** — the bar is full width, so it takes
  the whole row and the neighbouring ``ui.pane`` drops to **0 px wide**.
  It is the page's content that disappears, not the bar.

The guard says nothing as long as no ``ui.viewport`` exists in the
render: the default model — the document that scrolls — is not
concerned. ``traps.md`` § *A `sticky` bar outside the frozen frame*.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
)
from bretzel.components.base._wiring import register_sticky_bar
from bretzel.components.navigation._wiring import (
    capture_layout,
    current_path_resync_init,
    current_path_scope,
    render_badge,
    wire_nav_item,
)
from bretzel.components.navigation.bottom_bar.theme import (
    BOTTOM_BAR_ITEM_THEME,
    BOTTOM_BAR_THEME,
)
from bretzel.core.tree import Element

# ───────────────────────────────────────────────────────────────────────────
# BottomBar — root container
# ───────────────────────────────────────────────────────────────────────────


class BottomBar(Component):
    """Render a bottom navigation bar that tracks the current path."""

    THEME: ClassVar[dict[str, Any]] = BOTTOM_BAR_THEME
    THEME_KEY: ClassVar[str] = "bottom_bar"
    DEFAULT_TAG: ClassVar[str] = "nav"
    # The component has **no axis at all**: no colour, no size, no
    # variant, no positioning. Its shape is that of a tab bar, full stop.
    # ``()`` and not ``None``: ``None`` would mean "check nothing" and a
    # binding would be accepted then thrown away in silence.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    # The two axes shipped then cut, each for the same reason: they fail
    # the opinionation rule's decisive test — "would we have this
    # component in two shapes in the SAME app?". No: an app has a single
    # tab bar.
    #
    # ⚠️ The guard is not politeness. Without it, the base layer absorbs
    # the unknown kwarg into the raw attrs: ``ui.bottom_bar(sticky=False)``
    # would emit an HTML attribute ``sticky="false"`` **in silence**,
    # changing nothing in the render. The risk is concrete — the navbar,
    # of which this component is the mirror, kept ``sticky=`` AND
    # ``variant=``, so the gesture gets imitated.
    _CUT: ClassVar[dict[str, str]] = {
        "variant": (
            "the look (detached rounded pill vs full-width bar) is "
            "chosen once per app: it is a theme decision"
        ),
        "sticky": (
            "a tab bar is ALWAYS stuck — a bar that goes away on scroll "
            "is no longer a tab bar, it is a footer"
        ),
    }

    def __init__(self, **kwargs: Any) -> None:
        for name, why in self._CUT.items():
            if name in kwargs:
                raise ComponentUsageError(
                    f"ui.bottom_bar has no `{name}=`: {why}. "
                    f"Override the theme's `root` slot to change that — "
                    f'Bretzel(theme=Theme(components={{"bottom_bar": '
                    f'{{"slots": {{"root": "…"}}}}}})), or '
                    f'`slots={{"root": "…"}}` on the instance for a '
                    f"one-off."
                )
        super().__init__(**kwargs)
        # It registers, it does not judge itself: "am I well placed?"
        # is a question asked of the TREE, and the tree does not exist
        # yet. It is ``render/pipeline._drain`` that decides, once the
        # page is built. Cf. ``base/_wiring.check_sticky_bar_placement``.
        register_sticky_bar(self, "ui.bottom_bar")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("root", "")

        # ``current_path`` scope — strictly the same as Navbar's and
        # Sidebar's, so the three stay in agreement about the active item
        # when a page mounts several. The redundancy is intended: the
        # bottom bar must work on a page that has neither of the other
        # two.
        attrs.setdefault("bz-data", current_path_scope())
        # Resync on back/forward and on a partial nav triggered
        # elsewhere — without that the highlighting comes unstuck from
        # the URL at the first back (the bug the navbar carried until
        # 2026-07-27).
        attrs.setdefault("bz-init", current_path_resync_init())

        inner = Element(
            tag="div",
            attrs={"class": slots.get("inner", "")},
            children=tuple(self._render_children()),
        )

        return Element(tag=self._tag, attrs=attrs, children=(inner,))


# ───────────────────────────────────────────────────────────────────────────
# BottomBarItem — un onglet
# ───────────────────────────────────────────────────────────────────────────


class BottomBarItem(Component):
    """Render a bottom-bar item with an icon, label, and optional badge."""

    THEME: ClassVar[dict[str, Any]] = BOTTOM_BAR_ITEM_THEME
    THEME_KEY: ClassVar[str] = "bottom_bar_item"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    # Exact mirror of NavbarItem: ``active`` is auto-derived from
    # ``current_path`` when nothing is passed; ``badge`` and ``disabled``
    # accept a ClientBinding for a live counter (unread, cart).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("active", "badge", "disabled")

    label: str = reactive_prop(default="", emit_attr=False)
    href: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    active: Any = reactive_prop(default=None, emit_attr=False)
    badge: Any = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        label: str = "",
        *,
        icon: Any = None,
        href: str | None = None,
        active: Any = None,
        badge: Any = None,
        disabled: bool | None = None,
        color: str | None = None,
        on_click: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # The ``icon="home"`` shortcut is wrapped one size above the
        # default: a touch target needs a readable glyph (24px, the
        # iOS/Android order of magnitude), where ``Icon`` by default
        # renders 18px calibrated for a line of text. We only re-size the
        # STRING shortcut — an ``icon=ui.icon("home", size="xl")`` built
        # by the caller keeps its size.
        #
        # ⚠️ BEFORE the ``super()``, not after. Passing the string then
        # overwriting ``_slot_components`` builds TWO ``Icon`` per tab —
        # the one ``adopt_slot`` makes at the default size, thrown away
        # immediately, then the right one. Measured: ~10.6 µs per item,
        # that is 40 % of the construction cost and more than half of a
        # full ``render()``. By normalising here, the standard slot
        # pipeline adopts the value once. (EmptyState does the opposite
        # out of necessity: its icon size comes from the resolved theme,
        # so after ``super()``. Here it is the constant ``"lg"`` — the
        # constraint does not apply.)
        if isinstance(icon, str):
            from bretzel.components.primitives.icon.icon import Icon

            icon = Icon(icon, size="lg")

        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            label=label,
            href=href,
            active=active,
            badge=badge,
            disabled=disabled,
            color=color,
            icon=icon,
            on_click=on_click,
            **kwargs,
        )

        # Capture of the enclosing layout for the HTMX partial-nav
        # (same mechanics as SidebarItem / NavbarItem). At construction,
        # because the ``with @layout(): ...`` is still open here —
        # ``layout_stack`` is empty at ``render()`` time.
        self._captured_layout: str | None = capture_layout()

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        # Reading + wiring: the shared body of the three nav items
        # (navigation/_wiring.py). What follows is specific to this
        # component.
        w = wire_nav_item(self, slots)
        tag, attrs = w.tag, w.attrs
        badge_value, badge_binding = w.badge_value, w.badge_binding
        label = w.label

        # ── Children: (icon + badge) above, label below ───────────────
        #
        # The badge is anchored to the ICON, not to the tab: ``flex-1``
        # makes the tab far wider than its content, so a badge stuck to
        # the tab's corner would float in the void. Hence this relative
        # wrapper.
        wrapped: list[Any] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            Component._detach_from_parent(icon)
            wrapped.append(
                Component.with_slot_class(icon.render(), slots.get("icon", ""))
            )

        # A Component passed as badge only gets the PLACEMENT: it has
        # already decided its look, and repainting over it would put two
        # competing ``bg-*`` on the same node (cf. the theme).
        badge_class = slots.get("badge", "")
        if not isinstance(badge_value, Component):
            badge_class = f"{badge_class} {slots.get('badge_pill', '')}".strip()

        if badge_binding is not None:
            wrapped.append(
                render_badge(
                    badge_value,
                    badge_class,
                    reactive_path=self.path_of(badge_binding),
                )
            )
        elif badge_value is not None:
            wrapped.append(render_badge(badge_value, badge_class))

        children: list[Any] = []
        if wrapped:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("icon_wrap", "")},
                    children=tuple(wrapped),
                )
            )

        if label:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("label", "")},
                    children=(self.emit_text_slot(label),),
                )
            )

        return Element(tag=tag, attrs=attrs, children=tuple(children))


__all__ = ["BottomBar", "BottomBarItem"]

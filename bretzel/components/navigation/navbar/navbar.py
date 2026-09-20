"""``Navbar`` / ``NavbarSection`` / ``NavbarItem`` — top navigation bar.

API ::

    # Marketing / public site — navbar standalone.
    with ui.navbar(sticky=True):
        with ui.navbar_section(side="left"):
            ui.heading("Bretzel", level=1)
        with ui.navbar_section(side="center"):
            ui.navbar_item("Docs",    href="/docs")
            ui.navbar_item("Pricing", href="/pricing")
        with ui.navbar_section(side="right"):
            ui.button("Get started", color="primary")

    # Mobile shell — the navbar IS the mobile nav. Responsive is server-
    # driven : the layout branches on ``Screen().is_mobile`` (a navbar on
    # phones, a ``ui.sidebar`` on desktop). The sidebar no longer carries any
    # built-in mobile drawer — see ``.claude/bretzel/screen-responsive-nav.md``.
    with ui.navbar():
        with ui.navbar_section(side="left"):
            ui.heading("Acme Dashboard", level=1)
        with ui.navbar_section(side="right"):
            ui.avatar(src="/me.jpg")

Three pieces, mirror of the Sidebar trio :

- **Navbar** — the ``<header>``. Drives a ``current_path`` reactive
  (component-local ``bz-data`` scope, V3 runtime) the same way Sidebar
  does, so a page hosting both stays in sync on partial nav.
  ``sticky=True`` pins the bar to the top during scroll ;
  ``variant="floating"`` gives the Stripe / Linear marketing-site
  rounded-card look. A ``sticky`` bar in a "frozen document" shell
  (``ui.viewport``) is subject to the same placement guard as
  ``ui.bottom_bar``, of which it is the upward mirror — cf. the latter's
  docstring, and ``traps.md`` § *A `sticky` bar outside the frozen
  frame*. Without ``sticky``, nothing is judged: the bar scrolls with
  the document.
- **NavbarSection** — positional grouping with ``side="left"`` /
  ``"center"`` / ``"right"``. No behaviour of its own, just a flex
  container with the right margin auto.
- **NavbarItem** — horizontal counterpart of :class:`SidebarItem`.
  Same htmx partial-nav wiring (auto-injected ``hx-get`` /
  ``hx-target`` inside ``@layout``), same ``current_path``-driven
  active state, but with a horizontal pill look.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import register_sticky_bar
from bretzel.components.navigation._wiring import (
    capture_layout,
    current_path_resync_init,
    current_path_scope,
    render_badge,
    wire_nav_item,
)
from bretzel.components.navigation.navbar.theme import (
    NAVBAR_ITEM_THEME,
    NAVBAR_THEME,
)
from bretzel.core.tree import Element

# ───────────────────────────────────────────────────────────────────────────
# Navbar — root container
# ───────────────────────────────────────────────────────────────────────────


class Navbar(Component):
    """``<header>`` top bar. Owns ``current_path`` for active links."""

    THEME: ClassVar[dict[str, Any]] = NAVBAR_THEME
    THEME_KEY: ClassVar[str] = "navbar"
    DEFAULT_TAG: ClassVar[str] = "header"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    sticky: bool = reactive_prop(default=False, emit_attr=False)
    variant: str = reactive_prop(default="standard", emit_attr=False)

    def __init__(
        self,
        *,
        sticky: bool | None = None,
        variant: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(sticky=sticky, variant=variant, **kwargs)
        # A non-``sticky`` navbar is an ordinary block: it scrolls with
        # the rest and has nothing to say to the frozen model. Only the
        # stuck version depends on what contains it — the same mechanism
        # as ``ui.bottom_bar``, flipped upwards. We re-read the RESOLVED
        # value: ``sticky=`` can arrive as ``None``.
        if self._reactive_values.get("sticky"):
            register_sticky_bar(self, 'ui.navbar(sticky=True)')

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        variants = theme.get("variants", {})

        sticky = bool(self._reactive_values.get("sticky"))
        variant_key = self._reactive_values.get("variant") or "standard"

        root_class = " ".join(
            p
            for p in (
                slots.get("root", ""),
                theme.get("sticky", "") if sticky else "",
                variants.get(variant_key, ""),
            )
            if p
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        attrs.setdefault("role", "banner")

        # bz-data current_path scope — identical to Sidebar so a page
        # hosting both navbar + sidebar keeps the active state synced
        # on the same scope semantics. The redundancy is intentional :
        # the navbar must work on pages where no sidebar is mounted
        # (marketing site, settings shell), so it can't rely on the
        # sidebar's scope.
        attrs.setdefault("bz-data", current_path_scope())
        # Resync ``current_path`` on back/forward and on a partial nav
        # triggered elsewhere in the page. The optimistic flip on click
        # covers ONLY the navs that left from the navbar: without these
        # two listeners, the highlighting came unstuck from the URL at
        # the first back — while the class's docstring promised parity
        # with Sidebar (audit F26). Shared with it.
        attrs.setdefault("bz-init", current_path_resync_init())

        # Inner ``<nav>`` wraps the children with the max-width clamp +
        # horizontal padding + flex-row layout. Sections live inside.
        inner = Element(
            tag="nav",
            attrs={"class": slots.get("inner", "")},
            children=tuple(self._render_children()),
        )

        return Element(tag=self._tag, attrs=attrs, children=(inner,))


# ───────────────────────────────────────────────────────────────────────────
# NavbarSection — positional grouping (left/center/right)
# ───────────────────────────────────────────────────────────────────────────


class NavbarSection(Component):
    """One of three positional groupings inside a Navbar."""

    THEME: ClassVar[dict[str, Any]] = NAVBAR_THEME
    THEME_KEY: ClassVar[str] = "navbar"
    # the check on ``is not None``, so ``None`` = "check nothing" → a
    # binding passed here was ACCEPTED then thrown away in silence
    # (``side`` is ``emit_attr=False`` → the SSR value freezes and never
    # changes). ``()`` = "no bindable prop", and the refusal becomes
    # explicit. Cf. todo.md § C.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    # Default ``"left"`` matches the visual order : left → center →
    # right reads in source order, the auto-margin pushes each to its
    # corner via flex.
    side: str = reactive_prop(default="left", emit_attr=False)

    def __init__(
        self,
        *,
        side: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(side=side, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        side_key = self._reactive_values.get("side") or "left"

        slot_key = {
            "left": "section_left",
            "center": "section_center",
            "right": "section_right",
        }.get(side_key, "section_left")

        attrs = self.emit_attrs()
        attrs["class"] = slots.get(slot_key, "")

        children = self._render_children()
        return Element(tag=self._tag, attrs=attrs, children=children)


# ───────────────────────────────────────────────────────────────────────────
# NavbarItem — horizontal nav row
# ───────────────────────────────────────────────────────────────────────────


class NavbarItem(Component):
    """Horizontal nav row — icon + label + optional badge.

    Mirrors :class:`SidebarItem` : same htmx partial-nav wiring (when
    ``href`` is passed inside an ``@layout``), same
    ``current_path``-driven auto-active mode, same external-URL guard.
    Only the visual / theme differs — a horizontal pill instead of a
    full-width row, no fade-on-collapse (the navbar never collapses).
    """

    THEME: ClassVar[dict[str, Any]] = NAVBAR_ITEM_THEME
    THEME_KEY: ClassVar[str] = "navbar_item"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    # Curated reactive surface — active is auto-derived from
    # current_path when no explicit value is passed ; badge + disabled
    # accept ClientBinding so navbar items can show live counters
    # (notifications, unread, etc.).
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

        # Capture the enclosing layout name for htmx partial-nav (same
        # mechanic as SidebarItem). Done at construct time because the
        # ``with @layout(): ...`` block is still active here ;
        # ``ctx.layout_stack`` empties by the time ``render()`` runs.
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

        # ── Children : icon + label + badge ──────────────────────────
        children: list[Any] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            Component._detach_from_parent(icon)
            icon_node = Component.with_slot_class(
                icon.render(), slots.get("icon", "")
            )
            children.append(icon_node)

        if label:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("label", "")},
                    children=(self.emit_text_slot(label),),
                )
            )

        # ── Badge ────────────────────────────────────────────────────
        # Three shapes (mirror of the active resolution above) :
        # 1. Explicit binding → live counter. The badge always renders ;
        #    ``bz-text`` writes the running value into the pill and
        #    ``bz-show`` hides it when the count is falsy (0 / "" / null),
        #    so a "0 unread" badge collapses instead of showing a stale
        #    "0". The SSR ``badge_value`` (if any) paints the first frame
        #    before the runtime boots.
        # 2. Scalar / Component value → static pill (existing behaviour).
        # 3. None → no badge.
        if badge_binding is not None:
            path = self.path_of(badge_binding)
            children.append(
                render_badge(
                    badge_value,
                    slots.get("badge", ""),
                    reactive_path=path,
                )
            )
        elif badge_value is not None:
            children.append(render_badge(badge_value, slots.get("badge", "")))

        return Element(tag=tag, attrs=attrs, children=tuple(children))


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


__all__ = ["Navbar", "NavbarItem", "NavbarSection"]



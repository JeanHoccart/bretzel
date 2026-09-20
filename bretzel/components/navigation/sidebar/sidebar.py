"""``Sidebar`` / ``SidebarSection`` / ``SidebarItem`` — navigation rail.

API ::

    with ui.sidebar(open=client_state.expanded, collapsible=True):
        with ui.sidebar_section(label="MAIN"):
            ui.sidebar_item("Dashboard", icon="home", href="/")
            ui.sidebar_item("Issues", icon="bug", href="/issues",
                            badge=42)
        with ui.sidebar_section(label="ACCOUNT"):
            ui.sidebar_item("Settings", icon="settings", href="/settings")

Three pieces, all V1-derived but consolidated :

- **Sidebar** — the ``<aside>`` container. Drives the
  ``current_path`` reactive via ``bz-data`` + window listeners on
  ``popstate`` / ``htmx:after-request`` so the active
  ``SidebarItem`` highlights live without a server round-trip when
  the URL changes. ``open=`` (literal or ClientBinding) drives
  ``data-open`` which the theme reads to fade out labels + badges
  via ``md:group-data-[open=false]:*`` Tailwind selectors. The
  sidebar is DESKTOP navigation chrome only — responsive mobile nav
  is the app layout's job (``if Screen().is_mobile:``), not built
  into this component.
- **SidebarSection** — optional grouping with an uppercase label
  that hides on collapse.
- **SidebarItem** — the one nav-row primitive. When ``href`` is
  passed AND we're inside an ``@layout`` (the render context
  carries the layout name on ``ctx.layout_stack``), the item
  auto-injects ``hx-get`` / ``hx-target=#outlet_<layout>`` /
  ``hx-swap=morph:innerHTML`` / ``hx-push-url=true`` so the click
  partial-navigates without reloading the layout. The active
  highlight is driven by a reactive ``bz-attr:data-active`` comparing
  the item's href to the sidebar's ``current_path``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    TOGGLE_NEAREST_SIDEBAR,
    anchored_dismiss_init,
    anchored_panel_effect,
    bool_attr,
    escape_init,
    imperative_listeners,
    install_open_close_toggle,
    modal_root_effect,
    server_sync_marker,
    teleport_to_body,
    unwrap_transparent,
)
from bretzel.components.navigation._wiring import (
    capture_layout,
    current_path_resync_init,
    current_path_scope,
    is_external_href,
    render_badge,
    wire_nav_item,
)
from bretzel.components.navigation.sidebar.theme import (
    SIDEBAR_FOOTER_ITEM_THEME,
    SIDEBAR_FOOTER_THEME,
    SIDEBAR_ITEM_THEME,
    SIDEBAR_THEME,
)
from bretzel.components.primitives.divider import Divider
from bretzel.components.primitives.icon import Icon
from bretzel.components.primitives.menu_item import MenuItem
from bretzel.core.tree import Element
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.render.context import maybe_current_context


def _icon_name(icon: Any) -> str | None:
    """Normalise a title/footer ``icon=`` argument to a bare name string.

    Accepts ``"zap"`` (a name, optionally set-prefixed like ``"mdi:home"``)
    OR a built :class:`Icon` component (``ui.icon("zap")``). The sidebar
    title styles the glyph itself, so we only need the name — passing a
    full ``Icon`` is a convenience that should never crash. Returns
    ``None`` for a falsy icon.
    """
    if not icon:
        return None
    if isinstance(icon, str):
        return icon
    if isinstance(icon, Component):
        # Read the public ``name`` reactive prop (an Icon exposes "zap") ;
        # any other component without one yields None.
        name = getattr(icon, "name", None)
        return str(name) if name else None
    return str(icon)


def _iconify_ref(name: str) -> str:
    """Full iconify ``set:name`` reference for a glyph : honour an explicit
    set prefix ("mdi:home"), default to lucide for a bare name."""
    return name if ":" in name else f"lucide:{name}"


# ───────────────────────────────────────────────────────────────────────────
# Sidebar — root container
# ───────────────────────────────────────────────────────────────────────────


class Sidebar(Component):
    """Render a collapsible application sidebar."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    DEFAULT_TAG: ClassVar[str] = "aside"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("open",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("open", "close", "toggle")
    # Accepts literal / server-resolved / ClientBinding. Drives the
    # desktop expand/collapse.
    open: Any = reactive_prop(default=True, emit_attr=False, writes=True)
    width: str = reactive_prop(default="md", emit_attr=False)
    # ONE axis: what "collapsed" means. Replaces the ``variant=``
    # (rail/drawer) + ``collapsible=`` (True/False) pair, which made two
    # props for a single decision and let an absurd combination through
    # (``collapsible=False`` + drawer = a sidebar you can neither
    # collapse nor reopen).
    #
    #   "rail"      collapsed → 64px icon strip, IN the flow
    #   "offcanvas" collapsed → zero width, in the flow, content spreads
    #   "overlay"   closed → absent; open → floats above the content,
    #               dimmed backdrop, Escape, scroll locked
    #   "none"      never collapses, no chevron rendered
    #
    # ``overlay`` is the mode you mount on a phone — it is the ONLY one
    # not gated on ``md:``, cf. the theme.
    collapsible: str = reactive_prop(default="rail", emit_attr=False)

    #: The four legal values, read by the constructor's guard AND by the
    #: theme. One source: a fifth mode is added here.
    COLLAPSE_MODES: ClassVar[tuple[str, ...]] = (
        "rail", "offcanvas", "overlay", "none",
    )

    # Axis shipped then CUT (2026-08-15), on the opinionation rule's
    # decisive test: "would we have this component in two shapes in the
    # SAME app?". No — an app has a single side nav, and it is on the
    # left. No call site in the repository passed ``side="right"``; the
    # only one was the bench card that demonstrated it.
    #
    # Right mode was half dead anyway: the rail's tooltip anchors its X
    # on ``aside.getBoundingClientRect().right + 8`` (cf.
    # ``SidebarItem.render``), so in ``side="right"`` the panel went off
    # screen.
    #
    # ⚠️ The guard is not politeness — same reason as
    # ``bottom_bar._CUT``, of which this is the exact copy: without it,
    # the base layer absorbs the unknown kwarg into the raw attrs and
    # ``ui.sidebar(side="right")`` would emit an HTML attribute
    # ``side="right"`` **in silence**, changing nothing in the render.
    _CUT: ClassVar[dict[str, str]] = {
        "side": (
            "a side nav lives on the left — the two sides never coexist "
            "in the same app, so it is a theme decision"
        ),
        "variant": (
            "merged into `collapsible=` on 2026-08-15 — it never said "
            'anything other than "what the collapsed form looks like". '
            'Write `collapsible="rail"` (ex-variant="rail") or '
            '`collapsible="offcanvas"` (ex-variant="drawer")'
        ),
    }

    def __init__(
        self,
        *,
        open: Any = None,
        width: str | None = None,
        collapsible: str | None = None,
        **kwargs: Any,
    ) -> None:
        # ``collapsible`` was a BOOL until 2026-08-15. A call left in
        # the old shape would pass here without a sound — ``True`` is
        # none of the four modes, so the theme would compose no collapse
        # rule and the sidebar would simply stop collapsing, in silence.
        # The message says what to write.
        if isinstance(collapsible, bool):
            raise ComponentUsageError(
                f"ui.sidebar(collapsible={collapsible!r}): `collapsible=` "
                f"is no longer a boolean, it is the collapse mode. Write "
                f'`collapsible="rail"` (ex-True) or `collapsible="none"` '
                f"(ex-False)."
            )
        if collapsible is not None and collapsible not in self.COLLAPSE_MODES:
            raise ComponentUsageError(
                f"ui.sidebar(collapsible={collapsible!r}): unknown mode. "
                f"The four modes are {', '.join(self.COLLAPSE_MODES)}."
            )
        for name, why in self._CUT.items():
            if name in kwargs:
                raise ComponentUsageError(
                    f"ui.sidebar has no `{name}=`: {why}. "
                    f"Override the theme's `root` slot to change that — "
                    f'Bretzel(theme=Theme(components={{"sidebar": '
                    f'{{"slots": {{"root": "…"}}}}}})), or '
                    f'`slots={{"root": "…"}}` on the instance for a '
                    f"one-off."
                )
        # Direct forward: the base layer drops reactive ``None`` kwargs
        # (keeps the default) — no more manual guard.
        super().__init__(
            open=open,
            width=width,
            collapsible=collapsible,
            **kwargs,
        )
        # Write-only imperative API ``.open()`` / ``.close()`` /
        # ``.toggle()`` — installed as instance attributes (shadowing the
        # ``open`` descriptor) by the base helper, identical to the 4
        # open-driven overlays (write-through binding ∪ dispatch). Cf.
        # `imperative-api.md`.
        install_open_close_toggle(self)
        # The request's registry. It serves two questions that can only
        # be answered once the page is built: WHICH bar an argument-less
        # ``ui.sidebar_trigger`` speaks to, and whether that bar has a way
        # of being reopened
        # (``base/_wiring.check_sidebars_are_reachable``).
        ctx = maybe_current_context()
        if ctx is not None:
            ctx.sidebars.append(self)


    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        widths = theme.get("widths", {})
        collapse = theme.get("collapse", {})

        width_key = self._reactive_values.get("width") or "md"
        mode = self._reactive_values.get("collapsible") or "rail"
        # ``overlay`` takes the sidebar out of the flow: it becomes a
        # modal panel (dimmed backdrop, Escape, scroll locked). It is the
        # only mode that asks for wiring beyond the classes.
        is_overlay = mode == "overlay"

        # ── ``open`` resolution — literal vs binding ─────────────────
        # ``data-open`` reflects the desktop expanded state. The theme
        # composes ``data-[open=false]`` selectors per variant : rail
        # narrows to a 64px icon strip, drawer collapses to width 0.
        open_binding = self._binding_metadata.get("open")
        open_initial = bool(self._reactive_values.get("open"))
        initial_open = "true" if open_initial else "false"
        if open_binding is not None:
            bound_open = True
            open_expr = open_binding.binding_path()
            data_open_expr = open_expr
        else:
            bound_open = False
            open_expr = "open"
            data_open_expr = "open"

        root_class = " ".join(
            p
            for p in (
                slots.get("root", ""),
                widths.get(width_key, ""),
                collapse.get(mode, ""),
            )
            if p
        )

        attrs = self.emit_attrs()
        attrs["class"] = root_class
        attrs.setdefault("role", "navigation")
        attrs.setdefault("aria-label", "Sidebar")
        # Stable marker, read by ``ui.sidebar_trigger`` when it could
        # not resolve an id (a bar built in ANOTHER render than its own —
        # a zone refresh, for instance). Same gesture as shadcn's
        # ``data-sidebar``: a named hook rather than a tag selector,
        # because a page is allowed to have another ``<aside>``.
        attrs.setdefault("data-bz-sidebar", "")
        # Static initial state + reactive override. Theme rules read
        # ``data-open`` (desktop expand/collapse).
        # Runtime quirk : ``bz-attr:attr="expr"`` REMOVES the attribute
        # when ``expr`` is boolean ``false`` (the boolean-HTML-attr
        # idiom — sensible for ``disabled`` / ``hidden`` / ``checked``,
        # disastrous for data-attrs since we want the literal string
        # ``"false"`` so CSS ``[data-open="false"]`` selectors match.
        # Force a string via ternary so the runtime always writes a
        # value.
        # ⚠️ In ``none`` mode, ``data-open`` is FROZEN at ``true``, and
        # the reactive attribute is not emitted at all.
        #
        # "none" means: this sidebar has no collapsed state. Yet the
        # collapse is decided in TWO places — the WIDTH comes from the
        # ``collapse`` table (so from the mode), but everything else (the
        # logo that centres itself, the section label that becomes a
        # rule, the labels and badges that disappear) is gated on
        # ``md:group-data-[open=false]/sidebar:``, so on ``data-open``
        # ALONE. Two keys for a single decision.
        #
        # Consequence measured on 2026-08-15:
        # ``ui.sidebar(collapsible="none", open=False)`` rendered a
        # FULL-WIDTH sidebar with collapsed content — centred logo, a
        # rule in place of the section title, rows reduced to their icon.
        # 12 child rules fired while no width rule did.
        #
        # Freezing the attribute rather than going and gating the 12
        # rules on the mode: the mode says there is no collapsed state,
        # so the collapsed state must simply never be writable.
        # ``.toggle()`` on a ``none`` sidebar becomes a no-op, which is
        # the contract.
        if mode == "none":
            attrs["data-open"] = "true"
        else:
            attrs.setdefault("data-open", initial_open)
            attrs["bz-attr:data-open"] = bool_attr(data_open_expr)
        # ``data-collapse`` replaces ``data-variant``: it is the mode
        # that is carried, and the name follows the prop.
        attrs.setdefault("data-collapse", mode)

        # bz-data layout :
        #  - ``current_path`` : same path tracking as before, used by
        #    every SidebarItem to compute active-link state without a
        #    server round-trip on browser back/fwd.
        #  - ``open`` : present ONLY when no external binding drives
        #    the desktop state, so the chevron can flip something.
        # ``rail_tip`` / ``rail_tip_x`` / ``rail_tip_y`` feed the rail's
        # SHARED tooltip panel (cf. the theme's ``rail_tip`` slot). Each
        # SidebarItem writes its label and its row's rect there on hover;
        # the panel moves instead of existing in 62 copies. Empty =
        # nothing hovered, so panel hidden.
        rail_tip = "rail_tip: '', rail_tip_x: 0, rail_tip_y: 0"
        if bound_open:
            bz_data = current_path_scope(rail_tip)
        else:
            # ``open`` lives in a scope signal, so ``scope.absorb``
            # PRESERVES it across a morph (that is intended: a
            # neighbouring refresh must not close the menu you have just
            # opened). Consequence: without a marker, an
            # ``open=state.field`` changed SERVER-side is never
            # re-adopted — the menu would stay open. Hence the
            # ``_serverSync``.
            sync = server_sync_marker(
                "open", enabled=self._value_server_backed("open")
            )
            # ⚠️ The comma after ``{initial_open}`` belongs to the
            # CALLER, and the marker carries ITS OWN at the end — that is
            # the contract documented on ``server_sync_marker`` ("leading
            # space + trailing comma") and the shape Select/Slider/
            # Combobox use. Writing ``{initial_open}{sync}, `` produced
            # ``open: true _serverSync: ['open'],,``: an invalid literal,
            # so the aside's WHOLE scope failed to parse — no more
            # ``current_path`` (no active highlight), no more ``open``
            # (dead chevron) and no more rail tooltip. Silent on the
            # server side, a single console SyntaxError on the client
            # side. The case only appears on ``open=state.field`` — no
            # example in the repository passed one, hence six months of
            # survival.
            bz_data = current_path_scope(
                f"open: {initial_open},{sync} {rail_tip}"
            )
        attrs.setdefault("bz-data", bz_data)
        # Resync ``current_path`` — shared with Navbar (the detail of
        # the two listeners and of the compare-then-assign guard is
        # documented on the helper).
        attrs.setdefault("bz-init", current_path_resync_init())
        # ⚠️ ``bz-init`` is ALREADY set above (resync ``current_path``).
        # Overlay mode wants a second one (Escape): we COMPOSE, we do not
        # overwrite — it is traps.md's "clobbered internal handler" trap,
        # the one that ate on_focus/on_blur on 2026-07-18.
        _base_init = attrs["bz-init"]

        # ── Imperative API listeners ─────────────────────────────────
        # Wire ``bz-open`` / ``bz-close`` / ``bz-toggle`` on the root so
        # ``.open()`` / ``.close()`` / ``.toggle()`` work in both bound
        # and unbound modes (uniform contract). Bound mode : the
        # binding setter writes to ``open_expr`` directly, the event
        # arrives at this listener but the assignment is a no-op
        # because the binding has already settled the value. Cheap,
        # idempotent, simpler than gating. Shared with Dialog/Drawer/
        # Dropdown/Popover via the single-source helper (no drift).
        for _ev, _handler in imperative_listeners(open_expr).items():
            attrs.setdefault(_ev, _handler)

        # ── Modal wiring — ``overlay`` mode only ─────────────────────
        # A phone menu opened above the content must close on Escape and
        # must not let the page scroll behind it. Both helpers come from
        # ``base/_wiring`` — the SAME ones as Dialog and Drawer — so
        # nothing is rewritten here and the ``overlay/`` group is not
        # imported (anti-rule 5).
        #
        # The in-flow modes (rail / offcanvas) most certainly do not want
        # them: collapsing a rail on desktop must neither steal the
        # Escape key nor lock the page's scroll.
        if is_overlay:
            attrs["bz-init"] = f"{_base_init}; {escape_init(open_expr)}"
            attrs["bz-effect"] = modal_root_effect(open_expr)

        # ── Children layout ──────────────────────────────────────────
        children: list[Any] = []
        # ⚠️ **The auto floating chevron was REMOVED on 2026-08-21.**
        # It rendered when the bar had no ``SidebarTitle``, at
        # ``absolute top-2 right-2`` — that is to say exactly under the
        # edge, which takes the right-hand 24 px over the full height.
        # Measured by the gate: the click never reached it any more, a
        # 30 s timeout on a button that was nevertheless "visible,
        # enabled and stable". Two commands in the same place, one of
        # them unreachable.
        #
        # Shifting it would have been a bandaid: the edge does the same
        # job, in both states, over the full height — and without the
        # component deciding where an app affordance goes, which the
        # comment below already holds against its teleported
        # predecessor.
        # ── The clickable edge ───────────────────────────────────────
        # It lives HERE, on the bar, and not in ``SidebarTitle``: a bar
        # with no title must be able to collapse too, and it is the
        # aside's BORDER we make reachable — a detail of the bar, not of
        # its header.
        #
        # It does not replace the chevron: the two coexist, as at shadcn,
        # which ships its rail ON TOP OF a visible trigger. What it
        # replaces is the only gesture that did not exist on a machine
        # without hover.
        if mode != "none":
            children.append(_render_rail_edge(slots, open_expr))
        # ⚠️ There is no longer an auto-rendered reopen button. One
        # existed for ``variant="drawer"``: collapsed, the sidebar
        # disappeared along with its chevron, so the component teleported
        # a hard-coded floating hamburger under ``<body>`` (``top-3
        # left-3 z-50``). It was the component deciding where an APP
        # affordance goes — and it would have made a second one if the
        # app already had its own topbar. The dev places their button
        # where they want and calls ``sb.toggle()``; the imperative API
        # exists for that.
        # ⚠️ The backdrop is NO LONGER a child of the aside, and above
        # all it is no longer teleported — it becomes a SIBLING, under a
        # ``display:contents`` root (cf. the end of this ``render``). See
        # the comment down there: it is the only position from which its
        # ``z-40`` can be compared to the aside's ``z-50``.
        backdrop = _render_backdrop(theme, open_expr) if is_overlay else None

        # ── User children : pin header + footer, scroll the middle ───
        # The aside is a rigid ``flex-col h-screen`` frame ; it no longer
        # carries the scroll itself (it used to — ``overflow-y-auto`` on
        # the root — which scrolled the FOOTER away with an overflowing
        # nav list). So we partition the user children by type :
        #   • title   → pinned header (``shrink-0``)
        #   • footer  → pinned footer (``shrink-0``)
        #   • the rest → in the ``flex-1 min-h-0 overflow-y-auto`` box,
        #     the ONLY part that scrolls.
        #
        # ⚠️ **The sorting is done on the RENDERED node, not on the
        # child's Python type** — and that is the 2026-08-23 correction.
        # The version that tested ``isinstance(child, SidebarFooter)``
        # missed every WRAPPED footer: a ``@refreshable`` renders a
        # ``_RefreshableSection``, a ``ui.fragment`` renders a
        # ``Fragment``. The footer then fell into the middle, so INTO the
        # scrolling box.
        #
        # Measured on `examples/crm`, whose footer is a
        # ``@refreshable(deps=[ViewerPrefs])`` — it does have to refresh
        # when you switch account: the account block slid from 656 to
        # 504 px when you scrolled the nav, while a bare footer did not
        # move a pixel. The playground never showed the defect because
        # its footer is not in a zone.
        #
        # A node that carries TWO roles, or a role plus nav content,
        # stays in the middle: one cannot pin half a node, and cutting it
        # up would be deciding in the app's place.
        # We replicate ``_render_children``'s ``is_rendering`` bookkeeping
        # (sub-components built inside a ``render()`` skip parent-stack
        # registration) since we walk ``_children`` by hand to keep the
        # Python type for the partition.
        title_nodes: list[Any] = []
        middle_nodes: list[Any] = []
        footer_nodes: list[Any] = []
        ctx = maybe_current_context()
        prev_rendering = ctx.is_rendering if ctx is not None else None
        if ctx is not None:
            ctx.is_rendering = True
        try:
            for raw in getattr(self, "_children", []):
                # ``unwrap_transparent``: without it, a WRAPPED footer
                # — and a real app's is, it shows the signed-in account
                # so it has to refresh — is no longer an instance of
                # ``SidebarFooter`` and falls into the middle, that is to
                # say INTO the scrolling zone. The rewrap gives its
                # ``bz-id`` back to the zone.
                child, rewrap = unwrap_transparent(raw)
                node = self._render_one(child)
                if node is None:
                    continue
                node = rewrap(node)
                if isinstance(child, SidebarTitle):
                    title_nodes.append(node)
                elif isinstance(child, SidebarFooter):
                    footer_nodes.append(node)
                else:
                    middle_nodes.append(node)
        finally:
            if ctx is not None:
                ctx.is_rendering = bool(prev_rendering)

        children.extend(title_nodes)
        if middle_nodes:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": slots.get("scroll", "")},
                    children=tuple(middle_nodes),
                )
            )
        children.extend(footer_nodes)

        # The rail's SHARED tooltip panel, last child of the aside.
        # ``aria-hidden``: it is purely decorative — each entry's
        # accessible name travels on its own ``aria-label`` (cf.
        # ``SidebarItem.render``), which is the right a11y for an
        # icon-only rail anyway and does not depend on hover.
        children.append(
            Element(
                tag="div",
                attrs={
                    # ``bz-c-text``: the rail's panel is a tooltip, so
                    # it carries a tooltip's NEUTRAL tint and not the
                    # bar's colour. Its bridge is set here because it
                    # diverges from the root's.
                    "class": f'{slots.get("rail_tip", "")} bz-c-text'.strip(),
                    "role": "tooltip",
                    "aria-hidden": "true",
                    "data-tip": "off",
                    "bz-attr:data-tip": "rail_tip ? 'on' : 'off'",
                    "bz-attr:style": (
                        "'top:' + rail_tip_y + 'px;left:' + rail_tip_x + 'px'"
                    ),
                },
                children=(
                    # ⚠️ ``bz-text`` writes ``textContent``, which
                    # ERASES the node's children. It therefore lives on
                    # an inner ``<span>``, not on the panel — otherwise
                    # the arrow would be swept away on the first hover.
                    Element(
                        tag="span",
                        attrs={"bz-text": "rail_tip"},
                        children=(),
                    ),
                    Element(
                        tag="div",
                        attrs={"class": slots.get("rail_tip_arrow", "")},
                        children=(),
                    ),
                ),
            )
        )

        aside = Element(tag=self._tag, attrs=attrs, children=tuple(children))
        if backdrop is None:
            return aside

        # ── Overlay mode: the backdrop and the aside must be SIBLINGS ─
        #
        # A ``z-index`` only compares between siblings of a stacking
        # context — it does not cross a boundary. The backdrop therefore
        # lived **teleported under ``<body>``** until 2026-08-15, on the
        # assumption that it would be "a sibling of the sidebar" there.
        # It only is if the aside is itself a direct child of ``<body>``,
        # which no real shell does: the recommended shell is
        # ``fixed inset-0`` (``traps.md``), and ``position: fixed``
        # CREATES a context. The aside's ``z-50`` therefore stayed locked
        # inside it, the real comparison became "shell (``z-auto``)
        # against backdrop (``z-40``)", and the backdrop covered the
        # whole app — sidebar included, which it blurred with its
        # ``backdrop-filter``.
        #
        # ``display:contents`` (Tailwind ``contents``) is what settles
        # it: the root generates NO box, so no stacking context, and its
        # two children take part in the shell's. ``z-40`` and ``z-50``
        # finally compare there. It is also the structure of
        # ``ui.dialog`` / ``ui.drawer``, which never had the defect
        # because they keep their pair in the same place — three
        # components, a single way of doing it (principle 4).
        #
        # The caller's ``classes=`` is copied onto the ASIDE: the
        # universal wrap would set it on this root, where it would be
        # inert (a box that does not exist is not styled).
        # ⚠️ The SCOPE moves up to the root — without that the backdrop
        # sees nothing any more. The runtime resolves a ``bz-*`` by
        # walking up to the nearest ancestor carrying ``bz-data``; a
        # backdrop that has become a SIBLING of the aside therefore no
        # longer has the scope above it, and its ``bz-attr:data-open``
        # evaluates into the void. Measured by shipping it: the backdrop
        # stayed at ``data-open="true"`` with the sidebar closed, so
        # opaque and blurred over the whole screen — exactly the symptom
        # being repaired.
        #
        # The aside keeps seeing it: it descends from this root, so the
        # walk finds it. One scope, two consumers.
        # The component's IDENTITY follows the scope onto the root —
        # ``id`` included, and with it the imperative listeners.
        #
        # ⚠️ Do NOT leave the ``id`` on the aside: the base layer stamps
        # ``id`` + ``bz-id`` on any root that carries a ``bz-data`` and
        # does not yet have an ``id`` (``_stamp_scope_id``). The wrapper
        # therefore got one — the SAME as the aside. Two nodes, one id:
        # ``document.getElementById`` returns the first, that is to say
        # the wrapper, and the imperative API dispatched ``bz-toggle`` on
        # a node with no listener. Measured: the hamburger no longer did
        # anything, in silence, while the state and the render were
        # correct.
        #
        # The three ``bz-on:bz-*`` therefore migrate with the ``id`` they
        # serve. The rest (``bz-init``, ``bz-effect``,
        # ``bz-attr:data-open``) stays on the aside: it describes the
        # aside, and scope resolution walks up here anyway.
        aside_attrs = dict(aside.attrs)
        root_attrs: dict[str, Any] = {"class": "contents"}
        for key in (
            "bz-data",
            "bz-id",
            "id",
            "bz-on:bz-open",
            "bz-on:bz-close",
            "bz-on:bz-toggle",
        ):
            if key in aside_attrs:
                root_attrs[key] = aside_attrs.pop(key)

        # The caller's ``classes=`` is copied onto the ASIDE: the
        # universal wrap would set it on this root, where it would be
        # inert (a box that does not exist is not styled).
        user_cls = self._user_classes_str()
        if user_cls:
            aside_attrs["class"] = (
                f"{aside_attrs.get('class', '')} {user_cls}".strip()
            )

        aside = Element(
            tag=aside.tag, attrs=aside_attrs, children=aside.children
        )
        return Element(tag="div", attrs=root_attrs, children=(backdrop, aside))


# ───────────────────────────────────────────────────────────────────────────
# SidebarTrigger — the button that reopens it, placed by the app
# ───────────────────────────────────────────────────────────────────────────


class SidebarTrigger(Component):
    """Render a button that opens or closes a sidebar."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    #: ``panel-left`` and not ``menu``: it is the glyph lucide, shadcn
    #: and VS Code associate with "side bar", so it says WHAT IT OPENS.
    #: It is also the one the :class:`SidebarTitle` chevron already
    #: carries — the two commands look alike because they do the same
    #: thing.
    icon: str | Component = reactive_prop(
        default="panel-left", emit_attr=False
    )
    #: The density of the bar it sits in — a compact top bar wants
    #: ``sm``. It is the only axis that varies WITHIN one app.
    size: str = reactive_prop(default="md", emit_attr=False)

    # Two axes cut on the opinionation rule's decisive test: "would we
    # have this component in two shapes in the SAME app?". No — an app
    # has one side-bar trigger, and it looks like the rest of its top
    # bar. ``icon=`` survives the same test because the disagreement is
    # real and measurable: this repository writes ``menu`` in
    # ``examples/crm`` and ``panel-left`` in ``examples/chat``.
    #
    # ⚠️ The guard is not politeness — same reason as
    # ``bottom_bar._CUT``, of which this is the copy: without it, the
    # base layer absorbs the unknown kwarg into the raw attrs, and
    # ``ui.sidebar_trigger(variant="solid")`` would emit an HTML
    # attribute ``variant="solid"`` **in silence**, changing nothing in
    # the render.
    _CUT: ClassVar[dict[str, str]] = {
        "variant": (
            "the button's look is decided once per app, along with the "
            "rest of its top bar: it is a theme decision"
        ),
        "color": (
            "same — and `classes=` is still there for the one-off. If "
            "you really want a button of your own, the tier-2 escape "
            "hatch is whole: `ui.icon_button(…, on_click=sb.toggle())`"
        ),
    }

    def __init__(
        self,
        sidebar: Any = None,
        *,
        icon: str | Component | None = None,
        size: str | None = None,
        **kwargs: Any,
    ) -> None:
        for name, why in self._CUT.items():
            if name in kwargs:
                raise ComponentUsageError(
                    f"ui.sidebar_trigger has no `{name}=`: {why}."
                )
        super().__init__(icon=icon, size=size, **kwargs)
        self._sidebar: Any = None
        #: The fallback: aim at the stable marker and resolve at CLICK
        #: time. Replaced by the command by id as soon as a bar is known.
        self._command: str = TOGGLE_NEAREST_SIDEBAR
        if sidebar is not None:
            self.bind_sidebar(sidebar)
        else:
            # Resolved by ``base/_wiring.wire_sidebar_triggers`` once
            # the tree is built — the order of writing must not decide
            # whether the button works.
            ctx = maybe_current_context()
            if ctx is not None:
                ctx.sidebar_triggers.append(self)

    def bind_sidebar(self, sidebar: Any) -> None:
        """Attach this trigger to *sidebar*.

        Called either at construction (``ui.sidebar_trigger(sb)``), or by
        the resolution pass. Going through ``sidebar.toggle()`` is not a
        detail: it is what marks the bar as drivable, so what silences
        :func:`check_sidebars_are_reachable`. Both tiers of the API take
        the same path.
        """
        self._sidebar = sidebar
        self._command = sidebar.toggle()

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        button = IconButton(
            self._reactive_values.get("icon") or "panel-left",
            variant="ghost",
            size=self._reactive_values.get("size") or "md",
            color="muted",
            aria_label=text("sidebar.toggle"),
            on_click=self._command,
        )
        Component._detach_from_parent(button)
        node = button.render()
        attrs = dict(node.attrs)
        # The universal kwargs (``classes=``, ``id=``, ``visible=``,
        # ``tooltip=``…) are resolved by the base layer on THIS
        # component: we pour them back onto the button actually
        # rendered, otherwise they would fall into the void — the silent
        # failure mode ``_apply_universal_modifiers`` documents.
        mine = self.emit_attrs()
        classes = " ".join(
            c for c in (attrs.get("class", ""), mine.pop("class", "")) if c
        )
        attrs.update(mine)
        if classes:
            attrs["class"] = classes
        if self._sidebar is not None:
            # What the tier-2 escape hatch will never do by hand.
            attrs["aria-controls"] = self._sidebar.id
        return Element(tag=node.tag, attrs=attrs, children=node.children)


# ───────────────────────────────────────────────────────────────────────────
# SidebarSection — optional grouping with a label
# ───────────────────────────────────────────────────────────────────────────


class SidebarSection(Component):
    """Group of items with an optional uppercase label."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    # ``None`` disables the check, so a binding on ``label`` was
    # accepted then thrown away in silence. ``()`` makes the refusal
    # explicit.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    label: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        label: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(label=label, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        label = self._reactive_values.get("label")

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("section", "")

        children = list(self._render_children())
        if label:
            # Rail divider — the collapsed-rail form of the label. The
            # uppercase caption (``section_label``) hides at md+ collapse ;
            # in its place we drop a real :class:`~bretzel.components.
            # primitives.divider.Divider` (dogfooding — a primitive, so
            # importable here per anti-rule 5), so the caption visually
            # turns into a separator line. Only labelled sections get it :
            # an unlabelled group has no caption to collapse.
            #
            # The Divider's own root is ``flex`` ; ``hidden`` can't reliably
            # override a hardcoded ``flex`` (Tailwind orders ``display``
            # utilities by source, not class-attr order). So the rail-only
            # gate rides a PLAIN wrapper div (no base ``display``), and the
            # Divider sits inside it untouched.
            divider = Divider(color="muted")
            Component._detach_from_parent(divider)
            # Build the header in DOM order — label first, divider second —
            # then prepend it (only one of the two is ever visible : the
            # label when expanded, the divider in the rail).
            header = [
                Element(
                    tag="div",
                    attrs={"class": slots.get("section_label", "")},
                    children=(self.emit_text_slot(label),),
                ),
                Element(
                    tag="div",
                    attrs={"class": slots.get("section_divider", "")},
                    children=(divider.render(),),
                ),
            ]
            children = header + children

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))


# ───────────────────────────────────────────────────────────────────────────
# SidebarTitle — the header : logo + title + collapse toggle
# ───────────────────────────────────────────────────────────────────────────


class SidebarTitle(Component):
    """Render the sidebar title and optional home link."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_THEME
    THEME_KEY: ClassVar[str] = "sidebar"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    title: str = reactive_prop(default="", emit_attr=False)
    #: ⚠️ The default is a GLYPH, not ``None`` — same pattern as
    #: ``ui.datatable(empty_icon="inbox")``. Without it, a title written
    #: with no ``icon=`` left the rail's head empty, and a collapsed rail
    #: showed a hole above its items (reported on screen on 2026-09-12).
    #: ``home`` and not something else: this link leads to ``href=``,
    #: whose default is ``/``. The glyph therefore describes what the
    #: link DOES.
    #:
    #: **For no mark at all: ``icon=""``.** Not ``icon=None`` — the base
    #: layer drops reactive kwargs at ``None`` to keep the default, so an
    #: explicit ``None`` is indistinguishable from an absent argument
    #: (checked). The empty string, on the other hand, reaches here.
    icon: str | Component | None = reactive_prop(default="home", emit_attr=False)
    href: str = reactive_prop(default="/", emit_attr=False, never_code=True)

    def __init__(
        self,
        title: str = "",
        *,
        icon: str | Component | None = "home",
        href: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(title=title, icon=icon, href=href, **kwargs)
        # (A ``ui.icon(...)`` passed as ``icon=`` is detached from the parent
        # by ``Component.__init__`` now — the systemic fix for the "component
        # passed as a prop renders twice" class, cf. traps.md.)

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # NO ``str(...)``: ``title`` is a textual slot, so it can carry
        # a Component — coercing it here shipped its Python repr into the
        # page (``emit_text_slot`` sorts it out downstream).
        title = self._reactive_values.get("title") or ""
        # ``icon`` accepts a bare name ("zap") OR a built ``ui.icon(...)``.
        # We read its NAME (the title sizes the glyph uniformly) and its
        # COLOUR : a bare string gets the brand ``primary`` ; a passed
        # ``ui.icon(...)`` keeps its OWN colour (default "current" = inherit
        # the brand link) so ``ui.icon("zap", color="warning")`` shows orange.
        icon_arg = self._reactive_values.get("icon")
        icon_name = _icon_name(icon_arg)
        icon_color = (
            (getattr(icon_arg, "color", None) or "current")
            if isinstance(icon_arg, Component)
            else "primary"
        )
        # The STEP **plus the icon's bridge**, and both are necessary:
        # the icon's colour can differ from the header's
        # (``ui.icon("zap", color="warning")`` in a ``primary`` bar), so
        # the bridge the base layer set on the root does not fit. We set
        # one on the glyph itself.
        #
        # ``current`` is a bridge like any other: ``bz-c-current`` starts
        # ``--bz-text`` from ``currentColor``, so the icon inherits the
        # brand link — the previous behaviour, identical.
        from bretzel.theme.bridges import bridge_class

        icon_text_class = f"text-(--bz-text) {bridge_class(icon_color)}"
        href = str(self._reactive_values.get("href") or "/")

        def _glyph(name: str, cls: str) -> Element:
            return Element(
                tag="iconify-icon",
                attrs={"icon": _iconify_ref(name), "class": cls},
                children=(),
            )

        # ── In-sidebar header : brand link + collapse chevron ────────
        brand_children: list[Any] = []
        if icon_name:
            brand_children.append(
                _glyph(icon_name, f"{slots.get('title_logo', '')} {icon_text_class}")
            )
        if title:
            brand_children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("title_text", "")},
                    children=(self.emit_text_slot(title),),
                )
            )
        brand = Element(
            tag="a",
            attrs={"href": href, "class": slots.get("title_brand", "")},
            children=tuple(brand_children),
        )
        # Collapse toggle — a real IconButton (hover / a11y). ``Icon(size="lg")``
        # = ``text-2xl`` = a 24 px glyph (like the logo and the title), in an
        # IconButton ``size="md"`` = an ``h-10 w-10`` box. The header lockup
        # therefore does not change size on collapse. Bubbling ``bz-toggle`` —
        # caught by the Sidebar root's ``bz-on:bz-toggle``.
        #
        # ⚠️ This comment claimed "Sized to MATCH the rail toggle
        # exactly" and pointed at a ``title_rail_toggle`` slot. Neither
        # the slot nor that second button exists: the auto floating
        # chevron was removed on 2026-08-21, and the ``toggle`` slot that
        # dressed it left with it on 2026-08-29 — nobody read it any
        # more.
        # ``panel-left`` and not a chevron: it is the glyph everybody
        # associates with "side bar" (lucide, shadcn, VS Code), so it
        # says WHAT IT COLLAPSES. A chevron says only a direction, and
        # there are already four others in the catalogue that mean
        # something else.
        toggle = IconButton(
            Icon("panel-left", size="lg"),
            variant="ghost",
            size="md",
            color="muted",
            aria_label=text("sidebar.toggle"),
            on_click=(
                "$el.dispatchEvent(new CustomEvent("
                "'bz-toggle', {bubbles: true}))"
            ),
            classes=slots.get("title_toggle", ""),
        )
        Component._detach_from_parent(toggle)
        toggle_node = toggle.render()

        # ── The rail's logo: a LINK, not a collapse button ──────────
        # It carried the logo and turned into a chevron on hover; the
        # click collapsed. Two defects at once: on a machine without
        # hover nothing announced the gesture (the logo stayed a logo),
        # and the logo changed job depending on the bar's state — link
        # when expanded, button when collapsed.
        #
        # The collapse now has its EDGE (``Sidebar._render_rail_edge``),
        # visible in both states, so the logo has only one job left:
        # leading to ``href=``.
        # ⚠️ **No rail mark WITHOUT a glyph.** An ``<a>`` with no child
        # is not "invisible": measured on 2026-09-12 on a collapsed
        # rail, it occupies **40 × 40 px** at the head of the bar and
        # takes the FIRST focus — the first tab lands on a link you
        # cannot see. Same family as the closed overlay that kept its
        # commands reachable (``traps.md`` § A11y).
        #
        # Reported by the user, who saw the hole: "you did not put a
        # logo, and now we see an empty space". With no glyph, the rail
        # therefore starts at its items — it fills entirely, which is
        # what it offered — and the reopening affordance stays the EDGE
        # (``_render_rail_edge``), which is visible in both states.
        rail_brand = Element(
            tag="a",
            attrs={
                "href": href,
                "class": slots.get("title_rail_brand", ""),
                # The title disappears in the rail, so the link has
                # only its glyph left: with no accessible name it
                # announces itself as "link" and nothing else. It is the
                # class ``test_icon_only_controls_are_named`` has guarded
                # since finding 18.
                #
                # Only a STRING, as ``ui.icon_button`` does with its
                # ``tooltip=``: a ``title=ui.text(...)`` is rich content,
                # and flattening a tree into a label would produce a
                # sentence nobody wrote.
                "aria-label": (
                    title.strip() if isinstance(title, str) and title.strip()
                    else text("sidebar.home")
                ),
            },
            children=(
                _glyph(
                    icon_name,
                    f"text-2xl {icon_text_class}",
                ),
            ) if icon_name else (),
        )

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("title_root", "")

        children: list[Any] = [brand, toggle_node]
        if icon_name:
            children.append(rail_brand)

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))


# ───────────────────────────────────────────────────────────────────────────
# SidebarItem — the nav row primitive
# ───────────────────────────────────────────────────────────────────────────


class SidebarItem(Component):
    """One nav row : icon + label + optional badge."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_ITEM_THEME
    THEME_KEY: ClassVar[str] = "sidebar_item"
    IS_CONTAINER: ClassVar[bool] = False
    EVENTS: ClassVar[tuple[str, ...]] = ("click",)
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    # Curated reactive surface — active state (current_path derived
    # at runtime, see sidebar __init__) + badge content + disabled.
    # label and href are design-time (routes don't change live).
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

        # Capture the enclosing layout name at construction time —
        # the ``with @layout(): ...`` block is still active so
        # ``ctx.layout_stack`` is populated. We need this for the
        # ``hx-target`` attribute baked at render time.
        self._captured_layout: str | None = capture_layout()

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})

        # Reading + wiring: the shared body of the three nav items
        # (navigation/_wiring.py). What follows is specific to the
        # sidebar.
        w = wire_nav_item(self, slots)
        tag, attrs = w.tag, w.attrs
        label, href, disabled = w.label, w.href, w.disabled
        badge_value, badge_binding = w.badge_value, w.badge_binding

        # Sidebar-specific extra: on mount, if the item resolves to
        # active (a deep refresh in a list of 50+ entries), bring it back
        # into the viewport. ``block: 'nearest'`` is a no-op when it is
        # already visible — the common case — and pushes only the minimum
        # otherwise. Deferred through ``$nextTick`` so the runtime has
        # applied ``bz-attr:data-active`` before we read it.
        #
        # Placed AFTER the three ``apply_*`` (before, it lived between
        # the partial-nav and the disabled): ``apply_disabled`` only
        # removes the click channels, never the ``bz-init``, so the
        # result is the same.
        if href and self._captured_layout and not is_external_href(href):
            attrs.setdefault(
                "bz-init",
                "$nextTick(() => { if ($el.dataset.active === 'true') "
                "$el.scrollIntoView({ block: 'nearest' }); })",
            )

        # In the collapsed rail the label is ``hidden`` (icon-only square),
        # so we bring the name back on hover — via the ONE shared panel the
        # Sidebar renders (slot ``rail_tip``), which this row moves onto
        # itself. Disabled rows are skipped : ``pointer-events-none`` /
        # ``tabindex=-1`` already make them unhoverable / unfocusable.
        #
        # ⚠️ ``isinstance(label, str)`` discriminates Component-vs-string,
        # and NOTHING ELSE: a binding never reaches here, because
        # ``Component.__init__`` files ``binding.value`` — a string — in
        # ``_reactive_values``, from where ``wire_nav_item`` reads that
        # label.
        #
        # ``label`` is a textual slot, so it accepts a Component. The
        # rail's tooltip, though, has only STRING targets — it goes into
        # an ``aria-label`` and into the JS literal of ``rail_tip = "…"``,
        # which ``json.dumps`` refuses. The row keeps its rich content;
        # the rail's tooltip keeps quiet, as for an entry with no label.
        show_rail_tip = isinstance(label, str) and bool(label) and not disabled

        # ── Children : icon + label + badge ──────────────────────────
        children: list[Any] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            Component._detach_from_parent(icon)
            children.append(Component.with_slot_class(
                icon.render(), slots.get("icon", ""),
            ))

        if label:
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("label", "")},
                    children=(self.emit_text_slot(label),),
                )
            )

        # ── Badge — reactive when bound, static otherwise ────────────
        # ``badge`` is in BINDABLE_PROPS, so a ClientBinding must emit a
        # live directive — not silently degrade to the static SSR snapshot.
        # The badge holds CONTENT (a count / short label), so the live
        # channel is ``bz-text`` (the pill's textContent tracks the bound
        # value), paired with ``bz-show`` so the pill hides when the value
        # goes empty/null — mirroring the static ``is not None`` gate.
        if badge_binding is not None:
            children.append(render_badge(
                badge_value, slots.get("badge", ""),
                reactive_path=self.path_of(badge_binding),
            ))
        elif badge_value is not None:
            children.append(render_badge(badge_value, slots.get("badge", "")))

        # ── Rail tooltip: feed the sidebar's SHARED panel ────────────
        # We no longer instantiate a ``ui.tooltip`` per entry (62
        # pre-rendered panels = 94 kB, a third of the sidebar, for an
        # affordance that only ever shows one). The entry merely writes
        # its label and its position into the aside's scope; the single
        # panel moves there. The "collapsed rail + desktop" gate is in
        # CSS on the panel, so there is no longer a ``matchMedia`` nor a
        # ``closest('aside')`` copied 62 times.
        #
        # ``aria-label`` carries the accessible name on the link itself:
        # in the rail the visible label is ``hidden``, and a tooltip on
        # hover is not a keyboard/screen-reader affordance. So it is both
        # more correct than before and independent of the panel.
        if show_rail_tip:
            attrs.setdefault("aria-label", label)
            # X on the RAIL's edge, not on the entry's: collapsed, the
            # entry is a ``w-10`` square centred (``mx-auto``) in a 64 px
            # rail, so its right edge falls 4 px INSIDE the rail and the
            # panel overlapped it (probe, 2026-07-27).
            # Y on the entry's centre; the half offset is done in CSS
            # (``-translate-y-1/2``), not with a guessed height.
            enter = (
                f"rail_tip = {json.dumps(label)}; "
                "rail_tip_x = $el.closest('aside')"
                ".getBoundingClientRect().right + 8; "
                "(r => { rail_tip_y = r.top + r.height / 2 })"
                "($el.getBoundingClientRect())"
            )
            # Compose, do not overwrite: a user ``on_mouseenter=`` has
            # already been set in ``attrs`` by ``emit_attrs``.
            # Overwriting it is traps.md's "clobbered internal handler"
            # trap (the on_focus/on_blur pass, 2026-07-18).
            for event, internal in (
                ("bz-on:mouseenter", enter),
                ("bz-on:mouseleave", "rail_tip = ''"),
                ("bz-on:focus", enter),
                ("bz-on:blur", "rail_tip = ''"),
            ):
                existing = attrs.get(event)
                attrs[event] = f"{existing}; {internal}" if existing else internal

        node = Element(tag=tag, attrs=attrs, children=tuple(children))

        return node


# ───────────────────────────────────────────────────────────────────────────
# SidebarFooter — account row + popover menu, pinned to the bottom
# ───────────────────────────────────────────────────────────────────────────


def _footer_initials(name: Any) -> str:
    """Derive up-to-2-char initials from a display name ("Jean Hoccart"
    → "JH", "Jean" → "JE"). Falls back to "?" for an empty name.

    ``name`` is a textual slot, so it also carries a Component — from
    which no initial can be derived (``.split()`` would raise). The
    fallback is the same "?" chip as for an empty name, decided HERE so
    that this literal has a single owner. A binding, on the other hand,
    arrives already resolved to a string: ``Component.__init__`` files
    ``binding.value`` in ``_reactive_values``."""
    parts = [p for p in name.split() if p] if isinstance(name, str) else []
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


class SidebarFooter(Component):
    """Render the footer region of a sidebar."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_FOOTER_THEME
    THEME_KEY: ClassVar[str] = "sidebar_footer"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    name: str = reactive_prop(default="", emit_attr=False)
    subtitle: str | None = reactive_prop(default=None, emit_attr=False)
    # ``never_code``: the string form is an image URL — same family as
    # ``ui.avatar(src=)``, so the same exposure to the false positive.
    avatar: str | Component | None = reactive_prop(
        default=None, emit_attr=False, never_code=True
    )
    # Colour axis — tints the avatar chip + focus ring. Set by the
    # ``bz-c-<colour>`` bridge class on the root, which installs the
    # eleven steps on the subtree (cf. ``color_bridge_class``); the theme
    # writes COMPLETE classes like ``bg-(--bz-bg)``. This comment said
    # "via ``{bg_color}`` in the theme" until 2026-09-07, that is to say
    # the mechanism from BEFORE the bridge.
    # Defaults to ``primary`` like every other Bretzel component
    # (Button / Avatar / SidebarItem …).
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        name: str = "",
        *,
        subtitle: str | None = None,
        avatar: str | Component | None = None,
        color: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(
            name=name,
            subtitle=subtitle,
            avatar=avatar,
            color=color,
            **kwargs,
        )

    def _render_avatar(self, avatar: Any, name: Any, avatar_cls: str) -> Element:
        if isinstance(avatar, Component):
            # A passed ``ui.avatar(...)`` carries its OWN size/shape/colour
            # (and is already detached by ``Component.__init__``) — render it
            # as-is, don't double-wrap it in the initials-chip styling.
            return Element(
                tag="span", attrs={"class": "shrink-0 inline-flex"},
                children=(avatar.render(),),
            )
        # ``avatar`` is now ``str | None`` (the Component case returned
        # above) : use it as initials text if given, else derive from name
        # (``_footer_initials`` owns the fallback for a non-textual name).
        text = avatar or _footer_initials(name)
        return Element(
            tag="span", attrs={"class": avatar_cls},
            children=(TextNode(text),),
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # Same as ``title`` above: textual slot, no coercion.
        name = self._reactive_values.get("name") or ""
        subtitle = self._reactive_values.get("subtitle")
        avatar = self._reactive_values.get("avatar")
        open_expr = "acct_open"

        # ── Trigger row ──────────────────────────────────────────────
        avatar_node = self._render_avatar(
            avatar, name, slots.get("avatar", "")
        )

        # ⚠️ ``emit_text_slot`` returns ``None`` for an EMPTY slot, and
        # a ``None`` in ``children`` makes the serialiser raise ("Cannot
        # serialize unknown Node type"). The name's span is the only one
        # of this file's six slots not guarded by an ``if`` — a
        # ``ui.sidebar_footer()`` with no name is legal, and it rendered
        # an empty span before. We keep that behaviour.
        name_node = self.emit_text_slot(name)
        meta_children: list[Any] = [
            Element(
                tag="span", attrs={"class": slots.get("name", "")},
                children=(name_node,) if name_node is not None else (),
            )
        ]
        if subtitle:
            meta_children.append(
                Element(
                    tag="span", attrs={"class": slots.get("subtitle", "")},
                    children=(self.emit_text_slot(subtitle),),
                )
            )
        meta = Element(
            tag="div", attrs={"class": slots.get("meta", "")},
            children=tuple(meta_children),
        )

        # Up/down chevron — Icon primitive (font-size sized, centered).
        chevron = Icon(
            "chevrons-up-down", size="sm", color="muted",
            classes=slots.get("chevron", ""),
        )
        Component._detach_from_parent(chevron)

        trigger = Element(
            tag="button",
            attrs={
                "type": "button",
                "class": slots.get("trigger", ""),
                "bz-ref": "bztrigger",
                "bz-on:click": f"{open_expr} = !{open_expr}",
                "aria-haspopup": "menu",
                "bz-attr:aria-expanded": bool_attr(f"{open_expr}"),
                # Persistent SELECTED state while the popover is open (the
                # theme reads ``data-[menu-open=true]``). Stringified ternary
                # so bz-attr never drops the attr (cf. data-open quirk).
                "data-menu-open": "false",
                "bz-attr:data-menu-open": bool_attr(open_expr),
            },
            children=(avatar_node, meta, chevron.render()),
        )

        # ── Popover panel (the children) ─────────────────────────────
        # Shared anchored-overlay wiring (same as Dropdown/Popover) :
        # toggles display + attaches ``$bz.helpers.floating`` (→
        # position:fixed, escapes the sidebar overflow), anchored on the
        # trigger box. ``auto`` = best-fit : the footer sits at the bottom
        # so there's no room below → it opens UPWARD in the expanded
        # sidebar, and adapts on its own in the collapsed rail.
        panel_attrs: dict[str, Any] = {
            "class": slots.get("panel", ""),
            "role": "menu",
            # ``bzpanel`` ref : the teleport moves the panel out of the
            # root's subtree, so click-outside checks it as "inside".
            "bz-ref": "bzpanel",
            "bz-effect": anchored_panel_effect(open_expr, "auto"),
            # DropdownItem children dispatch ``bz-dropdown-pick`` on click
            # → close the menu after the action runs.
            "bz-on:bz-dropdown-pick": f"{open_expr} = false",
        }
        stamp_display_none(panel_attrs)  # hidden until opened (no FOUC)
        panel = Element(
            tag="div", attrs=panel_attrs,
            children=tuple(self._render_children()),
        )

        # ── Root ─────────────────────────────────────────────────────
        attrs = self.emit_attrs()
        attrs["class"] = self.compose_class("root")
        # Local open flag + Escape / click-outside dismiss (shared wiring).
        # clickOutside targets the root (trigger + panel), so clicking the
        # trigger never counts as "outside".
        attrs.setdefault("bz-data", f"{{{open_expr}: false}}")
        attrs["bz-init"] = anchored_dismiss_init(open_expr)
        # Panel teleports to <body> — the footer sits inside the sidebar's
        # overflow + stacking context, which would clip / hide an inline
        # panel (cf. traps.md ; see ``teleport_to_body``).
        return Element(
            tag=self._tag,
            attrs=attrs,
            children=(trigger, teleport_to_body(panel, self)),
        )


class SidebarFooterItem(MenuItem):
    """A clickable row inside a :class:`SidebarFooter` popover.

    Exactly the API of ``ui.dropdown_item`` — ``label`` / ``icon_left`` /
    ``icon_right`` / ``shortcut`` / ``href`` / ``color`` / ``disabled`` /
    ``on_click`` — because the row logic lives in the shared
    :class:`~bretzel.components.primitives.menu_item.MenuItem`. This shell
    only binds the footer-item theme. On click it dispatches
    ``bz-dropdown-pick``, which the footer popover catches to close ::

        with ui.sidebar_footer(name="Jean", subtitle="jean@acme.com"):
            ui.sidebar_footer_item(label="Settings", icon_left="settings",
                                   href="/me")
            ui.sidebar_footer_item(label="Log out", icon_left="log-out",
                                   color="error", on_click=auth.logout())
    """

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_FOOTER_ITEM_THEME
    THEME_KEY: ClassVar[str] = "sidebar_footer_item"


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _render_backdrop(theme: dict, open_expr: str) -> Element:
    """The dimmed backdrop of ``overlay`` mode — SIBLING of the aside.

    ⚠️ It was **teleported under ``<body>``** until 2026-08-15, on this
    reasoning written right here: "the aside is itself ``fixed z-50``, so
    a child would live above it; under ``<body>`` it is a sibling, and
    its ``z-40`` puts it behind the sidebar". The first half is right,
    the second is **false**: it is a sibling of the aside only if the
    aside is itself a direct child of ``<body>``, which no real shell
    does. A ``z-index`` only compares between siblings of a stacking
    context, and the recommended shell (``fixed inset-0``) creates one.
    The backdrop therefore covered the sidebar and blurred it — reported
    on screen, then measured.

    The way out was neither "child" nor "under body" but a THIRD
    position: sibling, under a ``display:contents`` root that generates
    no box hence no context (cf. ``Sidebar.render``). It is the structure
    of ``ui.dialog`` / ``ui.drawer``, which never had the defect. Gate:
    ``tests/runtime_js/test_backdrop_never_covers_its_panel.py``.

    It carries ``data-open`` as a mirror (the theme reads
    ``data-[open=false]:opacity-0`` + ``pointer-events-none``, so closed
    it is both invisible AND click-through), and a click closes it — the
    affordance everybody expects from a phone menu. ``aria-hidden``: it
    is decorative, keyboard closing goes through Escape.
    """
    node = Element(
        tag="div",
        attrs={
            "class": theme.get("backdrop", ""),
            "aria-hidden": "true",
            "data-open": "false",
            "bz-attr:data-open": bool_attr(open_expr),
            "bz-on:click": f"{open_expr} = false",
        },
        children=(),
    )
    return node


def _render_rail_edge(
    slots: dict[str, str],
    open_expr: str,
) -> Element:
    """The bar's right edge, made clickable.

    Why it exists (finding [29], 2026-08-21)
    ------------------------------------------
    In the collapsed rail, the collapse button CARRIED THE LOGO and
    turned into a chevron **on hover**. On a machine without hover — a
    touch laptop, the user's — there was therefore no signal at all: the
    logo looked like a logo, and nothing said the bar could be reopened.
    The gesture existed and nobody could discover it.

    The edge repairs that without hiding anything: the aside's right
    border is already painted permanently, we simply make it reachable.
    That is the exact difference from shadcn's ``SidebarRail``, invisible
    at rest — and which ``test_hover_only_controls_reachable`` would
    forbid here.

    It also frees the logo, which becomes a link again: it stops changing
    job depending on the bar's state.
    """
    return Element(
        tag="button",
        attrs={
            "type": "button",
            "class": slots.get("rail_edge", ""),
            "aria-label": text("sidebar.rail_toggle"),
            "bz-on:click": f"{open_expr} = !{open_expr}",
            # ── The edge is a PANE OF GLASS: the click stops there,
            # the wheel goes through ─────────────────────────────────
            # It is ``absolute`` and a direct child of the aside, so
            # OUTSIDE the scrolling box. The browser scrolls what is
            # under the pointer; under the pointer there is the edge,
            # which does not scroll. Measured on 2026-08-23, in BOTH
            # states: 400 px of wheel over the strip left ``scrollTop``
            # at 0.
            #
            # Reported like this: "I cannot scroll because there is the
            # sidebar offering me to close it". On a 16 px strip running
            # the full height, it is the bar's whole right-hand column
            # that becomes dead to the wheel.
            #
            # ``:scope >`` and not a bare ``querySelector``: a NESTED bar
            # would otherwise see its child's box. ``preventDefault``
            # because we have taken the gesture over by hand — without
            # it a scrollable ancestor would move too. A ``wheel`` set by
            # ``bz-on:`` is NOT passive (the passive default only holds
            # on window/document/body), so the cancel takes.
            "bz-on:wheel": (
                "(() => { const b = $el.parentElement"
                ".querySelector(':scope > .bz-rail-scroll');"
                " if (!b) return; b.scrollTop += $event.deltaY;"
                " $event.preventDefault(); })()"
            ),
        },
        children=(
            Element(
                tag="span",
                attrs={
                    "class": slots.get("rail_edge_line", ""),
                    "aria-hidden": "true",
                },
                children=(),
            ),
        ),
    )


__all__ = [
    "Sidebar",
    "SidebarFooter",
    "SidebarFooterItem",
    "SidebarItem",
    "SidebarSection",
    "SidebarTitle",
]



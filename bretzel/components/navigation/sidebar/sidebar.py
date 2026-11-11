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
  aims ``hx-target=#outlet_<layout>``, so the page's boost swaps only that
  outlet. The active
  highlight is driven by a reactive ``bz-attr:data-active`` comparing
  the item's href to the sidebar's ``current_path``.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
)
from bretzel.components.base.arguments import has_content, shown
from bretzel.components.base.composition import unwrap_transparent
from bretzel.components.base.overlay_wiring import (
    anchored_dismiss_init,
    anchored_panel,
    escape_init,
    focus_trap_effect,
    imperative_listeners,
    install_open_close_toggle,
    modal_root_effect,
    teleport_to_body,
)
from bretzel.components.base.page_checks import TOGGLE_NEAREST_SIDEBAR
from bretzel.components.base.scope_wiring import bool_attr, server_sync_marker
from bretzel.components.navigation._nav_item import NavItem
from bretzel.components.navigation._wiring import (
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
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text
from bretzel.render.context import maybe_current_context
from bretzel.runtime.protocol import BZ_ATTR_PREFIX


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


_OVERRIDE = (
    "Override the theme's `root` slot to change that — "
    'Bretzel(theme=Theme(components={"sidebar": {"slots": {"root": "…"}}}})), or '
    '`slots={"root": "…"}` on the instance for a one-off.'
)


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
    #: The four legal values, read by the socle's refusal AND by the
    #: theme. One source: a fifth mode is added here.
    COLLAPSE_MODES: ClassVar[tuple[str, ...]] = (
        "rail", "offcanvas", "overlay", "none",
    )
    collapsible: str = reactive_prop(default="rail", emit_attr=False, steps=COLLAPSE_MODES)

    # No ``side=`` axis, on the opinionation rule's decisive test: "would
    # we have this component in two shapes in the SAME app?". No — an app
    # has a single side nav, and it is on the left.
    REFUSED_PROPS: ClassVar[dict[str, str]] = {
        "side": (
            "a side nav lives on the left — the two sides never coexist "
            f"in the same app, so it is a theme decision. {_OVERRIDE}"
        ),
        "variant": (
            "merged into `collapsible=` — it never said "
            'anything other than "what the collapsed form looks like". '
            'Write `collapsible="rail"` (ex-variant="rail") or '
            f'`collapsible="offcanvas"` (ex-variant="drawer"). {_OVERRIDE}'
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
        # A boolean ``collapsible`` would otherwise pass here without a
        # sound — ``True`` is
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
        # (``base/page_checks.check_sidebars_are_reachable``).
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
        attrs.setdefault("role", "dialog" if is_overlay else "navigation")
        attrs.setdefault("aria-label", text("sidebar.label"))
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
        # Without the freeze, ``ui.sidebar(collapsible="none", open=False)``
        # would render a FULL-WIDTH sidebar with collapsed content — centred
        # logo, a rule in place of the section title, rows reduced to their
        # icon: the child rules would fire while no width rule does.
        #
        # Freezing the attribute rather than going and gating those
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
        # A CLOSED ``overlay`` is slid off screen and a closed
        # ``offcanvas`` is zero wide — yet their links stay in the Tab
        # order, and the keyboard would walk into a panel nobody sees.
        # ``inert`` takes the closed panel out of focus, pointer and
        # assistive tech at once, and ``bz-attr`` removes it when the
        # expression is false. ``rail`` keeps its icons usable, and
        # ``none`` never closes.
        if mode in ("overlay", "offcanvas"):
            if not open_initial:
                attrs["inert"] = ""
            attrs["bz-attr:inert"] = f"!({data_open_expr})"

        # bz-data layout :
        #  - ``current_path`` : same path tracking as before, used by
        #    every SidebarItem to compute active-link state without a
        #    server round-trip on browser back/fwd.
        #  - ``open`` : present ONLY when no external binding drives
        #    the desktop state, so the chevron can flip something.
        # The collapsed rail's labels show in the PAGE's one tooltip panel
        # (``tip.js``), each entry being its own trigger: the bar keeps
        # no panel of its own.
        if bound_open:
            bz_data = current_path_scope()
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
                f"open: {initial_open},{sync}".rstrip().rstrip(",")
            )
        attrs.setdefault("bz-data", bz_data)
        # Resync ``current_path`` — shared with Navbar (the detail of
        # the two listeners and of the compare-then-assign guard is
        # documented on the helper).
        attrs.setdefault("bz-init", current_path_resync_init())
        # ⚠️ ``bz-init`` is ALREADY set above (resync ``current_path``).
        # Overlay mode wants a second one (Escape): we COMPOSE, we do not
        # overwrite — it is the "clobbered internal handler" trap.
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
        # A phone menu opened above the content must close on Escape, keep
        # the focus in it and not let the page scroll behind it. These
        # helpers come from ``base/``, the SAME ones as Dialog and Drawer, so
        # nothing is rewritten here and the ``overlay/`` group is not
        # imported.
        #
        # The in-flow modes (rail / offcanvas) most certainly do not want
        # them: collapsing a rail on desktop must neither steal the
        # Escape key nor lock the page's scroll.
        if is_overlay:
            attrs["bz-init"] = (f"{_base_init}; {escape_init(open_expr)}; "
                                f"{_follow_closes_init(open_expr)}")
            attrs["aria-modal"] = "true"
            # One directive per element: a comma keeps it one expression.
            attrs["bz-effect"] = f"{modal_root_effect(open_expr)}, {focus_trap_effect(open_expr)}"

        # ── Children layout ──────────────────────────────────────────
        children: list[Any] = []
        # ⚠️ No automatic floating chevron for a bar with no
        # ``SidebarTitle``: at ``absolute top-2 right-2`` it would sit
        # exactly under the edge, which takes the right-hand 24 px over
        # the full height, and the click would never reach it. The edge
        # does the same job, in both states, over the full height — and
        # without the component deciding where an app affordance goes.
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
        # ⚠️ No auto-rendered reopen button. Collapsed, a ``drawer``
        # sidebar disappears along with its chevron, but where the
        # reopening control goes is an APP affordance, not the
        # component's — and a hard-coded one would make a second one if
        # the app already has its own topbar. The dev places their button
        # where they want and calls ``sb.toggle()``; the imperative API
        # exists for that.
        # ⚠️ The backdrop is NOT a child of the aside, and above all it
        # is not teleported — it is a SIBLING, under a
        # ``display:contents`` root (cf. the end of this ``render``). See
        # the comment down there: it is the only position from which its
        # ``z-40`` can be compared to the aside's ``z-50``.
        backdrop = _render_backdrop(theme, open_expr) if is_overlay else None

        # ── User children : pin header + footer, scroll the middle ───
        # The aside is a rigid ``flex-col h-screen`` frame ; it does not
        # carry the scroll itself, which would scroll the FOOTER away with
        # an overflowing nav list. So we partition the user children by
        # type :
        #   • title   → pinned header (``shrink-0``)
        #   • footer  → pinned footer (``shrink-0``)
        #   • the rest → in the ``flex-1 min-h-0 overflow-y-auto`` box,
        #     the ONLY part that scrolls.
        #
        # ⚠️ **The sorting is done on the RENDERED node, not on the
        # child's Python type.** An ``isinstance(child, SidebarFooter)``
        # would miss every WRAPPED footer: a ``@refreshable`` renders a
        # ``_RefreshableSection``, a ``ui.fragment`` renders a
        # ``Fragment``. The footer would then fall into the middle, so
        # INTO the scrolling box, and slide when the nav scrolls.
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
            scroll_attrs: dict[str, Any] = {"class": slots.get("scroll", "")}
            if is_overlay:
                # The aside is a ``dialog`` in this mode, which takes its
                # ``navigation`` landmark away: without this one the phone
                # menu is found by no navigation role (« jump to
                # navigation », a test reading the landmark). The modal
                # drawer's usual shape: the dialog, a nav inside it.
                scroll_attrs.update(role="navigation", **{"aria-label": attrs["aria-label"]})
            children.append(
                Element(
                    tag="div",
                    attrs=scroll_attrs,
                    children=tuple(middle_nodes),
                )
            )
        children.extend(footer_nodes)

        aside = Element(tag=self._tag, attrs=attrs, children=tuple(children))
        if backdrop is None:
            return aside

        # ── Overlay mode: the backdrop and the aside must be SIBLINGS ─
        #
        # A ``z-index`` only compares between siblings of a stacking
        # context — it does not cross a boundary. Teleported under
        # ``<body>``, the backdrop would be "a sibling of the sidebar"
        # only if the aside were itself a direct child of ``<body>``,
        # which no real shell does: the recommended shell is
        # ``fixed inset-0`` (``traps.md``), and ``position: fixed``
        # CREATES a context. The aside's ``z-50`` would stay locked
        # inside it, the real comparison would become "shell (``z-auto``)
        # against backdrop (``z-40``)", and the backdrop would cover the
        # whole app — sidebar included, which it would blur with its
        # ``backdrop-filter``.
        #
        # ``display:contents`` (Tailwind ``contents``) is what settles
        # it: the root generates NO box, so no stacking context, and its
        # two children take part in the shell's. ``z-40`` and ``z-50``
        # compare there. It is also the structure of
        # ``ui.dialog`` / ``ui.drawer``, which keep their pair in the
        # same place — three
        # components, a single way of doing it (principle 4).
        #
        # The caller's ``classes=`` is copied onto the ASIDE: the
        # universal wrap would set it on this root, where it would be
        # inert (a box that does not exist is not styled).
        # ⚠️ The SCOPE moves up to the root — without that the backdrop
        # sees nothing. The runtime resolves a ``bz-*`` by walking up to
        # the nearest ancestor carrying ``bz-data``; a backdrop that is a
        # SIBLING of the aside therefore does not have the scope above
        # it, and its ``bz-attr:data-open`` would evaluate into the void:
        # the backdrop would stay at ``data-open="true"`` with the sidebar
        # closed, so opaque and blurred over the whole screen.
        #
        # The aside keeps seeing it: it descends from this root, so the
        # walk finds it. One scope, two consumers.
        # The component's IDENTITY follows the scope onto the root —
        # ``id`` included, and with it the imperative listeners.
        #
        # ⚠️ Do NOT leave the ``id`` on the aside: the base layer stamps
        # ``id`` + ``bz-id`` on any root that carries a ``bz-data`` and
        # does not yet have an ``id`` (``_stamp_scope_id``). The wrapper
        # would therefore get one — the SAME as the aside. Two nodes, one
        # id: ``document.getElementById`` returns the first, that is to
        # say the wrapper, and the imperative API would dispatch
        # ``bz-toggle`` on a node with no listener: the hamburger would
        # do nothing, in silence, while the state and the render are
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
    # real and measurable: apps write ``menu`` as often as
    # ``panel-left``.
    REFUSED_PROPS: ClassVar[dict[str, str]] = {
        "variant": (
            "the button's look is decided once per app, along with the "
            "rest of its top bar: it is a theme decision."
        ),
        "color": (
            "same — and `classes=` is still there for the one-off. If "
            "you really want a button of your own, the tier-2 escape "
            "hatch is whole: `ui.icon_button(…, on_click=sb.toggle())`."
        ),
    }

    def __init__(
        self,
        # The bar this button toggles — POINTED AT, not rendered: it stays
        # where it was placed. Hence ``Sidebar`` and not ``Component``.
        sidebar: Sidebar | None = None,
        *,
        icon: str | Component | None = None,
        size: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(icon=icon, size=size, **kwargs)
        self._sidebar: Any = None
        #: The fallback: aim at the stable marker and resolve at CLICK
        #: time. Replaced by the command by id as soon as a bar is known.
        self._command: str = TOGGLE_NEAREST_SIDEBAR
        if sidebar is not None:
            self.bind_sidebar(sidebar)
        else:
            # Resolved by ``base/page_checks.wire_sidebar_triggers`` once
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
            # The binding when there is one: the button follows it live.
            bound if (bound := self._binding_metadata.get("icon")) is not None
            else self._reactive_values.get("icon") or "panel-left",
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
    label: str | Component | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        label: str | Component | None = None,
        **kwargs: Any,
    ) -> None:
        # Direct forward: the base layer drops reactive None kwargs (keeps the default).
        super().__init__(label=label, **kwargs)

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # ``shown``: a bound label is drawn live; ``has_content`` because
        # a binding refuses ``if label:``.
        label = shown(self, "label")

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("section", "")

        children = list(self._render_children())
        if has_content(label):
            # Rail divider — the collapsed-rail form of the label. The
            # uppercase caption (``section_label``) hides at md+ collapse ;
            # in its place we drop a real :class:`~bretzel.components.
            # primitives.divider.Divider` (dogfooding — a primitive, so
            # importable here), so the caption visually
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

    title: str | Component = reactive_prop(default="", emit_attr=False)
    #: ⚠️ The default is a GLYPH, not ``None`` — same pattern as
    #: ``ui.datatable(empty_icon="inbox")``. Without it, a title written
    #: with no ``icon=`` would leave the rail's head empty, and a
    #: collapsed rail would show a hole above its items.
    #: ``home`` and not something else: this link leads to ``href=``,
    #: whose default is ``/``. The glyph therefore describes what the
    #: link DOES.
    #:
    #: **For no mark at all: ``icon=""``.** Not ``icon=None`` — the base
    #: layer drops reactive kwargs at ``None`` to keep the default, so an
    #: explicit ``None`` is indistinguishable from an absent argument
    #: (checked). The empty string, on the other hand, reaches here.
    icon: str | Component | None = reactive_prop(default="home", emit_attr=False)
    href: str = reactive_prop(default="/", emit_attr=False)

    def __init__(
        self,
        title: str | Component = "",
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
        # a Component — coercing it here would ship its Python repr into
        # the page (``emit_text_slot`` sorts it out downstream).
        # ``shown``: a bound title is drawn
        # live. Like a Component, it names the rail's link by
        # ``aria-labelledby`` (an attribute cannot hold a binding, the
        # referenced span follows it).
        title = shown(self, "title")
        if not has_content(title):
            title = ""
        # ``icon`` accepts a bare name ("zap") OR a built ``ui.icon(...)``.
        # We read its NAME (the title sizes the glyph uniformly) and its
        # COLOUR : a bare string gets the brand ``primary`` ; a passed
        # ``ui.icon(...)`` keeps its OWN colour (default "current" = inherit
        # the brand link) so ``ui.icon("zap", color="warning")`` shows orange.
        icon_arg = self._reactive_values.get("icon")
        icon_binding = self._binding_metadata.get("icon")
        icon_name = _icon_name(icon_arg)
        mark = icon_arg if isinstance(icon_arg, Component) else None
        icon_color = (getattr(mark, "color", None) or "current") if mark else "primary"
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

        # A passed ``ui.icon(...)`` keeps the classes its author gave it;
        # any other Component (an image, a monogram) is drawn as it is,
        # dressed with the slot's classes — rendered once, placed twice.
        drawn = Component.render_detached(mark) if mark and not icon_name else None
        has_mark = bool(icon_name) or drawn is not None

        def _glyph(cls: str) -> Node:
            if drawn is not None:
                return Component.with_slot_class(drawn, cls)
            own = mark._user_classes_str() if mark else ""
            glyph_attrs = {"icon": _iconify_ref(icon_name), "class": f"{cls} {own}".strip()}
            if icon_binding is not None:
                # A bound name, followed live — the same resolver as
                # ``ui.icon`` (R1: ``icon`` is bindable on every slot).
                glyph_attrs[f"{BZ_ATTR_PREFIX}icon"] = (
                    f"$bz._resolveIcon({self.path_of(icon_binding)}, 'lucide', null)")
            return Element(tag="iconify-icon", attrs=glyph_attrs, children=())

        # ── In-sidebar header : brand link + collapse chevron ────────
        brand_children: list[Any] = []
        # A Component title names the rail's link by reference: its text
        # is read from the span, as the screen reader would read it.
        title_id = (
            f"{self.id}-title"
            if has_content(title) and not isinstance(title, str) else None
        )
        if has_mark:
            brand_children.append(
                _glyph(f"{slots.get('title_logo', '')} {icon_text_class}")
            )
        if has_content(title):
            brand_children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("title_text", ""), "id": title_id},
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
        # A logo that turned into a chevron on hover and collapsed on
        # click would have two defects: on a machine without hover
        # nothing would announce the gesture, and the logo would change
        # job depending on the bar's state.
        #
        # The collapse has its EDGE (``Sidebar._render_rail_edge``),
        # visible in both states, so the logo has only one job:
        # leading to ``href=``.
        # ⚠️ **No rail mark WITHOUT a glyph.** An ``<a>`` with no child
        # is not "invisible": on a collapsed rail, it occupies a square
        # at the head of the bar and takes the FIRST focus — the first
        # tab lands on a link you cannot see.
        #
        # With no glyph, the rail
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
                # A string is the name as written; a ``title=ui.text(...)``
                # is pointed at rather than flattened by hand, so the name
                # is exactly the text the expanded title shows.
                "aria-labelledby": title_id,
                "aria-label": None if title_id else (
                    title.strip() if isinstance(title, str) and title.strip()
                    else text("sidebar.home")
                ),
            },
            children=(
                _glyph(f"text-2xl {icon_text_class}"),
            ) if has_mark else (),
        )

        attrs = self.emit_attrs()
        attrs["class"] = slots.get("title_root", "")

        children: list[Any] = [brand, toggle_node]
        if has_mark:
            children.append(rail_brand)

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))


# ───────────────────────────────────────────────────────────────────────────
# SidebarItem — the nav row primitive
# ───────────────────────────────────────────────────────────────────────────


class SidebarItem(NavItem):
    """One nav row : icon + label + optional badge."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_ITEM_THEME
    THEME_KEY: ClassVar[str] = "sidebar_item"
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
        # so we bring the name back on hover — in the PAGE's one tooltip
        # panel (``tip.js``), this row being its trigger. Disabled rows are skipped : ``pointer-events-none`` /
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
        # an ``aria-label`` and into the ``data-bz-tip`` attribute. The row keeps its rich content;
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

        # The visible text follows a bound label (``shown``); the rail's
        # ``aria-label`` / ``data-bz-tip`` keep the
        # resolved string ``label`` — an attribute cannot hold a binding.
        label_text = shown(self, "label")
        if has_content(label_text):
            children.append(
                Element(
                    tag="span",
                    attrs={"class": slots.get("label", "")},
                    children=(self.emit_text_slot(label_text),),
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

        # ── Rail tooltip: this row triggers the page's shared panel ──
        # Not a ``ui.tooltip`` per entry, which would pre-render one panel
        # per row, and not a panel of the bar's own either, whose look
        # would be a COPY of the tooltip's. The row says its label and how
        # the rail wants it: beside the BAR's edge (collapsed, the entry is
        # a ``w-10`` square inside a 64 px rail, and a panel on the entry's
        # edge would bite into the rail), at once, on one line,
        # and only while the bar is collapsed — read at hover time.
        #
        # ``aria-label`` carries the accessible name on the link itself:
        # in the rail the visible label is ``hidden``, and a tooltip on
        # hover is not a keyboard/screen-reader affordance. The shared
        # panel does not describe a control whose name already says it.
        if show_rail_tip:
            # The name says the badge too: an ``aria-label`` replaces the
            # link's content, so the label alone would hide the badge from
            # screen readers. A reactive badge keeps the name in step.
            if "aria-label" not in attrs:
                if badge_binding is not None:
                    path = self.path_of(badge_binding)
                    attrs["bz-attr:aria-label"] = (
                        f"(v => v == null || v === '' ? {json.dumps(label)} : "
                        f"{json.dumps(label + ' ')} + v)({path})"
                    )
                if isinstance(badge_value, (str, int, float)) and str(badge_value) != "":
                    attrs["aria-label"] = f"{label} {badge_value}"
                else:
                    attrs["aria-label"] = label
            attrs.update({
                "data-bz-tip-root": "",
                "data-bz-tip": label,
                "data-bz-tip-position": "right",
                "data-bz-tip-beside": "aside",
                "data-bz-tip-delay": "0",
                "data-bz-tip-class": "whitespace-nowrap",
                "data-bz-tip-off": "$el.closest('aside').dataset.open !== 'false'",
            })

        node = Element(tag=tag, attrs=attrs, children=tuple(children))

        return node


# ───────────────────────────────────────────────────────────────────────────
# SidebarFooter — account row + popover menu, pinned to the bottom
# ───────────────────────────────────────────────────────────────────────────


def _footer_initials(name: Any) -> str:
    """Derive up-to-2-char initials from a display name ("Alex Martin"
    → "AM", "Alex" → "AL"). Falls back to "?" for an empty name.

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


def _is_image_source(avatar: str) -> bool:
    """True when the footer's ``avatar`` string names an image rather than
    initials: a path or URL (it has a ``/``) or a ``data:`` URI. Initials
    carry neither."""
    return "/" in avatar or avatar.startswith("data:")


class SidebarFooter(Component):
    """Render the footer region of a sidebar."""

    THEME: ClassVar[dict[str, Any]] = SIDEBAR_FOOTER_THEME
    THEME_KEY: ClassVar[str] = "sidebar_footer"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    name: str | Component = reactive_prop(default="", emit_attr=False)
    subtitle: str | Component | None = reactive_prop(default=None, emit_attr=False)
    avatar: str | Component | None = reactive_prop(
        default=None, emit_attr=False
    )
    # Colour axis — tints the avatar chip + focus ring. Set by the
    # ``bz-c-<colour>`` bridge class on the root, which installs the
    # eleven steps on the subtree (cf. ``color_bridge_class``); the theme
    # writes COMPLETE classes like ``bg-(--bz-bg)``.
    # Defaults to ``primary`` like every other Bretzel component
    # (Button / Avatar / SidebarItem …).
    color: str = reactive_prop(default="primary", emit_attr=False)

    def __init__(
        self,
        name: str | Component = "",
        *,
        subtitle: str | Component | None = None,
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
        # A bound avatar follows the client
        # value: an image source by ``bz-attr:src``, initials by
        # ``bz-text``. Which of the two is decided on the server value.
        bound = self._binding_metadata.get("avatar")
        if bound is not None:
            live: Node | None = (
                Element(tag="img", attrs={
                    "src": avatar, f"{BZ_ATTR_PREFIX}src": self.path_of(bound),
                    "alt": "", "class": "h-full w-full object-cover",
                }, children=())
                if isinstance(avatar, str) and _is_image_source(avatar)
                else self.emit_text_slot(bound)
            )
            return Element(
                tag="span", attrs={"class": avatar_cls},
                children=(live,) if live is not None else (),
            )
        if isinstance(avatar, Component):
            # A passed ``ui.avatar(...)`` carries its OWN size/shape/colour
            # (and is already detached by ``Component.__init__``) — render it
            # as-is, don't double-wrap it in the initials-chip styling.
            return Element(
                tag="span", attrs={"class": "shrink-0 inline-flex"},
                children=(avatar.render(),),
            )
        # ``avatar`` is now ``str | None`` (the Component case returned
        # above). An image source fills the chip; any other text is the
        # initials; nothing derives them from the name
        # (``_footer_initials`` owns the fallback for a non-textual name).
        if isinstance(avatar, str) and _is_image_source(avatar):
            # ``alt=""``: the name is written right beside it, a screen
            # reader must not announce the person twice (same rule as
            # ``ui.avatar``).
            content: Node = Element(tag="img", attrs={
                "src": avatar, "alt": "", "class": "h-full w-full object-cover",
            }, children=())
        else:
            content = TextNode(avatar or _footer_initials(name))
        return Element(
            tag="span", attrs={"class": avatar_cls}, children=(content,),
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        slots = theme.get("slots", {})
        # Same as ``title`` above: textual slot, no coercion.
        name = self._reactive_values.get("name") or ""
        # ``shown``: a bound name / subtitle is
        # drawn live. The initials fallback keeps deriving from the resolved
        # ``name`` — the server cannot split a value it never sees.
        name_text = shown(self, "name")
        subtitle = shown(self, "subtitle")
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
        name_node = self.emit_text_slot(name_text)
        meta_children: list[Any] = [
            Element(
                tag="span", attrs={"class": slots.get("name", "")},
                children=(name_node,) if name_node is not None else (),
            )
        ]
        if has_content(subtitle):
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
        panel = anchored_panel(
            css=slots.get("panel", ""),
            children=tuple(self._render_children()),
            open_expr=open_expr,
            placement="auto",
            role="menu",
            # The items dispatch ``bz-dropdown-pick`` on click: that closes
            # the menu after the action runs.
            attrs={"bz-on:bz-dropdown-pick": f"{open_expr} = false"},
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

        with ui.sidebar_footer(name="Alex", subtitle="alex@acme.com"):
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


def _follow_closes_init(open_expr: str) -> str:
    """``bz-init`` of ``overlay`` mode: following a link closes the panel.

    The sidebar lives in the layout, so a partial navigation keeps it —
    and its ``open`` — while the page changes behind it: on a phone the
    menu would stay over the page just asked for. A plain click on a link
    inside the aside
    closes it; a modified click (new tab) leaves it open, the page does
    not change.
    """
    return (
        "$el.addEventListener('click', (e) => { "
        "if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return; "
        f"if (e.target.closest('a[href]') && ({open_expr})) {{ {open_expr} = false; }} }})"
    )


def _render_backdrop(theme: dict, open_expr: str) -> Element:
    """The dimmed backdrop of ``overlay`` mode — SIBLING of the aside.

    ⚠️ It is neither a child of the aside (which is ``fixed z-50``, so a
    child would live above it) nor **teleported under ``<body>``**: it
    would be a sibling of the aside there only if the aside were itself a
    direct child of ``<body>``, which no real shell does. A ``z-index``
    only compares between siblings of a stacking context, and the
    recommended shell (``fixed inset-0``) creates one, so the backdrop
    would cover the sidebar and blur it.

    It takes a THIRD position: sibling, under a ``display:contents`` root
    that generates no box hence no context (cf. ``Sidebar.render``). It
    is the structure of ``ui.dialog`` / ``ui.drawer``. Gate:
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

    Why it exists
    --------------
    A collapse button that carries the logo and turns into a chevron
    **on hover** gives no signal at all on a machine without hover: the
    logo looks like a logo, and nothing says the bar can be reopened.

    The edge repairs that without hiding anything: the aside's right
    border is already painted permanently, we simply make it reachable.
    That is the exact difference from shadcn's ``SidebarRail``, invisible
    at rest — and which ``test_hover_only_controls_reachable`` would
    forbid here.

    It also frees the logo, which stays a link: it does not change job
    depending on the bar's state.
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
            # which does not scroll. The strip runs the full height, so
            # without the handler the bar's whole right-hand column would
            # be dead to the wheel, in BOTH states.
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



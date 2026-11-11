"""Default theme for the Sidebar family (Sidebar / SidebarSection / SidebarItem).

Three components : :class:`SidebarItem` takes ``icon`` / ``label`` /
``badge`` props. On desktop collapse, the icon stays put; the ``label``
FADES (``opacity-0`` + ``w-0`` + ``flex-none``, like ``title_brand``)
and the ``badge`` disappears at once — otherwise its ``ml-auto`` would
eat the square's free space and push the icon off centre.

Responsive model :

- The sidebar is DESKTOP navigation chrome only. ``open`` drives
  ``data-open`` which the ``variants`` map reads : ``"rail"`` collapses
  to a 64px icon strip, ``"drawer"`` collapses to width 0.
- Responsive mobile navigation is the app layout's responsibility
  (``if Screen().is_mobile:``), NOT built into this component — the
  sidebar ships no mobile drawer / topbar / hamburger.

Slots :
- ``sidebar.root``        : the ``<aside>`` flex column
- ``sidebar.section``     : grouping div for a single ``SidebarSection``
- ``sidebar.section_label`` : the small uppercase label above a section
- ``sidebar.section_divider`` : rail-only visibility gate wrapping a
  ``ui.divider`` (the collapsed-rail form of a labelled section caption)
- ``item.root``           : every item / nav row's outer ``<a>`` / ``<div>``
- ``item.active``         : extra classes layered when the row is active
- ``item.icon``           : icon slot wrapper (always visible)
- ``item.label``          : label text (fades out on desktop collapse)
- ``item.badge``          : right-aligned trailing badge (``hidden`` on desktop collapse, not a fade)
"""

from __future__ import annotations

from typing import Any

SIDEBAR_THEME: dict[str, Any] = {
    "slots": {
        # The frame. The ``data-[open=false]`` rules of the ``widths`` +
        # ``collapse`` tables switch the width on collapse.
        "root": (
            # ⚠️ NO ``position`` utility here — it lives in the
            # ``collapse`` table, one entry per mode. This is not tidying:
            # ``relative`` and ``fixed`` are two utilities of the SAME
            # specificity, so the winner is the last one in the Tailwind
            # sheet, not the last one in the ``class`` attribute.
            # With ``relative`` on the root, the ``overlay`` mode could
            # render ``position: relative`` and ``transform: none``: the
            # sidebar would stay in the flow and not close. Same trap as
            # ``h-screen`` against ``h-full``.
            "group/sidebar shrink-0 flex flex-col h-screen "
            # ⚠️ NEITHER ``position`` NOR ``z-index`` here — both live in
            # the ``collapse`` table, one entry per mode. Same reason, and
            # the ``z-40`` that lingered here cost a visible bug: it
            # competed with ``overlay`` mode's ``z-50`` (two ``z-index``
            # utilities of the SAME specificity → the sheet order decides),
            # the sidebar dropped to the dimmed backdrop's level and found
            # itself BLURRED under its own backdrop.
            "p-2 gap-1 bg-surface "
            # A side nav is on the left, so the border is on the right.
            "border-r-(length:--bz-stroke) border-text/10 "
            # NO ``overflow-y-auto`` here — the scroll lives on the
            # ``scroll`` slot (the middle region) so an overflowing nav
            # list scrolls WITHOUT dragging the footer down with it. The
            # aside stays a rigid ``flex-col h-screen`` frame : title +
            # footer are ``shrink-0`` siblings, the scroll box is
            # ``flex-1``. ``overflow-x-hidden`` stays : it clips the
            # horizontal jitter during the rail width-collapse animation.
            "overflow-x-hidden "
            # ``width`` covers the desktop rail collapse animation.
            "transition-[width] duration-200 ease-in-out "
            # (The position is in ``collapse``, cf. above.)
            ""
        ),
        # ── Scroll region (auto-wraps the middle children) ───────────
        # Everything that is NOT a SidebarTitle / SidebarFooter lands in
        # this box (see ``Sidebar.render``). ``flex-1`` makes it eat the
        # space the pinned header + footer leave ; ``min-h-0`` is
        # load-bearing — a flex child defaults to ``min-height:auto`` and
        # would refuse to shrink below its content, so the ``overflow``
        # never triggers and the footer gets pushed off-screen (the exact
        # bug this fixes ; cf. traps.md). ``flex flex-col gap-1`` gives the
        # same inter-section rhythm as if the aside were the direct
        # parent. ``overflow-x-hidden`` mirrors the aside so the rail
        # collapse doesn't show a horizontal bar.
        # ``bz-rail-scroll`` is a CSS hook (not a Tailwind utility) : the
        # global theme CSS (css.py ``_RAIL_SCROLL``) targets it to HIDE the
        # scrollbar in the collapsed desktop rail so the icon column stays
        # perfectly centred (no reserved gutter) ; scroll still works via
        # wheel. The expanded sidebar keeps the normal thin scrollbar
        # (the rule is gated on ``[data-open=false]`` alone).
        # ⚠️ ``-mx-1.5 px-1.5``: ROOM FOR THE FOCUS RING, not a decorative
        # margin. The ring is a ``box-shadow`` that overflows by 4px
        # (offset 2 + ring 2) and an ancestor with a non-visible
        # ``overflow`` clips its descendants' shadows. The row is at 0px
        # from both edges of this box, so the ring would be shaved on the
        # left AND on the right, in ALL states
        # (not only in the rail). The negative margin takes back the 6px
        # the padding adds: the row keeps exactly its position and its
        # width, only the clipping box widens. 6px for a 4px ring = 2px of
        # margin.
        #
        # ``overflow-x-hidden`` can NOT simply be dropped: ``overflow-y:
        # auto`` forces the X axis to a scrolling value (``visible``
        # computes to ``auto``), so removing it would make a horizontal
        # bar possible instead of nothing.
        "scroll": (
            "bz-rail-scroll flex-1 min-h-0 flex flex-col gap-1 "
            "-mx-1.5 px-1.5 "
            "overflow-y-auto overflow-x-hidden"
        ),
        # Rows sit tight, groups breathe: the hierarchy is the contrast
        # between this ``gap-0.5`` and the ``mt-4`` of ``section_label``.
        # The rows' focus ring is INSET, so no gap can be too small for it.
        "section": "flex flex-col gap-0.5",
        # ``font-semibold``, not ``font-bold``: the catalogue's other
        # micro-capitals are ``divider.label`` (semibold), this sidebar's
        # ``avatar`` (semibold) and ``calendar.weekday`` (medium).
        "section_label": (
            "text-xs font-semibold text-muted uppercase tracking-wide "
            "px-2 pt-1 pb-1.5 mt-4 "
            # Fades on collapse (the rail shows its separator instead).
            # Not ``hidden``: ``display:none`` would kill the fade, cf.
            # ``title_text``.
            "overflow-hidden "
            "transition-[opacity,visibility,height,padding,margin] "
            "duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:invisible "
            "group-data-[open=false]/sidebar:h-0 "
            "group-data-[open=false]/sidebar:py-0 "
            "group-data-[open=false]/sidebar:mt-0"
        ),
        # Rail divider — the collapsed form of a section LABEL. The
        # uppercase ``section_label`` hides at md+ when ``data-open=false``
        # ; this is its exact mirror : ``hidden`` by default + in the
        # expanded sidebar, shown ONLY at md+ collapse. So in the rail the
        # "MAIN" / "ACCOUNT" caption visually turns into a separator line.
        # This is just the visibility GATE — a plain wrapper with no base
        # ``display`` (so ``hidden``/``:block`` toggle cleanly) ; the line
        # itself is a real ``ui.divider`` rendered inside. ``px-2`` insets
        # it slightly from the 64px rail edges. Rendered ONLY for labelled
        # sections — an unlabelled group has no caption to collapse.
        "section_divider": (
            "hidden px-2 group-data-[open=false]/sidebar:block"
        ),
        # The collapsed rail's labels show in the PAGE's one tooltip panel
        # (``tip.js``, ``TOOLTIP_THEME``). One panel, one look.
        # ── The clickable EDGE ───────────────────────────────────────
        # The aside's right border (``border-r border-text/10``) is
        # already painted permanently: all we do is make it REACHABLE.
        # That is what sets this affordance apart from shadcn's rail,
        # invisible at rest and revealed on hover — which
        # ``test_hover_only_controls_reachable`` forbids here, and which
        # would not exist on a touch machine anyway.
        #
        # 24 px wide for the WCAG 2.2 § 2.5.8 target floor (the same one
        # ``ui.draggable``'s theme cites), straddling the border:
        # ``-right-3`` puts half of it above the content, which avoids
        # eating the rail icons' click area — at 64 px wide, an INNER
        # 24 px strip would cover 12 of their 40.
        #
        # ⚠️ ``cursor-pointer`` and most certainly NOT ``cursor-w-resize``:
        # shadcn uses the second, which promises a drag that does not
        # exist. Bretzel has a real resize gesture (``ui.resizable``), and
        # stealing its signal would make both illegible.
        #
        # Hover only ENRICHES: the line thickens and takes a tint. The
        # repository's rule allows it explicitly — "``hover:`` is still
        # welcome to ENRICH, never to reveal".
        "rail_edge": (
            # ⚠️ ``right-0``, NEVER a negative overflow. The aside
            # carries ``overflow-x-hidden`` (it holds back the expanded
            # content during the width animation), so a ``-right-3``
            # CUTS the outer half: the strip ends up ~12 px usable,
            # off-centre, and you can only aim at it from the left.
            # ⚠️ ``w-4`` = 16 px, and it is a TRADE-OFF, not a setting.
            # 24 px (the WCAG 2.2 § 2.5.8 target floor) would cover too
            # much of the rail's nav icons. 16 px leave them nearly whole
            # while staying far more aimable than the clipped version's
            # ~12 usable px.
            #
            # What we lose: the strip alone does not meet the touch
            # floor. It stays as tall as the whole bar — so a long
            # target, comfortable with a mouse — and on a bar WITH a
            # title the header's 40 px button stays a command in its own
            # right. It is written in the gate, which tells the two
            # shapes apart.
            "group/railedge absolute top-0 right-0 z-50 h-full w-4 "
            "hidden md:block bg-transparent border-0 p-0 "
            # The cursor IS the announcement. ``pointer`` does not set
            # this strip apart from the rest of the page; a DIRECTIONAL
            # resize cursor says both "this edge moves" and which way —
            # ``e-resize`` when the bar is collapsed (it is going to open
            # to the right), ``w-resize`` when it is expanded. It is
            # shadcn's choice, and I fall in with it: I had ruled it out
            # for fear of promising a drag, but without it the strip does
            # not exist for the mouse.
            "cursor-w-resize group-data-[open=false]/sidebar:cursor-e-resize "
            "focus-visible:outline-none"
        ),
        # The line INSIDE the edge: 2 px centred, transparent at rest
        # (the aside's border is already there, under it), tinted on
        # hover and on keyboard focus.
        # The line INSIDE the edge. It is flush with the RIGHT edge
        # (``right-0``) and not centred: that is where the aside's border
        # is, so that is the one it thickens — a line centred in the
        # strip would paint a second line 12 px from the first.
        #
        # 4 px and not 2: at 2 px, "the line is still very thin" and you
        # do not see it coming. It stays transparent at rest — the
        # aside's border is already there, under it.
        "rail_edge_line": (
            "absolute inset-y-0 right-0 w-1 "
            "bg-transparent transition-colors duration-150 "
            "group-hover/railedge:bg-primary/60 "
            "group-focus-visible/railedge:bg-primary"
        ),
        # ── SidebarTitle (header : logo + title + collapse toggle) ───
        # Row when expanded ; stacks + centers on desktop collapse so
        # the logo sits centered in the 64px rail with the chevron under.
        "title_root": (
            "relative flex flex-row items-center gap-2 px-2 py-3 shrink-0 "
            "group-data-[open=false]/sidebar:flex-col "
            "group-data-[open=false]/sidebar:items-center "
            "group-data-[open=false]/sidebar:justify-center "
            "group-data-[open=false]/sidebar:gap-1 "
            "group-data-[open=false]/sidebar:px-0"
        ),
        # The logo + title, a clickable home link. ``min-w-0`` lets the
        # title truncate ; ``flex-1`` pushes the toggle to the far edge.
        # Hidden entirely on desktop collapse — in the rail we show ONLY
        # the chevron (centered), not the logo.
        "title_brand": (
            "flex flex-row items-center gap-2 min-w-0 flex-1 "
            "text-text font-bold no-underline "
            # ⚠️ Fade AND release of the width, both. ``hidden``
            # (``display:none``) would remove the space but kills any
            # transition, so the title would JUMP. A plain ``opacity-0``
            # does the opposite — it fades, but keeps its place in the
            # row, and the logo then overflows the 64 px strip.
            #
            # So both are needed: the opacity animates, ``w-0`` +
            # ``flex-none`` give the space back to the rail's centred
            # chevron, and ``visibility`` switches at the end to leave
            # the tab order. ``flex-none`` is indispensable — ``flex-1``
            # would re-inflate the box despite ``w-0``.
            "overflow-hidden "
            "transition-[opacity,visibility,width,height] duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:invisible "
            "group-data-[open=false]/sidebar:flex-none "
            "group-data-[open=false]/sidebar:w-0 "
            "group-data-[open=false]/sidebar:h-0"
        ),
        # Header lockup is sized UNIFORMLY at ``text-2xl`` (24px) : the logo
        # glyph, the title text, and the collapse chevron all share the SAME
        # scale as the collapsed-rail logo (``title_rail_brand``, also in
        # ``text-2xl``). That is what makes the collapse clean: the logo
        # never changes size, only the label and the chevron fade.
        # 24 px is the ``lg`` step of the Icon scale, so the chevron
        # (``Icon(size="lg")`` in an IconButton ``size="md"``, an
        # ``h-10 w-10`` box) is indeed 40 px like the rail's logo.
        #
        # Logo glyph — sized by FONT-SIZE (iconify-icon renders at 1em ;
        # w-7/h-7 would only grow the box and leave a small glyph top-left),
        # the same convention as the Icon primitive.
        # Colour (``text-primary`` for a string icon, or the passed
        # ``ui.icon(...)``'s own colour) is injected by ``render()``.
        "title_logo": (
            "shrink-0 inline-flex items-center justify-center text-2xl"
        ),
        # Title text — ``text-2xl`` (matches the logo + rail glyph) ; bold
        # comes from ``title_brand``. Hides on desktop collapse.
        # ⚠️ The fade, and why it is NOT ``hidden``: ``display:none`` is
        # not animatable, so a ``transition-opacity`` next to
        # ``group-data-[open=false]:hidden`` would be DECLARED AND DEAD.
        # The text would jump to ``display:none`` at once, then the strip
        # would shrink over an already empty box.
        #
        # ``visibility`` accompanies the opacity (``ui.drawer``'s theme
        # pattern): it switches at the END of the duration, so the text
        # fades during the collapse then leaves the tab order. A plain
        # ``opacity-0`` would leave it focusable.
        "title_text": (
            "text-2xl truncate "
            "transition-[opacity,visibility] duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:invisible"
        ),
        # Expanded-state collapse chevron (right of the title). Its glyph is
        # sized to 24px by the explicit ``Icon(size="lg")`` passed to the
        # IconButton (see sidebar.py) — matches the logo + title + rail glyph.
        # Hidden in the rail, where it is the logo (``title_rail_brand``)
        # that reopens — there is no second button.
        "title_toggle": (
            "shrink-0 "
            "group-data-[open=false]/sidebar:hidden"
        ),
        # The collapsed rail's LOGO — visible only in the desktop rail.
        #
        # ``grid place-items-center`` (and not flex) centres the glyph in
        # the single cell, whatever its size.
        #
        # It is a LINK, leading where the expanded logo leads
        # (``href=``, ``/`` by default), and not a collapse button that
        # turns into a chevron ON HOVER: on a machine without hover, such
        # a logo would never announce that it collapses anything, and it
        # would change job
        # depending on the bar's state. The collapse, for its part, has
        # its edge (``rail_edge``) — visible in both states.
        "title_rail_brand": (
            "hidden place-items-center no-underline "
            "rounded-selector text-text hover:bg-text/10 transition-colors "
            "group-data-[open=false]/sidebar:grid "
            "group-data-[open=false]/sidebar:w-10 "
            "group-data-[open=false]/sidebar:h-10 "
            "group-data-[open=false]/sidebar:mx-auto "
            "group-data-[open=false]/sidebar:p-0"
        ),
    },
    # Desktop EXPANDED width preset. In ``rem``, not in spacing steps: a
    # step follows the density, which an app can set, and a frame's width
    # is not a control's — at 3 px per step ``w-64`` rendered 192 px, not 256.
    "widths": {
        "sm": "w-[12rem]",
        "md": "w-[16rem]",
        "lg": "w-[20rem]",
    },
    # ── A SINGLE axis: what "collapsed" means ────────────────────────
    # One axis, four values, zero illegal combination — shadcn's split,
    # plus ``overlay``. A look prop plus an on/off prop would allow an
    # absurd combination: a sidebar you can neither collapse nor reach.
    #
    # ⚠️ NO ``md:`` gate on any of the four modes, and that is a
    # decision: it is the DEV who chooses the mode, in
    # their ``if Screen().is_mobile``. The CSS has no business
    # contradicting them. With such a gate, collapsing below 768px would
    # do NOTHING, and it would be enough for the ``bz_screen`` cookie to
    # be one render late (a resize, a first load) to end up with an open
    # sidebar impossible to close.
    #
    # Each mode also carries its ``position`` AND its ``z-index``: these
    # are utilities whose two values compete at equal specificity, so
    # leaving them on ``root`` would make the winner depend on the
    # Tailwind sheet's order.
    "collapse": {
        # The three IN-FLOW modes carry ``relative`` (an ordinary layout
        # column); ``overlay`` carries ``fixed``. One position utility
        # per mode, so no ordering conflict.
        "rail": "relative z-40 data-[open=false]:w-16",
        "offcanvas": (
            "relative z-40 "
            "data-[open=false]:w-0 data-[open=false]:p-0 "
            "data-[open=false]:border-0 "
            "data-[open=false]:overflow-hidden"
        ),
        # Out of the flow, anchored to the left edge, slid off screen
        # when closed. ``z-50`` goes in front of the dimmed backdrop
        # (``z-40``). The translation rather than a ``display:none``: it
        # animates, and it keeps the node mounted so the client scope
        # survives. It slides IN and closes at once: the transition lives
        # on the open state (the why: ``overlay/dialog/theme.py``).
        "overlay": (
            "fixed inset-y-0 left-0 z-50 shadow-2xl "
            "data-[open=true]:transition-transform data-[open=true]:duration-200 data-[open=true]:ease-out "
            "data-[open=false]:-translate-x-full"
        ),
        "none": "relative z-40",
    },
    # The dimmed backdrop of ``overlay`` mode: a sibling of the aside,
    # not a child (cf. ``_render_backdrop``).
    "backdrop": (
        "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm "
        "data-[open=true]:transition-opacity data-[open=true]:duration-200 "
        "data-[open=false]:opacity-0 data-[open=false]:invisible "
        "data-[open=false]:pointer-events-none"
    ),
}


SIDEBAR_ITEM_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # ⚠️ ``text-sm`` DECLARED: a nav row with no size inherits the
            # browser's ``text-base``, which would make it stick out next
            # to ``navbar_item`` and ``sidebar_footer_item`` — the other
            # kind of row in the SAME file. The leading follows the size,
            # which tightens the rhythm without touching the padding and
            # keeps a correct touch target.
            "group/row relative flex flex-row items-center gap-2 w-full "
            "shrink-0 px-2 py-2 rounded-box cursor-pointer text-sm "
            # Desktop collapse : turn the row into a FIXED ``w-10 h-10``
            # square, centered in the 64px rail via ``mx-auto`` (the rail
            # inner box is 48px, so 4px gutters), with ``p-0`` so the
            # 20px icon owns the whole square. The ``label`` drops to
            # ``w-0`` + ``flex-none`` (cf. its slot) and the ``badge`` to
            # ``hidden``, so the flex row holds nothing but the icon →
            # ``justify-center`` puts it in the centre.
            # Content-independent.
            "group-data-[open=false]/sidebar:justify-center "
            "group-data-[open=false]/sidebar:items-center "
            "group-data-[open=false]/sidebar:w-10 "
            "group-data-[open=false]/sidebar:h-10 "
            "group-data-[open=false]/sidebar:mx-auto "
            "group-data-[open=false]/sidebar:p-0 "
            "group-data-[open=false]/sidebar:gap-0 "
            # Tactile feedback: the click's scale animates; the hover
            # does NOT fade — a row of a list lights at once, or sliding
            # down the nav the previous one would trail. Not
            # ``transition-all``, which would animate everything, bg
            # included.
            # ``active:scale-[0.97]`` is a touch gentler than
            # Button's 0.95 — rows are full-width so the inset reads as
            # "pressed" without making neighbors visually shift. On a
            # locked row it is ``aria-disabled:active:scale-100`` that
            # cancels it; the inertness itself comes from the runtime
            # base layer.
            "transition-[scale] duration-150 ease-out "
            "active:scale-[0.97] "
            "overflow-hidden whitespace-nowrap "
            "outline-none text-muted "
            # The focus ring is drawn INSIDE the row. An outer ring with an
            # offset left the row by 4 px and covered its neighbours, which
            # sit 1.5 px away. Inside a solid active row the ``--bz-focus``
            # ring would vanish (the same hue on itself), so there it takes
            # the colour written ON the fill.
            "focus-visible:ring-2 focus-visible:ring-inset "
            "focus-visible:ring-(--bz-focus) "
            "data-[active=true]:focus-visible:ring-(--bz-on-solid) "
            # Hover bump aligned with Button's ghost variant (/10
            # rather than /5) so the row clearly responds to pointer.
            "data-[active=false]:hover:bg-text/10 "
            "data-[active=false]:hover:text-text "
            # Hover and press are neutralised EXPLICITLY on a locked
            # item: the inertness comes from the base layer
            # (``$bz._inert``, derived from ``aria-disabled``), not from a
            # ``pointer-events-none`` — which would have cancelled the
            # cursor.
            "aria-disabled:active:scale-100 "
            "aria-disabled:data-[active=false]:hover:bg-transparent "
            "aria-disabled:data-[active=false]:hover:text-muted "
            # ``<a>`` has no native ``disabled`` attribute, so the aria
            # classes alone would render the item grey while the link
            # went on navigating. What makes it REALLY inert is
            # ``apply_disabled``: it removes ``href``, the ``hx-*`` and
            # sets ``tabindex=-1``. The REACTIVE case, where that SSR
            # strip did not happen, is covered by ``$bz._inert`` on the
            # runtime side — no more ``pointer-events-none`` here.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ⚠️ ``data-[active=true]:`` on the ``text-`` is NOT cosmetic.
        # The root's ``text-muted`` and a BARE ``text-(--bz-on-solid)`` are
        # two utilities of the SAME specificity (0,1,0): the winner is the
        # last one in the Tailwind sheet, and the order of the ``class=``
        # attribute changes nothing. In the generated `@theme`
        # (`theme/tailwind.py`), ``muted`` comes LAST of the semantic
        # colours, so a compiled build would most likely keep the root's
        # grey on the active item. The variant raises the specificity to
        # (0,2,0): the verdict does not depend on any order.
        # Guarded by `tests/consistency/test_active_layer_outranks_root.py`.
        "active": (
            "bg-(--bz-solid) data-[active=true]:text-(--bz-on-solid) font-medium "
            "data-[active=true]:hover:bg-(--bz-solid-hover)"
        ),
        # Icon slot — fixed 1.25rem square, sits before the label.
        "icon": (
            "shrink-0 inline-flex items-center justify-center "
            "w-5 h-5 text-current"
        ),
        # Label — it FADES on collapse, exactly like ``title_brand``.
        #
        # ⚠️ Not ``hidden``: the fade costs the centring nothing.
        # ``w-0`` + ``flex-none`` give the space back AS completely as
        # ``display:none``, so the flex row still holds nothing but the
        # icon and ``justify-center`` puts it in the centre of the
        # ``w-10 h-10`` square, whatever the label's length.
        #
        # The three classes go together, and none is decorative:
        # ``opacity-0`` animates, ``w-0`` gives the space back,
        # ``flex-none`` stops the expanded state's ``flex-1`` from
        # re-inflating the box despite ``w-0``. A plain ``opacity-0``
        # keeps its place and makes the row overflow the 64 px strip.
        #
        # No ``invisible`` here, unlike ``title_brand``: this ``<span>``
        # is not focusable, there is no tab order to protect. The
        # collapsed row's accessible name does not depend on this slot
        # anyway — it travels on the link's ``aria-label`` (cf.
        # ``SidebarItem.render``).
        "label": (
            "flex-1 min-w-0 truncate "
            "transition-[opacity,width] duration-200 "
            "group-data-[open=false]/sidebar:opacity-0 "
            "group-data-[open=false]/sidebar:flex-none "
            "group-data-[open=false]/sidebar:w-0"
        ),
        # Badge — removed from layout entirely on collapse (its
        # ``ml-auto`` would otherwise fight the icon's centering).
        "badge": (
            "shrink-0 inline-flex items-center justify-center "
            "ms-auto transition-opacity duration-200 "
            "group-data-[open=false]/sidebar:hidden"
        ),
        # NB: the collapsed rail's tooltip (the item's name on hover)
        # comes from the page's shared tooltip panel (``tip.js``), which
        # each item triggers through ``data-bz-tip``. A single moved panel
        # costs one node instead of N; it is a choice, not a lapse of
        # dogfooding.
    },
}


SIDEBAR_FOOTER_THEME: dict[str, Any] = {
    "slots": {
        # Pinned to the bottom of the sidebar column (``mt-auto``) ;
        # holds the trigger row + the (floating) popover panel.
        "root": "relative mt-auto shrink-0 px-1 pb-1 pt-2",
        # The clickable account row : [avatar] [name + subtitle] [chevron].
        # Collapses to a centered avatar-only square in the rail — same
        # ``w-10`` box + centering as :data:`SIDEBAR_ITEM_THEME` rows.
        "trigger": (
            "group/acct flex flex-row items-center gap-2 w-full "
            "px-2 py-2 rounded-selector cursor-pointer text-start "
            "hover:bg-text/10 transition-colors outline-none "
            # Stays SELECTED while the popover is open (``data-menu-open``
            # mirrors the ``acct_open`` flag) — not just on hover. A
            # distinct attr (not ``data-open``, which is the sidebar's
            # collapse state) so the two never clash.
            "data-[menu-open=true]:bg-text/10 "
            # ``-surface`` for the same reason as the nav row: the footer
            # rests on the aside, not on the page background.
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-offset-2 focus-visible:ring-offset-surface "
            "group-data-[open=false]/sidebar:w-10 "
            "group-data-[open=false]/sidebar:h-10 "
            "group-data-[open=false]/sidebar:mx-auto "
            "group-data-[open=false]/sidebar:p-0 "
            "group-data-[open=false]/sidebar:justify-center "
            "group-data-[open=false]/sidebar:gap-0"
        ),
        # Initials/image chip. ``shrink-0`` keeps it square next to text ;
        # stays visible (centered) in the collapsed rail. Tinted by the
        # ``color`` prop via son pont (default primary).
        "avatar": (
            "shrink-0 inline-flex items-center justify-center "
            "h-9 w-9 rounded-selector bg-(--bz-bg) text-(--bz-text) "
            "text-xs font-semibold uppercase overflow-hidden"
        ),
        # Name + subtitle column ; folds away in the rail.
        "meta": (
            "flex flex-col min-w-0 flex-1 leading-tight text-start "
            "group-data-[open=false]/sidebar:hidden"
        ),
        "name": "text-sm font-semibold text-text truncate",
        "subtitle": "text-xs text-muted truncate",
        # Up/down chevron at the far edge ; folds away in the rail.
        "chevron": (
            "shrink-0 ms-auto "
            "group-data-[open=false]/sidebar:hidden"
        ),
        # The popover menu. ``$bz.helpers.floating`` flips it to
        # ``position:fixed`` on open, so it ESCAPES the sidebar's
        # ``overflow-y-auto`` clip. Same card identity as the Dropdown
        # panel — no vertical padding, ``overflow-hidden``, a hovered row
        # fills it to its edge (the why: ``overlay/dropdown/theme.py``);
        # ``z-50`` sits above the aside (z-40).
        "panel": (
            "min-w-[14rem] overflow-hidden z-50 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-surface "
            # The enter fade. The three classes go together and none
            # serves alone — the why is in a single copy in
            # ``overlay/dropdown/theme.py``.
            "shadow-lg "
            "transition-opacity duration-150 "
            "starting:opacity-0"
        ),
    },
}


# Rows inside the SidebarFooter popover — same look + slot contract as
# DropdownItem (both are :class:`MenuItem` shells), kept here so the
# sidebar doesn't reach into the overlay group for a theme.
SIDEBAR_FOOTER_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # hover/focus bg lives in ``colors`` (incl. ``neutral``), not root —
        # so coloured rows tint cleanly. Plain ``hover:`` so ``<a>`` link
        # rows tint. Disabled : aria-only + NO ``pointer-events-none`` so the
        # ``cursor-not-allowed`` affordance paints (MenuItem keeps the row
        # inert by stripping the handlers). Same contract as
        # DROPDOWN_ITEM_THEME (both are MenuItem).
        "root": (
            "group flex items-center gap-2 w-full text-start "
            "px-3 py-1.5 text-sm cursor-pointer outline-none "
            # No fade: a row lights at once and goes out at once — sliding
            # down a list, the previous row would trail behind the
            # pointer. As in a native menu.
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ``opacity-70`` so the icon inherits the row's tint (a ``color=``
        # row's icon matches its label instead of staying grey).
        "icon_left": "shrink-0 opacity-70",
        "label": "flex-1 truncate",
        "icon_right": "shrink-0 opacity-70",
        # The mark of a ``checked=`` row: always there, shown on the
        # chosen one (``aria-checked="true"``, fixed or bound), so the
        # labels of a choice menu line up.
        "check": "shrink-0 invisible group-aria-checked:visible",
        "shortcut": "shrink-0 ms-auto text-xs text-muted/70 tabular-nums",
    },
    "colors": {
        "neutral": "hover:bg-interface focus:bg-interface",
        "error":   "text-error hover:bg-error/10 focus:bg-error/10",
        "warning": "text-warning hover:bg-warning/10 focus:bg-warning/10",
        "success": "text-success hover:bg-success/10 focus:bg-success/10",
    },
}

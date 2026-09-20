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
  sidebar no longer ships a mobile drawer / topbar / hamburger.

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
            # Measured on 2026-08-15: with ``relative`` on the root, the
            # ``overlay`` mode rendered ``position: relative`` and
            # ``transform: none`` — the sidebar stayed in the flow and did
            # not close. Exactly the same trap as ``h-screen`` against
            # ``h-full``, met the same day.
            "group/sidebar shrink-0 flex flex-col h-screen "
            # ⚠️ NEITHER ``position`` NOR ``z-index`` here — both live in
            # the ``collapse`` table, one entry per mode. Same reason, and
            # the ``z-40`` that lingered here cost a visible bug: it
            # competed with ``overlay`` mode's ``z-50`` (two ``z-index``
            # utilities of the SAME specificity → the sheet order decides),
            # the sidebar dropped to the dimmed backdrop's level and found
            # itself BLURRED under its own backdrop.
            "p-2 gap-1 bg-surface "
            # The border used to live in a two-entry ``sides`` table,
            # removed along with the ``side=`` prop on 2026-08-15: a side
            # nav is on the left, so the border is on the right.
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
            "transition-[width] duration-300 ease-in-out "
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
        # bug this fixes ; cf. traps.md). ``flex flex-col gap-1`` keeps the
        # same inter-section rhythm the aside used to give as the direct
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
        # ``overflow`` clips its descendants' shadows. Measured on
        # 2026-08-15: the row was at 0px from both edges of this box, so
        # the ring was shaved on the left AND on the right, in ALL states
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
        "section": "flex flex-col gap-0.5",
        # ``font-semibold``, not ``font-bold``: surveyed on 2026-08-15,
        # the catalogue's four micro-capitals are ``divider.label``
        # (semibold), this sidebar's ``avatar`` (semibold) and
        # ``calendar.weekday`` (medium). The ``bold`` here was the only
        # one, and in a file that already uses semibold for its other
        # capital.
        "section_label": (
            "text-xs font-semibold text-muted uppercase tracking-wide "
            "px-2 py-1 mt-2 "
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
        # ── Rail tooltip: ONE shared panel for the whole sidebar ─────
        # In the collapsed rail each entry's label is ``hidden``, so we
        # bring it back on hover. A SINGLE panel, moved onto the hovered
        # entry, instead of a ``ui.tooltip`` per entry: 62 pre-rendered
        # panels weighed 94 kB, that is a third of the sidebar, for an
        # affordance that only ever shows one (measured 2026-07-27).
        #
        # Visibility is ENTIRELY in CSS — no ``bz-show``, which would set
        # an inline ``display`` and overwrite the rail's gate. Two
        # conditions composed as variants, like the entries themselves:
        # ``group-data-[open=false]/sidebar:`` = collapsed rail, and
        # ``data-[tip=on]`` = something is hovered.
        # ``position: fixed`` + ``top``/``left`` set from the entry's
        # rect: no assumption about the rail's width nor about the side.
        # ⚠️ The surface tokens are those of ``TOOLTIP_THEME["panel"]``,
        # literally — ``bg-text text-text-foreground``, ``px-2.5
        # py-1.5``, ``rounded-selector``, ``text-xs font-medium leading-tight``,
        # ``shadow-md``, ``max-w-xs``. This panel is NOT a ``ui.tooltip``
        # (a single shared panel instead of 62, cf. above), but it must
        # differ from one by nothing visible. Measured on 2026-08-25,
        # before alignment: the text pulled towards ``text-background``
        # (248,250,252) against (244,245,245) for the real tooltip, and
        # the panel had NO arrow at all.
        #
        # ``whitespace-nowrap`` is the ONLY accepted divergence: a rail
        # entry carries a short label, and folding it onto two lines next
        # to a 40 px icon reads badly.
        "rail_tip": (
            "fixed z-50 px-2.5 py-1.5 rounded-box "
            "text-xs font-medium leading-tight whitespace-nowrap "
            # The STEPS, and the ``bz-c-text`` bridge set on the node at
            # render time: it is exactly what a ``ui.tooltip``'s panel
            # writes, and the two are read side by side in the same app
            # (``test_rail_tip_looks_like_a_tooltip``).
            "bg-(--bz-solid) text-(--bz-on-solid) shadow-md "
            "max-w-xs break-words pointer-events-none "
            # ``top`` receives the hovered entry's vertical CENTRE; the
            # half offset is done here, not in JS with a guessed panel
            # height.
            "-translate-y-1/2 "
            "opacity-0 invisible transition-opacity duration-150 "
            "group-data-[open=false]/sidebar:data-[tip=on]:opacity-100 "
            "group-data-[open=false]/sidebar:data-[tip=on]:visible"
        ),
        # The rail panel's arrow. ONE set of classes, not the four sides
        # of ``TOOLTIP_THEME["arrow"]``: a side nav lives on the left
        # (``Sidebar._CUT["side"]``) and the panel anchors on
        # ``aside.right + 8``, so it is ALWAYS to the right of the entry.
        # The arrow is therefore always on its left edge.
        # ``right-full`` = ``right: 100%``, which pushes the square
        # entirely out of the panel to the left; ``-mr-1`` brings it back
        # 4 px so it blends into the corner.
        #
        # The parent is ``fixed``, so it is already a containing block for
        # an ``absolute`` child — no ``relative`` to add.
        "rail_tip_arrow": (
            "absolute h-2 w-2 rotate-45 bg-(--bz-solid) "
            "right-full top-1/2 -translate-y-1/2 -mr-1"
        ),
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
            # Reported like this — "I have to click to the millimetre",
            # "I can overshoot on the left but not on the right".
            # ⚠️ ``w-4`` = 16 px, and it is a TRADE-OFF, not a setting.
            # 24 px (the WCAG 2.2 § 2.5.8 target floor) covered the right
            # 13 px of the rail's nav icons — measured: they had only
            # 28 clickable px of 40 left, and it showed. 16 px take only
            # 4 (the icons keep 36 px) while staying far more aimable
            # than the clipped version's ~12 usable px.
            #
            # What we lose: the strip alone no longer meets the touch
            # floor. It stays as tall as the whole bar — so a 16 × 600 px
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
            # ⚠️ Fade AND release of the width, both. This block carried
            # ``hidden``: ``display:none`` does remove the space but
            # kills any transition, so the title JUMPED (measured:
            # ``display:none`` at 60 ms, opacity still at 1.00). A plain
            # ``opacity-0`` does the opposite — it fades, but keeps its
            # place in the row, and the logo then overflows the 64 px
            # strip by 8 px (also measured, by the probe, while writing
            # this fix).
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
        # ⚠️ The original comment said "matches the rail toggle's 40px
        # box" and named a ``title_rail_toggle`` slot. It does not exist,
        # nor does the button it pointed at: the auto floating chevron
        # was removed on 2026-08-21. Corrected on 2026-08-29.
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
        # ⚠️ The fade, and why it is NOT ``hidden``. This slot carried
        # ``transition-opacity duration-200`` AND
        # ``group-data-[open=false]:hidden``: ``display:none`` is not
        # animatable, so the transition was DECLARED AND DEAD. Measured
        # frame by frame on 2026-08-18 — the text jumped to
        # ``display:none`` in 60 ms, opacity still at 1.00, then the
        # strip shrank for 300 ms over an already empty box.
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
        # ⚠️ Until 2026-08-26, this comment described the mechanism the
        # block below explains it REMOVED: "a single button : logo by
        # default, swapped to a chevron on hover ; ``group/railtoggle``
        # drives the icon swap". Two neighbouring paragraphs therefore
        # told two opposite designs — and it was the stale one you read
        # first. ``probe_sidebar`` looked for
        # ``button[class*="railtoggle"]`` for five days, found nothing,
        # and concluded that Tailwind was not compiling.
        #
        # ``grid place-items-center`` (and not flex) centres the glyph in
        # the single cell, whatever its size.
        # The logo, in the collapsed rail. It used to be a collapse
        # BUTTON carrying the logo and turning into a chevron ON HOVER —
        # so, on a machine without hover, a logo that never announced it
        # collapsed anything. The gesture existed and nobody could
        # discover it (finding [29], 2026-08-21).
        #
        # It is now a LINK, leading where the expanded logo leads
        # (``href=``, ``/`` by default): the logo stops changing job
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
    # Desktop EXPANDED width preset.
    "widths": {
        "sm": "w-48",
        "md": "w-64",
        "lg": "w-80",
    },
    # ── A SINGLE axis: what "collapsed" means ────────────────────────
    # Replaces the 2026-08-15 pair ``variant=`` (rail/drawer) +
    # ``collapsible=`` (True/False). Two props, four combinations, one of
    # them absurd (``collapsible=False`` + drawer = a sidebar you can
    # neither collapse nor reach). One axis, four values, zero illegal
    # combination — shadcn's split, plus ``overlay``.
    #
    # ⚠️ NO ``md:`` gate on any of the four modes, and that is a
    # decision. They all had one until 2026-08-15 — a legacy of the time
    # when the sidebar was "desktop chrome" and had to refuse to collapse
    # on a small screen.
    #
    # That is no longer true: it is the DEV who chooses the mode, in
    # their ``if Screen().is_mobile``. The CSS has no business
    # contradicting them. As long as it did, two bugs lived together —
    # collapsing below 768px did NOTHING (measured: 256px → 256px), and
    # it was enough for the ``bz_screen`` cookie to be one render late (a
    # resize, a first load) to end up with an open sidebar impossible to
    # close.
    #
    # Each mode also carries its ``position`` AND its ``z-index``: these
    # are utilities whose two values compete at equal specificity, so
    # leaving them on ``root`` made the winner depend on the Tailwind
    # sheet's order. Both got caught the same day.
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
        # survives.
        "overlay": (
            "fixed inset-y-0 left-0 z-50 shadow-2xl "
            "transition-transform duration-300 ease-in-out "
            "data-[open=false]:-translate-x-full"
        ),
        "none": "relative z-40",
    },
    # The dimmed backdrop of ``overlay`` mode, teleported under
    # ``<body>`` by ``Sidebar.render`` — otherwise it would live INSIDE
    # the aside, so above itself and below nothing at all.
    "backdrop": (
        "fixed inset-0 z-40 bg-black/50 backdrop-blur-sm "
        "transition-opacity duration-300 "
        "data-[open=false]:opacity-0 data-[open=false]:invisible "
        "data-[open=false]:pointer-events-none"
    ),
}


SIDEBAR_ITEM_THEME: dict[str, Any] = {
    "slots": {
        "root": (
            # ⚠️ ``text-sm`` DECLARED. It was missing, and a nav row with
            # no size inherits the browser's ``text-base``: measured on
            # 2026-08-15 at the bench, ``fontSize: 16`` on the row,
            # against 14 for ``navbar_item`` AND for
            # ``sidebar_footer_item`` — the other kind of row in the SAME
            # file. So it was not a choice, it was the omission that made
            # that one row stick out of the repository's whole
            # typographic scale. Intended side effect: the line height
            # goes from 40 to 36px (the leading follows the size), which
            # tightens the rhythm without touching the padding and keeps
            # a correct touch target.
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
            # Motion + tactile feedback — aligned with Button. ``-all``
            # so the bg/text transition AND the click scale animate
            # together. ``active:scale-[0.97]`` is a touch gentler than
            # Button's 0.95 — rows are full-width so the inset reads as
            # "pressed" without making neighbors visually shift. On a
            # locked row it is ``aria-disabled:active:scale-100`` that
            # cancels it; the inertness itself comes from the runtime
            # base layer.
            "transition-all duration-200 ease-out "
            "active:scale-[0.97] "
            "overflow-hidden whitespace-nowrap "
            "outline-none text-muted "
            # ⚠️ ``ring-offset-SURFACE``, not ``-background``, and it is not
            # cosmetic. The ring's offset is PAINTED: it must blend with the
            # background the row rests on. Yet the aside is ``bg-surface``
            # (#0f172a) and the ``background`` token is #020617 — DARKER.
            # Measured in the browser on 2026-08-15:
            # ``--tw-ring-offset-shadow: 0 0 0 2px rgb(2 6 23)`` on an aside
            # at ``rgb(15 23 42)``, which draws a black outline around the
            # focused row instead of an invisible offset.
            # The catalogue's 30 other ``ring-offset-background`` are right:
            # those are controls sitting on the PAGE background. The sidebar
            # (like the navbar) is the special case — it paints its own
            # surface under its focusable children.
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-surface "
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
        # attribute changes nothing. Measured on `bottom_bar`, which
        # carried the same shape: two colours out of six rendered GREY in
        # dev — and in the generated `@theme` (`theme/tailwind.py`),
        # ``muted`` comes LAST of the eleven semantic colours, so a
        # compiled build would most likely lose them all. The variant
        # raises the specificity to (0,2,0): the verdict no longer depends
        # on any order.
        # Guarded by `tests/consistency/test_active_layer_outranks_root.py`.
        "active": (
            "bg-(--bz-solid) data-[active=true]:text-(--bz-on-solid) font-medium "
            "data-[active=true]:hover:bg-(--bz-solid)/90"
        ),
        # Icon slot — fixed 1.25rem square, sits before the label.
        "icon": (
            "shrink-0 inline-flex items-center justify-center "
            "w-5 h-5 text-current"
        ),
        # Label — it FADES on collapse, exactly like ``title_brand``.
        #
        # ⚠️ It carried ``hidden`` until 2026-09-01, and the comment of
        # the time presented that as a trade-off: "we swap the fade for
        # an unconditional centring". The swap had no reason to be —
        # ``w-0`` + ``flex-none`` give the space back AS completely as
        # ``display:none``, so the flex row still holds nothing but the
        # icon and ``justify-center`` puts it in the centre of the
        # ``w-10 h-10`` square, whatever the label's length. The centring
        # costs the fade nothing; both simply had to be written.
        #
        # The three classes go together, and none is decorative:
        # ``opacity-0`` animates, ``w-0`` gives the space back,
        # ``flex-none`` stops the expanded state's ``flex-1`` from
        # re-inflating the box despite ``w-0``. A plain ``opacity-0``
        # keeps its place and makes the row overflow the 64 px strip —
        # measured on ``title_brand``, which got there the same way.
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
        # comes from the SHARED ``rail_tip`` panel — a single node, last
        # child of the aside, that each item moves by writing
        # ``rail_tip`` / ``rail_tip_x`` / ``rail_tip_y`` into the aside's
        # scope.
        # ⚠️ This comment announced a ``ui.tooltip(...)`` per item until
        # 2026-08-01: ``sidebar.py`` neither imports nor instantiates
        # Tooltip (zero occurrences). A single moved panel costs one node
        # instead of N; it is a choice, not a lapse of dogfooding.
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
        # panel ; ``z-50`` sits above the aside (z-40).
        "panel": (
            "min-w-[14rem] py-1 z-50 "
            "rounded-box border-(length:--bz-stroke) border-text/10 bg-interface "
            # The enter fade. The three classes go together and none
            # serves alone — the why is in a single copy in
            # ``overlay/dropdown/theme.py``.
            "shadow-lg "
            "transition-[opacity,display] transition-discrete duration-150 "
            "starting:opacity-0"
        ),
    },
}


# Rows inside the SidebarFooter popover — same look + slot contract as
# DropdownItem (both are :class:`MenuItem` shells), kept here so the
# sidebar doesn't reach into the overlay group for a theme (anti-rule 5).
SIDEBAR_FOOTER_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # hover/focus bg lives in ``colors`` (incl. ``neutral``), not root —
        # so coloured rows tint cleanly. Plain ``hover:`` so ``<a>`` link
        # rows tint. Disabled : aria-only + NO ``pointer-events-none`` so the
        # ``cursor-not-allowed`` affordance paints (MenuItem keeps the row
        # inert by stripping the handlers). Same contract as
        # DROPDOWN_ITEM_THEME (both are MenuItem).
        "root": (
            "flex items-center gap-2 w-full text-start "
            "px-3 py-1.5 text-sm cursor-pointer outline-none "
            "transition-colors duration-100 "
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ``opacity-70`` so the icon inherits the row's tint (a ``color=``
        # row's icon matches its label instead of staying grey).
        "icon_left": "shrink-0 opacity-70",
        "label": "flex-1 truncate",
        "icon_right": "shrink-0 opacity-70",
        "shortcut": "shrink-0 ms-auto text-xs text-muted/70 tabular-nums",
    },
    "colors": {
        "neutral": "hover:bg-text/[0.06] focus:bg-text/[0.06]",
        "error":   "text-error hover:bg-error/10 focus:bg-error/10",
        "warning": "text-warning hover:bg-warning/10 focus:bg-warning/10",
        "success": "text-success hover:bg-success/10 focus:bg-success/10",
    },
}

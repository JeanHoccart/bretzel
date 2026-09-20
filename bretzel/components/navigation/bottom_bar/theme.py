"""Default theme for the BottomBar family (BottomBar / BottomBarItem).

Two pieces, the *bottom of screen* counterpart of the Navbar trio:

- **BottomBar** — the ``<nav>`` stuck to the bottom of the viewport.
  ``sticky bottom-0`` and not ``fixed``: a sticky element **stays in the
  flow**, so it reserves its own height and the page's content is never
  masked — without the "spacer" node a ``fixed`` would have required, and
  which would have broken the universal kwargs (cf. the component's
  docstring).
- **BottomBarItem** — a tab: icon ABOVE the label, ``flex-1`` so every
  tab has the same width. That is the whole visual identity vs
  ``NavbarItem`` (horizontal pill, content width) — the behaviour, for
  its part, is shared word for word through ``navigation/_wiring``.

Composition rule (it carries two measured corrections, cf. the comments
in place): **a CSS property is declared by one layer only**, and any
class that must BEAT a root class carries a state variant, never the bare
form. The component no longer having any axis (neither ``variant`` nor
``sticky`` — both cut, cf. the component), everything fits in ``slots``
and the rule reads at a glance.

Slots :
- ``bottom_bar.root``     : the ``<nav>`` — geometry only
- ``bottom_bar.inner``    : the row of tabs (flex-row)
- ``item.root``           : the tab, icon + label column
- ``item.active``         : layer added when the tab is active
- ``item.icon_wrap``      : relative icon + badge container
- ``item.icon``           : icon slot
- ``item.label``          : the text under the icon
- ``item.badge``          : the PLACEMENT of the chip, at the icon's corner
- ``item.badge_pill``     : its default LOOK — scalar only, a Component
                            passed as badge keeps its own
"""

from __future__ import annotations

from typing import Any

BOTTOM_BAR_THEME: dict[str, Any] = {
    # ⚠️ THIS theme's composition rule: **a CSS property is declared only
    # ONCE**. Two competing utilities of the same specificity would let
    # the Tailwind sheet's order decide, not the ``class=``'s order — it
    # is the trap documented on the item's active layer, below, and it
    # cost two invisible colours.
    "slots": {
        # ``mt-auto``: in a ``flex flex-col`` layout taller than its
        # content (the case of an app shell in ``min-h-screen``), the bar
        # is pushed to the bottom rather than floating under a short
        # content. In classic block flow, ``margin-top: auto`` is 0 — no
        # side effect.
        #
        # ``pb-[env(safe-area-inset-bottom)]``: the iPhone's gesture bar
        # eats the bottom of the viewport. Without this padding, the last
        # tab is half under the line. On a device with no notch,
        # ``env()`` is 0 — so no cost.
        #
        # ``z-30``: same step as the navbar, below the sidebar (40) and
        # below dialog/drawer (50) — a modal paints over the bar.
        # ``sticky bottom-0``: the bar stays IN the flow — it reserves
        # its height, so nothing is ever masked — but refuses to leave
        # the screen at the bottom as long as its container goes lower.
        # That is what a tab bar is: a tab always under the thumb. It is
        # not an option (no ``sticky=`` prop, cf. the component): a bar
        # that goes away on scroll is no longer a tab bar.
        #
        # The background goes slightly translucent + ``backdrop-blur-md``
        # so the content scrolling underneath softens instead of
        # disappearing all at once (iOS idiom).
        "root": (
            "group/bottombar w-full mt-auto z-30 "
            "sticky bottom-0 bg-surface/95 backdrop-blur-md "
            "border-t-(length:--bz-stroke) border-text/10 "
            "pb-[env(safe-area-inset-bottom)]"
        ),
        # The row. It is each item's ``flex-1`` that makes the widths
        # equal (the tab bar idiom). ``14`` (56px) aligns the height with
        # the navbar's, so an app carrying both has the same gauge at the
        # top and at the bottom.
        #
        # ⚠️ ``min-h-14`` and NOT ``h-14``: with a FIXED height, an icon
        # larger than the default (``icon=ui.icon(…, size="xl")`` → 36px)
        # plus the gap plus the label exceed the available room, and the
        # ``overflow:hidden`` that ``truncate`` sets on the label clips it
        # VERTICALLY — the text shrinks to a sliver of glyphs. Seen by eye
        # on a screenshot, invisible to measurement: ``scrollWidth ==
        # clientWidth`` (nothing overflows horizontally) and the label has
        # its normal width. The repository settles this case on the
        # framework side: a component never clips its own content, it is
        # an invariant, not a trade-off left to the app (cf. todo.md
        # § A-ter, "Containment").
        "inner": "flex flex-row items-stretch min-h-14 w-full",
    },
    # ⚠️ NO ``variants`` table — and it is deliberate (decision
    # 2026-08-09). A rounded pill detached from the edges (the iOS 17 /
    # Material 3 idiom) existed here as ``variant="floating"`` for a day,
    # then was cut: it fails the four criteria of the opinionation rule,
    # and first of all the decisive one — "would we have this component
    # in TWO shapes in the SAME app?". No: an app has a single tab bar,
    # and the choice of look is made once. An axis you set only once per
    # app is a THEME decision, not a prop.
    #
    # The escape hatch is the documented tier 2 (``theme.md``), a
    # deep-merged override, gated by ``test_theme_override_merge`` ::
    #
    #     Bretzel(theme=Theme(components={"bottom_bar": {"slots": {
    #         "root": "group/bottombar w-full mt-auto z-30 mx-3 mb-3 "
    #                 "rounded-box border border-text/10 shadow-lg "
    #                 "pb-[env(safe-area-inset-bottom)]",
    #     }}}))
    #
    # Do NOT reintroduce a ``variant`` here without two shapes really
    # co-occurring in one view. Same verdict, and same reason, as
    # ToggleGroup's ``segmented``.
}


BOTTOM_BAR_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # The tab — icon/label column, ``flex-1`` for equal width,
        # ``min-w-0`` so the label can ellipsise instead of pushing its
        # neighbours.
        #
        # ``active:scale-[0.94]`` one step more marked than the navbar's
        # (0.97): a touch target needs more readable feedback than a
        # mouse hover, and it is a component made for the finger.
        #
        # No ``hover:bg-*`` here, unlike NavbarItem: on mobile hover does
        # not exist (memory `user_browser_has_no_fine_pointer` recalls it
        # even on desktop), and a background the full width of the tab is
        # visually heavy. Hover only changes the text's colour.
        #
        # ``focus-visible:ring-inset`` and not ``ring-offset-2``: the bar
        # is bordered and with no inner margin, an overflowing halo would
        # be clipped.
        "root": (
            "group/tab relative flex flex-1 min-w-0 flex-col "
            "items-center justify-center gap-1 px-1 py-1.5 "
            "cursor-pointer select-none "
            "transition-all duration-200 ease-out "
            "active:scale-[0.94] "
            "outline-none text-muted "
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-inset "
            "data-[active=false]:hover:text-text "
            # Hover and press are neutralised EXPLICITLY on a locked
            # item: the inertness comes from the base layer
            # (``$bz._inert``, derived from ``aria-disabled``), not from a
            # ``pointer-events-none`` — which would have cancelled the
            # cursor.
            "aria-disabled:active:scale-100 "
            "aria-disabled:data-[active=false]:hover:text-muted "
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # The active state does NOT repaint a background: on a tab bar,
        # it is the colour of the icon + label that signals the current
        # tab (iOS/Android).
        #
        # ⚠️ ``data-[active=true]:`` is NOT cosmetic — it is what makes
        # the active colour WIN. A bare ``text-(--bz-text)`` and the
        # root's ``text-muted`` are two utilities of the SAME specificity
        # (0,1,0): the winner is the one that comes later in the Tailwind
        # sheet, and the order of the ``class=`` attribute changes
        # NOTHING.
        #
        # Seen in the browser: with the bare form, ``color=error`` and
        # ``color=info`` rendered GREY (the four others passed). Do not
        # trust that particular split to infer a rule: in dev, Tailwind
        # runs in the browser and emits its rules **in the order it meets
        # the classes in the DOM** — so which side loses depends on the
        # page. The only stable order is that of the generated `@theme`
        # (`bretzel/theme/tailwind.py`), where ``muted`` comes **last** of
        # the eleven semantic colours: in a compiled build, the bare form
        # would most likely lose for ALL SIX colours. There is no
        # compiled build today to assert it (cf. memory
        # `reference_css_build_reality`), and that is precisely the
        # argument: the variant raises the specificity to (0,2,0), so the
        # verdict no longer depends on an order — neither the dev's nor a
        # future build's.
        #
        # The ``navbar`` and ``sidebar`` siblings still carry the bare form.
        "active": "data-[active=true]:text-(--bz-text) font-semibold",
        # Relative icon + badge container: it is what anchors the chip
        # to the ICON's corner, not to the tab's (which is far wider than
        # its content because of the flex-1).
        "icon_wrap": "relative inline-flex items-center justify-center",
        # No ``text-*`` here: ``<iconify-icon>`` sizes itself by
        # ``font-size``, and a size class set on the slot would compete
        # with the one the Icon component composes itself (cf. traps.md
        # § iconify-icon). The size therefore goes through
        # ``Icon(size="lg")`` in ``__init__``.
        "icon": "shrink-0 text-current",
        # ⚠️ ``leading-tight`` and NOT ``leading-none``. ``truncate``
        # implies ``overflow: hidden``; with ``line-height: 1``, the line
        # box is exactly the font size (11px) while the glyphs ask for
        # ~13 — so the descenders of "g" / "p" were clipped on EVERY
        # label. Measured: ``scrollHeight`` 13 vs ``clientHeight`` 11 on
        # the bench page's 100 tabs.
        #
        # The instrumentation trap was worth the lesson: the containment
        # probe only read the HORIZONTAL axis (``scrollWidth``), so it
        # was green while the text was cut off vertically. A clipping
        # defect is measured on both axes.
        "label": "max-w-full truncate text-[11px] leading-tight",
        # ⚠️ The badge is in TWO slots, and the split is load-bearing.
        #
        # ``badge`` = the PLACEMENT alone. It applies to any chip,
        # including a Component the caller styled themselves
        # (``badge=ui.badge("new", color="success")``). ``left-full
        # -ml-1`` rather than ``-right-2``: the anchoring starts from the
        # icon's right edge, so it holds whatever the glyph's width.
        #
        # ``badge_pill`` = the default LOOK, applied ONLY when the value
        # is a scalar — the only case where the framework has to invent a
        # visual. Measured before this split: a Component passed as badge
        # came out with ``bg-error`` AND ``bg-success/15``,
        # ``text-[10px]`` twice, and two competing text colours. It
        # rendered green in dev by luck of sheet order; ``error`` being
        # generated AFTER ``success`` in the `@theme`, a compiled build
        # would have turned it red. A component decides its look; the
        # parent only places it.
        #
        # ``text-error-foreground`` and not ``text-white``: the framework
        # emits a ``-foreground`` companion for every semantic colour
        # (`theme/tailwind.py`), so the digit follows a redefined palette
        # — a pale ``error`` would keep readable text, where a hard-coded
        # white would disappear. The chip's colour, for its part, stays
        # hard-coded ``error``: a notification is red whatever the tab's
        # colour.
        "badge": (
            "absolute -top-1 left-full -ml-1 "
            "inline-flex items-center justify-center"
        ),
        "badge_pill": (
            "min-w-4 h-4 px-1 rounded-full "
            "bg-error text-error-foreground text-[10px] font-semibold "
            "leading-none"
        ),
    },
}

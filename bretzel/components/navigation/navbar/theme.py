"""Default theme for the Navbar family (Navbar / NavbarSection / NavbarItem).

Three pieces, horizontal counterpart to the Sidebar trio :

- **Navbar** — the ``<header>`` container, full-width flex row. Sticky
  optional. Same ``current_path`` reactive scope (``bz-data``) as
  Sidebar so a single page can host both and they stay in sync on
  partial nav.
- **NavbarSection** — positional groupings (``left`` / ``center`` /
  ``right``) inside the navbar. Just flex containers with the right
  margin auto, no behaviour of their own.
- **NavbarItem** — horizontal nav row, mirror of SidebarItem with a
  different look (underline / bg pill on hover-and-active rather than
  fade-on-collapse). Reuses the same htmx partial-nav wiring +
  ``current_path``-driven active state.

Slots :
- ``navbar.root``         : the ``<header>`` flex row
- ``navbar.inner``        : the inner ``<nav>`` flex row (max-width clamp)
- ``navbar.section_left``     : left section flex container
- ``navbar.section_center``   : center section flex container
- ``navbar.section_right``    : right section flex container
- ``item.root``           : NavbarItem outer ``<a>`` / ``<div>``
- ``item.active``         : extra classes layered when the row is active
- ``item.icon``           : icon slot wrapper
- ``item.label``          : label text
- ``item.badge``          : trailing badge
"""

from __future__ import annotations

from typing import Any

NAVBAR_THEME: dict[str, Any] = {
    "slots": {
        # Outer ``<header>`` — full-bleed, surface background, optional
        # border. ``z-30`` sits below the sidebar (z-40) and dialog/drawer
        # (z-50), so a modal paints over the navbar.
        # ⚠️ The reason given here until 2026-08-01 — "a sidebar open on
        # mobile also darkens the navbar through its backdrop" — no
        # longer holds: the sidebar NO LONGER has a mobile drawer nor a
        # backdrop (removed from the component on 2026-07-14, mobile is
        # the dev's ``if Screen().is_mobile``). The z-index order stays
        # right, for the teleported overlays.
        "root": (
            "group/navbar w-full bg-surface z-30 "
            "border-b-(length:--bz-stroke) border-text/10"
        ),
        # Inner ``<nav>`` — clamps max-width + horizontal padding for
        # comfortable line length on wide viewports. Mirror of Container
        # but local to navbar so we don't accidentally pick up vertical
        # padding from a future Container theme change.
        "inner": (
            "mx-auto w-full max-w-screen-2xl "
            "px-4 sm:px-6 lg:px-8 "
            "flex flex-row items-center gap-4 h-14"
        ),
        # Per-side section containers. ``mr-auto`` on left + ``ml-auto``
        # on right push them to the edges ; center uses ``mx-auto``.
        # Each section is itself a flex-row so items + components inside
        # align naturally without an extra wrapper.
        "section_left": "flex flex-row items-center gap-2 me-auto",
        "section_center": (
            "flex flex-row items-center gap-2 mx-auto"
        ),
        "section_right": "flex flex-row items-center gap-2 ms-auto",
    },
    # ``sticky=True`` injects fixed positioning so the bar stays at the
    # top during page scroll. Backdrop blur softens content sliding
    # underneath.
    "sticky": "sticky top-0 backdrop-blur-md bg-surface/95",
    # ``variant`` axis kept narrow for v1 — "standard" = the default
    # bordered bar, "floating" = rounded card detached from the viewport
    # edges (Stripe / Linear marketing site idiom).
    "variants": {
        "standard": "",
        "floating": (
            "max-w-screen-2xl mx-auto mt-3 rounded-box "
            "border-(length:--bz-stroke) border-text/10 shadow-sm bg-surface/95 "
            "backdrop-blur-md"
        ),
    },
}


NAVBAR_ITEM_THEME: dict[str, Any] = {
    "slots": {
        # Outer pill — horizontal padding, gap for icon+label, hover bg
        # bump, active bg-color highlight. Same motion idiom as
        # SidebarItem (transition-all + active:scale-[0.97]) so the
        # whole nav family feels consistent.
        "root": (
            "group/row relative inline-flex flex-row items-center gap-2 "
            "px-3 py-1.5 rounded-box cursor-pointer "
            "transition-all duration-200 ease-out "
            "active:scale-[0.97] "
            "whitespace-nowrap "
            "outline-none text-muted text-sm font-medium "
            # ``-surface``, not ``-background``: the ring's offset is
            # PAINTED, so it must equal the background the entry rests on
            # — and the navbar's ``<header>`` is ``bg-surface``. With
            # ``-background`` (two steps darker) every focused entry
            # surrounded itself with a black outline. Same fault as the
            # sidebar's, fixed the same day; gated by
            # ``test_ring_offset_matches_its_surface``. The navbar has NO
            # ``overflow``, so unlike the sidebar it did not need room
            # made for the ring.
            "focus-visible:ring-2 focus-visible:ring-(--bz-focus) "
            "focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-surface "
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
            "aria-disabled:opacity-50 aria-disabled:cursor-not-allowed"
        ),
        # ⚠️ ``data-[active=true]:`` on the ``text-`` is NOT cosmetic.
        # The root's ``text-muted`` and a BARE ``text-(--bz-text)`` are
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
            "bg-(--bz-bg) data-[active=true]:text-(--bz-text) "
            "data-[active=true]:hover:bg-(--bz-bg-hover)"
        ),
        "icon": (
            "shrink-0 inline-flex items-center justify-center "
            "w-4 h-4 text-current"
        ),
        "label": "truncate",
        "badge": (
            "shrink-0 inline-flex items-center justify-center "
            "ml-1 text-xs"
        ),
    },
}

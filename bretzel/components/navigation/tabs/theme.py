"""Default :class:`Tabs` / :class:`Tab` / :class:`TabPanel` theme.

**One visual identity, no variants.** Each tab's label lives inside a
rounded *pill* (a badge) sitting above a shared baseline. The active
tab tints its pill (soft colour fill + coloured text) AND draws a 2px
coloured underline where its slot meets the baseline — a Crédit-Agricole
style tab strip.

The active state is driven entirely by a ``data-selected`` attribute on
the tab button :

- rendered STATIC (``data-selected="true"``) server-side on the initial
  active tab, so the active styling is correct at first paint, before
  the runtime hydrates ;
- kept reactive via ``bz-attr:data-selected`` so the runtime flips it on
  click.

The underline is pure CSS — ``data-[selected=true]:border-(--bz-solid)`` on
the button — so there is NO JavaScript measurement, no ``ResizeObserver``,
no sliding-indicator effect. The pill picks up the active tint through
Tailwind ``group-*`` selectors keyed on the same ``data-selected`` attribute.

Slots :
- ``root``    : outer wrapper (tablist stacked above the panels)
- ``tablist`` : the row of tab buttons + the shared baseline border
- ``tab``     : the ``<button role="tab">`` — carries ``group`` (so the
  pill can read its ``data-selected``) and the active underline
- ``pill``    : the ``<span>`` badge holding the icon + label
- ``panel``   : individual ``<div role="tabpanel">`` wrapper
"""

from __future__ import annotations

from typing import Any

TABS_THEME: dict[str, Any] = {
    "slots": {
        # Tablist stacked above the panels.
        "root": "flex flex-col gap-3",
        # Row of tab buttons sharing a hairline baseline. ``items-end``
        # so buttons of differing heights align on the baseline ; the
        # active button's 2px underline overlaps this 1px border via the
        # button's ``-mb-px``.
        "tablist": "flex items-end gap-1 border-b-(length:--bz-stroke) border-text/10",
        # The tab BUTTON. Only chrome + the active underline live here —
        # the visible label sits in the ``pill`` span below. ``group`` so
        # the pill can read this button's ``data-selected``. ``-mb-px``
        # pulls the 2px underline down over the tablist's 1px baseline so
        # the active segment reads as a single thick line.
        #
        # The button carries the resting + hover TEXT colour ; the pill
        # inherits it (and overrides only when active). This keeps the
        # hover gated by ``not-disabled:`` on the same element that owns the
        # ``:disabled`` state — the family idiom (Button / ToggleGroup /
        # Pagination) — so a disabled tab shows ``cursor-not-allowed``
        # with no hover tint, no ``pointer-events`` hack needed. Cf.
        # traps.md § "hover: sur un control disabled".
        "tab": (
            "group relative inline-flex items-center justify-center "
            "px-1.5 pb-1.5 -mb-px cursor-pointer outline-none text-muted "
            "border-b-(length:--bz-stroke-strong) border-transparent "
            "transition-[color,border-color] duration-200 ease-out "
            "not-disabled:hover:text-text "
            "focus-visible:ring-2 focus-visible:ring-offset-2 "
            "focus-visible:ring-offset-background "
            "focus-visible:ring-(--bz-focus) rounded-t-selector "
            "disabled:opacity-50 disabled:cursor-not-allowed "
            "data-[selected=true]:border-(--bz-solid)"
        ),
        # The label badge. Inherits the button's text colour at rest /
        # hover ; when the parent button is active it gets its own tinted
        # fill + coloured text. The ``group-data-[selected=true]:``
        # selectors read the button's ``data-selected`` attribute
        # (SSR-static then reactive).
        "pill": (
            "inline-flex items-center gap-2 rounded-selector font-medium "
            "transition-colors duration-200 ease-out "
            "group-data-[selected=true]:bg-(--bz-bg) "
            "group-data-[selected=true]:text-(--bz-text)"
        ),
        # ``col-start-1 row-start-1`` : all panels overlap in the same
        # grid cell of the parent ``.grid`` container (see
        # ``Tabs.render``) so a cross-fade doesn't stack them vertically.
        "panel": "outline-none col-start-1 row-start-1",
    },
    # Per-size dict — applied to the pill badge (text size + padding).
    "sizes": {
        "xs": {"pill": "text-[10px] px-2 py-0.5"},
        "sm": {"pill": "text-xs px-2.5 py-1"},
        "md": {"pill": "text-sm px-3 py-1"},
        "lg": {"pill": "text-base px-4 py-1.5"},
        "xl": {"pill": "text-lg px-5 py-2"},
    },
}

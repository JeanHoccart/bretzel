"""The app's only global: its theme.

**The scale comes from the framework**, and the app has nothing to ask
for: it is the DEFAULT shipped since 2026-09-13. It used to live here in
a 351-line ``core/preset.py`` resizing eleven components one by one;
``examples/ecole`` copied it, ended up with four field heights on one
screen (the eleven components NOT named stayed at the default), and both
apps ended up proving the same thing: density moves through the BASE of
the scale, not component by component.

What stays here is what the framework does not decide, because a shipped
scale never carries a brand:

- **the neutrals**, a very slightly desaturated mauve-grey rather than
  Tailwind's bluish slate, and a near-black in dark mode — it is the
  background of a card board, which must recede;
- **the hue**, a teal;
✅ **The two component refinements left for the framework** on
2026-09-13 — the badge's tabular figures and the card with a hairline
rather than a shadow at rest. They lived here by copying the shipped slot
string to change a single word in it, so they froze that day's version:
the need had nothing specific to a card board, and that is what made them
defaults, not overrides.
"""

from bretzel.theme import Theme

THEME = Theme(
    semantic={
        "primary": "#0d9488",  # teal
        "background": "#fbfbfc",
        "surface": "#ffffff",
        "interface": "#f6f6f8",
        "text": "#17171a",
        "muted": "#6e6e78",
    },
    semantic_dark={
        "background": "#0a0a0c",
        "surface": "#111114",
        "interface": "#191920",
        "text": "#f2f2f4",
        "muted": "#8a8a95",
    },
    components={
        "badge": {
            "slots": {
                "root": (
                    "inline-flex w-fit items-center gap-1 "
                    "max-w-[min(16rem,100%)] rounded-selector font-medium "
                    "leading-normal tabular-nums whitespace-nowrap "
                    "transition-colors duration-150"
                ),
            },
        },
        "card": {
            "slots": {
                "root": (
                    "block w-full rounded-box overflow-hidden "
                    "bg-(--bz-solid) text-(--bz-on-solid) "
                    "border-(length:--bz-stroke) border-text/8"
                ),
            },
            # ⚠️ The ``aria-disabled:`` selectors are copied as is:
            # they neutralise the relief by specificity (0,3,0 beats
            # 0,2,0), and omitting them would make a locked surface lift
            # on hover.
            "hoverable": (
                "transition-all duration-150 ease-out cursor-pointer "
                "relative top-0 "
                "hover:border-text/20 "
                "hover:shadow-sm "
                "hover:-top-px "
                "aria-disabled:cursor-default "
                "aria-disabled:hover:top-0 "
                "aria-disabled:hover:shadow-none "
                "aria-disabled:hover:border-text/8"
            ),
        },
    },
)

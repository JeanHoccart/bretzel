"""Semantic / palette name catalogue + type literals.

Pure constants — no class, no I/O. Imported by every other theme
module that needs to validate a color name or list the slots.

Two distinct concepts:

- **Semantic** : 11 fixed slots known to every component. The values
  change ; the names are part of the framework grammar.
- **Palette** : an open list of named hex colors. The user can add,
  remove or override entries — no framework-level meaning attached.
"""

from __future__ import annotations

from typing import Final, Literal

# ───────────────────────────────────────────────────────────────────────────
# Breakpoints — the Tailwind scale, single source
# ───────────────────────────────────────────────────────────────────────────
#
# It lives HERE and not in ``components/base/responsive.py`` (which
# re-exports it) because the SAFELIST needs it: ``responsive_classes``
# can prefix any graded class with any of these breakpoints, so the
# safelist's closure spans both axes. And ``theme`` may not import
# ``components`` — that is the DAG's meaning, checked by
# ``import-linter``. Two parallel tuples would have drifted: a breakpoint
# added on one side would have produced classes the compiler does not
# know, with no error.

BREAKPOINTS: Final[tuple[str, ...]] = ("sm", "md", "lg", "xl", "2xl")


# ───────────────────────────────────────────────────────────────────────────
# Semantic slots — 11, fixed, framework-known
# ───────────────────────────────────────────────────────────────────────────


SEMANTIC_COLOR_NAMES: Final[tuple[str, ...]] = (
    "primary",
    "secondary",
    "success",
    "error",
    "warning",
    "info",
    "background",
    "surface",
    "interface",
    "text",
    "muted",
)


SemanticColors = Literal[
    "primary",
    "secondary",
    "success",
    "error",
    "warning",
    "info",
    "background",
    "surface",
    "interface",
    "text",
    "muted",
]


# ───────────────────────────────────────────────────────────────────────────
# Font slots — 3, fixed, and deliberately Tailwind's own three
# ───────────────────────────────────────────────────────────────────────────
#
# These are not invented names: ``--font-sans`` / ``--font-serif`` /
# ``--font-mono`` are the tokens Tailwind v4 defines itself, and its
# preset's ``--default-font-family: var(--font-sans)`` means redefining
# ``sans`` changes the WHOLE page's font through the preflight
# (``html { font-family: var(--default-font-family, …) }``, verified in the
# compiled CSS). The ``font-sans`` / ``font-serif`` / ``font-mono``
# utilities follow for free — and ``Heading`` already hard-codes
# ``font-sans`` in its theme, so headings follow without a component
# moving.
#
# **No fourth slot** (``display``, ``heading``…): it would have to be
# invented on the Tailwind side AND Heading's theme rewritten, when a
# distinct heading font is already obtained through
# ``Theme(components={"heading": {"slots": {...}}})``.
#
# **No default is copied here.** An empty ``fonts`` section emits nothing
# and Tailwind's stacks hold. Copying ``ui-sans-serif, system-ui, …``
# into this file would create a duplicate whose only possible evolution
# is to diverge from upstream, silently.

FONT_SLOT_NAMES: Final[tuple[str, ...]] = ("sans", "serif", "mono")


# ───────────────────────────────────────────────────────────────────────────
# The scale — its BASE, not a multiplier
# ───────────────────────────────────────────────────────────────────────────
#
# The shipped base is Tailwind's (4 px step, 12/14/16/18/20/24 text). Its
# steps all land on integer line heights; a 13 px text has a FRACTIONAL one
# (18.57 px, Tailwind's ratio applied to a size it was not drawn for), which
# sets a button's label off centre.
#
# Two tokens, and they are Tailwind v4's: ``--spacing``, the unit every
# spacing utility derives from (``h-10`` is
# ``calc(var(--spacing) * 10)``, like ``p-4``, ``gap-2`` and ``w-6``), and
# ``--text-<step>``, which the ``text-*`` utilities read.
#
# **Why the base and not a slider.** Each component already has its
# ``size=``, and a global multiplier would be a second way of doing the
# same thing. ``size=`` picks a step; the theme decides which scale.
#
# An app wanting a dense tool scale writes
# ``Theme(spacing="0.1875rem", text={"xs": "11px", "sm": "13px",
# "base": "14px", …})``. Moving the base is what keeps a screen coherent:
# resizing components one by one leaves the others at the default and
# puts several field heights on one screen. A hand-written list is a list
# of the components one thought to name.
#
# **The market is unanimous on the mechanism, not on the name.** Ant
# Design ships a whole preset (``compactAlgorithm``) driven by seed
# tokens — ``sizeUnit`` 4, ``sizeStep``, ``controlHeight`` 32,
# ``fontSize`` 14; Radix Themes and Reflex expose a percentage
# (``scaling``); Mantine a ``scale`` plus its ``fontSizes``/``spacing``
# dicts. All move a base, none resizes component by component. The names
# kept here are Tailwind's because they are the tokens ACTUALLY read —
# same reason as the three font slots, and same benefit: nothing to
# translate.

#: The shipped spacing step: Tailwind's 4 px — a ROUND figure, and that is
#: the point. On a fractional step, ``h-10`` falls between two pixels,
#: which browsers round differently depending on the control's structure
#: (height on the bordered element, or on its child), so fields nothing
#: distinguishes in the code differ in height. On a whole pixel, every
#: notch lands on an integer.
DEFAULT_SPACING: Final[str] = "0.25rem"

#: The same step in PIXELS, for apps that must CALCULATE — the height of
#: an N-hour block in a grid is made of a number of notches, and a
#: Tailwind class cannot add up. Two authorities over
#: one quantity do not compose: their agreement is gated.
DEFAULT_SPACING_PX: Final[int] = 4

#: The shipped text steps — Tailwind's (12/14/16/18/20/24).
#:
#: ⚠️ **The display steps ARE PART OF IT.** ``ui.icon``'s size scale goes
#: up to ``text-6xl`` (``xl`` is ``text-4xl``, ``2xl`` is ``text-6xl``),
#: and ``ui.file_upload`` writes ``text-5xl``. Left out, an icon would
#: keep its upstream size in a button brought down with the scale, and
#: stick out — invisible to any reading of classes.
#:
#: That is the trap's general shape, and it holds beyond here: leaving
#: half of one quantity on the upstream scale and moving the other is two
#: authorities that do not compose. A BOX measured in notches and a GLYPH
#: measured in text steps must move together.
DEFAULT_TEXT: Final[dict[str, str]] = {
    "xs": "12px",
    "sm": "14px",
    "base": "16px",
    "lg": "18px",
    "xl": "20px",
    "2xl": "24px",
    "3xl": "30px",
    "4xl": "36px",
    "5xl": "48px",
    "6xl": "60px",
}

#: The ``--text-*`` steps, that is to say the ones Tailwind v4 defines.
#: Closed like the fonts: ``Theme(text={"md": …})`` is not an extension
#: but a token nothing will read — Tailwind's scale says ``base`` where a
#: component's ``size=`` says ``md``, and it is the component that
#: translates.
#:
#: ⚠️ A literal size is out of reach of this parameter — moving the base
#: does not move ``text-[10px]``; ``test_a_text_size_is_a_step`` refuses
#: one in a component theme. The page's own inherited size is the median
#: step too: ``<body>`` carries ``text-base`` (``render/shell.py``).
TEXT_SLOT_NAMES: Final[tuple[str, ...]] = (
    "xs",
    "sm",
    "base",
    "lg",
    "xl",
    "2xl",
    "3xl",
    "4xl",
    "5xl",
    "6xl",
    "7xl",
    "8xl",
    "9xl",
)


# ───────────────────────────────────────────────────────────────────────────
# Shape — the three radius families
# ───────────────────────────────────────────────────────────────────────────
#
# Emitted in ``@theme`` as ``--radius-<family>``, so Tailwind v4 builds
# real utilities from them: ``rounded-box``, ``rounded-field``,
# ``rounded-selector``, with their corner variants (``rounded-l-field``).
#
# **Why three families and not a scale.** A scale does not say why a
# component takes one step rather than another, and a single slider laid
# over it settles nothing decidable; three NAMED families make the
# question decidable at the call site.
#
# The cut is daisyUI 5's (``--radius-box`` / ``--radius-field`` /
# ``--radius-selector``), the only system on the market to partition by
# family — Radix, Material 3, Ant Design, Fluent, Bootstrap and Mantine
# all use a global scale plus a per-component assignment.
#
# ⚠️ **``rounded-full`` belongs to no family, and that is the most
# important rule here.** The roundness of a switch, a radio, a spinner or
# a progress bar is their SHAPE, not their style: squaring them would
# make the switch read as a checkbox. Radix Themes reaches the same
# conclusion and writes it down — for them "full" makes a button a pill
# but will never make a checkbox round, "to prevent any confusion between
# it and a Radio". 32 slots therefore stay hard-coded.

#: The three families, and what they mean:
#:
#: - ``box`` — the element CONTAINS other elements (card, panel, dialog,
#:   surface).
#: - ``field`` — a control one aims at, with a frame of its own (button,
#:   field, picker trigger).
#: - ``selector`` — a small mark, or a control NESTED inside another
#:   (checkbox, badge, clear cross, dot).
SHAPE_SLOT_NAMES: Final[tuple[str, ...]] = ("box", "field", "selector")

#: The three families of spacing, named after the radii's, plus the room
#: between blocks:
#:
#: - ``field`` — the controls: a button's height, a field's padding. It
#:   is Tailwind's ``--spacing``, which every ``h-10``, ``px-3`` reads;
#: - ``box``   — the padding INSIDE what contains: card, pane, dialog;
#: - ``gap``   — the space BETWEEN blocks: stacks, grids, flex rows.
#:
#: Separate steps let an app make its pages tighter without shrinking its
#: buttons under a finger. ``box`` and ``gap`` follow ``field`` unless the
#: theme says otherwise.
SPACING_SLOT_NAMES: Final[tuple[str, ...]] = ("field", "box", "gap")

#: The multiples of the ``gap`` step that the layout components' scale
#: writes (``gap="md"`` → ``--bz-gap-4``), and of the ``box`` step their
#: paddings write (``padding="md"`` → ``--bz-pad-4``, ``--bz-pad-6`` from
#: ``sm`` up). Emitted as variables, ONE table per family: the component
#: themes read them.
GAP_STEPS: Final[tuple[int, ...]] = (1, 2, 4, 6, 8)
PAD_STEPS: Final[tuple[int, ...]] = (2, 3, 4, 6, 8, 10)

#: The stroke width, and its two derived steps.
#:
#: **One single setting**, unlike the radius: the market is unanimous
#: where it diverges on shape. daisyUI (``--border``), Ant Design
#: (``lineWidth``) and Bootstrap (``--bs-border-width``) expose a global
#: width; Radix, Mantine, Material 3 and shadcn expose none. Nobody
#: partitions, and the repository gives the reason: its border vocabulary
#: is ALREADY decidable — 1 px everywhere, 2 px for emphasis (the
#: `outline` button, the active tab), 4 px for a side accent (the banner,
#: the quotation), 0 to remove.
#:
#: Hence the two DERIVED steps rather than tuned ones: if emphasis were a
#: fixed number, pushing the base to 2 px would make it disappear — the
#: `outline` button would stop being distinguishable from the solid one.
#: Here the ratio holds at every value.
#:
#: ⚠️ ``--bz-stroke`` and not ``--bz-border``: the latter is ALREADY a
#: colour step of the bridges (:mod:`bretzel.theme.bridges`), and
#: ``border-(--bz-border)`` compiles to ``border-color``. The collision
#: would have been silent one way (a width read as a colour) and
#: destructive the other. The name comes from Fluent 2, which calls its
#: width tokens ``strokeWidth*``.
DEFAULT_STROKE: Final[str] = "1px"

#: The default radius of each family. 8 px on a 40 px field reads as a
#: rounded rectangle, where a larger radius reads as a pill.
#: ``rounded-full`` slots are untouched (cf. above: their roundness is
#: their shape).
DEFAULT_SHAPE: Final[dict[str, str]] = {
    "box": "0.625rem",
    "field": "0.5rem",
    "selector": "0.25rem",
}


# ───────────────────────────────────────────────────────────────────────────
# Default palette — 31 named hex shipped with Bretzel
# ───────────────────────────────────────────────────────────────────────────


DEFAULT_PALETTE_NAMES: Final[tuple[str, ...]] = (
    # Neutrals.
    "gray",
    "mauve",
    "slate",
    "sage",
    "olive",
    "sand",
    # Reds & pinks.
    "tomato",
    "red",
    "ruby",
    "crimson",
    "pink",
    "plum",
    # Purples & blues.
    "purple",
    "violet",
    "iris",
    "indigo",
    "blue",
    "cyan",
    "sky",
    # Greens.
    "teal",
    "jade",
    "green",
    "grass",
    # Warms.
    "yellow",
    "amber",
    "orange",
    "gold",
    "bronze",
    "brown",
    # Extremes.
    "black",
    "white",
)


PaletteColors = Literal[
    "gray", "mauve", "slate", "sage", "olive", "sand",
    "tomato", "red", "ruby", "crimson", "pink", "plum",
    "purple", "violet", "iris", "indigo", "blue", "cyan", "sky",
    "teal", "jade", "green", "grass",
    "yellow", "amber", "orange", "gold", "bronze", "brown",
    "black", "white",
]  # fmt: skip


# ───────────────────────────────────────────────────────────────────────────
# Convenience union — every color the resolver can recognise
# ───────────────────────────────────────────────────────────────────────────


# In practice users pass plain ``str`` — the literal types are
# documentation hints for IDEs / mypy. The runtime checks the value
# against the actual palette at render time.
AnyColor = SemanticColors | PaletteColors | str


# ───────────────────────────────────────────────────────────────────────────
# Internal CSS prefix for palette colors
# ───────────────────────────────────────────────────────────────────────────


# Palette names share a global CSS namespace with Tailwind's stock
# utilities (``bg-red-500``, …). Prefixing our colors with ``ui-``
# avoids any clash without leaking the prefix to the user. ``color="red"``
# does not write ``bg-ui-red``: it sets the colour BRIDGE ``bz-c-red``
# (``bridges.py``), whose variables the component's classes read; the
# ``bg-ui-red`` utility stays for an app's own ``classes=``.
PALETTE_CLASS_PREFIX: Final[str] = "ui-"


# Foreground class is derived by appending this suffix to the class
# stem (``primary`` → ``primary-foreground``).
FOREGROUND_SUFFIX: Final[str] = "-foreground"

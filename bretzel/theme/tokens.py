"""Semantic / palette name catalogue + type literals.

Pure constants — no class, no I/O. Imported by every other theme
module that needs to validate a color name or list the slots.

Two distinct concepts (cf. ``.claude/bretzel/theme.md`` § *Mental model*) :

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
# ``Theme(components={"heading": {"slots": {...}}})``. Settled on
# 2026-08-16.
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
# ⚠️ **Since 2026-10-23 the shipped base IS Tailwind's again** (4 px step,
# 12/14/16/18/20/24 text). Jean's decision, on three variants of the same
# form rendered side by side. The 3 px / 14 px tool scale chosen on
# 2026-09-13 (history below) had two measured costs:
#
# - next to seven other frameworks rendering the same helpdesk
#   (python-ui-shootout), Bretzel read cramped — 30 px fields, 13 px
#   control text — where the others sit at 36 to 40 px;
# - its 13 px text has a FRACTIONAL line height (18.57 px, Tailwind's
#   ratio applied to a size it was not drawn for): a button's label sat
#   1.6 px above centre (6.7 px above it, 8.3 below, measured in
#   Chromium). Tailwind's steps all land on integer line heights; the
#   same button at 40 px reads 12 / 12.
#
# The mechanism below is unchanged: an app that wants the dense tool
# scale takes it back with ``Theme(spacing="0.1875rem", text={…})``.
#
# Two tokens, and they are Tailwind v4's: ``--spacing``, the unit every
# spacing utility derives from (``h-10`` is
# ``calc(var(--spacing) * 10)``, like ``p-4``, ``gap-2`` and ``w-6``), and
# ``--text-<step>``, which the ``text-*`` utilities read.
#
# ⚠️ **Bretzel sets its own values, and that is the subject.** This is not
# the upstream duplicate the fonts avoid: a copied value can only
# diverge, a CHOSEN value says something. Tailwind targets pages —
# controls at 40 px, body text at 16 px — and Bretzel is for building
# TOOLS, which show a lot in little space. Inheriting a document's scale
# was a flaw by omission, not a decision (2026-09-13).
#
# The reference point: Ant Design's defaults are ``controlHeight`` 32 and
# ``fontSize`` 14, roughly where these land, and its "compact" preset goes
# lower STILL. So it was Bretzel's default that was the exception.
#
# **Why the base and not a slider.** This place said "density is NOT
# open" until 2026-09-13, on the grounds that each component already has
# its ``size=`` and that a global multiplier would be a second way of
# doing the same thing. The grounds still hold — and its own get-out
# clause said what to open the day the need came up: *the BASE of this
# scale, not a new axis*. That is what is here. ``size=`` still picks a
# step; the theme decides which scale.
#
# Since 2026-10-23 the default IS the document scale (cf. the warning at
# the top of this section); an app wanting the dense tool scale writes
# ``Theme(spacing="0.1875rem", text={"xs": "11px", "sm": "13px",
# "base": "14px", …})`` — the 2026-09-13 values, still a valid choice.
#
# The need came up twice, measured: ``examples/kanban`` then
# ``examples/ecole`` each rewrote the same correction — the first by
# resizing eleven components one by one, which left eleven others at the
# default and put four field heights on one screen. A hand-written list
# is a list of the components one thought to name.
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

#: The shipped spacing step, and **exactly 3 px** — the round figure is
#: the point. At ``0.205rem``, ``h-10`` was 32.8 px: a step between two
#: pixels, which browsers round differently depending on the control's
#: structure (height on the bordered element, or on its child). Measured
#: on ``examples/ecole``: 31 px on one side, 33 on the other, for fields
#: nothing distinguishes in the code. At 3 px, every notch lands on an
#: integer.
DEFAULT_SPACING: Final[str] = "0.25rem"

#: The same step in PIXELS, for apps that must CALCULATE — the height of
#: an N-hour block in a grid is made of a number of notches, and a
#: Tailwind class cannot add up (cf.
#: ``examples/ecole/features/emploi_du_temps.py``). Two authorities over
#: one quantity do not compose: their agreement is gated.
DEFAULT_SPACING_PX: Final[int] = 4

#: The shipped text steps — one notch below Tailwind's
#: (12/14/16/18/20/24), which is the measurement two apps had found
#: separately before the framework settled it.
#:
#: ⚠️ **The display steps ARE PART OF IT, and that was measured.** This
#: place said "``3xl`` and above are not set: no chrome writes them".
#: That was false, and the price was a defect: ``ui.icon``'s size scale
#: goes up to ``text-6xl`` (``xl`` is ``text-4xl``, ``2xl`` is
#: ``text-6xl``), and ``ui.file_upload`` writes ``text-5xl``. A chevron
#: left at 36 px in a button brought down to 33 stuck out by **1.5 px** —
#: invisible to any reading of classes, found by
#: ``probe_calendar_width`` in French AND in English.
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
#: does not move ``text-[10px]``. There were 31 in the component themes,
#: all gone to ``text-xs`` on 2026-09-27; ``test_a_text_size_is_a_step``
#: refuses the next one. The page's own inherited size is the median step
#: too: ``<body>`` carries ``text-base`` (``render/shell.py``).
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
# Verified against the production binary on 2026-08-30.
#
# **Why three families and not a scale.** The repository had six (xl 46×,
# full 31×, md 28×, lg 12×, sm 7×, 2xl 3×) and nothing wrote down why a
# component took one rather than another. A single slider laid over six
# tokens with no logic settles nothing decidable; three NAMED families
# make the question decidable at the call site.
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

#: The starting values were 12 / 12 / 6 px (the ones most slots carried
#: when the families were cut, 2026-08-30). On 2026-10-23 they became
#: 10 / 8 / 4 px, Jean's call: "slightly squarer by default". On a 30 px
#: field, 12 px of radius read as a pill everywhere; 8 px on 40 px reads
#: as a rounded rectangle. ``rounded-full`` slots are untouched (cf.
#: above: their roundness is their shape).
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
# avoids any clash without leaking the prefix to the user — the
# framework rewrites ``color="red"`` to ``bg-ui-red`` at render time.
PALETTE_CLASS_PREFIX: Final[str] = "ui-"


# Foreground class is derived by appending this suffix to the class
# stem (``primary`` → ``primary-foreground``).
FOREGROUND_SUFFIX: Final[str] = "-foreground"

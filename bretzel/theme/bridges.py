"""The colour bridges — twelve steps derived from one source hue.

A **bridge** is a CSS class which, set on an element, installs there the
twelve variables component themes use to paint themselves ::

    <span class="bz-c-error bg-(--bz-bg) text-(--bz-text)">

The bridge does the translation; the theme now speaks only the steps'
vocabulary. That is what replaces the ``bg-{bg_color}`` templates, whose
flaw is structural: ``bg-{bg_color}`` is not a class but a **half-class**,
invisible to the Tailwind compiler, which therefore had to be closed by
hand — every shape × every colour.

Twelve **steps**, 43 **bridges**: the eleven semantic colours, plus
``current`` (cf. :data:`CURRENT_COLOR_NAME`), whose source is the
inherited colour and not a theme name.

What the steps make possible, and what was impossible
-----------------------------------------------------

1. **Tinting a whole zone.** ``bz-c-error`` on a container tints
   everything it holds, with no child knowing about it. Today one has to
   pass ``color="error"`` to each of them.
2. **Repainting ONE instance.** ``style="--bz-solid: #b91c1c"`` changes
   the eleven steps of that one component. No ``classes=`` can do that:
   it would mean rewriting every state, hover and focus included.
3. **A THIRD-PARTY component that tints itself.** It writes
   ``bg-(--bz-bg)``, a complete and literal class, so the compiler sees
   it. Nothing to declare, nothing to close.

Why eleven names and not numbers
--------------------------------

The names say the **intention**, not the CSS property nor a rank: that
is the convention the repository already follows for its foregrounds
(``--color-primary-foreground``), and shadcn's. One writes
``bg-(--bz-bg-hover)`` because one wants a background's hover, not
because one wants "step 4".

The scale itself is Radix's, whose twelve steps are defined by their
ROLE. **Opacity is not an absolute value, it is a step relative to the
substrate** — a hover laid on a ``/15`` background and a hover laid on a
solid fill cannot carry the same opacity. Absolute steps make the
problem disappear.

Dark mode is free
-----------------

No ``.dark`` rule here, and that is not an oversight. The formulas start
from ``--color-<name>``, ``--color-surface`` and ``--color-text``, which
are **already** redefined in the theme's ``.dark`` block. A bridge
written once therefore re-evaluates itself on the other side: the ramp
inverts without a single ``dark:`` class.

One exception, and it is measured, not styled: the two TEXT steps keep as
much of the colour as stays readable, and that depends on the mode's own
value of the colour (cf. :func:`readable_step_pct`). Where the dark
percentage differs, a ``.dark .bz-c-<name>`` rule restates those two
steps; nothing else is ever written per mode.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Final

from bretzel.theme.palette import Palette, ThemeError
from bretzel.theme.tokens import (
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
)

#: A bridge class's prefix. ``bz-c-primary``, ``bz-c-error``…
BRIDGE_CLASS_PREFIX = "bz-c-"

#: The two variables INTERNAL to the bridge: the source hue and its
#: foreground. They appear in no component theme — a theme reads the
#: steps, never the source. Exposing them would reopen the door we are
#: closing: ``bg-(--bz-src)/15`` would reinvent opacity as a way of
#: manufacturing a step.
SOURCE_VAR = "--bz-src"
SOURCE_FOREGROUND_VAR = "--bz-src-foreground"

#: The twelve steps, in scale order. The value is the formula, written
#: with ``{src}``, ``{fg}``, ``{surface}`` and ``{text}``.
#:
#: ``--bz-text`` and ``--bz-text-muted`` MIX TOWARDS THE TEXT. The raw
#: colour (Radix step 9) and its wash towards the surface fall below WCAG
#: AA on their own background for most colours; the mix is the way to
#: write "the TEXT version of this colour".
#:
#: Each colour gets its own percentages, per mode, starting from the
#: colour itself (:func:`readable_step_pct`). ``--bz-text`` holds 4.5:1;
#: ``--bz-text-muted`` holds the AFFORDANCE bar (WCAG 1.4.11: 3:1 for a UI
#: component): its sites are icons and close buttons, which go solid on
#: hover.
#:
#: ⚠️ **There is no room for two text steps both at 4.5:1** with this
#: palette, because the source hues are too light (the yellow above all).
#: Radix gets away with twelve steps tuned by hand per hue; here we name
#: the constraint instead of masking it.
#:
#: ``in srgb``, not ``in oklab``.
#:
#: Mixing towards ``--color-surface`` in sRGB **is** the operation an
#: opacity already performs: ``bg-error/50`` composites in sRGB. The two
#: spellings are therefore algebraically the same thing. In oklab, **no
#: percentage reproduces an opacity**: the gap depends on the HUE, so it
#: cannot be fixed with one number.
#:
#: The usual objection — "an sRGB mix crosses grey and goes muddy in the
#: middle of the scale" — is true of two CHROMATIC colours being mixed.
#: These formulas mix towards the surface, that is to say towards white
#: or near-black: there is no grey to cross.
#:
#: ⚠️ A perceptually uniform scale remains a better DESIGN goal, and it
#: is what would make the steps regular. But that is a visual change: it
#: has to be decided and shown on its own.
#:
#: ``feedback/notification/theme.py`` writes ``color-mix`` literally too.
COLOR_STEPS: tuple[tuple[str, str, str], ...] = (
    # (step name, formula, what it is for)
    (
        "--bz-bg",
        "color-mix(in srgb, var({src}) 10%, var({surface}))",
        "background of a tinted component (Radix 3)",
    ),
    (
        "--bz-bg-hover",
        "color-mix(in srgb, var({src}) 20%, var({surface}))",
        "son survol (Radix 4)",
    ),
    (
        "--bz-bg-active",
        "color-mix(in srgb, var({src}) 30%, var({surface}))",
        "its selected / active state (Radix 5)",
    ),
    (
        "--bz-border",
        "color-mix(in srgb, var({src}) 35%, var({surface}))",
        "bordure au repos (Radix 6-7)",
    ),
    (
        "--bz-border-hover",
        "color-mix(in srgb, var({src}) 50%, var({surface}))",
        "bordure au survol / au focus (Radix 7)",
    ),
    (
        "--bz-focus",
        "color-mix(in srgb, var({src}) 40%, transparent)",
        "anneau de focus (Radix 8)",
    ),
    (
        "--bz-focus-soft",
        "color-mix(in srgb, var({src}) 30%, transparent)",
        "SUSTAINED focus ring — a field's, lit for the whole time one "
        "types, hence more discreet",
    ),
    (
        "--bz-solid",
        "var({src})",
        "aplat plein (Radix 9)",
    ),
    (
        "--bz-solid-hover",
        "color-mix(in srgb, var({src}) 88%, var({text}))",
        "son survol (Radix 10)",
    ),
    (
        "--bz-on-solid",
        "var({fg})",
        "what is written ON the solid fill",
    ),
    (
        "--bz-text-muted",
        "color-mix(in srgb, var({src}) {pct_muted}%, var({text}))",
        "muted accented text (Radix 11) — an AFFORDANCE, not body "
        "text: the bar is 3:1 (WCAG 1.4.11), held at 3.41",
    ),
    (
        "--bz-text",
        "color-mix(in srgb, var({src}) {pct_text}%, var({text}))",
        "accented text (Radix 12) — readable, the bar is 4.5:1, held "
        "at 4.82 at worst",
    ),
)

#: The step names alone — what a component theme is allowed to write.
STEP_NAMES: tuple[str, ...] = tuple(name for name, _f, _r in COLOR_STEPS)


#: The twelfth bridge, whose source is not a NAMED colour.
#:
#: ``color="current"`` is the default of ``ui.icon``, ``ui.spinner`` and
#: ``ui.breadcrumb``, and it drives the whole datatable toolbar: it is
#: the framework's most widespread ``color=`` value, and without it phase
#: 3 would stumble on its most used component. ``currentColor`` is a real
#: CSS value, so the eleven formulas work on it with nothing changed.
#:
#: ⚠️ ``--bz-on-solid`` is the only SOFT choice of the twelve bridges:
#: ``current`` has no ``-foreground`` companion, so we take the page
#: background — what one writes on a solid fill made of the inherited
#: colour. It is an inert choice today: the four components that fall
#: back on ``current`` write **no** ``{fg_color}`` (verified), so nothing
#: reads it.
CURRENT_COLOR_NAME = "current"
CURRENT_COLOR_SOURCE = "currentColor"
CURRENT_COLOR_FOREGROUND = "var(--color-background)"

#: The steps the ``current`` bridge does NOT derive — it returns them
#: as-is.
#:
#: ⚠️ ``--bz-text`` on ``current`` is the inherited colour itself: **a
#: default icon takes its parent's colour.** Any mix towards the page text
#: would be invisible on a neutral background, where the inherited colour
#: IS the page text. On a solid fill — a ``solid`` button, a badge, an
#: alert — the two diverge, and the icon would come out a different colour
#: from the word it accompanies.
#:
#: It is also what ``icon/theme.py``'s docstring promises: "the icon
#: inherits its parent's text colour".
#:
#: Only ``--bz-text`` is concerned: it is the only step a component with
#: ``color="current"`` writes on text. ``--bz-bg`` &co stay derived, and
#: they make sense on ``currentColor`` as on the rest.
CURRENT_COLOR_IDENTITY_STEPS: frozenset[str] = frozenset({"--bz-text"})


def bridge_class(color: str) -> str:
    """A colour's bridge class name. ``primary`` → ``bz-c-primary``."""
    return f"{BRIDGE_CLASS_PREFIX}{color}"


def _color_var(name: str, *, semantic: bool) -> str:
    """The Tailwind variable carrying this colour.

    Semantic slots are emitted without a prefix (``--color-primary``),
    named colours with the palette's (``--color-ui-tomato``) — that is
    ``tailwind._emit_block``'s convention, not a choice remade here.
    """
    stem = name if semantic else f"{PALETTE_CLASS_PREFIX}{name}"
    return f"--color-{stem}"


@lru_cache(maxsize=8)
def bridged_color_names(palette: Palette) -> tuple[str, ...]:
    """The colours that receive a bridge.

    **Exactly what ``color=`` accepts**: the eleven semantic slots,
    ``current``, and the whole palette — the one the framework ships as
    well as the one the app adds.

    The rule is **coverage**. A missing bridge is not a saving, it is a
    component that renders without a colour: its steps are undefined, so
    its properties invalid (``ui.badge(color="tomato")`` would lose all
    its style).

    The count follows from the PALETTE's size, not from a list maintained
    here: a smaller palette returns fewer names without a line being
    touched, and an app declaring ``brand`` has its bridge.

    Coverage's cost is small against what it replaces: the bridges weigh
    a fraction of the shape × colour closure.

    Why it is memoised
    ------------------

    The body sweeps the whole palette — ``envelope_dict()`` recomputes a
    ``bg_class`` and an ``fg_class`` for each of its colours. That is
    cheap once, and this function is called by
    :func:`base/theme_values.refuse_unknown_color`, so
    **once per coloured component**, so a render would answer the same
    question many times over.

    The bet is safe, unlike ``escape_attr``'s: a
    :class:`~bretzel.theme.palette.Palette` is built once at startup, its
    tables are written only in its ``__init__``, and ``Theme.get_palette``
    always returns the same instance. The reuse rate is therefore not
    "high", it is **total** — and
    ``test_the_color_bridge_memo_still_pays`` checks it, because the day
    a palette were rebuilt per request, nothing would break: the page
    would stay correct, it would merely have gone slow again.
    """
    names = list(SEMANTIC_COLOR_NAMES) + [CURRENT_COLOR_NAME]
    names += sorted(set(palette.envelope_dict()) - set(SEMANTIC_COLOR_NAMES))
    return tuple(names)


#: The two TEXT steps and the bar each must clear.
#:
#: ``--bz-text`` is accented body text: WCAG AA, 4.5:1.
#: ``--bz-text-muted`` is an AFFORDANCE and not body text, so its bar is
#: the components' one (WCAG 1.4.11), 3:1.
_TEXT_STEP_TARGETS: Final[dict[str, tuple[str, float]]] = {
    "pct_text": ("--bz-text", 4.5),
    "pct_muted": ("--bz-text-muted", 3.0),
}

#: The STARTING percentages — the ramp we want, when it is readable.
_TEXT_STEP_BASE: Final[dict[str, int]] = {"pct_text": 100, "pct_muted": 70}

#: How far we back off at each step, and how far we go. Backing off
#: means LESS hue and more text — so more contrast, in both modes.
_TEXT_STEP_DOWN: Final[int] = 5
_TEXT_STEP_FLOOR: Final[int] = 25

#: The SURFACE slots, kept out of the derivation.
#:
#: ⚠️ **They would fail the same bar, and this is not a convenience
#: exemption:** they would back off too.
#:
#: They are kept out because **the gate does not judge them** — none of
#: these five is among the colours ``test_the_colour_steps_stay_readable``
#: holds. Moving them would change the appearance of
#: components against a bar nobody has ever held them to, and with no
#: measurement saying whether that is progress: a ``color="white"``
#: serves a white badge on a dark banner, not text on the page, so the
#: background to measure against is not the one this derivation assumes.
#:
#: It is therefore an open question, not an oversight. Widening it first
#: requires deciding WHAT a surface slot is measured AGAINST.
_SURFACE_SLOTS: Final[frozenset[str]] = frozenset({
    "background", "surface", "interface", "white", "black",
})


def readable_step_pct(
    palette: Palette, color: str, step: str, mode: str = "light"
) -> int:
    """The hue percentage of step ``step`` in ``mode``: as much of the
    colour as stays readable.

    The palette gives each colour a light AND a dark value; this reads the
    one of ``mode``. The ramp starts from the colour ITSELF (100 %) and
    mixes it towards the text only as far as its bar requires, against
    every ground it is written on: the page, a panel, and the colour's own
    tint (``--bz-bg``, a soft badge or an alert).

    Why
    ---
    One percentage for every colour in both modes would pull the text step
    towards the text colour even where the colour reads on its own: an
    outline button would write its label in a shade its border does not
    share.

    ``--bz-text-muted`` never carries more hue than ``--bz-text``'s
    percentage would allow it to drop to: it starts from
    ``max(70, text)``, so a colour readable as it is gives both steps the
    colour itself.

    Backing off increases contrast (the text is by construction the colour
    contrasting most with the ground), so the loop always ends.
    """
    base = _TEXT_STEP_BASE[step]
    _name, target = _TEXT_STEP_TARGETS[step]
    if color == CURRENT_COLOR_NAME or color in _SURFACE_SLOTS:
        # ``currentColor`` has no resolvable value: nothing to measure,
        # so nothing to back off. The SURFACE slots are kept out for
        # another reason — cf. ``_SURFACE_SLOTS``.
        return base
    if step == "pct_muted":
        base = max(base, readable_step_pct(palette, color, "pct_text", mode))
    for pct in range(base, _TEXT_STEP_FLOOR - 1, -_TEXT_STEP_DOWN):
        if _step_ratio(palette, color, mode, pct) >= target:
            return pct
    return _TEXT_STEP_FLOOR


def _step_ratio(palette: Palette, color: str, mode: str, pct: int) -> float:
    """The step's WORST contrast, at this percentage, over the grounds it
    is written on: the page, a panel (``surface``) and the colour's own
    tint (``--bz-bg``, 10 % of the colour over the surface)."""
    from bretzel.theme.palette import _contrast_ratio, _parse_hex

    try:
        src = _parse_hex(palette.resolve(color, mode).bg_hex)
    except ThemeError:
        return 21.0          # couleur inconnue ici : le juge, c'est ailleurs
    text = _parse_hex(palette.resolve("text", mode).bg_hex)
    background = _parse_hex(palette.resolve("background", mode).bg_hex)
    surface = _parse_hex(palette.resolve("surface", mode).bg_hex)

    def mix(a: tuple[int, ...], b: tuple[int, ...], part: float) -> tuple[int, ...]:
        return tuple(round(part * x + (1 - part) * y) for x, y in zip(a, b, strict=True))

    mixed = mix(src, text, pct / 100)
    tint = mix(src, surface, 0.10)
    return min(
        _contrast_ratio(mixed, ground)  # type: ignore[arg-type]
        for ground in (background, surface, tint)
    )


def generate_color_bridges(
    palette: Palette, *, names: Sequence[str] | None = None
) -> str:
    """The bridges' CSS block — one rule per colour.

    ``names`` forces the list (the tests use it); the default is
    :func:`bridged_color_names`.
    """
    colors = tuple(names) if names is not None else bridged_color_names(palette)
    semantics = set(SEMANTIC_COLOR_NAMES) | {CURRENT_COLOR_NAME}
    lines: list[str] = [
        "/* --- The colour bridges — cf. bretzel/theme/bridges.py --- */"
    ]
    for color in colors:
        lines.extend(
            _bridge_rule(color, semantic=color in semantics, palette=palette)
        )
    return "\n".join(lines) + "\n"


def _bridge_rule(
    color: str, *, semantic: bool, palette: Palette
) -> Iterable[str]:
    if color == CURRENT_COLOR_NAME:
        source, foreground = CURRENT_COLOR_SOURCE, CURRENT_COLOR_FOREGROUND
    else:
        var = _color_var(color, semantic=semantic)
        source, foreground = f"var({var})", f"var({var}-foreground)"
    def value(formula: str, mode: str) -> str:
        return formula.format(
            src=SOURCE_VAR,
            fg=SOURCE_FOREGROUND_VAR,
            surface="--color-surface",
            text="--color-text",
            pct_text=readable_step_pct(palette, color, "pct_text", mode),
            pct_muted=readable_step_pct(palette, color, "pct_muted", mode),
        )

    yield f".{bridge_class(color)} {{"
    yield f"  {SOURCE_VAR}: {source};"
    yield f"  {SOURCE_FOREGROUND_VAR}: {foreground};"
    for name, formula, _role in COLOR_STEPS:
        if color == CURRENT_COLOR_NAME and name in CURRENT_COLOR_IDENTITY_STEPS:
            # The inherited colour, as-is. Cf.
            # ``CURRENT_COLOR_IDENTITY_STEPS`` for the reason.
            yield f"  {name}: var({SOURCE_VAR});"
            continue
        yield f"  {name}: {value(formula, 'light')};"
    yield "}"
    # The text steps are measured per mode (``readable_step_pct``): where
    # the dark value differs, ``.dark`` says so — the only place a bridge
    # names a mode, because only these two steps depend on a measurement.
    dark = [
        (name, value(formula, "dark")) for name, formula, _role in COLOR_STEPS
        if value(formula, "dark") != value(formula, "light")
    ]
    if dark:
        yield f".dark .{bridge_class(color)} {{"
        for name, written in dark:
            yield f"  {name}: {written};"
        yield "}"

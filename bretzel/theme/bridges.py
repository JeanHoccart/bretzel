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

Dark mode is almost free
------------------------

The formulas start from ``--color-<name>``, ``--color-surface`` and
``--color-text``, which are **already** redefined in the theme's
``.dark`` block. A bridge written once therefore re-evaluates itself on
the other side: the ramp inverts without a single ``dark:`` class.

What a mode does change is the DOSE: every one is measured against that
mode's own colours (:func:`step_percentages`). Where a dark dose differs,
a ``.dark .bz-c-<name>`` rule restates that step, and nothing else.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from typing import Final

from bretzel.theme.palette import (
    Palette,
    ThemeError,
    _contrast_ratio,
    _distance,
    _parse_hex,
)
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
#: colour itself (:func:`step_percentages`). ``--bz-text`` holds 4.5:1;
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
COLOR_STEPS: tuple[tuple[str, str, str], ...] = (
    # (step name, formula, what it is for)
    (
        "--bz-bg",
        "color-mix(in srgb, var({src}) {pct_bg}%, var({surface}))",
        "background of a tinted component (Radix 3)",
    ),
    (
        "--bz-bg-hover",
        "color-mix(in srgb, var({src}) {pct_bg_hover}%, var({surface}))",
        "son survol (Radix 4)",
    ),
    (
        "--bz-bg-active",
        "color-mix(in srgb, var({src}) {pct_bg_active}%, var({surface}))",
        "its selected / active state (Radix 5)",
    ),
    (
        "--bz-border",
        "color-mix(in srgb, var({src}) {pct_border}%, var({surface}))",
        "bordure au repos (Radix 6-7)",
    ),
    (
        "--bz-border-hover",
        "color-mix(in srgb, var({src}) {pct_border_hover}%, var({surface}))",
        "bordure au survol / au focus (Radix 7)",
    ),
    (
        "--bz-focus",
        "color-mix(in srgb, var({src}) {pct_focus}%, transparent)",
        "anneau de focus (Radix 8)",
    ),
    (
        "--bz-focus-soft",
        "color-mix(in srgb, var({src}) {pct_focus_soft}%, transparent)",
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
        "color-mix(in srgb, var({src}) {pct_solid_hover}%, var({solid_hover_to}))",
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
    names = [*SEMANTIC_COLOR_NAMES, CURRENT_COLOR_NAME]
    names += sorted(set(palette.envelope_dict()) - set(SEMANTIC_COLOR_NAMES))
    return tuple(names)


#: The two TEXT steps and the bar each must clear.
#:
#: ``--bz-text`` is accented body text: WCAG AA, 4.5:1.
#: ``--bz-text-muted`` is an AFFORDANCE and not body text, so its bar is
#: the components' one (WCAG 1.4.11), 3:1.
_TEXT_STEP_TARGETS: Final[dict[str, float]] = {"pct_text": 4.5, "pct_muted": 3.0}

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


#: The DOSED steps: the percentage each starts from — the dose it had
#: when every step was a fixed number — and what it must read against.
#: A step that already reads keeps its dose; one that does not takes the
#: least it needs (Jean: « minimum guaranteed »). Distances are
#: OKLab ΔE × 100 (:func:`~bretzel.theme.palette._distance`), measured
#: against the page, a panel AND a field's grey: a step is global, it
#: does not know which of the three it will be laid on.
_DOSE_BASE: Final[dict[str, int]] = {
    "pct_bg": 10, "pct_bg_hover": 20, "pct_bg_active": 30,
    "pct_border": 35, "pct_border_hover": 50,
    "pct_focus": 40, "pct_focus_soft": 30, "pct_solid_hover": 88,
}
#: A tinted background against every ground. The 10 % wash measured
#: 0.6 to 4.9 against the field grey over the eight identities of the
#: gallery: a pressed B, a soft chip, read as nothing there.
_FROM_GROUND: Final[float] = 4.0
#: A state against the one it follows — hover after rest, press after
#: hover, a solid fill's hover after the fill. The fill's hover measured
#: 0 for some colours: nothing moved under the pointer.
_APART: Final[float] = 3.0
#: A border, a focus ring, against every ground.
_BORDER_FROM_GROUND: Final[float] = 9.0
_RING_FROM_GROUND: Final[float] = 10.0
_SOFT_RING_FROM_GROUND: Final[float] = 8.0
#: How far a dose may climb (a wash) or fall (the fill's hover).
_DOSE_CEILING: Final[int] = 60
_DOSE_FLOOR: Final[int] = 50
#: A state starts at least this many points above the one it follows,
#: so a hover never lands on its rest step's own dose.
_STATE_GAP: Final[int] = 5
#: A neutral step (``neutrals.py``) may climb up to the text itself.
_NEUTRAL_CEILING: Final[int] = 100


#: The same rules, as one table — what a client-side mirror of the
#: measurement (the gallery's studio repaints live) reads, so its numbers
#: cannot drift from these.
STEP_RULES: Final[dict[str, object]] = {
    "base": _DOSE_BASE, "from_ground": _FROM_GROUND, "apart": _APART,
    "border": _BORDER_FROM_GROUND, "ring": _RING_FROM_GROUND,
    "soft_ring": _SOFT_RING_FROM_GROUND, "ceiling": _DOSE_CEILING, "floor": _DOSE_FLOOR,
    "gap": _STATE_GAP, "neutral_ceiling": _NEUTRAL_CEILING,
    "text_base": _TEXT_STEP_BASE, "text_targets": _TEXT_STEP_TARGETS,
    "text_down": _TEXT_STEP_DOWN, "text_floor": _TEXT_STEP_FLOOR,
}

RGB = tuple[int, int, int]


def _rgb(palette: Palette, name: str, mode: str) -> RGB:
    """``name``'s value in ``mode``, as bytes."""
    return _parse_hex(palette.resolve(name, mode).bg_hex)  # type: ignore[arg-type]


def _grounds(palette: Palette, mode: str) -> tuple[RGB, RGB, RGB]:
    """What a step may be laid on: the page, a panel, a field's grey —
    a step is global, it does not know which of the three it gets."""
    return (_rgb(palette, "background", mode), _rgb(palette, "surface", mode),
            _rgb(palette, "interface", mode))


def _mix(a: Sequence[int], b: Sequence[int], pct: int | float) -> RGB:
    """``color-mix(in srgb, a pct%, b)`` — the browser's rounding, to the bit
    (``test_the_calculator_matches_the_browser``): a half goes UP, as
    ``Math.round`` does in the studio's mirror, not to the even neighbour
    as Python's ``round`` would — one unit apart is enough to flip a dose
    measured at its threshold."""
    part = pct / 100
    r, g, b = (math.floor(part * x + (1 - part) * y + 0.5) for x, y in zip(a, b, strict=True))
    return r, g, b


def _least(start: int, reads: Callable[[int], bool], ceiling: int = _DOSE_CEILING) -> int:
    """The first dose from ``start`` up that reads — else the ceiling."""
    return next((p for p in range(start, ceiling + 1) if reads(p)), ceiling)


def _seen_on(colour: RGB, grounds: Sequence[RGB]) -> float:
    """How far a colour laid on each ground stands from it, at worst."""
    return min(_distance(colour, g) for g in grounds)


def _seen_over(src: RGB, pct: int, grounds: Sequence[RGB]) -> float:
    """The same, for a step drawn over whatever is there
    (``transparent``): it composes over each ground first."""
    return min(_distance(_mix(src, g, pct), g) for g in grounds)


@lru_cache(maxsize=512)
def step_percentages(palette: Palette, color: str, mode: str = "light") -> dict[str, int | str]:
    """Every step's percentage for ``color`` in ``mode``, and the colour
    the fill's hover moves towards (``solid_hover_to``).

    The order is the scale's: a state is measured against the step it
    follows, so the rest wash is settled before its hover, the hover
    before the press, the border before its hover — and the text steps
    last, since they are read on the wash.
    """
    base: dict[str, int | str] = {**_DOSE_BASE, **_TEXT_STEP_BASE, "solid_hover_to": "text"}
    if color == CURRENT_COLOR_NAME or color in _SURFACE_SLOTS:
        # Nothing resolvable to measure (``currentColor``), or a plane
        # kept out of the derivation (``_SURFACE_SLOTS``).
        return base
    try:
        src = _rgb(palette, color, mode)
    except ThemeError:
        return base          # unknown here: judged elsewhere
    grounds = _grounds(palette, mode)
    surface, text = grounds[1], _rgb(palette, "text", mode)
    d = dict(_DOSE_BASE)

    def wash(pct: int) -> RGB:
        return _mix(src, surface, pct)

    def after(step: str, prev: str) -> None:
        before = wash(d[prev])
        d[step] = _least(max(d[step], d[prev] + _STATE_GAP),
                         lambda p: _distance(wash(p), before) >= _APART)

    d["pct_bg"] = _least(d["pct_bg"], lambda p: _seen_on(wash(p), grounds) >= _FROM_GROUND)
    after("pct_bg_hover", "pct_bg")
    after("pct_bg_active", "pct_bg_hover")
    d["pct_border"] = _least(d["pct_border"],
                             lambda p: _seen_on(wash(p), grounds) >= _BORDER_FROM_GROUND)
    after("pct_border_hover", "pct_border")
    d["pct_focus"] = _least(d["pct_focus"],
                            lambda p: _seen_over(src, p, grounds) >= _RING_FROM_GROUND)
    d["pct_focus_soft"] = _least(d["pct_focus_soft"],
                                 lambda p: _seen_over(src, p, grounds) >= _SOFT_RING_FROM_GROUND)
    # The fill's hover moves TOWARDS the text: less of the colour. A fill
    # as dark as the text (a black accent on a light page) cannot darken:
    # its hover lightens, towards the surface.
    toward = "text"
    for name, other in (("text", text), ("surface", surface)):
        dose = next((p for p in range(d["pct_solid_hover"], _DOSE_FLOOR - 1, -1)
                     if _distance(_mix(src, other, p), src) >= _APART), None)
        if dose is not None:
            d["pct_solid_hover"], toward = dose, name
            break
    # The text steps keep as much of the colour as stays readable — on the
    # page, a panel, a field's grey and the colour's own wash (a soft
    # badge, an alert): they mix towards the text only as far as their
    # bar requires. Backing off raises the contrast (the text is by
    # construction the colour contrasting most with the ground), so the
    # loop ends. ``--bz-text-muted`` never carries more of the colour
    # than ``--bz-text``: a colour readable as it is gives both itself.
    on = (*grounds, wash(d["pct_bg"]))

    def readable(start: int, bar: float) -> int:
        return next((p for p in range(start, _TEXT_STEP_FLOOR - 1, -_TEXT_STEP_DOWN)
                     if min(_contrast_ratio(_mix(src, text, p), g) for g in on) >= bar),
                    _TEXT_STEP_FLOOR)

    d["pct_text"] = readable(_TEXT_STEP_BASE["pct_text"], _TEXT_STEP_TARGETS["pct_text"])
    d["pct_muted"] = readable(max(_TEXT_STEP_BASE["pct_muted"], d["pct_text"]),
                              _TEXT_STEP_TARGETS["pct_muted"])
    return {**d, "solid_hover_to": toward}


def _formula_values(doses: dict[str, int | str]) -> dict[str, int | str]:
    """The doses as ``COLOR_STEPS`` spells them: the percentages, and the
    variable the fill's hover moves towards."""
    return {**doses, "solid_hover_to": f"--color-{doses['solid_hover_to']}"}


def wash_lines(palette: Palette, mode: str = "light") -> Iterable[str]:
    """The vivid colours' steps reachable BY NAME — ``bg-error-wash``,
    ``border-error-edge`` — for a variant table that writes one colour per
    row and so has no bridge class to read. The bridge's own formula and
    doses (:func:`step_percentages`), not a second measurement."""
    from bretzel.theme.tokens import WASH_COLOR_NAMES, WASH_STEPS

    formulas = {name: formula for name, formula, _role in COLOR_STEPS}
    for color in WASH_COLOR_NAMES:
        values = _formula_values(step_percentages(palette, color, mode))
        for suffix, step in WASH_STEPS.items():
            written = formulas[step].format(src=f"--color-{color}", surface="--color-surface",
                                            **values)
            yield f"--color-{color}-{suffix}: {written};"


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
            **_formula_values(step_percentages(palette, color, mode)),
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
    # Every dosed step is measured per mode (``step_percentages``): where
    # the dark dose differs, ``.dark`` says so — the only place a bridge
    # names a mode.
    dark = [
        (name, value(formula, "dark")) for name, formula, _role in COLOR_STEPS
        if value(formula, "dark") != value(formula, "light")
    ]
    if dark:
        yield f".dark .{bridge_class(color)} {{"
        for name, written in dark:
            yield f"  {name}: {written};"
        yield "}"

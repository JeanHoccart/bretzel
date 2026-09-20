"""The colour bridges — twelve steps derived from one source hue.

A **bridge** is a CSS class which, set on an element, installs there the
twelve variables component themes use to paint themselves ::

    <span class="bz-c-error bg-(--bz-bg) text-(--bz-text)">

The bridge does the translation; the theme now speaks only the steps'
vocabulary. That is what replaces the ``bg-{bg_color}`` templates, whose
flaw is structural: ``bg-{bg_color}`` is not a class but a **half-class**,
invisible to the Tailwind compiler, which therefore had to be closed by
hand — every shape × every colour. Measured on 2026-08-30: 72 shapes × 42
colours = 3 791 safelisted classes, so 576 KB out of 717, **80 % of the
sheet**. Twelve bridges weigh 156 lines.

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
ROLE. The repository had already reinvented it, badly: its 302 templates
reduced to 6 properties and 22 (property, opacity) pairs, fifteen of them
used three times or fewer. The measured lesson is that **opacity is not
an absolute value, it is a step relative to the substrate** — a hover
laid on a ``/15`` background and a hover laid on a solid fill cannot
carry the same opacity. Absolute steps make the problem disappear.

Dark mode is free
-----------------

No ``.dark`` rule here, and that is not an oversight. The formulas start
from ``--color-<name>``, ``--color-surface`` and ``--color-text``, which
are **already** redefined in the theme's ``.dark`` block. A bridge
written once therefore re-evaluates itself on the other side: measured,
the ramp inverts (``--bz-bg`` goes from L* 0.951 to 0.186) without a
single ``dark:`` class.
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
#: ``--bz-text`` and ``--bz-text-muted`` MIX TOWARDS THE TEXT, and that
#: is the project's only deliberate visual change. They were the raw
#: colour (Radix step 9) and its wash towards the surface until
#: 2026-08-30: measured, **seven colours out of eleven fell below WCAG
#: AA** on their own background, and ``warning`` in light mode went down
#: to **1.88**. That was not a regression of the steps — a ``soft`` badge
#: already rendered exactly that pair — but there was no way to write
#: "the TEXT version of this colour": there was only the colour.
#:
#: The two percentages are RESOLVED, not chosen. Over 8 colours × 2 modes
#: × 2 backgrounds:
#:
#:   --bz-text        55 %  as much hue as possible while holding 4.5:1
#:                          (at 60 % the worst falls to 4.26). Worst
#:                          measured: 4.82, against 1.88 before.
#:   --bz-text-muted  70 %  visibly lighter than the previous one, and it
#:                          holds 3.41 — the AFFORDANCE bar (WCAG 1.4.11:
#:                          3:1 for a UI component). Its five sites are
#:                          icons and close buttons, which go solid on
#:                          hover.
#:
#: ⚠️ **There is no room for two text steps both at 4.5:1** with this
#: palette: no percentage between 70 and 100 clears AA for the second,
#: because the source hues are too light (the yellow above all). Radix
#: gets away with twelve steps tuned by hand per hue; here we name the
#: constraint instead of masking it.
#:
#: ``in srgb`` — and the framing said ``in oklab``. A measurement settled
#: that, not a taste.
#:
#: Mixing towards ``--color-surface`` in sRGB **is** the operation an
#: opacity already performs: ``bg-error/50`` composites in sRGB. The two
#: spellings are therefore algebraically the same thing, and the
#: migration moves no colour. In oklab, no: measured on 2026-08-30 over
#: the 8 colours × 2 modes, **no percentage reproduces an opacity** — the
#: best fit for ``/50`` is 54 %, and it still leaves ΔE 3.9 on average
#: and 11.5 at worst. The gap depends on the HUE, so it cannot be fixed
#: with one number.
#:
#: It was visible: at 50 % in oklab the ``outline`` badge's border
#: rendered paler than its text in both modes — exactly the flaw phase 0
#: had corrected by eye twelve hours earlier.
#:
#: The reason written at framing time — "an sRGB mix crosses grey and
#: goes muddy in the middle of the scale" — is true of two CHROMATIC
#: colours being mixed. These formulas mix towards the surface, that is
#: to say towards white or near-black: there is no grey to cross.
#:
#: ⚠️ A perceptually uniform scale remains a better DESIGN goal, and it
#: is what will make the steps regular. But that is a visual change, so
#: it gets decided and shown — like phase 0's three opacities — not
#: slipped in during a migration whose contract is equality.
#:
#: The dependency on ``color-mix`` is already taken in production —
#: ``feedback/notification/theme.py`` has written it literally for
#: months.
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
#: ⚠️ Without this exception, ``current`` goes through the eleven
#: formulas like an ordinary colour, and ``--bz-text`` becomes
#: ``color-mix(in srgb, currentColor 55%, var(--color-text))``. In other
#: words: **a default icon does NOT take its parent's colour, it takes
#: 55 % of it pulled towards the page text.** On a neutral background the
#: inherited colour IS the page text, so the mix is the identity and
#: nobody sees anything. On a solid fill — a ``solid`` button, a badge,
#: an alert — the two diverge, and the icon comes out a different colour
#: from the word it accompanies.
#:
#: Measured on 2026-09-09 on a primary button in ``examples/kanban``:
#: label ``rgb(19 22 22)``, icon ``rgb(17 22 31)``. It is also what
#: ``icon/theme.py``'s docstring had always promised — "the icon inherits
#: its parent's text colour" — without the CSS holding it.
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

    The rule is not "twelve", it is **coverage**. A missing bridge is not
    a saving, it is a component that renders without a colour: its steps
    are undefined, so its properties invalid. Measured on 2026-08-30
    while migrating the Badge — ``ui.badge(color="tomato")`` lost all its
    style, and 21 components made ``test_palette_color_is_prefixed``
    turn red.

    The count of **twelve** in the 2026-08-30 decision stays true, and it
    arrives by itself: it follows from the PALETTE's size, not from a
    list maintained here. The day the 31 default colours are removed
    (phase 5 of the project), this function will return twelve names
    without a line being touched — and an app declaring ``brand`` will
    have its bridge, exactly as today.

    Coverage's cost is small against what it replaces: 43 bridges weigh
    ~33 KB against the 576 KB of the shape × colour closure.

    Why it is memoised
    ------------------

    The body sweeps the whole palette — ``envelope_dict()`` recomputes a
    ``bg_class`` and an ``fg_class`` for each of its ~42 colours. That is
    cheap once, and this function is called by
    :func:`bretzel.components.base._wiring._refuse_unknown_color`, so
    **once per coloured component**. Measured on 2026-09-05 on a hard
    load of the playground: 135 660 calls to ``bg_class`` for five
    renders of ``/tabs``, and 19 % of the request's time spent answering
    the same question 1 615 times.

    The bet is safe, unlike ``escape_attr``'s: a
    :class:`~bretzel.theme.palette.Palette` is built once at startup, its
    tables are written only in its ``__init__``, and ``Theme.get_palette``
    always returns the same instance. The reuse rate is therefore not
    "high", it is **total** — and
    ``test_the_color_bridge_memo_still_pays`` checks it, because the day
    a palette were rebuilt per request, nothing would break: the page
    would stay correct, it would merely have gone slow again.

    In-process A/B alternation, min of 14: ``/tabs``
    86.4 → 68.2 ms (−21 %), ``/datatable`` 330.1 → 198.3 ms (−40 %).
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
#: These are the values that were hard-coded in the formulas until
#: 2026-09-02.
_TEXT_STEP_BASE: Final[dict[str, int]] = {"pct_text": 55, "pct_muted": 70}

#: How far we back off at each step, and how far we go. Backing off
#: means LESS hue and more text — so more contrast, in both modes
#: (measured: dark has 14 to 17 of margin, there is nothing to break
#: there).
_TEXT_STEP_DOWN: Final[int] = 5
_TEXT_STEP_FLOOR: Final[int] = 25

#: The SURFACE slots, kept out of the derivation.
#:
#: ⚠️ **They fail the same bar, and that is a 2026-09-02 discovery — not
#: a convenience exemption.** Measured, they would back off too:
#: ``surface`` and ``white`` from 55 to 35 %, ``background`` and
#: ``interface`` to 40 %, ``black`` to 50 %.
#:
#: They are kept out because **the gate does not judge them** —
#: ``test_the_colour_steps_stay_readable`` holds 37 colours, and none of
#: these five is among them. Moving them would change the appearance of
#: components against a bar nobody has ever held them to, and with no
#: measurement saying whether that is progress: a ``color="white"``
#: serves a white badge on a dark banner, not text on the page, so the
#: background to measure against is not the one this derivation assumes.
#:
#: It is therefore an open question, not an oversight — recorded in
#: ``.claude/work/todo.md``. Widening it first requires deciding WHAT a
#: surface slot is measured AGAINST.
_SURFACE_SLOTS: Final[frozenset[str]] = frozenset({
    "background", "surface", "interface", "white", "black",
})


def readable_step_pct(palette: Palette, color: str, step: str) -> int:
    """The hue percentage of step ``step``, backed off if necessary.

    Why this exists (2026-09-02)
    ----------------------------
    A single formula serves all 43 colours: step 12 is "55 % of the hue
    + 45 % of the text". On a very light hue that does not clear 4.5:1 —
    measured, ``yellow`` in light mode rendered **3.76**, and its
    ``--bz-text-muted`` **2.58** against a bar of 3.

    The announced decision was "one formula OR one table per hue". This
    is a third way, and it is the same as ``palette._readable_fg``'s: the
    formula is kept, and BACKED OFF towards the text until the bar is
    cleared, stopping at the first step that suffices. So it is not a
    hand-tuned table — it is a derivation, which will serve a colour
    added tomorrow with nothing touched.

    Backing off increases contrast in BOTH modes, which is what lets a
    single CSS rule serve both: the text is by construction the colour
    contrasting most with the background, so adding more of it cannot
    bring them closer. Verified in dark mode, where the margin is 14 to
    17.

    ⚠️ The measurement is made against the CURRENT theme. A theme that
    changes its ``text`` or its ``background`` changes the result — that
    is intended, and it is better than the previous frozen percentage,
    which did not adapt at all.
    """
    base = _TEXT_STEP_BASE[step]
    _name, target = _TEXT_STEP_TARGETS[step]
    if color == CURRENT_COLOR_NAME or color in _SURFACE_SLOTS:
        # ``currentColor`` has no resolvable value: nothing to measure,
        # so nothing to back off. The SURFACE slots are kept out for
        # another reason — cf. ``_SURFACE_SLOTS``.
        return base
    for pct in range(base, _TEXT_STEP_FLOOR - 1, -_TEXT_STEP_DOWN):
        if all(
            _step_ratio(palette, color, mode, pct) >= target
            for mode in ("light", "dark")
        ):
            return pct
    return _TEXT_STEP_FLOOR


def _step_ratio(palette: Palette, color: str, mode: str, pct: int) -> float:
    """The step's contrast against the page BACKGROUND, at this percentage."""
    from bretzel.theme.palette import _contrast_ratio, _parse_hex

    try:
        src = _parse_hex(palette.resolve(color, mode).bg_hex)
    except ThemeError:
        return 21.0          # couleur inconnue ici : le juge, c'est ailleurs
    text = _parse_hex(palette.resolve("text", mode).bg_hex)
    background = _parse_hex(palette.resolve("background", mode).bg_hex)
    part = pct / 100
    mixed = tuple(
        round(part * a + (1 - part) * b)
        for a, b in zip(src, text, strict=True)
    )
    return _contrast_ratio(mixed, background)  # type: ignore[arg-type]


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
    yield f".{bridge_class(color)} {{"
    yield f"  {SOURCE_VAR}: {source};"
    yield f"  {SOURCE_FOREGROUND_VAR}: {foreground};"
    for name, formula, _role in COLOR_STEPS:
        if color == CURRENT_COLOR_NAME and name in CURRENT_COLOR_IDENTITY_STEPS:
            # The inherited colour, as-is. Cf.
            # ``CURRENT_COLOR_IDENTITY_STEPS`` for the measurement.
            yield f"  {name}: var({SOURCE_VAR});"
            continue
        value = formula.format(
            src=SOURCE_VAR,
            fg=SOURCE_FOREGROUND_VAR,
            surface="--color-surface",
            text="--color-text",
            pct_text=readable_step_pct(palette, color, "pct_text"),
            pct_muted=readable_step_pct(palette, color, "pct_muted"),
        )
        yield f"  {name}: {value};"
    yield "}"

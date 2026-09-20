"""Resolved palette — semantic + extras, with auto-foreground derivation.

The palette is the single source of truth for *what hex value* every
named color carries. Components consult it via :func:`Palette.resolve`
at render time to interpolate ``{bg_color}``/``{fg_color}`` tokens in
their slot templates.

Two responsibilities live here :

1. **Color algebra** : parse hex strings, derive a foreground that has
   enough contrast with the background, expose :class:`ResolvedColor`
   to downstream consumers.
2. **Palette assembly** : aggregate semantic + palette dictionaries
   for both light and dark modes, with sensible inheritance (dark
   omitting an entry → falls through to light).

Pure module — no I/O, no global state. The default palette and the
default semantic dictionaries that ship with Bretzel live here as
plain ``dict`` constants ; a user theme can take them as the basis
and overlay just the entries they want to change.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Final, Literal

from bretzel.theme.tokens import (
    FOREGROUND_SUFFIX,
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
)


class ThemeError(ValueError):
    """Raised on invalid theme input (missing slot, unknown color, …)."""


# ───────────────────────────────────────────────────────────────────────────
# Hex / RGB / HSL primitives
# ───────────────────────────────────────────────────────────────────────────


def _parse_hex(hex_str: str) -> tuple[int, int, int]:
    """Parse a ``#rrggbb`` (or ``#rgb``) string into ``(r, g, b)`` 0-255.

    Raises :class:`ThemeError` on malformed input — we'd rather fail
    at theme construction than emit a broken stylesheet.
    """
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        raise ThemeError(
            f"Invalid hex color {hex_str!r} : expected ``#rrggbb`` or ``#rgb``."
        )
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


#: The WCAG relative-luminance coefficients. Named — rather than left
#: as literals — because they are MIRRORED in JavaScript by the theme
#: studio, which cannot import Python. Same arrangement as
#: ``protocol.py`` ↔ ``runtime.js``, and the same gate guards it:
#: ``test_the_foreground_algebra_is_mirrored_in_js``.
_LUM_COEFFICIENTS: Final[tuple[float, float, float]] = (0.2126, 0.7152, 0.0722)
_LUM_LINEAR_CUTOFF: Final[float] = 0.03928
_LUM_LINEAR_DIVISOR: Final[float] = 12.92
_LUM_GAMMA_OFFSET: Final[float] = 0.055
_LUM_GAMMA_DIVISOR: Final[float] = 1.055
_LUM_GAMMA_EXPONENT: Final[float] = 2.4

#: The W3C threshold "from here on, write dark on this background".
_FG_DARK_CUTOFF: Final[float] = 0.179
#: The lightness of dark text, and that of light text.
_FG_DARK_LIGHTNESS: Final[float] = 0.08
_FG_LIGHT_LIGHTNESS: Final[float] = 0.96
#: The hue the text borrows from the background, and its ceiling. That is
#: what makes the pair feel "of a piece" instead of black-or-white.
_FG_TINT_FACTOR: Final[float] = 0.12
_FG_TINT_CAP: Final[float] = 0.08

#: The contrast ``--bz-on-solid`` must reach — WCAG AA normal text. A
#: value, not an "about right": it is the threshold the
#: ``test_the_colour_steps_stay_readable`` gate applies.
_FG_AA_TARGET: Final[float] = 4.5
#: The number of back-off steps. Five are enough: the worst measured
#: case (``plum``) clears AA at the second.
_FG_ESCALATION_STEPS: Final[int] = 5


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG relative luminance — 0 for black, 1 for white.

    Used by :func:`resolve_color_pair` to decide whether the
    auto-foreground should be light or dark. Also exposed (via the
    test suite) so we can assert the contrast ratio in tests.
    """
    def channel(v: int) -> float:
        c = v / 255.0
        if c <= _LUM_LINEAR_CUTOFF:
            return c / _LUM_LINEAR_DIVISOR
        return (
            (c + _LUM_GAMMA_OFFSET) / _LUM_GAMMA_DIVISOR
        ) ** _LUM_GAMMA_EXPONENT

    kr, kg, kb = _LUM_COEFFICIENTS
    return kr * channel(r) + kg * channel(g) + kb * channel(b)


def _contrast_ratio(rgb_a: tuple[int, int, int], rgb_b: tuple[int, int, int]) -> float:
    """WCAG contrast ratio — 1 for identical, 21 for white on black."""
    la = _relative_luminance(*rgb_a)
    lb = _relative_luminance(*rgb_b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


# ───────────────────────────────────────────────────────────────────────────
# Foreground derivation
# ───────────────────────────────────────────────────────────────────────────


def resolve_color_pair(hex_color: str) -> tuple[str, str]:
    """Return ``(bg_hex, fg_hex)`` for a single hex.

    Strategy: compare the background's luminance to a perceptual
    midpoint and pick a near-black or near-white foreground, then
    tint it lightly with the background's hue so the pair still
    feels of-a-piece visually — and back that tint off if it would
    cost readability (:func:`_readable_fg`).

    ⚠️ This line said "clears AA Large (>= 3.0) … and AA (>= 4.5) for
    MOST" until 2026-09-01, and the "most" was a quantifiable concession
    nobody had quantified: three colours of the shipped palette fell
    outside it. Since the back-off, AA holds for all of them — it is a
    guarantee, no longer a tendency, and
    ``test_the_colour_steps_stay_readable`` checks it.

    A pure invert-lightness approach (the v1 attempt) crashes on
    mid-luminance colors like ``#3e63dd`` whose inverted lightness
    is too close to the original — same hue + similar luminance =
    insufficient contrast.
    """
    r, g, b = _parse_hex(hex_color)
    h, _l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    bg_lum = _relative_luminance(r, g, b)

    # 0.179 is the W3C-suggested cutoff for "use dark text on this bg".
    # Above the cutoff: near-black foreground, lightly tinted with the bg's
    # hue + saturation so the pair stays visually unified. Below: near-white,
    # which tolerates a touch more saturation without losing legibility.
    base_l = (
        _FG_DARK_LIGHTNESS if bg_lum > _FG_DARK_CUTOFF
        else _FG_LIGHT_LIGHTNESS
    )
    base_s = min(s * _FG_TINT_FACTOR, _FG_TINT_CAP)
    return _to_hex(r, g, b), _readable_fg((r, g, b), h, base_l, base_s)


def _readable_fg(
    bg: tuple[int, int, int], hue: float, base_l: float, base_s: float
) -> str:
    """The tinted foreground, BACKED OFF until it is readable.

    Why this exists (2026-09-01)
    ----------------------------
    Three colours of the shipped palette missed AA on their own
    ``--bz-on-solid``, and the gate's ``_KNOWN_BELOW`` table carried them
    as debt: ``muted`` 4.36 · ``pink`` 4.48 · ``plum`` 4.33.

    The culprit was **not** the foreground's direction. Measured, the
    0.179 threshold already picks the better of the two candidates for
    all 31 colours — on ``plum``, pure black would give 4.42 where pure
    white gives 4.75. The culprit is the **tint**: the 0.08 of lightness
    held in reserve and the saturation borrowed from the background cost
    between 0.40 and 0.61 of ratio, and that is what takes those three
    under the bar.

    Hence the shape: the tint is kept, but BACKED OFF — towards the
    lightness extreme and towards zero saturation — until AA is cleared,
    stopping at the first step that suffices. Visual unity is an
    intention; readability is a contract.

    What it changes, and this is the point: **nothing for the others**. A
    colour that clears AA at step 0 comes out at step 0, byte for byte —
    73 of the default theme's 78 (name, mode) pairs. Only the three in
    debt move: ``pink`` at step 1, ``muted`` and ``plum`` at step 2.
    """
    extreme = 0.0 if base_l < 0.5 else 1.0
    fg = (0, 0, 0)
    for step in range(_FG_ESCALATION_STEPS + 1):
        t = step / _FG_ESCALATION_STEPS
        light = base_l + (extreme - base_l) * t
        sat = base_s * (1 - t)
        cr, cg, cb = colorsys.hls_to_rgb(hue, light, sat)
        fg = (round(cr * 255), round(cg * 255), round(cb * 255))
        if _contrast_ratio(bg, fg) >= _FG_AA_TARGET:
            break
    return _to_hex(*fg)


# ───────────────────────────────────────────────────────────────────────────
# Default palette + semantic dicts
# ───────────────────────────────────────────────────────────────────────────


# Lifted verbatim from spec § *DEFAULT_PALETTE*. Keeping the colors
# inline (vs. an external file) means the framework is reproducible
# without I/O at startup.
DEFAULT_PALETTE: Final[dict[str, str]] = {
    "gray":    "#8d8d93",
    "mauve":   "#8e8c99",
    "slate":   "#8b8d98",
    "sage":    "#868e8b",
    "olive":   "#868e80",
    "sand":    "#8d8d86",
    "tomato":  "#e54d2e",
    "red":     "#e5484d",
    "ruby":    "#e54666",
    "crimson": "#e93d82",
    "pink":    "#d6409f",
    "plum":    "#682747",
    "purple":  "#8e4ec6",
    "violet":  "#6e56cf",
    "iris":    "#5b5bd6",
    "indigo":  "#3e63dd",
    "blue":    "#0090ff",
    "cyan":    "#00a2c7",
    "sky":     "#30a5e2",
    "teal":    "#12a594",
    "jade":    "#29a383",
    "green":   "#30a46c",
    "grass":   "#46a758",
    "yellow":  "#f5d90a",
    "amber":   "#ffc53d",
    "orange":  "#f76b15",
    "gold":    "#e99536",
    "bronze":  "#a18072",
    "brown":   "#ad7f58",
    "black":   "#000000",
    "white":   "#ffffff",
}  # fmt: skip


# The six BRAND hues are spread across the colour wheel (blue / violet /
# green / amber / red / cyan) so every semantic pair stays perceptually
# distinct — worst-pair ΔE(CIE76) ≈ 36 vs the old palette's 17.7, where
# ``secondary``≈``warning`` (both amber) and ``primary``≈``success`` (both
# green) collapsed into confusable tints. Enforced by
# ``tests/consistency/test_palette_distinctness.py`` (min ΔE gate) — retune a
# hue here and the gate fails if it re-introduces a collision.
# ⚠️ **The neutrals are STRICTLY ACHROMATIC, and that is a decision of
# 2026-09-13.** They used to be Tailwind's ``slate`` — so bluish, and
# recognisable at a glance as "a project that did not choose its colours".
# A grey carrying a hue takes that hue's side: it warms or cools
# everything laid on it, and it quarrels with the app's accent as soon as
# that accent goes the other way. At zero hue, the background says
# nothing and **the brand is the only colour on screen** — which is
# exactly what one expects of a framework's default, since it does not
# know the brand of the app that will use it.
#
# ⚠️ **``interface`` is no longer equal to ``background``.** Both were at
# ``#f8fafc`` in light mode: a field, a select panel, a control's recess
# therefore rendered EXACTLY the page colour, and the whole depth
# hierarchy rested on the border alone. That was not a choice — it was
# the same token copied twice.
DEFAULT_SEMANTIC_LIGHT: Final[dict[str, str]] = {
    # The accent: a DEEP indigo rather than the previous royal blue
    # (``#2f5fd0``). It stops shouting on a light page, it stays plainly
    # distinct from ``info``'s cyan, and it carries enough violet not to
    # be mistaken for a browser link.
    #
    # The second is a muted PLUM, and its distance is measured: ΔE 47
    # from the accent, 47 from the error red, 96 from the green. An
    # amethyst (#8455ab) was tried the same day and refused by
    # ``test_palette_distinctness`` — ΔE 21 from the accent, so two
    # semantic colours that look alike and an ambiguous variant matrix.
    "primary":    "#682747",
    "secondary":  "#3a52b0",
    "success":    "#2f9e64",
    "error":      "#e5484d",
    "warning":    "#f0a91b",
    "info":       "#0e9bc4",
    "background": "#fafafa",
    "surface":    "#ffffff",
    "interface":  "#f0f0f1",
    "text":       "#171717",
    "muted":      "#6b6b6e",
}  # fmt: skip


# Only the slots that actually swap in dark mode — everything else
# falls through to light (the brand colors stay constant).
# The dark is neutral too, and **it is no longer a near-black navy**.
# ``#020617`` was almost pure black AND very blue: under a saturated
# fill it tires the eye within seconds, and the gap up to ``surface`` was
# a jump. The three planes now climb in regular steps, which is what
# makes depth readable.
#
# Only the slots that really SWAP are here — the brand and status colours
# keep their light value in both modes.
DEFAULT_SEMANTIC_DARK: Final[dict[str, str]] = {
    "background": "#0a0a0a",
    "surface":    "#151515",
    "interface":  "#212121",
    "text":       "#f5f5f5",
    "muted":      "#a0a0a3",
}  # fmt: skip


# ───────────────────────────────────────────────────────────────────────────
# ResolvedColor + Palette
# ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResolvedColor:
    """A color name + hex pair + the CSS class names that point to it."""

    name: str
    bg_hex: str
    fg_hex: str
    bg_class: str
    fg_class: str


# A palette entry can be either ``"#hex"`` (auto fg) or ``("#bg", "#fg")``
# (explicit fg). We normalise both shapes when building the palette.
_PaletteValue = str | tuple[str, str]


Mode = Literal["light", "dark"]


class Palette:
    """Resolved palette — semantic + extras for both light and dark modes.

    Built once at app startup ; every render call shares the same
    instance. The class is small on purpose : it owns the *resolution
    table*, not the user-facing :class:`Theme` ergonomics.
    """

    __slots__ = (
        "_palette_dark",
        "_palette_light",
        "_palette_prefix",
        "_semantic_dark",
        "_semantic_light",
    )

    def __init__(
        self,
        semantic_light: dict[str, _PaletteValue],
        semantic_dark: dict[str, _PaletteValue] | None = None,
        palette_light: dict[str, _PaletteValue] | None = None,
        palette_dark: dict[str, _PaletteValue] | None = None,
        *,
        palette_prefix: str = PALETTE_CLASS_PREFIX,
    ) -> None:
        # Validate semantic completeness — every slot must be present.
        missing = set(SEMANTIC_COLOR_NAMES) - set(semantic_light.keys())
        if missing:
            raise ThemeError(
                f"Missing semantic colors : {sorted(missing)}. "
                "Every slot in SEMANTIC_COLOR_NAMES must be defined."
            )

        # Reject unknown semantic keys. THIS is where the silence lived:
        # ``semantic_light`` was recomposed by comprehension OVER
        # ``SEMANTIC_COLOR_NAMES`` (so a surplus key was never iterated)
        # and ``semantic_dark`` carried an ``if name in
        # SEMANTIC_COLOR_NAMES`` that filtered it out. In both cases
        # ``Theme(semantic={"primry": "#f00"})`` was accepted, the key
        # vanished, and nothing — no error, no CSS, no hint —
        # distinguished that from an applied colour.
        #
        # The semantic slots are **closed**: they are the 11 names every
        # component knows, that is to say framework grammar. A key
        # outside the list can mean nothing but a mistake — unlike
        # ``palette=``, which is an OPEN list and stays one (the charter:
        # "the user can add, remove or override entries").
        for label, mapping in (("semantic", semantic_light), ("semantic_dark", semantic_dark)):
            unknown = sorted(set(mapping or {}) - set(SEMANTIC_COLOR_NAMES))
            if unknown:
                raise ThemeError(
                    f"Theme({label}=…): unknown slot(s) {unknown}. "
                    f"The 11 semantic slots are "
                    f"{list(SEMANTIC_COLOR_NAMES)} — a key outside that "
                    f"list is read by no component. To add a NAMED colour "
                )

        # Reject collisions between palette names and semantic ones —
        # an "primary" entry under ``palette=`` is almost always a
        # confusion between the two.
        palette_light_clean = palette_light or {}
        overlap = set(palette_light_clean.keys()) & set(SEMANTIC_COLOR_NAMES)
        if overlap:
            raise ThemeError(
                f"Palette names {sorted(overlap)} collide with semantic "
                "slots. You probably meant ``semantic=`` ."
            )

        self._semantic_light = {
            name: _coerce_pair(name, semantic_light[name])
            for name in SEMANTIC_COLOR_NAMES
        }
        # No more ``if name in SEMANTIC_COLOR_NAMES`` filter: the guard
        # above has already raised, so it could no longer remove
        # anything. Leaving it would suggest a key outside the list can
        # reach here.
        self._semantic_dark = {
            name: _coerce_pair(name, value)
            for name, value in (semantic_dark or {}).items()
        }
        self._palette_light = {
            name: _coerce_pair(name, value)
            for name, value in palette_light_clean.items()
        }
        self._palette_dark = {
            name: _coerce_pair(name, value)
            for name, value in (palette_dark or {}).items()
        }
        self._palette_prefix = palette_prefix

    # ── Lookups ─────────────────────────────────────────────────────────

    def resolve(self, color: str, mode: Mode = "light") -> ResolvedColor:
        """Look up a color by name. Honours dark-mode overrides.

        Raises :class:`ThemeError` if the color is unknown — a typo
        or rename would otherwise silently produce ``bg-tomatto`` and
        an empty Tailwind compile.
        """
        bg_hex, fg_hex = self._lookup(color, mode)
        return ResolvedColor(
            name=color,
            bg_hex=bg_hex,
            fg_hex=fg_hex,
            bg_class=self.bg_class(color),
            fg_class=self.fg_class(color),
        )

    def bg_class(self, color: str) -> str:
        """The CSS class name for backgrounds.

        - Semantic colors : no prefix (``bg-primary``).
        - Palette colors : the configured prefix (``bg-ui-tomato``).
        """
        if color in SEMANTIC_COLOR_NAMES:
            return color
        if color in self._palette_light or color in self._palette_dark:
            return f"{self._palette_prefix}{color}"
        raise ThemeError(self.unknown_color_message(color))

    def unknown_color_message(self, color: str) -> str:
        """The message for a refused colour — written ONCE.

        It states the consequence, not only the fault, because the
        consequence is invisible: the final class is ASSEMBLED at render
        time, so it exists in no source, so the production Tailwind
        compiler does not generate it. It works in dev (the browser
        compiler reads the live DOM) and comes out unstyled in
        production, with identical HTML on both sides. A message that
        merely said "unknown colour" would let the author believe it was
        a cosmetic detail.
        """
        from bretzel.theme.slots import COLOR_KEYWORDS

        known = sorted(
            {*SEMANTIC_COLOR_NAMES, *self._palette_light, *self._palette_dark}
        )
        return (
            f"Unknown colour: {color!r}.\n\n"
            f"This palette accepts: {', '.join(known)}.\n"
            f"Plus the CSS keywords: {', '.join(sorted(COLOR_KEYWORDS))}.\n\n"
            f"Why this RAISES instead of passing: the theme writes "
            f"``bg-{{bg_color}}/15``, which becomes ``bg-{color}/15`` at "
            f"render time — a class that appears literally in NO source. "
            f"The PRODUCTION Tailwind compiler only generates what it finds "
            f"written, and the safelist only expands the colours above. The "
            f"element would therefore have come out UNSTYLED in production, "
            f"while being correct in dev (the browser compiler reads the "
            f"live DOM). Identical HTML on both sides, no error: invisible "
            f"before deployment.\n\n"
            f"For a brand colour, declare it — it then enters the safelist: "
            f"Theme(palette={{{color!r}: '#hex'}})."
        )

    def fg_class(self, color: str) -> str:
        """The CSS class name for foregrounds (auto ``-foreground`` suffix)."""
        return f"{self.bg_class(color)}{FOREGROUND_SUFFIX}"

    def all_colors(self, mode: Mode = "light") -> dict[str, ResolvedColor]:
        """Every color the palette knows about, resolved for ``mode``."""
        out: dict[str, ResolvedColor] = {}
        for name in SEMANTIC_COLOR_NAMES:
            out[name] = self.resolve(name, mode)
        for name in self._palette_light:
            out[name] = self.resolve(name, mode)
        return out

    def envelope_dict(self) -> dict[str, dict[str, str]]:
        """Compact JSON-friendly summary for the runtime envelope.

        Output format, meant for the runtime ::

            { "primary": {"bg": "primary", "fg": "primary-foreground"}, … }

        Only class names are sent — hex values live in the compiled
        CSS variables and don't need to round-trip through JS.
        """
        out: dict[str, dict[str, str]] = {}
        for name in SEMANTIC_COLOR_NAMES:
            out[name] = {"bg": self.bg_class(name), "fg": self.fg_class(name)}
        for name in self._palette_light:
            out[name] = {"bg": self.bg_class(name), "fg": self.fg_class(name)}
        return out

    # ── Internal lookup walking light/dark/palette/semantic ─────────────

    def _lookup(self, color: str, mode: Mode) -> tuple[str, str]:
        if mode == "dark":
            if color in self._semantic_dark:
                return self._semantic_dark[color]
            if color in self._palette_dark:
                return self._palette_dark[color]
        if color in self._semantic_light:
            return self._semantic_light[color]
        if color in self._palette_light:
            return self._palette_light[color]
        raise ThemeError(self.unknown_color_message(color))


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _coerce_pair(name: str, value: _PaletteValue) -> tuple[str, str]:
    """Normalise a palette entry to ``(bg_hex, fg_hex)``.

    Accepts :

    - ``"#hex"`` → derives fg via :func:`resolve_color_pair`.
    - ``("#bg", "#fg")`` tuple → both hex values explicit.

    Validates the hex format eagerly so a typo trips at theme
    construction, not at first render.
    """
    if isinstance(value, str):
        return resolve_color_pair(value)
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(v, str) for v in value)
    ):
        bg, fg = value
        # Normalise via _parse_hex+_to_hex so casing and shorthand
        # (#abc) are smoothed to a canonical form.
        r, g, b = _parse_hex(bg)
        fr, fg_, fb = _parse_hex(fg)
        return _to_hex(r, g, b), _to_hex(fr, fg_, fb)
    raise ThemeError(
        f"Invalid palette entry for {name!r} : expected ``'#hex'`` "
        f"or ``('#bg','#fg')`` tuple, got {value!r}."
    )

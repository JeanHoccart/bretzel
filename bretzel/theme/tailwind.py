"""Generate the Tailwind v4 ``@theme`` block.

Tailwind v4's design lets you declare CSS custom properties under
``@theme {}`` and have them flow into every utility automatically —
``--color-primary`` becomes ``bg-primary``, ``text-primary``, ``ring-primary``,
etc., free of charge.

We emit two things:

- The **theme block** itself: every semantic + palette color, plus a
  ``-foreground`` companion. RGB triples are space-separated (Tailwind
  v4 convention) so ``bg-primary/50`` works without further setup.
- A **dark-mode override block** (``.dark { ... }``) carrying only the
  slots whose hex actually swaps.

The output is a string fed directly to Lightning CSS at compile time —
no AST, no template engine, no quoted CSS-in-Python tricks.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from bretzel.theme.palette import Palette
from bretzel.theme.tokens import (
    BREAKPOINTS,
    DEFAULT_SHAPE,
    DEFAULT_SPACING,
    DEFAULT_STROKE,
    DEFAULT_TEXT,
    FONT_SLOT_NAMES,
    FOREGROUND_SUFFIX,
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
    SHAPE_SLOT_NAMES,
    TEXT_SLOT_NAMES,
)


def _hex_to_rgb_value(hex_str: str) -> str:
    """Convert ``#rrggbb`` to ``"rgb(R G G)"`` — Tailwind v4 form.

    v4 expects ``--color-X`` to hold an actual CSS colour value
    (``rgb()`` / ``oklch()`` / hex). Earlier drafts used the v3
    space-separated triplet, but that produces invalid CSS in v4 :
    ``text-primary`` resolves to ``color: var(--color-primary)`` and
    a bare ``39 117 74`` is not a colour. The ``rgb()`` wrapper makes
    alpha modifiers (``bg-primary/50``) keep working — v4's
    ``color-mix`` engine handles the alpha step on its side.
    """
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return f"rgb({r} {g} {b})"


# ───────────────────────────────────────────────────────────────────────────
# Block builders
# ───────────────────────────────────────────────────────────────────────────


def generate_theme_css(
    palette: Palette,
    *,
    fonts: Mapping[str, str] | None = None,
    spacing: str | None = None,
    text: Mapping[str, str] | None = None,
    shape: Mapping[str, str] | None = None,
    stroke: str | None = None,
) -> str:
    """Build the ``@import`` + ``@theme`` + ``.dark`` blocks.

    ``fonts``: the families declared by ``Theme(fonts=…)``, keyed in
    :data:`~bretzel.theme.tokens.FONT_SLOT_NAMES`. Emitted INSIDE the
    ``@theme`` block as ``--font-<slot>``, so read by Tailwind on the
    same footing as its own tokens: the ``font-sans`` / ``font-serif`` /
    ``font-mono`` utilities inherit from them, and a redefined
    ``--font-sans`` changes the whole document's font (the v4 preflight
    sets ``html { font-family: var(--default-font-family, …) }`` and
    ``--default-font-family: var(--font-sans)``). An absent or empty
    section emits **nothing** — Tailwind's stacks stay in place, and no
    default is copied on our side.

    Output structure ::

        @import "tailwindcss";

        @custom-variant dark (&:where(.dark, .dark *));
        @custom-variant hover (&:hover);

        @theme {
          --font-sans: Inter, ui-sans-serif, system-ui, sans-serif;
          --color-primary: 39 117 74;
          --color-primary-foreground: 250 250 250;
          ...
          --color-ui-tomato: 229 77 46;
          --color-ui-tomato-foreground: 18 9 7;
          ...
        }

        .dark {
          --color-background: 2 6 23;
          --color-background-foreground: 247 248 250;
          ...
        }

    Note on ``@custom-variant dark``: Tailwind v4 ships with
    ``@media (prefers-color-scheme: dark)`` as the default ``dark:``
    variant. Bretzel uses class-based dark mode (``.dark`` on
    ``<html>``, written by the FOUC script + the ``ColorScheme``
    ClientState) so we MUST redefine the variant to match the class.
    Without this line every ``dark:hidden`` / ``dark:inline-flex`` /
    etc. silently fails to react to the user's toggle — they're
    bound to the OS preference instead.

    Note on ``@custom-variant hover``: Tailwind v4 wraps EVERY
    ``hover:`` utility in ``@media (hover: hover)``. Where the primary
    pointer doesn't hover, that query is false and **the rule doesn't
    exist** — class in the DOM, selector in the stylesheet, nothing
    applied. Redefining the variant restores the v3 semantics (the
    escape hatch Tailwind documents for this case). The trade-off is
    sticky hover on touch, taken deliberately: our hovers *enrich*, so
    a lingering tint is cosmetic where an invisible affordance is
    functional breakage. Measurements and date in ``traps.md``;
    ``hover:`` must still never CARRY an affordance.
    """
    light_lines = list(_emit_block(palette, mode="light"))
    dark_lines = list(_emit_dark_block(palette))

    parts = [
        '@import "tailwindcss";',
        "",
        "@custom-variant dark (&:where(.dark, .dark *));",
        "@custom-variant hover (&:hover);",
        "",
        "@theme {",
    ]
    # The fonts BEFORE the colours: the order has no effect on the
    # cascade (they are custom-property declarations in the same block),
    # it is there for reading — the first thing one looks for in a
    # generated theme is what was customised, not the 80 lines of
    # palette.
    parts.extend("  " + line for line in _emit_font_block(fonts))
    parts.extend("  " + line for line in _emit_scale_block(spacing, text))
    parts.extend("  " + line for line in _emit_shape_block(shape))
    parts.extend("  " + line for line in _emit_stroke_block(stroke))
    parts.extend("  " + line for line in light_lines)
    parts.append("}")

    if dark_lines:
        parts.append("")
        parts.append(".dark {")
        parts.extend("  " + line for line in dark_lines)
        parts.append("}")

    return "\n".join(parts) + "\n"


def _emit_font_block(fonts: Mapping[str, str] | None) -> Iterable[str]:
    """``--font-<slot>: <family>`` for each declared slot.

    Iterates over :data:`FONT_SLOT_NAMES` and not over the received
    keys: the output order therefore does not depend on the order the
    user wrote their dict in, and two equivalent themes produce the same
    CSS — hence the same sha256 fingerprint, hence the same compilation
    cache. Key validation lives in ``Theme.__init__`` (an unknown key
    raises at construction); here we simply ignore what is absent.
    """
    if not fonts:
        return
    for slot in FONT_SLOT_NAMES:
        family = fonts.get(slot)
        if family:
            yield f"--font-{slot}: {family};"


def _emit_scale_block(
    spacing: str | None, text: Mapping[str, str] | None
) -> Iterable[str]:
    """``--spacing`` and ``--text-<step>`` — the BASE of the scale.

    **Always emitted**, like the radii and unlike the fonts. Tailwind
    does ship both, but Bretzel no longer inherits them: it CHOOSES its
    own (cf. :data:`DEFAULT_SPACING` and :data:`DEFAULT_TEXT`), because
    the upstream scale targets pages and a tool's is tighter. Staying
    silent here would return the page to a document's scale with nobody
    having decided it.

    The DISPLAY steps (``3xl`` and above) stay absent from
    :data:`DEFAULT_TEXT`, so mute: no chrome writes them, and
    compressing them would spoil a landing page for nothing.

    A single ``--spacing`` is enough to move the whole spacing scale:
    Tailwind v4 derives ``h-10``, ``p-4``, ``gap-2``, ``w-6`` as
    ``calc(var(--spacing) * n)``. The text steps, by contrast, are
    independent tokens — hence a dict, and not a factor.

    ⚠️ **Line height is not touched, and that is deliberate.** Tailwind
    stores each step with its ``--text-<step>--line-height``, expressed
    as a RATIO (``calc(1.5 / 1)``): it therefore follows the size set
    here without our writing it. Emitting the pair would ask the app to
    decide two things where it decides one.

    Iterates over :data:`TEXT_SLOT_NAMES` and not over the received
    keys: deterministic output, hence a stable sha256 fingerprint, hence
    a stable compilation cache. Same contract as the fonts and the radii.
    """
    yield f"--spacing: {spacing or DEFAULT_SPACING};"
    merged = {**DEFAULT_TEXT, **(text or {})}
    for slot in TEXT_SLOT_NAMES:
        size = merged.get(slot)
        if size:
            yield f"--text-{slot}: {size};"


def _emit_shape_block(shape: Mapping[str, str] | None) -> Iterable[str]:
    """``--radius-<family>: <length>`` for the three families.

    Always emitted, unlike the fonts: an absent family does not let
    Tailwind fall back on a default — it makes ``rounded-box``
    NON-EXISTENT, so every slot that writes it loses its radius at once,
    silently. The fonts can stay silent because Tailwind has some; these
    three only exist if we write them.

    Iterates over :data:`SHAPE_SLOT_NAMES` and not over the received
    keys, same reason as for the fonts: deterministic output, hence a
    stable sha256 fingerprint, hence a stable compilation cache.
    """
    merged = {**DEFAULT_SHAPE, **(shape or {})}
    for slot in SHAPE_SLOT_NAMES:
        yield f"--radius-{slot}: {merged[slot]};"


def _emit_stroke_block(stroke: str | None) -> Iterable[str]:
    """``--bz-stroke`` and its two steps, derived with ``calc()``.

    Derived and not tuned: see :data:`DEFAULT_STROKE`. A ``calc()``
    rather than a Python computation because the value can be any CSS
    length — ``0.5px``, ``2px``, ``0.0625rem`` — and the browser knows
    how to multiply them where we would have to parse them.
    """
    base = stroke or DEFAULT_STROKE
    yield f"--bz-stroke: {base};"
    yield "--bz-stroke-strong: calc(var(--bz-stroke) * 2);"
    yield "--bz-stroke-accent: calc(var(--bz-stroke) * 4);"


def _emit_block(palette: Palette, *, mode: str) -> Iterable[str]:
    # Semantic slots first (no prefix), in declaration order.
    for name in SEMANTIC_COLOR_NAMES:
        resolved = palette.resolve(name, mode=mode)  # type: ignore[arg-type]
        yield _color_line(name, resolved.bg_hex)
        yield _color_line(_with_suffix(name), resolved.fg_hex)

    # Palette colors with the configured prefix.
    for name in palette.envelope_dict():
        if name in SEMANTIC_COLOR_NAMES:
            continue
        resolved = palette.resolve(name, mode=mode)  # type: ignore[arg-type]
        yield _color_line(_with_prefix(name), resolved.bg_hex)
        yield _color_line(_with_suffix(_with_prefix(name)), resolved.fg_hex)


def _emit_dark_block(palette: Palette) -> Iterable[str]:
    """Emit only the entries whose dark-mode hex differs from light.

    Skipping unchanged entries keeps the dark block small and makes
    visual diffs of the generated CSS easy to read.
    """
    for name in SEMANTIC_COLOR_NAMES:
        light = palette.resolve(name, "light")
        dark = palette.resolve(name, "dark")
        if light.bg_hex == dark.bg_hex and light.fg_hex == dark.fg_hex:
            continue
        if light.bg_hex != dark.bg_hex:
            yield _color_line(name, dark.bg_hex)
        if light.fg_hex != dark.fg_hex:
            yield _color_line(_with_suffix(name), dark.fg_hex)

    # Palette overrides (rare — most named colors stay constant in dark).
    for name in palette.envelope_dict():
        if name in SEMANTIC_COLOR_NAMES:
            continue
        light = palette.resolve(name, "light")
        dark = palette.resolve(name, "dark")
        if light.bg_hex != dark.bg_hex:
            yield _color_line(_with_prefix(name), dark.bg_hex)
        if light.fg_hex != dark.fg_hex:
            yield _color_line(_with_suffix(_with_prefix(name)), dark.fg_hex)


def _color_line(stem: str, hex_value: str) -> str:
    return f"--color-{stem}: {_hex_to_rgb_value(hex_value)};"


def _with_prefix(name: str) -> str:
    return f"{PALETTE_CLASS_PREFIX}{name}"


def _with_suffix(stem: str) -> str:
    return f"{stem}{FOREGROUND_SUFFIX}"


# ───────────────────────────────────────────────────────────────────────────
# Safelist generator
# ───────────────────────────────────────────────────────────────────────────


#: LAYOUT classes whose value is a runtime scalar.
#:
#: ``ui.grid(cols=3)`` produces ``grid-cols-3`` by f-string, and
#: ``ui.carousel(per_view=4)`` produces ``basis-1/4``. Those strings
#: exist in NO source file, so the production compiler does not see them
#: — like the colour classes, and for the same reason. Measured on
#: 2026-08-07: **the playground's grid fell back to one column in
#: compiled mode**, with no error and no trace, while being correct in
#: dev (the browser compiler scans the live DOM).
#:
#: The domain is BOUNDED, so the complete closure is writable — that is
#: exactly the colour safelist's argument. Beyond 12 columns, Tailwind
#: has no utility anyway: one needs the ``cols="grid-cols-[…]"`` escape
#: hatch, literal at the call site and therefore scanned.
#:
#: Gated by ``tests/consistency/test_emitted_classes_exist_in_source.py``.
_LAYOUT_CLASSES: tuple[str, ...] = (
    *(f"grid-cols-{n}" for n in range(1, 13)),
    "grid-cols-none", "grid-cols-auto",
    "basis-full",
    *(f"basis-1/{n}" for n in range(2, 13)),
)



# Floor: the templates the safelist guarantees even when the caller
# passes nothing (a bare ``generate_safelist_comment(palette)`` — a Theme
# used outside an app, a test). This floor WAS the whole safelist; it is
# not enough, hence the ``shapes`` parameter below.
def generate_safelist_comment(
    palette: Palette,
    responsive_classes: Sequence[str] = (),
) -> str:
    """Return a Tailwind v4 ``@source inline(...)`` directive.

    Lightning CSS / the v4 CDN scan the sources looking for utility
    patterns. A class no file writes LITERALLY will therefore not exist
    in the compiled CSS — it works in dev (the browser compiler scans
    the live DOM) and disappears in production, with no error and no
    trace. The safelist names what is in that situation.

    ``responsive_classes``: the tokens a graded prop can return prefixed
    by a breakpoint (``gap-6`` → ``md:gap-6``), supplied by
    :func:`bretzel.components.dynamic_responsive_classes`. This parameter
    exists because the ``theme`` base layer may not import
    ``components`` — it is the caller that bridges.

    ⚠️ **The COLOUR half of this function was dropped on 2026-08-30**
    (phase 5 of the token project). It expanded every theme template
    (``bg-{bg_color}/10``) over **all** the palette's colours: 3 791
    classes, 576 KB out of 717, **80 % of the sheet**. There is nothing
    left to expand — a theme writes ``bg-(--bz-bg)``, a complete class
    the compiler sees, and it is the bridge class on the root that says
    the colour (cf. :mod:`bretzel.theme.bridges`). Measured:
    ``style.css`` goes from 758 268 to 354 778 bytes.

    What remains here is the domain where the problem still exists: the
    LAYOUT classes, which an f-string assembles from a scalar
    (``grid-cols-3``, ``basis-1/4``) or which a graded prop draws from a
    theme table. Both halves are necessary: the first alone shipped on
    2026-08-07 and left
    ``ui.flex(direction={"base":"col","md":"row"})`` with no ``md:`` rule
    in production — the whole feature dead, with no error and no trace.

    v4 syntax: ``@source inline("class-1 class-2 …");`` (a real
    directive, not a CSS comment — the ``/* @source ... */`` form was
    silently ignored, which is why the colour utilities were missing).
    """
    classes: list[str] = []
    # The layout classes: a bounded domain, and ``responsive_classes``
    # can prefix any of them with any breakpoint — hence the closure over
    # both axes.
    #
    # ``_LAYOUT_CLASSES`` covers what an f-string assembles from a
    # SCALAR (``grid-cols-3``, ``basis-1/4``); ``responsive_classes``
    # covers what a graded prop draws from a theme TABLE (``gap-6``,
    # ``flex-row``, ``hidden``). Both halves are necessary: the first
    # alone shipped on 2026-08-07 and left
    # ``ui.flex(direction={"base":"col","md":"row"})`` with no ``md:``
    # rule in production — the whole feature dead, with no error and no
    # trace.
    for cls in (*_LAYOUT_CLASSES, *responsive_classes):
        classes.append(cls)
        classes.extend(f"{bp}:{cls}" for bp in BREAKPOINTS)

    inline_value = " ".join(classes)
    return f'@source inline("{inline_value}");'

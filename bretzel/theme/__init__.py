"""Visual identity, palettes, and Tailwind CSS generation."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from bretzel.theme.color_scheme import ColorScheme
from bretzel.theme.config import IconConfig, ScrollbarConfig
from bretzel.theme.css import generate_theme_css_full as generate_theme_css_full
from bretzel.theme.css import strip_safelist as strip_safelist
from bretzel.theme.css import strip_scan_roots as strip_scan_roots
from bretzel.theme.palette import (
    DEFAULT_PALETTE as DEFAULT_PALETTE,
)
from bretzel.theme.palette import (
    DEFAULT_SEMANTIC_DARK as DEFAULT_SEMANTIC_DARK,
)
from bretzel.theme.palette import (
    DEFAULT_SEMANTIC_LIGHT as DEFAULT_SEMANTIC_LIGHT,
)
from bretzel.theme.palette import (
    Palette as Palette,
)
from bretzel.theme.palette import (
    ResolvedColor as ResolvedColor,
)
from bretzel.theme.palette import (
    ThemeError,
)
from bretzel.theme.slots import merge_component_themes as merge_component_themes
from bretzel.theme.tokens import (
    DEFAULT_PALETTE_NAMES,
    DEFAULT_SHAPE,
    DEFAULT_SPACING,
    DEFAULT_STROKE,
    DEFAULT_TEXT,
    FONT_SLOT_NAMES,
    SEMANTIC_COLOR_NAMES,
    SHAPE_SLOT_NAMES,
    TEXT_SLOT_NAMES,
)
from bretzel.theme.tokens import (
    DEFAULT_SPACING_PX as DEFAULT_SPACING_PX,
)
from bretzel.theme.tokens import (
    AnyColor as AnyColor,
)
from bretzel.theme.tokens import (
    PaletteColors as PaletteColors,
)
from bretzel.theme.tokens import (
    SemanticColors as SemanticColors,
)

#: **What the user writes.** The internal generation, resolution and
#: serialisation tools stay importable by their precise path.
__all__ = [
    # Entry point: you build one and pass it to Bretzel(theme=…)
    "Theme",
    # Current light/dark mode — a ClientState supplied by the framework
    "ColorScheme",
    # Configuration sections passed to the constructor
    "IconConfig",
    "ScrollbarConfig",
    # What you name in a slot: the semantic colours
    "SEMANTIC_COLOR_NAMES",
    # The named hues of the shipped palette.
    "DEFAULT_PALETTE_NAMES",
    # What ``Theme(fonts=…)`` accepts — three slots, closed
    "FONT_SLOT_NAMES",
    # What ``Theme(shape=…)`` accepts — three families, closed
    "SHAPE_SLOT_NAMES",
    # What ``Theme(text=…)`` accepts — Tailwind's steps, closed.
    # The middle step is called ``base`` there and not ``md``: it is the
    # one place in the framework where the two scales touch.
    "TEXT_SLOT_NAMES",
    # The spacing step in PIXELS, for an app composing geometry in
    # Python (the height of an N-hour block in a grid) — a Tailwind class
    # cannot add up.
    "DEFAULT_SPACING_PX",
    # The error a malformed theme raises
    "ThemeError",
]

#: **Re-exported for the OTHER LAYERS, not for an app author.**
#:
#: Every name here carries the redundant ``X as X`` alias at import: that
#: is the PEP 484 marker of an intentional re-export. The list is checked
#: by ``tests/consistency/test_public_surface_is_classified.py``: nothing
#: enters a facade without being classified on one side or the other.
_INTERNAL = [
    "Palette",
    "ResolvedColor",
    "SemanticColors",
    "PaletteColors",
    "AnyColor",
    "merge_component_themes",
    "generate_theme_css_full",
    "strip_safelist",
    "strip_scan_roots",
    "DEFAULT_PALETTE",
    "DEFAULT_SEMANTIC_LIGHT",
    "DEFAULT_SEMANTIC_DARK",
]


# Sentinel to distinguish "user passed nothing" from "user passed None".
_UNSET: Any = object()


# ───────────────────────────────────────────────────────────────────────────
# Theme
# ───────────────────────────────────────────────────────────────────────────


class Theme:
    """Build a user-facing Bretzel theme."""

    __slots__ = (
        "_components",
        "_css",
        "_css_cache",
        "_fonts",
        "_icons",
        "_merged_components",
        "_palette",
        "_palette_dark",
        "_resolved_palette",
        "_scrollbar",
        "_semantic",
        "_semantic_dark",
        "_shape",
        "_spacing",
        "_stroke",
        "_text",
    )

    def __init__(
        self,
        *,
        semantic: Mapping[str, Any] | None = None,
        semantic_dark: Mapping[str, Any] | None = None,
        palette: Mapping[str, Any] | None = None,
        palette_dark: Mapping[str, Any] | None = None,
        components: Mapping[str, Any] | None = None,
        fonts: Mapping[str, str] | None = None,
        spacing: str | None = None,
        text: Mapping[str, str] | None = None,
        shape: Mapping[str, str] | None = None,
        stroke: str | None = None,
        css: str | Path | None = None,
        scrollbar: ScrollbarConfig | Mapping[str, Any] | None = _UNSET,
        icons: IconConfig | Mapping[str, Any] | None = _UNSET,
        base: Theme | None | Literal['default'] = "default",
    ) -> None:
        base_theme = _resolve_base(base)

        # ── Section-by-section merge with the resolved base ─────────────
        self._semantic = _merge_dict(_section(base_theme, "_semantic"), semantic)
        self._semantic_dark = _merge_dict(
            _section(base_theme, "_semantic_dark"), semantic_dark
        )
        self._palette = _merge_dict(_section(base_theme, "_palette"), palette)
        self._palette_dark = _merge_dict(
            _section(base_theme, "_palette_dark"), palette_dark
        )
        self._components = _deep_merge_dicts(
            _section(base_theme, "_components"), components
        )
        # Merges ``cls.THEME`` ↔ override, memoised by THEME_KEY (cf.
        # ``merged_component_theme``). Both inputs are immutable after
        # boot, so the merge is computed ONCE — without the cache,
        # ``compose_class`` re-merged on every slot of every render
        # (measured: +76 % on a render of an overridden Select).
        self._merged_components: dict[str, dict[str, Any]] = {}
        self._fonts = _merge_fonts(_section(base_theme, "_fonts"), fonts)
        # The scale: its base is a SCALAR (a single setting, like the
        # stroke), its text steps a dict of closed slots (like the
        # fonts). Both are mute by default — cf. ``_emit_scale_block``.
        self._spacing = _merge_spacing(_scalar(base_theme, "_spacing"), spacing)
        self._text = _merge_text(_section(base_theme, "_text"), text)
        self._shape = _merge_shape(_section(base_theme, "_shape"), shape)
        # ``_scalar`` and not ``_section``: the stroke is ONE string,
        # not a dict of slots — it has only one question to settle.
        self._stroke = _merge_stroke(
            _scalar(base_theme, "_stroke"), stroke
        )
        # The CSS door ADDS to the base's, it does not replace it.
        #
        # The first version replaced, on the grounds that inheriting
        # invisible rules from ``base=`` is unpleasant. Measured, that
        # gave half a theme: ``Theme(base=brand, css=…)`` kept the
        # brand's ``--font-sans`` (the dict sections do merge) and lost
        # the ``@font-face`` that made that font loadable. The page fell
        # back on the system stack **saying nothing** — the exact failure
        # mode this section exists to close.
        #
        # In strings, the last piece wins at equal specificity, so
        # "adding" is enough to override too: the CSS cascade IS the
        # removal mechanism. What remains is the reset, which an explicit
        # ``css=""`` provides — same way out as ``scrollbar=None``.
        self._css = _merge_css(_section_tuple(base_theme, "_css"), css)
        self._scrollbar = _coerce_scrollbar(
            scrollbar,
            base_theme._scrollbar if base_theme else ScrollbarConfig(),
        )
        self._icons = _coerce_icons(
            icons,
            base_theme._icons if base_theme else IconConfig(),
        )

        # ── Build the resolved Palette eagerly so any error surfaces here ──
        self._resolved_palette = Palette(
            semantic_light=self._semantic,
            semantic_dark=self._semantic_dark,
            palette_light=self._palette,
            palette_dark=self._palette_dark,
        )
        # CSS is generated lazily — first call to ``generate_css()``
        # caches it. Theme is immutable post-init, but the safelist
        # depends on the templates passed to the call: the cache is a
        # dict keyed by those templates.
        self._css_cache: dict[tuple[str, ...], str] = {}

    # ── Read-only accessors ─────────────────────────────────────────────

    def get_palette(self) -> Palette:
        return self._resolved_palette

    def get_component_theme(self, name: str) -> dict[str, Any]:
        """Return the RAW user override dict for ``name`` — empty dict
        when the component has no override. Components resolve their
        effective theme via :meth:`merged_component_theme` (called by
        ``Component._resolved_theme``)."""
        return self._components.get(name, {})

    def get_component_overrides(self) -> Mapping[str, Any]:
        """Return component overrides exactly as declared."""
        return self._components

    def merged_component_theme(
        self, name: str, shipped: dict[str, Any]
    ) -> dict[str, Any]:
        """Deep-merge of ``shipped`` (the component's ``cls.THEME``)
        with the user override registered under ``name`` — memoized.

        Both inputs are immutable after startup (``cls.THEME`` is a
        module constant ; the override dict is built once at ``Theme``
        construction), so the merge is computed once per THEME_KEY.
        Classes sharing a THEME_KEY (the Sidebar / Navbar families)
        share the SAME ``THEME`` dict object, so keying by name alone
        is sound. Returns ``shipped`` itself when no override exists —
        identity fast path ; callers must treat the result as
        read-only either way."""
        override = self._components.get(name)
        if not override:
            return shipped
        cached = self._merged_components.get(name)
        if cached is None:
            cached = merge_component_themes(shipped, override)
            self._merged_components[name] = cached
        return cached

    def get_scrollbar(self) -> ScrollbarConfig:
        return self._scrollbar

    def get_icons(self) -> IconConfig:
        return self._icons

    # ── Generators ──────────────────────────────────────────────────────

    def generate_css(
        self,
        *,
        responsive_classes: Sequence[str] = (),
    ) -> str:
        """The full ``theme.css`` Lightning CSS will ingest. Cached.

        ``responsive_classes``: the tokens of the graded tables (cf.
        :func:`bretzel.components.dynamic_responsive_classes`), injected
        at startup.

        The cache is keyed by the list — two calls with different lists
        must produce two different CSS outputs, otherwise the first call
        (often a bare call in a test) would freeze a truncated safelist
        for the whole process. That is also why the new list enters the
        key rather than being added to it silently: otherwise the CSS
        served would depend on the order of the calls.

        """
        key = tuple(responsive_classes)
        if key not in self._css_cache:
            self._css_cache[key] = generate_theme_css_full(
                self._resolved_palette,
                scrollbar=self._scrollbar,
                responsive_classes=key,
                fonts=self._fonts,
                spacing=self._spacing,
                text=self._text,
                shape=self._shape,
                stroke=self._stroke,
                extra_css="\n".join(self._css),
            )
        return self._css_cache[key]

    # ── Introspection ───────────────────────────────────────────────────

    def dump(self, format: Literal["json", "python"] = "json") -> str:
        """Serialise the resolved theme — handy for debugging."""
        payload: dict[str, Any] = {
            "semantic": dict(self._semantic),
            "semantic_dark": dict(self._semantic_dark),
            "palette": dict(self._palette),
            "palette_dark": dict(self._palette_dark),
            "components": dict(self._components),
            "fonts": dict(self._fonts),
            "spacing": self._spacing,
            "text": dict(self._text),
            "shape": dict(self._shape),
            "stroke": self._stroke,
            "css": list(self._css),
            "scrollbar": dataclasses.asdict(self._scrollbar),
            "icons": dataclasses.asdict(self._icons),
        }
        if format == "json":
            return json.dumps(payload, indent=2, default=str, sort_keys=True)
        # Python repr — useful when the user wants to copy a snapshot
        # back into source code.
        return repr(payload)


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


def _resolve_base(
    base: Theme | None | Literal['default'],
) -> Theme | None:
    """Resolve the ``base=`` argument into a concrete ``Theme | None``."""
    if base is None:
        return None
    if base == "default":
        return _default_theme()
    if isinstance(base, Theme):
        return base
    raise ThemeError(
        f"Unsupported ``base`` value : {base!r}. "
        "Expected None, 'default', or a Theme instance."
    )


_DEFAULT_THEME_INSTANCE: Theme | None = None


def _default_theme() -> Theme:
    """Lazy-construct the bundled default theme (cached after first call).

    Phase 1 builds it without component overrides — Layer 5 will land
    a ``presets/default.py`` aggregator that imports each component's
    theme dict and threads it through here.
    """
    global _DEFAULT_THEME_INSTANCE
    if _DEFAULT_THEME_INSTANCE is None:
        _DEFAULT_THEME_INSTANCE = Theme(
            base=None,
            semantic=DEFAULT_SEMANTIC_LIGHT,
            semantic_dark=DEFAULT_SEMANTIC_DARK,
            palette=DEFAULT_PALETTE,
            palette_dark=None,  # palette colors stay constant in dark
            components={},  # filled by presets/default.py once it ships
            scrollbar=ScrollbarConfig(),
            icons=IconConfig(),
        )
    return _DEFAULT_THEME_INSTANCE


def _section(base: Theme | None, attr: str) -> dict[str, Any]:
    """Read a section off the resolved base, defaulting to empty dict."""
    if base is None:
        return {}
    value = getattr(base, attr)
    return dict(value)


def _scalar(base: Theme | None, attr: str) -> str | None:
    """Read a scalar section off the resolved base, defaulting to None."""
    return None if base is None else getattr(base, attr)


def _section_tuple(base: Theme | None, attr: str) -> tuple[str, ...]:
    """Read a tuple section off the resolved base, defaulting to empty."""
    if base is None:
        return ()
    return tuple(getattr(base, attr))


def _merge_shape(
    base: Mapping[str, str], override: Mapping[str, str] | None
) -> dict[str, str]:
    """Shallow merge, **and refuse an unknown family** — same door as
    :func:`_merge_fonts`, for the same silence.

    ``Theme(shape={"card": "1rem"})`` is not an extension: it is a token
    nothing will emit and no class will read. Without the guard, the
    section would be accepted, the radius would not move, and there
    would be nothing to see.

    The message names the three families AND says where to go for a
    single component, because that is the real question behind an
    invented key: "I just want to round my cards more".
    """
    merged = {**DEFAULT_SHAPE, **base}
    if not override:
        return merged
    unknown = sorted(set(override) - set(SHAPE_SLOT_NAMES))
    if unknown:
        raise ThemeError(
            f"Theme(shape=…): unknown family/families {unknown}. "
            f"The three families are {list(SHAPE_SLOT_NAMES)} — `box` for "
            f"what contains, `field` for a control you aim at, `selector` "
            f"for a small mark or a nested control. "
            f"For ONE component's radius, override its theme: "
            f'Theme(components={{"card": {{"slots": {{"root": …}}}}}}).'
        )
    for slot, length in override.items():
        if not isinstance(length, str) or not length.strip():
            raise ThemeError(
                f"Theme(shape={{{slot!r}: {length!r}}}): expected a "
                f'non-empty CSS length, for example "0.75rem" or "0". To '
                f"leave this family alone, omit the key."
            )
    merged.update(override)
    return merged


def _merge_spacing(base: str | None, override: str | None) -> str:
    """The spacing step: a string, and it may stay absent.

    Absent, it is :data:`DEFAULT_SPACING` that comes out — Bretzel
    CHOOSES its scale instead of inheriting Tailwind's, which targets
    pages. That is the opposite of the fonts' rule, and the difference is
    clean: copying an upstream value can only diverge from it, choosing
    one says something.

    A CSS length and not a number, for the reason that already holds for
    the stroke: the value can be ``3px``, ``0.1875rem`` or ``0.2em``, and
    it is the browser that knows how to multiply them where we would have
    to parse them.
    """
    if override is None:
        return base or DEFAULT_SPACING
    if not isinstance(override, str) or not override.strip():
        raise ThemeError(
            f"Theme(spacing={override!r}): expected a non-empty CSS "
            f'length, for example "0.1875rem" (3 px, the shipped default) '
            f'or "0.25rem" (Tailwind\'s, that is to say a document '
            f"scale). To leave it alone, omit the keyword."
        )
    return override.strip()


def _merge_text(
    base: Mapping[str, str], override: Mapping[str, str] | None
) -> dict[str, str]:
    """The text steps — same guards as the fonts, same reason.

    An unknown step is refused rather than ignored: ``--text-md`` does
    not exist in Tailwind, so ``Theme(text={"md": "14px"})`` would emit a
    token nobody reads — nothing to see, no error, no CSS, no hint. It is
    the family of silences the theme layer has turned away at the door
    since 2026-08-16.

    ⚠️ ``base`` is Tailwind's name for the middle step, where a
    component's ``size=`` says ``md``. The two scales are not the same:
    this one is the CSS tokens', that one is a component's steps', and it
    is the component's theme that translates one into the other
    (``"md": "text-base"``).
    """
    merged = {**DEFAULT_TEXT, **base}
    if not override:
        return merged
    unknown = sorted(set(override) - set(TEXT_SLOT_NAMES))
    if unknown:
        raise ThemeError(
            f"Theme(text=…): unknown step(s) {unknown}. The steps are "
            f"{list(TEXT_SLOT_NAMES)} — Tailwind's, so the only ones the "
            f"`text-*` utilities read. Note: the middle step is called "
            f"`base`, not `md` (`md` is a `size=` name, not a CSS token)."
        )
    for slot, size in override.items():
        if not isinstance(size, str) or not size.strip():
            raise ThemeError(
                f"Theme(text={{{slot!r}: {size!r}}}): expected a "
                f'non-empty CSS length, for example "13px" or "0.8125rem". '
                f"To leave this step alone, omit the key."
            )
    merged.update({s: v.strip() for s, v in override.items()})
    return merged


def _merge_stroke(base: str | None, override: str | None) -> str:
    """The stroke width: a string, not a dict.

    One single value because there is only one question — the two other
    steps derive from it (cf. :data:`DEFAULT_STROKE`). The guard is the
    same as for the fonts and the families: an empty value can only mean
    "I am removing my override", and the way to say that is not to write
    the keyword.
    """
    if override is None:
        return base or DEFAULT_STROKE
    if not isinstance(override, str) or not override.strip():
        raise ThemeError(
            f"Theme(stroke={override!r}): expected a non-empty CSS "
            f'length, for example "1px" or "0.5px". To leave it alone, '
            f"omit the keyword. For a single component, override its "
            f'theme: Theme(components={{"card": {{"slots": {{…}}}}}}).'
        )
    return override


def _merge_css(
    base: tuple[str, ...], css: str | Path | None
) -> tuple[str, ...]:
    """Add the caller's piece to the base's.

    Stored as pieces rather than as one glued string so that resetting
    stays expressible: once concatenated, one no longer knows where the
    base ends. ``css=None`` inherits, ``css=""`` clears, everything else
    adds.
    """
    if css is None:
        return base
    chunk = _read_css(css).strip()
    if not chunk:
        return ()
    return (*base, chunk)


def _merge_fonts(
    base: Mapping[str, str], override: Mapping[str, str] | None
) -> dict[str, str]:
    """Shallow merge, **and refuse an unknown slot**.

    The three slots are Tailwind's (:data:`FONT_SLOT_NAMES`), so
    ``Theme(fonts={"body": …})`` is not an extension: it is a token
    nothing will emit and no class will read. Without this guard, the
    section would be accepted, the font would not change, and there would
    be **nothing to see** — no error, no CSS, no hint. It is the family
    of silences noted on 2026-08-16 on the theme layer (unknown
    component, misspelled slot, non-existent variant); this one is born
    closed rather than waiting for its lint rule.

    An empty family (``{"sans": ""}``) is refused by the same door: the
    only thing it can mean is "I am removing my override", and the way to
    say that is not to write the key.
    """
    if not override:
        return dict(base)
    unknown = sorted(set(override) - set(FONT_SLOT_NAMES))
    if unknown:
        raise ThemeError(
            f"Theme(fonts=…): unknown slot(s) {unknown}. "
            f"The three slots are {list(FONT_SLOT_NAMES)} — they are "
            f"Tailwind's, so the only ones the `font-*` utilities read. "
            f"For a distinct heading font, override the component's "
            f'theme: Theme(components={{"heading": {{"slots": {{…}}}}}}).'
        )
    for slot, family in override.items():
        if not isinstance(family, str) or not family.strip():
            raise ThemeError(
                f"Theme(fonts={{{slot!r}: {family!r}}}): expected a "
                f"non-empty CSS `font-family` value, for example "
                f'"Inter, ui-sans-serif, system-ui, sans-serif". To leave '
                f"this slot alone, omit the key."
            )
    # The merge itself goes through ``_merge_dict``, the contract of the
    # four colour sections: two implementations of a flat merge 40 lines
    # apart would end up diverging, and it is this section that would
    # keep the old behaviour silently.
    return _merge_dict(base, {s: f.strip() for s, f in override.items()})


def _read_css(css: str | Path) -> str:
    """Return the CSS of ``Theme(css=…)`` — literal string or file.

    Both forms exist because both uses exist: three rules are fine
    written in the source, a real sheet (``@font-face`` + keyframes)
    wants a ``.css`` with its syntax highlighting and its formatter. The
    discriminant is the **type**, not a heuristic on the content —
    guessing that a string "looks like a path" would make behaviour
    depend on the presence of a brace.

    A missing file RAISES: the failure mode we refuse is precisely that
    of a style that does not apply while saying nothing.
    """
    if isinstance(css, Path):
        try:
            return css.read_text(encoding="utf-8")
        except OSError as exc:
            raise ThemeError(
                f"Theme(css={str(css)!r}): unreadable file — {exc}. "
                f"The path is resolved as-is (relative to the process's "
                f"working directory, not to the module declaring the "
                f"theme)."
            ) from exc
    if isinstance(css, str):
        return css
    raise ThemeError(
        f"Theme(css={css!r}): expected a CSS string or a `pathlib.Path` "
        f"to a `.css` file."
    )


def _merge_dict(
    base: Mapping[str, Any], override: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Shallow merge — every key in ``override`` replaces the base
    entry at the top level. Used for color sections (the values are
    hex strings or tuples, not nested dicts)."""
    out = dict(base)
    if override:
        for k, v in override.items():
            out[k] = v
    return out


def _deep_merge_dicts(
    base: Mapping[str, Any], override: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Deep merge — for the components section where overrides describe
    nested ``{slots, variants, sizes}`` trees (cf. ``slots.py``)."""
    if not override:
        return dict(base)
    return merge_component_themes(dict(base), dict(override))


def _coerce_scrollbar(
    value: ScrollbarConfig | Mapping[str, Any] | None | object,
    fallback: ScrollbarConfig,
) -> ScrollbarConfig:
    if value is _UNSET:
        return fallback
    if value is None:
        return ScrollbarConfig()
    if isinstance(value, ScrollbarConfig):
        return value
    if isinstance(value, Mapping):
        # Allow ``{"width": "6px"}`` style overrides — fields not
        # mentioned fall through to the dataclass defaults.
        return dataclasses.replace(fallback, **dict(value))
    raise ThemeError(
        f"Unsupported scrollbar value : {value!r}. "
        "Expected ScrollbarConfig / mapping / None."
    )


def _coerce_icons(
    value: IconConfig | Mapping[str, Any] | None | object,
    fallback: IconConfig,
) -> IconConfig:
    if value is _UNSET:
        return fallback
    if value is None:
        return IconConfig()
    if isinstance(value, IconConfig):
        return value
    if isinstance(value, Mapping):
        return dataclasses.replace(fallback, **dict(value))
    raise ThemeError(
        f"Unsupported icons value : {value!r}. "
        "Expected IconConfig / mapping / None."
    )

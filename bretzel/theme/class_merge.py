"""The app's class wins over the theme's: the conflict is settled in the HTML.

Why this exists
---------------

Two Tailwind utilities that set the same CSS property have the same
specificity. What settles them is their order in the generated SHEET,
which Tailwind decides — never their order in the ``class`` attribute. A
``ui.card(classes="p-4")`` over a theme's ``p-2`` therefore lost about
one time in two, silently, and the apps learnt to write ``!p-4``.

So the conflict is resolved where we control it: before the classes
are joined, every utility of the THEME's string whose CSS properties the
APP's string redeclares, in the same variant scope, is removed. The app's
own string is never touched, its ``!`` included.

How a utility is classified
---------------------------

By the CSS properties Tailwind emits for it, not by a family name:
``p-4`` sets ``padding``, ``px-2`` sets ``padding-inline``, ``shadow-md``
sets ``--tw-shadow`` and ``box-shadow``, ``ring-2`` sets
``--tw-ring-shadow`` and ``box-shadow``. Shorthands are read as their
longhands (:data:`_LONGHANDS`), so the comparison is one of SETS: a theme
utility goes when all of its longhands are redeclared by the app's
utilities of the same scope, together (``w-16 h-16`` removes a
``size-9``). It is what keeps a ring from erasing a shadow — they share
``box-shadow`` but not their ``--tw-*`` — and a ``px-4`` from erasing a
``p-2`` (the block padding would go with it; the sheet puts the side
after the whole, so the ``px-4`` wins anyway).

The table is Python, so it could drift from Tailwind: the gate
``tests/consistency/test_class_merge_matches_the_sheet.py`` compiles
every class of the shipped themes and of the examples, and compares what
the table says with what the sheet declares.

**When in doubt, nothing is merged.** A class the table does not know —
``group``, ``bz-input``, a selector utility like ``space-y-2``, an
arbitrary value whose type cannot be told (``text-[var(--x)]``) — removes
nothing and is removed by nothing: the behaviour from before the merge,
never worse.

The vocabulary is the framework's, and closed: the eleven semantic
colours and their ``-foreground``, the app palette's ``ui-*`` names,
Tailwind's shaded families, the thirteen text steps. An app's theme
changes their values, never their names — so the classification does not
depend on the app, only the cache does (:meth:`Theme.merge_classes`).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from bretzel.theme.tokens import (
    FOREGROUND_SUFFIX,
    GENERATED_COLOR_NAMES,
    PALETTE_CLASS_PREFIX,
    SEMANTIC_COLOR_NAMES,
    TEXT_SLOT_NAMES,
)

__all__ = (
    "TAILWIND_COLOR_FAMILIES",
    "UNSHADED_COLORS",
    "longhands",
    "merge_classes",
    "slot_strings",
    "split_token",
    "utility_properties",
)


# ───────────────────────────────────────────────────────────────────────────
# Reading a token
# ───────────────────────────────────────────────────────────────────────────


def _top_level(text: str, separator: str) -> list[int]:
    """Where ``separator`` stands outside ``[...]`` and ``(...)`` — a
    ``:`` or a ``-`` inside a value (``[&:hover]``, ``(length:--x)``)
    belongs to it."""
    depth, found = 0, []
    for index, char in enumerate(text):
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        elif char == separator and depth == 0:
            found.append(index)
    return found


def split_token(token: str) -> tuple[str, str]:
    """``("dark:hover:", "bg-text/5")`` for ``dark:hover:!bg-text/5``.

    The variant scope keeps its colons; the utility loses its ``!`` in
    either of Tailwind's spellings (``!p-0``, ``p-0!``, and v3's
    ``!hover:p-0``). A ``:`` inside ``[...]`` or ``(...)`` is part of a
    value (``[&:hover]``, ``(length:--x)``), not a variant's.
    """
    colons = _top_level(token, ":")
    cut = colons[-1] + 1 if colons else 0
    scope = token[:cut].lstrip("!")
    utility = token[cut:]
    if utility.startswith("!"):
        utility = utility[1:]
    elif utility.endswith("!"):
        utility = utility[:-1]
    return scope, utility


# ───────────────────────────────────────────────────────────────────────────
# Values
# ───────────────────────────────────────────────────────────────────────────

#: Tailwind's colour families: with a shade (``stone-400``), they exist.
#: Shared with the ``unknown-theme-color`` rule, which judges the same names.
TAILWIND_COLOR_FAMILIES: Final = frozenset({
    "slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber", "yellow",
    "lime", "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet",
    "purple", "fuchsia", "pink", "rose", "mauve", "olive", "mist", "taupe",
})

#: The colours named without a shade.
UNSHADED_COLORS: Final = (
    frozenset(SEMANTIC_COLOR_NAMES)
    | {f"{name}{FOREGROUND_SUFFIX}" for name in SEMANTIC_COLOR_NAMES}
    | {"black", "white", "transparent", "current", "inherit"}
    | frozenset(GENERATED_COLOR_NAMES)
)

_ALPHA = r"(?:/(?:\d+(?:\.\d+)?|\[[^\]]+\]|\([^)]+\)))?"
_SHADED = re.compile(rf"^(?P<family>[a-z]+)-(?:50|[1-9]00|950){_ALPHA}$")
_NAMED = re.compile(rf"^(?P<name>[a-z][a-z0-9-]*?){_ALPHA}$")
#: ``(--x)`` — a bare variable. Tailwind reads it as a COLOUR wherever
#: the utility also takes one (``border-(--x)`` is a border colour; a
#: width is written ``border-(length:--x)``).
_BARE_VAR = re.compile(rf"^\(--[\w-]+\){_ALPHA}$")
_COLOR_VAR = re.compile(rf"^\(color:--[\w-]+\){_ALPHA}$")
_LENGTH_VAR = re.compile(r"^\(length:--[\w-]+\)$")
_ARBITRARY = re.compile(r"^\[(?P<body>.+)\]$")
_COLOR_FUNCTION = re.compile(r"^(?:#|(?:rgba?|hsla?|oklch|oklab|lab|lch|color-mix|color)\()")
_LENGTH_VALUE = re.compile(
    r"^(?:-?\d*\.?\d+(?:px|r?em|%|vh|vw|dvh|svh|lvh|vmin|vmax|ch|ex|lh|rlh|cqw|cqh|pt)?"
    r"|(?:calc|min|max|clamp)\(.*\))$"
)
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


def _is_color(value: str) -> bool:
    if _BARE_VAR.match(value) or _COLOR_VAR.match(value):
        return True
    arbitrary = _ARBITRARY.match(value)
    if arbitrary:
        body = arbitrary["body"]
        return bool(_COLOR_FUNCTION.match(body.removeprefix("color:")))
    shaded = _SHADED.match(value)
    if shaded:
        return shaded["family"] in TAILWIND_COLOR_FAMILIES
    named = _NAMED.match(value)
    if not named:
        return False
    name = named["name"]
    return name in UNSHADED_COLORS or (
        name.startswith(PALETTE_CLASS_PREFIX) and len(name) > len(PALETTE_CLASS_PREFIX))


def _is_length(value: str) -> bool:
    """A width spelled so Tailwind cannot take it for a colour."""
    if _LENGTH_VAR.match(value) or _NUMBER.match(value):
        return True
    arbitrary = _ARBITRARY.match(value)
    return bool(arbitrary and _LENGTH_VALUE.match(arbitrary["body"].removeprefix("length:")))


# ───────────────────────────────────────────────────────────────────────────
# The table
# ───────────────────────────────────────────────────────────────────────────

#: Utilities that are a word, not a prefix and a value.
_STATIC: Final[dict[str, tuple[str, ...]]] = {
    **dict.fromkeys(
        ("block", "inline-block", "inline", "flex", "inline-flex", "grid", "inline-grid",
         "contents", "flow-root", "table", "table-row", "table-cell", "list-item", "hidden"),
        ("display",)),
    **dict.fromkeys(("static", "fixed", "absolute", "relative", "sticky"), ("position",)),
    **dict.fromkeys(("visible", "invisible", "collapse"), ("visibility",)),
    "sr-only": ("border-width", "clip-path", "height", "margin", "overflow", "padding",
                "position", "white-space", "width"),
    "truncate": ("overflow", "text-overflow", "white-space"),
    **dict.fromkeys(("text-ellipsis", "text-clip"), ("text-overflow",)),
    **dict.fromkeys(("uppercase", "lowercase", "capitalize", "normal-case"),
                    ("text-transform",)),
    **dict.fromkeys(("italic", "not-italic"), ("font-style",)),
    **dict.fromkeys(("underline", "overline", "line-through", "no-underline"),
                    ("text-decoration-line",)),
    **dict.fromkeys(("text-left", "text-center", "text-right", "text-justify", "text-start",
                     "text-end"), ("text-align",)),
    **dict.fromkeys(("text-wrap", "text-nowrap", "text-balance", "text-pretty"),
                    ("text-wrap",)),
    "tabular-nums": ("--tw-numeric-spacing", "font-variant-numeric"),
    **dict.fromkeys(("flex-row", "flex-row-reverse", "flex-col", "flex-col-reverse"),
                    ("flex-direction",)),
    **dict.fromkeys(("flex-wrap", "flex-nowrap", "flex-wrap-reverse"), ("flex-wrap",)),
    **dict.fromkeys(("flex-1", "flex-auto", "flex-initial", "flex-none"), ("flex",)),
    "grow": ("flex-grow",),
    "shrink": ("flex-shrink",),
    "transition": ("transition-duration", "transition-property", "transition-timing-function"),
    "transition-none": ("transition-property",),
    **dict.fromkeys(("border-solid", "border-dashed", "border-dotted", "border-double",
                     "border-hidden", "border-none"), ("--tw-border-style", "border-style")),
    **dict.fromkeys(("border-collapse", "border-separate"), ("border-collapse",)),
    "outline-none": ("--tw-outline-style", "outline-style"),
    "ring-inset": ("--tw-ring-inset",),
    "break-words": ("overflow-wrap",),
    "break-all": ("word-break",),
    **dict.fromkeys(("snap-x", "snap-y", "snap-both"), ("scroll-snap-type",)),
    "snap-none": ("scroll-snap-type",),
    **dict.fromkeys(("snap-mandatory", "snap-proximity"), ("--tw-scroll-snap-strictness",)),
    **dict.fromkeys(("snap-start", "snap-center", "snap-end", "snap-align-none"),
                    ("scroll-snap-align",)),
    **dict.fromkeys(("list-inside", "list-outside"), ("list-style-position",)),
    "isolate": ("isolation",),
    "grayscale": ("--tw-grayscale", "filter"),
    "field-sizing-content": ("field-sizing",),
    "field-sizing-fixed": ("field-sizing",),
}

#: Prefixes whose every value sets the same properties.
_PLAIN: dict[str, tuple[str, ...]] = {
    "p": ("padding",), "px": ("padding-inline",), "py": ("padding-block",),
    "pt": ("padding-top",), "pr": ("padding-right",), "pb": ("padding-bottom",),
    "pl": ("padding-left",), "ps": ("padding-inline-start",),
    "pe": ("padding-inline-end",),
    "m": ("margin",), "mx": ("margin-inline",), "my": ("margin-block",),
    "mt": ("margin-top",), "mr": ("margin-right",), "mb": ("margin-bottom",),
    "ml": ("margin-left",), "ms": ("margin-inline-start",), "me": ("margin-inline-end",),
    "w": ("width",), "h": ("height",), "size": ("height", "width"),
    "min-w": ("min-width",), "max-w": ("max-width",),
    "min-h": ("min-height",), "max-h": ("max-height",),
    "inset": ("inset",), "inset-x": ("inset-inline",), "inset-y": ("inset-block",),
    "top": ("top",), "right": ("right",), "bottom": ("bottom",), "left": ("left",),
    "start": ("inset-inline-start",), "end": ("inset-inline-end",),
    "gap": ("gap",), "gap-x": ("column-gap",), "gap-y": ("row-gap",),
    "basis": ("flex-basis",), "grow": ("flex-grow",), "shrink": ("flex-shrink",),
    "order": ("order",), "z": ("z-index",), "opacity": ("opacity",),
    "grid-cols": ("grid-template-columns",), "grid-rows": ("grid-template-rows",),
    "col-span": ("grid-column",), "col-start": ("grid-column-start",),
    "col-end": ("grid-column-end",), "row-span": ("grid-row",),
    "row-start": ("grid-row-start",), "row-end": ("grid-row-end",),
    "aspect": ("aspect-ratio",),
    "leading": ("--tw-leading", "line-height"),
    "tracking": ("--tw-tracking", "letter-spacing"),
    "duration": ("--tw-duration", "transition-duration"),
    "ease": ("--tw-ease", "transition-timing-function"),
    "delay": ("transition-delay",),
    "rotate": ("rotate",),
    "translate-x": ("--tw-translate-x", "translate"),
    "translate-y": ("--tw-translate-y", "translate"),
    "line-clamp": ("-webkit-box-orient", "-webkit-line-clamp", "display", "overflow"),
    "scroll-pt": ("scroll-padding-top",), "scroll-pb": ("scroll-padding-bottom",),
    "scroll-mt": ("scroll-margin-top",), "scroll-mb": ("scroll-margin-bottom",),
    "underline-offset": ("text-underline-offset",),
    "outline-offset": ("outline-offset",),
    "cursor": ("cursor",), "select": ("-webkit-user-select", "user-select"),
    "pointer-events": ("pointer-events",), "resize": ("resize",),
    "animate": ("animation",), "overflow": ("overflow",), "overflow-x": ("overflow-x",),
    "overflow-y": ("overflow-y",), "whitespace": ("white-space",),
    "items": ("align-items",), "self": ("align-self",),
    "justify-items": ("justify-items",), "justify-self": ("justify-self",),
    "place-items": ("place-items",), "place-content": ("place-content",),
    "place-self": ("place-self",),
    "list": ("list-style-type",), "align": ("vertical-align",),
    "origin": ("transform-origin",), "blur": ("--tw-blur", "filter"),
    "brightness": ("--tw-brightness", "filter"),
    "backdrop-blur": ("--tw-backdrop-blur", "-webkit-backdrop-filter", "backdrop-filter"),
    "drop-shadow": ("--tw-drop-shadow", "--tw-drop-shadow-size", "filter"),
    "border-spacing": ("--tw-border-spacing-x", "--tw-border-spacing-y", "border-spacing"),
    "transition": ("transition-duration", "transition-property", "transition-timing-function"),
}

_CONTENT = frozenset({"start", "end", "center", "between", "around", "evenly", "stretch",
                      "normal", "baseline"})
_JUSTIFY = _CONTENT | {"center-safe", "end-safe"}
_OBJECT_FIT = frozenset({"contain", "cover", "fill", "none", "scale-down"})
_SHADOW_SIZES = frozenset({"2xs", "xs", "sm", "md", "lg", "xl", "2xl", "none"})
_WEIGHTS = frozenset({"thin", "extralight", "light", "normal", "medium", "semibold",
                      "bold", "extrabold", "black"})
_FAMILIES_FONT = frozenset({"sans", "serif", "mono"})
_TEXT_SIZE = re.compile(
    rf"^(?:{'|'.join(map(re.escape, TEXT_SLOT_NAMES))})(?:/(?:\d+|\[[^\]]+\]|\([^)]+\)))?$")
_DECORATION_STYLES = frozenset({"solid", "double", "dotted", "dashed", "wavy"})

#: ``border-t`` → ``border-top``: the sides Tailwind spells with one letter.
_BORDER_SIDES: Final = {"": "border", "x": "border-inline", "y": "border-block",
                        "t": "border-top", "r": "border-right", "b": "border-bottom",
                        "l": "border-left", "s": "border-inline-start",
                        "e": "border-inline-end"}
_RADIUS_CORNERS: Final = {
    "": ("border-radius",),
    "t": ("border-top-left-radius", "border-top-right-radius"),
    "r": ("border-bottom-right-radius", "border-top-right-radius"),
    "b": ("border-bottom-left-radius", "border-bottom-right-radius"),
    "l": ("border-bottom-left-radius", "border-top-left-radius"),
    "s": ("border-end-start-radius", "border-start-start-radius"),
    "e": ("border-end-end-radius", "border-start-end-radius"),
    "tl": ("border-top-left-radius",), "tr": ("border-top-right-radius",),
    "br": ("border-bottom-right-radius",), "bl": ("border-bottom-left-radius",),
    "ss": ("border-start-start-radius",), "se": ("border-start-end-radius",),
    "es": ("border-end-start-radius",), "ee": ("border-end-end-radius",),
}

_PLAIN.update({f"rounded-{corner}" if corner else "rounded": props
               for corner, props in _RADIUS_CORNERS.items()})

_Props = tuple[str, ...] | None


def _border(side: str, value: str | None) -> _Props:
    name = _BORDER_SIDES[side]
    if value is None or _is_length(value):
        return (f"{name}-style", f"{name}-width")
    if _is_color(value):
        return (f"{name}-color",)
    return None


def _text(value: str) -> _Props:
    if _TEXT_SIZE.match(value):
        return ("font-size", "line-height")
    if _is_color(value):
        return ("color",)
    if _is_length(value):
        return ("font-size",)
    return None


def _ring(value: str | None) -> _Props:
    if value is None or _is_length(value):
        return ("--tw-ring-shadow", "box-shadow")
    return ("--tw-ring-color",) if _is_color(value) else None


def _ring_offset(value: str) -> _Props:
    if _is_length(value):
        return ("--tw-ring-offset-shadow", "--tw-ring-offset-width")
    return ("--tw-ring-offset-color",) if _is_color(value) else None


def _shadow(value: str | None) -> _Props:
    if value is None or value in _SHADOW_SIZES:
        return ("--tw-shadow", "box-shadow")
    return ("--tw-shadow-color",) if _is_color(value) else None


def _outline(value: str | None) -> _Props:
    if value is None or _is_length(value):
        return ("outline-style", "outline-width")
    return ("outline-color",) if _is_color(value) else None


def _font(value: str) -> _Props:
    if value in _WEIGHTS:
        return ("--tw-font-weight", "font-weight")
    return ("font-family",) if value in _FAMILIES_FONT else None


def _colour_only(prop: str) -> Callable[[str], _Props]:
    return lambda value: (prop,) if _is_color(value) else None


def _fill(value: str) -> _Props:
    return ("fill",) if value == "none" or _is_color(value) else None


def _stroke(value: str) -> _Props:
    if _is_color(value):
        return ("stroke",)
    return ("stroke-width",) if _is_length(value) else None


def _decoration(value: str) -> _Props:
    if value in _DECORATION_STYLES:
        return ("text-decoration-style",)
    if _is_color(value):
        return ("text-decoration-color",)
    return ("text-decoration-thickness",) if _is_length(value) else None


def _scale(value: str) -> _Props:
    if _ARBITRARY.match(value):
        return ("scale",)
    return ("--tw-scale-x", "--tw-scale-y", "--tw-scale-z", "scale")


def _keyword(prop: str, words: frozenset[str]) -> Callable[[str], _Props]:
    return lambda value: (prop,) if value in words else None


def _content(value: str) -> _Props:
    if value in _CONTENT:
        return ("align-content",)
    return ("--tw-content", "content") if _ARBITRARY.match(value) else None


def _flex(value: str) -> _Props:
    return ("flex",) if _ARBITRARY.match(value) or _NUMBER.match(value) else None


def _object(value: str) -> _Props:
    return ("object-fit",) if value in _OBJECT_FIT else ("object-position",)


#: Prefixes whose value decides what they set.
_BY_VALUE: Final[dict[str, Callable[[str], _Props]]] = {
    "text": _text,
    "bg": _colour_only("background-color"),
    "ring": _ring,
    "ring-offset": _ring_offset,
    "shadow": _shadow,
    "outline": _outline,
    "font": _font,
    "fill": _fill,
    "stroke": _stroke,
    "decoration": _decoration,
    "accent": _colour_only("accent-color"),
    "caret": _colour_only("caret-color"),
    "scale": _scale,
    "justify": _keyword("justify-content", _JUSTIFY),
    "content": _content,
    "object": _object,
    "flex": _flex,
    **{f"border-{side}" if side else "border": (lambda v, s=side: _border(s, v))
       for side in _BORDER_SIDES},
}

#: The prefixes valid with no value at all: ``border``, ``rounded-t``,
#: ``shadow``… — read as the table reads them with a value, minus it.
_BARE: Final[dict[str, tuple[str, ...]]] = {
    **{prefix: props for prefix in ("border", *(f"border-{s}" for s in _BORDER_SIDES if s))
       if (props := _BY_VALUE[prefix](None)) is not None},  # type: ignore[arg-type]
    **{prefix: props for prefix, read in (("shadow", _shadow), ("ring", _ring),
                                           ("outline", _outline))
       if (props := read(None)) is not None},
    **{prefix: _PLAIN[prefix] for prefix in _PLAIN
       if prefix.startswith("rounded") or prefix in ("backdrop-blur", "blur")},
}

_ARBITRARY_PROPERTY = re.compile(r"^\[(?P<prop>-{0,2}[a-zA-Z][\w-]*):.+\]$")


def utility_properties(utility: str) -> tuple[str, ...] | None:
    """The CSS properties Tailwind emits for ``utility`` (no variant, no
    ``!``), sorted — or ``None`` when the table does not know it.

    ``None`` is a verdict, not a gap: such a class takes no part in the
    merge, which is what it did before the merge existed.
    """
    arbitrary = _ARBITRARY_PROPERTY.match(utility)
    if arbitrary:
        return (arbitrary["prop"],)
    if utility in _STATIC:
        return _STATIC[utility]
    if utility in _BARE:
        return tuple(sorted(_BARE[utility]))
    bare = utility[1:] if utility.startswith("-") else utility
    # Longest prefix first: ``border-t-text`` is ``border-t`` + ``text``,
    # ``min-w-0`` is ``min-w`` + ``0``. A ``-`` inside brackets or
    # parentheses belongs to the value.
    for cut in reversed(_top_level(bare, "-")):
        prefix, value = bare[:cut], bare[cut + 1:]
        if not value:
            continue
        if prefix in _BY_VALUE:
            props = _BY_VALUE[prefix](value)
            return tuple(sorted(props)) if props else None
        if prefix in _PLAIN:
            return tuple(sorted(_PLAIN[prefix]))
    return None


# ───────────────────────────────────────────────────────────────────────────
# Longhands — how "the app redeclares it" is decided
# ───────────────────────────────────────────────────────────────────────────


def _box(name: str, suffix: str = "") -> dict[str, frozenset[str]]:
    """``padding`` and its sides, each read as the longhands it sets.

    The logical sides (``-inline-start``) are kept apart from the
    physical ones (``-left``): which one is the left depends on the
    writing direction, and a merge must not decide it."""
    def side(s: str) -> str:
        return f"{name}-{s}{suffix}"

    top, right, bottom, left = side("top"), side("right"), side("bottom"), side("left")
    i_start, i_end = side("inline-start"), side("inline-end")
    b_start, b_end = side("block-start"), side("block-end")
    whole = frozenset({top, right, bottom, left, i_start, i_end, b_start, b_end})
    return {
        f"{name}{suffix}": whole,
        side("inline"): frozenset({left, right, i_start, i_end}),
        side("block"): frozenset({top, bottom, b_start, b_end}),
        **{s: frozenset({s}) for s in whole},
    }


_INSET_SIDES: Final = {"top", "right", "bottom", "left", "inset-inline-start",
                       "inset-inline-end", "inset-block-start", "inset-block-end"}

_LONGHANDS: Final[dict[str, frozenset[str]]] = {
    **_box("padding"),
    **_box("margin"),
    **_box("border", "-width"),
    **_box("border", "-style"),
    **_box("border", "-color"),
    "inset": frozenset(_INSET_SIDES),
    "inset-inline": frozenset({"left", "right", "inset-inline-start", "inset-inline-end"}),
    "inset-block": frozenset({"top", "bottom", "inset-block-start", "inset-block-end"}),
    "border-radius": frozenset({
        "border-top-left-radius", "border-top-right-radius", "border-bottom-right-radius",
        "border-bottom-left-radius", "border-start-start-radius", "border-start-end-radius",
        "border-end-start-radius", "border-end-end-radius"}),
    "overflow": frozenset({"overflow-x", "overflow-y"}),
    "flex": frozenset({"flex-grow", "flex-shrink", "flex-basis"}),
    "gap": frozenset({"column-gap", "row-gap"}),
    "grid-column": frozenset({"grid-column-start", "grid-column-end"}),
    "grid-row": frozenset({"grid-row-start", "grid-row-end"}),
}


def longhands(props: tuple[str, ...]) -> frozenset[str]:
    """``props`` with every shorthand read as the longhands it sets."""
    found: set[str] = set()
    for prop in props:
        found |= _LONGHANDS.get(prop, frozenset({prop}))
    return frozenset(found)


# ───────────────────────────────────────────────────────────────────────────
# The merge
# ───────────────────────────────────────────────────────────────────────────


def merge_classes(base: str, addition: str) -> str:
    """``base`` + ``addition``, without what ``addition`` redeclares.

    ``base`` is what the framework composed (the theme's slot, its
    variant, its size, an earlier override); ``addition`` is the app's.
    Every utility of ``base`` whose longhands the utilities of
    ``addition`` redeclare TOGETHER, in the same variant scope, is
    dropped, and so is a token ``addition`` repeats as is (``group``);
    ``addition`` is kept whole and last. Nothing to drop gives
    exactly ``f"{base} {addition}"`` — the HTML of a page with no
    conflict does not change by one byte.

    Uncached and pure: :meth:`bretzel.theme.Theme.merge_classes` is the
    cached door the render goes through.
    """
    if not base:
        return addition
    if not addition:
        return base
    covered: dict[str, set[str]] = {}
    repeated = set(addition.split())
    for token in repeated:
        scope, utility = split_token(token)
        props = utility_properties(utility)
        if props:
            covered.setdefault(scope, set()).update(longhands(props))
    tokens = base.split()
    kept = [token for token in tokens
            if token not in repeated and not (covered and _redeclared(token, covered))]
    if len(kept) == len(tokens):
        return f"{base} {addition}"
    return " ".join([*kept, addition])


def slot_strings(theme: dict, slot: str) -> list[str]:
    """What a component ``theme`` draws ``slot`` with: its template, the
    rows of its variants and sizes for that slot (a row is the root's
    string, or a dict keyed by slot), and the root's modifiers."""
    found = [theme.get("slots", {}).get(slot) or ""]
    for table in ("variants", "sizes"):
        for row in theme.get(table, {}).values():
            entry = row.get(slot) if isinstance(row, dict) else row if slot == "root" else None
            if isinstance(entry, str):
                found.append(entry)
    if slot == "root":
        found.extend(v for v in theme.get("modifiers", {}).values() if isinstance(v, str))
    return found


def _redeclared(token: str, covered: dict[str, set[str]]) -> bool:
    scope, utility = split_token(token)
    within = covered.get(scope)
    if not within:
        return False
    props = utility_properties(utility)
    return props is not None and longhands(props) <= within

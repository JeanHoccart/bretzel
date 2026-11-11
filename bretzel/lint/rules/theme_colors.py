"""Rule: a colour utility names no colour of the theme.

The silence it closes
---------------------

``classes="border-l border-base-300"`` reads like a hairline. ``base-300``
is DaisyUI's vocabulary, not Bretzel's: no ``--color-base-300`` exists, so
Tailwind generates no rule for the class — in dev as in production — and
the border takes ``currentColor``: a black line where a faint one was
meant. Nothing says so: no error, no warning, the class is in the HTML.

What the rule reads
-------------------

The literal tokens of a ``classes=`` (or ``class_=``), variants and ``!``
stripped. A colour utility (``bg-``, ``text-``, ``border-``, ``ring-``,
``divide-``, ``outline-``, ``fill-``, ``stroke-``…) is reported when its
colour is:

- a name with a shade (``-300``) that is no Tailwind family —
  ``base-300``, ``primary-500``: Bretzel's colours have no shades;
- a name with an opacity (``/50``) that is no colour at all —
  ``border-base/10``;
- a ``-content`` name, DaisyUI's foreground (``text-base-content``):
  Bretzel's is ``-foreground``.

The theme's colours (the eleven semantic names, their ``-foreground``),
the palette's (``ui-*``, open: an app may add its own) and Tailwind's own
(``red-500``, ``black``, ``transparent``…) pass.

⚠️ What the rule does NOT read
------------------------------

A bare unknown name without shade or opacity (``bg-brand``): it cannot be
told from a non-colour utility (``text-balance``, ``border-collapse``)
without the compiled sheet. The rule catches the borrowed vocabularies,
which is how the mistake is made.
"""

from __future__ import annotations

import ast
import re

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._app_calls import literal_tokens
from bretzel.theme.tokens import FOREGROUND_SUFFIX, PALETTE_CLASS_PREFIX, SEMANTIC_COLOR_NAMES

RULE = "unknown-theme-color"

_CLASS_KWARGS = frozenset({"classes", "class_"})

#: The utilities whose value is a colour, longest first: ``border-t-``
#: before ``border-``.
_COLOR_PREFIXES = tuple(sorted((
    "bg", "text", "border", "border-x", "border-y", "border-t", "border-r", "border-b",
    "border-l", "border-s", "border-e", "ring", "ring-offset", "inset-ring", "outline",
    "divide", "fill", "stroke", "decoration", "accent", "caret", "placeholder", "from",
    "via", "to", "shadow", "inset-shadow",
), key=len, reverse=True))

#: Tailwind's colour families: with a shade, they exist.
_TAILWIND_FAMILIES = frozenset({
    "slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber", "yellow", "lime",
    "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet", "purple",
    "fuchsia", "pink", "rose", "mauve", "olive", "mist", "taupe",
})

#: The colours that exist without a shade.
_KNOWN = (frozenset(SEMANTIC_COLOR_NAMES)
          | {f"{name}{FOREGROUND_SUFFIX}" for name in SEMANTIC_COLOR_NAMES}
          | {"black", "white", "transparent", "current", "inherit"})

#: What follows a colour prefix without being a colour: ``ring-offset-2``,
#: ``border-spacing-10``, ``bg-linear-to-r``, ``bg-opacity-50``…
_NOT_COLORS = frozenset({
    "offset", "spacing", "opacity", "x", "y", "t", "r", "b", "l", "s", "e", "size",
    "position", "linear", "radial", "conic", "gradient", "origin", "blend", "clip", "inset",
})

_SHAPE = re.compile(
    r"^(?P<name>[a-z]+(?:-[a-z]+)*?)(?:-(?P<shade>\d{2,3}))?"
    r"(?:/(?P<alpha>\d+|\[[^\]]+\]|\([^)]+\)))?$"
)
#: A variant's colon, not one inside an arbitrary value (``[&:hover]``).
_VARIANT = re.compile(r":(?![^\[]*\])")


def unknown_color(token: str) -> str | None:
    """The colour a class token names when no theme has it, else None."""
    utility = _VARIANT.split(token)[-1].strip("!").lstrip("-")
    prefix = next((p for p in _COLOR_PREFIXES if utility.startswith(f"{p}-")), None)
    if prefix is None:
        return None
    found = _SHAPE.match(utility[len(prefix) + 1:])
    if found is None:
        return None
    name, shade, alpha = found["name"], found["shade"], found["alpha"]
    if name.split("-")[0] in _NOT_COLORS or name.startswith(PALETTE_CLASS_PREFIX):
        return None
    if shade:
        return None if name in _TAILWIND_FAMILIES else f"{name}-{shade}"
    if name in _KNOWN or name in _TAILWIND_FAMILIES:
        return None
    if alpha or name.endswith("-content"):
        return name
    return None


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in module.nodes:
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg not in _CLASS_KWARGS:
                continue
            for token in literal_tokens(kw.value):
                color = unknown_color(token)
                if color is None:
                    continue
                findings.append(Finding(
                    rule=RULE,
                    path=module.path,
                    line=kw.value.lineno,
                    message=(f"`{token}`: `{color}` is no colour of the theme — Tailwind "
                             f"generates no rule for it, in dev as in production, and the "
                             f"property falls back to the text colour."),
                    hint=("Bretzel's colours have no shades: `primary`, `text`, `muted`, "
                          "`surface`… with an opacity (`border-text/10` for a hairline), "
                          "their `-foreground`, the palette's `ui-*`, or Tailwind's "
                          "(`slate-300`). `base-*` and `*-content` are DaisyUI's."),
                ))
    return findings

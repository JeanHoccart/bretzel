"""HTML / attribute / JS escaping primitives.

Pure ``str -> str`` transforms with no I/O, no dependencies beyond stdlib.
The only callers expected to bypass these are explicit ``HtmlNode`` escape-hatch
nodes in ``tree.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Final

# ───────────────────────────────────────────────────────────────────────────
# Body / attribute escaping
# ───────────────────────────────────────────────────────────────────────────

# Order matters: ``&`` first to avoid double-encoding.
#
# Do NOT add a "does this string need escaping at all ?" pre-scan in front
# of the loop — measured slower, not faster, on real render values (cf.
# ``traps.md`` § "the `should we escape?` guard is a PESSIMISATION").
_HTML_ESCAPES: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#x27;"),
)


def escape_html(text: str) -> str:
    """Escape a string for use in HTML body content.

    Maps ``< > & " '`` to their entity equivalents. Idempotent **only** in
    the absence of pre-existing entities — applying twice will encode the
    ``&`` of ``&amp;`` again. Callers must not double-escape.
    """
    out = text
    for char, entity in _HTML_ESCAPES:
        out = out.replace(char, entity)
    return out


# The table behind :func:`escape_attr`. It is NO LONGER derived from
# ``_HTML_ESCAPES``: an attribute value and body content do not share the
# same dangerous characters, and conflating them cost 6 bytes per
# apostrophe on pages carrying thousands of them (cf. the note under
# :func:`escape_attr`).
#
# The three control bytes at the tail do not terminate the value but are
# silently folded inside a quoted one, which loses information.
#
# ``'``, ``=`` and the backtick were all three removed from here — same
# reason, measured twice. See :func:`escape_attr`.
_ATTR_ESCAPES: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("\t", "&#x9;"),
    ("\n", "&#xA;"),
    ("\r", "&#xD;"),
)


#: The memo behind :func:`escape_attr`. Measured on 2026-08-27 against the
#: playground: one page calls the function ~4 000 times for ~1 150
#: **distinct** values, and the corpus settles at ~2 400 values for the
#: WHOLE site — so 99 % reuse from one request to the next. An entry weighs
#: the value plus its escaped form; 8 192 entries of ~80 characters fit in
#: ~1.5 MB, a ceiling that is reached and never exceeded.
_ATTR_CACHE_SIZE: Final[int] = 8192


@lru_cache(maxsize=_ATTR_CACHE_SIZE)
def escape_attr(value: str) -> str:
    """Escape a value for a double-quoted HTML attribute."""
    out = value
    for char, entity in _ATTR_ESCAPES:
        out = out.replace(char, entity)
    return out


# ───────────────────────────────────────────────────────────────────────────
# JS string-literal escaping (for ``bz-*`` attributes carrying JS code)
# ───────────────────────────────────────────────────────────────────────────

# Backslash MUST be first so subsequent inserted backslashes are not
# re-escaped. ``</`` is split to defeat naive HTML parsers that close the
# enclosing ``<script>`` early.
_JS_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", "\\\\"),
    ("'", "\\'"),
    ('"', '\\"'),
    ("\n", "\\n"),
    ("\r", "\\r"),
    ("\t", "\\t"),
    ("\b", "\\b"),
    ("\f", "\\f"),
    ("</", "<\\/"),
)


def escape_js(value: str) -> str:
    """Escape a string for inclusion as a JS string literal.

    Targets the ``bz-*`` attribute use case where the runtime evaluates the
    attribute value as a JS expression. After this function the result is
    safe to wrap in single or double quotes inside a JS context.
    """
    out = value
    for char, entity in _JS_ESCAPES:
        out = out.replace(char, entity)
    return out


def escape_inline_json(payload: str) -> str:
    """Defuse ``</`` in a JSON payload embedded inside an HTML tag.

    ``json.dumps`` output is valid JS but a literal ``</bz-envelope>``
    (or any ``</…``) inside a string value would close the host tag
    early during HTML parsing. ``<\\/`` is the standard JSON-safe
    spelling: identical once parsed, inert for the HTML tokenizer.
    Used by :mod:`bretzel.runtime.envelope` for the ``<bz-envelope>``
    and ``<bz-patch>`` payloads.
    """
    return payload.replace("</", "<\\/")


# ───────────────────────────────────────────────────────────────────────────
# Attribute-dict serialization
# ───────────────────────────────────────────────────────────────────────────


class RawAttrValue(str):
    """Marker subclass of ``str`` that bypasses ``escape_attr``.

    Used for attribute values whose content is a JS expression already
    composed by the framework (typically the ``bz-class`` / ``bz-attr:``
    expressions emitted for the client runtime — there is **no** ``bz-bind``
    directive, that name sat here until 2026-08-01). The payload is trusted
    to be syntactically valid for an HTML double-quoted attribute — it
    must not contain literal ``"`` chars or other attribute-breaking
    bytes. The framework controls the call site so this is a safe escape
    hatch; user code never reaches it.
    """

    __slots__ = ()


#: Attributes that name a RESOURCE TO LOAD, and for which an empty value
#: is never an intention — it is a bug.
#:
#: An empty attribute resolves against the document URL: ``<img src="">``
#: re-downloads THE CURRENT PAGE believing it loads an image, and
#: ``<iframe src="">`` puts the page inside itself. Nothing breaks on
#: screen, so it only shows in the server logs — that is how the bug was
#: found on 2026-08-14, on ``ui.video``, by the user.
#:
#: ⚠️ ``href`` and ``action`` are DELIBERATELY absent: ``<a href="">`` and
#: ``<form action="">`` point at the current page, which is a legitimate
#: and common use. The rule only covers *loading* attributes, not
#: navigation ones.
_EMPTY_IS_A_BUG: Final[frozenset[str]] = frozenset(
    {"src", "poster", "srcset", "background", "data", "cite"}
)


def serialize_attrs(attrs: Mapping[str, Any]) -> str:
    """Serialize HTML attributes into a leading-space string."""
    parts: list[str] = []
    for name, value in attrs.items():
        if value is None or value is False:
            continue
        if value == "" and name in _EMPTY_IS_A_BUG:
            continue
        if value is True:
            parts.append(name)
            continue
        if isinstance(value, RawAttrValue):
            parts.append(f'{name}="{value}"')
            continue
        escaped = escape_attr(str(value))
        parts.append(f'{name}="{escaped}"')
    if not parts:
        return ""
    return " " + " ".join(parts)

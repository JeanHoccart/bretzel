"""HTML / attribute / JS escaping primitives.

Pure ``str -> str`` transforms with no I/O, no dependencies beyond stdlib.
The only callers expected to bypass these are explicit ``HtmlNode`` escape-hatch
nodes in ``tree.py``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Final

from bretzel.core import base_path as _base_path

# ───────────────────────────────────────────────────────────────────────────
# Body / attribute escaping
# ───────────────────────────────────────────────────────────────────────────

# Order matters: ``&`` first to avoid double-encoding.
#
# Do NOT add a "does this string need escaping at all ?" pre-scan in front
# of the loop — it is slower, not faster, on real render values.
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


# The table behind :func:`escape_attr`. It is NOT derived from
# ``_HTML_ESCAPES``: an attribute value and body content do not share the
# same dangerous characters, and conflating them would inflate every
# apostrophe on pages carrying thousands of them.
#
# The three control bytes at the tail do not terminate the value but are
# silently folded inside a quoted one, which loses information.
#
# ``'``, ``=`` and the backtick are absent on purpose, for the same
# reason: :func:`escape_attr` serves double-quoted values.
_ATTR_ESCAPES: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("\t", "&#x9;"),
    ("\n", "&#xA;"),
    ("\r", "&#xD;"),
)


#: The memo behind :func:`escape_attr`. A page calls the function far more
#: often than it has **distinct** values, and a site's values settle, so
#: they are reused from one request to the next. An entry weighs the value
#: plus its escaped form; 8 192 entries of ~80 characters fit in ~1.5 MB.
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
    """Make a JSON payload inert as the TEXT of an HTML element.

    ``<bz-envelope>`` and ``<bz-patch>`` are ordinary elements, not
    ``<script>``: the HTML tokenizer reads their content as markup. A
    ``<`` in a string value therefore opens a REAL tag — a ``ClientState``
    field holding ``<img src=x onerror=…>`` would run its script — and an
    ``&amp;`` is decoded by ``textContent`` before ``JSON.parse`` sees it,
    so the data would change on the way.

    ``json.dumps`` escapes none of the three (``json.dumps('<a>')`` is
    ``"<a>"``). ``\\u003c``, ``\\u003e`` and ``\\u0026`` are the JSON
    spellings of the same characters: ``JSON.parse`` gives them back
    unchanged, the tokenizer sees no markup and no entity. They only
    ever occur inside string values — ``json.dumps`` writes none of them
    outside one. Used by :mod:`bretzel.runtime.envelope` and the
    notification patch.
    """
    return payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


# ───────────────────────────────────────────────────────────────────────────
# Attribute-dict serialization
# ───────────────────────────────────────────────────────────────────────────


#: Attributes that name a RESOURCE TO LOAD, and for which an empty value
#: is never an intention — it is a bug.
#:
#: An empty attribute resolves against the document URL: ``<img src="">``
#: re-downloads THE CURRENT PAGE believing it loads an image, and
#: ``<iframe src="">`` puts the page inside itself. Nothing breaks on
#: screen, so it only shows in the server logs.
#:
#: ⚠️ ``href`` and ``action`` are DELIBERATELY absent: ``<a href="">`` and
#: ``<form action="">`` point at the current page, which is a legitimate
#: and common use. The rule only covers *loading* attributes, not
#: navigation ones.
_EMPTY_IS_A_BUG: Final[frozenset[str]] = frozenset(
    {"src", "poster", "srcset", "background", "data", "cite"}
)


#: Attributes whose value is a URL the browser FOLLOWS or LOADS. A
#: ``javascript:`` URL there is script: ``ui.link("Site", href=website)``
#: with a website a user typed would run it on click.
URL_ATTRS: Final[frozenset[str]] = frozenset(
    {"href", "src", "action", "formaction", "xlink:href", "poster", "data",
     "background", "cite"}
)
#: The characters up to the space: browsers drop them from a URL before
#: reading its scheme (``java\tscript:`` is ``javascript:``).
_URL_BLANKS = re.compile(r"[\x00-\x20]")


def is_script_url(value: str) -> bool:
    """``javascript:`` or ``vbscript:``, as the browser reads the scheme.

    Mirrored by ``scriptUrl`` in ``runtime/_src/directives.js``, for a
    URL a ``bz-attr:`` sets in the browser."""
    return _URL_BLANKS.sub("", value).lower().startswith(("javascript:", "vbscript:"))


def serialize_attrs(attrs: Mapping[str, Any]) -> str:
    """Serialize HTML attributes into a leading-space string.

    A URL attribute holding a script URL is left out: an ``<a>`` without
    ``href`` is not a link, the honest rendering of one that must not be
    followed."""
    parts: list[str] = []
    base = _base_path.current()
    for name, value in attrs.items():
        if value is None or value is False:
            continue
        if base and name in _base_path.BASED_ATTRS and isinstance(value, str):
            value = _base_path.with_base(value, base)
        if value == "" and name in _EMPTY_IS_A_BUG:
            continue
        if name in URL_ATTRS and isinstance(value, str) and is_script_url(value):
            continue
        if value is True:
            parts.append(name)
            continue
        escaped = escape_attr(str(value))
        parts.append(f'{name}="{escaped}"')
    if not parts:
        return ""
    return " " + " ".join(parts)

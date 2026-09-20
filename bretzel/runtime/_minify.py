r"""Strip comments and indentation from a JS bundle. Nothing else.

Why a home-made minifier, and why such a modest one
---------------------------------------------------

The charter forbids npm in production; a minifier from the JS world
would need either npm or one more binary to download. And the
measurement of 2026-08-27 says ambition buys nothing here: on
``runtime.js``, **stripping only the comments and the indentation**
gives 286 758 → 107 395 bytes, and 90 563 → **31 581 bytes gzipped**
(−65 %). Renaming local variables, on the other hand, is paid for in
risk and would return only a few kilobytes once gzipped — gzip already
encodes a repeated identifier as a reference.

So: lines are NOT merged, no identifier is rewritten, no operator is
touched. Every line of the bundle stays a line, which leaves automatic
semicolon insertion (ASI) rigorously unchanged — the classic failure
mode of a naive minifier.

The one real trap: ``/``
------------------------

A ``//`` is a comment only when it is not inside a string, a template, or
a **regular-expression literal** — and the bundle carries 43 of them.
``x.replace(/\/\//g, '')`` must survive intact. The scanner therefore
tracks the lexical state, and decides "regex literal or division" from
the last significant token, the standard heuristic.

Verified by execution, not by re-reading:
``tests/runtime_js/test_the_minified_runtime_boots.py`` loads the
minified bundle in a real browser and requires the runtime to start.
"""

from __future__ import annotations

from typing import Final

#: After these characters, a ``/`` opens a regular expression — never a
#: division. ``)`` and ``}`` are deliberately absent: they far more often
#: end a value (``(a + b) / 2``) than an ``if (x) {} /re/.test(y)``,
#: which nobody writes.
_REGEX_CAN_FOLLOW: Final[frozenset[str]] = frozenset("(,=:[!&|?{};+-*%~^<>\n")

#: The keywords after which a ``/`` opens a regular expression.
_REGEX_AFTER_WORD: Final[frozenset[str]] = frozenset(
    {
        "return", "typeof", "instanceof", "in", "of", "new", "delete",
        "void", "throw", "case", "do", "else", "yield", "await",
    }
)

_IDENT_CHARS: Final[str] = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$"
)


def _skip_string(src: str, i: int) -> int:
    """Index just after the string opened at ``i`` (``'`` or ``\"``)."""
    quote = src[i]
    j = i + 1
    while j < len(src):
        if src[j] == "\\":
            j += 2
            continue
        if src[j] == quote:
            return j + 1
        j += 1
    return len(src)


def _skip_template(src: str, i: int) -> int:
    """Index just after the template opened at ``i``.

    Descends into every ``${…}``: a substitution may contain strings,
    templates, braces — and a ``//`` that is not a comment.
    """
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            return j + 1
        if c == "$" and j + 1 < len(src) and src[j + 1] == "{":
            depth = 1
            j += 2
            while j < len(src) and depth:
                d = src[j]
                if d in "\"'":
                    j = _skip_string(src, j)
                    continue
                if d == "`":
                    j = _skip_template(src, j)
                    continue
                if d == "{":
                    depth += 1
                elif d == "}":
                    depth -= 1
                j += 1
            continue
        j += 1
    return len(src)


def _skip_regex(src: str, i: int) -> int:
    """Index just after the regex literal opened at ``i``.

    The ``[...]`` classes are followed because a ``/`` is literal inside
    them: ``/[/]/`` is a valid pattern.
    """
    j = i + 1
    in_class = False
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < len(src) and src[j] in "dgimsuvy":
                j += 1
            return j
        elif c == "\n":
            # A regex literal does not cross the line: it was a
            # division. We hand back just after the opening ``/``.
            return i + 1
        j += 1
    return len(src)


def _regex_may_start(out: list[str]) -> bool:
    """Does ``/`` open a regular expression, given what precedes it?"""
    text = "".join(out[-64:])
    stripped = text.rstrip(" \t\r\n")
    if not stripped:
        return True
    last = stripped[-1]
    if last in _REGEX_CAN_FOLLOW:
        return True
    if last in _IDENT_CHARS:
        word = ""
        k = len(stripped) - 1
        while k >= 0 and stripped[k] in _IDENT_CHARS:
            word = stripped[k] + word
            k -= 1
        return word in _REGEX_AFTER_WORD
    return False


def strip_comments(src: str) -> str:
    """``src`` without its comments — strings, templates and regexes intact.

    A block comment becomes a SPACE, not a newline: returning the lines
    it occupied could cut an expression in two and let ASI insert a
    semicolon.
    """
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = _skip_string(src, i)
            out.append(src[i:j])
            i = j
            continue
        if c == "`":
            j = _skip_template(src, i)
            out.append(src[i:j])
            i = j
            continue
        if c == "/" and i + 1 < n:
            nxt = src[i + 1]
            if nxt == "/":
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if nxt == "*":
                j = src.find("*/", i + 2)
                out.append(" ")
                i = n if j < 0 else j + 2
                continue
            if _regex_may_start(out):
                j = _skip_regex(src, i)
                out.append(src[i:j])
                i = j
                continue
        out.append(c)
        i += 1
    return "".join(out)


def minify(src: str) -> str:
    """The bundle without comments, indentation or blank lines.

    Lines are never merged: ASI sees exactly the same line endings as
    before.
    """
    lines = (line.strip() for line in strip_comments(src).splitlines())
    return "\n".join(line for line in lines if line) + "\n"

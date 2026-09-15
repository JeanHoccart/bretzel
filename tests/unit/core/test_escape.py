"""Unit tests for ``bretzel.core.escape``."""

from __future__ import annotations

import pytest

from bretzel.core.escape import (
    escape_attr,
    escape_html,
    escape_js,
    serialize_attrs,
)

# ───────────────────────────────────────────────────────────────────────────
# escape_html
# ───────────────────────────────────────────────────────────────────────────


class TestEscapeHtml:
    def test_empty(self) -> None:
        assert escape_html("") == ""

    def test_plain_passthrough(self) -> None:
        assert escape_html("hello world") == "hello world"

    def test_lt_gt(self) -> None:
        assert escape_html("<div>") == "&lt;div&gt;"

    def test_ampersand_first(self) -> None:
        # & must be encoded before < / > so we never double-encode.
        assert escape_html("&<") == "&amp;&lt;"

    def test_quotes(self) -> None:
        assert escape_html('"') == "&quot;"
        assert escape_html("'") == "&#x27;"

    def test_full_payload(self) -> None:
        raw = "<script>alert(\"xss\")</script>"
        out = escape_html(raw)
        assert "<" not in out
        assert ">" not in out
        assert '"' not in out

    def test_double_escape_is_not_idempotent(self) -> None:
        # Documented in spec/01-core.md : applying twice re-encodes ``&``.
        once = escape_html("&")
        twice = escape_html(once)
        assert once != twice
        assert twice == "&amp;amp;"


# ───────────────────────────────────────────────────────────────────────────
# escape_attr
# ───────────────────────────────────────────────────────────────────────────


class TestEscapeAttr:
    def test_inherits_html_escapes(self) -> None:
        assert escape_attr("<") == "&lt;"
        assert escape_attr("&") == "&amp;"

    def test_whitespace_control(self) -> None:
        assert escape_attr("a\tb") == "a&#x9;b"
        assert escape_attr("a\nb") == "a&#xA;b"
        assert escape_attr("a\rb") == "a&#xD;b"

    def test_equals_and_backtick_pass_through(self) -> None:
        # Both are inert inside the double quotes ``escape_attr``
        # requires, and both are pervasive in the values Bretzel emits
        # (Tailwind ``data-[open=false]:…``, JS ``===``, query strings).
        # Escaping them cost 6 bytes each for no reachable protection.
        assert escape_attr("a=b") == "a=b"
        assert escape_attr("a`b") == "a`b"
        assert escape_attr("data-[open=false]:hidden") == "data-[open=false]:hidden"

    def test_safe_inside_double_quotes(self) -> None:
        # No raw " can survive — would close the attribute.
        assert '"' not in escape_attr('a"b')

    def test_cannot_break_out_of_a_double_quoted_attribute(self) -> None:
        # The precondition is "caller wraps in DOUBLE quotes". Given
        # that, no input may end the value early or inject an attribute.
        #
        # Single quotes used to work too. They stopped on 2026-08-28 :
        # ``'`` is no longer escaped, because it cost 6 bytes instead of
        # 1 thousands of times per page (every ``bz-*`` expression is
        # made of them). The contract narrowed with it — cf.
        # ``tests/consistency/test_escape_attr_result_is_quoted.py``,
        # which now REFUSES a single-quoted call site at the source.
        payload = "\" onload=alert(1) x='"
        rendered = f'<div title="{escape_attr(payload)}">'
        assert rendered.count('"') == 2

    def test_the_apostrophe_is_left_alone(self) -> None:
        # The saving, stated as a test : a ``bz-*`` expression travels
        # byte-for-byte instead of swelling by 5 bytes per quote.
        assert escape_attr("a ? 'x' : 'y'") == "a ? 'x' : 'y'"


# ───────────────────────────────────────────────────────────────────────────
# escape_js
# ───────────────────────────────────────────────────────────────────────────


class TestEscapeJs:
    def test_backslash_first(self) -> None:
        # Backslash must escape before others inject their own backslashes.
        assert escape_js("\\n") == "\\\\n"

    def test_quotes(self) -> None:
        assert escape_js("'") == "\\'"
        assert escape_js('"') == '\\"'

    def test_newlines(self) -> None:
        assert escape_js("a\nb") == "a\\nb"
        assert escape_js("a\rb") == "a\\rb"

    def test_close_tag_split(self) -> None:
        # </script> in a JS literal would otherwise close the parent tag.
        assert escape_js("</script>") == "<\\/script>"

    def test_other_controls(self) -> None:
        assert escape_js("\t") == "\\t"
        assert escape_js("\b") == "\\b"
        assert escape_js("\f") == "\\f"


# ───────────────────────────────────────────────────────────────────────────
# serialize_attrs
# ───────────────────────────────────────────────────────────────────────────


class TestSerializeAttrs:
    def test_empty(self) -> None:
        assert serialize_attrs({}) == ""

    def test_single_string(self) -> None:
        assert serialize_attrs({"class": "x"}) == ' class="x"'

    def test_multiple_preserves_order(self) -> None:
        # dict is insertion-ordered in CPython 3.7+ — we rely on it.
        out = serialize_attrs({"id": "a", "class": "b"})
        assert out == ' id="a" class="b"'

    def test_true_emits_bare(self) -> None:
        assert serialize_attrs({"disabled": True}) == " disabled"

    def test_false_omits(self) -> None:
        assert serialize_attrs({"disabled": False}) == ""
        assert serialize_attrs({"disabled": False, "class": "x"}) == ' class="x"'

    def test_none_omits(self) -> None:
        assert serialize_attrs({"class": None}) == ""
        assert serialize_attrs({"id": "a", "class": None}) == ' id="a"'

    def test_value_is_escaped(self) -> None:
        # User-controlled string flows through escape_attr.
        out = serialize_attrs({"data-x": '"><script>'})
        assert "<script>" not in out
        assert '"><' not in out

    def test_int_and_float(self) -> None:
        assert serialize_attrs({"tabindex": 0}) == ' tabindex="0"'
        assert serialize_attrs({"step": 0.5}) == ' step="0.5"'

    @pytest.mark.parametrize(
        ("attrs", "expected"),
        [
            ({}, ""),
            ({"a": "1"}, ' a="1"'),
            ({"a": True, "b": False, "c": None, "d": "x"}, ' a d="x"'),
        ],
    )
    def test_table(self, attrs: dict[str, object], expected: str) -> None:
        assert serialize_attrs(attrs) == expected

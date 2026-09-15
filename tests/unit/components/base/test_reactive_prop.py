"""Unit tests for ``bretzel.components.base.reactive_prop``."""

from __future__ import annotations

import pytest

from bretzel.components.base.reactive_prop import (
    ReactivePropDescriptor,
    looks_like_client_expr,
    reactive_prop,
)

# ───────────────────────────────────────────────────────────────────────────
# ReactivePropDescriptor — class + instance access
# ───────────────────────────────────────────────────────────────────────────


class TestDescriptor:
    def test_set_name(self) -> None:
        class C:
            x = reactive_prop(default=0)

        descriptor = C.__dict__["x"]
        assert isinstance(descriptor, ReactivePropDescriptor)
        assert descriptor.name == "x"

    def test_class_access_returns_descriptor(self) -> None:
        class C:
            x = reactive_prop(default=0)

        assert isinstance(C.x, ReactivePropDescriptor)

    def test_instance_default_when_no_storage(self) -> None:
        class C:
            x = reactive_prop(default=42)

        c = C()
        # No ``_reactive_values`` attached → falls back to descriptor default.
        assert c.x == 42

    def test_instance_value_overrides_default(self) -> None:
        class C:
            x = reactive_prop(default=0)

        c = C()
        c._reactive_values = {"x": 99}
        assert c.x == 99

    def test_default_factory(self) -> None:
        class C:
            items = reactive_prop(default_factory=list)

        c = C()
        assert c.items == []

    def test_both_default_and_factory_rejected(self) -> None:
        with pytest.raises(ValueError, match="both"):
            reactive_prop(default=0, default_factory=list)

    def test_no_default_returns_none_via_resolve(self) -> None:
        descriptor = reactive_prop()
        assert descriptor.resolve_default() is None
        assert descriptor.has_default() is False

    def test_repr_mentions_name(self) -> None:
        class C:
            disabled = reactive_prop(default=False)

        assert "disabled" in repr(C.__dict__["disabled"])


# ───────────────────────────────────────────────────────────────────────────
# looks_like_client_expr — heuristic
# ───────────────────────────────────────────────────────────────────────────


class TestLooksLikeAlpine:
    @pytest.mark.parametrize(
        "value",
        [
            "$store.x",
            "$bz.range(state)",
            "$dispatch('change')",
            "active === 1",
            "value !== null",
            "open && ready",
            "a < 1 || b > 0",
            "flag ? 'a' : 'b'",
            "() => x++",
            "$bz.state.cart.default.coupon",
            "foo()",
            "state.toggle()",
        ],
    )
    def test_detects_expressions(self, value: str) -> None:
        assert looks_like_client_expr(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "primary",
            "Hello world",
            "/users/42",
            "btn-solid rounded",
            "abc-xyz",
            "12345",
            # Regression : bare ``?`` in human text used to be classified
            # as Alpine ternary ; the input emitted ``:placeholder=…`` and
            # Alpine choked trying to parse the sentence as JS.
            "What needs to be done ?",
            "Why ? Because.",
            "Question ?",
            # Bare ``=>`` (CSS, arrow-like glyphs) shouldn't trigger.
            "Click =>",
            "a => b in some doc",
            # Regression (mai 2026, Input playground) — lone ``$``
            # and ``$<digit>`` are text (currency / amount prefix),
            # not Alpine.
            "$",
            "$1.50",
            "$5",
            # Regression — text content with parenthesised aside used
            # to match the function-call regex and trigger Alpine.
            "Sign up (free)",
            "Click here (link)",
            "Email (work)",
            # Regression — HTML embedded inside the value used to
            # match function-call detection on the inner ``alert(``.
            # ``<script>alert(1)</script>`` MUST stay literal.
            "<script>alert(1)</script>",
            "<em>highlighted</em>",
            "Hello <world>",
            # Regression (mai 2026, NumberInput playground) —
            # ``--`` collides with EVERY CSS custom property name
            # AND shows up in prose (``"C++ developer"``). The
            # ``--`` / ``++`` markers were removed from the Alpine
            # heuristic for that reason. A placeholder ``"--w:
            # 200px"`` used to emit ``:placeholder="--w: 200px"``
            # → Alpine parse error → page crash.
            "--w: 200px",
            "--bg-color: red",
            "--bz-overlay-z: 100",
            "--ring: 4px",
            "C++ developer",
            "version 2++",
            "padding: --space",
        ],
    )
    def test_treats_literals_as_literals(self, value: str) -> None:
        assert looks_like_client_expr(value) is False

    def test_empty_string_is_not_an_expression(self) -> None:
        assert looks_like_client_expr("") is False

    def test_non_string_is_not_an_expression(self) -> None:
        assert looks_like_client_expr(42) is False  # type: ignore[arg-type]
        assert looks_like_client_expr(None) is False  # type: ignore[arg-type]

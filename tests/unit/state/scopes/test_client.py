"""Unit tests for ``bretzel.state.scopes.client``."""

from __future__ import annotations

import pytest

from bretzel.state.fields.descriptor import field
from bretzel.state.scopes.client import (
    PERSISTS,
    ClientBinding,
    ClientExpression,
    ClientState,
    ReactivityError,
    _to_js,
    rendering_scope,
)

# ───────────────────────────────────────────────────────────────────────────
# Class declaration — persist kwarg
# ───────────────────────────────────────────────────────────────────────────


class TestClassDeclaration:
    def test_default_persist_memory(self) -> None:
        class S(ClientState):
            x: int = field(default=0)

        assert S.__persist__ == "memory"

    @pytest.mark.parametrize("persist", PERSISTS)
    def test_each_persist_accepted(self, persist: str) -> None:
        cls = type(
            f"S_{persist}",
            (ClientState,),
            {"__annotations__": {"x": int}, "x": field(default=0)},
            persist=persist,
        )
        assert cls.__persist__ == persist

    def test_invalid_persist_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid persist"):

            class S(ClientState, persist="cosmic"):  # type: ignore[call-arg]
                x: int = field(default=0)

    def test_page_persist_rejected(self) -> None:
        # "page" was a V2 mode, removed — must now be rejected like any
        # other invalid value.
        with pytest.raises(ValueError, match="Invalid persist"):

            class S(ClientState, persist="page"):  # type: ignore[call-arg]
                x: int = field(default=0)


# ───────────────────────────────────────────────────────────────────────────
# Render-flag-aware attribute access
# ───────────────────────────────────────────────────────────────────────────


class TestAttributeAccess:
    def test_outside_render_returns_raw(self) -> None:
        class S(ClientState):
            x: int = field(default=42)

        s = S()
        # Outside the render scope : raw Python value.
        assert s.x == 42

    def test_inside_render_returns_binding(self) -> None:
        class S(ClientState):
            x: int = field(default=42)

        s = S()
        with rendering_scope():
            value = s.x
        assert isinstance(value, ClientBinding)
        assert value.class_name == "S"
        assert value.instance_key == "default"
        assert value.field_name == "x"
        assert value.value == 42

    def test_binding_carries_custom_key(self) -> None:
        class S(ClientState):
            x: int = field(default=0)

        s = S(key="alpha")
        with rendering_scope():
            b = s.x
        assert isinstance(b, ClientBinding)
        assert b.instance_key == "alpha"

    def test_methods_not_wrapped(self) -> None:
        class S(ClientState):
            x: int = field(default=0)

        s = S()
        with rendering_scope():
            # ``to_dict`` is a method, not a Field — must not become a binding.
            d = s.to_dict()
        assert isinstance(d, dict)

    def test_factory_defaults_resolve_inside_render(self) -> None:
        class S(ClientState):
            items: list[int] = field(default_factory=list)

        s = S()
        with rendering_scope():
            b = s.items
        assert isinstance(b, ClientBinding)
        # Factory was materialised on access — value is a list.
        assert b.value == []


# ───────────────────────────────────────────────────────────────────────────
# Path serialisation
# ───────────────────────────────────────────────────────────────────────────


class TestPaths:
    def _make_binding(self) -> ClientBinding:
        return ClientBinding(
            class_name="FilterState",
            instance_key="default",
            field_name="is_active",
            value=False,
        )

    def test_serialize_path_short_form(self) -> None:
        assert self._make_binding().serialize_path() == (
            "FilterState.default.is_active"
        )

    def test_binding_path_full_form(self) -> None:
        assert self._make_binding().binding_path() == (
            "$bz.state.FilterState.default.is_active"
        )


# ───────────────────────────────────────────────────────────────────────────
# Bool trap
# ───────────────────────────────────────────────────────────────────────────


class TestBoolTrap:
    def test_bool_raises(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=False
        )
        with pytest.raises(ReactivityError, match="boolean context"):
            bool(b)

    def test_if_raises(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=True
        )
        with pytest.raises(ReactivityError):
            if b:
                pass


# ───────────────────────────────────────────────────────────────────────────
# Comparison operators
# ───────────────────────────────────────────────────────────────────────────


class TestComparisons:
    def setup_method(self) -> None:
        self.b = ClientBinding(
            class_name="S",
            instance_key="default",
            field_name="count",
            value=0,
        )

    # Résultat PARENTHÉSÉ — cf. tests/consistency/test_client_expression_atomic.py.

    def test_eq_emits_strict_equal(self) -> None:
        expr = self.b == 5
        assert isinstance(expr, ClientExpression)
        assert expr.binding_path() == "($bz.state.S.default.count === 5)"

    def test_ne(self) -> None:
        assert (self.b != 5).binding_path() == "($bz.state.S.default.count !== 5)"

    def test_lt_le_gt_ge(self) -> None:
        assert (self.b < 5).binding_path() == "($bz.state.S.default.count < 5)"
        assert (self.b <= 5).binding_path() == "($bz.state.S.default.count <= 5)"
        assert (self.b > 5).binding_path() == "($bz.state.S.default.count > 5)"
        assert (self.b >= 5).binding_path() == "($bz.state.S.default.count >= 5)"

    def test_eq_with_string_quoting(self) -> None:
        b_str = ClientBinding(
            class_name="S", instance_key="default", field_name="name", value=""
        )
        expr = b_str == "alice"
        assert expr.binding_path() == '($bz.state.S.default.name === "alice")'


# ───────────────────────────────────────────────────────────────────────────
# Arithmetic operators
# ───────────────────────────────────────────────────────────────────────────


class TestArithmetic:
    def setup_method(self) -> None:
        self.b = ClientBinding(
            class_name="S",
            instance_key="default",
            field_name="n",
            value=0,
        )

    def test_add(self) -> None:
        assert (self.b + 1).binding_path() == "($bz.state.S.default.n + 1)"

    def test_radd(self) -> None:
        assert (1 + self.b).binding_path() == "(1 + $bz.state.S.default.n)"

    def test_sub_mul_div_mod(self) -> None:
        assert (self.b - 1).binding_path() == "($bz.state.S.default.n - 1)"
        assert (self.b * 2).binding_path() == "($bz.state.S.default.n * 2)"
        assert (self.b / 2).binding_path() == "($bz.state.S.default.n / 2)"
        assert (self.b % 3).binding_path() == "($bz.state.S.default.n % 3)"

    def test_floordiv_uses_math_floor(self) -> None:
        # JS has no built-in integer division — emulate via Math.floor.
        assert (self.b // 2).binding_path() == (
            "Math.floor($bz.state.S.default.n / 2)"
        )

    def test_neg_abs_round(self) -> None:
        assert (-self.b).binding_path() == "(-$bz.state.S.default.n)"
        assert abs(self.b).binding_path() == "Math.abs($bz.state.S.default.n)"
        assert round(self.b).binding_path() == "Math.round($bz.state.S.default.n)"
        assert round(self.b, 2).binding_path() == (
            "(Math.round($bz.state.S.default.n * 100) / 100)"
        )


# ───────────────────────────────────────────────────────────────────────────
# Logical operators
# ───────────────────────────────────────────────────────────────────────────


class TestLogical:
    def setup_method(self) -> None:
        self.b = ClientBinding(
            class_name="S",
            instance_key="default",
            field_name="open",
            value=False,
        )

    def test_invert(self) -> None:
        assert (~self.b).binding_path() == "(!$bz.state.S.default.open)"

    def test_invert_of_a_comparison_negates_the_comparison(self) -> None:
        """Régression : ``!$n > 0`` se lit ``(!$n) > 0`` en JS.

        Prouvé sous node avec ``n = -1`` : la forme sans parenthèses rend
        ``false`` là où le sens voulu est ``true``. Divergence silencieuse.
        """
        n = ClientBinding(
            class_name="S", instance_key="default", field_name="n", value=0
        )
        assert (~(n > 0)).binding_path() == "(!($bz.state.S.default.n > 0))"

    def test_and(self) -> None:
        other = ClientBinding(
            class_name="T", instance_key="default", field_name="ready", value=True
        )
        result = self.b & other
        assert result.binding_path() == (
            "($bz.state.S.default.open && $bz.state.T.default.ready)"
        )

    def test_or(self) -> None:
        result = self.b | True
        assert result.binding_path() == "($bz.state.S.default.open || true)"


# ───────────────────────────────────────────────────────────────────────────
# Named accessors
# ───────────────────────────────────────────────────────────────────────────


class TestNamedAccessors:
    def test_eq_alias(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=0
        )
        assert b.eq(5).binding_path() == (b == 5).binding_path()

    def test_between(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=0
        )
        expr = b.between(0, 100)
        assert expr.binding_path() == (
            "($bz.state.S.default.x >= 0 && $bz.state.S.default.x <= 100)"
        )

    def test_length(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="items", value=[]
        )
        assert b.length().binding_path() == "$bz.state.S.default.items.length"

    def test_contains(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="tags", value=[]
        )
        assert b.contains("foo").binding_path() == (
            '$bz.state.S.default.tags.includes("foo")'
        )

    def test_not_alias(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="open", value=False
        )
        assert b.not_().binding_path() == (~b).binding_path()

    def test_then_else_ternary(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="count", value=0
        )
        expr = (b > 0).then_else("In cart", "Empty")
        assert expr.binding_path() == (
            '(($bz.state.S.default.count > 0) ? "In cart" : "Empty")'
        )

    def test_to_fixed(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="price", value=0
        )
        assert b.to_fixed(2).binding_path() == (
            "Number($bz.state.S.default.price).toFixed(2)"
        )


# ───────────────────────────────────────────────────────────────────────────
# Mutation helpers
# ───────────────────────────────────────────────────────────────────────────


class TestMutationHelpers:
    def setup_method(self) -> None:
        self.b = ClientBinding(
            class_name="S",
            instance_key="default",
            field_name="x",
            value=0,
        )

    def test_toggle(self) -> None:
        assert self.b.toggle() == (
            "$bz.state.S.default.x = !$bz.state.S.default.x"
        )

    def test_increment_default(self) -> None:
        assert self.b.increment() == "$bz.state.S.default.x += 1"

    def test_increment_by(self) -> None:
        assert self.b.increment(5) == "$bz.state.S.default.x += 5"

    def test_decrement(self) -> None:
        assert self.b.decrement() == "$bz.state.S.default.x -= 1"

    def test_set_int(self) -> None:
        assert self.b.set(10) == "$bz.state.S.default.x = 10"

    def test_set_string_quotes(self) -> None:
        assert self.b.set("hello") == '$bz.state.S.default.x = "hello"'

    def test_push(self) -> None:
        # Reassign with a fresh array (NOT in-place ``.push()``) — V3
        # signals are identity-compared, so a mutation would never fire.
        assert self.b.push(42) == (
            "$bz.state.S.default.x = [...($bz.state.S.default.x || []), 42]"
        )

    def test_clear(self) -> None:
        assert self.b.clear() == "$bz.state.S.default.x = []"


# ───────────────────────────────────────────────────────────────────────────
# ClientExpression — composability
# ───────────────────────────────────────────────────────────────────────────


class TestClientExpression:
    def test_constructed_from_binding(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=0
        )
        expr = b == 5
        assert isinstance(expr, ClientExpression)
        assert isinstance(expr, ClientBinding)  # subclass

    def test_chained_operators(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=0
        )
        expr = (b > 0) & (b < 10)
        # Combine two ClientExpressions via &. Chaque comparaison porte
        # ses propres parenthèses (atomicité), le `&&` ajoute les siennes.
        assert expr.binding_path() == (
            "(($bz.state.S.default.x > 0) && ($bz.state.S.default.x < 10))"
        )

    def test_bool_trap_inherited(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=0
        )
        expr = b == 5
        with pytest.raises(ReactivityError):
            bool(expr)


# ───────────────────────────────────────────────────────────────────────────
# _to_js — JS literal conversion
# ───────────────────────────────────────────────────────────────────────────


class TestToJs:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, "null"),
            (True, "true"),
            (False, "false"),
            (42, "42"),
            (3.14, "3.14"),
            ("hello", '"hello"'),
            ([1, 2, 3], "[1, 2, 3]"),
            ({"a": 1}, '{"a": 1}'),
        ],
    )
    def test_primitives(self, value: object, expected: str) -> None:
        assert _to_js(value) == expected

    def test_string_with_quotes_escaped(self) -> None:
        # JSON encoding handles escaping properly.
        assert _to_js('say "hi"') == '"say \\"hi\\""'

    def test_binding_inlined(self) -> None:
        b = ClientBinding(
            class_name="S", instance_key="default", field_name="x", value=0
        )
        assert _to_js(b) == "$bz.state.S.default.x"

    def test_unsupported_type_raises(self) -> None:
        class Custom:
            pass

        with pytest.raises(TypeError):
            _to_js(Custom())

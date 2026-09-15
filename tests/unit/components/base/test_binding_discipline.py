"""Unit tests for the declared-type capture on reactive_prop descriptors."""

from __future__ import annotations

from bretzel.components.base import Component, reactive_prop


class _DummyComp(Component):
    THEME = {}
    THEME_KEY = "dummy"
    DEFAULT_TAG = "div"

    label: str = reactive_prop(default="")
    count: int = reactive_prop(default=0)
    flag: bool = reactive_prop(default=False)


class TestDeclaredType:
    def test_str_annotation_captured(self) -> None:
        desc = _DummyComp.__reactive_props__["label"]
        assert desc.declared_type is str

    def test_int_annotation_captured(self) -> None:
        desc = _DummyComp.__reactive_props__["count"]
        assert desc.declared_type is int

    def test_bool_annotation_captured(self) -> None:
        desc = _DummyComp.__reactive_props__["flag"]
        assert desc.declared_type is bool


from bretzel.components.base.binding_discipline import (
    is_scalar_type,
    validate_scalar_binding,
)
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.state.scopes.client import ClientBinding


class TestIsScalarType:
    def test_str_int_float_bool_are_scalar(self) -> None:
        assert is_scalar_type(str)
        assert is_scalar_type(int)
        assert is_scalar_type(float)
        assert is_scalar_type(bool)

    def test_none_type_is_scalar(self) -> None:
        assert is_scalar_type(type(None))

    def test_list_dict_tuple_are_not_scalar(self) -> None:
        assert not is_scalar_type(list)
        assert not is_scalar_type(dict)
        assert not is_scalar_type(tuple)
        assert not is_scalar_type(set)

    def test_optional_str_is_scalar(self) -> None:
        # ``str | None`` (PEP 604) and ``Optional[str]`` both unwrap.
        assert is_scalar_type(str | None)

    def test_string_annotation_is_not_scalar(self) -> None:
        # When the metaclass's get_type_hints fallback leaves a raw
        # string annotation on declared_type, discipline must NOT
        # treat it as scalar — better silent permissive than silent
        # bypass of a real mismatch.
        assert not is_scalar_type("str")
        assert not is_scalar_type("list[int]")

    def test_list_generic_is_not_scalar(self) -> None:
        assert not is_scalar_type(list[int])
        assert not is_scalar_type(dict[str, int])


class TestValidateScalarBinding:
    def _make(self, value):
        return ClientBinding(
            class_name="Foo", instance_key="default",
            field_name="bar", value=value,
        )

    def test_scalar_binding_against_str_prop_ok(self) -> None:
        # No raise.
        validate_scalar_binding(
            "label", declared_type=str,
            binding=self._make("hi"), owner="Button",
        )

    def test_list_binding_against_scalar_prop_raises(self) -> None:
        try:
            validate_scalar_binding(
                "label", declared_type=str,
                binding=self._make(["a", "b"]),
                owner="Button",
            )
        except ComponentUsageError as err:
            assert "Button" in str(err)
            assert "label" in str(err)
            assert "list" in str(err)
            return
        raise AssertionError("ComponentUsageError not raised")

    def test_none_declared_type_skips_check(self) -> None:
        # Permissive when annotation is missing — no raise even for list.
        validate_scalar_binding(
            "label", declared_type=None,
            binding=self._make(["a"]), owner="Button",
        )

    def test_string_declared_type_skips_check(self) -> None:
        # When the metaclass fallback left a string on declared_type,
        # we cannot reliably validate — degrade to permissive.
        validate_scalar_binding(
            "label", declared_type="str",
            binding=self._make(["a"]), owner="Button",
        )

    def test_non_scalar_declared_type_skips_check(self) -> None:
        # ``list[int]`` declared : passing a list binding is fine
        # (it's a collection prop, discipline is N/A here).
        validate_scalar_binding(
            "items", declared_type=list[int],
            binding=self._make([1, 2]), owner="DataTable",
        )


import pytest
from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class _MisuseState(ClientState, persist="memory"):
    tags: list = field(default_factory=list)
    flag: bool = field(default=False)


class TestDisciplineIntegration:
    """Use ``disabled`` (a Button BINDABLE_PROPS reactive_prop) to
    exercise the scalar-vs-list discipline check on a real component
    surface. ``disabled`` is declared ``bool`` ; binding a list[*]
    must raise loudly (the discipline layer is orthogonal to
    BINDABLE_PROPS and validates type shape).
    """

    def test_list_binding_on_scalar_disabled_raises(self) -> None:
        with render_isolated(), rendering_scope():
            state = _MisuseState()
            with pytest.raises(ComponentUsageError, match="Button.disabled"):
                Button("hi", disabled=state.tags)

    def test_scalar_binding_on_scalar_disabled_ok(self) -> None:
        # ``flag`` field is annotated ``bool`` in _MisuseState.
        with render_isolated(), rendering_scope():
            state = _MisuseState()
            btn = Button("hi", disabled=state.flag)
            assert btn is not None

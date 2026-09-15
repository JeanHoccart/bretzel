"""Regression suite for two-way binding via ``bz-model`` (V3).

The bug we're guarding against : every form-bound component used to
read its binding from ``self._reactive_values[<prop>]`` and check
``isinstance(..., ClientBinding)`` — but the metaclass split stores
the binding's underlying SSR value there, not the binding object,
so the isinstance check is always False and the two-way directive
was never emitted. Live two-way binding silently fell back to a
read-only ``bz-attr:<prop>`` directive.

The fix routes every form-bound component through
:py:meth:`Component._bind_x_model` (name kept from V2 ; emits the V3
``bz-model``), which reads the canonical ``self._binding_metadata``
dict instead.

This module asserts the contract end-to-end on the rendered HTML :

- a ClientBinding produces ``bz-model="$bz.state.<path>"``
- the read-only ``bz-attr:<prop>`` is dropped from the real control
- autoname derives the HTML ``name`` attribute from the binding's
  field name (for components that opt in via ``AUTONAME_FROM``)

Adding a new form-bound component ? Append it to the list below ;
the parametrised tests will catch the regression for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.checkbox import Checkbox
from bretzel.components.inputs.input import Input
from bretzel.components.inputs.radio import Radio, RadioGroup
from bretzel.components.inputs.switch import Switch
from bretzel.components.inputs.textarea import Textarea
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


@dataclass(frozen=True)
class _Case:
    """One form-bound component under test."""

    label: str
    # Build the component bound to ``binding``. Kept as a closure so
    # composite cases (Radio inside RadioGroup) can stage the parent.
    build: Callable[[ClientBinding], Any]
    # The binding's serialized path that should appear in x-model.
    expected_path: str = "draft.default.field"
    # Field name autoname should derive (None = component opts out).
    expected_name: str | None = "field"


def _binding() -> ClientBinding:
    return ClientBinding(
        class_name="draft",
        instance_key="default",
        field_name="field",
        value="",
    )


CASES: list[_Case] = [
    _Case(
        label="input",
        build=lambda b: Input(value=b),
    ),
    _Case(
        label="textarea",
        build=lambda b: Textarea(value=b),
    ),
    _Case(
        label="checkbox",
        build=lambda b: Checkbox(checked=b),
    ),
    _Case(
        label="switch",
        build=lambda b: Switch(checked=b),
    ),
    # Radio inherits the binding from its enclosing RadioGroup ;
    # autoname is delegated to the group, the radio itself takes the
    # group's ``name`` at render time. Pre-build via a helper that
    # spins up the group and adopts a single child.
    _Case(
        label="radio",
        build=lambda b: _build_radio_in_group(b),
        # Autoname is on the GROUP root ; the radio's <input> picks
        # up ``name`` from the group via render-time inheritance, but
        # only if the group derived one. Asserted separately below.
        expected_name="field",
    ),
]


def _build_radio_in_group(binding: ClientBinding) -> RadioGroup:
    """Build ``RadioGroup(value=binding)`` containing one Radio so the
    rendered output carries the radio's ``<input>`` with x-model."""
    with RadioGroup(value=binding) as group:
        Radio("a", label="A")
    return group


def _iter_open_tags(html: str, tag: str) -> list[str]:
    """Yield each opening-tag fragment for ``tag`` (e.g. ``"<input"``).

    Returns the substring from the opening ``<input`` up to the next
    ``>``, exclusive — exactly what we want to scan for stray
    directives on the element itself, ignoring siblings/wrappers.
    """
    fragments: list[str] = []
    cursor = 0
    while True:
        start = html.find(tag, cursor)
        if start == -1:
            return fragments
        end = html.find(">", start)
        if end == -1:
            return fragments
        fragments.append(html[start:end])
        cursor = end + 1


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.label)
class TestBindingProducesXModel:
    def test_bz_model_present(self, case: _Case) -> None:
        with render_isolated():
            comp = case.build(_binding())
            out = serialize(comp.render())
        assert f'bz-model="$bz.state.{case.expected_path}"' in out, out

    def test_no_read_only_bz_attr_on_real_input(self, case: _Case) -> None:
        # The read-only directive must be dropped from the actual
        # ``<input>`` / ``<textarea>`` — emitting both would race
        # (the runtime binds twice) and the read-only one would block
        # writes from the user's keystrokes back into state.
        #
        # We scope this assertion to the input element itself, not
        # the surrounding wrapper : RadioGroup carries the binding
        # at the cluster level (so its root <div> still gets a
        # read-only ``bz-attr:value`` for the universal contract),
        # but each child <input> must not.
        with render_isolated():
            comp = case.build(_binding())
            out = serialize(comp.render())
        for tag in ("<input", "<textarea"):
            for fragment in _iter_open_tags(out, tag):
                assert "bz-attr:value" not in fragment, fragment
                assert "bz-attr:checked" not in fragment, fragment

    def test_autoname_from_binding(self, case: _Case) -> None:
        if case.expected_name is None:
            pytest.skip("component opts out of autoname")
        with render_isolated():
            comp = case.build(_binding())
            out = serialize(comp.render())
        assert f'name="{case.expected_name}"' in out, out


class TestLiteralValueFallback:
    """When no binding is passed, components must NOT emit x-model and
    must keep their literal-value rendering intact."""

    def test_input_literal_value(self) -> None:
        with render_isolated():
            out = serialize(Input(value="hello").render())
        assert "bz-model" not in out
        assert 'value="hello"' in out

    def test_textarea_literal_value_in_text_content(self) -> None:
        with render_isolated():
            out = serialize(Textarea(value="hello").render())
        assert "bz-model" not in out
        # Textarea literal value lives as text content, not as attr.
        assert 'value="hello"' not in out
        assert ">hello<" in out

    def test_checkbox_literal_true(self) -> None:
        with render_isolated():
            out = serialize(Checkbox(checked=True).render())
        assert "bz-model" not in out
        assert "checked" in out

    def test_checkbox_literal_false_emits_no_checked(self) -> None:
        with render_isolated():
            out = serialize(Checkbox(checked=False).render())
        assert "bz-model" not in out
        # No bare ``checked`` attribute when the literal is False.
        assert "checked=" not in out
        assert ' checked ' not in out
        assert ' checked>' not in out

    def test_switch_literal_true(self) -> None:
        with render_isolated():
            out = serialize(Switch(checked=True).render())
        assert "bz-model" not in out
        assert "checked" in out

    def test_radio_static_match_emits_checked(self) -> None:
        # Group has a literal value, child radio whose option matches
        # ships ``checked``. No x-model since no binding.
        with render_isolated():
            with RadioGroup(value="b") as group:
                Radio("a", label="A")
                Radio("b", label="B")
            out = serialize(group.render())
        assert "bz-model" not in out
        assert "checked" in out


class TestProgressReactiveExpression:
    """Progress is family C (custom reactive expression, not bz-model).
    Binding still must drive the live ``bz-attr:style`` width and
    ``bz-text`` label expressions ; absence of binding falls back to a
    static width/percent."""

    def test_binding_drives_style_expression(self) -> None:
        from bretzel.components.feedback.progress import Progress

        binding = ClientBinding(
            class_name="job",
            instance_key="default",
            field_name="pct",
            value=0,
        )
        with render_isolated():
            out = serialize(Progress(value=binding, max=100).render())
        # The fill div carries a bz-attr:style directive that reads
        # the live state value.
        assert "bz-attr:style" in out
        assert "$bz.state.job.default.pct" in out
        # SSR fallback width is 0.0% since the binding starts at 0.
        assert "width: 0.0%" in out

    def test_binding_drives_label_expression(self) -> None:
        from bretzel.components.feedback.progress import Progress

        binding = ClientBinding(
            class_name="job",
            instance_key="default",
            field_name="pct",
            value=42,
        )
        with render_isolated():
            out = serialize(
                Progress(value=binding, max=100, show_label=True).render()
            )
        # bz-text drives the label live ; SSR stamps the initial text.
        assert "bz-text" in out
        assert "$bz.state.job.default.pct" in out

    def test_literal_value_static_width(self) -> None:
        from bretzel.components.feedback.progress import Progress

        with render_isolated():
            out = serialize(Progress(value=50, max=100).render())
        # No reactive expression — just a static width.
        assert "bz-attr:style" not in out
        assert "width: 50.0%" in out
        assert 'aria-valuenow="50"' in out


class TestNativePickerTypesBlocked:
    """Input rejects HTML5 types that ship a native browser popup.
    Each kind has its own dedicated Bretzel component instead."""

    def test_date_type_raises(self) -> None:
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated
        from bretzel.components.inputs.input import Input
        import pytest

        with render_isolated(), pytest.raises(
            ComponentUsageError, match="ui.date_picker"
        ):
            Input(type="date")

    def test_time_type_raises(self) -> None:
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated
        from bretzel.components.inputs.input import Input
        import pytest

        with render_isolated(), pytest.raises(
            ComponentUsageError, match="ui.time_picker"
        ):
            Input(type="time")

    def test_color_type_raises(self) -> None:
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated
        from bretzel.components.inputs.input import Input
        import pytest

        with render_isolated(), pytest.raises(
            ComponentUsageError, match="ui.color_picker"
        ):
            Input(type="color")

    def test_file_type_raises(self) -> None:
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated
        from bretzel.components.inputs.input import Input
        import pytest

        with render_isolated(), pytest.raises(
            ComponentUsageError, match="ui.file_upload"
        ):
            Input(type="file")

    def test_arbitrary_unknown_type_raises(self) -> None:
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated
        from bretzel.components.inputs.input import Input
        import pytest

        with render_isolated(), pytest.raises(
            ComponentUsageError, match="Allowed"
        ):
            Input(type="foobar")

    def test_text_email_password_accepted(self) -> None:
        from bretzel.components.base.testing import render_isolated
        from bretzel.components.inputs.input import Input

        # Should NOT raise. ``type="number"`` removed from this list
        # in mai 2026 — ``ui.number_input`` ships a dedicated
        # component with proper steppers / clamp / precision. Input
        # raises ComponentUsageError for ``type="number"`` now,
        # pointing to the right helper. See _NATIVE_PICKER_TYPES in
        # ``bretzel/components/inputs/input/input.py``.
        with render_isolated():
            Input(type="text")
            Input(type="email")
            Input(type="password")
            Input(type="tel")
            Input(type="url")
            Input(type="search")

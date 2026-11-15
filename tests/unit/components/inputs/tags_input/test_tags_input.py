"""Unit tests for :class:`bretzel.components.inputs.tags_input.TagsInput`."""

from __future__ import annotations

import html
import json

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.tags_input import TagsInput
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding

CONTACTS = [("s@x.fr", "Sophie"), ("t@x.fr", "Thomas")]


def _html(**kwargs) -> str:
    with render_isolated():
        return html.unescape(serialize(TagsInput(CONTACTS, **kwargs).render()))


def _change(value: str = "") -> None:
    pass


def _search(query: str = "") -> None:
    pass


class TestStructure:
    def test_the_input_is_a_combobox_over_the_suggestions(self) -> None:
        out = _html()
        assert 'role="combobox"' in out
        assert 'role="listbox"' in out
        assert 'aria-autocomplete="list"' in out
        panel_id = out.split('aria-controls="')[1].split('"')[0]
        assert f'id="{panel_id}"' in out

    def test_one_suggestion_per_option(self) -> None:
        out = _html()
        assert out.count('role="option"') == 2
        assert 'data-bz-value="s@x.fr"' in out

    def test_the_tags_are_a_list_cloned_from_the_value(self) -> None:
        out = _html(value=["s@x.fr"])
        assert 'role="list"' in out
        assert 'bz-for="v in _picked() :key=v"' in out
        assert 'role="listitem"' in out

    def test_a_tag_knows_its_label_from_the_options(self) -> None:
        # Config (re-seeded), copied by the browser into its own memory at
        # mount: ``_labels`` itself is never seeded, a search would wipe it.
        out = _html(value=["s@x.fr", "z@y.fr"])
        assert '_known: {"s@x.fr": "Sophie"}' in out
        assert "_labels: {}" in out

    def test_pattern_travels_as_config(self) -> None:
        out = _html(pattern=r"[^@]+@[^@]+")
        assert '_pattern: "[^@]+@[^@]+"' in out
        assert "_pattern: null" in _html()

    def test_a_live_region_says_what_changed(self) -> None:
        assert 'aria-live="polite"' in _html()

    def test_render_draws_the_suggestion_body(self) -> None:
        from bretzel import ui

        def row(value, label):
            return ui.badge(label)

        with render_isolated():
            plain = serialize(TagsInput(CONTACTS).render())
            drawn = serialize(TagsInput(CONTACTS, render=row).render())
        assert drawn != plain and "Sophie" in drawn


class TestValue:
    def test_local_value_is_a_list(self) -> None:
        assert 'value: ["s@x.fr"]' in _html(value=["s@x.fr"])

    def test_a_scalar_value_becomes_one_tag(self) -> None:
        assert 'value: ["s@x.fr"]' in _html(value="s@x.fr")

    def test_a_name_carries_the_value_as_json(self) -> None:
        out = serialize_raw(value=["s@x.fr"], name="to")
        assert 'name="to"' in out
        assert 'value="[&quot;s@x.fr&quot;]"' in out

    def test_binding_reads_and_writes_the_store(self) -> None:
        binding = ClientBinding(class_name="Mail", instance_key="default",
                                field_name="to", value=["s@x.fr"])
        out = _html(value=binding)
        assert "$bz.state.Mail.default.to" in out
        assert 'value: ["s@x.fr"]' not in out

    def test_binding_on_a_non_bindable_prop_raises(self) -> None:
        binding = ClientBinding(class_name="Mail", instance_key="default",
                                field_name="p", value="x")
        with render_isolated(), pytest.raises(ComponentUsageError):
            TagsInput(CONTACTS, pattern=binding)


def serialize_raw(**kwargs) -> str:
    with render_isolated():
        return serialize(TagsInput(CONTACTS, **kwargs).render())


class TestEvents:
    def test_change_rides_the_hidden_input(self) -> None:
        out = _html(on_change=_change)
        hidden = out[out.index('bz-ref="bzhidden"'):out.index('bz-ref="bztrigger"')]
        assert "hx-post" in hidden

    def test_search_waits_for_a_pause_and_carries_the_query(self) -> None:
        out = _html(on_search=_search)
        assert 'hx-trigger="input changed delay:200ms"' in out
        assert 'name="query"' in out


class TestCommands:
    def test_every_command_is_a_client_expression(self) -> None:
        with render_isolated():
            t = TagsInput(CONTACTS)
            for expr in (t.set(["a"]), t.clear(), t.add("a; b"), t.focus(), t.blur()):
                assert isinstance(expr, str) and expr

    def test_add_dispatches_its_value(self) -> None:
        with render_isolated():
            expr = TagsInput(CONTACTS).add("a@b.fr")
        assert "bz-add" in expr and json.dumps("a@b.fr") in html.unescape(expr)


class TestSizes:
    @pytest.mark.parametrize("pair", [("xs", "md"), ("md", "xl")])
    def test_two_sizes_render_differently(self, pair) -> None:
        assert _html(size=pair[0]) != _html(size=pair[1])

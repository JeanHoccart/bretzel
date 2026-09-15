"""Unit tests for :class:`bretzel.components.inputs.radio` —
``Radio`` + ``RadioGroup``."""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.radio import Radio, RadioGroup
from bretzel.core.serialize import serialize


class TestGroupStructure:
    def test_role_radiogroup(self) -> None:
        with render_isolated():
            with RadioGroup() as rg:
                Radio("a", label="A")
            out = serialize(rg.render())
        assert 'role="radiogroup"' in out

    def test_aria_required_when_required(self) -> None:
        with render_isolated():
            with RadioGroup(required=True) as rg:
                Radio("a", label="A")
            out = serialize(rg.render())
        assert 'aria-required="true"' in out

    @pytest.mark.parametrize(
        ("direction", "klass"),
        [("col", "flex-col"), ("row", "flex-row")],
    )
    def test_direction_class(self, direction: str, klass: str) -> None:
        with render_isolated():
            with RadioGroup(direction=direction) as rg:
                Radio("a", label="A")
            assert klass in serialize(rg.render())

    def test_renders_one_input_per_radio(self) -> None:
        with render_isolated():
            with RadioGroup(name="plan") as rg:
                Radio("free", label="Free")
                Radio("pro", label="Pro")
                Radio("enterprise", label="Enterprise")
            out = serialize(rg.render())
        assert out.count("<input") == 3


class TestRadioInheritance:
    """Radio inherits ``name`` / ``value`` (binding) / ``color`` /
    ``size`` from the enclosing ``RadioGroup`` captured at construction
    time."""

    def test_radio_inherits_name_from_group(self) -> None:
        with render_isolated():
            with RadioGroup(name="plan") as rg:
                Radio("free", label="Free")
                Radio("pro", label="Pro")
            out = serialize(rg.render())
        assert out.count('name="plan"') == 2

    def test_checked_when_value_matches_option(self) -> None:
        with render_isolated():
            with RadioGroup(name="plan", value="pro") as rg:
                Radio("free", label="Free")
                Radio("pro", label="Pro")
            out = serialize(rg.render())
        inputs = re.findall(r"<input[^>]+>", out)
        assert len(inputs) == 2
        # First (free) is unchecked, second (pro) is checked.
        assert "checked" not in inputs[0]
        assert "checked" in inputs[1]

    def test_no_checked_when_value_unset(self) -> None:
        with render_isolated():
            with RadioGroup(name="plan") as rg:
                Radio("free", label="Free")
                Radio("pro", label="Pro")
            out = serialize(rg.render())
        for m in re.findall(r"<input[^>]+>", out):
            assert "checked" not in m


class TestRadioVisual:
    def test_input_is_peer_sronly(self) -> None:
        # V1 idiom : real input visually hidden, fake circle/dot
        # listens to its checked state via Tailwind ``peer-*`` classes.
        with render_isolated():
            with RadioGroup() as rg:
                Radio("a", label="A")
            out = serialize(rg.render())
        assert "peer sr-only" in out

    def test_circle_and_dot_present(self) -> None:
        with render_isolated():
            with RadioGroup() as rg:
                Radio("a", label="A")
            out = serialize(rg.render())
        # Two divs after the input : circle then dot.
        assert "rounded-full" in out
        assert "peer-checked:opacity-100" in out
        assert "peer-checked:border-" in out

    def test_label_text_rendered(self) -> None:
        with render_isolated():
            with RadioGroup() as rg:
                Radio("a", label="Free plan")
            assert ">Free plan<" in serialize(rg.render())

    def test_label_omitted_when_no_label_kwarg(self) -> None:
        with render_isolated():
            with RadioGroup() as rg:
                Radio("a")
            out = serialize(rg.render())
        # No <span> child for the label text.
        assert "<span" not in out


class TestRadioStandalone:
    """A ``Radio`` outside a ``RadioGroup`` still renders ; it just
    won't inherit anything."""

    def test_standalone_radio_renders(self) -> None:
        with render_isolated():
            r = Radio("solo", label="Solo")
            out = serialize(r.render())
        assert "<input" in out
        assert 'value="solo"' in out
        # No ``name`` since there's no group to inherit from and the
        # caller didn't pass one explicitly.
        assert "name=" not in out

    def test_standalone_radio_with_explicit_name(self) -> None:
        with render_isolated():
            r = Radio("solo", name="x", label="Solo")
            assert 'name="x"' in serialize(r.render())


class TestRadioDisabledPropagation:
    """``disabled`` on the group propagates to every child ``<input>``
    because native HTML has no "disable a radio group" — the only way
    to lock the cluster is to stamp ``disabled`` on each radio input.

    Three paths covered :
    - Per-item literal ``disabled=True`` works as expected.
    - Group literal ``disabled=True`` forces every child locked.
    - Group ``ClientBinding`` propagates reactively to each child via
      ``bz-attr:disabled`` so the runtime flips the cluster in
      lockstep (V3 : falsy → removeAttribute, truthy → attr set).
    """

    _DISABLED_ATTR_RE = re.compile(r'<input[^>]*\sdisabled[\s/>]')

    def test_per_item_disabled_locks_only_that_radio(self) -> None:
        with render_isolated():
            with RadioGroup(name="g") as rg:
                Radio("a", label="A")
                Radio("b", label="B (locked)", disabled=True)
                Radio("c", label="C")
            out = serialize(rg.render())
        assert len(self._DISABLED_ATTR_RE.findall(out)) == 1

    def test_group_literal_disabled_locks_every_child(self) -> None:
        with render_isolated():
            with RadioGroup(name="g", disabled=True) as rg:
                Radio("a", label="A")
                Radio("b", label="B")
                Radio("c", label="C")
            out = serialize(rg.render())
        assert len(self._DISABLED_ATTR_RE.findall(out)) == 3

    def test_group_binding_disabled_propagates_to_every_child(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _C(ClientState, persist="memory"):
            locked: bool = field(default=False)

        with render_isolated(), rendering_scope():
            c = _C()
            with RadioGroup(name="g", disabled=c.locked) as rg:
                Radio("a", label="A")
                Radio("b", label="B")
            out = serialize(rg.render())

        # Every <input type="radio"> carries the reactive directive
        # (V3 : full ``$bz.state.<path>`` expression, falsy →
        # removeAttribute).
        directive = 'bz-attr:disabled="$bz.state._C.default.locked"'
        assert out.count(directive) == 2
        # No literal ``disabled`` SSR-stamp since the bound value is False.
        assert self._DISABLED_ATTR_RE.search(out) is None

    def test_group_binding_ssr_stamps_literal_when_value_truthy(
        self,
    ) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _D(ClientState, persist="memory"):
            locked: bool = field(default=True)

        with render_isolated(), rendering_scope():
            c = _D()
            with RadioGroup(name="g", disabled=c.locked) as rg:
                Radio("a", label="A")
                Radio("b", label="B")
            out = serialize(rg.render())

        # Both inputs carry the reactive directive AND the SSR-stamped
        # literal so the cluster shows locked before the runtime boots
        # (no flash-of-unlocked-then-locked).
        directive = 'bz-attr:disabled="$bz.state._D.default.locked"'
        assert out.count(directive) == 2
        assert len(self._DISABLED_ATTR_RE.findall(out)) == 2

    def test_per_item_binding_not_overridden_by_group_binding(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _E(ClientState, persist="memory"):
            group_locked: bool = field(default=False)
            item_locked:  bool = field(default=False)

        with render_isolated(), rendering_scope():
            e = _E()
            with RadioGroup(name="g", disabled=e.group_locked) as rg:
                Radio("a", label="A", disabled=e.item_locked)
                Radio("b", label="B")
            out = serialize(rg.render())

        # Radio A keeps its own per-item binding (item_locked).
        # Radio B inherits the group's binding (group_locked).
        assert 'bz-attr:disabled="$bz.state._E.default.item_locked"' in out
        assert 'bz-attr:disabled="$bz.state._E.default.group_locked"' in out


class TestImperativeAPI:
    """``RadioGroup.set(value)`` write-only method (v2-C scope).

    Single-method API : radios are one-of-N, so ``.clear()`` (deselect
    all) and ``.focus()`` / ``.blur()`` (no single target on a group)
    are explicitly out of scope. Branches at call time on whether
    ``value=`` carries a binding : binding → write-through ; literal →
    DOM dispatch caught by the wrapper's own ``bz-on:bz-set``
    listener."""

    # ── No-binding path : DOM dispatch ─────────────────────────────────

    def test_set_without_binding_returns_dispatch_with_payload(self) -> None:
        with render_isolated():
            with RadioGroup(name="g") as rg:
                Radio("a", label="A")
                Radio("b", label="B")
            out = rg.set("b")
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '"b"' in out  # _to_js wraps str in quotes
        assert rg.id in out

    def test_set_returns_str(self) -> None:
        with render_isolated():
            with RadioGroup(name="g") as rg:
                Radio("a", label="A")
            assert isinstance(rg.set("a"), str)

    # ── Binding path : write-through ──────────────────────────────────

    def test_set_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState, field
        from bretzel.state.scopes.client import rendering_scope

        class _Prefs(ClientState, persist="memory"):
            plan: str = field(default="free")

        with render_isolated(), rendering_scope():
            prefs = _Prefs()
            with RadioGroup(name="g", value=prefs.plan) as rg:
                Radio("free", label="Free")
                Radio("pro", label="Pro")
            out = rg.set("pro")
        assert "$bz.state._Prefs.default.plan" in out
        assert '"pro"' in out
        assert "dispatchEvent" not in out

    # ── Render-time wiring : listener (V3) ────────────────────────────

    def test_wrapper_carries_no_scope_residue(self) -> None:
        # V3 : ``bz-on:`` listeners resolve against the runtime's
        # root scope — no ``x-data`` / ``bz-data`` on the wrapper.
        with render_isolated():
            with RadioGroup(name="g") as rg:
                Radio("a", label="A")
            attrs = rg.render().attrs
        assert "x-data" not in attrs
        assert "bz-data" not in attrs

    def test_wrapper_carries_bz_set_listener(self) -> None:
        with render_isolated():
            with RadioGroup(name="g") as rg:
                Radio("a", label="A")
            attrs = rg.render().attrs
        assert "bz-on:bz-set" in attrs
        assert "@bz-set" not in attrs  # V2 Alpine form gone
        # Listener iterates child radio inputs and flips ``checked``
        # based on payload value.
        listener = attrs["bz-on:bz-set"]
        assert "querySelectorAll" in listener
        assert "input[type=" in listener
        assert "$event.detail.value" in listener
        # Newly-checked radio fires a synthetic ``change`` so user
        # ``on_change=`` handlers run.
        assert "new Event('change'" in listener

    def test_wrapper_always_carries_id_for_external_dispatch(self) -> None:
        # External callers .set() target the wrapper via getElementById.
        # The id MUST always be emitted, even on a bare unbound group
        # with no on_change= passed (regression for _needs_identity).
        with render_isolated():
            with RadioGroup(name="g") as rg:
                Radio("a", label="A")
            attrs = rg.render().attrs
        assert attrs.get("id") == rg.id
        assert rg.id in rg.set("a")

    def test_no_clear_or_focus_methods(self) -> None:
        # v2-C scope is intentionally minimal — radios are one-of-N so
        # ``.clear()`` has no real use case, and the group has no single
        # focus target. If we ever add them, drop this test.
        with render_isolated():
            with RadioGroup(name="g") as rg:
                Radio("a", label="A")
        assert not hasattr(rg, "clear")
        assert not hasattr(rg, "focus")
        assert not hasattr(rg, "blur")

"""Unit tests for :class:`bretzel.components.inputs.number_input.NumberInput`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.number_input import NumberInput
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


def _change_handler() -> None: ...


# ───────────────────────────────────────────────────────────────────────────
# A. Render structure
# ───────────────────────────────────────────────────────────────────────────


class TestStructure:
    def test_renders_root_with_bzdata(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "<div" in out
        assert "bz-data=" in out

    def test_input_is_type_text_not_number(self) -> None:
        """We use ``type="text"`` + ``inputmode="decimal"`` rather
        than ``type="number"`` to avoid native browser quirks
        (leading zero stripping, scientific notation, inconsistent
        clamp behavior across browsers)."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert 'type="text"' in out
        assert 'inputmode="decimal"' in out
        # NOT type="number".
        assert 'type="number"' not in out

    def test_two_stepper_buttons(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert 'aria-label="Increment"' in out
        assert 'aria-label="Decrement"' in out

    def test_stepper_buttons_have_chevron_icons(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "chevron-up" in out
        assert "chevron-down" in out

    def test_steppers_have_tabindex_minus1(self) -> None:
        """Stepper buttons must not steal keyboard focus from the
        input — the input is the canonical focusable element."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        # Two stepper buttons with tabindex="-1".
        assert out.count('tabindex="-1"') == 2

    def test_initial_value_in_bzdata(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "value: 42" in out


# ───────────────────────────────────────────────────────────────────────────
# B. Bounds + step + precision
# ───────────────────────────────────────────────────────────────────────────


class TestBoundsAndStep:
    def test_min_max_step_baked_in_bzdata(self) -> None:
        with render_isolated():
            out = serialize(
                NumberInput(value=5, min=0, max=10, step=0.5).render()
            )
        assert "_min: 0" in out
        assert "_max: 10" in out
        assert "_step: 0.5" in out

    def test_unbounded_min_max(self) -> None:
        """When min / max are omitted, _min / _max stay ``null`` and
        the clamp becomes a no-op on that side."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "_min: null" in out
        assert "_max: null" in out

    def test_precision_helper_present(self) -> None:
        """The precision / clamp / snap / nudge logic lives ONCE in the
        shared runtime factory ``$bz.numberInput.scope`` (no longer
        inlined per instance) ; the bz-data spreads it in."""
        with render_isolated():
            out = serialize(
                NumberInput(value=0, step=0.1).render()
            )
        assert "$bz.numberInput.scope" in out
        assert "_step: 0.1" in out

    def test_atmin_atmax_disable_steppers(self) -> None:
        """Stepper buttons disable when the value is already at the
        respective bound — :disabled="_atMin()" / _atMax()."""
        with render_isolated():
            out = serialize(
                NumberInput(value=0, min=0, max=10).render()
            )
        assert 'bz-attr:disabled="_atMax()"' in out
        assert 'bz-attr:disabled="_atMin()"' in out


# ───────────────────────────────────────────────────────────────────────────
# C. Keyboard + wheel
# ───────────────────────────────────────────────────────────────────────────


class TestKeyboardWheel:
    def test_arrow_keys_nudge(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        # V3 has no key modifiers — all keys live in one bz-on:keydown
        # body with inlined ``$event.key`` guards. Arrow up / down ±
        # step ; PageUp / PageDown ± step*10.
        assert "bz-on:keydown=" in out
        for key in ("ArrowUp", "ArrowDown", "PageUp", "PageDown"):
            assert f"'{key}'" in out
        # ``preventDefault`` inlined (was the ``.prevent`` modifier).
        assert "preventDefault()" in out

    def test_wheel_on_by_default(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        # ``preventDefault`` so the page doesn't scroll while wheel-
        # tweaking — inlined (V3 bz-on has no ``.prevent`` modifier).
        assert "bz-on:wheel=" in out

    def test_wheel_only_fires_when_focused(self) -> None:
        """The wheel handler gates on ``_focused`` — without that
        the input would bump as the user scrolls past the page,
        which is awful UX."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        # The wheel body checks _focused first.
        assert "if (_focused)" in out

    def test_wheel_off_when_disabled(self) -> None:
        with render_isolated():
            out = serialize(
                NumberInput(value=42, wheel=False).render()
            )
        assert "bz-on:wheel" not in out


# ───────────────────────────────────────────────────────────────────────────
# D. Display / draft / commit flow
# ───────────────────────────────────────────────────────────────────────────


class TestDisplayDraftCommit:
    def test_input_value_branches_on_focused(self) -> None:
        """The input's ``bz-attr:value`` shows ``_draft`` while typing
        (preserves the user's raw text including intermediate
        states like ``"1."``) ; switches to ``_displayValue()``
        when blurred for the canonical re-formatted value."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert (
            'bz-attr:value="_focused ? _draft : _displayValue()"' in out
        )

    def test_commit_draft_helper_present(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "_commitDraft" in out

    def test_no_self_triggering_change_handler(self) -> None:
        """Regression : the input must NOT carry a self-wired
        ``bz-on:change="_commitDraft(true)"`` listener. ``_commitDraft
        (true)`` ends by calling ``_emitChange()`` which dispatches
        a synthetic ``change`` event — wiring our own listener back
        onto ``change`` made every commit re-trigger itself →
        infinite loop, page froze. ``bz-on:blur`` already covers the
        "commit on lose focus" path.

        This test parses the raw input attrs (no user handler
        wired) to ensure no internal ``change`` listener is emitted
        by the framework on its own."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        # No internal change handler on the input. The only acceptable
        # bz-on:change is when the user explicitly wires ``on_change=``
        # — covered in TestEvents below.
        assert 'bz-on:change="_commitDraft(true)"' not in out
        assert 'bz-on:change="_commitDraft' not in out

    def test_blur_commits_final(self) -> None:
        """On blur, _commitDraft(true) does the clamp + snap +
        emits change ; on plain bz-on:input it does a soft commit (no
        clamp) so the user can freely type intermediate values.
        Note : the JS ``=`` is HTML-escaped to ``=`` inside
        attribute values."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        # bz-on:blur sets _focused = false then commits with clamp.
        assert (
            'bz-on:blur="_focused = false; _commitDraft(true)"'
            in out
        )
        # bz-on:input writes the raw text into _draft and does a soft
        # commit (no clamp yet — that runs on blur).
        assert (
            'bz-on:input="_draft = $event.target.value; '
            '_commitDraft(false)"' in out
        )


# ───────────────────────────────────────────────────────────────────────────
# E. Reactive contract — literal vs ClientBinding
# ───────────────────────────────────────────────────────────────────────────


class TestLiteralValue:
    def test_local_value_field_when_no_binding(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "value: 42" in out

    def test_no_hidden_name_without_binding(self) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        # Without a binding the input has no derived name.
        assert 'name=' not in out


class TestClientBindingValue:
    def test_binding_path_resolves(self) -> None:
        class S(ClientState, persist="memory"):
            amount: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            out = serialize(
                NumberInput(value=state.amount).render()
            )
        assert "$bz.state.S.default.amount" in out

    def test_binding_uses_read_write(self) -> None:
        class S(ClientState, persist="memory"):
            amount: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            out = serialize(
                NumberInput(value=state.amount).render()
            )
        # Binding mode points the shared factory at the store path via
        # ``_read`` / ``_write`` (no local ``value`` field, no frozen
        # ``get value()`` — cf. the scope.absorb getter-freeze trap).
        assert "_read()" in out and "_write(v)" in out
        assert "$bz.state." in out

    def test_autoname_from_binding_field(self) -> None:
        class S(ClientState, persist="memory"):
            amount: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            out = serialize(
                NumberInput(value=state.amount).render()
            )
        assert 'name="amount"' in out


class TestEvents:
    def test_change_relays_to_input(self) -> None:
        """A callable ``on_change=`` lands the native HTMX action set on
        the root via ``emit_attrs`` ; NumberInput relocates it onto the
        visible ``<input>`` (the form-data carrier — no separate hidden
        node). Re-spec'd for the V3 wire."""
        with render_isolated():
            out = serialize(
                NumberInput(value=42,
                            on_change=_change_handler).render()
            )
        # The HTMX action attrs land on the input itself.
        assert "hx-post=" in out
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "hx-post=" in opening

    def test_emit_change_uses_captured_carrier(self) -> None:
        """``_emitChange`` dispatches from ``this._carrier`` (the input
        captured at bz-init) — a scope method can't reach ``$refs`` /
        ``$el`` (directive-only locals), so the carrier is captured up
        front."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "_carrier" in out
        # Captured from the ref (or $el) in the input's bz-init.
        assert "$refs.bzinput || $el" in out

    def test_callable_change_routes_to_private_bzchange(self) -> None:
        """A callable ``on_change=`` must observe the COMMITTED value,
        not the browser's native ``change`` (which fires on blur, before
        the draft is reformatted, with the raw typed text). The trigger
        is rewritten to the private ``bzchange`` event that only
        ``_emitChange`` dispatches — leaving the native ``change`` with
        no observers (no leak of dirty text, no native+synthetic
        double-fire)."""
        with render_isolated():
            out = serialize(
                NumberInput(value=42, on_change=_change_handler).render()
            )
        assert 'hx-trigger="bzchange"' in out
        assert 'hx-trigger="change"' not in out

    def test_callable_change_keeps_modifier_on_bzchange(self) -> None:
        """``debounce=`` / ``throttle=`` append a modifier after the
        event name — the rewrite must keep it (``bzchange delay:300ms``),
        rewriting only the leading event token."""
        with render_isolated():
            out = serialize(
                NumberInput(value=42, on_change=_change_handler,
                            debounce=300).render()
            )
        assert 'hx-trigger="bzchange delay:300ms"' in out

    def test_string_change_routes_to_private_bzchange(self) -> None:
        """A string (client-only) ``on_change=`` is relocated as
        ``bz-on:bzchange`` for the same reason — never ``bz-on:change``,
        which would also catch the native blur ``change``."""
        with render_isolated():
            out = serialize(
                NumberInput(value=42,
                            on_change="$bz.log($event.target.value)").render()
            )
        assert "bz-on:bzchange=" in out
        assert "bz-on:change=" not in out

    def test_beforeinput_filters_non_numeric_keystrokes(self) -> None:
        """The carrier is ``type="text"`` (so partial drafts are
        readable), so the browser blocks nothing at the keyboard — a
        ``beforeinput`` guard rejects any inserted char outside
        ``[0-9.-]`` before it lands, so letters never show."""
        with render_isolated():
            out = serialize(NumberInput(value=42).render())
        assert "bz-on:beforeinput=" in out
        assert "/[^0-9.-]/.test" in out


# ───────────────────────────────────────────────────────────────────────────
# F. Theme sizes
# ───────────────────────────────────────────────────────────────────────────


class TestThemeSizes:
    @pytest.mark.parametrize(
        ("size", "shell_marker"),
        [
            ("xs", "h-7"),
            ("sm", "h-8"),
            ("md", "h-10"),
            ("lg", "h-12"),
            ("xl", "h-14"),
        ],
    )
    def test_size_scales_shell_height(
        self, size: str, shell_marker: str
    ) -> None:
        with render_isolated():
            out = serialize(NumberInput(value=42, size=size).render())
        assert shell_marker in out


# ───────────────────────────────────────────────────────────────────────────
# G. Imperative API
# ───────────────────────────────────────────────────────────────────────────


class TestImperativeAPI:
    def test_set_dispatches_when_no_binding(self) -> None:
        with render_isolated():
            n = NumberInput(value=10)
            out = n.set(42)
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert "42" in out

    def test_set_writes_through_binding(self) -> None:
        class S(ClientState, persist="memory"):
            amount: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            n = NumberInput(value=state.amount)
            out = n.set(42)
        assert "$bz.state.S.default.amount" in out
        assert "dispatchEvent" not in out

    def test_clear_uses_min_if_bounded(self) -> None:
        with render_isolated():
            n = NumberInput(value=50, min=10, max=100)
            out = n.clear()
        # Clear → reset to min (10).
        assert "10" in out

    def test_clear_uses_zero_if_unbounded(self) -> None:
        with render_isolated():
            n = NumberInput(value=42)
            out = n.clear()
        assert "0" in out

    def test_increment_dispatches_bz_step(self) -> None:
        with render_isolated():
            n = NumberInput(value=10)
            out = n.increment()
        assert "bz-step" in out
        # The dispatched payload is +1 (multiplier on step).
        assert "1" in out

    def test_decrement_dispatches_bz_step(self) -> None:
        with render_isolated():
            n = NumberInput(value=10)
            out = n.decrement()
        assert "bz-step" in out
        # The dispatched payload is -1.
        assert "-1" in out

    def test_focus_targets_input(self) -> None:
        with render_isolated():
            n = NumberInput(value=42)
            out = n.focus()
        assert "input[type=text]" in out
        assert ".focus()" in out

    def test_blur_targets_input(self) -> None:
        with render_isolated():
            n = NumberInput(value=42)
            out = n.blur()
        assert "input[type=text]" in out
        assert ".blur()" in out


# ───────────────────────────────────────────────────────────────────────────
# H. Bindable surface
# ───────────────────────────────────────────────────────────────────────────


class TestBindableSurface:
    def test_bindable_props(self) -> None:
        assert set(NumberInput.BINDABLE_PROPS) == {"value", "disabled"}

    def test_events_declared(self) -> None:
        assert set(NumberInput.EVENTS) == {"change", "focus", "blur"}

    def test_autoname_from_is_value(self) -> None:
        assert NumberInput.AUTONAME_FROM == "value"


class TestInputBlocksTypeNumber:
    """Regression : ui.input(type="number") must raise — the user
    is pointed at ui.number_input instead. Without this block the
    two ways to spell "numeric input" diverge silently."""

    def test_input_raises_for_type_number(self) -> None:
        from bretzel.components.base.binding_discipline import (
            ComponentUsageError,
        )
        from bretzel.components.inputs.input import Input

        with render_isolated(), pytest.raises(ComponentUsageError):
            Input(type="number")


class TestUserHandlerDoesNotClobberInternalWiring:
    """Regression : a user-supplied on_focus=/on_blur= client-string
    handler used to silently OVERWRITE the component's own internal
    wiring (dict.update() by key), not combine with it. On on_blur=
    specifically this destroyed _commitDraft(true) -- the typed value
    was never clamped/snapped/committed, and _emitChange() (nested
    inside _commitDraft) never fired either, so on_change= went dead
    too. Fixed by concatenating (internal first) instead of
    overwriting when both target the same bz-on:<event> key."""

    def test_on_blur_preserves_commit_draft(self) -> None:
        with render_isolated():
            html = serialize(
                NumberInput(value=42, on_blur="console.log(1)").render()
            )
        assert "_commitDraft(true)" in html
        assert "console.log(1)" in html
        # Internal logic runs first, the caller's expression after.
        assert html.index("_commitDraft(true)") < html.index("console.log(1)")

    def test_on_focus_preserves_draft_reset(self) -> None:
        with render_isolated():
            html = serialize(
                NumberInput(value=42, on_focus="console.log(2)").render()
            )
        # ``_focused = true`` (html-escaped ``=``) is unique to the
        # internal bz-on:focus wiring (unlike ``_displayValue()``, which
        # also appears unconditionally in the bz-attr:value binding) --
        # a real regression check.
        marker = "_focused = true"
        assert marker in html
        assert "console.log(2)" in html
        assert html.index(marker) < html.index("console.log(2)")

    def test_no_handler_still_wires_internal_only(self) -> None:
        with render_isolated():
            html = serialize(NumberInput(value=42).render())
        assert "_commitDraft(true)" in html
        assert "_focused = true" in html

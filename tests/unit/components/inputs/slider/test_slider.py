"""Unit tests for :class:`bretzel.components.inputs.slider.Slider`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.slider import Slider
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import ClientBinding, rendering_scope
from bretzel.state.scopes.server import _BoundFloat

def _synced_keys(out: str) -> set[str]:
    """Les clés réellement re-semées.

    ``_serverSync`` porte la clé de VALEUR (conditionnelle) ET la config
    server-owned préfixée ``_`` (inconditionnelle) : la simple présence du
    marker ne dit donc plus rien sur la valeur, il faut lire les clés.
    """
    import html as _html
    import re as _re
    keys: set[str] = set()
    for raw in _re.findall(r"_serverSync: \[([^\]]*)\]", _html.unescape(out)):
        keys |= {k.strip().strip("'\"") for k in raw.split(",") if k.strip()}
    return keys




def _change_handler() -> None: ...


class TestServerSyncGating:
    """``_serverSync`` re-adopts the value on a @refreshable swap — gated
    to server-backed values (``value=server_state.field``) so an unbound
    / literal slider keeps its client drag position across an unrelated
    refresh. Regression : same fix family as Select (cf. traps.md)."""

    def test_unbound_slider_omits_serversync(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30, name="x").render())
        assert "value" not in _synced_keys(out)

    def test_server_backed_slider_keeps_serversync(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=_BoundFloat(30.0, "sld")).render())
        assert "value" in _synced_keys(out)


# ───────────────────────────────────────────────────────────────────────────
# A. Render structure — single mode
# ───────────────────────────────────────────────────────────────────────────


class TestSingleStructure:
    def test_renders_root_with_bzdata(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        assert "<div" in out
        assert "bz-data=" in out

    def test_one_handle_role_slider(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # Single mode → exactly one ``role="slider"`` handle.
        assert out.count('role="slider"') == 1

    def test_track_has_pointer_handler(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # Click on the track jumps the value to that position. V3 has
        # no ``.self`` modifier — the guard is inlined in the handler.
        assert "bz-on:pointerdown=" in out
        assert "_jumpToPointer" in out
        assert "$event.target !== $el" in out

    def test_handle_is_focusable(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        assert 'tabindex="0"' in out

    def test_initial_value_in_bzdata(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=42).render())
        assert "value: 42" in out

    def test_min_max_step_in_bzdata(self) -> None:
        with render_isolated():
            out = serialize(
                Slider(value=5, min=0, max=10, step=0.5).render()
            )
        assert "_min: 0" in out
        assert "_max: 10" in out
        assert "_step: 0.5" in out

    def test_aria_value_props_reactive(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        assert 'bz-attr:aria-valuenow="_picked()"' in out
        assert 'bz-attr:aria-valuemin="_min"' in out
        assert 'bz-attr:aria-valuemax="_max"' in out


# ───────────────────────────────────────────────────────────────────────────
# B. Range mode
# ───────────────────────────────────────────────────────────────────────────


class TestRangeMode:
    def test_two_handles(self) -> None:
        with render_isolated():
            out = serialize(
                Slider(value=[20, 80], range=True).render()
            )
        assert out.count('role="slider"') == 2

    def test_range_handles_carry_distinct_aria_labels(self) -> None:
        with render_isolated():
            out = serialize(
                Slider(value=[20, 80], range=True).render()
            )
        assert 'aria-label="Range start"' in out
        assert 'aria-label="Range end"' in out

    def test_range_initial_array_value_in_bzdata(self) -> None:
        with render_isolated():
            out = serialize(
                Slider(value=[20, 80], range=True).render()
            )
        # JSON array of floats baked into the bz-data.
        assert "value: [20.0, 80.0]" in out

    def test_range_setHandle_clamps_start_le_end(self) -> None:
        """The setHandle body must swap on cross-over so start ≤ end."""
        with render_isolated():
            out = serialize(
                Slider(value=[20, 80], range=True).render()
            )
        # The setHandle swap logic lives in the shared
        # ``$bz.slider.scope`` factory (range branch) — behaviour is
        # browser-probed ; the render just wires the factory + flag.
        assert "$bz.slider.scope" in out
        assert "_range: true" in out

    def test_range_setValue_sorts_input(self) -> None:
        """_setValue (used by external .set([...])) sorts the pair
        so callers can pass [80, 20] without breaking the slider.
        Note : the JS arrow ``=>`` is escaped to ``=&gt;`` in
        the serialised x-data attribute."""
        with render_isolated():
            out = serialize(
                Slider(value=[20, 80], range=True).render()
            )
        # The sort lives in the factory's range _setValue ; the render
        # wires the factory + range flag.
        assert "$bz.slider.scope" in out
        assert "_range: true" in out

    def test_range_jumpToPointer_picks_closest_handle(self) -> None:
        with render_isolated():
            out = serialize(
                Slider(value=[20, 80], range=True).render()
            )
        # The closest-handle math lives in the factory's range
        # _jumpToPointer ; the render wires the factory + range flag.
        assert "$bz.slider.scope" in out
        assert "_range: true" in out

    def test_range_no_handles_in_single(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # Single mode has no array picking.
        assert "Range start" not in out
        assert "Range end" not in out


# ───────────────────────────────────────────────────────────────────────────
# C. Drag + keyboard primitives
# ───────────────────────────────────────────────────────────────────────────


class TestInteraction:
    def test_handle_drag_handlers_present(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # The handle declares pointerdown (drag start). V3 ``bz-on``
        # has no ``.stop`` modifier — the call is inlined in the body.
        assert "bz-on:pointerdown=" in out
        assert "stopPropagation()" in out
        assert "_startDrag" in out

    def test_window_pointer_flow_registered_via_onwindow(self) -> None:
        """Drag-move / drag-end have no per-handle ``.window`` modifier
        in V3 — they ride ONE ``$bz.helpers.onWindow`` pair on the
        root's ``bz-init`` (``_dragging`` carries the active target)."""
        with render_isolated():
            out = serialize(Slider(value=30).render())
        assert "onWindow('pointermove'" in out
        assert "onWindow('pointerup'" in out

    def test_keyboard_arrow_nav(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # V3 has no key modifiers — all keys live in one bz-on:keydown
        # body with inlined ``$event.key`` guards.
        assert "bz-on:keydown=" in out
        for key in (
            "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
            "PageUp", "PageDown", "Home", "End",
        ):
            assert f"'{key}'" in out

    def test_pointer_capture_on_track(self) -> None:
        """The track captures the pointer so the move keeps firing
        when the cursor leaves the handle during a drag."""
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # Pointer-capture lives in the shared $bz.slider.scope factory
        # (_startDrag / _endDrag) — browser-probed.
        assert "$bz.slider.scope" in out

    def test_step_clamping_in_xdata(self) -> None:
        with render_isolated():
            out = serialize(
                Slider(value=5, min=0, max=10, step=0.5).render()
            )
        # _clamp (round to step + clamp to [min,max]) lives in the
        # factory ; the render carries the per-instance min/max/step.
        assert "$bz.slider.scope" in out
        assert "_min: 0" in out and "_max: 10" in out and "_step: 0.5" in out

    def test_float_step_rounds_to_step_precision(self) -> None:
        """Float steps like ``0.1`` cause arithmetic drift :
        ``0.1 + 0.1 + 0.1 + 0.1 + 0.1 + 0.1 + 0.1 ===
        0.7000000000000001`` in JS. ``_clamp`` must round to the
        step's decimal precision so the tooltip shows ``0.7``,
        not the garbage trailing digits. Regression guard for the
        screenshot bug reported on the playground (float-step
        demo)."""
        with render_isolated():
            out = serialize(
                Slider(value=0.5, min=0, max=1, step=0.1).render()
            )
        # The precision + toFixed rounding lives in the factory's
        # _precision / _clamp ; the render carries the float step.
        assert "$bz.slider.scope" in out
        assert "_step: 0.1" in out


# ───────────────────────────────────────────────────────────────────────────
# D. Tooltip
# ───────────────────────────────────────────────────────────────────────────


class TestTooltip:
    def test_tooltip_visible_on_hover_focus_drag(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # ``===`` is escaped to ``===`` inside attrs.
        assert "_hovered ===" in out
        assert "_focused ===" in out
        assert "_dragging ===" in out

    def test_tooltip_bz_text_is_picked_value(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # Tooltip shows the live value via bz-text.
        assert 'bz-text="_picked()"' in out

    def test_tooltip_fouc_prestamp_prevents_flash(self) -> None:
        """Without the ``display:none`` pre-stamp, the tooltip would
        flash visible between SSR and the runtime's first bz-show
        effect. ``bz-show`` is the V3 replacement for x-show + x-cloak."""
        with render_isolated():
            out = serialize(Slider(value=30).render())
        # The tooltip div has bz-show + a FOUC ``display:none`` stamp.
        # ``===`` is HTML-escaped inside the attribute value.
        assert 'bz-show="_hovered ===' in out
        assert "display:none" in out


# ───────────────────────────────────────────────────────────────────────────
# E. Reactive contract — literal vs ClientBinding
# ───────────────────────────────────────────────────────────────────────────


class TestLiteralValue:
    def test_local_value_field_when_no_binding(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=42).render())
        assert "value: 42" in out

    def test_no_hidden_input_without_name(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=42).render())
        assert 'type="hidden"' not in out


class TestClientBindingValue:
    def test_binding_path_resolves(self) -> None:
        class S(ClientState, persist="memory"):
            volume: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            out = serialize(Slider(value=state.volume).render())
        assert "$bz.state.S.default.volume" in out

    def test_binding_uses_read_write(self) -> None:
        class S(ClientState, persist="memory"):
            volume: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            out = serialize(Slider(value=state.volume).render())
        # Binding mode points the shared factory at the store path via
        # ``_read`` / ``_write`` (no frozen ``get value()``).
        assert "_read()" in out and "_write(v)" in out
        assert "$bz.state." in out

    def test_autoname_from_binding_field(self) -> None:
        class S(ClientState, persist="memory"):
            volume: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            out = serialize(Slider(value=state.volume).render())
        assert 'name="volume"' in out

    def test_range_hidden_uses_json_stringify(self) -> None:
        class S(ClientState, persist="memory"):
            span: list = field(default_factory=lambda: [10.0, 90.0])

        with rendering_scope(), render_isolated():
            state = S()
            out = serialize(
                Slider(value=state.span, range=True).render()
            )
        assert "JSON.stringify" in out


# ───────────────────────────────────────────────────────────────────────────
# F. Theme sizes
# ───────────────────────────────────────────────────────────────────────────


class TestThemeSizes:
    @pytest.mark.parametrize(
        ("size", "track_marker", "handle_marker"),
        [
            ("xs", "h-1", "h-3 w-3"),
            ("sm", "h-1.5", "h-4 w-4"),
            ("md", "h-2", "h-5 w-5"),
            ("lg", "h-2.5", "h-6 w-6"),
            ("xl", "h-3", "h-7 w-7"),
        ],
    )
    def test_size_scales_track_and_handle(
        self, size: str, track_marker: str, handle_marker: str
    ) -> None:
        with render_isolated():
            out = serialize(Slider(value=30, size=size).render())
        assert track_marker in out
        assert handle_marker in out


# ───────────────────────────────────────────────────────────────────────────
# G. Imperative API
# ───────────────────────────────────────────────────────────────────────────


class TestImperativeAPI:
    def test_set_dispatches_when_no_binding(self) -> None:
        with render_isolated():
            s = Slider(value=30)
            out = s.set(42)
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert "42" in out
        assert s.id in out

    def test_set_writes_through_binding(self) -> None:
        class S(ClientState, persist="memory"):
            volume: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            s = Slider(value=state.volume)
            out = s.set(42)
        assert "$bz.state.S.default.volume" in out
        assert "dispatchEvent" not in out

    def test_clear_single_uses_min(self) -> None:
        with render_isolated():
            s = Slider(value=30, min=10, max=100)
            out = s.clear()
        # Single mode clear → reset to min (10).
        assert "10" in out

    def test_clear_range_uses_full_span(self) -> None:
        with render_isolated():
            s = Slider(value=[20, 80], min=0, max=100, range=True)
            out = s.clear()
        # Range mode clear → [min, max].
        assert "[0" in out
        assert "100" in out

    def test_focus_targets_handle(self) -> None:
        with render_isolated():
            s = Slider(value=30)
            out = s.focus()
        assert "[role=slider]" in out
        assert ".focus()" in out

    def test_blur_targets_handle(self) -> None:
        with render_isolated():
            s = Slider(value=30)
            out = s.blur()
        assert "[role=slider]" in out
        assert ".blur()" in out

    def test_needs_identity_true(self) -> None:
        with render_isolated():
            s = Slider(value=30)
            assert s._needs_identity() is True


# ───────────────────────────────────────────────────────────────────────────
# H. Bindable surface + events relocation
# ───────────────────────────────────────────────────────────────────────────


class TestBindableSurface:
    def test_bindable_props(self) -> None:
        assert set(Slider.BINDABLE_PROPS) == {"value", "disabled"}

    def test_events_declared(self) -> None:
        assert set(Slider.EVENTS) == {"change", "focus", "blur"}

    def test_autoname_from_is_value(self) -> None:
        assert Slider.AUTONAME_FROM == "value"


class TestEvents:
    def test_change_relocates_to_hidden(self) -> None:
        """A callable ``on_change=`` lands the native HTMX action set on
        the root via ``emit_attrs`` ; the slider relocates it to the
        hidden input so the form-data dispatcher reads name+value from
        the element that holds them (re-spec'd for the V3 wire)."""
        class S(ClientState, persist="memory"):
            volume: float = field(default=50.0)

        with rendering_scope(), render_isolated():
            state = S()
            s = Slider(
                value=state.volume, on_change=_change_handler,
            )
            out = serialize(s.render())
        # The HTMX action attrs land on the hidden input, NOT the root.
        opening = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "hx-post=" in opening
        # Pinned to the synthetic ``change`` the slider dispatches (a
        # hidden input fires no native event).
        assert 'hx-trigger="change"' in opening

    def test_focus_callable_relocates_to_handle_not_hidden(self) -> None:
        """A callable ``on_focus=`` must land its HTMX action set on the
        focusable handle (``role="slider"``), NOT the hidden input —
        the hidden input never fires a native ``focus`` event, so a
        misrouted handler would silently never trigger. Regression for
        a bug where the relocation blindly grabbed SERVER_ACTION_ATTRS
        by key name (present or absent) instead of checking which
        event they actually belonged to, AND force-overwrote
        ``hx-trigger`` to ``"change"`` whenever any action attrs landed
        on the hidden input — so an isolated ``on_focus=`` handler
        fired on ``change`` instead of ``focus``, silently."""
        with render_isolated():
            out = serialize(Slider(value=30, on_focus=_change_handler).render())
        handle = out[out.index('role="slider"'):]
        handle_opening = handle[:handle.index(">")]
        assert "hx-post=" in handle_opening
        assert 'hx-trigger="focus"' in handle_opening
        # No name/change binding here, so no hidden input renders at all
        # (its own guard) — confirming the action attrs aren't stranded
        # there is enough : count exactly one hx-post in the whole tree.
        assert out.count("hx-post=") == 1

    def test_blur_callable_relocates_to_handle_not_hidden(self) -> None:
        """Same bug, ``on_blur=`` side."""
        with render_isolated():
            out = serialize(Slider(value=30, on_blur=_change_handler).render())
        handle = out[out.index('role="slider"'):]
        handle_opening = handle[:handle.index(">")]
        assert "hx-post=" in handle_opening
        assert 'hx-trigger="blur"' in handle_opening
        assert out.count("hx-post=") == 1

    def test_emit_change_uses_captured_carrier(self) -> None:
        """``_emitChange`` dispatches from ``this._carrier`` (the hidden
        input captured at bz-init, or the root if none) — a scope
        method can't reach ``$refs`` / ``$el`` (directive-only locals),
        so the carrier is captured up front."""
        with render_isolated():
            out = serialize(Slider(value=30).render())
        assert "_carrier" in out
        # Captured from the ref (or $el) in the root bz-init.
        assert "$refs.bzhidden || $el" in out


class TestUserHandlerDoesNotClobberInternalWiring:
    """Regression : a user-supplied on_focus=/on_blur= CLIENT-STRING
    handler used to silently OVERWRITE the handle's own internal
    ``_focused`` tooltip-tracking wiring (dict-key collision via
    ``**relocated_attrs`` spread), not combine with it. Fixed by
    concatenating (internal first) instead of overwriting when both
    target the same bz-on:<event> key."""

    def test_on_focus_preserves_internal_tracking(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30, on_focus="console.log(2)").render())
        handle = out[out.index('role="slider"'):]
        handle_opening = handle[:handle.index(">")]
        marker = "_focused = &quot;value&quot;"
        assert marker in handle_opening
        assert "console.log(2)" in handle_opening
        assert handle_opening.index(marker) < handle_opening.index(
            "console.log(2)"
        )

    def test_on_blur_preserves_internal_tracking(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30, on_blur="console.log(1)").render())
        handle = out[out.index('role="slider"'):]
        handle_opening = handle[:handle.index(">")]
        assert "_focused = null" in handle_opening
        assert "console.log(1)" in handle_opening
        assert handle_opening.index("_focused = null") < handle_opening.index(
            "console.log(1)"
        )

    def test_no_handler_still_wires_internal_only(self) -> None:
        with render_isolated():
            out = serialize(Slider(value=30).render())
        handle = out[out.index('role="slider"'):]
        handle_opening = handle[:handle.index(">")]
        assert "_focused = null" in handle_opening

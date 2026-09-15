"""Unit tests for :class:`bretzel.components.inputs.select.Select`.

V3 ships a custom popover-based combobox — no native ``<select>``.
The trigger is a button, the panel is an anchored dropdown of option
buttons (``$bz.helpers.floating``), and the keyboard navigation is
wired client-side via the V3 runtime (``bz-data`` scope + ``bz-on``
directives, no Alpine modifier grammar).
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.select import Select
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope
from bretzel.state.scopes.server import _BoundStr


def _synced_keys(out: str) -> set[str]:
    """Les clés réellement re-semées.

    ``_serverSync`` porte la clé de VALEUR (conditionnelle) ET la config
    server-owned préfixée ``_`` (inconditionnelle) : la présence du marker
    ne dit donc plus rien sur la valeur, il faut lire les clés.
    """
    import html as _html
    import re as _re
    keys: set[str] = set()
    for raw in _re.findall(r"_serverSync: \[([^\]]*)\]", _html.unescape(out)):
        keys |= {k.strip().strip("'\"") for k in raw.split(",") if k.strip()}
    return keys




class TestStructure:
    def test_root_is_div_no_native_select(self) -> None:
        with render_isolated():
            sel = Select(options=["A"])
            out = serialize(sel.render())
        # No more native ``<select>`` — root is a ``<div>`` carrying
        # the bz-data state, with a button trigger inside.
        assert out.startswith("<div")
        assert "<select" not in out
        assert "<button" in out

    def test_trigger_carries_combobox_aria(self) -> None:
        with render_isolated():
            sel = Select(options=["A"])
            out = serialize(sel.render())
        assert 'role="combobox"' in out
        assert 'aria-haspopup="listbox"' in out
        # V3 reactive attr — stringified so the data-attr stays present.
        assert "bz-attr:aria-expanded=" in out

    def test_panel_has_listbox_role(self) -> None:
        with render_isolated():
            sel = Select(options=["A", "B"])
            out = serialize(sel.render())
        assert 'role="listbox"' in out

    def test_one_option_button_per_option(self) -> None:
        with render_isolated():
            sel = Select(options=["A", "B", "C"])
            out = serialize(sel.render())
        assert out.count('role="option"') == 3


class TestOptionShapes:
    def test_string_options(self) -> None:
        with render_isolated():
            sel = Select(options=["Apple", "Banana"])
            out = serialize(sel.render())
        assert ">Apple<" in out
        assert ">Banana<" in out

    def test_tuple_options_value_label(self) -> None:
        with render_isolated():
            sel = Select(options=[("a", "Apple"), ("b", "Banana")])
            out = serialize(sel.render())
        # Label visible in the option button.
        assert ">Apple<" in out
        # Click writes the value, not the label.
        assert '_pick(&quot;a&quot;)' in out
        assert '_pick(&quot;b&quot;)' in out

    def test_dict_options_with_disabled(self) -> None:
        with render_isolated():
            sel = Select(options=[
                {"value": "a", "label": "Apple"},
                {"value": "b", "label": "Banana", "disabled": True},
            ])
            out = serialize(sel.render())
        # The disabled option button carries the ``disabled`` attr.
        # ``role="option"`` count + one of them disabled.
        assert out.count('role="option"') == 2
        assert "disabled" in out


class TestPlaceholder:
    def test_placeholder_text_baked_into_label_lookup(self) -> None:
        with render_isolated():
            sel = Select(options=["A"], placeholder="Pick…")
            out = serialize(sel.render())
        # The label x-text expression includes the placeholder fallback.
        assert "Pick" in out


class TestValueBinding:
    """``value=`` accepts the universal three shapes — literal,
    server-resolved, ClientBinding — like every reactive prop."""

    def test_literal_value_picks_local_x_data(self) -> None:
        with render_isolated():
            sel = Select(options=["a", "b"], value="b")
            out = serialize(sel.render())
        # Local Alpine flag stores the value.
        assert "value: " in out

    def test_binding_value_writes_through_binding_path(self) -> None:
        class UI(ClientState, persist="memory"):
            pick: str = field(default='b')

        with render_isolated(), rendering_scope():
            ui_state = UI()
            sel = Select(
                options=[("a", "Apple"), ("b", "Banana")],
                value=ui_state.pick,
            )
            out = serialize(sel.render())
        # The pick handler writes to the binding path, not to a
        # local ``value`` field.
        assert "$bz.state.UI.default.pick" in out


class TestFormIntegration:
    def test_no_hidden_input_without_name(self) -> None:
        with render_isolated():
            sel = Select(options=["A"])
            out = serialize(sel.render())
        assert 'type="hidden"' not in out

    def test_hidden_input_carries_name_when_set(self) -> None:
        with render_isolated():
            sel = Select(options=["a"], name="fruit", value="a")
            out = serialize(sel.render())
        assert 'type="hidden"' in out
        assert 'name="fruit"' in out

    def test_hidden_input_value_bound_to_binding(self) -> None:
        class UI(ClientState, persist="memory"):
            pick: str = field(default='a')

        with render_isolated(), rendering_scope():
            ui_state = UI()
            sel = Select(
                options=["a", "b"], name="fruit", value=ui_state.pick
            )
            out = serialize(sel.render())
        # V3 one-way reactive attr : ``bz-attr:value`` carries the
        # ``String($bz.state.…)`` form (single mode stringifies).
        assert "bz-attr:value=" in out
        assert "$bz.state.UI.default.pick" in out


class TestServerSyncGating:
    """``_serverSync: ['value']`` re-adopts the value from the server on a
    @refreshable swap. It must be emitted ONLY when the value is backed by
    server state — otherwise a refresh of the surrounding section wipes an
    unbound select's client pick AND fires a phantom ``change(value='')``
    (the change-emit effect sees the value reset to the empty SSR initial).
    Regression : user report 2026-06-13, ``on_change`` select inside its
    own @refreshable logged a double event + lost its value."""

    def test_unbound_select_omits_serversync(self) -> None:
        with render_isolated():
            sel = Select(options=["a", "b"], on_change="x = 1")
            out = serialize(sel.render())
        assert "value" not in _synced_keys(out)

    def test_literal_value_omits_serversync(self) -> None:
        # A one-time literal initial is not a live server source ; the
        # client owns the value across refreshes.
        with render_isolated():
            sel = Select(options=["a", "b"], value="b")
            out = serialize(sel.render())
        assert "value" not in _synced_keys(out)

    def test_server_backed_value_keeps_serversync(self) -> None:
        # ``value=server_state.field`` carries a ``field_name`` stamp —
        # the server is authoritative, a re-render should win.
        with render_isolated():
            sel = Select(
                options=["a", "b"], value=_BoundStr("b", "fruit"),
            )
            out = serialize(sel.render())
        # (quotes are HTML-escaped in the serialised ``bz-data`` attr).
        assert "value" in _synced_keys(out)

    def test_unbound_multi_omits_serversync(self) -> None:
        with render_isolated():
            sel = Select(options=["a", "b"], multiple=True, on_change="x=1")
            out = serialize(sel.render())
        assert "value" not in _synced_keys(out)

    def test_hidden_input_keeps_change_emit_effect(self) -> None:
        # The change dispatcher is the ``bz-effect`` on the hidden input
        # (the scope's ``_emitChange`` fires from the root carrier and
        # never reaches the htmx listener on this child). Guard against a
        # regression that strips it — change would silently stop firing.
        with render_isolated():
            sel = Select(options=["a"], name="fruit", value="a",
                         on_change="x = 1")
            out = serialize(sel.render())
        op = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "bz-effect=" in op
        assert "dispatchEvent" in op


def _trigger_attrs(sel: Select) -> dict:
    """The trigger element's attrs — the child carrying
    ``role="combobox"`` (button single / div multi)."""
    for child in sel.render().children:
        if getattr(child, "attrs", {}).get("role") == "combobox":
            return child.attrs
    raise AssertionError("no combobox trigger found")


class TestKeyboardNav:
    """V3 fuses every per-key handler into ONE ``bz-on:keydown`` with
    ``$event.key`` guards (the runtime has no Alpine modifier
    grammar)."""

    def test_arrow_keys_wired(self) -> None:
        with render_isolated():
            sel = Select(options=["A", "B"])
            attrs = _root_attrs(sel)
            trigger = _trigger_attrs(sel)
        # The fused handler lives on the trigger (single button).
        kd = trigger["bz-on:keydown"]
        assert "ArrowDown" in kd
        assert "ArrowUp" in kd
        # The directive name is the bare event, no modifiers.
        assert "bz-on:keydown" in trigger
        assert "@keydown" not in attrs

    def test_enter_and_space_open_or_pick(self) -> None:
        with render_isolated():
            sel = Select(options=["A"])
            trigger = _trigger_attrs(sel)
        kd = trigger["bz-on:keydown"]
        assert "'Enter'" in kd
        assert "' '" in kd  # space key
        # Both prevent default through the inlined guard.
        assert "preventDefault" in kd

    def test_escape_closes_globally(self) -> None:
        # V3 : Escape-to-close rides the shared anchored dismiss init
        # (``$bz.helpers.escapeKey``) on the root bz-init, plus the
        # per-trigger keydown guard handles Escape when focused.
        with render_isolated():
            sel = Select(options=["A"])
            attrs = _root_attrs(sel)
        assert "escapeKey" in attrs["bz-init"]
        assert "open = false" in attrs["bz-init"]


class TestAttrs:
    def test_disabled_attr_on_trigger(self) -> None:
        with render_isolated():
            sel = Select(options=["A"], disabled=True)
            out = serialize(sel.render())
        assert "disabled" in out

    def test_required_passes_through(self) -> None:
        with render_isolated():
            sel = Select(options=["A"], required=True)
            out = serialize(sel.render())
        assert 'aria-required="true"' in out


class TestTheme:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [("sm", "h-8"), ("md", "h-10"), ("lg", "h-12")],
    )
    def test_size_class_on_trigger_not_root(
        self, size: str, expected: str
    ) -> None:
        with render_isolated():
            sel = Select(options=["A"], size=size)
            out = serialize(sel.render())
        # Same regression as Tier 2 : the size modifier lives on the
        # trigger, not on the wrapper ``<div>``.
        wrapper = out.split("<button", 1)[0]
        assert expected not in wrapper
        assert expected in out

    def test_color_substitutes_on_focus_ring(self) -> None:
        with render_isolated():
            sel = Select(options=["A"], color="success")
            out = serialize(sel.render())
        assert "focus:border-(--bz-solid)" in out
        assert "bz-c-success" in out


def _root_attrs(sel: Select) -> dict:
    return sel.render().attrs


class TestImperativeAPI:
    """``.set/.clear/.focus/.blur`` write-only methods.

    Same v2-C contract as Input — branches on whether ``value=``
    carries a binding : binding → write-through ; literal → DOM
    dispatch caught by the wrapper's own ``@bz-*`` listener (the
    listener calls Select's internal ``_pick`` setter so the
    displayed label updates AND fires ``change`` on the hidden
    input so user ``on_change=`` handlers run).

    ``.focus()`` / ``.blur()`` are pure DOM commands — they target
    the trigger ``<button>`` (the only focusable element in the
    Select) via ``querySelector('button[role=combobox]')`` on the
    rooted wrapper.
    """

    # ── No-binding path : DOM dispatch ─────────────────────────────────

    def test_set_without_binding_returns_dispatch_with_payload(self) -> None:
        with render_isolated():
            sel = Select(options=["a", "b"])
            out = sel.set("a")
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '"a"' in out  # _to_js wraps str in quotes
        assert sel.id in out

    def test_clear_without_binding_dispatches_empty_string(self) -> None:
        with render_isolated():
            sel = Select(options=["a", "b"])
            out = sel.clear()
        # .clear() is sugar over .set("") — same dispatch shape.
        assert "dispatchEvent" in out
        assert "bz-set" in out
        assert '""' in out

    def test_set_with_int_value(self) -> None:
        # value= can be any JSON-serialisable type. Numbers ride naked.
        with render_isolated():
            sel = Select(options=[(1, "One"), (2, "Two")])
            out = sel.set(2)
        assert "value: 2" in out

    # ── Focus / blur : direct DOM, no dispatch ─────────────────────────

    def test_focus_targets_trigger_button_via_querySelector(self) -> None:
        # The wrapper ``<div>`` carries ``self.id`` but is not
        # focusable ; we reach the trigger via querySelector so the
        # method actually moves keyboard focus.
        with render_isolated():
            sel = Select(options=["a"])
            out = sel.focus()
        assert "document.getElementById" in out
        assert sel.id in out
        assert "querySelector" in out
        # Trigger selector widened from ``button[role=combobox]`` to
        # ``[role=combobox]`` because multi mode swaps the trigger
        # to a ``<div>`` (so it can host pills + nested × buttons
        # without nested-button invalid HTML). The role= attribute
        # is the stable selector across both shapes.
        assert "[role=combobox]" in out
        assert ".focus()" in out
        assert "dispatchEvent" not in out

    def test_blur_targets_trigger_button_via_querySelector(self) -> None:
        with render_isolated():
            sel = Select(options=["a"])
            out = sel.blur()
        assert "document.getElementById" in out
        assert sel.id in out
        assert "querySelector" in out
        # Trigger selector widened from ``button[role=combobox]`` to
        # ``[role=combobox]`` because multi mode swaps the trigger
        # to a ``<div>`` (so it can host pills + nested × buttons
        # without nested-button invalid HTML). The role= attribute
        # is the stable selector across both shapes.
        assert "[role=combobox]" in out
        assert ".blur()" in out
        assert "dispatchEvent" not in out

    # ── Binding path : write-through ──────────────────────────────────

    def test_set_with_binding_writes_through(self) -> None:
        class UI(ClientState, persist="memory"):
            pick: str = field(default='')

        with render_isolated(), rendering_scope():
            ui_state = UI()
            sel = Select(options=[("a", "A"), ("b", "B")],
                         value=ui_state.pick)
            out = sel.set("a")
        assert "$bz.state.UI.default.pick" in out
        assert '"a"' in out
        assert "dispatchEvent" not in out

    def test_clear_with_binding_writes_empty_string(self) -> None:
        class UI(ClientState, persist="memory"):
            pick: str = field(default='a')

        with render_isolated(), rendering_scope():
            ui_state = UI()
            sel = Select(options=[("a", "A"), ("b", "B")],
                         value=ui_state.pick)
            out = sel.clear()
        assert "$bz.state.UI.default.pick" in out
        assert '""' in out
        assert "dispatchEvent" not in out

    # ── Render-time wiring : scope + listeners ────────────────────────

    def test_root_carries_bz_data_scope(self) -> None:
        # The root already carries the full Select bz-data state
        # machine (open / value / _pick / _highlight / ...) — the
        # bz-on:bz-* directives register inside that scope so they can
        # call ``_pick`` directly.
        with render_isolated():
            sel = Select(options=["a"])
            attrs = _root_attrs(sel)
        assert "bz-data" in attrs
        # ``_pick`` (+ the rest of the scope) lives in the shared
        # $bz.select.single factory ; the bz-data spreads it in.
        assert "$bz.select.single" in attrs["bz-data"]

    def test_root_carries_bz_set_listener_and_clear_is_set_sugar(self) -> None:
        with render_isolated():
            sel = Select(options=["a"])
            attrs = _root_attrs(sel)
        assert "bz-on:bz-set" in attrs
        # ``.clear()`` is sugar for ``.set("")`` — it dispatches ``bz-set``
        # with an empty value, so there is NO dedicated ``bz-clear`` listener.
        assert "bz-on:bz-clear" not in attrs
        assert "bz-set" in sel.clear()
        assert "bz-clear" not in sel.clear()

    def test_listeners_call_pick_and_fire_change_event(self) -> None:
        # The listener calls ``_pick`` (the canonical setter), which just
        # ``_write``s the value ; the hidden input's
        # ``_change_emit_effect`` observes the mutation and dispatches the
        # ``change`` so any ``on_change=`` user handler runs — same
        # contract as the click-an-option path. The scope does NOT
        # dispatch change itself (no ``_emitChange`` — a removed redundant
        # dispatcher).
        with render_isolated():
            sel = Select(options=["a"])
            attrs = _root_attrs(sel)
        assert "_pick(" in attrs["bz-on:bz-set"]
        assert "$bz.select.single" in attrs["bz-data"]
        # The scope no longer carries the (removed) carrier machinery.
        assert "_carrier" not in attrs["bz-data"]
        assert "_emitChange" not in attrs["bz-data"]

    def test_root_always_carries_id_for_external_dispatch(self) -> None:
        # External callers .set() / .focus() target the wrapper via
        # getElementById. The id MUST always be emitted, even on a
        # bare unbound Select with no handlers (where the base
        # _needs_identity heuristic would otherwise skip it).
        with render_isolated():
            sel = Select(options=["a"])
            attrs = _root_attrs(sel)
        assert attrs.get("id") == sel.id
        assert sel.id in sel.set("a")
        assert sel.id in sel.focus()

    def test_methods_return_str(self) -> None:
        with render_isolated():
            sel = Select(options=["a"])
            assert isinstance(sel.set("a"), str)
            assert isinstance(sel.clear(),  str)
            assert isinstance(sel.focus(),  str)
            assert isinstance(sel.blur(),   str)


def _change_handler() -> None: ...


def _hidden_input_attrs(out: str) -> str:
    """Slice the first ``<input>`` open tag from serialized output."""
    start = out.index("<input")
    return out[start:out.index(">", start)]


class TestEventRelocation:
    """V3 event wiring : change → hidden input, focus/blur → trigger.

    A callable handler rides the native HTMX action set (``hx-post`` +
    ``hx-trigger`` + …) ; a string handler rides ``bz-on:<event>``.
    The ``hx-trigger`` names the firing event, so the change bundle
    must land on the element that fires ``change`` (the hidden input,
    via ``_change_emit_effect``)."""

    def test_string_change_relocates_to_hidden(self) -> None:
        with render_isolated():
            sel = Select(
                options=["a"], name="fruit", value="a",
                on_change="state.x = 1",
            )
            out = serialize(sel.render())
        op = _hidden_input_attrs(out)
        assert "bz-on:change=" in op
        # The root must NOT keep the change listener.
        root = out[: out.index("<input")]
        assert "bz-on:change" not in root

    def test_callable_change_relocates_with_pinned_trigger(self) -> None:
        class S(ClientState, persist="memory"):
            pick: str = field(default='')

        with render_isolated(), rendering_scope():
            state = S()
            sel = Select(
                options=["a", "b"], value=state.pick,
                on_change=_change_handler,
            )
            out = serialize(sel.render())
        op = _hidden_input_attrs(out)
        assert "hx-post=" in op
        # Pinned to the synthetic ``change`` the hidden input dispatches
        # (a hidden input fires no native event).
        assert 'hx-trigger="change"' in op
        # The change-emit effect lives on the hidden input.
        assert "bz-effect=" in op
        # Root stays clean of the action bundle.
        root = out[: out.index("<input")]
        assert "hx-post" not in root

    def test_focus_blur_relocate_to_trigger(self) -> None:
        with render_isolated():
            sel = Select(
                options=["a"], on_focus="f()", on_blur="b()",
            )
            trigger = _trigger_attrs(sel)
        assert trigger.get("bz-on:focus") == "f()"
        assert trigger.get("bz-on:blur") == "b()"

    def test_callable_focus_blur_wire_to_trigger_not_change(self) -> None:
        """Regression : a callable ``on_focus`` / ``on_blur`` used to be
        popped to the hidden input and re-keyed to ``change`` (so it fired
        on change, never on focus/blur). It must ride the focusable trigger
        keyed to its own event."""
        with render_isolated():
            sel = Select(options=["a"], on_focus=_change_handler)
            trigger = _trigger_attrs(sel)
        assert trigger.get("hx-post")                  # on the trigger
        assert trigger.get("hx-trigger") == "focus"    # fires on focus
        with render_isolated():
            sel = Select(options=["a"], on_blur=_change_handler)
            trigger = _trigger_attrs(sel)
        assert trigger.get("hx-post")
        assert trigger.get("hx-trigger") == "blur"

    def test_change_dispatched_by_hidden_input_effect_not_scope(self) -> None:
        # ``change`` is dispatched by the hidden input's
        # ``_change_emit_effect`` (from ``$el``), NOT by a scope method.
        # The removed ``_emitChange`` / ``_carrier`` carrier machinery
        # must leave no trace : it dispatched a second, redundant change
        # (a double event on Combobox) and never reliably reached the
        # input on Select.
        with render_isolated():
            sel = Select(options=["a"], name="x", value="a",
                         on_change="y = 1")
            attrs = _root_attrs(sel)
            out = serialize(sel.render())
        assert "_carrier" not in attrs["bz-data"]
        assert "_carrier" not in attrs.get("bz-init", "")
        assert "_emitChange" not in out
        # The hidden input carries the dispatcher.
        op = out[out.index("<input"):out.index(">", out.index("<input"))]
        assert "bz-effect=" in op and "dispatchEvent" in op


class TestAnchoredPanel:
    """The panel rides the shared overlay wiring : a panel bz-effect
    toggles display + attaches floating against the ``bztrigger``
    ref ; the root carries open/close dispatch + dismiss init."""

    def test_panel_has_floating_effect_and_ref(self) -> None:
        with render_isolated():
            sel = Select(options=["a", "b"])
            out = serialize(sel.render())
        assert 'bz-ref="bzpanel"' in out
        assert "floating" in out
        # FOUC pre-stamp keeps the panel hidden before boot.
        assert "display:none" in out or "display: none" in out

    def test_trigger_carries_anchor_ref(self) -> None:
        with render_isolated():
            sel = Select(options=["a"])
            trigger = _trigger_attrs(sel)
        assert trigger.get("bz-ref") == "bztrigger"

    def test_root_dispatch_and_dismiss_wiring(self) -> None:
        with render_isolated():
            sel = Select(options=["a"])
            attrs = _root_attrs(sel)
        # Open/close dispatch effect + Escape/click-outside dismiss.
        assert "bz-effect" in attrs
        assert "clickOutside" in attrs["bz-init"]
        assert "escapeKey" in attrs["bz-init"]


# ───────────────────────────────────────────────────────────────────────────
# Multi mode — pills, header bar, bulk actions, imperative
# ───────────────────────────────────────────────────────────────────────────


def _build_multi(*, value=None, **kwargs):
    """Stage a multi-mode Select with three options."""
    return Select(
        options=[("a", "Alpha"), ("b", "Bravo"), ("c", "Charlie")],
        value=value if value is not None else [],
        multiple=True,
        **kwargs,
    )


class TestMultiMode:
    def test_trigger_switches_to_div_with_tabindex(self) -> None:
        """In multi the trigger is a focusable ``<div role=combobox
        tabindex=0>`` instead of a ``<button>`` so it can host
        pills + nested × buttons (nested ``<button>`` in
        ``<button>`` would be invalid HTML)."""
        with render_isolated():
            out = serialize(_build_multi().render())
        assert 'role="combobox"' in out
        assert 'tabindex="0"' in out

    def test_single_trigger_stays_a_button(self) -> None:
        """Regression : single mode keeps the existing ``<button>``
        trigger shape — backward-compatible for callers."""
        with render_isolated():
            sel = Select(options=["a"], value="a")
            out = serialize(sel.render())
        # Look for ``<button type="button" class="…" role="combobox"``.
        assert '<button type="button"' in out
        assert 'role="combobox"' in out

    def test_pills_template_in_trigger(self) -> None:
        """Multi trigger renders ``<template bz-for>`` so picked
        values appear as removable pills inside the trigger."""
        with render_isolated():
            out = serialize(_build_multi(value=["a"]).render())
        # The serializer escapes ``=`` to ``=`` inside attr values ;
        # the runtime reads the unescaped form via getAttribute.
        assert 'bz-for="v in _picked() :key=v"' in out

    def test_pills_template_absent_in_single(self) -> None:
        with render_isolated():
            sel = Select(options=["a"], value="a")
            out = serialize(sel.render())
        assert "bz-for" not in out

    def test_multi_uses_toggle_pick_on_option_click(self) -> None:
        """Option click in multi calls ``_togglePick`` (flips array
        membership) — picking a picked option deselects."""
        with render_isolated():
            out = serialize(_build_multi().render())
        assert "_togglePick(" in out

    def test_single_uses_pick_on_option_click(self) -> None:
        with render_isolated():
            sel = Select(options=["a", "b"])
            out = serialize(sel.render())
        assert "_pick(" in out
        # No togglePick in single mode.
        assert "_togglePick(" not in out

    def test_header_bar_in_panel_multi(self) -> None:
        """Multi mode adds a sticky header at the top of the panel
        with the picked pills."""
        with render_isolated():
            out = serialize(_build_multi(value=["a"]).render())
        # The pills template appears TWICE in multi : once inside
        # the trigger (CLOSED visual), once in the panel header
        # (OPEN visual). Single mode has zero.
        assert out.count('bz-for="v in _picked() :key=v"') == 2

    def test_header_bar_absent_in_single(self) -> None:
        with render_isolated():
            sel = Select(options=["a"], value="a")
            out = serialize(sel.render())
        # No header_bar layout class in single mode.
        assert "sticky top-0" not in out

    def test_bulk_actions_adds_buttons(self) -> None:
        with render_isolated():
            out = serialize(
                _build_multi(bulk_actions=True).render()
            )
        assert "Select all" in out
        assert ">Clear<" in out
        assert "_selectAll()" in out
        assert "_clearAll()" in out

    def test_bulk_actions_header_always_visible(self) -> None:
        """When ``bulk_actions=True`` the header bar must be
        visible even with zero picks — Select all has to be
        discoverable before the user has clicked anything."""
        with render_isolated():
            out = serialize(
                _build_multi(bulk_actions=True).render()
            )
        assert 'bz-show="true"' in out

    def test_bulk_actions_ignored_in_single(self) -> None:
        with render_isolated():
            sel = Select(
                options=["a"], multiple=False, bulk_actions=True,
            )
            out = serialize(sel.render())
        # bulk_actions has no effect on single mode — same as Combobox.
        assert "Select all" not in out


class TestMultiHiddenInput:
    def test_multi_hidden_uses_json_stringify(self) -> None:
        """Multi mode serialises the picked array as JSON so the
        value survives one form-data round-trip."""
        class S(ClientState, persist="memory"):
            picked: list = field(default_factory=list)

        with rendering_scope(), render_isolated():
            state = S()
            sel = Select(
                options=[("a", "A"), ("b", "B")],
                value=state.picked,
                multiple=True,
            )
            out = serialize(sel.render())
        assert "JSON.stringify" in out

    def test_multi_initial_array_value_in_hidden(self) -> None:
        with render_isolated():
            sel = _build_multi(value=["a", "b"])
            out = serialize(sel.render())
        # Without a binding there's no hidden input by default,
        # but ``value: [...]`` appears in the x-data scope.
        assert "value: [&quot;a&quot;, &quot;b&quot;]" in out


class TestMultiImperative:
    def test_select_all_dispatches(self) -> None:
        with render_isolated():
            sel = _build_multi()
            out = sel.select_all()
        assert "bz-select-all" in out
        assert "detail" not in out  # no payload

    def test_deselect_all_dispatches(self) -> None:
        with render_isolated():
            sel = _build_multi()
            out = sel.deselect_all()
        assert "bz-deselect-all" in out

    def test_clear_multi_sends_empty_array(self) -> None:
        with render_isolated():
            sel = _build_multi()
            out = sel.clear()
        assert "bz-set" in out
        assert "[]" in out

    def test_clear_single_sends_empty_string(self) -> None:
        with render_isolated():
            sel = Select(options=["a"])
            out = sel.clear()
        assert "bz-set" in out
        assert '""' in out


class TestMultiBindable:
    def test_multiple_prop_is_reactive(self) -> None:
        """``multiple`` is a reactive_prop ; the kwarg routing
        accepts it and the render branches on it."""
        assert hasattr(Select, "multiple")

    def test_bulk_actions_prop_is_reactive(self) -> None:
        assert hasattr(Select, "bulk_actions")


# ───────────────────────────────────────────────────────────────────
# render= — le corps de l'option
# ───────────────────────────────────────────────────────────────────


class TestRenderHatch:
    """`COLLECTION_OWNER = "component"` : c'est le Select qui itère
    ``options=``, donc l'auteur n'a que ce rappel pour poser du balisage.

    Le partage corps/enveloppe est gaté catalogue-large par
    ``tests/consistency/test_render_hatch_universal.py`` ; ici on épingle
    ce qui est propre au picker."""

    def _html(self, **kwargs) -> str:

        with render_isolated():
            return serialize(
                Select(options=[("a", "Alpha"), ("b", "Beta")], **kwargs)
                .render()
            )

    def test_the_callback_body_reaches_the_option(self) -> None:
        from bretzel import ui

        out = self._html(render=lambda v, label: ui.badge(label="ZZ"))
        assert out.count("ZZ") == 2, "un corps par option, une seule fois"

    def test_the_envelope_survives(self) -> None:
        """`data-value` et l'état sélectionné appartiennent au composant.
        Un rappel qui les avalerait casserait la sélection au premier
        usage."""
        from bretzel import ui

        out = self._html(render=lambda v, label: ui.badge(label="ZZ"))
        assert 'data-value="a"' in out
        assert 'role="option"' in out
        assert "aria-selected" in out

    def test_the_callback_gets_normalised_value_and_label(self) -> None:
        """⚠️ ``(value, label)`` DÉJÀ normalisés, jamais l'option brute :
        ``options=`` accepte str / tuple / dict, donc un rappel écrit
        ``lambda opt: opt["label"]`` planterait sur deux des trois. Même
        défaut livré puis retiré sur ``breadcrumb`` le 2026-08-18."""
        seen: list[tuple] = []

        def spy(value, label):
            seen.append((value, label))
            return label

        with render_isolated():
            serialize(Select(options=["A", ("b", "Beta"),
                                      {"value": "c", "label": "Gamma"}],
                             render=spy).render())
        assert seen == [("A", "A"), ("b", "Beta"), ("c", "Gamma")], (
            "les trois formes d'option doivent arriver normalisées à "
            "l'identique — c'est ce qui rend le rappel écrivable."
        )

    def test_without_the_hatch_the_label_renders(self) -> None:
        out = self._html()
        assert "Alpha" in out and "Beta" in out

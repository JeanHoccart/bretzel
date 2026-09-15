"""Unit tests for ``bretzel.components.base.events`` (V3 wire)."""

from __future__ import annotations

import functools
import json

import pytest

from bretzel.components.base.attrs import ComponentDefinitionError
from bretzel.components.base.events import (
    HandlerError,
    action_attrs,
    client_event_attr,
    cross_check_events,
    encode_handler_id,
)
from bretzel.server.handlers import encode_args


# Module-level functions are addressable via ``module::qualname``.
def my_handler() -> None:
    pass


class _Holder:
    @staticmethod
    def static_handler() -> None:
        pass

    @classmethod
    def class_handler(cls) -> None:
        pass


# ───────────────────────────────────────────────────────────────────────────
# encode_handler_id
# ───────────────────────────────────────────────────────────────────────────


class TestEncode:
    def test_module_function(self) -> None:
        out = encode_handler_id(my_handler)
        assert out.endswith("::my_handler")
        assert "test_events" in out

    def test_static_method(self) -> None:
        out = encode_handler_id(_Holder.static_handler)
        # Static method's qualname is "_Holder.static_handler".
        assert "_Holder.static_handler" in out

    def test_class_method(self) -> None:
        out = encode_handler_id(_Holder.class_handler)
        assert "_Holder.class_handler" in out

    def test_partial_unwrapped(self) -> None:
        out = encode_handler_id(functools.partial(my_handler))
        assert out.endswith("::my_handler")

    def test_lambda_rejected(self) -> None:
        with pytest.raises(HandlerError, match="Lambda"):
            encode_handler_id(lambda: None)

    def test_closure_rejected(self) -> None:
        def outer() -> None:
            def inner() -> None: ...
            encode_handler_id(inner)

        with pytest.raises(HandlerError, match="Closure"):
            outer()

    def test_non_callable_rejected(self) -> None:
        with pytest.raises(HandlerError, match="callable"):
            encode_handler_id(42)  # type: ignore[arg-type]


# ───────────────────────────────────────────────────────────────────────────
# client_event_attr — string handlers (client-only JS expressions)
# ───────────────────────────────────────────────────────────────────────────


class TestClientEventAttr:
    def test_emits_bz_on(self) -> None:
        assert client_event_attr("click") == "bz-on:click"

    def test_other_event_names(self) -> None:
        assert client_event_attr("focus") == "bz-on:focus"
        assert client_event_attr("keydown") == "bz-on:keydown"


# ───────────────────────────────────────────────────────────────────────────
# action_attrs — server handlers (native HTMX attribute set)
# ───────────────────────────────────────────────────────────────────────────


class TestActionAttrs:
    def test_callable_emits_full_htmx_set(self) -> None:
        action_id = encode_handler_id(my_handler)
        out = action_attrs("click", action_id, "", "")
        assert out["hx-post"] == f"/_bretzel/action/{action_id}"
        assert out["hx-post"].endswith("::my_handler")
        assert out["hx-trigger"] == "click"
        assert out["hx-target"] == "#bz-sink"
        assert out["hx-swap"] == "innerHTML"

    def test_partial_args_ride_hx_vals(self) -> None:
        bound = functools.partial(my_handler, item_id=42)
        action_id = encode_handler_id(bound)
        blob = encode_args(bound)
        assert blob  # the partial produced a non-empty blob
        out = action_attrs("click", action_id, blob, "")
        assert json.loads(out["hx-vals"]) == {"_args": blob}

    def test_no_args_no_hx_vals(self) -> None:
        out = action_attrs("click", "m::f", "", "")
        assert "hx-vals" not in out

    def test_sig_present_stamps_data_bz_sig(self) -> None:
        out = action_attrs("click", "m::f", "", "deadbeef")
        assert out["data-bz-sig"] == "deadbeef"

    def test_empty_sig_no_data_bz_sig(self) -> None:
        out = action_attrs("click", "m::f", "", "")
        assert "data-bz-sig" not in out

    def test_modifier_appends_to_trigger(self) -> None:
        out = action_attrs("input", "m::f", "", "", modifier="delay:300ms")
        assert out["hx-trigger"] == "input delay:300ms"

    def test_no_modifier_plain_trigger(self) -> None:
        out = action_attrs("input", "m::f", "", "", modifier=None)
        assert out["hx-trigger"] == "input"


# ───────────────────────────────────────────────────────────────────────────
# cross_check_events
# ───────────────────────────────────────────────────────────────────────────


class TestCrossCheck:
    def test_matched_passes(self) -> None:
        class C:
            EVENTS = ("click",)

            def __init__(self, *, on_click=None): ...

        cross_check_events(C)  # no raise

    def test_mismatch_raises(self) -> None:
        class C:
            EVENTS = ("click", "focus")

            def __init__(self, *, on_click=None): ...

        with pytest.raises(ComponentDefinitionError, match="on_focus"):
            cross_check_events(C)

    def test_no_events_no_check(self) -> None:
        class C:
            EVENTS: tuple[str, ...] = ()

            def __init__(self): ...

        cross_check_events(C)  # no raise

    def test_class_without_init_passes(self) -> None:
        class C:
            EVENTS = ("click",)

        cross_check_events(C)  # no raise — abstract / inherits ``object.__init__``


# ───────────────────────────────────────────────────────────────────────────
# debounce= / throttle= — HTMX trigger modifiers on a server event
# ───────────────────────────────────────────────────────────────────────────


class TestDebounceThrottle:
    def _trigger_of(self, **kw) -> str:
        import re

        from bretzel import ui
        from bretzel.components.base.testing import render_isolated
        from bretzel.render import serialize_html

        with render_isolated():
            html = serialize_html(ui.input(on_input=my_handler, **kw))
        m = re.search(r'hx-trigger="([^"]*)"', html)
        return m.group(1) if m else ""

    def test_debounce_becomes_delay(self) -> None:
        assert self._trigger_of(debounce=300) == "input delay:300ms"

    def test_throttle_becomes_throttle(self) -> None:
        assert self._trigger_of(throttle=500) == "input throttle:500ms"

    def test_no_modifier_is_plain(self) -> None:
        assert self._trigger_of() == "input"

    def test_mutually_exclusive(self) -> None:
        from bretzel import ui
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated

        with pytest.raises(ComponentUsageError):
            with render_isolated():
                ui.input(on_input=my_handler, debounce=1, throttle=1)


class TestPending:
    """``ui.pending()`` — le témoin « une action est en vol ».

    Ce que ces tests gardent, c'est la FORME émise. Le comportement (le
    seuil de 200 ms, le retour au repos) n'est mesurable qu'au
    navigateur : ``tests/probes/probe_pending.py``.
    """

    def _html(self, factory) -> str:
        from bretzel import ui
        from bretzel.components.base.testing import render_isolated
        from bretzel.render import serialize_html

        with render_isolated():
            box = ui.vstack()
            with box:
                factory()
            return serialize_html(box)

    def test_bare_form_targets_the_carrying_element(self) -> None:
        from bretzel import ui

        assert ui.pending().binding_path() == "$bz.pending($el, 200)"

    def test_after_is_milliseconds_like_debounce(self) -> None:
        from bretzel import ui

        assert ui.pending(after=0).binding_path() == "$bz.pending($el, 0)"
        assert ui.pending(after=750).binding_path() == "$bz.pending($el, 750)"

    def test_handler_form_uses_the_wire_id(self) -> None:
        from bretzel import ui

        expr = ui.pending(my_handler).binding_path()
        assert encode_handler_id(my_handler) in expr

    def test_loading_emits_the_show_mutex_and_the_disabled_or(self) -> None:
        from bretzel import ui

        html = self._html(
            lambda: ui.button("Go", on_click=my_handler, loading=ui.pending())
        )
        # Le spinner est un ENFANT du bouton : c'est pour ça que le
        # runtime remonte au porteur du ``hx-post`` par ``closest``.
        assert 'bz-show="$bz.pending($el, 200)"' in html
        assert 'bz-attr:disabled="($bz.pending($el, 200)) || (false)"' in html

    def test_remote_addressing_binds_visible(self) -> None:
        from bretzel import ui

        html = self._html(lambda: ui.skeleton(visible=ui.pending(my_handler)))
        assert "bz-show=" in html and "$bz.pending(" in html

    def test_no_flash_at_ssr(self) -> None:
        """Aucune requête ne peut être en vol quand le serveur rend.

        Sans ce ``display:none`` pré-posé, le squelette s'affiche à
        CHAQUE chargement jusqu'à ce que le runtime évalue — un
        clignotement garanti, sur le mécanisme dont le but est
        justement d'éviter les clignotements.
        """
        from bretzel import ui

        html = self._html(lambda: ui.skeleton(visible=ui.pending(my_handler)))
        assert "display:none" in html

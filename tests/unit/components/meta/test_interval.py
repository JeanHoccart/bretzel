"""Unit tests for ``ui.interval`` — the controllable client timer.

It wires the ``on_tick`` callable as a signed action on a custom ``tick``
trigger, and a ``bz-effect`` that gates a ``setInterval`` on ``active``.
"""

from __future__ import annotations

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.render import serialize_html
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class Play(ClientState):
    active: bool = field(default=False)


def tick() -> None:
    pass


def test_emits_signed_action_on_tick_trigger() -> None:
    with render_isolated():
        html = serialize_html(ui.interval(on_tick=tick, seconds=2))
    assert 'hx-post="/_bretzel/action/' in html
    assert 'hx-trigger="tick"' in html          # custom trigger, not a DOM event
    assert "$bz._tick($el" in html
    assert ", 2000)" in html                     # seconds=2 → ms
    assert "hidden" in html                      # the timer is invisible


def test_a_disabled_binding_gates_the_effect() -> None:
    with render_isolated(), rendering_scope():
        html = serialize_html(ui.interval(on_tick=tick, disabled=~Play().active))
    # The gate is the client signal, not a frozen value.
    assert "$bz._tick($el, (!((!$bz.state.Play.default.active))), 1000)" in html


def test_static_not_disabled() -> None:
    with render_isolated():
        html = serialize_html(ui.interval(on_tick=tick, disabled=False))
    assert "$bz._tick($el, (true), 1000)" in html

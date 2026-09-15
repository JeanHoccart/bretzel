"""Gate : the ``module::qualname`` wire-id separator is single-sourced,
and the two encoders that must agree DO agree.

An action/zone id is ``<module>::<qualname>``. The ``::`` separator was
defined twice (``server/handlers`` + ``components/base/events``) and
hardcoded in ``render/decorators/refreshable`` ; ``resolve_handler``
splits on it. Any drift → actions and zone refetches 404. The import DAG
(``components`` < ``server``) forbids the two encoders sharing one
function, so ``encode_action_id`` (server) and ``encode_handler_id``
(components) are near-duplicate by necessity — this gate pins the
separator to one source (``protocol.WIRE_ID_SEP``) and asserts the
encoders can't diverge in what they accept, reject, or produce.
"""

from __future__ import annotations

import pytest

import bretzel.components.base.events as _events
import bretzel.server.handlers as _handlers
from bretzel.components.base.events import encode_handler_id
from bretzel.runtime import WIRE_ID_SEP
from bretzel.server.handlers import encode_action_id


def _a_module_level_handler() -> None:  # a genuine module-level callable
    ...


def test_separator_single_sourced() -> None:
    assert _handlers._ACTION_ID_SEPARATOR is WIRE_ID_SEP
    assert _events._ACTION_ID_SEPARATOR is WIRE_ID_SEP


def test_encoders_agree_on_a_module_level_handler() -> None:
    aid = encode_action_id(_a_module_level_handler)
    hid = encode_handler_id(_a_module_level_handler)
    assert aid == hid, "the server and component encoders must produce one id"
    assert aid.endswith(f"{WIRE_ID_SEP}_a_module_level_handler")


def test_both_encoders_reject_a_lambda() -> None:
    with pytest.raises(Exception):
        encode_action_id(lambda: None)
    with pytest.raises(Exception):
        encode_handler_id(lambda: None)


def test_both_encoders_reject_a_closure() -> None:
    def _make():
        def _inner() -> None: ...

        return _inner

    closure = _make()
    with pytest.raises(Exception):
        encode_action_id(closure)
    with pytest.raises(Exception):
        encode_handler_id(closure)

"""End-to-end : ``@background`` runs after the action response ships.

Posts a signed action whose handler schedules a background task, then
asserts the task ran — and ran AFTER the handler (order proves the
"after-response" contract, not just "it ran").
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from bretzel import Bretzel, background
from bretzel.server.handlers import encode_action_id, sign_action

_SECRET = "x" * 32

# Module-level so the handler/task are addressable via ``module::qualname``.
_order: list[str] = []


@background
def record_after(tag: str) -> None:
    _order.append(f"task:{tag}")


def schedule_handler() -> None:
    _order.append("handler")
    record_after.schedule(tag="done")


def _post(client: TestClient, app: Bretzel, handler) -> int:
    action_id = encode_action_id(handler)
    signature = sign_action(app.config._action_key, action_id, "")
    resp = client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": signature},
        data={"_args": ""},
    )
    return resp.status_code


class TestBackgroundEndToEnd:
    def test_scheduled_task_runs_after_response(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")
        _order.clear()
        with TestClient(app) as client:
            status = _post(client, app, schedule_handler)
        # Handler queued no refreshable / client-state → 204.
        assert status == 204
        # Task ran, and ran AFTER the handler (after-response contract).
        assert _order == ["handler", "task:done"]

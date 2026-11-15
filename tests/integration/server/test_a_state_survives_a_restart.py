"""Gate: with ``state_url="sqlite:///…"``, a state survives the process.

Two real processes, one after the other, on the same app module
(``_restart_app``): the first renders the page, clicks a signed action
that changes an ``AppState`` and a ``SessionState``, and exits; the
second starts the app afresh, sends back the first one's session cookie,
and renders the page. What it shows is what the store gave back — a
TestClient cannot fake that, since nothing of the first process is left.

Both sides: on a file the second process shows the change; in memory
(no ``state_url``) it shows the defaults — the gate measures the store,
not a value the page would print anyway.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

_FIRST = """
import json
from fastapi.testclient import TestClient
from bretzel.server.handlers import encode_action_id, sign_action
from tests._session import session_of
from tests.integration.server._restart_app import app, avancer
with TestClient(app) as client:
    client.get("/")
    action_id = encode_action_id(avancer)
    sig = sign_action(app.config._action_key, action_id, "", session_id=session_of(client))
    done = client.post(f"/_bretzel/action/{action_id}", headers={"X-Bz-Sig": sig},
                       data={"_args": ""})
    print(json.dumps({"status": done.status_code, "cookies": dict(client.cookies)}))
"""

_SECOND = """
import json, sys
from fastapi.testclient import TestClient
from tests.integration.server._restart_app import app
with TestClient(app, cookies=json.loads(sys.argv[1])) as client:
    print(client.get("/").text)
"""


def _python(script: str, *args: str, state_url: str | None) -> str:
    env = {**os.environ, "BZ_TEST_STATE_URL": state_url or ""}
    done = subprocess.run([sys.executable, "-c", script, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout


def _restart(state_url: str | None) -> str:
    """Click in one process, render in the next: the second page."""
    first = json.loads(_python(_FIRST, state_url=state_url).strip().splitlines()[-1])
    assert first["status"] == 200, first
    return _python(_SECOND, json.dumps(first["cookies"]), state_url=state_url)


@pytest.mark.parametrize(("store", "expected"), [
    ("sqlite", "compte=1 fil=42"),
    ("memory", "compte=0 fil=aucun"),
])
def test_a_state_survives_a_restart_only_in_a_file(
    tmp_path: Path, store: str, expected: str
) -> None:
    url = f"sqlite:///{(tmp_path / 'etat.db').as_posix()}" if store == "sqlite" else None
    assert expected in _restart(url)

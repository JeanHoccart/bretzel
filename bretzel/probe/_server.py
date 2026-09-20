"""Serving the app for the probe's duration — in a thread, or a subprocess.

The **thread** is the default, and that is not a convenience detail: it
is the only one of the two where the app lives in OUR process, so the
only one where :func:`bretzel.probe.Probe.state` can read what the server
believes. Without it, a motionless screen is indistinguishable from a
broken render.

The **subprocess** is kept for the case ``tests/probes/probe_kanban.py``
documents: the app may want to start with its own environment
(variables, the installed runtime bundle rather than the repository's, a
Redis worker). One loses ``state()`` there, and the refusal says so.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def resolve(app: Any) -> Any:
    """``"module:attr"`` → the object. An object stays itself."""
    if not isinstance(app, str):
        return app
    if ":" not in app:
        raise ValueError(
            f"{app!r} is not an app target: it must be "
            "\"module:attribute\", for example \"examples.kanban.main:app\"."
        )
    import importlib

    module_name, _, attr = app.partition(":")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ValueError(
            f"the module {module_name!r} has no attribute {attr!r}."
        ) from exc


class _ThreadServer:
    def __init__(self, app: Any, port: int) -> None:
        import uvicorn

        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        )
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        # uvicorn exposes no "ready" event: we poll its flag. Tight
        # first — measured on 2026-09-10, it flips in 6 to 40 ms once the
        # imports are warm, so a 50 ms step wastes half of it — then we
        # relax, the budget being 5 s.
        deadline = time.monotonic() + 5.0
        step = 0.002
        while time.monotonic() < deadline:
            if self._server.started:
                return
            time.sleep(step)
            step = min(step * 1.5, 0.05)
        raise RuntimeError("the server did not start within 5 seconds")

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)


class _SubprocessServer:
    def __init__(self, target: str, port: int) -> None:
        self._target = target
        self._port = port
        self._proc: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self._proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", self._target,
                "--host", "127.0.0.1", "--port", str(self._port),
                "--log-level", "error",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # A deliberately missing route: a 404 proves it is listening as
        # well as a 200, and it does not make the whole home page render
        # just to answer a probe.
        url = f"http://127.0.0.1:{self._port}/_bretzel_probe_ping"
        deadline = time.time() + 30.0
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"the server {self._target!r} stopped at startup "
                    f"(code {self._proc.returncode})."
                )
            try:
                with urllib.request.urlopen(url, timeout=1.0):
                    return
            except urllib.error.HTTPError:
                return  # it answers, even with a 4xx: it is up.
            except OSError:
                time.sleep(0.05)
        raise RuntimeError(f"server {self._target!r} did not respond within 30 seconds")

    def stop(self) -> None:
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._proc.kill()


@contextlib.contextmanager
def serve(app: Any, *, mode: str) -> Iterator[tuple[str, Any]]:
    """Return ``(base_url, app_object_or_None)``.

    The object is only returned in thread mode — it is what carries the
    state backend, so it is what makes ``state()`` possible.
    """
    if mode not in ("thread", "subprocess"):
        raise ValueError(f"unknown serving mode: {mode!r}")

    port = free_port()
    if mode == "subprocess":
        if not isinstance(app, str):
            raise ValueError(
                "subprocess mode needs a \"module:attr\" target, not an "
                "app object: the subprocess must be able to import it "
                "itself."
            )
        server: Any = _SubprocessServer(app, port)
        served: Any = None
    else:
        served = resolve(app)
        server = _ThreadServer(served, port)

    server.start()
    try:
        yield f"http://127.0.0.1:{port}", served
    finally:
        server.stop()

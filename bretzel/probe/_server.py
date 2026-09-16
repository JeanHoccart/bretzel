"""Servir l'app le temps du probe — en thread, ou en sous-processus.

Le **thread** est le défaut, et ce n'est pas un détail de confort : c'est
la seule des deux façons où l'app vit dans NOTRE processus, donc la seule
où :func:`bretzel.probe.Probe.state` peut lire ce que le serveur croit.
Sans elle, un écran immobile ne se distingue pas d'un rendu cassé.

Le **sous-processus** est conservé pour le cas que
``tests/probes/probe_kanban.py`` documente : l'app peut vouloir démarrer
avec son propre environnement (variables, bundle runtime installé plutôt
que celui du dépôt, worker Redis). On y perd ``state()``, et le refus le
dit.
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
    """``"module:attr"`` → l'objet. Un objet reste lui-même."""
    if not isinstance(app, str):
        return app
    if ":" not in app:
        raise ValueError(
            f"{app!r} n'est pas une cible d'app : il faut "
            "« module:attribut », par exemple « examples.kanban.main:app »."
        )
    import importlib

    module_name, _, attr = app.partition(":")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ValueError(
            f"le module {module_name!r} n'a pas d'attribut {attr!r}."
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
        # uvicorn n'expose pas d'événement « prêt » : on sonde son
        # drapeau. Fin d'abord — mesuré le 2026-09-10, il bascule en 6 à
        # 40 ms une fois les imports chauds, donc un pas de 50 ms en
        # gaspille la moitié — puis on relâche, le budget restant 5 s.
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
        # Une route volontairement absente : un 404 prouve qu'il écoute
        # aussi bien qu'un 200, et il ne fait pas rendre la page
        # d'accueil entière juste pour répondre à une sonde.
        url = f"http://127.0.0.1:{self._port}/_bretzel_probe_ping"
        deadline = time.time() + 30.0
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"le serveur {self._target!r} s'est arrêté au démarrage "
                    f"(code {self._proc.returncode})."
                )
            try:
                with urllib.request.urlopen(url, timeout=1.0):
                    return
            except urllib.error.HTTPError:
                return  # il répond, même en 4xx : il est debout.
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
    """Rend ``(base_url, objet_app_ou_None)``.

    L'objet n'est rendu qu'en mode thread — c'est lui qui porte le
    backend d'état, donc c'est lui qui rend ``state()`` possible.
    """
    if mode not in ("thread", "subprocess"):
        raise ValueError(f"unknown serving mode: {mode!r}")

    port = free_port()
    if mode == "subprocess":
        if not isinstance(app, str):
            raise ValueError(
                "le mode sous-processus a besoin d'une cible « module:attr », "
                "pas d'un objet d'app : le sous-processus doit pouvoir "
                "l'importer lui-même."
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

"""Unit tests for :mod:`bretzel.server._dev` — the owned dev watcher.

Validates the spawn-target helper and the watchfiles wiring without
ever actually starting uvicorn or spawning a subprocess (mocked).
"""

from __future__ import annotations

import inspect

import pytest


pytestmark = pytest.mark.unit


# ───────────────────────────────────────────────────────────────────────────
# _run_uvicorn — the spawn target
# ───────────────────────────────────────────────────────────────────────────


class TestRunUvicorn:
    def test_importable_at_module_level(self) -> None:
        # Precondition for watchfiles' spawn ctx : the function must
        # be importable by ``module:qualname`` in a fresh interpreter.
        from bretzel.server._dev import _run_uvicorn

        assert _run_uvicorn.__module__ == "bretzel.server._dev"
        assert _run_uvicorn.__qualname__ == "_run_uvicorn"

    def test_signature_matches_what_run_dev_server_passes(self) -> None:
        # The args tuple shape is locked here so a refactor of one
        # side without the other fails loudly.
        from bretzel.server._dev import _run_uvicorn

        sig = inspect.signature(_run_uvicorn)
        params = list(sig.parameters)
        assert params == ["target", "host", "port", "log_level"]


# ───────────────────────────────────────────────────────────────────────────
# run_dev_server — the watchfiles parent loop
# ───────────────────────────────────────────────────────────────────────────


class TestRunDevServer:
    def test_invokes_watchfiles_with_function_mode(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Mock watchfiles.run_process so we capture the call without
        # actually spawning anything.
        captured: dict[str, object] = {}

        def fake_run_process(*paths, **kwargs):  # type: ignore[no-untyped-def]
            captured["paths"] = paths
            captured["kwargs"] = kwargs

        import watchfiles

        monkeypatch.setattr(watchfiles, "run_process", fake_run_process)

        from bretzel.server._dev import _run_uvicorn, run_dev_server

        run_dev_server(
            target="my_app.main:app",
            host="127.0.0.1",
            port=8000,
            log_level="info",
            watch_dirs=["/tmp/app", "/tmp/bretzel"],
        )

        # Function mode + our helper + the args tuple the helper expects.
        assert captured["paths"] == ("/tmp/app", "/tmp/bretzel")
        assert captured["kwargs"]["target"] is _run_uvicorn
        assert captured["kwargs"]["args"] == (
            "my_app.main:app", "127.0.0.1", 8000, "info",
        )
        assert captured["kwargs"]["target_type"] == "function"

        # PythonFilter so only *.py triggers (and __pycache__/.git/.venv
        # are skipped natively — no need for our own reload_excludes).
        from watchfiles import PythonFilter
        assert isinstance(captured["kwargs"]["watch_filter"], PythonFilter)

        # User-visible log line at startup.
        out = capsys.readouterr().out
        assert "[bretzel] watching:" in out
        assert "/tmp/app" in out


# ───────────────────────────────────────────────────────────────────────────
# Bretzel._derive_watch_dirs — auto-detection of dirs to watch
# ───────────────────────────────────────────────────────────────────────────


class TestDeriveWatchDirs:
    """``_derive_watch_dirs(app_dir)`` returns the list of dirs the
    watcher should monitor. Logic ported from V1 :

    - Always the user app's dir (passed in as ``app_dir`` when
      ``_derive_uvicorn_target`` could compute it ; else fall back
      to ``__main__.__file__``'s parent).
    - PLUS ``bretzel/`` itself when the framework is a local checkout
      (not site-packages), so framework devs get auto-reload on
      framework edits without configuring anything.
    - Just the app dir when bretzel is pip-installed.
    """

    def _make_app(self) -> object:
        from bretzel import Bretzel

        return Bretzel(secret_key="x" * 32, mode="dev")

    def test_explicit_app_dir_is_resolved(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        app = self._make_app()
        dirs = app._derive_watch_dirs(str(tmp_path))

        # tmp_path comes first ; bretzel may or may not be appended
        # depending on whether we're running from site-packages.
        from pathlib import Path
        assert dirs[0] == Path(tmp_path).resolve()

    def test_bretzel_checkout_appends_framework_dir(
        self, tmp_path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        # Force the "bretzel is a local checkout" branch by patching
        # bretzel.__file__ to a path outside site-packages.
        import bretzel
        from pathlib import Path

        fake_checkout = tmp_path / "fake_bretzel_checkout"
        fake_checkout.mkdir()
        monkeypatch.setattr(bretzel, "__file__", str(fake_checkout / "__init__.py"))

        app_dir = tmp_path / "user_app"
        app_dir.mkdir()

        app = self._make_app()
        dirs = app._derive_watch_dirs(str(app_dir))

        assert dirs == [app_dir.resolve(), fake_checkout.resolve()]

    def test_bretzel_site_packages_skips_framework_dir(
        self, tmp_path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        import bretzel
        from pathlib import Path

        fake_install = tmp_path / "site-packages" / "bretzel"
        fake_install.mkdir(parents=True)
        monkeypatch.setattr(bretzel, "__file__", str(fake_install / "__init__.py"))

        app_dir = tmp_path / "user_app"
        app_dir.mkdir()

        app = self._make_app()
        dirs = app._derive_watch_dirs(str(app_dir))

        # Only the user app dir — site-packages bretzel is not watched.
        assert dirs == [app_dir.resolve()]

    def test_none_app_dir_falls_back_to_main_file(
        self, tmp_path, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        import sys
        import types
        from pathlib import Path

        fake_main = types.ModuleType("__main__")
        fake_main.__file__ = str(tmp_path / "main.py")  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "__main__", fake_main)

        app = self._make_app()
        dirs = app._derive_watch_dirs(None)

        # First entry is the dir of __main__.__file__.
        assert dirs[0] == tmp_path.resolve()


# ───────────────────────────────────────────────────────────────────────────
# ensure_port_is_free — le port pris se DIT, il ne se subit pas
# ───────────────────────────────────────────────────────────────────────────


class TestPortPreflight:
    """Gate : un port déjà tenu fait lever AVANT tout lancement.

    Le défaut qu'elle ferme, mesuré le 2026-09-03 :
    ``watchfiles.run_process`` lance uvicorn dans un processus ENFANT.
    Quand le parent meurt sans propager — terminal fermé, ``timeout``,
    kill — l'enfant survit et garde le port. Le lancement suivant échoue
    alors DANS l'enfant, et selon le terminal l'``[Errno 10048]`` ne
    remonte pas : on voit « watching: … » puis le prompt, et rien qui
    explique. Constaté en vrai, PID 5640 tenant le 8006.

    Les deux sens sont mesurés : un port tenu lève, un port libre passe.
    Sans le second, une garde qui lèverait TOUJOURS passerait pour
    mordante.
    """

    def test_a_taken_port_raises_and_names_it(self) -> None:
        import socket

        from bretzel.server._dev import PortAlreadyTakenError, ensure_port_is_free

        holder = socket.socket()
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        port = holder.getsockname()[1]
        try:
            with pytest.raises(PortAlreadyTakenError) as caught:
                ensure_port_is_free("127.0.0.1", port)
        finally:
            holder.close()

        message = str(caught.value)
        assert str(port) in message, (
            "le refus ne nomme pas le port — c'est la seule chose que "
            f"l'utilisateur peut chercher :\n{message}"
        )
        assert "Get-NetTCPConnection" in message, (
            "le refus ne dit pas COMMENT trouver le tenant. `netstat` peut "
            "ne rien rendre dans ce cas précis (mesuré), donc la commande "
            f"qui marche fait partie du diagnostic :\n{message}"
        )

    def test_a_free_port_passes(self) -> None:
        """Le versant LICITE — sans lui, la garde pourrait tout refuser."""
        import socket

        from bretzel.server._dev import ensure_port_is_free

        finder = socket.socket()
        finder.bind(("127.0.0.1", 0))
        port = finder.getsockname()[1]
        finder.close()

        ensure_port_is_free("127.0.0.1", port)

    def test_the_preflight_runs_before_anything_is_spawned(self) -> None:
        """L'ordre EST le remède : lever après le lancement ne sert à rien.

        Vérifié sur la SOURCE plutôt qu'en lançant un serveur : ce qui
        compte est que l'appel précède `run_process`, et c'est une
        propriété statique.
        """
        from bretzel.server import _dev

        source = inspect.getsource(_dev.run_dev_server)
        assert source.index("ensure_port_is_free") < source.index("run_process("), (
            "la vérification du port passe APRÈS le lancement de l'enfant — "
            "or c'est précisément dans l'enfant que l'erreur se perd."
        )

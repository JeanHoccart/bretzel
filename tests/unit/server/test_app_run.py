"""Unit tests for :meth:`bretzel.Bretzel.run` — both reload modes.

We never let uvicorn actually start a server in these tests
(``uvicorn.run`` is monkey-patched to record its args).
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


_SECRET = "x" * 32


class TestRunNoReload:
    """``reload=False`` (default) : pass the instance directly to
    uvicorn.run. No watcher, no string-target derivation."""

    def test_passes_instance_to_uvicorn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bretzel import Bretzel

        recorded: dict = {}

        def fake_uvicorn_run(app, **kwargs):  # type: ignore[no-untyped-def]
            recorded["app"] = app
            recorded["kwargs"] = kwargs

        import uvicorn

        monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)

        app = Bretzel(secret_key=_SECRET, mode="dev")
        app.run(host="127.0.0.1", port=8001, log_level="warning")

        assert recorded["app"] is app
        assert recorded["kwargs"]["host"] == "127.0.0.1"
        assert recorded["kwargs"]["port"] == 8001
        assert recorded["kwargs"]["reload"] is False


class TestRunReload:
    """``reload=True`` : delegate to ``bretzel.server._dev.run_dev_server``
    with a derived target string + auto-detected watch dirs. uvicorn.run
    is NEVER called from this path."""

    def test_delegates_to_run_dev_server(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bretzel import Bretzel

        captured: dict = {}

        def fake_run_dev_server(
            target, host, port, log_level, watch_dirs,
        ):  # type: ignore[no-untyped-def]
            captured["target"] = target
            captured["host"] = host
            captured["port"] = port
            captured["log_level"] = log_level
            captured["watch_dirs"] = watch_dirs

        import bretzel.server._dev as _dev

        monkeypatch.setattr(_dev, "run_dev_server", fake_run_dev_server)

        # Boom-trap : if anything calls uvicorn.run on this path the
        # test fails loudly.
        import uvicorn

        def boom(*_a, **_kw):  # type: ignore[no-untyped-def]
            raise AssertionError(
                "uvicorn.run must NOT be called when reload=True — "
                "the watcher owns the spawn."
            )

        monkeypatch.setattr(uvicorn, "run", boom)

        app = Bretzel(secret_key=_SECRET, mode="dev")
        # Use the explicit ``target`` escape hatch so we don't need a
        # real __main__ module in the test process.
        app.run(
            host="127.0.0.1",
            port=8002,
            log_level="warning",
            reload=True,
            target="tests.fake:app",
        )

        assert captured["target"] == "tests.fake:app"
        assert captured["host"] == "127.0.0.1"
        assert captured["port"] == 8002
        assert captured["log_level"] == "warning"
        assert isinstance(captured["watch_dirs"], list)

    def test_extra_kwargs_with_reload_raise_typeerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Boom-trap both delegation paths — TypeError must fire before
        # either is reached.
        import bretzel.server._dev as _dev
        import uvicorn

        def boom(*_a, **_kw):  # type: ignore[no-untyped-def]
            raise AssertionError("delegation should not be reached")

        monkeypatch.setattr(_dev, "run_dev_server", boom)
        monkeypatch.setattr(uvicorn, "run", boom)

        from bretzel import Bretzel

        app = Bretzel(secret_key=_SECRET, mode="dev")

        # ``reload_dirs`` is one of the kwargs uvicorn used to accept
        # on its --reload path ; we now reject it loudly so users see
        # the escape hatch instead of silent breakage.
        with pytest.raises(TypeError, match="watchfiles.run_process"):
            app.run(
                host="127.0.0.1",
                port=8003,
                reload=True,
                target="tests.fake:app",
                reload_dirs=["src/"],
            )

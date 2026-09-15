"""Unit tests for :class:`bretzel.render.screen.Screen`.

Screen is **server-authoritative** : it reads the ``bz_screen`` cookie off
the active request and exposes real Python bools, so an app can branch the
nav with a plain ``if Screen().is_mobile:`` (a ClientState field would return
a ClientBinding whose ``__bool__`` raises by design — cf.
screen-responsive-nav.md, the pivot on 2026-07-13).
"""

from __future__ import annotations

from typing import Any

from bretzel import Screen
from bretzel.render.context import RenderContext, use_context


class _FakeRequest:
    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = cookies


class _StubApp:
    @property
    def theme(self) -> object:
        return object()

    @property
    def state_backend(self) -> Any:
        return None

    @property
    def debug(self) -> bool:
        return True


def _ctx(cookies: dict[str, str]) -> RenderContext:
    return RenderContext(app=_StubApp(), request=_FakeRequest(cookies))


class TestPublicSurface:
    def test_exported_top_level(self) -> None:
        import bretzel

        assert bretzel.Screen is Screen

    def test_fields_are_real_bools_not_bindings(self) -> None:
        # The whole point of the pivot : usable in a plain ``if``.
        with use_context(_ctx({"bz_screen": "1,1"})):
            s = Screen()
            assert s.is_mobile is True
            assert s.is_touch is True
            assert bool(s.is_mobile)  # would raise on a ClientBinding


class TestCookieParsing:
    def test_mobile_touch_from_cookie(self) -> None:
        with use_context(_ctx({"bz_screen": "1,0"})):
            s = Screen()
            assert s.is_mobile is True
            assert s.is_touch is False

    def test_desktop_non_touch_from_cookie(self) -> None:
        with use_context(_ctx({"bz_screen": "0,0"})):
            s = Screen()
            assert s.is_mobile is False
            assert s.is_touch is False


class TestFallback:
    def test_missing_cookie_is_desktop_non_touch(self) -> None:
        # First-ever hit : no cookie yet → documented desktop fallback.
        with use_context(_ctx({})):
            s = Screen()
            assert s.is_mobile is False
            assert s.is_touch is False

    def test_malformed_cookie_falls_back_safely(self) -> None:
        with use_context(_ctx({"bz_screen": "garbage"})):
            s = Screen()
            assert s.is_mobile is False
            assert s.is_touch is False

    def test_outside_render_context_is_desktop(self) -> None:
        # No active request (e.g. a background task) → safe desktop default,
        # never a crash.
        s = Screen()
        assert s.is_mobile is False
        assert s.is_touch is False

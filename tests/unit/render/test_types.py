"""Unit tests for ``bretzel.render.types``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bretzel.render.types import BretzelApp


class _FakeApp:
    """Minimal structural impl of :class:`BretzelApp` for tests."""

    def __init__(self) -> None:
        self._pages: list[Callable[..., Any]] = []
        self._error_handlers: dict[int, Callable[..., Any]] = {}

    @property
    def theme(self) -> object:
        return object()

    @property
    def state_backend(self) -> Any:
        return None

    @property
    def sse_broker(self) -> Any:
        return None

    @property
    def debug(self) -> bool:
        return True


class TestProtocol:
    def test_structural_match(self) -> None:
        # ``runtime_checkable`` lets us assert structural conformance
        # without inheritance.
        app: BretzelApp = _FakeApp()
        assert isinstance(app, BretzelApp)

    def test_missing_attribute_fails(self) -> None:
        class Incomplete:
            # Missing every attribute ; isinstance must report False.
            pass

        # ``runtime_checkable`` Protocol's ``isinstance`` only checks
        # presence of declared methods/properties on the class — and
        # since ``Incomplete`` has none of the registry attrs, we expect
        # it to fail.
        assert not isinstance(Incomplete(), BretzelApp)

    def test_collections_addressable(self) -> None:
        # Render code reaches into _pages / _error_handlers / etc. ;
        # verify those are real attributes on a conforming impl.
        app = _FakeApp()
        assert isinstance(app._pages, list)
        assert isinstance(app._error_handlers, dict)

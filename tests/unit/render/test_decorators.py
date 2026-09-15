"""Unit tests for ``bretzel.render.decorators.*``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from bretzel.render.decorators import (
    LayoutMeta,
    PageMeta,
    RefreshableHandle,
    error_page,
    layout,
    page,
    refresh,
    refreshable,
)

# ───────────────────────────────────────────────────────────────────────────
# Fake app fixture
# ───────────────────────────────────────────────────────────────────────────


class _StubApp:
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


# ───────────────────────────────────────────────────────────────────────────
# @page
# ───────────────────────────────────────────────────────────────────────────


class TestPage:
    def test_basic_mark(self) -> None:
        # Free decorator — only MARKS the function ; registration is the
        # app's job at ``include`` time (see ``TestInclude``).
        @page("/cart")
        def cart_page() -> None:
            pass

        meta = cart_page._bz_page  # type: ignore[attr-defined]
        assert isinstance(meta, PageMeta)
        assert meta.path == "/cart"
        assert meta.methods == ("GET",)

    def test_optional_kwargs(self) -> None:
        def my_layout() -> None: ...
        def my_shell(*a: object, **k: object) -> str: return ""

        @page(
            "/x",
            layout=my_layout,
            title="X",
            description="x desc",
            shell=my_shell,
            methods=("GET", "post"),  # accepts lowercase
        )
        def x_page() -> None: ...

        meta = x_page._bz_page  # type: ignore[attr-defined]
        assert meta.layout is my_layout
        assert meta.title == "X"
        assert meta.description == "x desc"
        assert meta.shell is my_shell
        # Methods are normalised to upper-case.
        assert meta.methods == ("GET", "POST")

    def test_signature_captured(self) -> None:
        @page("/users/{id}")
        def user_page(id: int, prefs: object) -> None: ...

        meta = user_page._bz_page  # type: ignore[attr-defined]
        params = list(meta.signature.parameters)
        assert params == ["id", "prefs"]

    def test_returns_function_unchanged(self) -> None:
        @page("/")
        def home() -> str:
            return "ok"

        # The decorator must not wrap — we still call the original.
        assert home() == "ok"


# ───────────────────────────────────────────────────────────────────────────
# @layout
# ───────────────────────────────────────────────────────────────────────────


class TestLayout:
    def test_bare_form(self) -> None:
        # Free decorator — marks ``_bz_layout`` ; layouts need no
        # registration (resolved by direct reference + parent chain).
        @layout
        def app_layout() -> None: ...

        meta = app_layout._bz_layout  # type: ignore[attr-defined]
        assert isinstance(meta, LayoutMeta)
        assert meta.name == "app_layout"
        assert meta.parent is None

    def test_parent_form(self) -> None:
        @layout
        def app_layout() -> None: ...

        @layout(parent=app_layout)
        def admin_layout() -> None: ...

        assert admin_layout._bz_layout.parent is app_layout  # type: ignore[attr-defined]

    def test_returns_function_unchanged(self) -> None:
        @layout
        def my_layout() -> str: return "ok"

        assert my_layout() == "ok"


# ───────────────────────────────────────────────────────────────────────────
# @refreshable
# ───────────────────────────────────────────────────────────────────────────


class TestRefreshable:
    def test_returns_handle(self) -> None:
        def cart_summary() -> None: ...

        handle = refreshable(cart_summary)
        assert isinstance(handle, RefreshableHandle)
        assert handle.fn is cart_summary

    def test_id_stable_across_calls(self) -> None:
        def cart_summary() -> None: ...

        a = refreshable(cart_summary)
        b = refreshable(cart_summary)
        assert a.id == b.id

    def test_id_short(self) -> None:
        def cart_summary() -> None: ...

        h = refreshable(cart_summary)
        # `refresh_<8 hex>` — 16 characters total.
        assert h.id.startswith("refresh_")
        assert len(h.id) == 16

    def test_callable_passes_through(self) -> None:
        # Zone VARIADIQUE : depuis le 2026-09-04, un paramètre NOMMÉ est
        # refusé à la décoration (le rafraîchissement appelle la poignée
        # nue, cf. ``test_a_zone_takes_no_parameter``). La propriété
        # testée ici — hors contexte, ``__call__`` transmet à ``fn`` — est
        # inchangée ; seule la signature du cobaye devait l'être.
        def cart_summary(**kwargs: int) -> int:
            return kwargs["x"] * 2

        h = refreshable(cart_summary)
        assert h(x=21) == 42

    def test_zone_qualname_is_addressable(self) -> None:
        # Registration is implicit now : no ``app._refreshables`` dict.
        # The realtime route resolves the zone back through
        # ``sys.modules`` via this ``module::qualname`` wire id, the
        # same scheme as action handlers.
        def cart_summary() -> None: ...

        h = refreshable(cart_summary)
        assert h.zone_qualname == (
            f"{cart_summary.__module__}::{cart_summary.__qualname__}"
        )

    def test_refresh_outside_context_is_noop(self) -> None:
        def f() -> None: ...

        h = refreshable(f)
        # Outside any RenderContext — must not raise.
        refresh(h)

    def test_refresh_inside_context_queues(self) -> None:
        from bretzel.render.context import RenderContext, use_context

        app = _StubApp()

        def f() -> None: ...

        h = refreshable(f)
        ctx = RenderContext(app=app, request=object())
        with use_context(ctx):
            refresh(h)
            refresh(h)  # idempotent
        assert ctx.refresh_queue == [h]


# ───────────────────────────────────────────────────────────────────────────
# @error_page
# ───────────────────────────────────────────────────────────────────────────


class TestError:
    def test_basic_mark(self) -> None:
        # Free decorator — marks ``_bz_error_page`` (+ a ``_bz_page`` for the
        # render pipeline) ; the app picks it up at ``include`` time.
        @error_page(404)
        def not_found() -> None: ...

        assert not_found._bz_error_page.status_code == 404  # type: ignore[attr-defined]
        assert not_found._bz_page is not None  # type: ignore[attr-defined]

    @pytest.mark.parametrize("code", [99, 600, 0, -1])
    def test_invalid_status_rejected(self, code: int) -> None:
        with pytest.raises(ValueError, match="HTTP status"):
            error_page(code)

    def test_returns_function_unchanged(self) -> None:
        @error_page(404)
        def nf() -> str: return "not found"

        assert nf() == "not found"


# ───────────────────────────────────────────────────────────────────────────
# Bretzel.include — discovery of marked pages / error handlers
# ───────────────────────────────────────────────────────────────────────────


class TestInclude:
    @staticmethod
    def _app() -> Any:
        from bretzel import Bretzel

        return Bretzel(secret_key="x" * 32)

    def test_registers_page_from_callable(self) -> None:
        app = self._app()

        @page("/cart")
        def cart() -> None: ...

        app.include(cart)
        assert cart in app._pages

    def test_registers_error_not_as_page(self) -> None:
        app = self._app()

        @error_page(404)
        def nf() -> None: ...

        app.include(nf)
        # Error handlers land in ``_error_handlers``, never on the route
        # table — even though they carry a ``_bz_page`` for rendering.
        assert app._error_handlers[404] is nf
        assert nf not in app._pages

    def test_scans_module_and_iterable(self) -> None:
        import sys
        import types

        app = self._app()

        @page("/a")
        def a() -> None: ...

        @page("/b")
        def b() -> None: ...

        mod = types.ModuleType("tmp_include_mod")
        mod.a = a  # type: ignore[attr-defined]
        sys.modules["tmp_include_mod"] = mod
        try:
            app.include(mod, [b])  # module + iterable in one call
        finally:
            del sys.modules["tmp_include_mod"]
        assert a in app._pages
        assert b in app._pages

    def test_idempotent(self) -> None:
        app = self._app()

        @page("/once")
        def once() -> None: ...

        app.include(once)
        app.include(once)
        assert app._pages.count(once) == 1

    def test_unknown_module_name_raises(self) -> None:
        app = self._app()
        with pytest.raises(ValueError, match="can't resolve module"):
            app.include("definitely.not.imported.module")

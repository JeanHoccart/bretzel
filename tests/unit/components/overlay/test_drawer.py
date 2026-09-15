"""Unit tests for :class:`bretzel.components.overlay.drawer.Drawer`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.overlay.drawer import Drawer
from bretzel.state import field


class TestImperativeAPI:
    """Write-only `.open()` / `.close()` / `.toggle()` methods —
    returns Alpine source compatible with ``on_click=``. Branches on
    construction-time presence of a ClientBinding for ``open``."""

    def test_open_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            d = Drawer(title="X")
            out = d.open()
        assert "dispatchEvent" in out
        assert "bz-open" in out
        assert d.id in out
        # Must NOT carry a binding write — no binding was passed.
        assert "$bz.state" not in out

    def test_close_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            d = Drawer(title="X")
            out = d.close()
        assert "dispatchEvent" in out
        assert "bz-close" in out
        assert d.id in out

    def test_toggle_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            d = Drawer(title="X")
            out = d.toggle()
        assert "dispatchEvent" in out
        assert "bz-toggle" in out
        assert d.id in out

    def test_open_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                d = Drawer(title="X", open=ui_state.flag)
                out = d.open()
        # Write-through : returns the binding setter, no DOM dispatch.
        assert "$bz.state.UI.default.flag" in out
        assert "= true" in out
        assert "dispatchEvent" not in out

    def test_close_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                d = Drawer(title="X", open=ui_state.flag)
                out = d.close()
        assert "$bz.state.UI.default.flag" in out
        assert "= false" in out
        assert "dispatchEvent" not in out

    def test_toggle_with_binding_writes_through(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                d = Drawer(title="X", open=ui_state.flag)
                out = d.toggle()
        path = "$bz.state.UI.default.flag"
        # ClientBinding.toggle returns "<path> = !<path>".
        assert out == f"{path} = !{path}"
        assert "dispatchEvent" not in out

    def test_bz_listeners_present_on_root_local(self) -> None:
        # Local bz-data case : listeners flip the local ``open``.
        with render_isolated():
            d = Drawer(title="X")
            el = d.render()
        assert el.attrs.get("bz-on:bz-open") == "open = true"
        assert el.attrs.get("bz-on:bz-close") == "open = false"
        assert el.attrs.get("bz-on:bz-toggle") == "open = !open"

    def test_bz_listeners_present_on_root_bound(self) -> None:
        # Bound case : listeners flip the binding path directly. Both
        # paths (binding setter via .open() AND incoming bz-open
        # dispatch) converge on the same write.
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            flag: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                d = Drawer(title="X", open=ui_state.flag)
                el = d.render()
        path = "$bz.state.UI.default.flag"
        assert el.attrs.get("bz-on:bz-open") == f"{path} = true"
        assert el.attrs.get("bz-on:bz-close") == f"{path} = false"
        assert el.attrs.get("bz-on:bz-toggle") == f"{path} = !{path}"

    def test_methods_return_str_consumable_by_on_click(self) -> None:
        # Sanity : the returned values are plain strings (same shape as
        # ClientBinding.set/toggle) so they slot into on_click=
        # transparently.
        with render_isolated():
            d = Drawer(title="X")
            assert isinstance(d.open(),   str)
            assert isinstance(d.close(),  str)
            assert isinstance(d.toggle(), str)

    def test_root_always_carries_id_even_without_binding_or_handler(self) -> None:
        # Regression : external callers `.open()` from a sibling button
        # dispatch via `document.getElementById(self.id)`. If the root
        # doesn't carry `id=` (because the base heuristic
        # `_needs_identity` returns False without bindings or events),
        # the dispatch silently fails. The override in Drawer must
        # force identity unconditionally.
        with render_isolated():
            d = Drawer(title="X")
            el = d.render()
        assert el.attrs.get("id") == d.id
        # And the id referenced in `.open()` matches.
        assert d.id in d.open()

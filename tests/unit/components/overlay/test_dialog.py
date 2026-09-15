"""Unit tests for :class:`bretzel.components.overlay.dialog.Dialog`."""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.overlay.dialog import Dialog
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.state import field


def _make(*, title="Confirm", width="md", dismissible=True, persistent=False):
    return Dialog(
        title=title,
        width=width,
        dismissible=dismissible,
        persistent=persistent,
    )


class TestStructure:
    def test_root_uses_contents_for_layout_neutrality(self) -> None:
        # ``contents`` collapses the wrapper from the layout flow so
        # the dialog's ``fixed`` children anchor against the viewport,
        # not the wrapper's box.
        with render_isolated():
            with _make() as d:
                Text("body")
            out = serialize(d.render())
        assert 'class="contents"' in out

    def test_panel_has_dialog_aria(self) -> None:
        with render_isolated():
            with _make() as d:
                Text("body")
            out = serialize(d.render())
        assert 'role="dialog"' in out
        assert 'aria-modal="true"' in out

    def test_title_renders_in_header(self) -> None:
        with render_isolated():
            with _make(title="Delete?") as d:
                Text("body")
            out = serialize(d.render())
        assert "<h2" in out
        assert ">Delete?<" in out

    def test_aria_labelledby_points_at_title(self) -> None:
        with render_isolated():
            with _make(title="Delete?") as d:
                Text("body")
            out = serialize(d.render())
        # The title <h2> has an id ; the panel's ``aria-labelledby``
        # references it.
        assert "_title" in out
        assert "aria-labelledby=" in out

    def test_no_header_when_no_title_and_persistent(self) -> None:
        with render_isolated():
            with _make(title=None, persistent=True, dismissible=False) as d:
                Text("body")
            out = serialize(d.render())
        # No header → no <h2>, no close button (the IconButton is the
        # only place the X icon shows up).
        assert "<h2" not in out
        assert 'icon="lucide:x"' not in out


class TestRuntimeWiring:
    def test_bz_data_open_flag(self) -> None:
        with render_isolated():
            with _make() as d:
                Text("body")
            out = serialize(d.render())
        assert 'bz-data="{open: false}"' in out

    def test_open_initial_state(self) -> None:
        with render_isolated():
            with Dialog(open=True, title="X") as d:
                Text("body")
            out = serialize(d.render())
        assert 'bz-data="{open: true}"' in out

    def test_body_scroll_lock_via_helper(self) -> None:
        with render_isolated():
            with _make() as d:
                Text("body")
            out = serialize(d.render())
        # The root's bz-effect engages $bz.helpers.scrollLock while
        # open and releases it on close.
        assert "$bz.helpers.scrollLock" in out

    def test_focus_trap_on_panel(self) -> None:
        with render_isolated():
            with _make() as d:
                Text("body")
            out = serialize(d.render())
        assert "$bz.helpers.focusTrap" in out

    def test_dismissible_wires_escape_and_backdrop_click(self) -> None:
        with render_isolated():
            with _make() as d:
                Text("body")
            out = serialize(d.render())
        # Escape-to-close registered at mount via the runtime helper.
        assert "$bz.helpers.escapeKey" in out
        # Backdrop has bz-on:click → close. Persistent overrides this.
        assert out.count("open = false") + out.count("open = false") >= 1

    def test_persistent_drops_dismiss_handlers(self) -> None:
        with render_isolated():
            with _make(persistent=True) as d:
                Text("body")
            out = serialize(d.render())
        assert "$bz.helpers.escapeKey" not in out

    def test_closed_dialog_hidden_via_data_open(self) -> None:
        # FOUC strategy (V3) : an initially-closed dialog carries
        # ``data-open="false"`` on backdrop / container / panel, and the
        # theme's ``data-[open=false]:invisible`` keeps them hidden + inert
        # until the runtime flips ``data-open`` (the bz-data root is also
        # visibility:hidden via the shell's pre-boot anti-flash rule, which
        # stops applying once ``bz-ready`` lands).
        with render_isolated():
            with _make() as d:
                Text("body")
            out = serialize(d.render())
        assert out.count('data-open="false"') >= 3
        # ``=`` is entity-escaped inside the class attribute value.
        assert "data-[open=false]:invisible" in out


class TestWidths:
    @pytest.mark.parametrize(
        ("width", "expected"),
        [
            ("sm",   "max-w-sm"),
            ("md",   "max-w-md"),
            ("lg",   "max-w-lg"),
            ("xl",   "max-w-xl"),
            ("full", "max-w-none"),
        ],
    )
    def test_panel_width_class(self, width: str, expected: str) -> None:
        with render_isolated():
            with _make(width=width) as d:
                Text("body")
            out = serialize(d.render())
        assert expected in out


class TestOpenBinding:
    """``open=`` accepts the framework's universal three shapes :
    literal, server-resolved, ClientBinding. When a binding is passed,
    the dialog reads + writes the binding path instead of carrying its
    own ``x-data`` flag — same primitive as every other reactive prop
    in the framework."""

    def _make_binding(self):
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            is_open: bool = field(default=False)

        # Field access only returns a ClientBinding inside a rendering
        # scope ; that's how the framework distinguishes handlers from
        # render-time access.
        with rendering_scope():
            return UI(), UI()

    def test_literal_open_uses_local_bz_data(self) -> None:
        with render_isolated():
            d = Dialog(title="X", open=False)
            el = d.render()
        assert el.attrs.get("bz-data") == "{open: false}"
        assert "open" in el.attrs.get("bz-effect", "")

    def test_literal_open_true_initial_flag(self) -> None:
        with render_isolated():
            d = Dialog(title="X", open=True)
            el = d.render()
        assert el.attrs.get("bz-data") == "{open: true}"

    def test_binding_open_reads_binding_path(self) -> None:
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            is_open: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                d = Dialog(title="X", open=ui_state.is_open)
                el = d.render()
        # No local scope — the binding owns the state, expressions
        # address the global store directly.
        assert "bz-data" not in el.attrs
        # bz-effect, bz-show, escape handler all read the binding path.
        path = "$bz.state.UI.default.is_open"
        assert path in el.attrs.get("bz-effect", "")
        assert path in el.attrs.get("bz-init", "")  # escapeKey closure

    def test_binding_open_close_button_writes_binding(self) -> None:
        # The header's close X must write to the binding path, not to
        # a local ``open`` flag. We check the rendered tree (not the
        # serialized string) so we don't fight HTML attribute escaping.
        from bretzel.state import ClientState
        from bretzel.state.scopes.client import rendering_scope

        class UI(ClientState, persist="memory"):
            is_open: bool = field(default=False)

        with render_isolated():
            with rendering_scope():
                ui_state = UI()
                d = Dialog(title="X", open=ui_state.is_open)
                # Serialise to a string then count occurrences of the
                # raw expression escaped — the serializer encodes ``=``
                # as ``=`` in attribute values.
                out = serialize(d.render())
        path = "$bz.state.UI.default.is_open"
        # Backdrop click closes the dialog → binding path written.
        assert path in out
        assert "= false" in out or "= false" in out


class TestComposedClickHandlers:
    """``on_click=[server_callable, alpine_string]`` chains both on
    one click. Universal Component-level mechanism — works for every
    component, every event. Used for optimistic-close patterns where
    a server action fires + a client-side state mutation fires in
    the same click."""

    def _handler(self) -> None:
        pass

    def test_list_with_callable_and_string_emits_both_attrs(self) -> None:
        from bretzel.components.actions.button import Button
        with render_isolated():
            b = Button("X", on_click=[self._handler, "x = 1"], size="sm")
            out = serialize(b.render())
        # Server route (hx-post) AND client expression (bz-on:),
        # both on the same button — V3 wire.
        assert "hx-post=" in out
        assert "bz-on:click=" in out

    def test_list_with_only_strings_emits_only_client_expr(self) -> None:
        from bretzel.components.actions.button import Button
        with render_isolated():
            b = Button("X", on_click=["x = 1"], size="sm")
            out = serialize(b.render())
        assert "bz-on:click=" in out
        assert "hx-post=" not in out

    def test_list_strings_joined_with_semicolon(self) -> None:
        # Multiple client expressions chain via ``;`` — the V3
        # evaluator runs the statements in order.
        from bretzel.components.actions.button import Button
        with render_isolated():
            b = Button("X", on_click=["foo = 1", "bar = 2"], size="sm")
        assert b.render().attrs.get("bz-on:click") == "foo = 1; bar = 2"

    def test_two_callables_in_list_raises(self) -> None:
        from bretzel.components.actions.button import Button
        from bretzel.components.base.attrs import ComponentUsageError
        with render_isolated():
            with pytest.raises(ComponentUsageError):
                Button(
                    "X",
                    on_click=[self._handler, self._handler],
                    size="sm",
                )


class TestDualServerEvents:
    """A single overlay wires BOTH ``on_open`` and ``on_close`` to the
    server : the first rides the root ``hx-post``, the second is
    relocated onto a hidden carrier listening ``from:#<root>`` (one
    element hosts one hx-post — cf. ``ALLOW_MULTI_SERVER_EVENTS``)."""

    @staticmethod
    def _open() -> None: ...
    @staticmethod
    def _close() -> None: ...

    def test_both_server_handlers_emit_two_posts(self) -> None:
        with render_isolated():
            d = Dialog(title="X", id="dlg", on_open=self._open,
                       on_close=self._close)
            with d:
                Text("body")
            out = serialize(d.render())
        # Root hosts on_open ; carrier hosts on_close listening from root.
        assert out.count("hx-post=") == 2
        assert 'hx-trigger="open"' in out
        assert 'hx-trigger="close from:#dlg"' in out
        # Carrier is hidden and findable.
        assert 'id="dlg__onclose"' in out
        assert "hidden" in out

    def test_close_only_server_handler_stays_on_root(self) -> None:
        # A single server handler (even close) never needs a carrier.
        with render_isolated():
            d = Dialog(title="X", id="dlg", on_close=self._close)
            with d:
                Text("body")
            out = serialize(d.render())
        assert out.count("hx-post=") == 1
        assert "from:#" not in out
        assert "__onclose" not in out

    def test_open_server_close_client_no_carrier(self) -> None:
        # Mixed : server open + client-string close → close is a plain
        # ``bz-on:close`` on the root, no carrier, single hx-post.
        with render_isolated():
            d = Dialog(title="X", id="dlg", on_open=self._open,
                       on_close="x = 1")
            with d:
                Text("body")
            out = serialize(d.render())
        assert out.count("hx-post=") == 1
        assert "bz-on:close=" in out
        assert "__onclose" not in out


class TestStandalone:
    def test_dialog_without_trigger_renders(self) -> None:
        # Dialog is purely visual — opened from elsewhere via the
        # imperative API (``.open()``) or a ClientBinding. The root
        # never carries a built-in trigger wrapper.
        with render_isolated():
            d = Dialog(title="X", open=True)
            with d:
                Text("body")
            out = serialize(d.render())
        assert "<button" in out  # only the close X (dismissible default)
        # No trigger wrapper element should ever appear.
        assert 'aria-haspopup="dialog"' not in out


class TestImperativeAPI:
    """Write-only `.open()` / `.close()` / `.toggle()` methods —
    returns Alpine source compatible with ``on_click=``. Branches on
    construction-time presence of a ClientBinding for ``open``."""

    def test_open_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            d = Dialog(title="X")
            out = d.open()
        assert "dispatchEvent" in out
        assert "bz-open" in out
        assert d.id in out
        # Must NOT carry a binding write — no binding was passed.
        assert "$bz.state" not in out

    def test_close_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            d = Dialog(title="X")
            out = d.close()
        assert "dispatchEvent" in out
        assert "bz-close" in out
        assert d.id in out

    def test_toggle_without_binding_returns_dispatch(self) -> None:
        with render_isolated():
            d = Dialog(title="X")
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
                d = Dialog(title="X", open=ui_state.flag)
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
                d = Dialog(title="X", open=ui_state.flag)
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
                d = Dialog(title="X", open=ui_state.flag)
                out = d.toggle()
        path = "$bz.state.UI.default.flag"
        # ClientBinding.toggle returns "<path> = !<path>".
        assert out == f"{path} = !{path}"
        assert "dispatchEvent" not in out

    def test_bz_listeners_present_on_root_local(self) -> None:
        # Local bz-data case : listeners flip the local ``open``.
        with render_isolated():
            d = Dialog(title="X")
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
                d = Dialog(title="X", open=ui_state.flag)
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
            d = Dialog(title="X")
            assert isinstance(d.open(),   str)
            assert isinstance(d.close(),  str)
            assert isinstance(d.toggle(), str)

    def test_root_always_carries_id_even_without_binding_or_handler(self) -> None:
        # Regression : external callers `.open()` from a sibling button
        # dispatch via `document.getElementById(self.id)`. If the root
        # doesn't carry `id=` (because the base heuristic
        # `_needs_identity` returns False without bindings or events),
        # the dispatch silently fails. The override in Dialog must
        # force identity unconditionally.
        with render_isolated():
            d = Dialog(title="X")
            el = d.render()
        assert el.attrs.get("id") == d.id
        # And the id referenced in `.open()` matches.
        assert d.id in d.open()

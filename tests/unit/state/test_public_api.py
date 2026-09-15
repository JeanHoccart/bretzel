"""Smoke tests for ``bretzel.state`` public surface.

Verifies that the documented imports actually resolve and behave as
declared in spec ``02-state.md``.
"""

from __future__ import annotations

import bretzel.state as st
from bretzel.state import field
from bretzel.state.persistence.memory import MemoryBackend

# ───────────────────────────────────────────────────────────────────────────
# Public names exist
# ───────────────────────────────────────────────────────────────────────────


class TestPublicNames:
    def test_documented_names_present(self) -> None:
        # The "core 7" from the spec.
        assert hasattr(st, "ServerState")
        assert hasattr(st, "ClientState")
        assert hasattr(st, "field")
        assert hasattr(st, "computed")
        assert hasattr(st, "validator")
        assert hasattr(st, "form_value")
        # Pre-scoped server bases.
        for name in ("PageState", "SessionState", "UserState", "AppState"):
            assert hasattr(st, name)


# ───────────────────────────────────────────────────────────────────────────
# Pre-scoped sugar bases
# ───────────────────────────────────────────────────────────────────────────


class TestPrescopedBases:
    def test_session_alias(self) -> None:
        class Cart(st.SessionState):
            x: int = field(default=0)

        assert Cart.__scope__ == "session"

    def test_user_alias(self) -> None:
        class Prefs(st.UserState):
            theme: str = field(default='light')

        assert Prefs.__scope__ == "user"

    def test_app_alias(self) -> None:
        class Flags(st.AppState):
            on: bool = field(default=False)

        assert Flags.__scope__ == "app"

    def test_page_alias(self) -> None:
        class Draft(st.PageState):
            body: str = field(default='')

        assert Draft.__scope__ == "page"

    def test_can_still_use_serverstate_with_scope(self) -> None:
        # The original explicit form remains valid alongside the aliases.
        class Cart(st.ServerState, scope="session"):
            x: int = field(default=0)

        assert Cart.__scope__ == "session"


# ───────────────────────────────────────────────────────────────────────────
# state.form_value — escape hatch
# ───────────────────────────────────────────────────────────────────────────


class TestFormValue:
    def test_outside_registry_returns_default(self) -> None:
        assert st.form_value("anything") is None
        assert st.form_value("anything", default=42) == 42

    def test_missing_key_returns_default(self) -> None:
        registry = st.StateRegistry(MemoryBackend(), form_data={"a": "1"})
        with st.use_registry(registry):
            assert st.form_value("missing", default="fallback") == "fallback"

    def test_existing_value_returned_raw(self) -> None:
        registry = st.StateRegistry(MemoryBackend(), form_data={"name": "alice"})
        with st.use_registry(registry):
            assert st.form_value("name") == "alice"

    def test_cast_int(self) -> None:
        registry = st.StateRegistry(MemoryBackend(), form_data={"age": "42"})
        with st.use_registry(registry):
            assert st.form_value("age", cast=int) == 42

    def test_cast_bool_html_semantics(self) -> None:
        registry = st.StateRegistry(
            MemoryBackend(),
            form_data={
                "checkbox_on": "on",
                "checkbox_true": "true",
                "checkbox_yes": "yes",
                "checkbox_1": "1",
                "checkbox_off": "",
                "checkbox_false_str": "false",
            },
        )
        with st.use_registry(registry):
            assert st.form_value("checkbox_on", cast=bool) is True
            assert st.form_value("checkbox_true", cast=bool) is True
            assert st.form_value("checkbox_yes", cast=bool) is True
            assert st.form_value("checkbox_1", cast=bool) is True
            assert st.form_value("checkbox_off", cast=bool) is False
            assert st.form_value("checkbox_false_str", cast=bool) is False

    def test_default_with_cast_skipped_when_missing(self) -> None:
        # Cast is not applied to the default — that's an implementation
        # detail but test it explicitly so we don't drift.
        registry = st.StateRegistry(MemoryBackend(), form_data={})
        with st.use_registry(registry):
            assert st.form_value("missing", default="not cast", cast=int) == "not cast"


# ───────────────────────────────────────────────────────────────────────────
# End-to-end mini-flow — wire everything together
# ───────────────────────────────────────────────────────────────────────────


class TestEndToEnd:
    def test_session_roundtrip(self) -> None:
        # Two requests in sequence : second one sees the first's state.
        import asyncio

        backend = MemoryBackend()

        class Cart(st.SessionState):
            coupon: str = field(default='')

        # ── Request 1 : mutate, commit ──
        r1 = st.StateRegistry(backend, session_id="sid_42")
        with st.use_registry(r1):
            cart = Cart()
            cart.coupon = "SUMMER"
        asyncio.new_event_loop().run_until_complete(r1.commit())

        # ── Request 2 : resolve, observe carry-over ──
        r2 = st.StateRegistry(backend, session_id="sid_42")
        with st.use_registry(r2):
            cart2 = asyncio.new_event_loop().run_until_complete(
                r2.resolve(Cart)
            )
            assert cart2.coupon == "SUMMER"

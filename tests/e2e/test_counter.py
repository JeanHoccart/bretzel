"""End-to-end Counter tests : real browser, real server, every scope.

These exist because we shipped a counter app where every server
endpoint returned 200 — and nothing visibly worked. The whole
``btn → POST → response → DOM update`` chain is a chain of
interfaces : Alpine directive matching, HTMX OOB swap acceptance,
the JS runtime hydrating ``$bz.state``, the persistence backend
wired through ``Alpine.effect``. Every interface had a bug, every
unit test passed.

The pattern below is intentionally repetitive : one test per scope,
each one scripted so it would have caught a specific bug we hit in
production-like conditions.
"""

from __future__ import annotations

import pytest

# Skip everything in this file if Playwright isn't available.
playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import BrowserContext, Page, expect


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _row(page: Page, label: str):
    """Locate the row vstack whose label is exactly ``label``.

    Each row in the counter is structured as ::

        <div class="...vstack..."> ← row root
          <span ...weight="semibold">{label}</span>
          <span ...color="muted">{subtitle}</span>
          <span class="...font-bold">{count}</span>     ← value
          <div class="...hstack...">                    ← buttons
            <button>−</button>
            <button>Reset</button>
            <button>+</button>
          </div>
        </div>

    We anchor on the label span (exact match — partial match would
    grab "ClientState" for all three persist modes) and walk up to
    the parent div, which is the row root.
    """
    label_span = page.get_by_text(label, exact=True).first
    return label_span.locator("xpath=..")


def _value_span(row) -> "playwright.Locator":
    """The ``<span class="font-bold">{count}</span>`` carrying the value."""
    # Three font-bold spans live inside each row : the label
    # (font-semibold actually, not font-bold), and the value
    # (size 3xl + font-bold). The value is the only one with both
    # ``font-bold`` AND no ``font-semibold``. Match by class
    # signature : 3xl + font-bold.
    return row.locator("span.text-3xl.font-bold").first


def _click_button(row, label: str) -> None:
    # ``get_by_role`` scoped to the row matches buttons by accessible
    # name (the visible label), and is exact by default.
    row.get_by_role("button", name=label, exact=True).click()


# ───────────────────────────────────────────────────────────────────────────
# Module variable — Python global, server-driven via @refreshable
# ───────────────────────────────────────────────────────────────────────────


class TestModuleVariable:
    """Asserts : button click → POST → handler mutates global → OOB swap → DOM."""

    def test_initial_value_is_zero(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, "Module variable")
        expect(_value_span(row)).to_have_text("0")

    def test_increment_persists_across_clicks_in_same_page(
        self, page: Page, server_url: str
    ) -> None:
        page.goto(server_url)
        row = _row(page, "Module variable")
        for _ in range(3):
            _click_button(row, "+")
        expect(_value_span(row)).to_have_text("3")

    def test_decrement_goes_negative(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, "Module variable")
        for _ in range(2):
            _click_button(row, "−")
        expect(_value_span(row)).to_have_text("-2")

    def test_reset_zeros_the_counter(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, "Module variable")
        _click_button(row, "+")
        _click_button(row, "+")
        _click_button(row, "Reset")
        expect(_value_span(row)).to_have_text("0")

    def test_increment_dispatches_exactly_one_post_per_click(
        self, page: Page, server_url: str
    ) -> None:
        # Regression : the morph hook used to call ``Alpine.initTree``
        # on the trigger button after every swap, attaching duplicate
        # listeners → +2/+3/+4 per click. We assert one POST per click.
        posts: list[str] = []
        page.on(
            "request",
            lambda req: posts.append(req.url) if req.method == "POST" else None,
        )
        page.goto(server_url)
        row = _row(page, "Module variable")
        # Wait for initial render to settle before counting.
        expect(_value_span(row)).to_have_text("0")
        posts.clear()
        _click_button(row, "+")
        expect(_value_span(row)).to_have_text("1")
        assert len(posts) == 1, f"expected exactly 1 POST, got {len(posts)} : {posts}"


# ───────────────────────────────────────────────────────────────────────────
# AppState — process-wide server state
# ───────────────────────────────────────────────────────────────────────────


class TestAppState:
    def test_increment_persists_across_clicks(
        self, page: Page, server_url: str
    ) -> None:
        page.goto(server_url)
        row = _row(page, "AppState")
        for _ in range(2):
            _click_button(row, "+")
        expect(_value_span(row)).to_have_text("2")

    def test_app_state_is_shared_across_browser_contexts(
        self, browser, server_url: str
    ) -> None:
        # AppState is process-wide : a second visitor sees the same
        # number. Two distinct contexts = two "visitors".
        ctx_a = browser.new_context()
        ctx_b = browser.new_context()
        try:
            page_a = ctx_a.new_page()
            page_a.goto(server_url)
            row_a = _row(page_a, "AppState")
            _click_button(row_a, "+")
            _click_button(row_a, "+")
            expect(_value_span(row_a)).to_have_text("2")

            page_b = ctx_b.new_page()
            page_b.goto(server_url)
            row_b = _row(page_b, "AppState")
            # Same count visible to a "different visitor".
            expect(_value_span(row_b)).to_have_text("2")
        finally:
            ctx_a.close()
            ctx_b.close()


# ───────────────────────────────────────────────────────────────────────────
# SessionState — per-session-cookie server state
# ───────────────────────────────────────────────────────────────────────────


class TestSessionState:
    def test_session_persists_across_reload(
        self, page: Page, server_url: str
    ) -> None:
        page.goto(server_url)
        row = _row(page, "SessionState")
        for _ in range(3):
            _click_button(row, "+")
        expect(_value_span(row)).to_have_text("3")

        page.reload()
        row = _row(page, "SessionState")
        # Same Bretzel_session cookie → registry resolves the same
        # SessionCounter instance → 3 still on screen.
        expect(_value_span(row)).to_have_text("3")

    def test_session_isolated_across_contexts(
        self, browser, server_url: str
    ) -> None:
        # Distinct contexts = distinct cookies = distinct sessions.
        ctx_a = browser.new_context()
        ctx_b = browser.new_context()
        try:
            page_a = ctx_a.new_page()
            page_a.goto(server_url)
            for _ in range(4):
                _click_button(_row(page_a, "SessionState"), "+")
            expect(_value_span(_row(page_a, "SessionState"))).to_have_text("4")

            page_b = ctx_b.new_page()
            page_b.goto(server_url)
            # Fresh session → fresh counter.
            expect(_value_span(_row(page_b, "SessionState"))).to_have_text("0")
        finally:
            ctx_a.close()
            ctx_b.close()


# ───────────────────────────────────────────────────────────────────────────
# PageState — per-page-render server state
# ───────────────────────────────────────────────────────────────────────────


class TestPageState:
    def test_clicks_compound_within_same_page(
        self, page: Page, server_url: str
    ) -> None:
        # Regression : page scope used to drop the value after every
        # request, so clicks always showed 1. The ``X-Bretzel-Page-ID``
        # echo wires the registry to the same row across actions.
        page.goto(server_url)
        row = _row(page, "PageState")
        for _ in range(3):
            _click_button(row, "+")
        expect(_value_span(row)).to_have_text("3")

    def test_reload_resets_to_zero(self, page: Page, server_url: str) -> None:
        # Reload → new ``bz-page-<uuid>`` → fresh PageCounter row.
        page.goto(server_url)
        row = _row(page, "PageState")
        _click_button(row, "+")
        _click_button(row, "+")
        expect(_value_span(row)).to_have_text("2")

        page.reload()
        row = _row(page, "PageState")
        expect(_value_span(row)).to_have_text("0")


# ───────────────────────────────────────────────────────────────────────────
# ClientState — three persist modes, every one client-pure (zero round-trip)
# ───────────────────────────────────────────────────────────────────────────


class _ClientStateAssertions:
    """Mixin : assert that NO POST happens during the click sequence.

    This is the hard guarantee for ``ClientState`` : the whole point
    of the binding methods (``count.increment()`` etc.) is that the
    mutation lives client-side.
    """

    @staticmethod
    def _no_post_during(page: Page, action) -> None:
        posts: list[str] = []
        page.on(
            "request",
            lambda req: posts.append(req.url) if req.method == "POST" else None,
        )
        action()
        # Give Alpine a tick to flush ; if a POST were going to fire
        # (regression), it'd already be queued by now.
        page.wait_for_timeout(50)
        assert posts == [], (
            f"ClientState mutation must not contact the server, "
            f"got POSTs : {posts}"
        )


class TestClientStateMemory(_ClientStateAssertions):
    LABEL = 'ClientState (persist="memory")'

    def test_increment_does_not_post(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, self.LABEL)
        expect(_value_span(row)).to_have_text("0")
        self._no_post_during(page, lambda: _click_button(row, "+"))
        expect(_value_span(row)).to_have_text("1")

    def test_state_lost_on_reload(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, self.LABEL)
        for _ in range(3):
            _click_button(row, "+")
        expect(_value_span(row)).to_have_text("3")
        page.reload()
        row = _row(page, self.LABEL)
        expect(_value_span(row)).to_have_text("0")


class TestClientStateSession(_ClientStateAssertions):
    LABEL = 'ClientState (persist="session")'

    def test_increment_does_not_post(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, self.LABEL)
        expect(_value_span(row)).to_have_text("0")
        self._no_post_during(page, lambda: _click_button(row, "+"))
        expect(_value_span(row)).to_have_text("1")

    def test_persists_across_reload_in_same_tab(
        self, page: Page, server_url: str
    ) -> None:
        # Regression : the ``Alpine.effect`` that writes to
        # sessionStorage on mutation was missing — F5 dropped state.
        page.goto(server_url)
        row = _row(page, self.LABEL)
        for _ in range(3):
            _click_button(row, "+")
        expect(_value_span(row)).to_have_text("3")
        page.reload()
        row = _row(page, self.LABEL)
        expect(_value_span(row)).to_have_text("3")


class TestClientStateLocal(_ClientStateAssertions):
    LABEL = 'ClientState (persist="local")'

    def test_increment_does_not_post(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, self.LABEL)
        expect(_value_span(row)).to_have_text("0")
        self._no_post_during(page, lambda: _click_button(row, "+"))
        expect(_value_span(row)).to_have_text("1")

    def test_persists_across_reload(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, self.LABEL)
        _click_button(row, "+")
        _click_button(row, "+")
        expect(_value_span(row)).to_have_text("2")
        page.reload()
        row = _row(page, self.LABEL)
        expect(_value_span(row)).to_have_text("2")

    def test_decrement_works(self, page: Page, server_url: str) -> None:
        page.goto(server_url)
        row = _row(page, self.LABEL)
        for _ in range(3):
            _click_button(row, "−")
        expect(_value_span(row)).to_have_text("-3")

    def test_reset_zeros_the_counter(
        self, page: Page, server_url: str
    ) -> None:
        page.goto(server_url)
        row = _row(page, self.LABEL)
        for _ in range(5):
            _click_button(row, "+")
        _click_button(row, "Reset")
        expect(_value_span(row)).to_have_text("0")


# ───────────────────────────────────────────────────────────────────────────
# Cross-cutting smoke : every row visible, every value zero, no console errors
# ───────────────────────────────────────────────────────────────────────────


class TestPageSmoke:
    def test_all_seven_rows_present_with_initial_zeros(
        self, page: Page, server_url: str
    ) -> None:
        page.goto(server_url)
        for label in (
            "Module variable",
            "AppState",
            "SessionState",
            "PageState",
            'ClientState (persist="memory")',
            'ClientState (persist="session")',
            'ClientState (persist="local")',
        ):
            expect(_value_span(_row(page, label))).to_have_text("0")

    def test_no_console_errors_on_load(
        self, page: Page, server_url: str
    ) -> None:
        # Regression : a stale bundle / Alpine evaluation error used
        # to spam the console with ``ClientCounter is not defined`` ;
        # the runtime silently dropped state hydration.
        errors: list[str] = []
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(server_url, wait_until="networkidle")
        # Filter favicon 404s — irrelevant DevTools noise.
        relevant = [e for e in errors if "favicon" not in e.lower()]
        assert relevant == [], f"console errors at load : {relevant}"

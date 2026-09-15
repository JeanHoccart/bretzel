"""End-to-end regression : a teleported dropdown item's server action must
keep firing AFTER the board has refreshed.

Guards the ``bindTeleport`` htmx-processing fix (traps.md § "Teleported
``hx-post`` mort après un refresh"). Before the fix, the very first
``Move`` fired the POST (htmx's observer caught the first projection) but
every subsequent one was dead : the refresh re-projected the panel clone
under ``<body>`` via ``scan`` only, never ``htmx.process`` — so the item's
``hx-post`` had no htmx handler and the click fired only the client
``bz-dropdown-pick`` (menu closes), never the server round-trip.

Boots ``tests.e2e.apps.board_app:app`` via the ``kanban_url`` session
fixture — a test-owned board, not the kanban demo (migrated 2026-08-16).
"""

from __future__ import annotations

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect


def _column_count(page: Page, heading: str) -> int:
    """Read the badge count rendered next to a column heading."""
    return page.evaluate(
        """(heading) => {
            const h = [...document.querySelectorAll('h3')]
                .find(e => e.textContent.trim() === heading);
            if (!h) return -1;
            const badge = h.parentElement.querySelector('span');
            return badge ? parseInt(badge.textContent.trim(), 10) : -1;
        }""",
        heading,
    )


def _move_first_card(page: Page) -> list[str]:
    """Open the first card's ⋮ menu, click ``Move``, return the POST urls
    fired by that click."""
    posts: list[str] = []
    page.on(
        "request",
        lambda req: posts.append(req.url) if req.method == "POST" else None,
    )
    page.locator('[aria-haspopup="menu"]').first.click()
    move = page.locator('button:visible', has_text="Move").first
    expect(move).to_be_visible(timeout=1500)
    move.click()
    page.wait_for_timeout(400)
    return posts


class TestDropdownActionAfterRefresh:
    def test_first_move_fires_server_action(
        self, page: Page, kanban_url: str
    ) -> None:
        # Baseline : the very first Move always worked, even pre-fix.
        page.goto(kanban_url, wait_until="networkidle")
        before = _column_count(page, "In progress")
        posts = _move_first_card(page)
        assert any("move_task" in u for u in posts), (
            f"first Move must POST move_task, got : {posts}"
        )
        expect(page.get_by_text("In progress")).to_be_visible()
        assert _column_count(page, "In progress") == before + 1

    def test_move_still_fires_after_a_refresh(
        self, page: Page, kanban_url: str
    ) -> None:
        # The regression : a Move whose panel was RE-PROJECTED by the
        # first move's board refresh. Pre-fix this fired zero POSTs.
        page.goto(kanban_url, wait_until="networkidle")

        # First move — refreshes the board (re-projects every panel clone).
        page.locator('[aria-haspopup="menu"]').first.click()
        m1 = page.locator('button:visible', has_text="Move").first
        expect(m1).to_be_visible(timeout=1500)
        m1.click()
        # Wait for the board swap to land : To do count drops from 2 to 1.
        expect(page.locator("h3", has_text="To do")).to_be_visible()
        page.wait_for_function(
            """() => {
                const h = [...document.querySelectorAll('h3')]
                    .find(e => e.textContent.trim() === 'To do');
                const b = h && h.parentElement.querySelector('span');
                return b && b.textContent.trim() === '1';
            }""",
            timeout=2000,
        )

        # Second move — on a re-projected clone. Capture its POSTs.
        posts: list[str] = []
        page.on(
            "request",
            lambda req: posts.append(req.url) if req.method == "POST" else None,
        )
        # The first card in DOM order is now the remaining To do card ;
        # moving it advances it into In progress.
        inprog_before = _column_count(page, "In progress")
        page.locator('[aria-haspopup="menu"]').first.click()
        m2 = page.locator('button:visible', has_text="Move").first
        expect(m2).to_be_visible(timeout=1500)
        m2.click()
        page.wait_for_timeout(500)

        assert any("move_task" in u for u in posts), (
            "Move AFTER a refresh must still POST move_task (teleport "
            f"clone lost its htmx wiring), got : {posts}"
        )
        # And the state actually changed (card advanced a column).
        assert _column_count(page, "In progress") == inprog_before + 1

    def test_delete_fires_after_a_refresh(
        self, page: Page, kanban_url: str
    ) -> None:
        # Same class of bug via the Delete item — a second teleported
        # action after the first one's refresh.
        page.goto(kanban_url, wait_until="networkidle")

        page.locator('[aria-haspopup="menu"]').first.click()
        page.locator('button:visible', has_text="Move").first.click()
        page.wait_for_timeout(500)

        posts: list[str] = []
        page.on(
            "request",
            lambda req: posts.append(req.url) if req.method == "POST" else None,
        )
        page.locator('[aria-haspopup="menu"]').first.click()
        delete = page.locator('button:visible', has_text="Delete").first
        expect(delete).to_be_visible(timeout=1500)
        delete.click()
        page.wait_for_timeout(500)

        assert any("delete_task" in u for u in posts), (
            f"Delete after a refresh must POST delete_task, got : {posts}"
        )

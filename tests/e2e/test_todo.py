"""End-to-end TODO tests — driven against a DEDICATED fixture app.

The app under test is ``tests/e2e/apps/todo_app.py`` (session fixture
``todo_url``), NOT ``examples/todo``. The example is free to evolve for
demo reasons ; this fixture is a stable, test-owned minimal TODO whose only
job is to exercise the framework contracts below. (The old suite drove the
example directly and silently died when the example was restructured — see
``tests/consistency/test_fixture_apps_import``.)

Contracts covered : add (form submit + Enter + server validator), toggle,
delete (icon-only affordance), pure-client filter (zero round-trip),
remaining counter, persistence across reload (SessionState + sessionStorage
filter), isolation across browser contexts.
"""

from __future__ import annotations

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect

# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


#: « La zone est POSÉE », pas seulement « le contenu est apparu ».
#: Deux conditions : aucune requête htmx en vol, et trois sondages
#: consécutifs sans une seule mutation du DOM. L'observateur est réarmé
#: par :func:`_settled` avant chaque attente.
_SETTLED_JS = """() => {
    if (document.querySelector('.htmx-request')) return false;
    if (!window.__bzSettle) {
        window.__bzSettle = {quiet: 0};
        new MutationObserver(() => { window.__bzSettle.quiet = 0; })
            .observe(document.body,
                     {childList: true, subtree: true, attributes: true});
    }
    window.__bzSettle.quiet += 1;
    return window.__bzSettle.quiet >= 3;
}"""


def _settled(page: Page) -> None:
    """Bloque jusqu'à ce que le sous-arbre échangé soit INTERACTIF.

    « Le label est visible » marque le moment où le fragment OOB atterrit
    dans le DOM — pas celui où ses lignes répondent à un clic. Entre les
    deux, un clic est perdu **en silence** : aucune erreur, aucun POST.

    Mesuré le 2026-08-16, A/B alterné dans le même process (cette machine
    dérive d'un facteur 2-3 entre deux runs, un avant/après séquentiel ne
    mesurerait qu'elle) : cocher la case juste après un ``_add`` aboutit
    **9 fois sur 20**, après ce point d'attente **20 fois sur 20**. Ce
    n'est pas une lenteur mais un tout-ou-rien — quand le POST part, le
    compteur bouge en 30 à 110 ms, très loin des 2 s accordées.

    Pourquoi le test ne peut pas s'en remettre à Playwright : ces cases
    exigent ``force=True``, parce que l'``<input>`` réel est masqué
    derrière la case stylée et que Playwright le juge donc non
    actionnable — ``check()`` nu lève ``TimeoutError`` 10 fois sur 10. Or
    ``force`` est précisément ce qui court-circuite les vérifications
    d'actionnabilité. Le point d'attente doit donc venir d'ici.
    """
    page.evaluate("() => { window.__bzSettle = null; }")
    page.wait_for_function(_SETTLED_JS, timeout=5000, polling=40)


def _add(page: Page, label: str) -> None:
    """Type ``label``, click Add, and wait for the zone to be interactive.

    Deux temps, et il faut les deux : le label visible dit que le swap a
    atterri, :func:`_settled` dit qu'on peut cliquer dedans.
    """
    page.locator('input[name="label"]').fill(label)
    page.get_by_role("button", name="Add", exact=True).click()
    expect(page.get_by_text(label, exact=True).first).to_be_visible(timeout=2000)
    _settled(page)


def _add_via_enter(page: Page, label: str) -> None:
    inp = page.locator('input[name="label"]')
    inp.fill(label)
    inp.press("Enter")
    expect(page.get_by_text(label, exact=True).first).to_be_visible(timeout=2000)
    _settled(page)


def _set_done(page: Page, label: str, *, done: bool = True) -> None:
    """Cocher / décocher la ligne ``label``, puis attendre que ça ait pris.

    Le ``_settled`` de sortie compte autant que celui d'entrée : un test
    qui coche puis clique aussitôt sur un onglet de filtre lisait l'état
    d'AVANT le toggle, et voyait une ligne encore active.
    """
    box = _checkbox_for(_item_row(page, label))
    box.check(force=True) if done else box.uncheck(force=True)
    _settled(page)


def _item_row(page: Page, label: str):
    """The row hstack whose label equals ``label`` exactly."""
    return page.get_by_text(label, exact=True).first.locator("xpath=..")


def _checkbox_for(row):
    return row.locator('input[type="checkbox"]')


def _delete_button_for(row):
    return row.get_by_role("button", name="Delete task", exact=True)


# ───────────────────────────────────────────────────────────────────────────
# Initial state
# ───────────────────────────────────────────────────────────────────────────


class TestEmptyState:
    def test_empty_message_visible(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        expect(page.get_by_text("No tasks yet — add one above.")).to_be_visible()

    def test_zero_tasks_remaining(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        expect(page.get_by_text("0 tasks remaining")).to_be_visible()

    def test_input_field_present(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        expect(page.locator('input[name="label"]')).to_be_visible()


# ───────────────────────────────────────────────────────────────────────────
# Add — server action (form submit + validator)
# ───────────────────────────────────────────────────────────────────────────


class TestAdd:
    def test_clicking_add_appends_item(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add(page, "Buy milk")
        expect(page.get_by_text("Buy milk", exact=True)).to_be_visible()
        expect(page.get_by_text("No tasks yet — add one above.")).not_to_be_visible()

    def test_pressing_enter_submits(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add_via_enter(page, "Walk the dog")
        expect(page.get_by_text("Walk the dog", exact=True)).to_be_visible()

    def test_three_items_in_order(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        for label in ("First", "Second", "Third"):
            _add(page, label)
        for label in ("First", "Second", "Third"):
            expect(page.get_by_text(label, exact=True)).to_be_visible()

    def test_remaining_counter_increments(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add(page, "Task A")
        expect(page.get_by_text("1 task remaining")).to_be_visible()
        _add(page, "Task B")
        expect(page.get_by_text("2 tasks remaining")).to_be_visible()

    def test_empty_label_rejected_by_server_validator(
        self, page: Page, todo_url: str
    ) -> None:
        # The HTML5 ``required`` blocks the submit browser-side ; the server
        # handler is the authoritative gate (it drops a blank label). Bypass
        # ``required`` client-side, submit, and assert nothing was appended.
        page.goto(todo_url)
        page.evaluate(
            "document.querySelector('input[name=\"label\"]')"
            ".removeAttribute('required')"
        )
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.get_by_text("No tasks yet — add one above.")).to_be_visible()


# ───────────────────────────────────────────────────────────────────────────
# Toggle — server round-trip
# ───────────────────────────────────────────────────────────────────────────


class TestToggle:
    def test_clicking_checkbox_marks_done(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add(page, "Buy milk")
        _set_done(page, "Buy milk")
        expect(page.get_by_text("0 tasks remaining")).to_be_visible()

    def test_unchecking_brings_back_active(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add(page, "Walk dog")
        _set_done(page, "Walk dog")
        expect(page.get_by_text("0 tasks remaining")).to_be_visible()
        # ``_set_done`` re-localise la ligne à chaque appel : le swap a
        # remplacé le nœud précédent.
        _set_done(page, "Walk dog", done=False)
        expect(page.get_by_text("1 task remaining")).to_be_visible()


# ───────────────────────────────────────────────────────────────────────────
# Delete — server round-trip, icon-only affordance
# ───────────────────────────────────────────────────────────────────────────


class TestDelete:
    def test_clicking_delete_removes_item(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add(page, "Buy milk")
        _add(page, "Walk dog")
        _delete_button_for(_item_row(page, "Buy milk")).click()
        expect(page.get_by_text("Buy milk", exact=True)).not_to_be_visible()
        expect(page.get_by_text("Walk dog", exact=True)).to_be_visible()
        expect(page.get_by_text("1 task remaining")).to_be_visible()

    def test_delete_last_returns_to_empty_state(
        self, page: Page, todo_url: str
    ) -> None:
        page.goto(todo_url)
        _add(page, "Solo")
        _delete_button_for(_item_row(page, "Solo")).click()
        expect(page.get_by_text("No tasks yet — add one above.")).to_be_visible()


# ───────────────────────────────────────────────────────────────────────────
# Filter — pure client (zero round-trip)
# ───────────────────────────────────────────────────────────────────────────


class TestFilter:
    def _seed_two_one_done(self, page: Page) -> None:
        _add(page, "Active task")
        _add(page, "Done task")
        _set_done(page, "Done task")
        expect(page.get_by_text("1 task remaining")).to_be_visible(timeout=2000)

    def test_filter_active_hides_completed_with_zero_posts(
        self, page: Page, todo_url: str
    ) -> None:
        page.goto(todo_url)
        self._seed_two_one_done(page)

        posts: list[str] = []
        page.on(
            "request",
            lambda req: posts.append(req.url) if req.method == "POST" else None,
        )
        page.get_by_role("button", name="Active", exact=True).click()
        page.wait_for_timeout(80)

        expect(page.get_by_text("Active task", exact=True)).to_be_visible()
        expect(page.get_by_text("Done task", exact=True)).not_to_be_visible()
        # The filter is a pure ClientState mutation — it must not POST.
        assert posts == [], f"Filter must not POST, got : {posts}"

    def test_filter_completed_hides_active(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        self._seed_two_one_done(page)
        page.get_by_role("button", name="Completed", exact=True).click()
        expect(page.get_by_text("Active task", exact=True)).not_to_be_visible()
        expect(page.get_by_text("Done task", exact=True)).to_be_visible()

    def test_filter_all_shows_everything(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        self._seed_two_one_done(page)
        page.get_by_role("button", name="Active", exact=True).click()
        page.get_by_role("button", name="All", exact=True).click()
        expect(page.get_by_text("Active task", exact=True)).to_be_visible()
        expect(page.get_by_text("Done task", exact=True)).to_be_visible()


# ───────────────────────────────────────────────────────────────────────────
# Persistence — SessionState (server) + sessionStorage (client filter)
# ───────────────────────────────────────────────────────────────────────────


class TestPersistence:
    def test_list_survives_reload(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add(page, "Persistent task")
        page.reload()
        expect(page.get_by_text("Persistent task", exact=True)).to_be_visible()

    def test_filter_survives_reload(self, page: Page, todo_url: str) -> None:
        page.goto(todo_url)
        _add(page, "A task")
        _add(page, "Another task")
        _set_done(page, "Another task")
        page.get_by_role("button", name="Active", exact=True).click()
        expect(page.get_by_text("Another task", exact=True)).not_to_be_visible()
        page.reload()
        # Filter restored from sessionStorage → still active.
        expect(page.get_by_text("A task", exact=True)).to_be_visible()
        expect(page.get_by_text("Another task", exact=True)).not_to_be_visible()

    def test_separate_contexts_have_separate_lists(
        self, browser, todo_url: str
    ) -> None:
        ctx_a = browser.new_context()
        ctx_b = browser.new_context()
        try:
            page_a = ctx_a.new_page()
            page_a.goto(todo_url)
            _add(page_a, "Visible only to A")
            expect(
                page_a.get_by_text("Visible only to A", exact=True)
            ).to_be_visible()

            page_b = ctx_b.new_page()
            page_b.goto(todo_url)
            # Different session cookie → different TodoStore (SessionState).
            expect(
                page_b.get_by_text("Visible only to A", exact=True)
            ).not_to_be_visible()
            expect(
                page_b.get_by_text("No tasks yet — add one above.")
            ).to_be_visible()
        finally:
            ctx_a.close()
            ctx_b.close()


# ───────────────────────────────────────────────────────────────────────────
# Tooltip — the icon-only delete affordance gets a hover label
# ───────────────────────────────────────────────────────────────────────────


class TestDeleteTooltip:
    # Regression guard for the empty->populated OOB-swap teleport gap : this
    # test adds ONE item then hovers, landing on the empty->1 swap where the
    # first tooltip's ``bz-teleport`` used to not project (role=tooltip stuck
    # at 0 until a later swap). Fixed at the swap boundary — see the mechanism
    # note in ``runtime/_src/05_bridge.js`` afterSwap.
    def test_hover_delete_button_reveals_tooltip(
        self, page: Page, todo_url: str
    ) -> None:
        page.goto(todo_url, wait_until="networkidle")
        _add(page, "Item one")
        _delete_button_for(_item_row(page, "Item one")).hover()
        tooltip = page.locator('[role="tooltip"]', has_text="Delete task")
        expect(tooltip).to_be_visible(timeout=2000)


# ───────────────────────────────────────────────────────────────────────────
# Smoke
# ───────────────────────────────────────────────────────────────────────────


class TestSmoke:
    def test_no_console_errors_on_load(self, page: Page, todo_url: str) -> None:
        errors: list[str] = []
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(todo_url, wait_until="networkidle")
        relevant = [e for e in errors if "favicon" not in e.lower()]
        assert relevant == [], f"console errors at load : {relevant}"

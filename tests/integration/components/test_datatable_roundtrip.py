"""``ui.datatable`` round-trip — the sort/page/search spine, on the bytes.

The unit tests pin :func:`apply_query` (a pure function) and the render
shape. Neither proves the thing the component actually promises : that
clicking a header **changes what comes back**. That path crosses the
whole spine — header button → signed action → ``sys.modules`` resolution
of a *state class* by reference → ``cycle_sort`` → dirty diff → the
enclosing zone's ``deps`` → OOB re-render with the new order baked in.

The state-by-reference hop is the novel piece and the fragile one : an
action's bound args must be JSON-serialisable, so the Datatable ships
``<module>::<QualName>`` and resolves it server-side. If that ever breaks,
the page still renders, the button still posts, and nothing moves — the
silent failure this file exists to make loud.

The app / zone / state live at MODULE level on purpose : the action route
resolves through ``sys.modules`` and would 404 on a ``<locals>`` class.
"""

from __future__ import annotations

import base64
import json
import re

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import field
from bretzel.components import DatatableState
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action

_SECRET = "x" * 32

# Deliberately NOT in alphabetical order, and with one blank score, so a
# sorted body is distinguishable from the source order at a glance.
ROWS = [
    {"id": 3, "name": "Grace", "score": 94},
    {"id": 1, "name": "Ada", "score": 99},
    {"id": 4, "name": "Nikola", "score": None},
    {"id": 2, "name": "Alan", "score": 97},
]

COLUMNS = [
    ui.column("name", label="Name", sortable=True),
    ui.column("score", label="Score", sortable=True),
]


class People(DatatableState):
    per_page: int = field(default=2)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable(deps=[People])
def people_zone() -> None:
    ui.datatable(state=People, columns=COLUMNS, rows=ROWS)


@page("/")
def home() -> None:
    people_zone()


_app.include(home)


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _names(html: str) -> list[str]:
    """The Name cells present in ``html``, in document order."""
    return [n for n in ("Ada", "Alan", "Grace", "Nikola")
            if f">{n}<" in html]


def _order(html: str) -> list[str]:
    """Same, but ordered by position rather than by the probe list."""
    found = [(html.index(f">{n}<"), n) for n in _names(html)]
    return [n for _, n in sorted(found)]


def _find_action(html: str, handler: str, needle: str = "") -> tuple[str, str, str]:
    """``(url, args_blob, sig)`` of the first action on ``handler``.

    ``needle`` narrows to a specific instance — the bound column key of a
    sort button, which lives INSIDE the base64 ``_args`` blob, not in the
    markup, so it is matched after decoding. Each attribute is matched
    independently because HTMX attribute ORDER is not part of the
    contract ; a regex spanning them would pin the emitter's field order
    rather than the wiring.
    """
    for chunk in html.split("<button")[1:]:
        head = chunk[:2000]
        if handler not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r'_args&quot;: &quot;([^&]*)&quot;', head)
        sig = re.search(r'data-bz-sig="([^"]*)"', head)
        if not (url and sig):
            continue
        blob = args.group(1) if args else ""
        if needle and needle not in str(
            json.loads(base64.b64decode(blob)) if blob else ""
        ):
            continue
        return url.group(1), blob, sig.group(1)
    raise AssertionError(f"no action found for {handler!r} / {needle!r}")


def _find_action_any(html: str, handler: str) -> tuple[str, str, str]:
    """Same as :func:`_find_action`, for a control that is not a button.

    The search box is an ``<input>``, so the button-scoped scan misses it.
    """
    for chunk in html.split("<input")[1:]:
        head = chunk[:2000]
        if handler not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r'_args&quot;: &quot;([^&]*)&quot;', head)
        sig = re.search(r'data-bz-sig="([^"]*)"', head)
        if url and sig:
            return url.group(1), (args.group(1) if args else ""), sig.group(1)
    raise AssertionError(f"no non-button action found for {handler!r}")


def _page_id(html: str) -> str:
    """The page instance uuid the shell hands to the runtime.

    ``PageState`` is keyed by it, and the browser echoes it back on every
    action via ``X-Bretzel-Page-ID``. A synthetic POST that omits it gets
    a FRESH state each time — which silently turns "the sort persists"
    into "the sort resets", so the tests carry it like a real client.
    """
    # ``data-bretzel-page-id`` et pas le JSON d'``hx-headers`` : les
    # deux portent la MÊME valeur, mais l'attribut nu est stable
    # tandis que le JSON dépend de son échappement — quatre copies de
    # cette ligne ont rougi le 2026-08-28 quand ``hx-headers`` est
    # passé en doubles quotes, sans qu'aucun comportement ne change.
    match = re.search(r'data-bretzel-page-id="([^"]+)"', html)
    assert match, "the shell must publish the page id for actions to reuse"
    return match.group(1)


def _post(client: TestClient, url: str, args: str, page: str,
          extra: dict | None = None):
    action_id = url.rsplit("/", 1)[-1]
    return client.post(
        url,
        headers={
            "X-Bz-Sig": sign_action(_app.config._action_key, action_id, args),
            HEADER_PAGE_ID: page,
        },
        data={"_args": args, **(extra or {})},
    )


# Each test opens its own ``TestClient`` and therefore its own page id,
# so the page-scoped query starts clean — no reset fixture needed. That
# is only true because ``_post`` carries the page id it was given rather
# than letting the middleware mint a new one.


# ───────────────────────────────────────────────────────────────────────────
# 1. The spine : a header click reorders the rows that come back
# ───────────────────────────────────────────────────────────────────────────


class TestSortRoundTrip:
    def test_header_click_reorders_the_rerendered_zone(self) -> None:
        with TestClient(_app) as client:
            initial = client.get("/").text
            # Source order, first page of two.
            assert _order(initial) == ["Grace", "Ada"]

            url, args, _ = _find_action(initial, "sort_by", "name")
            response = _post(client, url, args, _page_id(initial))

            assert response.status_code == 200
            body = response.text
            # Came back as an OOB swap of the same zone…
            assert "hx-swap-oob" in body
            # …with the rows in ascending name order.
            assert _order(body) == ["Ada", "Alan"]

    def test_second_click_reverses_and_third_restores_source_order(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/").text
            page = _page_id(html)
            url, args, _ = _find_action(html, "sort_by", "name")

            first = _post(client, url, args, page).text
            assert _order(first) == ["Ada", "Alan"]

            # The button's args are stable (module::Class + column key),
            # so the same POST is the same second click.
            second = _post(client, url, args, page).text
            assert _order(second) == ["Nikola", "Grace"]

            third = _post(client, url, args, page).text
            assert _order(third) == ["Grace", "Ada"], (
                "third click must return to SOURCE order — the neutral "
                "position is what a two-state toggle can never reach"
            )

    def test_blank_cells_stay_last_in_both_directions(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/").text
            page = _page_id(html)
            url, args, _ = _find_action(html, "sort_by", "score")

            ascending = _post(client, url, args, page).text
            assert "Nikola" not in _order(ascending), (
                "the None score must not lead the ascending page"
            )
            descending = _post(client, url, args, page).text
            assert "Nikola" not in _order(descending), (
                "…nor the descending one : reverse=True would flip blanks "
                "to the front if they rode a sort key instead of being "
                "partitioned out"
            )

    def test_bound_args_carry_the_state_by_reference(self) -> None:
        """The novel hop, asserted directly rather than through behaviour."""
        with TestClient(_app) as client:
            html = client.get("/").text
        _, args, _ = _find_action(html, "sort_by", "name")
        payload = json.loads(base64.b64decode(args))
        state_ref, column_key = payload["args"]
        assert column_key == "name"
        module, _, qualname = state_ref.partition("::")
        assert qualname == "People"
        assert module == __name__, (
            "the reference must address the SUBCLASS's module — pointing at "
            "bretzel.state would resolve the base class and every table on "
            "the page would share one query"
        )


# ───────────────────────────────────────────────────────────────────────────
# 2. Pagination and search ride the same spine
# ───────────────────────────────────────────────────────────────────────────


class TestPagerAndSearch:
    def test_pager_submits_its_page_and_the_zone_follows(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/").text
            assert _order(html) == ["Grace", "Ada"]

            url, args, _ = _find_action(html, "go_to_page")
            response = _post(client, url, args, _page_id(html),
                             {"bz_dt_page__People": "2"})

            assert response.status_code == 200
            assert _order(response.text) == ["Nikola", "Alan"]

    def test_search_narrows_and_sends_the_reader_back_to_page_one(self) -> None:
        """Both halves, because the second one is the easy thing to forget.

        Narrowing the result set while the reader sits on page 4 leaves
        them staring at an empty table — a bug that reads as data loss.
        """
        with TestClient(_app) as client:
            html = client.get("/").text
            page = _page_id(html)

            # Go to page 2 first, so "back to page 1" is observable.
            page_url, page_args, _ = _find_action(html, "go_to_page")
            moved = _post(client, page_url, page_args, page,
                          {"bz_dt_page__People": "2"})
            assert _order(moved.text) == ["Nikola", "Alan"]

            search_url, search_args, _ = _find_action_any(html, "search_for")
            narrowed = _post(client, search_url, search_args, page,
                             {"bz_dt_search__People": "a"})

            assert narrowed.status_code == 200
            # "Ada", "Alan", "Grace" and "Nikola" all contain an "a" —
            # 4 matches over 2 per page, and we are on the FIRST page.
            assert _order(narrowed.text) == ["Grace", "Ada"]

    def test_a_malformed_page_number_is_ignored_not_fatal(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/").text
            url, args, _ = _find_action(html, "go_to_page")
            response = _post(client, url, args, _page_id(html),
                             {"bz_dt_page__People": "not-a-number"})
        assert response.status_code in (200, 204), (
            "a tampered page value must not 500 — the pager is reachable "
            "from any client"
        )

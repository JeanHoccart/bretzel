"""``ui.datatable`` CSV export — the download route, on the bytes.

The export is the one path that leaves the action pipeline : a signed GET
whose response IS the file. That makes it the one path where the usual
safety nets do not apply, so this file pins all four things that could
go wrong quietly :

1. **It exports the whole result, not the page.** The bug writes itself :
   the component holds twenty rows, and a callable that ignores
   ``for_export`` returns exactly those.
2. **It follows the reader's current query.** Exporting the unfiltered
   table when the screen shows a filtered one is worse than no export.
3. **The CSV is well-formed for Excel.** A BOM (else accents mojibake on
   Windows) and conditional quoting per RFC 4180 — the two corrections
   the V1 implementation had already had to make.
4. **The link cannot be forged.** ``rows_ref`` names a callable the
   server will invoke ; without the signature this endpoint would call
   any module-level function on request.

Module level on purpose : the export addresses the state class and the
rows callable through ``sys.modules``.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import field
from bretzel.components import Datatable, DatatableState, Query, apply_query
from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action

_SECRET = "x" * 32

# A comma, an embedded quote and an accent — one row that exercises every
# escaping rule at once.
ROWS = [
    {"id": 1, "name": 'Ada, "the first"', "status": "open"},
    {"id": 2, "name": "Alan Turing", "status": "closed"},
    {"id": 3, "name": "Émilie du Châtelet", "status": "open"},
    {"id": 4, "name": "Grace Hopper", "status": "closed"},
    {"id": 5, "name": "Lise Meitner", "status": "open"},
]

COLUMNS = [
    ui.column("id", label="#", sortable=True),
    ui.column("name", label='Name "full"', sortable=True),
    ui.column("status", label="Status", filter=["open", "closed"]),
]


class People(DatatableState):
    per_page: int = field(default=2)


def load_people(q: Query) -> tuple[list, int]:
    return apply_query(ROWS, COLUMNS, q)


_app = Bretzel(secret_key=_SECRET, mode="dev")


@refreshable(deps=[People])
def people_zone() -> None:
    ui.datatable(state=People, columns=COLUMNS, rows=load_people,
                 exportable=True, export_filename="people.csv")


@page("/")
def home() -> None:
    people_zone()


_app.include(home)


def _export_url(html: str) -> str:
    match = re.search(r'href="(/_bretzel/datatable\.csv\?q=[^"]+)"', html)
    assert match, "the toolbar must carry a signed export link"
    return match.group(1).replace("&amp;", "&")


def _rows_of(csv_text: str) -> list[str]:
    return csv_text.lstrip("﻿").splitlines()


class TestExportContent:
    def test_exports_every_matching_row_not_the_page(self) -> None:
        """``per_page`` is 2. A CSV of 2 rows is the failure mode."""
        with TestClient(_app) as client:
            html = client.get("/").text
            body = client.get(_export_url(html)).text
        lines = _rows_of(body)
        assert len(lines) == 1 + len(ROWS)

    def test_header_row_uses_the_column_labels(self) -> None:
        with TestClient(_app) as client:
            body = client.get(_export_url(client.get("/").text)).text
        # The label holds a quote, so it is quoted and the quote doubled.
        assert _rows_of(body)[0] == '#,"Name ""full""",Status'

    def test_quotes_only_where_rfc4180_requires_it(self) -> None:
        with TestClient(_app) as client:
            body = client.get(_export_url(client.get("/").text)).text
        row = _rows_of(body)[1]
        # Comma AND quote inside → quoted, inner quotes doubled…
        assert '"Ada, ""the first"""' in row
        # …while the plain fields around it stay bare.
        assert row.startswith("1,")
        assert row.endswith(",open")

    def test_carries_a_bom_so_excel_keeps_the_accents(self) -> None:
        with TestClient(_app) as client:
            response = client.get(_export_url(client.get("/").text))
        assert response.text.startswith("﻿"), (
            "without the BOM, Excel on Windows reads UTF-8 as the system "
            "codepage and every accented name arrives mojibake"
        )
        assert "Émilie du Châtelet" in response.text

    def test_serves_as_a_named_attachment(self) -> None:
        with TestClient(_app) as client:
            response = client.get(_export_url(client.get("/").text))
        assert response.headers["content-type"].startswith("text/csv")
        assert response.headers["content-disposition"] == (
            'attachment; filename="people.csv"'
        )


def _page_id(html: str) -> str:
    # ``data-bretzel-page-id`` et pas le JSON d'``hx-headers`` : les
    # deux portent la MÊME valeur, mais l'attribut nu est stable
    # tandis que le JSON dépend de son échappement — quatre copies de
    # cette ligne ont rougi le 2026-08-28 quand ``hx-headers`` est
    # passé en doubles quotes, sans qu'aucun comportement ne change.
    match = re.search(r'data-bretzel-page-id="([^"]+)"', html)
    assert match
    return match.group(1)


def _post(client: TestClient, url: str, args: str, page_id: str,
          extra: dict | None = None):
    """Fire one action, carrying the page identity like a real client."""
    action_id = url.rsplit("/", 1)[-1]
    return client.post(
        url,
        headers={
            "X-Bz-Sig": sign_action(_app.config._action_key, action_id, args),
            HEADER_PAGE_ID: page_id,
        },
        data={"_args": args, **(extra or {})},
    )


def _find_action(html: str, handler: str, *bound: str):
    """``(url, args)`` of the control bound to ``handler`` with ``bound``.

    ``bound`` is matched against the DECODED positional args, in order
    and by EQUALITY — a filter value lives in the base64 blob, and a
    substring match would hit the wrong checkbox : every one of them
    carries the whole domain (``["open","closed"]``) as its last
    argument, so searching for "closed" anywhere in the blob unticks
    "open". That mistake is why this takes exact args.
    """
    import base64
    import json

    for chunk in re.split(r"<(?:button|input|div)", html)[1:]:
        head = chunk[:2500]
        if handler not in head:
            continue
        url = re.search(r'hx-post="([^"]+)"', head)
        args = re.search(r"_args&quot;: &quot;([^&]*)&quot;", head)
        if not url:
            continue
        blob = args.group(1) if args else ""
        decoded = json.loads(base64.b64decode(blob))["args"] if blob else []
        if bound and list(bound) != [a for a in decoded if isinstance(a, str)][1:]:
            continue
        return url.group(1), blob
    raise AssertionError(f"no action for {handler!r} / {bound!r}")


class TestExportFollowsTheQuery:
    def test_a_filtered_table_exports_only_the_filtered_set(self) -> None:
        """Exporting more than the screen shows is the expensive direction
        of this bug — you hand someone rows they had filtered out."""
        with TestClient(_app) as client:
            html = client.get("/").text
            page_id = _page_id(html)
            url = _export_url(html)
            assert len(_rows_of(client.get(url).text)) == 1 + 5

            # Le filtre s'applique a la FERMETURE du panneau : une seule
            # action, portant la selection finale via l'input caché du
            # combobox — donc le test poste ce que le navigateur
            # posterait, pas un clic par case. La valeur est le tableau
            # JSON que `bz-attr:value="JSON.stringify(value || [])"`
            # ecrit sur cet input.
            toggle_url, toggle_args = _find_action(html, "apply_filter")
            swapped = _post(
                client, toggle_url, toggle_args, page_id,
                {"bz_dt_filter__People__status": '["open"]'},
            )

            # The link is REGENERATED by the refresh that changed the
            # query — it carries the view, so the browser reads the fresh
            # one out of the OOB swap. Holding the old href is what a
            # stale-link bug would look like.
            body = client.get(_export_url(swapped.text)).text
            lines = _rows_of(body)
        assert len(lines) == 1 + 3, (
            f"expected the 3 open rows, got {len(lines) - 1}"
        )
        assert "closed" not in body

    def test_sort_order_reaches_the_file(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/").text
            page_id = _page_id(html)
            url = _export_url(html)
            assert _rows_of(client.get(url).text)[1].startswith("1,")

            # Sort by name descending : Lise Meitner leads.
            sort_url, sort_args = _find_action(html, "sort_by", "name")
            _post(client, sort_url, sort_args, page_id)          # asc
            swapped = _post(client, sort_url, sort_args, page_id)  # desc

            first = _rows_of(client.get(_export_url(swapped.text)).text)[1]
        assert "Lise Meitner" in first, f"got {first!r}"


class TestExportSecurity:
    def test_a_tampered_signature_is_refused(self) -> None:
        with TestClient(_app) as client:
            url = _export_url(client.get("/").text)
            forged = url.split("&sig=")[0] + "&sig=deadbeef"
            assert client.get(forged).status_code == 403

    def test_a_missing_signature_is_refused(self) -> None:
        with TestClient(_app) as client:
            url = _export_url(client.get("/").text)
            assert client.get(url.split("&sig=")[0]).status_code == 403

    def test_an_unsigned_payload_cannot_redirect_the_callable(self) -> None:
        """The signature covers the payload, so ``rows_ref`` is fixed.

        Without it, this endpoint would be a "call any module-level
        function of my choosing" gadget.
        """
        import base64
        import json

        evil = base64.urlsafe_b64encode(json.dumps({
            "s": f"{__name__}::People",
            "r": "os::system",
            "c": [["id", "#"]],
            "f": "x.csv",
        }).encode()).decode()
        with TestClient(_app) as client:
            assert client.get(
                f"/_bretzel/datatable.csv?q={evil}&sig=whatever"
            ).status_code == 403


class TestExportGuard:
    def test_exportable_over_a_plain_list_is_refused(self) -> None:
        """A list is gone by the time the endpoint runs, so the button
        would download one page — or nothing at all."""
        with render_isolated():
            with pytest.raises(ComponentUsageError, match="callable"):
                Datatable(state=People, columns=COLUMNS, rows=ROWS,
                          exportable=True, search=False)

"""In dev, a table row that renders differently from the same inputs raises.

A row taken back (``render/row_memo.py``) is only right if a column's
``render=`` depends on nothing but the row and the state it reads. One that
reads the time, a query or a global would be served stale in production, in
silence. In dev the memo rebuilds the row instead of serving it and compares:
the difference raises :class:`RowMismatchError`, naming the row.
"""

from __future__ import annotations

import itertools

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.render.row_memo import RowMismatchError

app = Bretzel(secret_key="memo-dev-secret-key-0123456789abcd", mode="dev")

TICKS = itertools.count()
ROWS = [{"id": i, "name": f"row {i}"} for i in range(3)]


def impure(value, row):
    return ui.text(f"{value} · {next(TICKS)}")  # a global, invisible to the tracking


def pure(value, row):
    return ui.text(value)


@page("/impure")
def impure_page() -> None:
    ui.table(columns=[ui.column("name", render=impure)], rows=ROWS, row_key="id")


@page("/pure")
def pure_page() -> None:
    ui.table(columns=[ui.column("name", render=pure)], rows=ROWS, row_key="id")


app.include(__name__)


def test_an_impure_row_raises_in_dev() -> None:
    with TestClient(app) as client:
        client.get("/impure")
        with pytest.raises(RowMismatchError, match=r"renders differently"):
            client.get("/impure")


def test_a_pure_row_passes_the_check() -> None:
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/pure").status_code == 200

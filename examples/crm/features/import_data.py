"""features/import_data — data: read an accounts CSV, judge it, write it.

Serves screen 9. Three stages, three functions, and the boundary between
them is what counts: **parsing** does not touch the database, **judging**
does not touch it either, **writing** is the only one that does — and it
refuses everything if a single row is bad.

That last point is not decorative caution: a half-applied import leaves
the user in front of a database they can neither keep nor replay.
"""

from __future__ import annotations

import csv
import io

from bretzel import Feature
from examples.crm.core.db import connect
from examples.crm.core.domain import (
    COUNTRY_KEYS,
    INDUSTRIES,
    OWNERS,
    SIZES,
    TODAY,
)

#: The expected columns, in order. It is also the template offered for
#: download — an import for which one cannot produce a valid example is an
#: import nobody gets right first time.
IMPORT_COLUMNS: tuple[str, ...] = (
    "name", "industry", "country", "city", "size", "arr", "owner",
)

#: An import's ceiling. Beyond it, the preview is no longer a preview and
#: the transaction becomes a long lock on a database the other screens are
#: reading.
IMPORT_MAX_ROWS = 500

EXAMPLE_CSV = (
    "name,industry,country,city,size,arr,owner\n"
    "Northway Retail Ltd,Retail,France,Lyon,Small,42000,Marc Dubois\n"
    "Northern Works,Manufacturing,Belgium,Ghent,Micro,9000,Sofia Rossi\n"
)


def parse_csv(raw: str) -> tuple[list[dict], str]:
    """``(rows, header error)``. Opens no connection.

    The header is checked BEFORE the rows: a file whose columns do not
    match would otherwise produce one error per row, all identical, and
    the user would read the same reproach five hundred times.
    """
    text = raw.lstrip("﻿")
    if not text.strip():
        return [], "The file is empty."
    reader = csv.DictReader(io.StringIO(text))
    header = tuple(reader.fieldnames or ())
    if header != IMPORT_COLUMNS:
        return [], (
            f"Colonnes attendues : {', '.join(IMPORT_COLUMNS)}. "
            f"Colonnes lues : {', '.join(header) if header else '(aucune)'}."
        )
    rows: list[dict] = []
    for index, row in enumerate(reader, start=2):
        if len(rows) >= IMPORT_MAX_ROWS:
            break
        rows.append({"_ligne": index, **{k: (row.get(k) or "").strip()
                                         for k in IMPORT_COLUMNS}})
    return rows, ""


def judge(rows: list[dict], owner: str | None) -> list[dict]:
    """Annotate every row with an ``_error`` — empty when it is good.

    The verdict lives ON the row rather than in a separate list: the
    preview is a table, and an error that is not in the row it concerns
    forces the reader to count again.

    ``owner`` scopes the write, and does so by REFUSING rather than
    rewriting: silently forcing every row's owner would mean a file
    prepared for a colleague imports onto oneself without saying
    anything. It is the CRM's only place where the scoping bears on a
    write, and the refusal is what makes it visible.
    """
    judged: list[dict] = []
    for row in rows:
        problems: list[str] = []
        if not row["name"]:
            problems.append("empty name")
        if row["industry"] not in INDUSTRIES:
            problems.append(f"unknown industry “{row['industry']}”")
        if row["country"] not in COUNTRY_KEYS:
            problems.append(f"unknown country “{row['country']}”")
        if row["size"] not in SIZES:
            problems.append(f"unknown size “{row['size']}”")
        if row["owner"] not in OWNERS:
            problems.append(f"unknown owner \u201c{row['owner']}\u201d")
        elif owner is not None and row["owner"] != owner:
            problems.append(f"hors portefeuille « {row['owner']} »")
        if not row["arr"].isdigit():
            problems.append("ARR is not a number")
        judged.append({**row, "_error": " · ".join(problems)})
    return judged


def commit_rows(rows: list[dict], owner: str | None) -> int:
    """Write the rows in ONE transaction. Returns the number inserted.

    A single connection and a single ``commit``: five hundred isolated
    ``execute()`` are five hundred file openings and five hundred fsyncs.

    ⚠️ **The scoping is redone HERE**, although :func:`judge` has already
    checked it. It is not belt and braces: ``judge`` runs on the
    "Check" request and ``commit_rows`` on the "Import" one. Between
    the two, a director may have changed portfolio — and the ``_error``
    verdict the writer would take on trust was computed under another
    policy. The verdict EXPLAINS, the write ENFORCES.
    """
    if owner is not None:
        rows = [row for row in rows if row["owner"] == owner]
    payload = [
        (row["name"], row["industry"], row["country"], row["city"],
         row["size"], int(row["arr"]), row["owner"], TODAY.isoformat())
        for row in rows
    ]
    if not payload:
        return 0
    conn = connect()
    try:
        conn.executemany(
            "INSERT INTO accounts "
            "(name, industry, country, city, size, arr, owner, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
        conn.commit()
    finally:
        conn.close()
    return len(payload)


feature = Feature(
    name="import_data",
    kind="data",
    provides=[parse_csv, judge, commit_rows],
    uses=["db"],
)

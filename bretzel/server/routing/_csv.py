"""CSV writing, shared by both download paths.

Extracted from ``routing/datatable.py`` on 2026-09-02, when ``@download``
became the second consumer. The content does not change: these are the
two corrections the V1 implementation had already identified and that one
easily misses — the UTF-8 BOM, and letting ``csv.writer`` decide when to
quote.

Why it is here and not in ``core``: it only serves to answer a request.
Mounting it lower in the DAG would make the base layer carry an HTTP
output format.
"""

from __future__ import annotations

import csv
import io
from typing import Any

#: Excel on Windows reads a BOM-less UTF-8 CSV in the system code page,
#: so every accented name arrives as mojibake. One character repairs it,
#: and it is the most reported bug of every CSV export ever written.
BOM = "﻿"


def to_csv(rows: Any, columns: list[list[str]], read: Any) -> str:
    """RFC 4180 text: one header row, then one record per line.

    ``csv.writer`` carries the quoting rules (quote only when the value
    contains a delimiter, a quote or a newline; double an inner quote) —
    that is very precisely where hand-written exports go wrong.

    ``read`` is the cell-reading function. It is passed rather than
    imported so this module does not depend on the components:
    ``datatable`` gives it its ``read_cell`` (which handles objects,
    dicts and attributes), ``@download`` gives it a dict access.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([label or key for key, label in columns])
    for row in rows:
        writer.writerow([
            "" if (value := read(row, key)) is None else str(value)
            for key, _label in columns
        ])
    return BOM + buffer.getvalue()


def columns_of(rows: Any) -> list[list[str]]:
    """The columns DERIVED from a list of dicts — key and label equal.

    ⚠️ The order comes from the FIRST record, and the union of the keys
    is not taken: two dicts with different keys would give a table with
    holes and nobody could say which row is missing what. A heterogeneous
    shape calls for explicit columns — which is what ``ui.datatable``
    supplies on its side.
    """
    first = next(iter(rows), None)
    if first is None:
        return []
    if not isinstance(first, dict):
        raise TypeError(
            "@download: a list was returned but its first element is "
            f"not a dict ({type(first).__name__}). Return a list of dicts "
            "for a CSV, or build the ``Response`` yourself if the shape "
            "is something else."
        )
    return [[str(key), str(key)] for key in first]

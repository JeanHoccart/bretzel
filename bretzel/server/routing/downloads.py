"""Mounting the ``@download`` routes.

One route per marked function, as ``GET``, served as a file
(``Content-Disposition: attachment``). No signature in the URL — cf. the
decorator's docstring for the reason, which is the fundamental
difference from the datatable's export.
"""

from __future__ import annotations

import mimetypes
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any

from starlette.responses import Response

from bretzel.core import call_without_blocking
from bretzel.render.context import maybe_current_context
from bretzel.server.routing._csv import columns_of, to_csv
from bretzel.state.registry import use_registry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


#: The types the framework KNOWS, consulted BEFORE ``mimetypes``.
#:
#: ⚠️ ``mimetypes.guess_type`` is not reproducible: on Windows it reads
#: the REGISTRY (``HKCR``), so its answer depends on the software
#: installed on the machine. Measured on 2026-09-02 on a machine with
#: Excel: ``.csv`` → ``application/vnd.ms-excel``. On a Linux server
#: without Excel, the same code would have returned ``text/csv``.
#:
#: A response header that changes with the developer's workstation is a
#: silent failure mode: it works on your machine, it behaves otherwise in
#: production, and nothing says so. This table is what makes the output
#: deterministic for the formats Bretzel produces itself; ``mimetypes``
#: stays the fallback for everything else.
_KNOWN_TYPES: dict[str, str] = {
    ".csv": "text/csv; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _type_of(name: str, fallback: str) -> str:
    """``name``'s MIME type — known table, then ``mimetypes``, then default."""
    point = name.rfind(".")
    if point != -1:
        extension = name[point:].lower()
        if extension in _KNOWN_TYPES:
            return _KNOWN_TYPES[extension]
        guessed, _ = mimetypes.guess_type(name)
        if guessed:
            return guessed
    return fallback


def _read_dict_cell(row: Any, key: str) -> Any:
    return row.get(key)


def _coerce(value: Any, meta: Any) -> Response:
    """The value the function returned → an HTTP file response.

    Four accepted shapes, and the order of the tests matters: a
    ``Response`` passes BEFORE everything else, otherwise the escape
    hatch would not be one.
    """
    if isinstance(value, Response):
        return value

    if isinstance(value, bytes):
        body: Any = value
        default_type = "application/octet-stream"
    elif isinstance(value, str):
        body = value
        default_type = "text/plain; charset=utf-8"
    elif isinstance(value, list):
        body = to_csv(value, columns_of(value), _read_dict_cell)
        default_type = "text/csv; charset=utf-8"
    else:
        raise TypeError(
            f"@download({meta.path!r}) returned a {type(value).__name__}. "
            f"The accepted shapes are: list[dict] (→ CSV), str, bytes, or "
            f"a hand-built ``Response``. Returning anything else cannot be "
            f"guessed — a file has a type and an encoding, and inventing "
            f"them would download just anything under just any name."
        )

    # The type derived from the NAME wins over the shape's default: a
    # ``@download("/plan.svg")`` returning a ``str`` does serve SVG.
    return Response(
        body,
        media_type=meta.media_type or _type_of(meta.filename, default_type),
        headers={
            "Content-Disposition": f'attachment; filename="{meta.filename}"'
        },
    )


def register_download_routes(
    fastapi: FastAPI, bretzel_app: BretzelApp, functions: Any
) -> None:
    """Mount one ``GET`` route per function carrying ``_bz_download``."""
    for fn in functions:
        meta = getattr(fn, "_bz_download", None)
        if meta is None:      # pragma: no cover — the caller already filters
            continue
        _mount(fastapi, fn, meta)


def _mount(fastapi: FastAPI, fn: Any, meta: Any) -> None:
    """One closure per route — otherwise the N routes share the loop's
    last ``fn``, the classic trap."""

    @fastapi.get(meta.path, include_in_schema=False)
    async def _serve() -> Response:
        # The caller's code runs INSIDE the request's state registry,
        # as at the four other entry points (page render, action,
        # real-time refetch, datatable export). Without it, two
        # ``MyState()`` in the same function return two DIFFERENT objects
        # — measured on the export, which had been written bare.
        ctx = maybe_current_context()
        registry = getattr(ctx, "state_registry", None) if ctx else None
        with use_registry(registry) if registry is not None else nullcontext():
            # A function that fetches rows from a database is this
            # routable's reason to exist: awaited if ``async``, offloaded
            # onto the threadpool if a ``def`` — otherwise it freezes the
            # loop for the duration of the download (cf. ``core/invoke``).
            value = await call_without_blocking(fn)
        return _coerce(value, meta)

    _serve.__name__ = f"_download_{meta.filename.replace('.', '_')}"

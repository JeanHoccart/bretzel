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
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import Response

from bretzel.core import call_without_blocking
from bretzel.render.context import maybe_current_context
from bretzel.render.decorators.download import path_params_of
from bretzel.server.navigation import redirect_response, response_is_read_by_htmx
from bretzel.server.routing._csv import columns_of, to_csv
from bretzel.state.registry import use_registry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


#: The types the framework KNOWS, consulted BEFORE ``mimetypes``.
#:
#: ⚠️ ``mimetypes.guess_type`` is not reproducible: on Windows it reads
#: the REGISTRY (``HKCR``), so its answer depends on the software
#: installed on the machine. On a machine with Excel, ``.csv`` gives
#: ``application/vnd.ms-excel``; on a Linux server without Excel, the
#: same code returns ``text/csv``.
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


def attachment(name: str) -> str:
    """The ``Content-Disposition`` of a file named ``name``.

    The name can come from the request (``/files/{name}``): in the quoted
    ``filename`` it keeps only printable ASCII with no quote, backslash,
    slash or semicolon — it cannot close the string nor add a parameter —
    and the exact name rides percent-encoded in ``filename*`` (RFC 6266).
    """
    plain = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in '"\\/;' else "_" for ch in name
    ) or "download"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name, safe='')}"


def _read_dict_cell(row: Any, key: str) -> Any:
    return row.get(key)


def _path_arguments(raw: dict[str, Any], meta: Any) -> dict[str, Any] | None:
    """The route's path parameters, typed by the function's annotations
    (``int``, ``float``); ``None`` when one does not convert — a 404, as
    for an id that does not exist."""
    out: dict[str, Any] = {}
    for name, param in meta.signature.parameters.items():
        if name not in raw:
            continue
        value = raw[name]
        annotation = param.annotation
        if annotation in (int, float, "int", "float") and isinstance(value, str):
            try:
                value = (int if annotation in (int, "int") else float)(value)
            except ValueError:
                return None
        out[name] = value
    return out


def _coerce(value: Any, meta: Any, filename: str | None = None) -> Response:
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

    # The type derived from the DECLARED name wins over the shape's
    # default: a ``@download("/plan.svg")`` returning a ``str`` does serve
    # SVG. Declared, never requested: in ``/files/{name}`` the client
    # would otherwise pick it — ``/files/x.html`` served as HTML.
    return Response(
        body,
        media_type=meta.media_type or _type_of(meta.filename, default_type),
        headers={"Content-Disposition": attachment(filename or meta.filename)},
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


async def _produce(request: Request, fn: Any, meta: Any) -> Response:
    """Run the marked function and turn what it returns into the file."""
    # The caller's code runs INSIDE the request's state registry, as at
    # the other entry points (page render, action, real-time refetch,
    # datatable export). Without it, two ``MyState()`` in the same
    # function return two DIFFERENT objects.
    ctx = maybe_current_context()
    registry = getattr(ctx, "state_registry", None) if ctx else None
    with use_registry(registry) if registry is not None else nullcontext():
        # A function that fetches rows from a database is this routable's
        # reason to exist: awaited if ``async``, offloaded onto the
        # threadpool if a ``def`` — otherwise it freezes the loop for the
        # duration of the download (cf. ``core/invoke``).
        kwargs = _path_arguments(request.path_params, meta)
        if kwargs is None:
            return Response(status_code=404)
        value = await call_without_blocking(fn, **kwargs)
    filename = meta.filename
    if "{" in filename:
        filename = filename.format(**{k: kwargs[k] for k in path_params_of(meta.path)})
    return _coerce(value, meta, filename)


def _mount(fastapi: FastAPI, fn: Any, meta: Any) -> None:
    """One closure per route — otherwise the N routes share the loop's
    last ``fn``, the classic trap."""

    @fastapi.get(meta.path, include_in_schema=False)
    async def _serve(request: Request) -> Response:
        # A link in a boosted shell arrives through htmx, which would swap
        # the file into the page. Only a real navigation downloads, so
        # htmx is told to make one, before the function runs.
        if response_is_read_by_htmx(request):
            query = f"?{request.url.query}" if request.url.query else ""
            response = redirect_response(request, request.url.path + query)
        else:
            response = await _produce(request, fn, meta)
        # The same URL answers the file or the redirect: without this, the
        # browser's cache could hand htmx the file on a second click.
        response.headers.add_vary_header("HX-Request")
        return response

    _serve.__name__ = f"_download_{meta.filename.replace('.', '_')}"

"""``@download`` — the routable that returns a FILE, not a page.

Settled in session (``these-portee-2026-08-19.md`` § 7), shipped on
2026-09-02 ::

    @download("/customers.csv")
    async def customers_csv() -> list[dict]:
        return await db.customers()

Why this is not an action
-------------------------
An inherited constraint, already documented by the datatable's export:
an action's response is **swallowed by the bridge** and applied as a
``<bz-patch>``. A download has to BE the file. So it is a real link —
``ui.link("Export", href="/customers.csv")`` — and not an ``on_click=``.

Why it is NOT signed, unlike the datatable's export
---------------------------------------------------
That is the difference justifying the new routable, and it goes the right
way. The datatable's link carries in its URL the NAME of the function to
invoke (``rows_ref``, a ``module::qualname``), so it has to be signed —
without which the endpoint would become a "call the function of my
choice". From that it inherits being a **bearer capability**: whoever
holds the URL gets the rows, with no tie to the user and no expiry.

A ``@download`` carries none of that: the function is fixed at
DECORATION time, as for ``@page``. The URL decides nothing, so there is
nothing to sign — and the route goes through the same middleware as the
pages, so an app that protects its pages protects its downloads without
writing a line.

What the function may return
----------------------------
=================  ==========================================================
``list[dict]``     a CSV — headers derived from the first record's keys
``str``            the text as-is
``bytes``          the bytes as-is (a PDF, an image, a zip)
a ``Response``     the escape hatch — everything the rest does not cover
=================  ==========================================================

The file name and the MIME type are derived from the path
(``/customers.csv`` → ``customers.csv``, ``text/csv``), and both can be
overridden.

⚠️ What it does NOT do yet
--------------------------
``ui.datatable(exportable=True)`` is not rewired onto it. § 7 of the
thesis announced that "``exportable=True`` reduces to setting down a
``@download``"; it is not that simple, and it is better written down than
forced: the datatable's export needs the **reader's query** — the sort,
the filters, the search at the moment of the click — which does not exist
in a static route. That is what its signed payload carries. Rewiring them
requires deciding how a view travels to a ``@download``, and that is a
decision, not housekeeping.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bretzel.core.errors import BretzelError


class DownloadAlreadyMarkedError(BretzelError):
    """Two ``@download`` on the SAME function — the second would erase the first.

    Same refusal, same reason and same measurement as
    :class:`~bretzel.render.decorators.page.PageAlreadyMarkedError`: the
    mark lives on the function object, so a second decoration makes the
    first route unreachable, as a 404, without a word.
    """


@dataclass(frozen=True, slots=True)
class DownloadMeta:
    """Captured at decoration time, read by the route registrar."""

    path: str
    filename: str
    media_type: str | None
    signature: inspect.Signature


def _filename_of(path: str) -> str:
    """``/exports/customers.csv`` → ``customers.csv``.

    The last segment, and nothing else: a ``Content-Disposition``
    carrying slashes would leave the browser to choose, and browsers do
    not choose alike.
    """
    last = path.rstrip("/").rsplit("/", 1)[-1]
    return last or "download"


def download(
    path: str,
    *,
    filename: str | None = None,
    media_type: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function as the producer for a file served at ``GET path``."""
    if not path.startswith("/"):
        raise ValueError(
            f"@download({path!r}): a route path starts with '/'. Without "
            f"that the route mounts somewhere nobody guesses, and the "
            f"app's link returns 404."
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        meta = DownloadMeta(
            path=path,
            filename=filename or _filename_of(path),
            media_type=media_type,
            signature=inspect.signature(fn),
        )
        seen = getattr(fn, "_bz_download", None)
        if seen is not None and seen != meta:
            raise DownloadAlreadyMarkedError(
                f"{getattr(fn, '__qualname__', fn)!r} is already marked for "
                f"{seen.path!r} and is being re-marked for {path!r}. The "
                f"mark lives on the function object: the second "
                f"OVERWRITES the first, so {seen.path!r} would become a "
                f"404 without a word. To serve the same file in two "
                f"places, give it two functions."
            )
        fn._bz_download = meta  # type: ignore[attr-defined]
        return fn

    return decorator

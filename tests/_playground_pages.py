"""The playground's pages, discovered once and rendered ONCE per process.

Measured on 2026-11-03: three files rendered each of the 84 pages on
their own — ``test_example_pages_render`` three times (status, duplicate
``bz-id``, duplicate ``id``), ``test_emitted_classes_exist_in_source``
and ``test_no_two_pages_share_a_scope`` once more each. Five renders of
the same page, 3 min of the fast suite between them. Each of those tests
only READS a plain ``GET``: one render serves them all.

Under ``-n``, each worker renders the pages it needs once — never more.
"""

from __future__ import annotations

import atexit
import functools
import importlib
import pkgutil
from dataclasses import dataclass


def _discover() -> list[str]:
    """The paths the features declare, discovered and not listed.

    A list written by hand would only cover what one thought of putting
    in it — and the next page would be born outside every gate.
    """
    import examples.playground.features as features

    paths: set[str] = set()
    for mod_info in pkgutil.iter_modules(features.__path__):
        module = importlib.import_module(f"examples.playground.features.{mod_info.name}")
        path = getattr(module, "PATH", None)
        if isinstance(path, str):
            paths.add(path)
    return sorted(paths)


PLAYGROUND_PATHS: list[str] = _discover()


@dataclass(frozen=True, slots=True)
class Rendered:
    """What a plain ``GET`` of a page returned."""

    status: int
    html: str


def _serve():
    from starlette.testclient import TestClient

    from examples.playground.main import app

    # ``raise_server_exceptions=False``: the CODE, not an exception that
    # stops the parametrisation at the first broken page.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@functools.cache
def _client():
    served = _serve()
    client = next(served)
    # The lifespan's shutdown — the ``with`` above closes — at the end of
    # the process.
    atexit.register(served.close)
    return client


@functools.cache
def page(path: str) -> Rendered:
    """``path`` rendered once for the whole process."""
    response = _client().get(path, headers={"Accept-Encoding": "identity"})
    return Rendered(response.status_code, response.text)


def every_page() -> dict[str, Rendered]:
    return {path: page(path) for path in PLAYGROUND_PATHS}

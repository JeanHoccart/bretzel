"""Gate: a stored value its field no longer accepts is dropped, not a 500.

A stored row outlives the code that wrote it. ``ouvert: bool`` becomes
``ouvert: str``, a validator appears: the old value is refused by
``Field.__set__``. Until 2026-11-14 that refusal escaped the hydration,
and EVERY request reading the state answered 500 until somebody emptied
the store. In memory nobody saw it — a restart forgets everything — and
with ``state_url="sqlite:///…"`` it is the first type change.

Both sides: a value that fits is applied (the hydration still reads the
store), a value that does not is dropped with a warning naming the state,
the field and the value — on the page render and on
``StateRegistry.reload``, the two paths that read a stored row.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.state import AppState, field
from bretzel.state.registry import StateRegistry


class Reglages(AppState):
    ouvert: bool = field(default=True)
    largeur: int = field(default=320)


_app = Bretzel(secret_key="t" * 32, mode="dev")


@page("/")
def accueil() -> None:
    reglages = Reglages()
    ui.text(f"ouvert={reglages.ouvert} largeur={reglages.largeur}")


_app.include(accueil)


def _page_with(stored: dict, caplog) -> str:
    with TestClient(_app) as client:
        asyncio.new_event_loop().run_until_complete(
            _app.state_backend.save("app", "Reglages:default", stored)
        )
        with caplog.at_level(logging.WARNING, logger="bretzel.state"):
            response = client.get("/")
    assert response.status_code == 200, response.text[-1500:]
    return response.text


def test_a_value_of_the_old_type_is_dropped_and_said(caplog) -> None:
    html = _page_with({"ouvert": "todo", "largeur": 280}, caplog)
    assert "ouvert=True largeur=280" in html
    assert any("Reglages.ouvert" in r.getMessage() and "'todo'" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]


def test_a_value_that_fits_is_still_applied(caplog) -> None:
    html = _page_with({"ouvert": False, "largeur": 280}, caplog)
    assert "ouvert=False largeur=280" in html
    assert not [r for r in caplog.records if "no longer fits" in r.getMessage()]


def test_reload_drops_it_too(caplog) -> None:
    from bretzel.state import MemoryBackend

    backend = MemoryBackend()

    async def scenario() -> Reglages:
        await backend.save("app", "Reglages:default", {"ouvert": True, "largeur": "large"})
        return await StateRegistry(backend).reload(Reglages)

    with caplog.at_level(logging.WARNING, logger="bretzel.state"):
        reglages = asyncio.new_event_loop().run_until_complete(scenario())
    assert (reglages.ouvert, reglages.largeur) == (True, 320)
    assert any("Reglages.largeur" in r.getMessage() for r in caplog.records)

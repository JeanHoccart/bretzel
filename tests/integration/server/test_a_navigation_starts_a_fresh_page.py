"""Gate : une navigation commence une page NEUVE — son ``PageState`` aussi.

``state.md`` le promettait : « reset au F5 / à la navigation (nouveau
``page_id``) ». Le pont envoyait pourtant l'identifiant de la page
QUITTÉE avec chaque requête, lien boosté compris, et le serveur
retrouvait l'état d'avant. Mesuré dans le cockpit du produit : « Nouvelle
conversation » (``/atelier`` depuis ``/atelier?c=X``) laissait le fil X
à l'écran — un champ adressable absent de l'adresse gardait sa valeur.

Les deux versants :
- une NAVIGATION (GET d'une page) repart de zéro, même avec l'ancien
  identifiant, et renvoie le nouveau ;
- une ACTION (POST) et un GET du framework (``/_bretzel/…``) gardent,
  eux, l'état de la page qui les envoie — sans quoi plus rien ne tient.

Le trajet complet dans un navigateur (le pont adopte le nouvel
identifiant) : ``tests/runtime_js/test_a_navigation_starts_a_fresh_page.py``.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.runtime import HEADER_PAGE_ID
from bretzel.server.handlers import sign_action
from bretzel.server.middleware.render_context import _is_navigation
from bretzel.state import PageState, field
from tests._session import session_of

_SECRET = "n" * 32


class Compteur(PageState):
    n: int = field(default=0)


class Vue(PageState):
    fil: str = field(default="")

    URL = {"fil": "c"}


def plus() -> None:
    Compteur().n += 1


@refreshable
def etat() -> None:
    ui.text(f"n={Compteur().n} fil=[{Vue().fil}]")


@page("/")
def accueil() -> None:
    ui.button("plus", on_click=plus)
    etat()


_app = Bretzel(secret_key=_SECRET, mode="dev")
_app.include(accueil)

ETAT = re.compile(r"n=\d+ fil=\[[^\]]*\]")


def _page_id(html: str) -> str:
    match = re.search(r'data-bz-page-id="([^"]+)"', html)
    assert match, "le shell doit publier l'id de page"
    return match.group(1)


def _plus(client: TestClient, html: str, page_id: str, current: str):
    """Cliquer « plus », en disant de quelle page on parle."""
    match = re.search(r'hx-post="([^"]+::plus)"', html)
    assert match, "pas d'action « plus » sur la page"
    url, args = match.group(1), ""  # « plus » ne prend pas d'argument
    return client.post(url, data={"_args": args}, headers={
        "X-Bz-Sig": sign_action(_app.config._action_key, url.rsplit("/", 1)[-1], args, session_id=session_of(client)),
        HEADER_PAGE_ID: page_id, "HX-Request": "true", "HX-Current-URL": current})


def test_a_boosted_navigation_starts_a_fresh_page_state() -> None:
    with TestClient(_app) as client:
        home = client.get("/?c=X").text
        old = _page_id(home)
        _plus(client, home, old, "http://t/?c=X")
        second = _plus(client, home, old, "http://t/?c=X")
        assert "n=2 fil=[X]" in second.text, ETAT.findall(second.text)

        # Le lien « / » cliqué depuis la page : le pont y joint l'ancien id.
        nav = client.get("/", headers={
            "HX-Request": "true", "HX-Boosted": "true", HEADER_PAGE_ID: old})

    assert "n=0 fil=[]" in nav.text, (
        "la navigation a retrouvé l'état de la page quittée : "
        f"{ETAT.findall(nav.text)}"
    )
    fresh = nav.headers.get(HEADER_PAGE_ID)
    assert fresh and fresh != old, (
        "la navigation doit renvoyer le NOUVEL id, que le pont adopte : "
        f"{fresh!r} (ancien {old!r})"
    )


def test_only_a_page_get_is_a_navigation() -> None:
    """Le versant qui borne : une action et un GET du framework parlent
    pour la page qui les envoie, et gardent son état."""
    assert _is_navigation({"method": "GET", "path": "/atelier"})
    assert not _is_navigation({"method": "POST", "path": "/_bretzel/action/x"})
    assert not _is_navigation({"method": "GET", "path": "/_bretzel/refetch"})
    assert not _is_navigation({"method": "GET", "path": "/_bretzel/datatable.csv"})

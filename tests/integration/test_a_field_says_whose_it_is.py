"""Gate : le ``name`` d'un champ lié dit À QUEL ÉTAT il appartient.

Le défaut, mesuré le 2026-11-06
-------------------------------
Un contrôle lié dérivait son ``name`` du champ SEUL : ``Delivery.mode`` et
``Payment.mode`` partaient tous deux sous ``name="mode"``. Dans un même
formulaire :

- ``save(mode)`` recevait la dernière valeur, l'autre perdue sans un mot ;
- ``save(d: Delivery, p: Payment)`` recevait ``d.mode == p.mode`` — la
  valeur du paiement ÉCRITE dans la livraison, puis sauvegardée.

Le nom porte maintenant l'état : ``Delivery.mode`` (``Delivery[clé].mode``
pour une instance à clé). Un handler demande toujours ce qu'il veut :
l'état (``d: Delivery``), ou le champ nu (``mode``) — qui lit LE seul
``<État>.mode`` envoyé, et refuse d'en choisir un parmi deux. Un ``name=``
écrit par l'app n'est jamais réécrit (``state/_wire_name.py``).
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.state import ClientState, SessionState, field, form_value
from bretzel.state._wire_name import (
    AmbiguousFieldError,
    lookup,
    split_wire_name,
    wire_name,
)
from tests._carriers import carriers_of, post

_app = Bretzel(secret_key="w" * 32, mode="dev")

SEEN: list[Any] = []


class Delivery(SessionState):
    mode: str = field(default="")


class Payment(SessionState):
    mode: str = field(default="")


class Prefs(ClientState, persist="memory"):
    mode: str = field(default="a")


def save_both(d: Delivery, p: Payment) -> None:
    SEEN.append((d.mode, p.mode))


def save_bare(mode: str = "") -> None:
    SEEN.append(mode)


def save_raw() -> None:
    SEEN.append(form_value("mode"))


@page("/")
def home() -> None:
    with ui.form(on_submit=save_both, id="both"):
        ui.input(value=Delivery().mode)
        ui.input(value=Payment().mode)
    with ui.form(on_submit=save_bare, id="bare"):
        ui.input(value=Delivery().mode)
    with ui.form(on_submit=save_raw, id="raw"):
        ui.input(value=Payment().mode)
    ui.input(value=Delivery().mode, name="mode", id="written")
    ui.input(value=Prefs(key="paris").mode, id="keyed")


_app.include(home)


@pytest.fixture
def client():
    SEEN.clear()
    with TestClient(_app) as c:
        yield c


@pytest.fixture
def html(client: TestClient) -> str:
    return client.get("/").text


def test_the_name_says_whose_field_it_is(html: str) -> None:
    assert 'name="Delivery.mode"' in html and 'name="Payment.mode"' in html
    assert 'name="Prefs[paris].mode"' in html


def test_a_name_the_app_wrote_is_never_rewritten(html: str) -> None:
    assert 'id="written"' in html
    written = html.split('id="written"')[0].rsplit("<input", 1)[1]
    assert 'name="mode"' in written


def test_two_states_in_one_form_each_get_their_value(client, html) -> None:
    (carrier,) = carriers_of(html, save_both)
    post(client, carrier, **{"Delivery.mode": "poste", "Payment.mode": "carte"})
    assert SEEN == [("poste", "carte")]


def test_a_bare_parameter_reads_the_one_field_sent(client, html) -> None:
    (carrier,) = carriers_of(html, save_bare)
    post(client, carrier, **{"Delivery.mode": "poste"})
    assert SEEN == ["poste"]


def test_form_value_reads_the_one_field_sent(client, html) -> None:
    (carrier,) = carriers_of(html, save_raw)
    post(client, carrier, **{"Payment.mode": "carte"})
    assert SEEN == ["carte"]


def test_a_bare_parameter_refuses_to_pick_one_of_two(html) -> None:
    """Deux champs ``mode`` : le handler qui demande ``mode`` seul est
    refusé, avec ce qu'il faut écrire — plus de perte silencieuse."""
    with TestClient(_app, raise_server_exceptions=True) as client:
        (carrier,) = carriers_of(client.get("/").text, save_bare)
        with pytest.raises(AmbiguousFieldError, match=r"d: Delivery"):
            post(client, carrier, **{"Delivery.mode": "poste",
                                     "Payment.mode": "carte"})


# ── Le format, et son lecteur ─────────────────────────────────────────


def test_the_format() -> None:
    assert wire_name("Delivery", "default", "mode") == "Delivery.mode"
    assert wire_name("Delivery", "paris", "mode") == "Delivery[paris].mode"
    assert split_wire_name("Delivery[paris].mode") == ("Delivery", "paris", "mode")
    assert split_wire_name("_Picks.filter") == ("_Picks", "default", "filter")
    # Trois segments à majuscule : l'instantané d'état CLIENT que le pont
    # ajoute à chaque requête, jamais un argument de handler.
    assert split_wire_name("Delivery.default.mode") is None
    assert split_wire_name("mode") is None


def test_lookup_prefers_the_written_name_then_the_one_owner() -> None:
    assert lookup({"mode": "x", "Delivery.mode": "y"}, "mode") == (True, "x")
    assert lookup({"Delivery.mode": "y"}, "mode") == (True, "y")
    assert lookup({"other": "z"}, "mode") == (False, None)
    with pytest.raises(AmbiguousFieldError):
        lookup({"Delivery.mode": "y", "Payment.mode": "z"}, "mode")

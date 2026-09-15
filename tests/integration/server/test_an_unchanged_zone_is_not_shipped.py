"""Une zone dont le rendu n'a pas bougé ne repart pas sur le fil.

Le rendu est déjà payé quand on le sait — c'est l'expédition, le gzip et
le morph qu'on épargne. Mesuré le 2026-09-08 sur ``examples/messagerie`` :
re-cliquer un fil déjà ouvert coûtait **9 461 octets et 50 ms** ; avec
cette optimisation, **300 octets et 10 ms**. Le même clic sur un fil
DIFFÉRENT coûte toujours ses 9,4 Ko, et c'est normal — tout y change.

Le serveur ne stocke RIEN. L'empreinte de référence vient du client, qui
porte le HTML en question : il la reçoit dans
:data:`~bretzel.runtime.protocol.HEADER_ZONE_HASHES` et la représente
dans :data:`~bretzel.runtime.protocol.HEADER_ZONES`, en ``id:empreinte``.

⚠️ **Le test qui compte le plus est**
:func:`test_a_zone_that_changed_is_shipped_even_with_a_stale_hash`.
Une empreinte absente, périmée ou mensongère ne doit pouvoir que faire
RÉ-EXPÉDIER la zone. Le sens inverse — taire une zone que le navigateur
n'a pas — produirait une page qui cesse de se mettre à jour, sans une
erreur nulle part : exactement le mode d'échec le plus cher à
diagnostiquer, et pire que le gaspillage qu'on répare.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.runtime.protocol import HEADER_ZONE_HASHES, HEADER_ZONES
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import SessionState, field

_SECRET = "x" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")


class Compteur(SessionState):
    n: int = field(default=0)
    #: Muté par l'action « sans effet visible » : la zone lit ``n``, pas
    #: celui-ci, donc son rendu ne bouge pas alors qu'elle est bien sale.
    invisible: int = field(default=0)


@refreshable(deps=[Compteur])
def zone() -> None:
    ui.text(f"N={Compteur().n}")


def incrementer() -> None:
    Compteur().n += 1


def toucher_sans_rien_changer() -> None:
    """Salit l'état SANS changer ce que la zone affiche."""
    Compteur().invisible += 1


def _agir(client: TestClient, quoi, entetes: dict[str, str]):
    action_id = encode_action_id(quoi)
    sig = sign_action(_app.config._action_key, action_id, "")
    reponse = client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig, **entetes},
        data={"_args": ""},
    )
    assert reponse.status_code in (200, 204), reponse.text[:200]
    return reponse


@page("/")
def accueil() -> None:
    zone()


_app.include(accueil)


@pytest.fixture
def client():
    with TestClient(_app) as c:
        c.get("/")
        yield c


def test_the_response_announces_what_it_shipped(client) -> None:
    """Plancher : sans l'en-tête de réponse, le client n'a rien à
    représenter et toute l'optimisation est inerte."""
    reponse = _agir(client, incrementer, {HEADER_ZONES: zone.id})
    entete = reponse.headers.get(HEADER_ZONE_HASHES, "")
    assert entete.startswith(f"{zone.id}:"), (
        f"la réponse n'annonce pas l'empreinte de la zone qu'elle "
        f"expédie : {entete!r}"
    )


def test_an_unchanged_zone_is_silenced(client) -> None:
    """L'économie : deux actions de suite, la seconde ne renvoie rien.

    ``toucher_sans_rien_changer`` salit bien la zone — elle est rendue —
    mais son HTML est identique, donc il ne part pas.
    """
    premiere = _agir(client, incrementer, {HEADER_ZONES: zone.id})
    empreinte = premiere.headers[HEADER_ZONE_HASHES].split(":", 1)[1]
    assert "N=" in premiere.text

    seconde = _agir(
        client,
        toucher_sans_rien_changer,
        {HEADER_ZONES: f"{zone.id}:{empreinte}"},
    )
    assert "N=" not in seconde.text, (
        "une zone au rendu identique a quand même été expédiée : "
        f"{len(seconde.text)} octets."
    )


def test_a_zone_that_changed_is_shipped_even_with_a_stale_hash(
    client,
) -> None:
    """Le versant qui compte le plus — l'empreinte périmée.

    Si elle pouvait faire taire une zone que le navigateur n'a pas, la
    page cesserait de se mettre à jour sans qu'une erreur soit levée.
    """
    premiere = _agir(client, incrementer, {HEADER_ZONES: zone.id})
    empreinte = premiere.headers[HEADER_ZONE_HASHES].split(":", 1)[1]

    # ``incrementer`` change ce que la zone affiche : l'empreinte que le
    # client représente ne vaut plus, et la zone DOIT repartir.
    seconde = _agir(
        client, incrementer, {HEADER_ZONES: f"{zone.id}:{empreinte}"}
    )
    assert "N=" in seconde.text, (
        "une zone dont le rendu a changé a été tue au motif d'une "
        "empreinte périmée : la page ne se met plus à jour."
    )


def test_a_client_that_sends_no_hash_gets_everything(client) -> None:
    """Un client muet — runtime en cache, client tiers — reçoit tout.

    Même raison que pour le filtre de zones vivantes : « je ne sais pas »
    n'est pas « rien n'a changé ».
    """
    _agir(client, incrementer, {HEADER_ZONES: zone.id})
    seconde = _agir(client, toucher_sans_rien_changer, {HEADER_ZONES: zone.id})
    assert "N=" in seconde.text, (
        "un client qui n'envoie pas d'empreinte ne reçoit plus sa zone : "
        "l'absence a été confondue avec l'égalité."
    )


def test_the_two_ends_of_the_protocol_agree() -> None:
    """Le nom de l'en-tête est le même en Python et dans le runtime.

    Le JS ne peut pas importer la constante ; c'est ce test qui tient les
    deux bouts, comme ``test_dnd_wire_field_matches_runtime`` le fait
    pour le champ de glisser-déposer.
    """
    from pathlib import Path

    pont = (
        Path(__file__).resolve().parents[3]
        / "bretzel"
        / "runtime"
        / "_src"
        / "05_bridge.js"
    ).read_text(encoding="utf-8")
    assert f'"{HEADER_ZONE_HASHES}"' in pont, (
        f"le pont ne lit pas {HEADER_ZONE_HASHES!r} : le serveur annonce "
        f"des empreintes que personne ne recueille, et l'optimisation ne "
        f"se déclenche jamais."
    )
    assert '":" + vu' in pont or '":"+vu' in pont, (
        "le pont n'envoie plus les empreintes en ``id:empreinte`` — le "
        "serveur ne peut plus comparer."
    )

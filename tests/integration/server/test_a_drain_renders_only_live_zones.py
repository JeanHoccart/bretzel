"""Le drain ne rend que les zones que le navigateur a sous les yeux.

``_ZONES_BY_DEP`` est indexé par CLASSE d'état, pas par page. Une classe
partagée par plusieurs écrans traîne donc toutes leurs zones, et
``enqueue_deps`` les enfilait toutes : le serveur rendait celles des
autres pages, les sérialisait, les envoyait, et le navigateur les jetait
faute de cible. Rien ne lève, rien ne s'affiche de travers — c'est du
temps serveur brûlé, invisible.

Mesuré le 2026-09-05 sur ``examples/mad`` : une action depuis
``/patients`` rendait aussi la zone du tableau de bord, **8,4 ms** contre
9,6 ms pour la zone utile — près de la moitié du drain. Sur
``examples/crm``, ``ViewerPrefs`` traîne 14 zones sur 8 modules pour 4 au
plus par page.

⚠️ Le test le plus important de ce fichier est
:func:`test_without_the_header_nothing_is_filtered`. Un filtre qui se
tromperait de sens ferait taire TOUTES les zones du premier client qui ne
parle pas la dernière version du protocole — un runtime en cache, un
client tiers — et le symptôme serait une page qui cesse de se mettre à
jour, sans une erreur nulle part. C'est pire que le gaspillage qu'on
répare.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.runtime.protocol import HEADER_ZONES
from bretzel.server.handlers import encode_action_id, sign_action
from bretzel.state import SessionState, field

_SECRET = "x" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")


class Compteur(SessionState):
    n: int = field(default=0)


#: Deux zones sur LA MÊME classe, une par page — la configuration qui
#: produit le gaspillage. Chacune écrit un marqueur reconnaissable pour
#: qu'on puisse dire laquelle a été rendue.
@refreshable(deps=[Compteur])
def zone_accueil() -> None:
    ui.text(f"ACCUEIL={Compteur().n}")


@refreshable(deps=[Compteur])
def zone_ailleurs() -> None:
    ui.text(f"AILLEURS={Compteur().n}")


def incrementer() -> None:
    Compteur().n += 1


@page("/")
def accueil() -> None:
    zone_accueil()


@page("/ailleurs")
def ailleurs() -> None:
    zone_ailleurs()


_app.include(accueil)
_app.include(ailleurs)


def _agir(client: TestClient, entetes: dict[str, str]) -> str:
    """Déclencher l'action et rendre le corps de la réponse."""
    action_id = encode_action_id(incrementer)
    sig = sign_action(_app.config._action_key, action_id, "")
    reponse = client.post(
        f"/_bretzel/action/{action_id}",
        headers={"X-Bz-Sig": sig, **entetes},
        data={"_args": ""},
    )
    # 204 quand il n'y a RIEN à renvoyer — le chemin que ``drain_refresh_queue``
    # prend déjà quand la file est vide. C'est le cas légitime d'un filtre
    # qui a tout écarté, pas une erreur.
    assert reponse.status_code in (200, 204), reponse.text[:200]
    return reponse.text


@pytest.fixture
def client():
    with TestClient(_app) as c:
        yield c


def test_both_zones_are_declared_on_the_same_class() -> None:
    """Plancher. Sans DEUX zones sur la classe, il n'y a rien à filtrer
    et tout le fichier passerait sur un montage vide."""
    from bretzel.render.decorators.refreshable import _ZONES_BY_DEP

    zones = _ZONES_BY_DEP.get(Compteur, ())
    assert len(zones) >= 2, (
        f"{len(zones)} zone(s) déclarée(s) sur Compteur — le montage ne "
        f"reproduit pas la configuration qui gaspille."
    )


def test_only_the_zone_the_browser_has_is_rendered(client) -> None:
    """L'interdiction : la zone de l'AUTRE page n'est pas rendue."""
    client.get("/")
    zone_id = zone_accueil.id
    corps = _agir(client, {HEADER_ZONES: zone_id})
    assert "ACCUEIL=" in corps, (
        "la zone de la page courante n'a pas été rendue — le filtre est "
        "trop large et casse le rafraîchissement."
    )
    assert "AILLEURS=" not in corps, (
        "la zone de l'autre page a été rendue et envoyée : le navigateur "
        "va la jeter, et le serveur a payé son rendu pour rien."
    )


def test_without_the_header_nothing_is_filtered(client) -> None:
    """Le versant qui compte le plus.

    En-tête absent = « je ne sais pas », PAS « aucune zone ». Un client
    qui se tait doit retomber sur l'ancien comportement — les deux zones
    rendues — et jamais sur le silence.
    """
    client.get("/")
    corps = _agir(client, {})
    assert "ACCUEIL=" in corps and "AILLEURS=" in corps, (
        "un client qui n'envoie pas l'en-tête ne reçoit plus toutes ses "
        "zones : le filtre a confondu « inconnu » et « vide ». Toute page "
        "servie par un runtime en cache cesserait de se mettre à jour, "
        "sans une erreur."
    )


def test_an_empty_header_is_read_as_silence(client) -> None:
    """Une valeur vide ou blanche ne veut pas dire « aucune zone ».

    Le runtime omet l'en-tête quand il n'a rien à déclarer, donc une
    chaîne vide ne peut venir que d'un intermédiaire — un proxy qui
    normalise, un client approximatif. La traiter comme un ensemble vide
    ferait taire toutes les zones.
    """
    client.get("/")
    for valeur in ("", "   ", ",,"):
        corps = _agir(client, {HEADER_ZONES: valeur})
        assert "ACCUEIL=" in corps, (
            f"en-tête {valeur!r} traité comme « aucune zone » — toutes les "
            f"zones se taisent."
        )


def test_an_unknown_zone_id_filters_everything_out(client) -> None:
    """Le pendant : un identifiant qui ne correspond à rien filtre bien.

    Sans ce versant, le filtre pourrait ne jamais mordre (rendre toujours
    tout) et les deux tests au-dessus passeraient quand même.
    """
    client.get("/")
    corps = _agir(client, {HEADER_ZONES: "refresh_nexistepas"})
    assert "ACCUEIL=" not in corps and "AILLEURS=" not in corps, (
        "le filtre ne mord pas : il rend des zones que le client dit ne "
        "pas avoir."
    )
    # Et le drain sait déjà ne rien renvoyer plutôt qu'un corps vide :
    # c'est le 204 que ``drain_refresh_queue`` produit quand la file est
    # vide, atteint ici par le filtre au lieu de l'absence de deps.
    assert corps == ""


def test_the_zone_marker_is_in_the_page(client) -> None:
    """Le client ne peut déclarer que ce qu'il sait reconnaître.

    Le marqueur est ce qui lui permet d'énumérer les zones sans deviner
    le préfixe ``refresh_``. S'il disparaît du HTML, le runtime n'envoie
    plus rien, le filtre s'éteint en silence, et on revient au
    gaspillage sans qu'aucun test ne rougisse — sauf celui-ci.
    """
    html = client.get("/").text
    assert "data-bz-zone" in html, (
        "aucune zone ne porte data-bz-zone : le runtime ne peut plus les "
        "énumérer et le filtre est mort sans bruit."
    )
    assert zone_accueil.id in html

"""Gate — un changement atteint les autres onglets que sa portée autorise.

Le modèle
---------
Une zone se redessine quand ce qu'elle a lu change, dans tous les onglets
qui l'affichent. Rien ne se déclare : l'abonnement d'un onglet vient de ce
que ses zones ont lu, et la PORTÉE de l'état dit qui entend le signal.

- ``PageState`` : rien ne part, l'onglet qui agit a déjà sa réponse ;
- ``SessionState`` : les onglets de cette session (``only_session``) ;
- ``UserState`` : les onglets de cet utilisateur (``only_user``) ;
- ``AppState`` et ``Topic`` : tout le monde.

Ce qui traverse n'est qu'un SIGNAL : chaque onglet relit sa zone dans son
propre contexte, aucune donnée ne passe d'un client à l'autre.

Ce qu'elle remplace
-------------------
``@refreshable(broadcast=[...])`` listait à la main ce qu'une zone
écoutait des autres onglets. La liste répétait ce que la zone lisait, et
dérivait dans les deux sens sans rien lever : un état oublié figeait la
zone chez les autres, un état de trop les faisait relire pour rien. Elle
existait parce qu'un état personnel lu par une zone partagée aurait fait
relire tout le monde ; depuis que la portée restreint le signal à son
propriétaire, la liste ne disait plus rien que la lecture ne dise.

Ce qu'elle mesure
-----------------
Ce qui part VRAIMENT sur le fil — un faux courtier note chaque publication
et ses destinataires —, pas ce que la zone déclare.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.render.decorators.refreshable import (
    ZoneRegistry,
    broadcast_changes,
    refreshable,
    state_qualname,
)
from bretzel.state import (
    AppState,
    PageState,
    SessionState,
    Topic,
    UserState,
    field,
    reads,
    writes,
)


class Vue(PageState):
    filtre: str = field(default="")


class Panier(SessionState):
    lignes: int = field(default=0)


class Prefs(UserState):
    langue: str = field(default="fr")


class Planning(AppState):
    rev: int = field(default=0)


AGENDA = Topic("agenda")


@reads(AGENDA)
def rendez_vous() -> list[str]:
    return []


@writes(AGENDA)
def prendre_rendez_vous() -> None:
    """L'autre moitié du sujet : sans elle, il ne sonnerait jamais."""


@refreshable
def ecran() -> None:
    """Une zone qui lit une donnée de chaque portée."""
    Vue().filtre
    Panier().lignes
    Prefs().langue
    Planning().rev
    rendez_vous()


class _Courtier:
    """Note chaque publication avec ses destinataires."""

    def __init__(self) -> None:
        self.publie: dict[str, dict[str, str]] = {}

    def publish(self, qualname: str, **cible: str) -> None:
        self.publie[qualname] = cible

    def subscribe(self, session_id: str, qualname: str) -> None:
        pass


def _sur_le_fil(changes: set[type]) -> dict[str, dict[str, str]]:
    courtier = _Courtier()
    zones = ZoneRegistry()
    zones.add(ecran)
    ctx: Any = SimpleNamespace(
        app=SimpleNamespace(sse_broker=courtier, zones=zones),
        tab_id="onglet-a", session_id="session-a", user_id="alice",
    )
    broadcast_changes(ctx, {cls: set() for cls in changes})
    return courtier.publie


@pytest.fixture(autouse=True, scope="module")
def _ecran_rendu() -> None:
    """Le processus sait ce que la zone lit, comme après un premier rendu."""
    with render_isolated() as ctx:
        ctx.app.sse_broker = None
        ecran()


def test_la_zone_a_lu_chaque_portee() -> None:
    """Plancher : sans ces lectures, tous les tests suivants seraient vides."""
    assert set(ecran.reads) == {Vue, Panier, Prefs, Planning, AGENDA._revision}


def test_un_etat_de_page_ne_quitte_pas_son_onglet() -> None:
    assert _sur_le_fil({Vue}) == {}


def test_un_etat_de_session_reste_dans_sa_session() -> None:
    cible = _sur_le_fil({Panier})[state_qualname(Panier)]
    assert cible["only_session"] == "session-a"
    assert cible["except_tab"] == "onglet-a"


def test_un_etat_utilisateur_reste_avec_son_utilisateur() -> None:
    cible = _sur_le_fil({Prefs})[state_qualname(Prefs)]
    assert cible["only_user"] == "alice"
    assert cible["only_session"] == ""


@pytest.mark.parametrize("etat", [Planning, AGENDA._revision])
def test_un_etat_partage_atteint_tout_le_monde(etat: type) -> None:
    cible = _sur_le_fil({etat})[state_qualname(etat)]
    assert cible["only_session"] == "" and "only_user" not in cible


def test_un_etat_que_personne_n_affiche_reste_muet() -> None:
    class Ailleurs(AppState):
        x: int = field(default=0)

    assert _sur_le_fil({Ailleurs}) == {}


def test_la_gate_verrait_un_etat_de_page_diffuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le versant qui mord : la portée ``page`` admise, l'état part."""
    module = sys.modules["bretzel.render.decorators.refreshable"]
    monkeypatch.setattr(module, "SHARED_SCOPES",
                        frozenset({"page", "session", "user", "app"}))
    assert state_qualname(Vue) in _sur_le_fil({Vue})

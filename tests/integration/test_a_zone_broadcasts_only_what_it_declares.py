"""Gate — une zone ne diffuse que sur les états qu'elle a DÉCLARÉS.

Le défaut qu'elle ferme (finding [23], 2026-08-23)
----------------------------------------------------
``deps=`` servait **deux rôles dans le même mot** : « ce qui me re-rend »
et, quand ``broadcast=True``, « ce sur quoi je diffuse à tous les
clients ». Les deux listes étant la même, une zone temps réel ne pouvait
pas déclarer une dépendance **personnelle** — y mettre une préférence
d'utilisateur aurait fait refetcher le monde entier dès qu'une seule
personne change son réglage.

Conséquence mesurée sur ``examples/crm`` : les deux zones de l'écran
temps réel ne suivaient pas le changement de portefeuille de la
direction. Pas par oubli — **faute de pouvoir l'écrire**.

*(Rassurant, vérifié au passage : le broadcast publie un SIGNAL, chaque
client refetch dans SON contexte. Aucune donnée ne traverse d'un client à
l'autre — c'était un problème de bruit, pas de fuite.)*

Ce que ``broadcast`` veut dire maintenant
-------------------------------------------
**Deux listes orthogonales**, et la question qu'elles posent est la même :
*qui change cet état ?*

==============  ======================================================
qui le change   où on l'écrit
==============  ======================================================
**moi**         ``deps`` — re-rendu DANS la réponse de l'action.
**les autres**  ``broadcast`` — signal SSE puis refetch.
**les deux**    les deux listes — « instantané pour moi, poussé aux
                autres ». Pas une redondance : ça dit quelque chose.
==============  ======================================================

Un ``broadcast=[X]`` **seul** est donc légitime, et il n'y a **aucune
règle d'inclusion**. ``broadcast=True`` (« tous mes deps ») a existé une
journée et a été supprimé : sans inclusion il recoud les deux listes
qu'on vient de séparer, et il donnerait une seconde façon d'écrire
``deps=[X], broadcast=[X]``.

Ce qu'elle mesure
------------------
Pas la forme déclarée (ça, ``handle.broadcast`` le dit), mais **ce qui
part vraiment sur le fil** : un faux broker capture les publications, et
on mute l'état personnel pour vérifier que RIEN ne sort.
"""

from __future__ import annotations

import pytest

from bretzel.render.decorators.refreshable import (
    broadcast_deps,
    refreshable,
    state_qualname,
)
from bretzel.state import SessionState, field


class Globale(SessionState):
    """L'état PARTAGÉ — le pipeline, la file, ce que tout le monde voit."""

    rev: int = field(default=0)


class Personnelle(SessionState):
    """L'état PERSONNEL — la préférence de celui qui regarde."""

    portefeuille: str = field(default="tous")


class _Broker:
    """Un broker qui note au lieu de pousser."""

    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, qualname: str, *, except_tab: str = "") -> None:
        # ``except_tab`` : l'onglet émetteur, que le vrai courtier
        # saute. Le double le reçoit et l'ignore — ce qu'il mesure,
        # c'est QUELS canaux sont publiés, pas à qui.
        del except_tab
        self.published.append(qualname)


class _Ctx:
    def __init__(self, broker: _Broker) -> None:
        self.app = type("App", (), {"sse_broker": broker})()


class Ailleurs(SessionState):
    """Un état que CETTE zone ne change jamais elle-même."""

    tick: int = field(default=0)


@refreshable(deps=[Globale, Personnelle], broadcast=[Globale])
def zone_mixte() -> None:
    """La forme que le finding rendait impossible."""


@refreshable(deps=[Globale], broadcast=[Globale])
def zone_deux_chemins() -> None:
    """Le cas courant : instantané pour moi, poussé aux autres."""


@refreshable(broadcast=[Ailleurs])
def zone_ecoute_seulement() -> None:
    """Sans ``deps`` — « cet état, je ne le change jamais moi-même ».

    Un job de fond, un autre utilisateur. Cette écriture n'avait aucun
    sens tant que ``broadcast`` était un sous-ensemble de ``deps``.
    """


@refreshable(deps=[Personnelle])
def zone_locale() -> None:
    """Aucun broadcast — le défaut."""


def _published(changed: set[type]) -> list[str]:
    broker = _Broker()
    broadcast_deps(_Ctx(broker), changed)
    return broker.published


class TestWhatIsDeclared:
    def test_the_two_lists_are_independent(self) -> None:
        assert zone_mixte.deps == (Globale, Personnelle)
        assert zone_mixte.broadcast == (Globale,)

    def test_both_paths_is_written_by_naming_it_twice(self) -> None:
        """Et ce n'est PAS une redondance : ça dit « les deux chemins »."""
        assert zone_deux_chemins.deps == (Globale,)
        assert zone_deux_chemins.broadcast == (Globale,)

    def test_a_zone_can_listen_without_depending(self) -> None:
        """``broadcast`` seul — l'écriture que la règle d'inclusion interdisait."""
        assert zone_ecoute_seulement.deps == ()
        assert zone_ecoute_seulement.broadcast == (Ailleurs,)

    def test_no_broadcast_is_the_default(self) -> None:
        assert zone_locale.broadcast == ()

    def test_the_boolean_is_refused(self) -> None:
        """``broadcast=True`` est supprimé, pas réinterprété.

        Il voulait dire « tous mes deps » — donc il recoud les deux
        listes qu'on vient de séparer, et il donnerait une seconde façon
        d'écrire ``deps=[X], broadcast=[X]``. Un refus bruyant plutôt
        qu'un ``tuple(True)`` et son ``TypeError`` incompréhensible.
        """
        with pytest.raises(TypeError, match="prend une LISTE"):

            @refreshable(deps=[Globale], broadcast=True)
            def zone_ancienne() -> None: ...


class TestWhatActuallyGoesOnTheWire:
    """Le cœur : ce que le broker reçoit, pas ce que la zone déclare."""

    def test_the_shared_state_is_published(self) -> None:
        assert _published({Globale}) == [state_qualname(Globale)]

    def test_the_personal_state_is_not_published(self) -> None:
        """Le défaut d'origine, dans son expression exacte.

        Avant le 2026-08-23, ``zone_mixte`` était inécrivable : dès que
        ``Personnelle`` figurait dans ``deps`` d'une zone diffusante, sa
        mutation partait à tous les clients.
        """
        assert _published({Personnelle}) == [], (
            "muter un état PERSONNEL a publié un signal SSE : tous les "
            "clients vont refetcher parce qu'une seule personne a changé "
            "son réglage. `broadcast_deps` doit tester `cls in "
            "zone.broadcast`, pas `zone.broadcast` tout court."
        )

    def test_both_at_once_publishes_only_the_shared_one(self) -> None:
        """Le cas réel : une action touche les deux."""
        assert _published({Globale, Personnelle}) == [state_qualname(Globale)]

    def test_a_listen_only_zone_still_gets_its_signal(self) -> None:
        """Un canal SANS ``deps`` publie quand même.

        C'est ce qui rend l'écriture utile : l'index des canaux est
        SÉPARÉ de celui des deps. S'il était un filtre dessus, cette zone
        serait invisible au fan-out et n'apprendrait jamais rien.
        """
        assert _published({Ailleurs}) == [state_qualname(Ailleurs)]

    def test_a_purely_local_zone_publishes_nothing(self) -> None:
        """Contrôle POSITIF — sinon « rien n'est publié » ne dit rien.

        ``Personnelle`` est aussi le dep d'une zone SANS broadcast : si
        cette gate passait parce que plus rien n'est jamais publié, ce
        test-ci resterait vert et le premier aussi. C'est
        ``test_the_shared_state_is_published`` qui les sépare.
        """
        assert _published({Personnelle}) == []


class TestTheAppUsesIt:
    """Le CRM était le cas d'usage — il doit porter la nouvelle écriture."""

    def test_the_realtime_screen_splits_its_deps(self) -> None:
        from examples.crm.features.access import ViewerPrefs
        from examples.crm.features.deals_data import DealsRev
        from examples.crm.features.realtime import board_pulse, recent_moves

        for zone in (board_pulse, recent_moves):
            assert ViewerPrefs in zone.deps, (
                f"{zone.name} ne re-rend pas sur le portefeuille regardé — "
                f"c'est le symptôme que le finding décrit."
            )
            assert ViewerPrefs not in zone.broadcast, (
                f"{zone.name} DIFFUSE une préférence personnelle : chaque "
                f"changement de portefeuille fera refetcher tous les "
                f"clients."
            )
            assert DealsRev in zone.broadcast, (
                f"{zone.name} ne diffuse plus le pipeline — l'écran temps "
                f"réel ne bouge plus dans l'onglet qui n'a rien fait."
            )

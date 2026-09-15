"""Gate : une valeur adressable à ESPACES fait l'aller-retour complet.

Ce qu'elle ferme
----------------
``URL = {…}`` promet trois choses d'un coup, et aucune n'est codée par
l'app : le lien se partage, le favori retrouve la même vue, et les
flèches du navigateur font l'aller-retour. Une valeur qui ne voyage pas
les casse toutes les trois **sans un signal** — rien ne lève, la vue à
l'écran est juste, et seule l'adresse ment.

Le doute qui l'a fait écrire
-----------------------------
``todo.md`` portait depuis le 2026-09-08 un item disant que la barre
d'adresse ne bougeait PAS quand la valeur contenait des espaces,
constaté en construisant ``examples/messagerie``. L'app avait été
réparée en changeant la DONNÉE — la clé de fil est devenue un slug — donc
le défaut n'a jamais été isolé, et l'item l'écrivait : « ce qui n'est PAS
établi : pourquoi le navigateur refuse ».

**Rejoué le 2026-09-11 sur banc, il ne se reproduit pas.** Le serveur
pousse ``?avec=les+plans+du+hangar+3``, la barre suit, le rechargement
retrouve la vue et la flèche retour ramène la valeur — y compris sous la
coque GELÉE (``ui.viewport`` + ``ui.pane``) de la messagerie, seule
différence structurelle nommable entre le banc et l'app. Soit le défaut
a été réparé entre-temps par un commit qui ne le visait pas, soit le
diagnostic était faux ; on ne peut plus trancher.

Ce qui EST tranché, c'est qu'on ne repartira pas de zéro : la mesure qui
a fermé la question devient la gate qui la garde. Sans elle, la
prochaine session qui voit une adresse bizarre rouvre le même item et
refait le même banc.

Les quatre trajets
------------------
Pousser ne suffit pas. Une valeur peut partir correctement et ne pas
revenir : ``+`` et ``%20`` sont deux encodages du même espace, et seul
l'aller-retour complet dit qu'ils sont tous deux relus.

Run : ``py -m pytest tests/runtime_js/test_an_addressable_value_with_spaces_travels.py -q -m browser``
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, layout, page, refreshable, ui
from bretzel.probe import Window, probe
from bretzel.state import PageState, field

pytestmark = pytest.mark.browser

#: Espaces ET un chiffre : c'est la valeur exacte de l'item d'origine.
VALEUR = "les plans du hangar 3"


class Vue(PageState):
    """Un champ adressable à espaces, un témoin sans."""

    avec: str = field(default="")
    sans: str = field(default="")

    URL = {"avec": "avec", "sans": "sans"}


def poser() -> None:
    Vue().avec = VALEUR


def vider() -> None:
    Vue().avec = ""


@refreshable(deps=[Vue])
def vue() -> None:
    ui.text(f"avec=[{Vue().avec}]")


@layout
def coque() -> None:
    """La coque GELÉE, comme la messagerie où le doute est né.

    ⚠️ Ce n'est pas du décor : c'est la seule différence de structure
    nommable entre le banc qui n'a pas reproduit le défaut et l'app qui
    l'avait montré. La garder ici évite de refaire la comparaison.
    """
    with ui.viewport(direction="col"), ui.pane():
        ui.outlet()


@page("/", title="banc", layout=coque)
def accueil() -> None:
    ui.button("poser", id="poser", on_click=poser)
    ui.button("vider", id="vider", on_click=vider)
    vue()


#: ⚠️ Tout se déclare au niveau MODULE et se récolte par `include(__name__)`.
#: Une zone `@refreshable` née dans une fabrique n'est récoltée par
#: personne : la page rend alors ses boutons et PAS la zone, donc la gate
#: chercherait un élément qui n'existe pas — vu en l'écrivant.
APP = Bretzel(secret_key="s" * 32, mode="dev")
APP.include(__name__)


#: La zone elle-même, et pas un ``id=`` posé sur son contenu : une zone
#: à enfant UNIQUE estampille son propre identifiant sur cet enfant, donc
#: un ``ui.text(id="avec")`` seul dans une zone perd son id (la
#: « transparence d'identité » du socle). Viser la zone évite de dépendre
#: du nombre d'enfants.
ZONE = "[data-bz-zone]"


def _rendu(w: Window) -> str:
    return w.text(ZONE)


def test_a_value_with_spaces_makes_the_whole_round_trip() -> None:
    """Les quatre trajets, dans un seul probe : ils partagent une app."""
    with probe(APP) as p:
        (a,) = p.windows

        # ① Le lien PARTAGÉ, encodage `+` — celui que le serveur produit.
        a.goto("/?avec=les+plans+du+hangar+3")
        p.check("① `+` tapé à froid sème l'état",
                _rendu(a) == f"avec=[{VALEUR}]", _rendu(a))

        # ② Le même lien en `%20` — celui qu'un humain colle.
        a.goto("/?avec=les%20plans%20du%20hangar%203")
        p.check("② `%20` tapé à froid sème l'état",
                _rendu(a) == f"avec=[{VALEUR}]", _rendu(a))

        # ③ La POUSSÉE : muter l'état réécrit la barre, sans navigation.
        a.goto("/")
        a.click("#poser")
        p.settle()
        pousse = a.page.url
        p.check("③ muter pousse la valeur dans la barre d'adresse",
                "avec=" in pousse, pousse)

        # ④ Et l'adresse poussée est RELISIBLE — c'est le favori.
        a.page.reload()
        a.settle(floor=0)
        p.check("④ recharger l'adresse poussée retrouve la vue",
                _rendu(a) == f"avec=[{VALEUR}]", f"{_rendu(a)} — {pousse}")

        # ⑤ Les FLÈCHES : vider sort le champ, retour le ramène.
        a.click("#vider")
        p.settle()
        p.check("⑤ vider retire le champ de l'adresse",
                "avec=" not in a.page.url, a.page.url)
        a.page.go_back()
        a.settle(floor=0)
        p.check("⑤ la flèche retour ramène la valeur à espaces",
                _rendu(a) == f"avec=[{VALEUR}]",
                f"{_rendu(a)} — url {a.page.url}")

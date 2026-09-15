"""``outlet=`` dit QUELLE région un lien remplace.

Sans lui, la coque booste tous les liens internes vers
``[data-bz-outlet]`` (``render/shell.py``) et htmx retient le PREMIER
outlet du document. Avec des coques imbriquées, c'est toujours le plus
extérieur : le serveur re-rend donc la coque intérieure EN PLUS de la
page, alors que le lien ne change que la page.

Mesuré en A/B alterné dans le même processus le 2026-09-08, 20 clics par
variante : **1 204 octets et 10 ms** en visant l'extérieur, **569 octets
et 3 ms** en visant l'intérieur. Moitié moins de poids, trois fois plus
rapide — et sur un banc dont la colonne de gauche est légère.

⚠️ **Le kwarg prend la FONCTION de coque, jamais son id**, et c'est le
test :func:`test_a_string_is_refused` qui garde ce choix. L'id s'écrit
``outlet_<nom>`` ; l'écrire à la main donne un sélecteur qui ne matche
rien, et htmx n'envoie alors **aucune requête, sans erreur**. C'est
exactement ce qui est arrivé au banc qui a produit la mesure ci-dessus :
une cible mal orthographiée, zéro requête, zéro message.
"""

from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, layout, page, ui
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.runtime.protocol import outlet_id_for

_SECRET = "x" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")


@layout
def coque() -> None:
    ui.outlet()


@layout(parent=coque)
def cadre() -> None:
    ui.outlet()


@page("/", layout=cadre)
def accueil() -> None:
    ui.card(href="/vise", outlet=cadre)
    ui.card(href="/libre")


@page("/refus", layout=cadre)
def refus() -> None:
    """Une page qui essaie de nommer l'outlet par une chaîne."""
    ui.card(href="/x", outlet="cadre")


_app.include(accueil)
_app.include(refus)


@pytest.fixture
def html() -> str:
    with TestClient(_app) as c:
        return c.get("/").text


def _cible(html: str, href: str) -> str | None:
    """La ``hx-target`` du lien qui pointe vers ``href``."""
    lien = re.search(rf'<a [^>]*href="{re.escape(href)}"[^>]*>', html)
    assert lien, f"aucun lien vers {href} dans la page"
    trouve = re.search(r'hx-target="([^"]*)"', lien.group(0))
    return trouve.group(1) if trouve else None


def test_the_page_really_nests_two_outlets(html: str) -> None:
    """Plancher : sans DEUX outlets, il n'y a rien à viser et tout le
    fichier passerait sur un montage qui ne reproduit pas le cas."""
    outlets = re.findall(r'id="(outlet_[a-z_]+)"', html)
    assert len(set(outlets)) >= 2, (
        f"un seul outlet rendu ({outlets}) — le montage n'imbrique pas."
    )


def test_a_link_that_names_its_outlet_targets_it(html: str) -> None:
    """L'affirmation : le lien vise la région nommée."""
    assert _cible(html, "/vise") == "#" + outlet_id_for("cadre")


def test_a_link_that_says_nothing_keeps_the_inherited_target(
    html: str,
) -> None:
    """Le versant qui compte : ne rien dire doit rester le défaut.

    Si ``outlet=`` posait une cible à tout le monde, chaque lien de
    chaque app changerait de comportement d'un coup — et les liens qui
    doivent bien remplacer la coque extérieure cesseraient de le faire.
    """
    assert _cible(html, "/libre") is None, (
        "un lien sans ``outlet=`` a reçu une cible : le défaut hérité de "
        "la coque a été écrasé."
    )


def test_a_string_is_refused() -> None:
    """Le mode d'échec le plus cher : une cible qui ne matche rien.

    htmx n'émet alors AUCUNE requête et ne dit rien. Le kwarg refuse donc
    tout ce qui n'est pas une coque, plutôt que de laisser composer un
    sélecteur à la main.
    """
    with TestClient(_app) as c, pytest.raises(ComponentUsageError) as leve:
        c.get("/refus")
    assert "@layout" in str(leve.value), (
        f"le refus ne dit pas ce qu'il attend : {leve.value}"
    )

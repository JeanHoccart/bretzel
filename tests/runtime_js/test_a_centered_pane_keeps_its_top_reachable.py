"""Gate navigateur — un pane centré ne coupe pas son haut.

Ce qu'elle garde
----------------
``ui.pane(justify="center")`` est la forme d'une page de connexion : une
carte au milieu d'un écran gelé. Tant que la carte tient, tout va bien.
Le jour où elle dépasse — un champ de plus, une fenêtre basse, un zoom —
le centrage la fait déborder des DEUX côtés, et **le défilement ne
remonte jamais au-dessus de son origine**. Le haut n'est pas difficile à
atteindre : il est inatteignable.

Mesuré le 2026-08-24 sur ``examples/auth`` en 1280×600 : contenu de
732 px dans un cadre de 600, et à ``scrollTop = 0`` le contenu commençait
à **-108 px**. Le titre et le premier champ n'existaient plus. Le
symptôme ne désigne rien — la page a simplement l'air tronquée, ce qui
se lit comme un bug de rendu.

Pourquoi au NAVIGATEUR
----------------------
``tests/consistency/test_a_scrolling_container_never_centers_unsafely``
garde l'orthographe de la classe. Elle ne peut pas dire si le mot-clé
``safe`` atteint le DOM ni si le moteur l'applique — et c'est exactement
ce qui manquait le jour du défaut : la classe ``justify-center`` était
parfaitement correcte, c'est son EFFET qui était faux.

Le témoin, et ce qu'il prouve
-----------------------------
La route ``/haut`` rend le même contenu en ``justify="start"``, qui n'a
jamais eu le défaut. Sans lui, « le haut est atteignable » serait vrai
même si la sonde lisait toujours zéro.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_centered_pane_keeps_its_top_reachable.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

#: De quoi dépasser LARGEMENT un écran de test de 600 px.
#:
#: ⚠️ « Ça déborde » ne suffit pas, et c'est le piège qui a rendu cette
#: gate muette à sa première écriture : le centrage ne pousse le contenu
#: hors du cadre que si le débordement dépasse le PADDING du pane. Avec
#: 30 px de débordement pour 24 px de padding, le haut restait
#: atteignable et la mutation passait — la gate était verte pour la
#: mauvaise raison. D'où :file:`_MIN_OVERFLOW`, qui mesure la marge, pas
#: seulement son signe.
_ENOUGH = 40

#: Le débordement minimal pour que le cas gardé EXISTE — très au-delà de
#: tout padding de pane (``p-4`` / ``sm:p-6`` = 16 à 24 px).
_MIN_OVERFLOW = 150

app = Bretzel(secret_key="c" * 32, title="Bretzel · pane centré", mode="dev")


def _tall_card(marker: str) -> None:
    with ui.card(padding="lg"), ui.vstack(gap="md", id=marker):
        ui.heading("Le premier élément", level=1, size="xl", id=f"{marker}_premier")
        for i in range(_ENOUGH):
            ui.text(f"Ligne {i + 1}", size="sm")


@page("/")
def centre() -> None:
    """La forme d'une page de connexion : une carte centrée qui dépasse."""
    with ui.viewport(), ui.pane(align="center", justify="center", padding="md"):
        _tall_card("centre")


@page("/haut")
def haut() -> None:
    """Le TÉMOIN — même contenu, aligné en haut. Il n'a jamais coupé."""
    with ui.viewport(), ui.pane(align="center", justify="start", padding="md"):
        _tall_card("haut")


app.include(__name__)

#: Remonte au maximum, puis compare le haut du contenu à celui du cadre.
#: Un écart négatif = des pixels que rien ne permet d'atteindre.
_REACH = """(marker) => {
  const first = document.getElementById(marker + '_premier');
  const pane = first.closest('[class*="overflow-y-auto"]');
  pane.scrollTop = 0;
  const paneTop = pane.getBoundingClientRect().top;
  const firstTop = first.getBoundingClientRect().top;
  return {
    deborde: pane.scrollHeight - pane.clientHeight,
    coupe: Math.round(paneTop - firstTop),
  };
}"""


def _goto(pg, path: str) -> None:
    origin = "//".join(pg.url.split("/", 3)[:3][:1] + [pg.url.split("/", 3)[2]])
    pg.goto(origin + path)
    pg.wait_for_selector("html.bz-ready", state="attached")
    pg.wait_for_timeout(300)


@pytest.fixture(scope="module")
def live():
    with audit_server(app) as url, browser_page(url, "/") as pg:
        pg.set_viewport_size({"width": 1280, "height": 600})
        pg.wait_for_selector("html.bz-ready", state="attached")
        yield pg


@pytest.mark.browser
def test_the_content_overflows_past_the_padding(live) -> None:
    """Le plancher, et il mesure une MARGE, pas un signe.

    Un débordement plus petit que le padding du pane ne pousse rien hors
    du cadre : le haut reste atteignable même sans ``safe``, et la gate
    passerait pour de bon sans rien garder. C'est arrivé à la première
    écriture (30 px de débordement pour 24 de padding).
    """
    _goto(live, "/")
    overflow = live.evaluate(_REACH, "centre")["deborde"]
    assert overflow >= _MIN_OVERFLOW, (
        f"{overflow} px de débordement seulement : en dessous de "
        f"{_MIN_OVERFLOW}, le centrage ne coupe rien et la gate ne garde "
        "plus rien. Augmente _ENOUGH."
    )


@pytest.mark.browser
def test_a_centered_pane_keeps_its_first_element_reachable(live) -> None:
    _goto(live, "/")
    coupe = live.evaluate(_REACH, "centre")["coupe"]
    assert coupe <= 0, (
        f"{coupe} px du haut sont INATTEIGNABLES : même à scrollTop=0, le "
        "premier élément commence au-dessus du cadre. C'est le centrage "
        "flex sans ``safe`` — cf. le thème de ui.pane."
    )


@pytest.mark.browser
def test_the_witness_never_cut(live) -> None:
    """``justify="start"`` n'a jamais eu le défaut — l'instrument le voit."""
    _goto(live, "/haut")
    assert live.evaluate(_REACH, "haut")["coupe"] <= 0

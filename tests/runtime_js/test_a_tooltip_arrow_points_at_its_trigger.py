"""La flèche d'une bulle vise son DÉCLENCHEUR, pas le milieu de la bulle.

``$bz.helpers.floating`` recadre un panneau ancré pour qu'il tienne dans
l'écran (``Math.max(4, Math.min(left, vw - w - 4))``). Le côté résolu
était publié — la flèche suivait donc un retournement — mais **pas le
décalage** : la flèche restait posée en ``left-1/2``, c'est-à-dire au
milieu du panneau. Tant que le panneau est centré sur son déclencheur les
deux coïncident, et c'est le cas de tous les bancs du dépôt, qui posent
leurs contrôles loin des bords.

Contre un bord, non. Mesuré le 2026-09-09 sur ``examples/kanban``, un
bouton collé au bord droit : déclencheur centré à 1468 px, flèche à
1443 px. Vingt-cinq pixels — la bulle semble mal placée alors que son
placement est juste, et c'est la flèche qui ment.

Les DEUX bras comptent
-----------------------
Le versant licite — un déclencheur au milieu de l'écran — est ce qui
empêche de « réparer » en décalant la flèche pour tout le monde. Et le
plancher vérifie que le cas de bord EST un cas de bord : si le panneau
n'était pas recadré, la mesure serait vraie pour une raison qui n'a rien
à voir avec ce qu'elle prétend garder.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_tooltip_arrow_points_at_its_trigger.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

#: L'écart toléré entre le centre de la flèche et celui du déclencheur.
#: Deux pixels, pas zéro : les deux boîtes sont mesurées en sous-pixels et
#: arrondies, et la flèche est un carré tourné de 45°.
TOLERANCE_PX = 2

app = Bretzel(secret_key="f" * 32, title="Bretzel · flèche de bulle",
              mode="dev")


@page("/")
def home() -> None:
    # ``justify="between"`` sur toute la largeur : le premier bouton
    # touche le bord gauche, le dernier le bord droit. C'est exactement
    # la configuration qu'aucun banc du dépôt n'avait.
    with ui.vstack(gap="lg", classes="p-0 w-full"):
        with ui.hstack(justify="between", classes="w-full"):
            ui.button("G", size="sm", id="gauche",
                      tooltip="Une bulle assez large pour être recadrée "
                              "contre le bord de la fenêtre")
            ui.button("M", size="sm", id="milieu",
                      tooltip="Une bulle assez large pour être recadrée "
                              "contre le bord de la fenêtre")
            ui.button("D", size="sm", id="droite",
                      tooltip="Une bulle assez large pour être recadrée "
                              "contre le bord de la fenêtre")


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


GEOMETRIE = """(function () {
  const t = [...document.querySelectorAll('[role=tooltip]')]
    .find(n => n.getBoundingClientRect().width > 0);
  if (!t) return null;
  const p = t.getBoundingClientRect();
  const f = t.querySelector('[aria-hidden=true]');
  if (!f) return null;
  const r = f.getBoundingClientRect();
  return {panneau_centre: p.left + p.width / 2,
          panneau: [p.left, p.right],
          fleche_centre: r.left + r.width / 2,
          cote: t.getAttribute('data-side')};
})()"""


def bulle(page, ident: str) -> dict:
    """Survole le bouton ``ident`` et rend la géométrie de sa bulle."""
    declencheur = page.locator("#" + ident)
    declencheur.hover()
    page.wait_for_function(
        "() => [...document.querySelectorAll('[role=tooltip]')]"
        ".some(n => n.getBoundingClientRect().width > 0)",
        timeout=5000,
    )
    page.wait_for_timeout(250)
    mesure = page.evaluate(GEOMETRIE)
    assert mesure, f"aucune bulle visible pour #{ident}"
    boite = declencheur.bounding_box()
    mesure["ancre_centre"] = boite["x"] + boite["width"] / 2
    return mesure


@pytest.mark.browser
def test_an_edge_trigger_really_shifts_its_panel(base_url: str) -> None:
    """Plancher : sans recadrage, le cas de bord ne prouve rien.

    Si le panneau du bouton de droite restait centré sur lui, la mesure
    d'à côté passerait avec la flèche posée au milieu de la bulle — donc
    avec le bug intact.
    """
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        droite = bulle(pg, "droite")
        ecart = abs(droite["panneau_centre"] - droite["ancre_centre"])
        assert ecart > 10, (
            f"le panneau du bord droit n'est pas recadré (écart {ecart:.0f} "
            f"px) — la fenêtre est trop large, ou la bulle trop courte")


@pytest.mark.browser
def test_the_arrow_follows_the_trigger_at_the_edges(base_url: str) -> None:
    """Le versant INTERDIT : contre un bord, la flèche reste sur l'ancre."""
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        for ident in ("gauche", "droite"):
            mesure = bulle(pg, ident)
            ecart = abs(mesure["fleche_centre"] - mesure["ancre_centre"])
            assert ecart <= TOLERANCE_PX, (
                f"#{ident} : la flèche est à {mesure['fleche_centre']:.0f} "
                f"px, le déclencheur à {mesure['ancre_centre']:.0f} — "
                f"{ecart:.0f} px à côté")
            pg.mouse.move(10, 400)
            pg.wait_for_timeout(300)


@pytest.mark.browser
def test_a_centred_trigger_keeps_a_centred_arrow(base_url: str) -> None:
    """Le versant LICITE : loin des bords, rien ne doit bouger.

    Une « correction » qui décalerait la flèche de tout le monde
    rendrait le test ci-dessus vert en cassant le cas ordinaire, qui est
    la quasi-totalité des bulles d'une app.
    """
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        mesure = bulle(pg, "milieu")
        assert abs(mesure["fleche_centre"] - mesure["ancre_centre"]) \
            <= TOLERANCE_PX, "la flèche a quitté son déclencheur au milieu"
        assert abs(mesure["fleche_centre"] - mesure["panneau_centre"]) \
            <= TOLERANCE_PX, (
                "au milieu de l'écran, le panneau EST centré sur son "
                "déclencheur : la flèche doit donc y être aussi")

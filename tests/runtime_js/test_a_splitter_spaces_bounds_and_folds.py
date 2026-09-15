"""``ui.resizable`` — la gouttière, le plafond, et le repli.

Les trois manques fermés le 2026-08-23
----------------------------------------
1. **`gap=`** — le groupe est un conteneur flex (racine ``flex w-full``,
   comme ``ui.flex``) et n'exposait pas l'espacement. On écrivait donc
   ``ui.hstack(gap="md")`` d'un côté et ``ui.resizable(classes="gap-4")``
   de l'autre : même CSS, deux écritures.

   Le symptôme d'origine n'y ressemblait pas — « l'espacement au niveau
   de resizable n'existe pas ». Mesuré sur la coque du CRM (parent en
   ``p-8``), le panneau commençait bien à x=32 : le padding de l'ancêtre
   l'atteignait. Mais son contenu courait jusqu'à 384, où la poignée
   commence. **Un padding d'ancêtre ne peut pas créer d'espace à
   l'INTÉRIEUR du groupe** ; seul le parent des panneaux sait où est la
   poignée.

2. **`max_size`** — ``min_size`` vivait seul. Une asymétrie, pas une
   décision : un panneau qu'on veut borner à 45 % n'avait aucun moyen de
   le dire.

3. **`collapsible`** — double-clic sur la poignée (ou ``Entrée`` quand
   elle a le focus) range le panneau et rend sa place au voisin. Le
   geste **passe outre ``min_size``**, et c'est le but : le minimum dit
   « ne me réduis pas en tirant », le repli dit « range-le ».

Pourquoi au NAVIGATEUR
-----------------------
Rien de tout ça ne se lit dans le HTML. La gouttière est une valeur
calculée entre deux boîtes ; le plafond ne se voit qu'en TIRANT au-delà ;
le repli est un aller-retour d'état piloté par un double-clic. Un test
SSR vérifierait que les classes et les attributs sont là — ce qu'ils
étaient déjà, à l'époque où le geste ne marchait pas.

⚠️ Le versant **licite** est verrouillé autant que l'autre : que le
glissement soit INSENSIBLE à la gouttière est le fait qui autorise
`gap=` (la math somme les largeurs de panneaux, elle n'a jamais supposé
qu'elles remplissaient le conteneur). Sans cette mesure, la prop serait
un pari.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_splitter_spaces_bounds_and_folds.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

app = Bretzel(secret_key="s" * 32, title="Bretzel · splitter", mode="dev")

#: L'échelle `md`, en pixels — `gap-4` vaut `1rem`.
_GAP_MD_PX = 16


def fill(label: str) -> None:
    with ui.flex(justify="center", align="center", classes="h-40 w-full"):
        ui.text(label)


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-8 w-[900px]"):
        with ui.resizable(sizes=[40, 60], id="nu"):
            with ui.resizable_panel():
                fill("A")
            with ui.resizable_panel():
                fill("B")

        with ui.resizable(sizes=[40, 60], gap="md", id="espace"):
            with ui.resizable_panel():
                fill("A")
            with ui.resizable_panel():
                fill("B")

        with ui.resizable(sizes=[40, 60], id="borne"):
            with ui.resizable_panel(min_size=20, max_size=45):
                fill("borné")
            with ui.resizable_panel():
                fill("libre")

        with ui.resizable(sizes=[40, 60], id="pliable"):
            with ui.resizable_panel(min_size=25, collapsible=True):
                fill("range-moi")
            with ui.resizable_panel():
                fill("voisin")

        with ui.resizable(sizes=[40, 60], id="clavier"):
            with ui.resizable_panel(min_size=25, collapsible=True):
                fill("au clavier")
            with ui.resizable_panel():
                fill("voisin")


app.include(__name__)

#: Les largeurs des deux panneaux + la gouttière de gauche, en pixels.
_GEOM = """(id) => {
  const g = document.getElementById(id);
  const panels = g.querySelectorAll(':scope > [data-bz-rz-panel]');
  const handle = g.querySelector(':scope > [data-bz-rz-handle]');
  const r = (e) => e.getBoundingClientRect();
  return {
    a: Math.round(r(panels[0]).width),
    b: Math.round(r(panels[1]).width),
    gouttiere: Math.round(r(handle).left - r(panels[0]).right),
    valuenow: handle.getAttribute('aria-valuenow'),
  };
}"""


def _drag(pg, group: str, dx: int) -> None:
    """Tirer la poignée de ``group`` de ``dx`` pixels."""
    handle = pg.query_selector(f"#{group} [data-bz-rz-handle]")
    box = handle.bounding_box()
    y = box["y"] + box["height"] / 2
    pg.mouse.move(box["x"] + box["width"] / 2, y)
    pg.mouse.down()
    pg.mouse.move(box["x"] + box["width"] / 2 + dx, y, steps=10)
    pg.mouse.up()
    pg.wait_for_timeout(250)


@pytest.fixture(scope="module")
def pg():
    with audit_server(app) as url:
        with browser_page(url, "/") as page_:
            page_.wait_for_selector("html.bz-ready")
            page_.wait_for_timeout(600)
            yield page_


class TestTheGutter:
    def test_a_bare_group_has_none(self, pg) -> None:
        """Contrôle POSITIF — sans quoi « il y a une gouttière » ne dit rien."""
        assert pg.evaluate(_GEOM, "nu")["gouttiere"] == 0

    def test_gap_puts_real_pixels_around_the_handle(self, pg) -> None:
        assert pg.evaluate(_GEOM, "espace")["gouttiere"] == _GAP_MD_PX, (
            f"`gap=\"md\"` ne pose rien : {pg.evaluate(_GEOM, 'espace')}. "
            f"C'est un `gap` flex ordinaire — si la classe est là et "
            f"l'espace absent, la racine n'est plus un conteneur flex."
        )

    def test_the_drag_does_not_care(self, pg) -> None:
        """Le fait qui AUTORISE la prop.

        La math du glissement somme les largeurs de PANNEAUX
        (``totalPx``) et n'a jamais supposé qu'elles remplissaient le
        conteneur. Si ce n'était pas vrai, la gouttière décalerait le
        curseur sous la poignée à chaque frame.
        """
        avant_nu = pg.evaluate(_GEOM, "nu")["a"]
        avant_gap = pg.evaluate(_GEOM, "espace")["a"]
        _drag(pg, "nu", 100)
        _drag(pg, "espace", 100)
        delta_nu = pg.evaluate(_GEOM, "nu")["a"] - avant_nu
        delta_gap = pg.evaluate(_GEOM, "espace")["a"] - avant_gap
        assert abs(delta_nu - 100) <= 3, f"sans gouttière : {delta_nu} px"
        assert abs(delta_gap - 100) <= 3, f"avec gouttière : {delta_gap} px"


class TestTheCeiling:
    def test_max_size_stops_the_handle(self, pg) -> None:
        before = pg.evaluate(_GEOM, "borne")
        _drag(pg, "borne", 600)  # bien au-delà du plafond
        after = pg.evaluate(_GEOM, "borne")
        total = after["a"] + after["b"]
        share = 100 * after["a"] / total
        assert share <= 46, (
            f"le panneau a pris {share:.1f} % malgré `max_size=45` "
            f"(avant {100 * before['a'] / (before['a'] + before['b']):.1f} %). "
            f"Le plafond n'est pas appliqué : `_pair` ne borne que par le "
            f"bas."
        )

    def test_min_size_still_stops_it_the_other_way(self, pg) -> None:
        """Contrôle POSITIF — le plancher n'a pas été cassé en ajoutant
        le plafond. Les quatre contraintes se croisent dans la même
        expression, donc l'une peut annuler l'autre."""
        _drag(pg, "borne", -600)
        after = pg.evaluate(_GEOM, "borne")
        share = 100 * after["a"] / (after["a"] + after["b"])
        assert share >= 19, f"le panneau est tombé à {share:.1f} % (min 20)"


class TestTheFold:
    def test_a_double_click_puts_it_away(self, pg) -> None:
        before = pg.evaluate(_GEOM, "pliable")
        assert before["a"] > 50, "le panneau part déjà replié"
        pg.dblclick("#pliable [data-bz-rz-handle]")
        pg.wait_for_timeout(300)
        after = pg.evaluate(_GEOM, "pliable")
        assert after["a"] <= 2, (
            f"le panneau repliable fait encore {after['a']} px après un "
            f"double-clic. ⚠️ Il porte `min_size=25` : le repli doit "
            f"PASSER OUTRE, sinon un minimum rend le repli impossible."
        )

    def test_a_second_one_brings_it_back(self, pg) -> None:
        before = pg.evaluate(_GEOM, "pliable")["a"]
        pg.dblclick("#pliable [data-bz-rz-handle]")
        pg.wait_for_timeout(300)
        after = pg.evaluate(_GEOM, "pliable")["a"]
        assert after > before + 50, (
            f"le panneau ne revient pas ({before} → {after} px). La "
            f"mémoire `_folded` a perdu sa taille d'avant."
        )

    def test_enter_does_the_same_from_the_keyboard(self, pg) -> None:
        """Un geste souris sans jumeau clavier n'existe pas pour la
        moitié des gens — et la poignée est déjà focusable."""
        before = pg.evaluate(_GEOM, "clavier")["a"]
        pg.focus("#clavier [data-bz-rz-handle]")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(300)
        after = pg.evaluate(_GEOM, "clavier")["a"]
        assert after <= 2, (
            f"`Entrée` sur la poignée ne replie pas ({before} → {after} px)."
        )
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(300)
        assert pg.evaluate(_GEOM, "clavier")["a"] > 50, "et ne déplie pas"

    def test_a_non_collapsible_group_ignores_the_gesture(self, pg) -> None:
        """Contrôle POSITIF — le repli est un opt-in, pas un défaut."""
        before = pg.evaluate(_GEOM, "nu")["a"]
        pg.dblclick("#nu [data-bz-rz-handle]")
        pg.wait_for_timeout(300)
        assert pg.evaluate(_GEOM, "nu")["a"] == before, (
            "un double-clic replie un panneau qui n'est pas `collapsible`."
        )

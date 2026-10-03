"""Les onglets se parcourent AU CLAVIER — flèches, Début, Fin.

L'index de tabulation d'une barre d'onglets est itinérant : seul l'onglet
actif est dans l'ordre de tabulation (``tabindex=0``, les autres ``-1``).
C'est le motif WAI-ARIA, et il n'a de sens qu'avec sa moitié clavier : les
flèches passent d'un onglet à l'autre. Jusqu'au 2026-10-03 cette moitié
manquait — aucune gestion de touche dans le runtime — et un utilisateur au
clavier atteignait l'onglet actif et RIEN d'autre. Aucun test ne le
voyait : tous cliquaient.

Ce que le test exige, dans un vrai Chromium :

- Flèche droite / gauche : le focus ET la sélection passent au voisin, en
  bouclant aux deux bouts ; un onglet désactivé est sauté ;
- Début / Fin : premier et dernier onglet actifs ;
- le panneau suit, et chaque onglet nomme son panneau
  (``aria-controls`` ↔ ``id``, et ``aria-labelledby`` en retour).

Le versant licite : une touche sans rôle (une lettre) ne déplace rien.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_tabs_answer_the_keyboard.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

app = Bretzel(secret_key="t" * 32, title="Bretzel · onglets au clavier", mode="dev")


@page("/")
def home() -> None:
    with ui.tabs(value="a", id="onglets"):
        ui.tab("a", label="Alpha")
        ui.tab("b", label="Beta")
        ui.tab("c", label="Gamma", disabled=True)
        ui.tab("d", label="Delta")
        for cle in ("a", "b", "c", "d"):
            with ui.tab_panel(cle):
                ui.text(f"panneau {cle}")


app.include(__name__)


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


#: L'onglet qui a le focus, celui qui est sélectionné, et le panneau visible.
ETAT = """() => {
  const actif = document.activeElement;
  const choisi = document.querySelector('[role=tab][aria-selected=true]');
  const visibles = [...document.querySelectorAll('[role=tabpanel]')]
    .filter(p => getComputedStyle(p).display !== 'none');
  return {
    focus: actif && actif.getAttribute('role') === 'tab' ? actif.dataset.tab : null,
    choisi: choisi ? choisi.dataset.tab : null,
    panneaux: visibles.map(p => p.textContent.trim()),
  };
}"""


def presser(pg, touche: str) -> dict:
    pg.keyboard.press(touche)
    pg.wait_for_timeout(50)
    return pg.evaluate(ETAT)


def test_arrows_home_and_end_move_focus_and_selection(base_url: str) -> None:
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        pg.locator('[role=tab][data-tab="a"]').focus()
        assert pg.evaluate(ETAT) == {
            "focus": "a", "choisi": "a", "panneaux": ["panneau a"],
        }, "le banc ne part pas de l'onglet a"

        parcours = [
            ("ArrowRight", "b"),
            ("ArrowRight", "d"),  # c est désactivé : sauté
            ("ArrowRight", "a"),  # boucle au bout
            ("ArrowLeft", "d"),   # et dans l'autre sens
            ("Home", "a"),
            ("End", "d"),
        ]
        for touche, attendu in parcours:
            etat = presser(pg, touche)
            assert etat == {
                "focus": attendu, "choisi": attendu,
                "panneaux": [f"panneau {attendu}"],
            }, f"{touche} : attendu l'onglet {attendu!r}, obtenu {etat}"


def test_a_key_without_a_role_moves_nothing(base_url: str) -> None:
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        pg.locator('[role=tab][data-tab="a"]').focus()
        etat = presser(pg, "x")
        assert etat == {"focus": "a", "choisi": "a", "panneaux": ["panneau a"]}, (
            f"une lettre a déplacé l'onglet : {etat}"
        )


def test_each_tab_names_its_panel_and_back(base_url: str) -> None:
    with browser_page(base_url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        liens = pg.evaluate("""() => [...document.querySelectorAll('[role=tab]')]
          .map(t => {
            const p = document.getElementById(t.getAttribute('aria-controls'));
            return [t.dataset.tab, !!p && p.getAttribute('role') === 'tabpanel'
                    && p.getAttribute('aria-labelledby') === t.id];
          })""")
        assert len(liens) == 4, f"{len(liens)} onglets trouvés, 4 attendus"
        casses = [cle for cle, ok in liens if not ok]
        assert not casses, f"onglets sans panneau lié dans les deux sens : {casses}"

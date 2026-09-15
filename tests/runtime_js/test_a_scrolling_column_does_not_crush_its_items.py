"""L'idiome documenté d'une colonne qui défile n'écrase PAS ses items.

Le bug, mesuré le 2026-08-21 (finding [26], rapporté par l'utilisateur en
se servant du CRM) : « les personnes sont coupées en deux » sur la liste
de contacts. Et le détail qui rend le défaut si dur à voir en revue : « il
n'y a qu'à la page 803 qu'on voit mieux » — c'est la dernière page, 6
lignes au lieu de 25. Le contenu tient, donc rien ne s'écrase. Même code,
deux rendus.

Le mécanisme
-------------
La taille minimale automatique d'un flex-item ne vaut son contenu **que
si son débordement est visible**. Dès que sa racine clippe
(``overflow-hidden`` et compagnie), ``min-height: auto`` retombe à zéro :
dans une colonne à hauteur bornée, l'item se comprime jusqu'au premier
enfant qui refuse, et le reste est coupé — sans scrollbar interne, sans
erreur.

Pourquoi une gate sur la DOC plutôt qu'un correctif
----------------------------------------------------
La correction n'appartient pas au composant : poser ``shrink-0`` sur le
root de ``ui.card`` déplacerait le bug, parce qu'une carte est aussi un
PANNEAU réductible. Elle appartient au CONTENEUR, qui seul sait s'il
défile — et elle s'écrit ``[&>*]:shrink-0``, la quatrième classe de
l'idiome, celle que personne n'écrit.

Une doc qu'on croit ne vaut rien : ce test mesure que l'idiome à quatre
classes tient VRAIMENT, sur la population que la gate rapide a découverte
(``tests/consistency/test_a_clipping_root_is_documented.py``), et il garde
le **témoin à trois classes** — sans quoi il passerait aussi bien si la
quatrième ne servait à rien, et la doc prescrirait une superstition.

⚠️ Le témoin est la moitié qui coûte. C'est lui qui prouve que
``[&>*]:shrink-0`` est *load-bearing* ; les deux bras doivent rester.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_scrolling_column_does_not_crush_its_items.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

#: L'idiome COMPLET, celui que ``traps.md`` prescrit.
_IDIOM = "w-56 h-[380px] min-h-0 overflow-y-auto [&>*]:shrink-0"

#: Le même, amputé de sa quatrième classe — le témoin.
_NAIVE = "w-56 h-[380px] min-h-0 overflow-y-auto"

#: Combien d'items il faut pour REMPLIR la colonne. En dessous, rien ne
#: s'écrase et le test passerait pour de mauvaises raisons — c'est très
#: exactement ce que « il n'y a qu'à la page 803 qu'on voit mieux »
#: décrit.
_ENOUGH = 25


def _card() -> None:
    with ui.card(), ui.vstack(gap="xs"):
        ui.text("Nora Moreau", weight="bold")
        ui.text("12 activités")
        ui.badge("actif")


app = Bretzel(
    secret_key="c" * 32,
    title="Bretzel · colonne qui défile",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.hstack(gap="lg", align="start", classes="p-6"):
        # Le témoin de RÉFÉRENCE : la même carte, sans contrainte.
        with ui.vstack(gap="xs", classes="w-56", id="free"):
            _card()
        with ui.vstack(gap="xs", classes=_IDIOM, id="idiom"):
            for _ in range(_ENOUGH):
                _card()
        with ui.vstack(gap="xs", classes=_NAIVE, id="naive"):
            for _ in range(_ENOUGH):
                _card()


app.include(__name__)

_MEASURE = """(sel) => {
  const el = document.querySelector(sel + ' > *');
  if (!el) return null;
  return { h: el.getBoundingClientRect().height,
           clipped: el.scrollHeight - el.clientHeight };
}"""


@pytest.fixture(scope="module")
def measured():
    with audit_server(app) as url, browser_page(url, "/") as pg:
        pg.wait_for_selector("html.bz-ready")
        pg.wait_for_timeout(600)
        yield {
            key: pg.evaluate(_MEASURE, f"#{key}")
            for key in ("free", "idiom", "naive")
        }


@pytest.mark.browser
def test_the_free_card_is_tall_enough_to_be_crushed(measured) -> None:
    """Le plancher. Une carte déjà minuscule ne pourrait pas s'écraser, et
    les deux bras ci-dessous passeraient sans rien dire."""
    free = measured["free"]
    assert free and free["h"] >= 80, (
        f"la carte témoin ne fait que {free and free['h']}px — il n'y a "
        f"rien à comprimer, donc rien à mesurer."
    )


@pytest.mark.browser
def test_the_documented_idiom_keeps_the_items_whole(measured) -> None:
    free, idiom = measured["free"], measured["idiom"]
    assert idiom is not None, "la colonne à l'idiome n'a rendu aucun item"
    assert abs(free["h"] - idiom["h"]) < 1, (
        f"l'idiome documenté n'empêche PAS l'écrasement : la carte fait "
        f"{idiom['h']:.0f}px dans la colonne contre {free['h']:.0f}px "
        f"libre.\n"
        f"  `traps.md` § « Une colonne qui défile ÉCRASE ses items » "
        f"prescrit `{_IDIOM}` — s'il ne tient plus, c'est la DOC qu'il "
        f"faut corriger, pas ce test."
    )
    assert idiom["clipped"] <= 0, (
        f"{idiom['clipped']:.0f}px de contenu coupés malgré l'idiome."
    )


@pytest.mark.browser
def test_without_the_fourth_class_the_items_are_crushed(measured) -> None:
    """Le TÉMOIN — la moitié qui prouve que la quatrième classe sert.

    Sans lui, ce fichier passerait tout aussi bien le jour où
    ``[&>*]:shrink-0`` deviendrait inutile (un navigateur qui change de
    règle, un composant qui se met à porter ``shrink-0`` lui-même) — et la
    doc continuerait de prescrire une superstition à tout le monde.
    """
    free, naive = measured["free"], measured["naive"]
    assert naive is not None, "la colonne naïve n'a rendu aucun item"
    assert naive["h"] < free["h"] - 1, (
        f"à TROIS classes, la carte n'est plus écrasée "
        f"({naive['h']:.0f}px contre {free['h']:.0f}px libre). Deux "
        f"lectures, et il faut trancher avant de toucher au test :\n"
        f"  - soit un composant s'est mis à se protéger lui-même "
        f"(`shrink-0` sur sa racine) — alors la gate rapide l'a déjà "
        f"sorti de la population, et il faut changer de sujet ici ;\n"
        f"  - soit le comportement CSS a changé, et c'est `traps.md` "
        f"qu'il faut réécrire.\n"
        f"  Dans les deux cas, ne supprime pas ce bras : c'est lui qui "
        f"dit que la quatrième classe est load-bearing."
    )

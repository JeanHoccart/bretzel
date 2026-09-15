"""``ui.button(href=…)`` — l'habillage d'un bouton, la sémantique d'un lien.

Le trou qu'elle ferme (finding [6])
-------------------------------------
« Pas de lien-bouton » : ``ui.link`` n'a que trois variantes de TEXTE et
``ui.button`` n'avait pas de ``href=``. Un appel à l'action qui NAVIGUE
n'avait aucune forme dans le catalogue.

En mesurant, le trou s'est révélé plus étroit que rapporté :
``ui.button(tag="a", attrs={"href": …})`` marchait — c'est l'échappatoire
tier 2, et elle rend l'ancre avec tout l'habillage. Ce qui manquait était
le tier 1, et la correction de deux défauts que l'échappatoire livrait
tels quels :

1. un ``type="button"`` **sur un ``<a>``**, où l'attribut désigne le type
   MIME de la cible ;
2. un état ``disabled`` **purement décoratif** : le thème habillait
   l'état via ``disabled:``, c'est-à-dire la pseudo-classe ``:disabled``,
   qui ne matche jamais un ``<a>``. Le lien-bouton désactivé s'affichait
   à pleine opacité, curseur normal, et s'éclaircissait encore au survol.

Pourquoi au NAVIGATEUR
-----------------------
Le point 2 ne se lit pas dans une chaîne de classes : ``disabled:opacity-50``
EST présent dans le HTML des deux côtés — c'est le navigateur qui décide
qu'il ne s'applique pas. Il faut un ``getComputedStyle``, et une feuille
Tailwind réellement compilée. Un test SSR aurait été vert sur le bug.

Et le point qui justifie la prop plutôt que ``classes=`` se mesure ici
aussi : un ``<a>`` NAVIGUE au clic. C'est une différence fonctionnelle,
pas décorative — c'est ce qui lui fait mériter sa place au sens de la
règle d'API.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_link_button_is_a_real_link.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

app = Bretzel(secret_key="l" * 32, title="Bretzel · lien-bouton", mode="dev")


def act() -> None:  # pragma: no cover — jamais appelé, câblé pour comparer
    pass


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", align="start", classes="p-8"):
        ui.button("Agir", on_click=act, id="plain")
        ui.button("Créer", href="/ailleurs", id="lien")
        ui.button("Indisponible", href="/ailleurs", disabled=True, id="off")
        ui.button("Doc", href="/ailleurs", external=True, id="ext")


@page("/ailleurs")
def ailleurs() -> None:
    ui.text("Arrivé", id="arrivee")


app.include(__name__)

_LOOK = """(sel) => {
  const el = document.querySelector(sel);
  const st = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  return {
    tag: el.tagName, href: el.getAttribute('href'),
    type: el.getAttribute('type'), rel: el.getAttribute('rel'),
    target: el.getAttribute('target'),
    aria: el.getAttribute('aria-disabled'), tab: el.getAttribute('tabindex'),
    h: Math.round(r.height), radius: st.borderRadius,
    bg: st.backgroundColor, color: st.color,
    opacity: Number(st.opacity), cursor: st.cursor,
  };
}"""


@pytest.fixture(scope="module")
def live():
    """UNE session pour tout le fichier.

    Playwright sync refuse un second contexte dans la même boucle
    asyncio : le test de navigation partage donc la page des mesures, et
    passe en dernier — il quitte l'écran.
    """
    with audit_server(app) as url:
        with browser_page(url, "/") as pg:
            pg.wait_for_selector("html.bz-ready")
            pg.wait_for_timeout(600)
            yield pg


@pytest.fixture(scope="module")
def look(live):
    return {
        name: live.evaluate(_LOOK, f"#{name}")
        for name in ("plain", "lien", "off", "ext")
    }


def test_it_is_an_anchor_and_not_a_button(look) -> None:
    assert look["lien"]["tag"] == "A", (
        f"ui.button(href=…) rend un {look['lien']['tag']} : le clic-milieu, "
        f"« ouvrir dans un nouvel onglet » et le rôle lu par un lecteur "
        f"d'écran sont perdus. C'est toute la raison d'être de la prop."
    )
    assert look["lien"]["href"] == "/ailleurs"
    assert look["plain"]["tag"] == "BUTTON", "le bouton nu a changé de balise"


def test_the_anchor_drops_the_button_type(look) -> None:
    """Sur un ``<a>``, ``type`` désigne un type MIME."""
    assert look["lien"]["type"] is None, (
        f"`<a type={look['lien']['type']!r}>` : l'attribut survit à la "
        f"bascule de balise et ment sur ce qu'il désigne. C'est ce que "
        f"livrait l'échappatoire `tag=\"a\"`."
    )
    assert look["plain"]["type"] == "button", (
        "contrôle POSITIF : un vrai bouton garde son `type`, sinon la "
        "correction aurait juste tout effacé."
    )


def test_it_wears_the_same_clothes_as_a_button(look) -> None:
    """Le point de la fonctionnalité : même habillage, autre sémantique."""
    a, b = look["lien"], look["plain"]
    assert (a["bg"], a["color"], a["radius"]) == (b["bg"], b["color"], b["radius"]), (
        f"le lien-bouton ne ressemble pas au bouton : {a} vs {b}"
    )
    assert abs(a["h"] - b["h"]) <= 1, f"hauteurs {a['h']} vs {b['h']}"


def test_an_external_link_neuters_its_opener(look) -> None:
    """``rel`` n'est pas cosmétique : sans lui la cible atteint ``opener``."""
    assert look["ext"]["target"] == "_blank"
    assert look["ext"]["rel"] == "noopener noreferrer"


class TestTheDisabledState:
    """Celui qui ne se voyait PAS — ``:disabled`` ne matche pas un ``<a>``."""

    def test_it_is_visibly_dimmed(self, look) -> None:
        assert look["off"]["opacity"] < 0.75, (
            f"un lien-bouton désactivé rend à opacité {look['off']['opacity']} "
            f"— donc identique à un actif. Le thème habille l'état via "
            f"`disabled:`, la pseudo-classe `:disabled`, qui ne matche "
            f"JAMAIS un `<a>` : il faut les jumeaux `aria-disabled:`."
        )

    def test_an_enabled_one_is_not(self, look) -> None:
        """Contrôle POSITIF — sans lui, tout assombrir passerait la gate."""
        assert look["lien"]["opacity"] >= 0.99, (
            f"le lien-bouton ACTIF est à {look['lien']['opacity']} : la "
            f"règle désactivée s'applique à tout le monde."
        )

    def test_the_cursor_says_no(self, look) -> None:
        assert look["off"]["cursor"] == "not-allowed", (
            f"curseur `{look['off']['cursor']}` : rien n'annonce que le "
            f"contrôle est mort avant le clic."
        )

    def test_it_is_inert_and_says_so(self, look) -> None:
        assert look["off"]["href"] is None, (
            "un lien désactivé garde sa destination : le clavier et le "
            "clic-milieu y vont quand même."
        )
        assert look["off"]["aria"] == "true"
        assert look["off"]["tab"] == "-1"


@pytest.mark.browser
def test_zz_clicking_it_actually_navigates(live, look) -> None:
    """La preuve que ce n'est pas qu'un habillage : ça mène quelque part.

    ``zz`` dans le nom : il quitte la page, donc il passe APRÈS les
    mesures (pytest exécute dans l'ordre du fichier, mais le préfixe le
    dit à qui relit).
    """
    live.click("#lien")
    live.wait_for_selector("#arrivee", timeout=5000)
    assert "/ailleurs" in live.url, f"resté sur {live.url}"

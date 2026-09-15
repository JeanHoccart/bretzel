"""Gate navigateur — l'écran gelé : le document ne défile pas, les panes si.

Ce qu'elle garde
-----------------
``ui.viewport`` + ``ui.pane`` livrés le 2026-08-23 mettent un nom sur une
chaîne de classes recopiée dix-sept fois dans ``examples/``. Ce que ces
classes FONT ne se lit pas dans le HTML — il faut un moteur de rendu.
Quatre affirmations, chacune mesurée en pixels :

1. sous un ``viewport``, le **document n'a aucune barre de défilement** —
   c'est toute la promesse du modèle gelé ;
2. le ``pane``, lui, **défile** ;
3. **deux panes côte à côte défilent indépendamment** — c'est la seule
   chose que le modèle « document qui défile » ne sait pas faire, donc la
   seule justification du coût du modèle gelé ;
4. un pane défile dans les **deux formes de parent** — colonne flex avec
   un en-tête épinglé, et bloc à hauteur définie.

Le témoin, et ce qu'il prouve VRAIMENT
----------------------------------------
La route ``/en-flux`` rend le même contenu **sans cadre ni pane** : le
document doit alors déborder. Sans elle, « le document ne défile pas »
pourrait être vrai parce que l'instrument ne sait pas mesurer autre
chose que zéro.

⚠️ Ce n'est **pas** un témoin du piège ``h-screen``, et il faut le dire.
J'ai essayé de le reproduire — un cadre ``h-screen w-full
overflow-hidden`` avec une colonne fixe et un panneau qui défile, dans
Chromium, 150 lignes de contenu : ``scrollHeight - clientHeight`` vaut
**0**, avec ``fixed`` comme avec ``h-screen``, avec et sans le ``h-full``
du pane. L'inflation mesurée deux fois en 2026 venait donc d'autre chose
que de cette forme minimale — un maillon de hauteur cassé plus bas, très
probablement. ``fixed inset-0`` reste la forme livrée (c'est la
convention mesurée du dépôt, deux fois, et la changer n'est pas le sujet
de ce commit), mais la justification écrite dans ``traps.md`` n'a **pas**
été re-mesurée ici. À savoir avant de re-tenter un revert : l'absence de
reproduction n'est pas une preuve d'innocuité.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_frozen_screen_scrolls_only_its_panes.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

#: Assez de contenu pour déborder d'un écran de test, sans quoi rien ne
#: défile et les deux bras passeraient pour de mauvaises raisons.
_ENOUGH = 60


def _filler(prefix: str) -> None:
    for i in range(_ENOUGH):
        with ui.card(padding="sm"):
            ui.text(f"{prefix} {i + 1}", size="sm")


app = Bretzel(secret_key="v" * 32, title="Bretzel · écran gelé", mode="dev")


@page("/")
def frozen() -> None:
    """La forme livrée : un cadre gelé, deux panes indépendants."""
    with ui.viewport():
        with ui.vstack(gap="sm", classes="w-48 shrink-0 p-3", id="fixe"):
            ui.text("Colonne fixe")
        with ui.pane(gap="xs", padding="sm", id="gauche"):
            _filler("Gauche")
        with ui.pane(gap="xs", padding="sm", id="droite"):
            _filler("Droite")


@page("/en-flux")
def in_flow() -> None:
    """Le TÉMOIN — le même contenu, sans cadre ni pane.

    Le document doit déborder. C'est ce qui prouve que l'instrument sait
    mesurer autre chose que zéro : sans lui,
    ``test_the_document_does_not_scroll`` serait vert même si la sonde
    lisait toujours 0.
    """
    with ui.vstack(gap="xs", classes="p-4", id="temoin"):
        _filler("Témoin")


@page("/parents")
def parents() -> None:
    """Les deux formes de parent, côte à côte.

    ``flex-1`` seul échoue dans le parent bloc, ``h-full`` seul rate la
    place restante dans la colonne flex — le pane porte les deux, et
    c'est ici qu'on vérifie que la paire tient dans les deux.
    """
    with ui.viewport():
        # Parent = colonne flex, avec un en-tête qui doit rester épinglé.
        with ui.vstack(gap="none", classes="flex-1 min-w-0"):
            with ui.hstack(classes="shrink-0 px-3 py-2", id="entete"):
                ui.text("En-tête épinglé")
            with ui.pane(gap="xs", padding="sm", id="sous_entete"):
                _filler("Colonne")
        # Parent = bloc à hauteur définie, le pane est son seul enfant.
        with ui.vstack(gap="none", classes="flex-1 min-w-0"):
            with ui.card(padding="none", classes="h-full"):
                with ui.pane(gap="xs", padding="sm", id="dans_bloc"):
                    _filler("Bloc")


app.include(__name__)

_DOC = """() => ({
  docScroll: document.documentElement.scrollHeight
             - document.documentElement.clientHeight,
  barWidth: window.innerWidth - document.documentElement.clientWidth,
})"""

_BOX = """(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  return { overflow: el.scrollHeight - el.clientHeight,
           top: Math.round(el.getBoundingClientRect().top),
           h: Math.round(el.getBoundingClientRect().height) };
}"""


def _goto(pg, path: str) -> None:
    """Naviguer dans la page déjà ouverte, et attendre le runtime."""
    pg.goto(pg.url.split("/", 3)[0] + "//" + pg.url.split("/", 3)[2] + path)
    pg.wait_for_selector("html.bz-ready", state="attached")
    pg.wait_for_timeout(400)


@pytest.fixture(scope="module")
def live():
    with audit_server(app) as url, browser_page(url, "/") as pg:
        pg.set_viewport_size({"width": 1100, "height": 600})
        pg.wait_for_selector("html.bz-ready", state="attached")
        pg.wait_for_timeout(400)
        yield pg


# ───────────────────────────────────────────────────────────────────────
# ① Le plancher — il y a bien de quoi déborder
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_the_panes_have_something_to_scroll(live) -> None:
    for pane_id in ("gauche", "droite"):
        box = live.evaluate(_BOX, f"#{pane_id}")
        assert box is not None, f"#{pane_id} n'a pas été rendu"
        assert box["overflow"] > 200, (
            f"#{pane_id} ne déborde que de {box['overflow']}px : il n'y a "
            f"presque rien à faire défiler, et « le document ne défile "
            f"pas » serait vrai sans rien prouver."
        )


# ───────────────────────────────────────────────────────────────────────
# ② La promesse du modèle gelé
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_the_document_does_not_scroll(live) -> None:
    doc = live.evaluate(_DOC)
    assert doc["docScroll"] <= 1, (
        f"le document déborde de {doc['docScroll']}px sous un "
        f"`ui.viewport` : il y a une SECONDE barre de défilement en plus "
        f"de celle du pane. C'est le piège que `fixed inset-0` ferme — "
        f"vérifie que le thème du viewport n'est pas repassé en "
        f"`h-screen` (cf. traps.md, le correctif a déjà été reverté une "
        f"fois)."
    )
    assert doc["barWidth"] <= 1, (
        f"une barre de défilement de {doc['barWidth']}px est rendue au "
        f"niveau du viewport."
    )


@pytest.mark.browser
def test_two_panes_scroll_independently(live) -> None:
    """La justification entière du modèle gelé."""
    live.evaluate("() => document.querySelector('#gauche').scrollTop = 300")
    live.wait_for_timeout(120)
    positions = live.evaluate(
        "() => [document.querySelector('#gauche').scrollTop,"
        "       document.querySelector('#droite').scrollTop]"
    )
    assert positions[0] > 250, (
        f"le pane de gauche n'a pas défilé (scrollTop={positions[0]}) — "
        f"il grandit au lieu de défiler, donc `min-h-0` ou "
        f"`overflow-y-auto` a disparu de son thème."
    )
    assert positions[1] == 0, (
        f"faire défiler le pane de GAUCHE a bougé celui de droite "
        f"(scrollTop={positions[1]}) : les deux régions partagent un "
        f"conteneur de défilement, donc le modèle ne tient pas sa seule "
        f"promesse."
    )


# ───────────────────────────────────────────────────────────────────────
# ③ Le témoin — la moitié qui prouve que `fixed` sert
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_without_a_viewport_the_document_does_scroll(live) -> None:
    """Le contrôle POSITIF — la sonde sait lire autre chose que zéro.

    Même contenu, sans cadre ni pane : le document déborde. Si ce test
    rougissait, ``test_the_document_does_not_scroll`` serait vert pour
    une raison qu'on ne connaîtrait pas (une sonde qui rend toujours 0,
    une page qui ne rend rien).
    """
    _goto(live, "/en-flux")
    doc = live.evaluate(_DOC)
    assert doc["docScroll"] > 200, (
        f"sans `ui.viewport`, le document ne déborde que de "
        f"{doc['docScroll']}px alors qu'il porte {_ENOUGH} cartes : la "
        f"sonde ou la page ne rend pas ce qu'on croit, et l'assertion "
        f"« le document ne défile pas » ne prouve alors plus rien."
    )


# ───────────────────────────────────────────────────────────────────────
# ④ Les deux formes de parent
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def parent_shapes(live):
    """Mesures de ``/parents``, prises sur LA page de ``live``.

    Pas un second ``browser_page`` : Playwright sync refuse un deuxième
    contexte dans la même boucle asyncio, et la fixture mourait sur
    « It looks like you are using Playwright Sync API inside the asyncio
    loop ».
    """
    _goto(live, "/parents")
    return {
        key: live.evaluate(_BOX, f"#{key}")
        for key in ("entete", "sous_entete", "dans_bloc")
    }


@pytest.mark.browser
@pytest.mark.parametrize(
    ("pane_id", "forme"),
    [("sous_entete", "colonne flex sous un en-tête"),
     ("dans_bloc", "bloc à hauteur définie")],
)
def test_a_pane_scrolls_in_both_parent_shapes(parent_shapes, pane_id,
                                              forme) -> None:
    box = parent_shapes[pane_id]
    assert box is not None, f"#{pane_id} n'a pas été rendu"
    assert box["overflow"] > 200, (
        f"le pane ne défile pas dans un parent « {forme} » : il fait "
        f"{box['h']}px et ne déborde que de {box['overflow']}px, donc il "
        f"a GRANDI au lieu de se borner.\n"
        f"  Le thème doit porter `flex-1` ET `h-full` : dans une colonne "
        f"flex c'est `flex-basis` qui rend et `h-full` est ignoré ; dans "
        f"un bloc c'est l'inverse. Retirer l'un casse une des deux "
        f"formes, et seulement une."
    )


@pytest.mark.browser
def test_the_pinned_header_kept_its_place(parent_shapes) -> None:
    """Le contrôle : le pane a pris la place RESTANTE, pas toute la place.

    S'il avait pris toute la hauteur, l'en-tête serait poussé hors du
    cadre — c'est le mode d'échec exact de `h-full` seul dans une colonne
    flex, et sans ce contrôle le test ci-dessus resterait vert.
    """
    entete, pane = parent_shapes["entete"], parent_shapes["sous_entete"]
    assert entete is not None and entete["h"] > 0, "en-tête non rendu"
    assert entete["top"] >= 0, (
        f"l'en-tête épinglé est sorti par le haut (top={entete['top']}) : "
        f"le pane a pris toute la hauteur au lieu de la place restante."
    )
    assert pane["top"] >= entete["top"] + entete["h"] - 1, (
        f"le pane chevauche son en-tête (pane top={pane['top']}, en-tête "
        f"bas={entete['top'] + entete['h']})."
    )

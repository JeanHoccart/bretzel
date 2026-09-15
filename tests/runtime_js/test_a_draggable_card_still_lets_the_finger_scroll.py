"""Le doigt peut DÉFILER une colonne de cartes déplaçables — et attraper.

Le bug, rapporté par l'utilisateur (finding [27], 2026-08-21) : « le
tactile ne marche pas, je ne peux pas scroller en sélectionnant les
cards ». Mesuré : ``ui.draggable`` sans ``handle=`` posait
``touch-action: none`` sur TOUTE la carte, ce qui retire au navigateur le
geste de défilement sur cette surface. Dans un kanban dont les colonnes
sont pleines de cartes, le doigt ne pouvait plus faire défiler **dès
qu'il se posait sur une carte** — c'est-à-dire presque partout.

Un arbitrage jamais mesuré, et le code affirmait le contraire
--------------------------------------------------------------
``19_dnd.js`` porte un seuil ``TOUCH_TOLERANCE_PX`` commenté « c'est elle
qui PRÉSERVE LE SCROLL : un doigt qui file dans une liste ne doit pas
emporter la carte qu'il a effleurée ». Le désarmement marchait très bien.
Mais la CSS avait déjà interdit le défilement, donc **rien ne défilait** —
un commentaire qui promettait un comportement que la feuille de style
rendait impossible. Le thème et le geste avaient été écrits séparément,
chacun juste de son côté.

Pourquoi ce test est en contexte TACTILE réel
-----------------------------------------------
``tests/runtime_js/test_dnd_gesture.py`` couvre déjà le geste, mais en
dispatchant des ``PointerEvent`` synthétiques : ce chemin ne passe pas par
la décision du navigateur, donc il reste vert quel que soit le
``touch-action`` du composant. Il ne pouvait pas voir ce bug, et ne le
verra jamais. Ici le contexte est ``has_touch`` et les événements partent
par CDP (``Input.dispatchTouchEvent``) : c'est Chromium qui arbitre entre
défiler et nous donner le geste, comme chez l'utilisateur.

Les DEUX bras comptent
-----------------------
Rendre le défilement en cassant l'attrape ne vaut rien — et c'est
exactement ce qui arrive avec le seul changement de CSS : mesuré
``pan-x pan-y`` seul, le défilement revient (0 → 335 px) **et l'attrape
est perdue**. Il a fallu la seconde moitié : un ``touchmove`` NON PASSIF
qui reprend le geste une fois l'appui long abouti. À cet instant le doigt
n'a pas bougé, donc aucun défilement n'est en cours et la reprise est
propre.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_draggable_card_still_lets_the_finger_scroll.py -q -m browser
"""

from __future__ import annotations

import time

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

_ITEM = "[data-bz-draggable]"

#: L'appui qui fait basculer du défilement vers l'attrape. Au-dessus du
#: ``TOUCH_HOLD_MS`` du runtime (250 ms), avec de la marge.
_HOLD_MS = 450


def moved(move=None) -> None:
    """Le handler n'a rien à faire : ce qui est mesuré, c'est le GESTE."""


app = Bretzel(
    secret_key="t" * 32,
    title="Bretzel · doigt et cartes déplaçables",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="sm", classes="p-4 h-screen min-h-0"):
        ui.text("colonne", weight="bold")
        with ui.vstack(
            gap="xs",
            classes="flex-1 min-h-0 overflow-y-auto [&>*]:shrink-0",
            id="col",
        ), ui.dropzone(name="col", on_move=moved):
            for i in range(30):
                with ui.draggable(key=str(i)), ui.card(padding="sm"):
                    ui.text(f"carte {i}")


app.include(__name__)

_SCROLLTOP = "() => document.querySelector('#col').scrollTop"
_DRAGGING = (
    "() => !!document.querySelector('[data-bz-dragging=\"true\"]')"
    " || !!document.querySelector('.bz-drag-preview')"
)


def _swipe(cdp, x, y0, y1, *, steps=12, hold_ms=0, release=True) -> None:
    """Un VRAI geste tactile — le seul chemin qui passe par ``touch-action``."""
    cdp.send("Input.dispatchTouchEvent", {
        "type": "touchStart", "touchPoints": [{"x": x, "y": y0, "id": 1}],
    })
    if hold_ms:
        time.sleep(hold_ms / 1000)
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [{"x": x, "y": y0 + (y1 - y0) * i / steps, "id": 1}],
        })
        time.sleep(0.02)
    if release:
        cdp.send("Input.dispatchTouchEvent",
                 {"type": "touchEnd", "touchPoints": []})


@pytest.fixture(scope="module")
def touched():
    with (
        audit_server(app) as url,
        browser_page(url, "/", touch=True, viewport=(420, 780)) as pg,
    ):
        pg.wait_for_selector("html.bz-ready")
        pg.wait_for_timeout(600)
        cdp = pg.context.new_cdp_session(pg)
        cdp.send("Emulation.setTouchEmulationEnabled",
                 {"enabled": True, "maxTouchPoints": 5})
        yield pg, cdp


@pytest.mark.browser
def test_the_column_can_scroll_at_all(touched) -> None:
    """Le plancher : la colonne a de quoi défiler.

    Sans lui, une colonne trop courte rendrait le bras « ça défile »
    faux-négatif — et le bras « ça n'écrase pas » vert pour rien."""
    pg, _ = touched
    room = pg.evaluate(
        "() => { const c = document.querySelector('#col');"
        " return c.scrollHeight - c.clientHeight; }"
    )
    assert room > 200, (
        f"la colonne n'a que {room}px de débattement — il n'y a rien à "
        f"faire défiler, donc rien à mesurer."
    )


@pytest.mark.browser
def test_a_draggable_item_never_forbids_panning(touched) -> None:
    """Le versant CSS, lu sur le COMPUTED — pas sur la chaîne de classes.

    Une classe peut être écrite et ne pas compiler (cf. la memory sur les
    classes assemblées) ; ce qui décide du geste, c'est ce que le
    navigateur calcule.
    """
    pg, _ = touched
    value = pg.evaluate(
        f"() => getComputedStyle(document.querySelector('{_ITEM}')).touchAction"
    )
    assert value != "none", (
        "une carte déplaçable pose `touch-action: none`, donc le doigt ne "
        "peut plus faire défiler la colonne dès qu'il se pose dessus — "
        "c'est-à-dire presque partout dans un kanban.\n"
        "  Le thème doit laisser le pan (`touch-pan-x touch-pan-y`), et "
        "c'est le `touchmove` NON PASSIF de `19_dnd.js` qui reprend le "
        "geste une fois l'appui long abouti."
    )


@pytest.mark.browser
def test_a_finger_flicking_scrolls_the_column(touched) -> None:
    pg, cdp = touched
    pg.evaluate("() => document.querySelector('#col').scrollTop = 0")
    pg.wait_for_timeout(150)
    before = pg.evaluate(_SCROLLTOP)
    _swipe(cdp, 200, 600, 250)
    pg.wait_for_timeout(400)
    after = pg.evaluate(_SCROLLTOP)
    assert after > before + 20, (
        f"le doigt n'a fait défiler la colonne que de {after - before}px "
        f"en partant d'une CARTE. C'est le symptôme rapporté : « je ne "
        f"peux pas scroller en sélectionnant les cards »."
    )


@pytest.mark.browser
def test_a_long_press_still_grabs_the_card(touched) -> None:
    """L'autre bras — celui qui interdit de « réparer » en cassant.

    Le seul changement de CSS rend le défilement ET perd l'attrape :
    mesuré, ``pan-x pan-y`` sans le `touchmove` non passif laisse le
    navigateur emporter le geste. Si ce test rougit pendant que le
    précédent passe, la moitié runtime du correctif a sauté.
    """
    pg, cdp = touched
    pg.evaluate("() => document.querySelector('#col').scrollTop = 0")
    pg.wait_for_timeout(150)
    _swipe(cdp, 200, 300, 480, hold_ms=_HOLD_MS, release=False)
    grabbed = pg.evaluate(_DRAGGING)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd",
                                          "touchPoints": []})
    assert grabbed, (
        "un appui long suivi d'un glissement n'attrape plus la carte : le "
        "geste tactile est mort. Vérifie le `touchmove` non passif de "
        "`19_dnd.js` — sans lui, le navigateur emporte le geste dès que "
        "l'item laisse le pan."
    )

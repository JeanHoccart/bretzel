"""Gate : un overlay FERMÉ n'a aucune commande joignable au clavier.

Le défaut, mesuré
-----------------
Un ``ui.dialog`` fermé se cache en ``visibility:hidden``
(``data-[open=false]:invisible``). Mais ``visibility`` est la propriété
qu'un DESCENDANT peut reprendre à son compte, et la règle anti-flash du
shell le faisait pour tout porteur de ``bz-data`` :
``html.bz-ready [bz-data]{visibility:visible}``. Le premier composant à
état client d'un dialogue fermé redevenait donc ``visible`` — sans être
peint ni occuper de place, mais **focusable**.

Constaté le 2026-09-07 sur ``examples/messagerie`` : la 2ᵉ tabulation de
la page atterrissait dans le ``ui.file_upload`` du dialogue de rédaction.
Un utilisateur au clavier remplissait un formulaire qu'il ne voyait pas.
Rejoué sur banc le 2026-09-10, corrigé en bornant la règle au pré-boot
(``html:not(.bz-ready)``), qui ne relève plus rien après le scan.

Pourquoi une gate NAVIGATEUR
-----------------------------
Aucune lecture de HTML ne le voit : les classes sont exactement celles
qu'on attend, le nœud est là, le ``data-open="false"`` est juste. C'est
la CASCADE qui ment, et seul un moteur de rendu la calcule. Le balayage
de ``bretzel.probe`` porte la même mesure pour les apps ; celle-ci tient
les composants du framework, qui n'ont pas d'app.

Les quatre familles, et pas seulement les deux atteintes
--------------------------------------------------------
``dialog`` et ``drawer`` cachent en ``visibility`` — ce sont eux qui
mordaient. ``popover`` et ``dropdown`` cachent en ``display:none``, qu'un
descendant ne peut pas reprendre : ils étaient déjà saufs. Ils restent
dans la gate parce que l'invariant est « un overlay fermé est
inatteignable », pas « la règle anti-flash est bornée » — le jour où l'un
des deux passera à ``visibility`` pour animer sa sortie, la gate le dira
avant l'utilisateur.

Run : ``py -m pytest tests/runtime_js/test_a_closed_overlay_is_out_of_the_tab_order.py -q -m browser``
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser

#: Les familles d'overlay, et le fait qu'elles soient FERMÉES est tout le
#: sujet — aucune n'est ouverte ici.
FAMILIES = ("dialog", "drawer", "popover", "dropdown")

#: Combien de tabulations. Le tour complet de la page de sonde fait trois
#: contrôles ; vingt le parcourt six fois, donc un contrôle fantôme
#: n'échappe pas à la mesure en se rangeant tard dans l'ordre.
_TABS = 20

#: On vise le PANNEAU, jamais la racine : celle d'un ``popover`` contient
#: son déclencheur, qui est légitimement joignable. Et on vise les
#: marqueurs que le framework pose déjà — ``data-bz-overlay`` vient de
#: ``show_attrs``, ``bz-ref="bzpanel"`` de ``_anchored`` — plutôt qu'un
#: attribut planté sur le contenu : un marqueur maison ne couvrirait que
#: les nœuds qu'on a pensé à taguer, et laisserait passer une fuite sur
#: le bouton de fermeture, qui vit dans l'en-tête du panneau.
#:
#: Le sélecteur ancré ne dit pas « fermé » — un panneau de ``popover``
#: fermé est en ``display:none``, donc rien ne peut y prendre le focus.
#: Sur cette page où AUCUN overlay n'est ouvert, y être est la faute.
_CLOSED_PANEL = '[data-bz-overlay][data-open="false"], [bz-ref="bzpanel"]'

_WHO_HAS_FOCUS = f"""() => {{
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    return {{
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 50),
        visibility: getComputedStyle(el).visibility,
        inClosedOverlay: el.closest('{_CLOSED_PANEL}') !== null,
    }};
}}"""


def _build_probe_app() -> Bretzel:
    """Une page par famille : un contrôle avant, l'overlay fermé, un après."""
    app = Bretzel(secret_key="s" * 32, mode="dev")
    #: Chaque famille se construit différemment — les ancrés veulent un
    #: déclencheur — et c'est la SEULE différence entre les quatre pages.
    builders = {
        "dialog": lambda: ui.dialog(title="sonde"),
        "drawer": lambda: ui.drawer(title="sonde"),
        "popover": lambda: ui.popover(trigger=ui.button("déclencheur")),
        "dropdown": lambda: ui.dropdown(trigger=ui.button("déclencheur")),
    }
    assert tuple(builders) == FAMILIES

    def build(family: str):
        @page(f"/{family}")
        def probe_page() -> None:
            ui.button("avant")
            with builders[family]():
                # Le contenu n'est pas au hasard. ``ui.file_upload``
                # porte un ``bz-data`` — c'est LUI qui déclenchait le
                # défaut — et ``ui.input`` est le témoin : il n'en porte
                # pas, donc il restait correctement masqué. Retirer le
                # ``file_upload`` rendrait la gate verte pour la mauvaise
                # raison.
                ui.file_upload()
                ui.input(placeholder="sujet")
            ui.button("après")

        return probe_page

    app.include(*(build(family) for family in FAMILIES))
    return app


@pytest.fixture(scope="module")
def base_url():
    """Un seul uvicorn pour les quatre familles."""
    with audit_server(_build_probe_app()) as url:
        yield url


def _tab_through(base_url: str, path: str) -> list[dict]:
    # ``wait_until="load"`` : une page portant un overlay peut tenir une
    # connexion ouverte, et ``networkidle`` n'arriverait jamais.
    # ``browser_page`` attend déjà 600 ms après le chargement, de quoi
    # laisser finir les transitions — inutile d'en rajouter.
    with browser_page(base_url, path, wait_until="load") as browser:
        seen = []
        for _ in range(_TABS):
            browser.keyboard.press("Tab")
            focused = browser.evaluate(_WHO_HAS_FOCUS)
            if focused is not None:
                seen.append(focused)
        return seen


@pytest.mark.parametrize("family", FAMILIES)
def test_a_closed_overlay_never_receives_the_focus(
    family: str, base_url: str
) -> None:
    """Vingt tabulations, et aucune n'entre dans le panneau fermé."""
    seen = _tab_through(base_url, f"/{family}")

    assert seen, (
        f"aucune tabulation n'atteint quoi que ce soit sur /{family} — la "
        "gate ne mesure rien ; vérifier que la page rend ses boutons."
    )
    intruders = [f for f in seen if f["inClosedOverlay"]]
    assert not intruders, (
        f"Un ui.{family} FERMÉ garde {len(intruders)} contrôle(s) dans "
        f"l'ordre de tabulation : {intruders[:3]}\n\n"
        "Invisible et pourtant joignable au clavier — un utilisateur "
        "tabule dans un formulaire qu'il ne voit pas. Cause connue : une "
        "règle CSS qui redéclare `visibility:visible` sur un descendant "
        "du panneau. `visibility` est écrasable par un descendant ; "
        "`display:none` et `inert` ne le sont pas."
    )

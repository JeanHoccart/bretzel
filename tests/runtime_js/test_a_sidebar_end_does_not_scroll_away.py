"""Le pied de la barre ne part pas avec la nav — en pixels.

Le complément de ``tests/consistency/test_a_wrapped_sidebar_end_stays_pinned``,
qui vérifie la STRUCTURE (le nœud n'est pas dans la box qui défile). Ici
on vérifie la CONSÉQUENCE, dans Chromium : il ne bouge pas d'un pixel
quand on fait défiler.

Les deux ne sont pas redondants. La containment se lit dans le SSR et
tourne à chaque ``pytest`` ; elle ne dit rien du cas où la box de
défilement changerait de forme et emporterait quand même le pied (un
``position: sticky`` mal placé, une hauteur qui déborde le cadre). Une
mesure de position le dit.

Le défaut mesuré le 2026-08-23, deux barres côte à côte, même contenu :

    pied nu             504 px → 504 px   fixe
    pied @refreshable   656 px → 504 px   il glisse

Le pied d'``examples/crm`` est une zone — il affiche le compte connecté
et doit se rafraîchir quand on en change. Le playground n'a jamais montré
le défaut parce que son pied n'est pas enveloppé.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_a_sidebar_end_does_not_scroll_away.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, refreshable, ui
from bretzel.state import SessionState, field
from tests.audit.harness import audit_server, browser_page

app = Bretzel(secret_key="p" * 32, title="Bretzel · pied de barre", mode="dev")


class Prefs(SessionState):
    tick: int = field(default=0)


def body() -> None:
    """Assez d'entrées pour que la nav déborde à 560 px de haut."""
    for section in ("VENTES", "PILOTAGE", "OUTILS"):
        with ui.sidebar_section(label=section):
            for i in range(4):
                ui.sidebar_item(f"{section} {i}", icon="circle", href=f"/{section}{i}")


def footer_markup() -> None:
    with ui.sidebar_footer(name="Aïcha Benali", subtitle="Commercial"):
        ui.sidebar_footer_item(label="Paramètres", icon_left="settings",
                               href="/p")


@refreshable(deps=[Prefs])
def footer_in_a_zone() -> None:
    """La forme d'``examples/crm`` : le pied DOIT être rafraîchissable."""
    footer_markup()


@page("/")
def home() -> None:
    with ui.hstack(gap="none", align="stretch",
                   classes="fixed inset-0 w-full overflow-hidden"):
        with ui.sidebar(collapsible="rail", open=True, id="nu"):
            ui.sidebar_title("Nu")
            body()
            footer_markup()
        with ui.sidebar(collapsible="rail", open=True, id="zone"):
            ui.sidebar_title("Zone")
            body()
            footer_in_a_zone()
        ui.text("contenu")


app.include(__name__)

_PROBE = """(id) => {
  const aside = document.getElementById(id);
  const scroll = aside.querySelector('[class*="overflow-y-auto"]');
  // Le premier element AVEC UNE BOITE qui porte le nom. L'ordre du
  // document donne l'exterieur d'abord ; le filtre sur la hauteur ecarte
  // l'enveloppe de la zone, qui se rend en ``display:contents`` et n'a
  // donc aucune boite (c'est ce qui la rend transparente a la
  // disposition, et ce qui faisait rendre 0 a un rect naif).
  const foot = Array.from(aside.querySelectorAll('*')).find(
    (e) => e.textContent.includes("Aïcha Benali")
           && e.getBoundingClientRect().height > 0);
  if (!scroll || !foot) return {erreur: 'introuvable', scroll: !!scroll, foot: !!foot};
  const top = () => Math.round(foot.getBoundingClientRect().top);
  const avant = top();
  scroll.scrollTop = scroll.scrollHeight;
  const apres = top();
  scroll.scrollTop = 0;
  return {
    deborde: Math.round(scroll.scrollHeight - scroll.clientHeight),
    dans_le_scroll: scroll.contains(foot),
    avant: avant, apres: apres, glissement: Math.abs(apres - avant),
  };
}"""


@pytest.fixture(scope="module")
def live():
    """UNE session pour tout le fichier.

    Playwright sync refuse un second contexte dans la même boucle
    asyncio. 560 px de haut : assez court pour que la nav déborde —
    sans débordement il n'y a rien à faire défiler, et tout serait vert
    quoi qu'il arrive.
    """
    with audit_server(app) as url:
        with browser_page(url, "/", viewport=(1200, 560)) as pg:
            pg.wait_for_selector("html.bz-ready", state="attached")
            pg.wait_for_timeout(600)
            yield pg


@pytest.fixture(scope="module")
def probe(live):
    return {name: live.evaluate(_PROBE, name) for name in ("nu", "zone")}


@pytest.mark.parametrize("bar", ["nu", "zone"])
def test_the_nav_really_overflows(probe, bar) -> None:
    """① Le plancher : sans débordement, rien ne pourrait glisser."""
    assert probe[bar].get("deborde", 0) > 40, (
        f"la nav de la barre « {bar} » ne déborde pas ({probe[bar]}), donc "
        f"le test ne mesure rien. Rallonge `body()` ou raccourcis le "
        f"viewport."
    )


@pytest.mark.parametrize("bar", ["nu", "zone"])
def test_the_footer_stays_put(probe, bar) -> None:
    """② Il ne bouge pas."""
    r = probe[bar]
    assert r["glissement"] == 0, (
        f"le pied de la barre « {bar} » glisse de {r['glissement']} px "
        f"quand la nav défile ({r['avant']} → {r['apres']}).\n"
        f"  dans la box de défilement : {r['dans_le_scroll']}\n"
        f"  `Sidebar.render` déballe ses enfants avec "
        f"`base/_wiring.unwrap_transparent` avant son `isinstance` : un "
        f"pied ENVELOPPÉ — `@refreshable`, `ui.fragment` — n'est plus une "
        f"instance de `SidebarFooter`, c'était le bug d'origine."
    )


def test_both_bars_agree(probe) -> None:
    """Le contrôle POSITIF : l'enveloppe ne change RIEN.

    Sans lui, « le pied ne bouge pas » passerait aussi sur une barre où
    plus rien ne défile du tout.
    """
    assert probe["nu"]["avant"] == probe["zone"]["avant"], (
        f"les deux pieds ne sont pas à la même hauteur : "
        f"{probe['nu']['avant']} vs {probe['zone']['avant']}. L'un des "
        f"deux est encore dans le flux de la nav."
    )


@pytest.mark.parametrize("bar", ["nu", "zone"])
def test_the_edge_lets_the_wheel_through(live, bar) -> None:
    """L'arête de repli est une VITRE : le clic s'y arrête, la molette passe.

    Le second défaut du même endroit, rapporté à l'usage le
    2026-08-23 : « je ne peux pas scroller car il y a la sidebar qui me
    propose la fermeture ». L'arête est ``absolute``, enfant direct de
    l'aside, donc HORS de la boîte qui défile — et le navigateur fait
    défiler ce qui est sous le pointeur. Mesuré avant correctif, dans
    les deux états : 400 px de molette au-dessus de la bande laissaient
    ``scrollTop`` à **0**. Sur 16 px courant sur toute la hauteur, c'est
    toute la colonne de droite de la barre qui était morte à la molette.

    Le témoin — la même molette AILLEURS dans la barre — donne la valeur
    que le geste doit atteindre, au lieu d'un seuil choisi à la main.
    """
    edge = live.query_selector(f"#{bar} [class*='railedge']")
    assert edge is not None, f"pas d'arête sur la barre « {bar} »"
    box = edge.bounding_box()

    def wheel_at(x: float, y: float) -> int:
        live.evaluate(
            "(id) => { document.querySelector('#' + id + ' .bz-rail-scroll')"
            ".scrollTop = 0; }", bar)
        live.mouse.move(x, y)
        live.mouse.wheel(0, 400)
        live.wait_for_timeout(300)
        return live.evaluate(
            "(id) => Math.round(document.querySelector('#' + id + "
            "' .bz-rail-scroll').scrollTop)", bar)

    aside = live.query_selector(f"#{bar}").bounding_box()
    ailleurs = wheel_at(aside["x"] + 8, 300)
    sur_arete = wheel_at(box["x"] + box["width"] / 2, 300)

    assert ailleurs > 0, (
        f"la nav de « {bar} » ne défile pas ({ailleurs}) : rien à mesurer."
    )
    assert sur_arete == ailleurs, (
        f"« {bar} » : la molette au-dessus de l'arête donne {sur_arete} là "
        f"où elle donne {ailleurs} ailleurs dans la barre. La bande mange "
        f"le geste — elle est hors de la boîte qui défile, donc le "
        f"navigateur ne trouve rien à faire défiler sous le pointeur. "
        f"Elle doit transmettre le `deltaY` elle-même (`bz-on:wheel`)."
    )

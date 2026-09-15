"""La barre latérale a une commande de repli VISIBLE dans les deux états.

Le défaut qu'elle ferme (finding [29], mesuré le 2026-08-21)
------------------------------------------------------------
Dans le rail replié, le bouton de repli **portait le logo** et se changeait
en chevron **au survol**. Sur une machine sans survol — un portable
tactile, celle de l'utilisateur, dont le Chrome rapporte ``hover: none``
et dix points de contact — il n'y avait donc aucun signal : le logo avait
l'air d'un logo, et rien ne disait que la barre pouvait se rouvrir. Le
geste existait et **personne ne pouvait le découvrir**.

Second défaut du même endroit : le logo changeait de MÉTIER selon l'état.
Lien vers l'accueil déplié, bouton de repli replié. Deux fonctions sur la
même cible, et l'une des deux inaccessible à tout moment.

Ce que la gate mesure, et pourquoi au navigateur
--------------------------------------------------
Une commande « visible » ne se lit pas dans une chaîne de classes : il
faut une boîte non nulle et un ``visibility`` calculé. Et « elle replie
vraiment » ne se lit nulle part ailleurs que dans la largeur de l'aside
après le clic. Les deux se mesurent ici, dans les DEUX états, et sur les
DEUX formes de barre — avec un ``ui.sidebar_title`` et sans, parce que
c'est la présence d'un titre qui décide du chevron auto.

⚠️ Ce que la gate n'affirme PAS : que la commande soit jolie ou bien
placée. Elle ferme la classe : *une barre qu'on ne peut pas rouvrir sans
deviner*.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_the_sidebar_can_always_be_collapsed.py -q -m browser
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, page, ui
from tests.audit.harness import audit_server, browser_page

#: Le plancher de cible tactile, WCAG 2.2 § 2.5.8 — le même que cite le
#: thème de ``ui.draggable``. Une commande plus petite existe sans être
#: atteignable au doigt.
_TARGET_PX = 24

#: L'exception, ÉCRITE et bornée : une bande qui court sur toute la
#: hauteur de la barre. Sa largeur seule ne dit pas si elle est visable —
#: 16 × 600 px se pointe très bien à la souris, et c'est une affordance
#: ``md:`` (desktop) par construction.
#:
#: Le compromis a été mesuré : à 24 px la bande recouvrait les 13 px de
#: droite des icônes de nav du rail (il leur restait 28 px sur 40) ; à
#: 16 px elle n'en prend plus que 4. Rendre l'arête conforme au plancher
#: revenait à faire descendre les icônes vers lui.
_STRIP_MIN_PX = 16
_STRIP_MIN_HEIGHT = 200

app = Bretzel(
    secret_key="s" * 32,
    title="Bretzel · replier la barre",
    mode="dev",
)


def _nav() -> None:
    with ui.sidebar_section(label="MENU"):
        ui.sidebar_item("Accueil", icon="home", href="/")
        ui.sidebar_item("Contacts", icon="users", href="/c")


@page("/titled")
def titled() -> None:
    with ui.hstack(gap="none", classes="h-screen w-full overflow-hidden"):
        with ui.sidebar(open=False, collapsible="rail"):
            ui.sidebar_title("Mon CRM", icon="zap")
            _nav()
        ui.text("contenu")


@page("/bare")
def bare() -> None:
    """Sans titre : l'arête est la SEULE commande.

    C'est le cas le plus exposé — il n'y a pas de bouton d'en-tête pour
    rattraper. Le chevron flottant qui jouait ce rôle a été retiré : il
    se rendait sous l'arête, donc il n'était plus cliquable.
    """
    with ui.hstack(gap="none", classes="h-screen w-full overflow-hidden"):
        with ui.sidebar(open=False, collapsible="rail"):
            _nav()
        ui.text("contenu")


app.include(__name__)

#: Toute commande capable de replier : celles que le composant rend
#: (arête, chevron auto, chevron d'en-tête). Découvertes par leur RÔLE —
#: un ``<button>`` dans l'aside — pas par une classe, qui changerait avec
#: le thème.
_CONTROLS = """() => {
  const aside = document.querySelector('aside');
  return Array.from(aside.querySelectorAll('button')).map((b) => {
    const r = b.getBoundingClientRect();
    const st = getComputedStyle(b);
    return { w: Math.round(r.width), h: Math.round(r.height),
             visible: st.visibility !== 'hidden' && st.opacity !== '0',
             label: b.getAttribute('aria-label') || '' };
  });
}"""

_WIDTH = "() => Math.round(document.querySelector('aside').getBoundingClientRect().width)"


def _usable(controls: list[dict]) -> list[dict]:
    """Les commandes réellement visables — deux formes, deux règles.

    Une commande COMPACTE (le bouton de l'en-tête) doit tenir le plancher
    de 24 × 24. Une BANDE qui court sur toute la hauteur est jugée sur sa
    largeur seule, avec un plancher plus bas : sa surface la rend visable
    même étroite, et c'est le compromis qui garde aux icônes de nav leur
    propre cible.
    """
    out = []
    for c in controls:
        if not c["visible"]:
            continue
        compact = c["w"] >= _TARGET_PX and c["h"] >= _TARGET_PX
        strip = c["w"] >= _STRIP_MIN_PX and c["h"] >= _STRIP_MIN_HEIGHT
        if compact or strip:
            out.append(c)
    return out


@pytest.fixture(scope="module")
def base_url():
    with audit_server(app) as url:
        yield url


@pytest.mark.parametrize("path", ["/titled", "/bare"])
@pytest.mark.browser
def test_a_collapsed_sidebar_shows_a_usable_control(base_url, path) -> None:
    with browser_page(base_url, path) as pg:
        pg.wait_for_selector("html.bz-ready")
        pg.wait_for_timeout(500)
        usable = _usable(pg.evaluate(_CONTROLS))
    assert usable, (
        f"la barre repliée de {path} n'expose AUCUNE commande visible — ni "
        f"bouton de {_TARGET_PX}px, ni bande de {_STRIP_MIN_PX}px sur "
        f"toute la hauteur. Elle ne peut être rouverte que par "
        f"quelqu'un qui sait déjà où appuyer.\n"
        f"  Une commande révélée au survol ne compte pas — c'est le défaut "
        f"d'origine, et elle n'existe pas sur une machine tactile."
    )


@pytest.mark.parametrize("path", ["/titled", "/bare"])
@pytest.mark.browser
def test_the_control_really_collapses_and_reopens(base_url, path) -> None:
    """Visible ne suffit pas : il faut que ça REPLIE, dans les deux sens."""
    with browser_page(base_url, path) as pg:
        pg.wait_for_selector("html.bz-ready")
        pg.wait_for_timeout(500)
        collapsed = pg.evaluate(_WIDTH)
        target = _usable(pg.evaluate(_CONTROLS))[0]["label"]
        pg.click(f"[aria-label={target!r}]")
        pg.wait_for_timeout(500)
        opened = pg.evaluate(_WIDTH)
        pg.click(f"[aria-label={target!r}]")
        pg.wait_for_timeout(500)
        back = pg.evaluate(_WIDTH)
    assert opened > collapsed + 50, (
        f"{path} : la commande « {target} » est visible mais n'ouvre pas la "
        f"barre ({collapsed}px → {opened}px)."
    )
    assert back == collapsed, (
        f"{path} : la barre ne se referme pas ({opened}px → {back}px)."
    )


@pytest.mark.browser
def test_the_rail_logo_is_a_link_and_not_a_toggle(base_url) -> None:
    """Le logo a UN métier, et c'est de mener quelque part.

    Il portait les deux : lien déplié, bouton de repli replié. Une même
    cible qui change de fonction selon un état que rien n'annonce, c'est
    ce qui a fait dire « je ne comprends pas ».
    """
    with browser_page(base_url, "/titled") as pg:
        pg.wait_for_selector("html.bz-ready")
        pg.wait_for_timeout(500)
        found = pg.evaluate("""() => {
          const aside = document.querySelector('aside');
          const els = Array.from(aside.querySelectorAll('a, button'));
          const logo = els.find((e) => {
            const r = e.getBoundingClientRect();
            return r.top < 80 && r.width >= 24 && r.height >= 24
                && getComputedStyle(e).visibility !== 'hidden'
                && e.querySelector('iconify-icon');
          });
          return logo ? { tag: logo.tagName, href: logo.getAttribute('href') }
                      : null;
        }""")
    assert found is not None, "aucun logo visible en tête du rail"
    assert found["tag"] == "A" and found["href"], (
        f"le logo du rail est un {found['tag']} sans destination : il "
        f"replie la barre au lieu de mener quelque part, et c'est un "
        f"métier qu'il ne tient QUE dans cet état.\n"
        f"  Le repli appartient à l'arête (`rail_edge`), visible dans les "
        f"deux états."
    )

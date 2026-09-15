"""Gate : la tête de rail a un logo par défaut, et jamais de lien vide.

Ce qu'elle ferme
----------------
``ui.sidebar_title`` rendait sa « marque de rail » — le lien qui porte le
logo dans la barre repliée — même quand aucune icône n'était donnée. Un
``<a>`` sans enfant n'est pas invisible pour autant : mesuré le
2026-09-12 sur un rail replié, il occupait **40 × 40 px** en tête de
barre et prenait le **premier focus**. La première tabulation atterrissait
donc sur un lien qu'on ne voit pas.

Deux défauts pour un, et le second est le plus coûteux :

- à l'œil, un trou au-dessus des items — c'est ce que l'utilisateur a vu
  et signalé (« tu n'as pas mis de logo, et maintenant on voit un espace
  vide ») ;
- au clavier, un contrôle invisible et joignable. Même famille que
  l'overlay fermé qui gardait ses commandes dans l'ordre de tabulation,
  fermé le 2026-09-10.

Les DEUX moitiés du remède
---------------------------
1. **Un défaut** : ``icon="home"``, comme ``ui.datatable`` a
   ``empty_icon="inbox"``. Le rail a donc toujours quelque chose à
   montrer, et le glyphe décrit ce que le lien fait — il mène à
   ``href=``, dont le défaut est ``/``. C'est la moitié qui règle
   l'ergonomie, proposée par l'utilisateur.
2. **Une garde** : sans glyphe, le nœud n'est pas rendu du tout. C'est la
   moitié qui règle la CORRECTION, et elle reste nécessaire — le défaut
   se désactive (``icon=""``), et ce jour-là le lien vide reviendrait.

⚠️ L'échappatoire est ``icon=""`` et **pas** ``icon=None`` : le socle
drope les kwargs réactifs à ``None`` pour garder le défaut, donc un
``None`` explicite est indistinguable d'un argument absent. Vérifié, et
c'est pourquoi la chaîne vide est testée ici plutôt que ``None`` — une
gate qui aurait employé ``None`` aurait mesuré le cas par défaut en
croyant mesurer l'opt-out, et serait passée pour de mauvaises raisons.

Les trois états
---------------
Le versant illicite seul ne dirait rien : un composant qui ne rendrait
JAMAIS de marque passerait aussi. On mesure donc les trois.

Run : ``py -m pytest tests/runtime_js/test_a_rail_without_a_logo_has_no_empty_link.py -q -m browser``
"""

from __future__ import annotations

import pytest

from bretzel import Bretzel, layout, page, ui
from bretzel.probe import probe

pytestmark = pytest.mark.browser

#: Le rail replié — 64 px de large. C'est l'état où la marque existe.
REPLIE = (
    "() => document.querySelector('aside')"
    ".getAttribute('data-open') === 'false'"
)

#: Ce que la tête de barre contient VRAIMENT, une fois repliée.
TETE = """
() => {
    const aside = document.querySelector('aside');
    const liens = [...aside.querySelectorAll('a')];
    const vides = liens.filter(
        a => a.children.length === 0 && !a.innerText.trim()
    ).map(a => {
        const r = a.getBoundingClientRect();
        return {aria: a.getAttribute('aria-label'),
                w: Math.round(r.width), h: Math.round(r.height)};
    });
    const marque = aside.querySelector('a[aria-label="Atelier"]');
    const glyphe = marque && marque.querySelector('iconify-icon');
    return {
        vides,
        marque: marque === null ? null : {
            glyphes: marque.querySelectorAll('iconify-icon').length,
            nom: glyphe ? glyphe.getAttribute('icon') : null,
        },
    };
}
"""

FOCUS = """
() => {
    const el = document.activeElement;
    const r = el.getBoundingClientRect();
    return {tag: el.tagName, texte: (el.innerText || '').trim(),
            aria: el.getAttribute('aria-label'),
            w: Math.round(r.width), h: Math.round(r.height)};
}
"""

#: Le sentinelle « pas d'argument », distinct de toute valeur passable.
DEFAUT = object()


def build(icone: object) -> Bretzel:
    """Une app à UNE page sous un rail — la seule variable est l'icône."""
    app = Bretzel(secret_key="s" * 32, mode="dev")

    @layout
    def coque() -> None:
        with ui.viewport():
            with ui.sidebar(collapsible="rail"):
                if icone is DEFAUT:
                    ui.sidebar_title("Atelier")
                else:
                    ui.sidebar_title("Atelier", icon=icone)
                with ui.sidebar_section(label="Mesures"):
                    ui.sidebar_item("Tâches", icon="activity", href="/")
                    ui.sidebar_item("Phases", icon="layers", href="/b")
            with ui.pane(classes="flex-1 min-w-0 p-6"):
                ui.outlet()

    @page("/", title="banc", layout=coque)
    def accueil() -> None:
        ui.text("contenu")

    app.include(coque, accueil)
    return app


PAR_DEFAUT = build(DEFAUT)
SANS = build("")
EXPLICITE = build("activity")


def replier(window) -> None:
    """Replier la barre, et ATTENDRE que ce soit fait.

    L'état se lit sur ``data-open`` : cliquer puis mesurer tout de suite
    lirait la barre encore dépliée, où la marque de rail est masquée de
    toute façon — le constat serait vert sans rien prouver.
    """
    window.click('button[aria-label*="ollapse"]')
    window.page.wait_for_function(REPLIE, timeout=5000)
    window.settle()


def test_a_title_without_an_icon_gets_the_default_logo() -> None:
    """① Le DÉFAUT : sans rien écrire, le rail a sa marque."""
    with probe(PAR_DEFAUT) as p:
        (a,) = p.windows
        a.goto("/")
        replier(a)

        tete = a.page.evaluate(TETE)
        p.check("aucun lien vide", not tete["vides"], tete["vides"])
        p.check(
            "la marque de rail porte le glyphe par défaut",
            tete["marque"] is not None and "home" in (tete["marque"]["nom"] or ""),
            tete["marque"],
        )


def test_an_empty_icon_renders_no_link_at_all() -> None:
    """② L'OPT-OUT : `icon=""` ne laisse ni trou ni lien vide.

    C'est la moitié « correction » du remède, et elle reste nécessaire
    malgré le défaut — sans elle, désactiver le logo ramènerait un
    contrôle invisible dans l'ordre de tabulation.
    """
    with probe(SANS) as p:
        (a,) = p.windows
        a.goto("/")
        replier(a)

        tete = a.page.evaluate(TETE)
        p.check("aucun lien VIDE dans la barre repliée",
                not tete["vides"], tete["vides"])
        p.check("et aucune marque de rail du tout",
                tete["marque"] is None, tete["marque"])

        a.press("Tab")
        premier = a.page.evaluate(FOCUS)
        p.check(
            "la première tabulation atteint un contrôle VISIBLE",
            bool(premier["texte"] or premier["aria"]) and premier["w"] > 0,
            premier,
        )


def test_an_explicit_icon_is_the_one_rendered() -> None:
    """③ Le versant LICITE — sinon « ne jamais rien rendre » passerait."""
    with probe(EXPLICITE) as p:
        (a,) = p.windows
        a.goto("/")
        replier(a)

        tete = a.page.evaluate(TETE)
        p.check("aucun lien vide non plus", not tete["vides"], tete["vides"])
        p.check(
            "c'est le glyphe DEMANDÉ qui est rendu, pas le défaut",
            tete["marque"] is not None
            and "activity" in (tete["marque"]["nom"] or ""),
            tete["marque"],
        )

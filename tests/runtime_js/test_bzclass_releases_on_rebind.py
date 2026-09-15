"""``bz-class`` doit RETIRER sa classe quand il quitte l'élément.

Le pendant exact de ``test_bzclass_survives_morph`` — même directive,
faute symétrique. Là-bas la classe DISPARAISSAIT à tort après un morph ;
ici elle SURVIT à tort après une navigation.

La faute (reproduite en direct le 2026-08-16 sur ``examples/todo``)
------------------------------------------------------------------
``bindEl`` commence par ``disposeEl``, et le bridge re-bind après CHAQUE
swap htmx. Le handler ``class`` capture une baseline au bind ::

    const base = new Set(el.classList);   // 02_directives.js

``base`` existe pour protéger un token que le thème répète entre sa
couche statique et sa couche dynamique — un vrai bug, documenté sur
place. Mais l'ancien effet mourait en LAISSANT ses classes sur
l'élément : au re-bind suivant, elles entraient dans la nouvelle
``base`` et devenaient **définitivement irretirables**. Le garde finissait
par protéger ce que le RUNTIME avait ajouté au lieu de ce que le SERVEUR
avait écrit.

Mesuré avant le fix, après un partial-nav de ``/`` vers ``/stats`` ::

    Tasks    data-active=false    fond peint=True    <-- incohérent
    Stats    data-active=true     fond peint=True

Un item à MOITIÉ actif : ``bz-attr:data-active`` bascule (il n'a pas de
baseline), ``bz-class`` non. Les deux canaux d'un même état divergent, et
le thème ne gate qu'une moitié de la couche active sur ``data-active`` —
d'où un fond peint sous un texte resté gris.

Pourquoi ce test NAVIGUE
------------------------
C'est le point, pas un détail de mise en scène. Le dépôt n'avait AUCUNE
suite qui navigue : les tests montent une page et s'arrêtent. Tout ce qui
ne survit pas à un partial-nav était donc structurellement hors
couverture — ce bug a vécu sous 34 tests verts. Une assertion sur un
rendu statique ne peut pas le voir : il faut deux pages et un swap entre
les deux.

Lourd (uvicorn + Chromium) — lancer explicitement ::

    py -m pytest tests/runtime_js/test_bzclass_releases_on_rebind.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

#: Les lignes de nav de la sidebar du playground. Elles portent la couche
#: active via ``bz-class`` UNIQUEMENT (``active=None`` → le serveur n'émet
#: aucune classe active), ce qui en fait une sonde sans ambiguïté : un
#: fond peint ne peut venir que de la directive.
_ROWS = "aside a[class*='group/row']"

#: ⚠️ Deux précautions, chacune apprise sur un faux positif de CETTE
#: gate — et toutes deux nécessaires pour que « peint » veuille dire
#: quelque chose :
#:
#: 1. la ligne porte ``transition-all duration-200`` : lue trop tôt, une
#:    couche en train de disparaître compte encore comme peinte. On coupe
#:    la transition avant de mesurer plutôt que d'attendre au hasard ;
#: 2. le clic de Playwright LAISSE le pointeur sur sa cible, et le thème
#:    a ``data-[active=false]:hover:bg-text/10``. Sans écarter la souris,
#:    la gate accuse le survol d'être une couche active résiduelle.
_STATE = """
() => {
  const rows = [...document.querySelectorAll("aside a")]
    .filter(a => a.className.includes("group/row"));
  for (const a of rows) a.style.transition = "none";
  return rows.map(a => ({
    href: a.getAttribute("href"),
    active: a.dataset.active,
    painted: getComputedStyle(a).backgroundColor !== "rgba(0, 0, 0, 0)",
  }));
}
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_active_layer_is_released_after_a_rebind(base_url: str) -> None:
    """Le geste qui compte est le RE-BIND, pas la navigation seule.

    ⚠️ Une première version de ce test se contentait de naviguer, et elle
    passait AVEC LE FIX RETIRÉ — donc elle ne gardait rien. La raison est
    structurelle : un partial-nav ne swappe que l'outlet, la sidebar vit
    en dehors, elle n'est donc jamais re-bindée. Sur ``examples/todo``
    (realtime, zones ``broadcast``) elle l'était, d'où le bug là-bas et
    pas ici.

    On force donc le re-bind avec ``$bz._scan`` — exactement ce que fait
    le bridge dans ``htmx:afterSwap``, et exactement le geste que le test
    frère (``test_bzclass_survives_morph``) a retenu pour la même raison.
    """
    with browser_page(base_url, "/") as page:
        page.wait_for_selector(_ROWS)
        page.wait_for_function(
            "() => [...document.querySelectorAll('aside a')]"
            ".some(a => a.dataset.active === 'true')"
        )

        # Le re-bind : l'ancien effet meurt. S'il laisse sa classe en
        # place, elle entre dans la baseline du NOUVEAU bind et devient
        # irretirable — c'est toute la faute.
        page.evaluate("() => $bz._scan(document.querySelector('aside'))")
        page.wait_for_timeout(150)

        page.click("aside a[href='/badge']")
        page.wait_for_function("() => window.location.pathname === '/badge'")
        page.wait_for_function(
            "() => [...document.querySelectorAll('aside a')]"
            ".some(a => a.getAttribute('href') === '/badge'"
            " && a.dataset.active === 'true')"
        )

        page.mouse.move(2, 2)  # cf. _STATE : sortir du survol
        page.wait_for_timeout(150)
        stale = [
            r for r in page.evaluate(_STATE)
            if r["active"] == "false" and r["painted"]
        ]
        assert not stale, (
            "Après un re-bind puis une navigation, une entrée porte encore "
            f"sa couche active alors que ``data-active`` dit false :\n"
            f"  {stale}\n"
            "``bz-class`` n'a pas retiré ce qu'il avait ajouté en mourant : "
            "ses classes sont entrées dans la baseline ``base`` du bind "
            "suivant, où le garde les protège pour toujours — il finit par "
            "protéger ce que le RUNTIME a ajouté au lieu de ce que le "
            "SERVEUR a écrit."
        )


def test_the_probe_is_not_vacuous(base_url: str) -> None:
    """La sonde doit VOIR une couche active quand il y en a une.

    Sans ça, un sélecteur périmé (``group/row`` renommé, la sidebar qui
    change de balise) rendrait les assertions ci-dessus vertes en ne
    mesurant rien — le mode d'échec que la première version de ce fichier
    a réellement eu.
    """
    with browser_page(base_url, "/") as page:
        page.wait_for_selector(_ROWS)
        page.wait_for_function(
            "() => [...document.querySelectorAll('aside a')]"
            ".some(a => a.dataset.active === 'true')"
        )
        page.mouse.move(2, 2)
        page.wait_for_timeout(150)
        rows = page.evaluate(_STATE)
        assert len(rows) >= 3, f"sonde ne voit que {len(rows)} lignes de nav"
        painted = [r for r in rows if r["painted"]]
        assert len(painted) == 1, (
            f"exactement UNE ligne doit être peinte au repos, vu {painted}"
        )

"""Un picker reste VIVANT après une navigation ``hx-boost``.

Le trou que ce probe bouche
---------------------------
Toutes les suites de ce dépôt montent une page, agissent dessus, et
s'arrêtent là. **Aucune ne navigue.** Or le runtime n'est pas rechargé
par un ``hx-boost`` : son magasin de scopes, une ``Map`` indexée par le
``bz-id`` STRING, traverse la navigation. Tout ce qui se répète d'une
page à l'autre — un id, un parent capturé une fois — devient donc un
état partagé entre deux pages qui ne se connaissent pas.

C'est ce qui est arrivé aux quatre pickers de date. Leur
``<bz-calendar>`` interne portait un id page-indépendant
(``root_calendar_0``), donc la nouvelle page retrouvait le scope de
l'ancienne, dont le parent est le picker de la page PRÉCÉDENTE. Le
``on_change`` écrivait alors dans un scope mort : la grille se
surlignait, le champ restait vide, et il fallait un F5. Le symptôme est
indiscernable d'un composant cassé, alors que le composant est intact —
d'où le temps perdu à le chercher dedans.

Ce probe est le seul endroit du dépôt où ça peut se voir : il faut deux
pages ET la vraie sidebar. Le pendant statique et rapide est
``tests/consistency/test_panel_calendar_id_is_page_unique.py``, qui
épingle l'id à la source ; les deux sont nécessaires — celui-là ne peut
pas prouver que le scope reste vivant, celui-ci ne peut pas s'exécuter
sans navigateur.

⚠️ **Ce probe ne garde PAS l'id** — mesuré, pas supposé. Le fix a deux
niveaux, et ils se couvrent l'un l'autre : rendre l'id page-indépendant
laisse ce probe **VERT**, parce que la re-résolution du parent dans
``ensureScope`` (``03_scope.js``) rattrape la collision. Il faut retirer
les DEUX pour le faire rougir. C'est le comportement correct d'une gate
de RÉSULTAT — elle mesure ce que l'utilisateur obtient, et l'utilisateur
va bien tant qu'un des deux niveaux tient.

La conséquence pratique est le piège : voir ce probe rester vert après
avoir touché aux ids ne veut pas dire que les ids sont libres. C'est
``test_panel_calendar_id_is_page_unique`` qui garde ce niveau-là, et
lui seul.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_boost_nav_keeps_pickers_live.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

#: Deux clics sur la grille, puis l'état visible du champ.
#:
#: ⚠️ Les clics passent par le DOM et non par Playwright : le panneau est
#: fermé, donc ses cellules ne sont pas *visibles*, et ``locator.click()``
#: attendrait une visibilité qui n'arrivera jamais. Ce qu'on teste ici
#: n'est pas l'ouverture du popover (couverte ailleurs) mais le fait que
#: la valeur ATTEIGNE le champ.
_PICK_TWO_DAYS = """
async () => {
  const settle = () => new Promise(r => queueMicrotask(
      () => queueMicrotask(r)));
  const cal = document.querySelector('bz-calendar[mode="range"]');
  if (!cal) return {error: 'aucun bz-calendar[mode=range] sur la page'};
  const root = cal.parentElement.closest('[bz-data]');
  const live = [...cal.querySelectorAll(
      '[data-day-cell]:not([aria-disabled="true"])')];
  if (live.length < 15) return {error: 'grille trop courte: ' + live.length};
  const a = live[8].getAttribute('data-date');
  const b = live[14].getAttribute('data-date');
  live[8].click();  await settle();
  live[14].click(); await settle();
  return {
    a: a, b: b,
    calAttr: cal.getAttribute('value'),
    calId: cal.getAttribute('bz-id'),
    fields: [...root.querySelectorAll('input[type="text"]')].map(i => i.value),
  };
}
"""

_CLICK_SIDEBAR_LINK = """
(href) => {
  const link = document.querySelector('a[href="' + href + '"]');
  if (!link) return false;
  link.click();
  return true;
}
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_a_range_pick_lands_after_boosting_from_another_picker_page(
    base_url: str,
) -> None:
    """Arriver par la sidebar doit valoir arriver par un F5.

    Le F5 est la référence VOLONTAIRE, et pas une valeur écrite en dur :
    c'est exactement ce que l'utilisateur faisait pour contourner le bug,
    donc c'est la formulation la plus fidèle de ce qui doit tenir.
    """
    with browser_page(base_url, "/date_range_picker") as page:
        # Référence — la page atteinte directement, sans navigation.
        fresh = page.evaluate(_PICK_TWO_DAYS)
        assert "error" not in fresh, fresh

        # Puis la même page atteinte par un hx-boost depuis un AUTRE picker.
        page.goto(f"{base_url}/week_picker", wait_until="networkidle")
        assert page.evaluate(_CLICK_SIDEBAR_LINK, "/date_range_picker"), (
            "pas de lien sidebar vers /date_range_picker — la navigation "
            "du playground a bougé, ce probe ne teste plus rien."
        )
        page.wait_for_function(
            "() => location.pathname === '/date_range_picker' && "
            "!!document.querySelector('bz-calendar[mode=range]')",
            timeout=5000,
        )
        boosted = page.evaluate(_PICK_TWO_DAYS)
        assert "error" not in boosted, boosted

    assert boosted["fields"] == [boosted["a"], boosted["b"]], (
        "après une navigation hx-boost, les dates cliquées n'atteignent "
        f"plus le champ : {boosted['fields']!r} au lieu de "
        f"{[boosted['a'], boosted['b']]!r}.\n\n"
        f"La grille, elle, a bien enregistré {boosted['calAttr']!r} — donc "
        "le composant marche et c'est le SCOPE qui est mort. Le calendrier "
        f"porte bz-id={boosted['calId']!r} : s'il ne descend pas de l'id "
        "du picker, il partage son scope avec la page précédente."
    )
    assert boosted["fields"] == fresh["fields"], (
        "arriver par la sidebar ne donne pas le même résultat qu'arriver "
        f"par un F5 : {boosted['fields']!r} contre {fresh['fields']!r}."
    )

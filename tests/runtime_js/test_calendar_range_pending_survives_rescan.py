"""Une plage à moitié ouverte doit survivre à un re-scan du runtime.

Le mode ``range`` est le seul à commiter en DEUX temps : le premier clic
ouvre une plage, le second la ferme, et seul le second émet un
``change``. Entre les deux, la sélection existe — mais le scope du picker
ne peut PAS la représenter : il n'a que ``vstart`` / ``vend``, tous deux
encore vides.

C'est ce trou qui a produit le bug. Le début en attente vivait dans
l'attribut ``value`` du calendrier, et le ``bz-effect`` miroir du wrapper
traite le scope comme la source de vérité : dès qu'il re-tourne avec un
scope vide, il pousse ``''`` dans l'attribut. Or il re-tourne à **chaque
swap HTMX** — le bridge rescanne la cible (``05_bridge.js``,
``$bz._scan(target)``). Résultat : le début en attente était effacé, le
second clic rouvrait une plage au lieu de la fermer, et l'utilisateur
cliquait indéfiniment sur un champ qui restait vide.

Rien ne l'attrapait. Le symptôme dépend d'un aller-retour serveur tombant
ENTRE deux clics, donc il paraissait aléatoire ; et aucune suite ne
montait le calendrier sous son vrai miroir.

D'où la forme de ce probe : il ne rejoue AUCUN câblage à la main. Il rend
le vrai ``DateRangePicker`` et scanne son SSR, donc le miroir, le scope à
deux bornes et la place du ``<bz-calendar>`` dans l'arbre viennent tous du
composant. Une réécriture de n'importe lequel des trois reste couverte —
c'est le seul moyen que la gate ne mente pas le jour où l'implémentation
bouge.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_calendar_range_pending_survives_rescan.py -q -m browser
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.date_range_picker import DateRangePicker
from bretzel.core.serialize import serialize
from tests.audit.harness import audit_server, browser_page


def _ssr() -> str:
    """Le HTML SSR d'un ``DateRangePicker`` non lié, tel qu'il part.

    Rendre le VRAI composant, et pas une imitation de son wrapper. Une
    version recopiée à la main de ce câblage tiendrait le jour où on
    l'écrit et mentirait ensuite : le scope à deux bornes, l'``bz-effect``
    unique qui fusionne le push-store et le miroir, la position du
    ``<bz-calendar>`` dans l'arbre — tout ça peut bouger sans que le
    probe s'en aperçoive, et il continuerait à rendre vert en testant un
    montage qui n'existe plus. C'est l'idiome du répertoire (cf.
    ``test_date_picker_disabled_binding``).
    """
    with render_isolated():
        return serialize(DateRangePicker().render())


#: Monte le SSR dans une boîte qui AVALE les events.
#:
#: ⚠️ Le ``stopPropagation`` n'est pas cosmétique : le calendrier
#: dispatche un ``change`` bullant, et sans la boîte un HTMX à l'écoute
#: tuerait le contexte Playwright (cf. le probe du mode ``week``).
#:
#: ⚠️ Vider le body ne suffit PAS à isoler deux montages, et le probe
#: échoue alors par ORDRE plutôt que par cas — la signature qui fait
#: perdre le plus de temps.
#:
#: Les scopes vivent dans une Map indexée par le ``bz-id`` STRING, pas par
#: le nœud (``03_scope.js``), et le SSR rend des ids DÉTERMINISTES. Deux
#: montages successifs du même composant portent donc le même id, et
#: ``absorb`` préserve volontairement les signaux existants : le second
#: calendrier héritait des ``vstart`` / ``vend`` du test précédent, que le
#: miroir repoussait aussitôt dans son attribut ``value``.
#:
#: ``_sweepScopes`` est l'éviction du runtime lui-même — elle drope les
#: scopes dont le ``bz-id`` n'est plus dans le document. Appelée APRÈS le
#: vidage et AVANT l'insertion, elle rend le montage réellement neuf.
#: C'est ce que le bridge fait après chaque swap.
_MOUNT = """
(html) => {
  document.body.innerHTML = '';
  window.$bz._sweepScopes();
  const box = document.createElement('div');
  box.addEventListener('change', e => e.stopPropagation());
  box.innerHTML = html;
  document.body.appendChild(box);
  window.$bz._scan(box);
  return !!box.querySelector('bz-calendar[mode="range"]');
}
"""

#: Les deux clics, avec un re-scan INSÉRÉ entre eux — exactement ce que
#: le bridge fait après un swap. Rend l'état à chaque étape.
#:
#: ⚠️ Deux précautions qui coûtent un test faussement rouge si on les
#: oublie. Le repaint du début en attente est ASYNCHRONE
#: (``_scheduleRender`` batche en microtask), donc lire l'état juste
#: après ``click()`` mesure l'avant. Et ce repaint REMPLACE les
#: cellules : la référence ``a`` pointe alors sur un nœud détaché, dont
#: les attributs sont figés à jamais. D'où le ``await`` puis la
#: re-résolution par ``data-date``.
_TWO_CLICKS = """
async (rescanBetween) => {
  const settle = () => new Promise(r => queueMicrotask(
      () => queueMicrotask(r)));
  const cal = document.querySelector('bz-calendar[mode="range"]');
  const live = [...cal.querySelectorAll(
      '[data-day-cell]:not([aria-disabled="true"])')];
  const aDate = live[8].getAttribute('data-date');
  const bDate = live[14].getAttribute('data-date');
  const cellOf = d => cal.querySelector('[data-date="' + d + '"]');

  cellOf(aDate).click();
  await settle();
  const afterFirst = {
    attr: cal.getAttribute('value'),
    selected: cellOf(aDate).getAttribute('data-selected'),
  };
  if (rescanBetween) window.$bz._scan(document.body);
  await settle();
  const afterRescan = { attr: cal.getAttribute('value') };
  cellOf(bDate).click();
  await settle();
  return {
    a: aDate,
    b: bDate,
    afterFirst: afterFirst,
    afterRescan: afterRescan,
    final: cal.getAttribute('value'),
  };
}
"""

_RUNTIME = (
    Path(__file__).resolve().parents[2] / "bretzel" / "runtime" / "runtime.js"
)


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    """Page vide + runtime injecté — un seul Chromium pour le module.

    Ces tests laissent volontairement un calendrier dans un état de
    sélection intermédiaire, donc l'isolation est réelle — mais elle se
    paie au MONTAGE (``_MOUNT`` vide le body), pas en relançant un
    navigateur par test. Le lancement coûte un Playwright complet plus un
    chargement de ``/calendar`` que la fixture jette aussitôt.
    """
    with browser_page(base_url, "/calendar") as p:
        p.goto("about:blank")
        p.add_script_tag(content=_RUNTIME.read_text(encoding="utf-8"))
        p.wait_for_function(
            "() => !!customElements.get('bz-calendar')", timeout=5000
        )
        yield p


@pytest.fixture
def mounted(page):
    """Un ``DateRangePicker`` frais, scanné, dans un body vide."""
    assert page.evaluate(_MOUNT, _ssr()), "le SSR n'a pas produit de grille"
    return page


# ``pytest.mark.browser`` n'est PAS répété ici : ``tests/runtime_js/
# conftest.py`` l'estampille sur tout le répertoire.
@pytest.mark.parametrize("rescan", [False, True], ids=["nominal", "rescan"])
def test_a_pending_range_closes_on_the_second_click(mounted, rescan):
    """Le second clic FERME la plage — re-scan intercalé ou non.

    Le cas ``nominal`` n'est pas décoratif : il prouve que le cas
    ``rescan`` n'échouait pas pour une raison indépendante du re-scan.
    Sans lui, un probe rouge des deux côtés se lirait comme une
    régression du re-scan alors que le clic serait cassé tout court.
    """
    result = mounted.evaluate(_TWO_CLICKS, rescan)

    assert result["final"] == f'["{result["a"]}","{result["b"]}"]', (
        "le second clic devait fermer la plage ; "
        f"obtenu {result['final']!r} — un début SEUL signifie que "
        "l'attente a été perdue et qu'une nouvelle plage s'est ouverte"
    )


def test_the_pending_start_never_reaches_the_value_attribute(mounted):
    """L'attribut ``value`` ne porte QUE du commité.

    C'est l'invariant de fond, et il est plus fort que « le second clic
    marche » : tant qu'une paire à moitié ouverte peut atteindre
    l'attribut, le miroir a de nouveau quelque chose à écraser, et le bug
    revient par un autre chemin.
    """
    result = mounted.evaluate(_TWO_CLICKS, True)

    assert result["afterFirst"]["attr"] == "", (
        "le début en attente a fuité dans l'attribut : "
        f"{result['afterFirst']['attr']!r}"
    )
    assert result["afterFirst"]["selected"] == "true", (
        "l'attente doit rester VISIBLE — la sortir de l'attribut ne "
        "dispense pas de peindre la cellule de début"
    )
    assert result["afterRescan"]["attr"] == "", (
        "un re-scan ne doit rien changer à un attribut déjà vide"
    )

"""Une étape verrouillée TERNIT-elle, dans les deux modes ?

Le fix du 2026-08-13 fait passer la pastille de ``disabled:`` à
``aria-disabled:`` : la première variante ne matche que les contrôles de
formulaire, donc sur la pastille ``<span>`` du mode non cliquable elle ne
matchait jamais et ``disabled=True`` n'avait AUCUN effet visible.

Un test Python ne peut pas juger ça — il verrait la classe présente dans
les deux cas. Ce qui départage est l'``opacity`` calculée, et il faut un
navigateur pour l'obtenir.

Chaque mesure porte son **témoin** : l'étape voisine, active. Sans lui,
« opacity 0.5 » ne dit pas si c'est le verrou qui l'a produite ou le
style de base des étapes à venir.

⚠️ Ce fichier est né comme un ``probe_*`` et a été promu en test le jour
même. La raison est mesurée : la gate déterministe
``test_disabled_affordance`` ne peut vérifier que la PRÉSENCE de la
classe ``cursor-not-allowed``, jamais qu'elle s'applique — et c'est
précisément par là que le défaut était passé (``disabled:`` sur un
``<span>``, une variante qui ne matche aucun élément non-formulaire).
Laissé en probe, ce contrôle serait sorti de toute suite et aurait pourri
en silence, comme ses voisins (memory ``project_probes_rot_silently``).

Run : ``py -m pytest tests/runtime_js/test_step_disabled_paints.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

pytestmark = pytest.mark.browser


_BUILD = """
(clickable) => {
  document.querySelectorAll('.probe-step').forEach(n => n.remove());
  const box = document.createElement('div');
  box.className = 'probe-step';
  box.style.cssText =
    'position:fixed;top:0;left:0;z-index:99999;background:#fff;padding:8px';
  box.innerHTML = window.__markup[clickable ? 'on' : 'off'];
  document.body.appendChild(box);
  return true;
}
"""

_READ = """
() => {
  const box = document.querySelector('.probe-step');
  const bullets = [...box.querySelectorAll('[aria-disabled], span, button')]
    .filter(el => el.className && /rounded-full/.test(el.className));
  return bullets.slice(0, 4).map(el => ({
    tag: el.tagName,
    locked: el.getAttribute('aria-disabled') === 'true',
    opacity: getComputedStyle(el).opacity,
    cursor: getComputedStyle(el).cursor,
  }));
}
"""


def _markup() -> dict[str, str]:
    from bretzel import ui
    from bretzel.components.base.testing import render_isolated
    from bretzel.core.serialize import serialize

    out = {}
    for key, clickable in (("on", True), ("off", False)):
        with render_isolated():
            with ui.stepper(clickable=clickable) as stepper:
                ui.step("Active")
                ui.step("Locked", disabled=True)
            out[key] = serialize(stepper.render())
    return out


@pytest.fixture(scope="module")
def page():
    markup = _markup()
    with audit_server() as base_url:
        with browser_page(base_url, "/stepper") as p:
            p.wait_for_function("() => !!window.$bz")
            p.evaluate("(m) => { window.__markup = m; }", markup)
            yield p


@pytest.mark.parametrize("clickable", [True, False], ids=["clickable", "indicator"])
def test_a_locked_step_dims_against_its_neighbour(page, clickable) -> None:
    page.evaluate(_BUILD, clickable)
    page.wait_for_timeout(400)  # le JIT dev régénère sa feuille
    rows = page.evaluate(_READ)
    locked = [r for r in rows if r["locked"]]
    free = [r for r in rows if not r["locked"]]
    assert locked, "aucune pastille aria-disabled rendue"
    assert free, (
        "TÉMOIN absent : pas de pastille active à comparer, donc "
        "« la verrouillée est pâle » ne prouverait rien"
    )
    assert float(locked[0]["opacity"]) < float(free[0]["opacity"]), (
        f"la pastille verrouillée n'est pas plus pâle que l'active "
        f"({locked[0]['opacity']} vs {free[0]['opacity']}) — la variante "
        f"ne matche pas cet élément"
    )
    assert locked[0]["cursor"] == "not-allowed", (
        f"curseur {locked[0]['cursor']!r} sur une étape verrouillée"
    )


def test_an_indicator_bullet_does_not_mimic_a_control(page) -> None:
    """``not-disabled:`` est une négation GÉNÉRIQUE en Tailwind v4
    (``&:not(:disabled)``), pas ``&:enabled`` — elle matchait donc le
    ``<span>`` d'un stepper indicateur, qui rendait ``cursor: pointer``
    sans que rien ne soit cliquable. C'est ``enabled:`` qu'il faut."""
    page.evaluate(_BUILD, False)
    page.wait_for_timeout(400)
    rows = page.evaluate(_READ)
    liars = [r for r in rows if not r["locked"] and r["cursor"] == "pointer"]
    assert not liars, (
        f"{len(liars)} pastille(s) d'un stepper NON cliquable rendent "
        f"`cursor: pointer` — elles annoncent une interaction qui n'existe "
        f"pas"
    )

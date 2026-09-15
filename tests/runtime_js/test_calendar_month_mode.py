"""Le mode ``month`` du ``<bz-calendar>`` — la grille d'ANNÉE.

C'est le **second type de grille** du composant, et le seul endroit où il
ne rend pas des jours. Le SSR n'émet qu'un conteneur vide : les douze
cellules, leur sélection et leur bornage n'existent qu'à l'exécution.

Trois invariants, chacun cassant en silence :

1. **Douze cellules, aucune cellule de jour.** Le retour anticipé de
   ``_render`` est ce qui l'assure ; s'il tombait, on obtiendrait les
   deux grilles empilées — et la page resterait « à peu près correcte »,
   donc relue sans alerte.
2. **Le bornage se compare en ``"YYYY-MM"``**, jamais en dates. Un
   ``min`` au 15 mars ne doit PAS interdire mars : une partie du mois
   reste permise. Comparer des dates complètes le grillerait, et
   personne ne clique un mois grisé pour vérifier pourquoi.
3. **Le clic écrit ``"YYYY-MM"``**, pas une date. C'est le contrat de
   valeur du mode, et il traverse une form data.

Tourne sur ``about:blank`` + le runtime injecté, PAS sur une page de
playground : cf. traps.md § « tester un custom element SUR une page de
playground ».

    py -m pytest tests/runtime_js/test_calendar_month_mode.py -q -m browser
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.audit.harness import audit_server, browser_page

_RUNTIME = (
    Path(__file__).resolve().parents[2]
    / "bretzel" / "runtime" / "runtime.js"
)

_MAKE = """
(opts) => {
  const o = opts || {};
  const box = document.createElement('div');
  box.addEventListener('change', e => e.stopPropagation());
  document.body.appendChild(box);
  const cal = document.createElement('bz-calendar');
  cal.setAttribute('mode', 'month');
  if (o.value) cal.setAttribute('value', o.value);
  if (o.min) cal.setAttribute('min', o.min);
  if (o.max) cal.setAttribute('max', o.max);
  if (o.month) cal.setAttribute('month', o.month);
  box.appendChild(cal);
  return cal;
}
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    with browser_page(base_url, "/calendar") as p:
        p.goto("about:blank")
        p.add_script_tag(content=_RUNTIME.read_text(encoding="utf-8"))
        p.wait_for_function(
            "() => !!customElements.get('bz-calendar')", timeout=5000
        )
        yield p


def test_twelve_cells_and_no_day_grid(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const cal = make({{value: '2026-08'}});
            const out = {{
                months: cal.querySelectorAll('[data-month-cell]').length,
                days: cal.querySelectorAll('[data-day-cell]').length,
                weekdays: cal.querySelectorAll('[data-bz-cal-weekdays]').length,
            }};
            cal.remove();
            return out;
        }}"""
    )
    assert r["months"] == 12, f"douze mois attendus, {r['months']} rendus"
    assert r["days"] == 0, (
        f"{r['days']} cellules de JOUR rendues — les deux grilles "
        f"coexistent, donc le retour anticipé de _render est tombé"
    )
    assert r["weekdays"] == 0


def test_the_selected_month_is_the_only_one_marked(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const cal = make({{value: '2026-08', month: '2026-01-01'}});
            const sel = [...cal.querySelectorAll('[data-month-cell]')]
              .filter(c => c.getAttribute('data-selected') === 'true')
              .map(c => c.getAttribute('data-value'));
            cal.remove();
            return sel;
        }}"""
    )
    assert r == ["2026-08"], f"sélection : {r}"


def test_clicking_writes_a_year_month_string(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const cal = make({{month: '2026-01-01'}});
            cal.querySelectorAll('[data-month-cell]')[10].click();
            const out = cal.getAttribute('value');
            cal.remove();
            return out;
        }}"""
    )
    assert r == "2026-11", f"le clic doit écrire « YYYY-MM », got {r!r}"


def test_bounds_are_compared_at_month_granularity(page) -> None:
    # ``min`` au 15 mars : mars reste CLIQUABLE, parce qu'une partie du
    # mois est permise. Comparer des dates complètes le grillerait.
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const cal = make({{month: '2026-01-01',
                              min: '2026-03-15', max: '2026-09-30'}});
            const open = [...cal.querySelectorAll('[data-month-cell]')]
              .filter(c => c.getAttribute('aria-disabled') === 'false')
              .map(c => c.getAttribute('data-value'));
            cal.remove();
            return open;
        }}"""
    )
    assert r == [f"2026-{m:02d}" for m in range(3, 10)], (
        f"mars..septembre attendus (mars inclus malgré min au 15) : {r}"
    )


def test_no_bounds_opens_every_month(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const cal = make({{month: '2026-01-01'}});
            const n = [...cal.querySelectorAll('[data-month-cell]')]
              .filter(c => c.getAttribute('aria-disabled') === 'true').length;
            cal.remove();
            return n;
        }}"""
    )
    assert r == 0, f"{r} mois grisés sans bornes"


def test_a_day_value_does_not_mark_anything(page) -> None:
    # Le mode attend « YYYY-MM ». Recevoir une date complète ne doit RIEN
    # sélectionner plutôt que de deviner — c'est Python qui tronque, et
    # ce test garde la frontière.
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const cal = make({{value: '2026-08-14', month: '2026-01-01'}});
            const n = [...cal.querySelectorAll('[data-month-cell]')]
              .filter(c => c.getAttribute('data-selected') === 'true').length;
            cal.remove();
            return n;
        }}"""
    )
    assert r == 0, f"une date complète ne doit marquer aucun mois : {r}"

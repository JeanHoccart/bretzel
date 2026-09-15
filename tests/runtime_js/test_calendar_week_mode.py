"""Le mode ``week`` du ``<bz-calendar>`` — le recalage, dans un vrai
moteur JS.

Ce que ce probe protège n'existe **qu'à l'exécution** : le HTML rendu ne
contient qu'un ``mode="week"`` et une grille de jours. Toute la règle du
mode — *cliquer n'importe quel jour choisit sa semaine, et ce qui sort
est le PREMIER jour de cette semaine* — vit dans le custom element.

Trois invariants, chacun cassant en silence :

1. **Le recalage est idempotent.** Deux clics dans la même semaine
   doivent produire la MÊME valeur. Sans recalage on rendrait le jour
   cliqué, et « la semaine du 5 » vaudrait tantôt le 3, tantôt le 5 —
   deux lignes de base de données pour une seule semaine.
2. **``weekstart`` est respecté.** La même date appartient à deux
   semaines différentes selon qu'on démarre lundi ou dimanche. Se
   tromper décale toute l'application d'un jour, ce qui ne se voit qu'aux
   bords de mois.
3. **Le modulo doit être doublé.** ``(d.getDay() - weekstart + 7) % 7``
   sans le ``+ 7`` rend un reste NÉGATIF dès que le jour cliqué tombe
   avant ``weekstart`` — et la sélection remonte d'une semaine entière.
   C'est le seul bug de ce fichier qu'un humain ne verrait pas en
   relisant.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_calendar_week_mode.py -q -m browser
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.audit.harness import audit_server, browser_page

#: Un ``<bz-calendar mode="week">`` monté à la volée, dans une boîte qui
#: AVALE ses events.
#:
#: ⚠️ Le ``stopPropagation`` n'est pas une précaution de style : le
#: calendrier dispatche un ``change`` bullant sur son input caché, et la
#: page hôte (``/calendar``, un vrai playground) a du HTMX à l'écoute.
#: Sans la boîte, le premier clic déclenchait une requête et Playwright
#: mourait sur « Execution context was destroyed, most likely because of
#: a navigation » — un message qui accuse la navigation et ne dit rien du
#: clic qui l'a causée. Les tests échouaient alors par ORDRE d'exécution,
#: pas par cas : de quoi croire à un bug du composant.
_MAKE = """
(weekstart, value) => {
  const box = document.createElement('div');
  box.addEventListener('change', e => e.stopPropagation());
  document.body.appendChild(box);
  const cal = document.createElement('bz-calendar');
  cal.setAttribute('mode', 'week');
  cal.setAttribute('weekstart', String(weekstart));
  if (value) cal.setAttribute('value', value);
  box.appendChild(cal);
  return cal;
}
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


_RUNTIME = (
    Path(__file__).resolve().parents[2]
    / "bretzel" / "runtime" / "runtime.js"
)


@pytest.fixture(scope="module")
def page(base_url: str):
    """Une page VIDE avec le runtime injecté — pas une page du playground.

    Ces tests ne portent que sur le custom element : ils n'ont besoin de
    rien d'autre que sa définition. Les faire tourner sur ``/calendar``
    coûtait deux jours de faux signaux et ne prouvait rien de plus.

    Ce qui s'y passait, dans l'ordre où je l'ai compris : les
    ``page.evaluate`` mouraient sur « Execution context was destroyed,
    most likely because of a navigation ». Le message accuse une
    navigation — il n'y en a aucune, vérifié en écoutant
    ``htmx:beforeRequest`` / ``submit`` / ``beforeunload`` autour d'un
    clic, qui ne produit qu'un ``change``. Et l'échec se DÉPLAÇAIT d'un
    cas à l'autre entre deux exécutions, ce qui ressemble à un bug du
    composant alors que c'est la signature d'une course avec le chargement
    du playground. Ni une page par test ni ``networkidle`` ne l'ont
    fermée.

    La page vide la ferme par construction : plus de HTMX, plus de
    refreshables, plus rien qui puisse bouger sous les pieds du test. Le
    serveur reste utilisé — il sert le runtime — mais la page ne lui doit
    plus rien après le chargement.
    """
    with browser_page(base_url, "/calendar") as p:
        p.goto("about:blank")
        p.add_script_tag(content=_RUNTIME.read_text(encoding="utf-8"))
        p.wait_for_function(
            "() => !!customElements.get('bz-calendar')", timeout=5000
        )
        yield p


@pytest.mark.parametrize(
    "clicked,weekstart,expected",
    [
        # Août 2026 : le 3 est un lundi, le 9 un dimanche.
        ("2026-08-03", 1, "2026-08-03"),   # le lundi lui-même
        ("2026-08-05", 1, "2026-08-03"),   # mercredi → son lundi
        ("2026-08-09", 1, "2026-08-03"),   # dimanche → le MÊME lundi
        # Semaine démarrant le dimanche : le 9 ouvre sa propre semaine.
        ("2026-08-05", 0, "2026-08-02"),
        ("2026-08-09", 0, "2026-08-09"),
        # Le cas du modulo négatif : samedi avec weekstart=1 est le jour
        # le plus éloigné en arrière (6 jours). Un modulo non doublé
        # remonterait d'une semaine de plus.
        ("2026-08-08", 1, "2026-08-03"),
        # Traversée de fin de mois — l'arithmétique passe par Date(),
        # jamais par la chaîne.
        ("2026-09-01", 1, "2026-08-31"),
        ("2027-01-01", 1, "2026-12-28"),
    ],
)
def test_click_snaps_to_the_week_start(
    page, clicked, weekstart, expected
) -> None:
    got = page.evaluate(
        f"""async ([clicked, ws]) => {{
            const make = {_MAKE};
            const cal = make(ws, null);
            // La grille montre le mois courant ; naviguer vers la date
            // visée. ``setAttribute('month')`` planifie le rendu en
            // MICROTÂCHE (cf. ``_dispatchMonthChange``), donc interroger
            // le DOM tout de suite ne trouve rien — il faut céder la main
            // une fois. Ce n'était pas une subtilité du mode week mais du
            // custom element, et c'est mon probe qui l'ignorait.
            cal.setAttribute('month', clicked);
            await new Promise(r => setTimeout(r, 0));
            const target = cal.querySelector('[data-date="' + clicked + '"]');
            if (!target) return 'CELLULE ABSENTE';
            target.click();
            const out = cal.getAttribute('value');
            cal.remove();
            return out;
        }}""",
        [clicked, weekstart],
    )
    assert got == expected, (
        f"clic sur {clicked} (weekstart={weekstart}) → {got!r}, "
        f"attendu {expected!r}"
    )


def test_snapping_is_idempotent(page) -> None:
    # Deux jours de la MÊME semaine doivent donner la même valeur —
    # sinon « la semaine du 5 » vaut tantôt le 3, tantôt le 5.
    r = page.evaluate(
        f"""async () => {{
            const make = {_MAKE};
            const out = [];
            for (const day of ['2026-08-03', '2026-08-05', '2026-08-09']) {{
                const cal = make(1, null);
                cal.setAttribute('month', day);
                await new Promise(r => setTimeout(r, 0));
                cal.querySelector('[data-date="' + day + '"]').click();
                out.push(cal.getAttribute('value'));
                cal.remove();
            }}
            return out;
        }}"""
    )
    assert len(set(r)) == 1, (
        f"trois jours de la même semaine ont donné {r} — le recalage "
        f"n'est pas idempotent"
    )


def test_the_whole_row_is_banded(page) -> None:
    # Une semaine EST une plage fermée de 7 jours : elle réutilise le
    # vocabulaire de bande du mode range plutôt qu'un second langage
    # visuel pour la même idée.
    r = page.evaluate(
        f"""async () => {{
            const make = {_MAKE};
            const cal = make(1, '2026-08-03');
            cal.setAttribute('month', '2026-08-03');
            await new Promise(r => setTimeout(r, 0));
            const band = [...cal.querySelectorAll('[data-day-cell]')]
              .filter(c => c.getAttribute('data-selected') === 'true'
                        || c.getAttribute('data-in-range') === 'true')
              .map(c => c.getAttribute('data-date'));
            const ends = [...cal.querySelectorAll('[data-day-cell]')]
              .filter(c => c.getAttribute('data-range-start') === 'true'
                        || c.getAttribute('data-range-end') === 'true')
              .map(c => c.getAttribute('data-date'));
            cal.remove();
            return {{band: band.sort(), ends: ends.sort()}};
        }}"""
    )
    assert len(r["band"]) == 7, (
        f"la bande doit couvrir les 7 jours, pas {len(r['band'])} : "
        f"{r['band']}"
    )
    assert r["band"][0] == "2026-08-03"
    assert r["band"][-1] == "2026-08-09"
    assert r["ends"] == ["2026-08-03", "2026-08-09"], (
        f"les deux extrémités portent le marqueur de bord : {r['ends']}"
    )


def test_an_empty_value_bands_nothing(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const cal = make(1, null);
            const n = [...cal.querySelectorAll('[data-day-cell]')]
              .filter(c => c.getAttribute('data-in-range') === 'true').length;
            cal.remove();
            return n;
        }}"""
    )
    assert r == 0, f"sans valeur, aucune cellule ne doit être bandée : {r}"

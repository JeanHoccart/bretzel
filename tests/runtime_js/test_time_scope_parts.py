"""Le scope partagé du TimePicker — découpe et écriture, dans un vrai
moteur JS.

Ce que ce probe protège est **invisible au SSR** : le HTML ne contient
que ``pick(0, '09')`` et ``_is(1, '30')``, des appels dont le résultat
n'existe qu'à l'exécution. Trois invariants s'y jouent, et chacun casse
en silence :

1. **La découpe tolère ce que le champ accepte.** Le champ est un
   ``<input type=text>`` : l'utilisateur peut y taper `9:30` avant que la
   normalisation au blur ne le repasse en `09:30`. Entre les deux, le
   panneau doit quand même surligner la bonne heure. Une regex trop
   stricte n'y arriverait pas, et personne ne le verrait — le panneau
   serait juste « parfois sans sélection ».
2. **Choisir une partie ne détruit pas l'autre.** Cliquer une heure quand
   la minute est déjà posée doit garder la minute. C'est le bug évident à
   écrire et invisible à relire.
3. **Une partie choisie seule vaut ``:00``**, pas une valeur vide. Sans
   ça, le premier clic ne changerait rien à l'écran et l'utilisateur
   croirait que le panneau est mort.

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_time_scope_parts.py -q -m browser
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

#: Un scope monté à la main, comme le composant le fait : l'indirection
#: ``_read`` / ``_write`` sur un simple champ d'objet.
_MAKE = """
(start, closeOnPick) => Object.assign(Object.create($bz.time.scope), {
  v: start === undefined ? "" : start,
  open: true,
  _closeOnPick: !!closeOnPick,
  _read() { return this.v; },
  _write(x) { this.v = x; },
})
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    with browser_page(base_url, "/time_picker") as p:
        p.wait_for_function("() => !!(window.$bz && $bz.time)", timeout=5000)
        yield p


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("09:30", ["09", "30"]),
        # Le champ est un input texte : « 9:30 » existe entre la frappe
        # et la normalisation au blur. Le panneau doit surligner quand
        # même.
        ("9:30", ["09", "30"]),
        ("23:59", ["23", "59"]),
        ("00:00", ["00", "00"]),
        # Rien d'exploitable → aucune sélection, jamais une exception.
        ("", ["", ""]),
        ("nawak", ["", ""]),
        ("9h30", ["", ""]),
    ],
)
def test_parts_tolerates_what_the_field_accepts(page, raw, expected) -> None:
    r = page.evaluate(
        f"""(raw) => {{
            const make = {_MAKE};
            return make(raw)._parts();
        }}""",
        raw,
    )
    assert r == expected, f"_parts({raw!r}) = {r}, attendu {expected}"


def test_picking_one_part_keeps_the_other(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const out = {{}};
            const a = make("09:30"); a._pick(0, "14"); out.hour = a.v;
            const b = make("09:30"); b._pick(1, "45"); out.minute = b.v;
            return out;
        }}"""
    )
    assert r["hour"] == "14:30", (
        f"choisir une heure doit garder la minute : {r['hour']}"
    )
    assert r["minute"] == "09:45", (
        f"choisir une minute doit garder l'heure : {r['minute']}"
    )


def test_a_lone_part_completes_with_zero(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const a = make(""); a._pick(0, "14"); const hour = a.v;
            const b = make(""); b._pick(1, "45"); const minute = b.v;
            return {{hour, minute}};
        }}"""
    )
    assert r["hour"] == "14:00", (
        "une heure choisie seule vaut :00 — sinon le premier clic ne "
        f"changerait rien à l'écran : {r['hour']!r}"
    )
    assert r["minute"] == "00:45", f"{r['minute']!r}"


def test_is_marks_exactly_the_selected_cells(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const s = make("09:30");
            return {{
                hour_hit:  s._is(0, "09"), hour_miss:  s._is(0, "10"),
                min_hit:   s._is(1, "30"), min_miss:   s._is(1, "45"),
                // Le piège croisé : la même chaîne dans l'autre colonne.
                cross:     s._is(1, "09"),
            }};
        }}"""
    )
    assert r == {
        "hour_hit": True, "hour_miss": False,
        "min_hit": True, "min_miss": False, "cross": False,
    }, f"sélection mal attribuée : {r}"


def test_close_on_pick_fires_on_the_minute_only(page) -> None:
    # L'ordre de lecture est heure puis minute : refermer à l'heure
    # couperait la main de l'utilisateur au milieu de son geste.
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE};
            const a = make("09:30", true);  a.pick(0, "14");
            const b = make("09:30", true);  b.pick(1, "45");
            const c = make("09:30", false); c.pick(1, "45");
            return {{after_hour: a.open, after_minute: b.open,
                     disabled: c.open}};
        }}"""
    )
    assert r["after_hour"] is True, (
        "cliquer une HEURE ne doit pas refermer — la minute reste à "
        "choisir"
    )
    assert r["after_minute"] is False, "cliquer une MINUTE referme"
    assert r["disabled"] is True, "close_on_pick=False ne referme jamais"

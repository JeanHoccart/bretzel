"""Le scope partagé du Stepper — statut dérivé et bornes, dans un vrai
moteur JS.

Ce que ce probe protège est **invisible au SSR** et à `node --check` :
le HTML rendu ne contient que `_status(2)` et `next()`, des appels dont
le RÉSULTAT n'existe qu'à l'exécution. Deux invariants s'y jouent, et
tous deux se cassent en silence :

1. **Le statut est dérivé, pas déclaré.** Toute la mécanique du composant
   (la pastille remplie, le check qui remplace le numéro, le connecteur
   teinté, le panneau visible) dépend d'une seule fonction de trois
   lignes. Une comparaison qui basculerait de `<` à `<=` déplacerait
   toute la frise d'un cran sans qu'aucun test Python ne bronche.
2. **Les bornes de `next()` / `prev()`.** `_max` vaut
   `max(len(steps), len(panels)) - 1` — donc un panneau de plus que
   d'étapes rend l'écran « terminé » atteignable. C'est la seule raison
   d'être de ce calcul, et rien côté serveur ne peut vérifier qu'il est
   respecté : le serveur émet un nombre, c'est le runtime qui décide de
   s'arrêter dessus.

S'y ajoute la **coercition** : la valeur revient d'une form data en
CHAÎNE (l'input caché la sérialise), et `"1" === 1` est faux en JS. Un
`Number()` oublié ferait qu'un stepper marche à la souris et meurt après
un aller-retour serveur — le genre de bug qui ne se voit qu'en
production.

Le probe exerce le scope DIRECTEMENT, sans dépendre de la structure
d'une page (même forme que ``test_shared_scope_factories``).

Lourd (uvicorn + Chromium) — à lancer explicitement ::

    py -m pytest tests/runtime_js/test_stepper_scope_bounds.py -q
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

#: Un scope de stepper monté à la main : le composant y injecte
#: ``_read`` / ``_write`` (champ local OU cellule de store) et ``_max``.
#: Ici un simple champ d'objet fait l'affaire — c'est justement ce que
#: l'indirection rend possible.
_MAKE_SCOPE = """
(start, max_) => Object.assign(Object.create($bz.stepper.scope), {
  v: start,
  _read() { return this.v; },
  _write(x) { this.v = x; },
  _max: max_,
})
"""


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


@pytest.fixture(scope="module")
def page(base_url: str):
    with browser_page(base_url, "/stepper") as p:
        p.wait_for_function("() => !!(window.$bz && $bz.stepper)", timeout=5000)
        yield p


def test_status_is_derived_from_the_index(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE_SCOPE};
            const s = make(1, 2);
            return [s._status(0), s._status(1), s._status(2)];
        }}"""
    )
    assert r == ["done", "current", "upcoming"], (
        "la dérivation du statut a bougé — toute la frise (pastille "
        f"remplie, check, connecteur, panneau) suit cette fonction : {r}"
    )


def test_status_survives_a_string_index(page) -> None:
    # La valeur revient d'une form data en chaîne : « "1" === 1 » est faux.
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE_SCOPE};
            const s = make("1", 2);
            return [s._status(0), s._status(1), s._status(2)];
        }}"""
    )
    assert r == ["done", "current", "upcoming"], (
        f"un index reçu en CHAÎNE doit se comporter comme l'entier : {r}"
    )


def test_next_stops_at_the_upper_bound(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE_SCOPE};
            const s = make(0, 2);
            const seen = [];
            for (let i = 0; i < 5; i++) {{ s.next(); seen.push(s.v); }}
            return seen;
        }}"""
    )
    assert r == [1, 2, 2, 2, 2], (
        f"next() doit avancer puis se figer sur _max, pas déborder : {r}"
    )


def test_prev_stops_at_zero(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE_SCOPE};
            const s = make(2, 2);
            const seen = [];
            for (let i = 0; i < 4; i++) {{ s.prev(); seen.push(s.v); }}
            return seen;
        }}"""
    )
    assert r == [1, 0, 0, 0], (
        f"prev() ne doit jamais passer sous 0 : {r}"
    )


def test_the_extra_panel_is_reachable(page) -> None:
    # 3 étapes + 4 panneaux → _max = 3 : le dernier next() atteint
    # l'écran « terminé », qui n'a pas d'étape en face de lui. C'est la
    # SEULE raison d'être de max(len(steps), len(panels)) - 1.
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE_SCOPE};
            const s = make(2, 3);
            s.next();
            const at_done = s.v;
            s.next();
            return {{at_done, saturated: s.v, statuses:
                [s._status(0), s._status(1), s._status(2)]}};
        }}"""
    )
    assert r["at_done"] == 3, (
        "avec un panneau de plus que d'étapes, next() doit atteindre "
        f"l'écran terminé : {r['at_done']}"
    )
    assert r["saturated"] == 3
    assert r["statuses"] == ["done", "done", "done"], (
        f"sur l'écran terminé, toutes les étapes sont franchies : {r}"
    )


def test_goto_ignores_a_no_op_move(page) -> None:
    r = page.evaluate(
        f"""() => {{
            const make = {_MAKE_SCOPE};
            const s = make(1, 3);
            let writes = 0;
            s._write = function (x) {{ writes++; this.v = x; }};
            s.goTo(1);        // même valeur -> aucune écriture
            const after_same = writes;
            s.goTo("2");      // chaîne -> coercition, puis écriture
            return {{after_same, writes, value: s.v}};
        }}"""
    )
    assert r["after_same"] == 0, (
        "goTo(valeur courante) ne doit rien écrire — sans cette garde, "
        "chaque clic re-notifie et l'input caché re-dispatche un change "
        f"fantôme : {r}"
    )
    assert r["writes"] == 1
    assert r["value"] == 2, (
        f'goTo("2") doit écrire l\'ENTIER 2, pas la chaîne : {r["value"]!r}'
    )

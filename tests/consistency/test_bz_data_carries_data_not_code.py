"""Un ``bz-data`` porte de l'ÉTAT, pas un algorithme.

Le scope client d'une instance doit contenir ses données et, au plus, une
indirection courte (``_read`` / ``_write``) qui branche les méthodes
partagées sur le bon état. L'algorithme, lui, vit une seule fois dans un
slab du runtime — ``$bz.<composant>.scope``.

Pourquoi c'est un invariant et pas une préférence
--------------------------------------------------
Quand un builder sérialise des corps de méthode, la configuration finit
**cuite dans le code** :

    totalPages() { return Math.max(1, +(10) || 1); }   ← Pagination
    toggle(v) { … if (true) { … } }                    ← Accordion, collapsible

Deux instances de configurations différentes produisent alors deux CODES
différents, pas deux états différents. C'est ce qui rend la factorisation
impossible — et c'est le VRAI diagnostic, pas « c'est trop gros ».

La bascule est donc « config en données ». Poids mesurés avant/après :

===============  ==========  =========
composant        avant       après
===============  ==========  =========
Pagination       957 o       142 o
Accordion        622 o       137 o
Tree             293 o       158 o
===============  ==========  =========

⚠️ Ce que cette gate NE dit pas
--------------------------------
Elle interdit les **algorithmes** dans le scope, pas toute méthode : une
indirection d'une ligne (``_read() { return this.x; }``) est le mécanisme
qui permet aux méthodes partagées de servir les deux modes de valeur
(champ local ou cellule du store). C'est la longueur du corps qui
discrimine, pas sa présence.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import bz_data_of, public_component_classes

# Un corps de méthode qui dépasse ce seuil n'est plus une indirection,
# c'est de la logique. Mesuré : les indirections réelles font 20-45
# caractères (``_read() { return this.active; }`` = 31) ; les algorithmes
# retirés en faisaient 300 à 900.
_BODY_BUDGET = 90

_METHOD = re.compile(r"\b(\w+)\s*\([^)]*\)\s*\{")

_CLASSES = public_component_classes()


#: Promu dans ``_discovery`` : cette gate et
#: ``test_measured_deps_are_declared`` en veulent la même lecture, et la
#: version locale se re-rendait 2-3× par composant (une fois pour le
#: plancher, une fois par cas paramétré). Le cache de ``_discovery`` rend
#: cette passe une seule fois pour les deux.
_bz_data = bz_data_of


def _long_bodies(data: str) -> list[tuple[str, int]]:
    """Les méthodes du scope dont le corps dépasse le budget."""
    out: list[tuple[str, int]] = []
    for m in _METHOD.finditer(data):
        start = m.end() - 1
        depth, i = 0, start
        while i < len(data):
            if data[i] == "{":
                depth += 1
            elif data[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        body = data[start : i + 1]
        if len(body) > _BODY_BUDGET:
            out.append((m.group(1), len(body)))
    return out


def test_the_gate_has_a_population() -> None:
    """Plancher de non-vacuité — sans lui, un rendu cassé rendrait la
    gate verte sur zéro scope inspecté."""
    scopes = [c for c in _CLASSES if _bz_data(c)]
    assert len(scopes) >= 15, (
        f"seulement {len(scopes)} composants émettent un `bz-data` "
        f"(28 mesurés le 2026-07-29) — la construction a régressé."
    )


@pytest.mark.parametrize("cls", _CLASSES, ids=lambda c: c.__name__)
def test_bz_data_holds_no_algorithm(cls: type) -> None:
    data = _bz_data(cls)
    if data is None:
        pytest.skip("pas de bz-data / non constructible nu")

    offenders = _long_bodies(data)
    assert not offenders, (
        f"{cls.__name__} sérialise de la LOGIQUE dans son `bz-data` : "
        + ", ".join(f"{n}() {ln} car." for n, ln in offenders)
        + f" (budget {_BODY_BUDGET}).\n"
        f"  Sors l'algorithme dans un slab `bretzel/runtime/_src/` exposé "
        f"en `$bz.<nom>.scope`, et n'émets ici que l'état + la config EN "
        f"DONNÉES.\n"
        f"  Le vrai coût n'est pas la taille : une config cuite dans un "
        f"corps de méthode (`+(10)`, `if (true)`) fait que deux instances "
        f"de configs différentes produisent deux CODES différents — c'est "
        f"ça qui rend la factorisation impossible.\n"
        f"  Une indirection courte (`_read() {{ return this.x; }}`) reste "
        f"permise : c'est elle qui laisse les méthodes partagées servir "
        f"le mode local ET le mode binding."
    )


# ── Le littéral Python qui fuit dans le JS ────────────────────────────
_PY_LITERAL = re.compile(r'(^|[^\w."])(True|False|None)([^\w"]|$)')


@pytest.mark.parametrize("cls", _CLASSES, ids=lambda c: c.__name__)
def test_bz_data_holds_no_python_literal(cls: type) -> None:
    """``True`` / ``False`` / ``None`` sont du Python, pas du JavaScript.

    Trouvé au navigateur le 2026-07-29 : ``ui.tooltip(enabled=state.enabled)``
    émettait ``_enabled: True``, d'où un ``ReferenceError: True is not
    defined`` au premier survol — l'effet mourait.

    La cause vaut d'être retenue : une valeur **backée serveur** n'est pas
    un ``bool`` au sens d'``isinstance``. ``ServerState`` la tamponne en
    ``_BoundBool``, sous-classe d'``int`` portant son ``field_name``. Un
    ``if isinstance(v, bool)`` la rate donc, et le ``str()`` de repli écrit
    le littéral Python.

    ⚠️ Les 9 400 tests Python étaient verts. Seul un vrai navigateur
    pouvait voir ce bug — et c'est l'argument de cette gate : elle porte
    au niveau déterministe ce qui n'était visible qu'à l'exécution.
    """
    data = _bz_data(cls)
    if data is None:
        pytest.skip("pas de bz-data / non constructible nu")

    hits = [m.group(2) for m in _PY_LITERAL.finditer(data)]
    assert not hits, (
        f"{cls.__name__} émet le littéral PYTHON {sorted(set(hits))} dans "
        f"son `bz-data` :\n    {data[:160]}\n"
        f"  En JS, `True` est un identifiant non défini — l'effet lève au "
        f"premier accès.\n"
        f"  Cause habituelle : une valeur backée serveur n'est PAS un "
        f"`bool` (`ServerState` la tamponne en `_BoundBool`, sous-classe "
        f"d'`int`), donc un `isinstance(v, bool)` la rate et le `str()` de "
        f"repli écrit du Python. Convertis explicitement : "
        f"`\"true\" if v else \"false\"`."
    )

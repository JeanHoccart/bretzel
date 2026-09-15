"""Gate : `RESERVED_KWARGS` colle aux `kwargs.pop` qui la réalisent.

``Component.RESERVED_KWARGS`` déclare les kwargs que tout composant
absorbe. La déclaration ne peut pas *faire* le travail : les onze ``pop``
sont hétérogènes (chacun fait quelque chose de différent de sa valeur —
coercition de binding, capture de slot, choix de tag), donc on ne peut pas
boucler dessus. Mais on peut refuser qu'ils divergent.

**Pourquoi ça valait une gate.** La liste a existé en **cinq**
exemplaires jusqu'au 2026-08-16 — les ``pop``, la prose de
``split_kwargs``, deux gates de ``tests/consistency/`` et
``bretzel.introspect`` — et deux avaient déjà dérivé : l'une avait perdu
``key``, l'autre a gagné ``slots`` un an trop tard, **après avoir fait
rougir du code correct** (un ``ui.sidebar(slots={"root": …})`` vivant).
Les copies sont regroupées ; celle-ci garde la source.
"""

from __future__ import annotations

import ast
from functools import cache

from bretzel.components.base.component import RESERVED_KWARGS
from tests.consistency._discovery import REPO_ROOT

#: Preuve de morsure : controle POSITIF — le balayage trouve encore des kwargs reserves
#: reellement consommes par le socle ; une comparaison avec un ensemble
#: vide serait verte des deux cotes.
MUTATION_PROOF = "test_the_scan_is_not_vacuous"

_COMPONENT_PY = REPO_ROOT / "bretzel" / "components" / "base" / "component.py"


@cache
def _popped_in_component_init() -> frozenset[str]:
    """Les littéraux de ``kwargs.pop("X"…)`` du socle.

    Mis en cache : le fichier fait ~132 Ko / 2 685 lignes et son
    ``ast.parse`` coûte ~43 ms — les deux tests d'ici le demandaient deux
    fois. Lu en ``utf-8-sig`` : un BOM avait déjà sorti un fichier de sept
    gates dans ce dépôt, et celle-ci n'en lit qu'un seul.

    Le garde ``ast.Constant`` écarte au passage le seul ``pop`` dynamique
    du socle (``kwargs.pop(ev_key)``, qui retire un handler d'event) — il
    n'a pas à figurer dans une liste de kwargs universels.
    """
    tree = ast.parse(_COMPONENT_PY.read_text(encoding="utf-8-sig"))
    return frozenset(
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "pop"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "kwargs"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    )


def test_the_scan_is_not_vacuous() -> None:
    """Le balayage AST trouve encore des ``kwargs.pop`` — sinon la gate
    comparerait deux ensembles vides et resterait verte avec le socle
    entièrement réécrit."""
    assert _COMPONENT_PY.exists(), f"{_COMPONENT_PY} introuvable"
    assert len(_popped_in_component_init()) >= 8, (
        f"le balayage ne voit plus que {sorted(_popped_in_component_init())} "
        f"dans {_COMPONENT_PY.name} — vérifie le chemin et la forme avant de "
        "croire que la gate passe."
    )


def test_reserved_kwargs_match_the_socle() -> None:
    socle = _popped_in_component_init()
    declared = set(RESERVED_KWARGS)

    missing = sorted(socle - declared)
    extra = sorted(declared - socle)
    assert not missing and not extra, (
        "`Component.RESERVED_KWARGS` a dérivé des `kwargs.pop` qui la "
        "réalisent.\n"
        f"  popé par le socle mais pas déclaré : {missing}\n"
        f"  déclaré mais plus popé            : {extra}\n"
        "Les `pop` sont la réalité — corrige la déclaration, ou le `pop` si "
        "c'est lui qui a disparu par erreur."
    )

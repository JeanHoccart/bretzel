"""Gate : la suite e2e boote ses PROPRES apps, jamais une démo.

Le défaut qu'elle ferme
-----------------------
``examples/`` est de la **documentation**. Une démo doit rester libre de
changer pour des raisons de démo — renommer un bouton, réordonner une
colonne, retirer une ligne devenue redondante. Quand un test du framework
la pilote, ce mouvement casse un test qui ne parle pas d'elle, et le
signal est trompeur dans les deux sens : ou bien on croit le framework
cassé, ou bien on renonce à améliorer la démo.

Ce n'était pas théorique. Au 2026-08-16, ``tests/e2e/`` portait **deux
conventions contradictoires** :

- ``test_todo`` avait son app dédiée ``apps/todo_app.py``, migrée exprès
  le 2026-07-14 pour sortir de ``examples/todo`` ;
- ``test_counter`` bootait ``examples/counter``, et ``test_dropdown_action``
  ``examples/kanban`` — ce dernier **écrit le jour même de cette
  migration**, contre un exemple.

Le bon motif avait donc été inventé, puis pas appliqué. Et les deux cibles
empruntées bougeaient : 7 commits pour ``examples/counter``, 4 pour
``examples/kanban``, **les deux touchés le 2026-08-16**.

Les trois fixtures bootent désormais depuis ``tests/e2e/apps/``. Cette
gate existe pour que la convention ne redevienne pas à moitié appliquée —
c'est le mode de dérive observé ici, pas un risque imaginé.

Portée honnête
--------------
1. On interdit l'**import** d'``examples`` depuis ``tests/e2e/``. Un test
   qui atteindrait une démo autrement — une URL en dur vers un port de
   démo, un ``subprocess`` qui lance ``py -m examples.…`` — passerait. La
   forme interdite est celle qui existait, et c'est la seule qu'on sache
   nommer sans deviner.
2. Rien n'oblige une app de ``apps/`` à être **utilisée**. Une fixture
   orpheline reste verte ici ; c'est ``test_fixture_apps_import`` qui
   garde qu'elles se chargent.
3. Les autres suites ne sont PAS concernées. ``tests/unit`` et
   ``tests/consistency`` lisent ``examples/`` **exprès** — pour vérifier
   que les démos utilisent la vraie API (``test_examples_pass_real_kwargs``,
   ``test_playground_demos_the_api``). Y étendre l'interdiction casserait
   des gates saines.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest

from tests.consistency._discovery import REPO_ROOT, parsed_sources

#: Preuve de morsure : contrôle POSITIF — le balayage des imports de
#: `tests/e2e` rend une population réelle, donc l'interdiction porte sur
#: des imports vus et non sur le vide.
MUTATION_PROOF = "test_discovery_is_not_vacuous"

_E2E = REPO_ROOT / "tests" / "e2e"

#: 12 fichiers sous tests/e2e le 2026-08-19 ; le plancher laisse de la
#: marge sans laisser passer un balayage mort.
_E2E_FLOOR = 6


@functools.lru_cache(maxsize=1)
def _e2e_sources() -> tuple[tuple[Path, ast.Module], ...]:
    # ``parsed_sources`` lit en utf-8-sig et LÈVE sur un fichier
    # illisible : un fichier ne sort jamais du balayage en silence
    # (cf. ``test_no_gate_swallows_a_file``). Elle porte aussi le
    # plancher, donc la gate n'en écrit pas un second.
    return tuple(
        (s.path, s.tree) for s in parsed_sources(_E2E, floor=_E2E_FLOOR)
    )


@functools.lru_cache(maxsize=1)
def _imports() -> tuple[tuple[str, int, str], ...]:
    """``(fichier, ligne, module importé)`` pour chaque import de ``tests/e2e``."""
    found: list[tuple[str, int, str]] = []
    for path, tree in _e2e_sources():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    found.append((rel, node.lineno, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    found.append((rel, node.lineno, alias.name))
    return tuple(found)


def test_discovery_is_not_vacuous() -> None:
    """Plancher ancré sur la DÉCOUVERTE : le balayage ET l'extraction.

    Sans le second cran, un jour où l'extraction cesserait de rendre des
    imports — fichiers déplacés, ``ast`` mal parcouru — l'interdiction
    serait verte sur zéro import, en certifiant la santé de rien.
    """
    sources = _e2e_sources()
    assert len(sources) >= 6, (
        f"seulement {len(sources)} fichiers sous {_E2E} (9 le 2026-08-16) — "
        f"la suite a-t-elle bougé ?"
    )
    imports = _imports()
    assert len(imports) >= 20, (
        f"seulement {len(imports)} imports extraits des {len(sources)} "
        f"fichiers e2e (33 le 2026-08-16) — l'extraction AST a cassé."
    )


@pytest.mark.parametrize(
    ("source", "lineno", "module"),
    _imports(),
    ids=[f"{s}:{n}:{m}" for s, n, m in _imports()],
)
def test_e2e_never_imports_an_example(source: str, lineno: int, module: str) -> None:
    assert not (module == "examples" or module.startswith("examples.")), (
        f"{source}:{lineno} importe `{module}`.\n\n"
        f"  Un test e2e boote ses propres apps, depuis `tests/e2e/apps/`. "
        f"`examples/` est de la documentation : elle doit rester libre de "
        f"changer sans casser la suite du framework, et la suite doit "
        f"pouvoir exiger une forme stable sans figer une démo.\n"
        f"  Copie ce dont tu as besoin dans une app de `tests/e2e/apps/` et "
        f"pointe la fixture dessus — c'est ce qu'ont fait `todo_app`, "
        f"`counter_app` et `board_app`."
    )

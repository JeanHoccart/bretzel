"""Gate : les apps d'``examples/`` restent importables.

Deux balayages, deux raisons différentes — cf. les deux sections
ci-dessous. Le premier est une LISTE (les apps dont un test dépend,
à des chemins qui ne sont pas tous ``main.py``), le second est
DÉCOUVERT (toutes les apps, sans liste à tenir).

I. Les apps dont un test dépend
--------------------------------

The test suite dogfoods real ``examples/`` apps as its apps-under-test :
``tests/e2e/conftest.py`` boots counter / todo / kanban, ``tests/audit/
harness.py`` boots the playground, and a couple of integration tests
import flat / mad / playground / docs directly. Those examples exist to
DEMO the framework and are refactored for demo reasons — when the todo
example was rebuilt from ``examples/todo/todo.py`` into a feature-based
``examples/todo/main.py``, the e2e ``todo_url`` fixture kept importing the
old path. Nobody noticed : the import is lazy (inside the fixture body),
e2e is not in the fast subset, and there is no CI. The whole
``test_todo.py`` suite was silently dead for weeks.

This gate makes that class of breakage surface at fast-subset speed
(``pytest tests/consistency``) instead of only when someone happens to run
the browser suites. It is import-only — no server boots, no browser — so
it stays milliseconds-cheap.

**Keep in sync** with the module paths in ``tests/e2e/conftest.py``,
``tests/audit/harness.py``, ``tests/integration/test_feature_include.py``
and ``tests/integration/test_matrix_reactivity.py``. If a test starts
depending on a new example app, add it here.

II. Toutes les autres (2026-08-29)
-----------------------------------
La liste ci-dessus ne couvre que **sept** apps sur dix-sept, et
``examples/crm`` n'en fait pas partie. Le 2026-08-29 elle a cessé
d'importer : ``features/accounts.py`` prenait ``DatatableState`` dans
``bretzel``, alors que le symbole était descendu dans ``bretzel/state/``
en gardant sa porte chez ``bretzel.components`` (6baaf918). Les deux
autres sites du dépôt l'écrivaient déjà correctement — donc le
refactor était bon, et c'est ce seul appelant qui est resté en arrière.

**Rien ne l'a vu.** L'app la plus grosse du dépôt, celle qui sert de
démonstration produit, est restée non démarrable jusqu'à ce que
quelqu'un essaie de la lancer à la main. C'est la classe que ce second
balayage ferme, et il est DÉCOUVERT : toute app d'``examples/`` qui a un
``main.py`` y entre d'elle-même, sans liste à mettre à jour — la liste
oubliée étant précisément ce qui a coûté la première moitié de cette
gate.

Ce qu'il ne fait PAS
---------------------
Il importe, il ne rend pas. Une app peut importer et rendre 500 sur
toutes ses pages ; ce balayage-là existe pour les BANCS
(``test_every_bench_page_still_renders``) et pas pour les exemples, dont
plusieurs demandent une session ou des données semées. Import-only reste
la mesure la moins chère qui aurait attrapé le cas réel.
"""

from __future__ import annotations

import importlib

import pytest

from tests.consistency._discovery import REPO_ROOT

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "importe les modules et vérifie qu'ils s'importent : l'exécution "
    "EST le test, il n'y a aucun motif à reconnaître"
)

#: Neuf apps le 2026-09-07 (dix-sept le 2026-08-29 : l'élagage des
#: exemples en a retiré onze, et `counter` n'expose pas de `main`). Le
#: plancher est ancré sur la DÉCOUVERTE, pas sur la population : un glob
#: cassé rendrait la gate verte en n'ayant rien importé, ce qui est
#: exactement le mode d'échec qu'elle vient fermer.
EXAMPLE_APPS_FLOOR = 8


def _example_apps() -> list[str]:
    """Les modules ``examples.<nom>.main`` présents sur le disque."""
    root = REPO_ROOT / "examples"
    return sorted(
        f"examples.{d.name}.main"
        for d in root.iterdir()
        if d.is_dir() and (d / "main.py").is_file()
    )


EXAMPLE_APP_MODULES: tuple[str, ...] = tuple(_example_apps())

# (module path, must expose a top-level ``app``) — the exact modules the
# test suite imports as fixtures / harness roots.
FIXTURE_APP_MODULES: tuple[tuple[str, bool], ...] = (
    ("tests.e2e.apps.todo_app", True),    # e2e todo_url — dedicated fixture app
    ("examples.kanban.main", True),       # e2e kanban_url
    ("examples.playground.main", True),   # audit harness + matrix reactivity
    ("examples.playground.app.routes", False),  # audit harness side-effect import
)


@pytest.mark.parametrize(
    "module_path,needs_app",
    FIXTURE_APP_MODULES,
    ids=[m for m, _ in FIXTURE_APP_MODULES],
)
def test_fixture_app_module_imports(module_path: str, needs_app: bool) -> None:
    """The example module a test depends on must import cleanly, and — when
    it is booted as an app — expose a top-level ``app``."""
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # the whole point is to report ANY import failure
        pytest.fail(
            f"{module_path!r} is imported by a test fixture/harness but no "
            f"longer imports ({type(exc).__name__}: {exc}). An example was "
            f"likely moved/renamed for demo reasons — update the test that "
            f"depends on it (and this gate's list)."
        )

    if needs_app:
        assert hasattr(module, "app"), (
            f"{module_path!r} is booted as an app-under-test but no longer "
            f"exposes a top-level ``app``."
        )


def test_the_sweep_found_the_examples() -> None:
    """Plancher : la découverte a bien lu le disque.

    Sans lui, un ``examples/`` déplacé ou un glob cassé laisserait le
    paramétrage vide — zéro cas, zéro rouge, et la gate attesterait que
    dix-sept apps démarrent alors qu'elle n'en a ouvert aucune.
    """
    assert len(EXAMPLE_APP_MODULES) >= EXAMPLE_APPS_FLOOR, (
        f"{len(EXAMPLE_APP_MODULES)} app(s) découverte(s) sous "
        f"`examples/`, plancher {EXAMPLE_APPS_FLOOR}. La découverte ne "
        "lit plus le dossier — ce balayage n'affirme donc plus rien."
    )


@pytest.mark.parametrize("module_path", EXAMPLE_APP_MODULES,
                         ids=[m.split(".")[1] for m in EXAMPLE_APP_MODULES])
def test_every_example_app_still_imports(module_path: str) -> None:
    """Toute app d'``examples/`` s'importe et expose son ``app``.

    Un rouge ici veut presque toujours dire qu'un symbole du framework a
    bougé et qu'un appelant est resté en arrière. **On corrige l'exemple,
    pas le framework** : c'est le sens du refactor qui décide, et
    l'exemple est là pour le suivre.
    """
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # on veut REMONTER n'importe quel échec
        pytest.fail(
            f"{module_path!r} ne s'importe plus ({type(exc).__name__}: "
            f"{exc}). Un symbole du framework a probablement bougé — "
            "corrige l'appelant dans `examples/`, pas la surface publique."
        )
    assert hasattr(module, "app"), (
        f"{module_path!r} n'expose plus de `app` au niveau module : "
        "`py -m examples.<nom>.main` ne démarrera pas."
    )

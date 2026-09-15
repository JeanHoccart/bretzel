"""Un banc sert son compilateur CSS, il ne le télécharge pas chez un tiers.

Ce que cette gate ferme
-----------------------

En mode dev, Bretzel laisse le compilateur Tailwind travailler DANS la
page et va le chercher chez unpkg.com — deux allers-retours et 276 Ko par
chargement (``bretzel/render/shell.DEFAULT_TAILWIND_BROWSER_URL``). Pour
un humain qui développe c'est un bon compromis : pas de binaire à
installer, pas de 3 s à chaque redémarrage.

**Pour une suite, c'en est un mauvais**, et le prix a été payé. Les 84
probes tournent en dev, donc leur fiabilité dépendait d'un site tiers.
Mesuré le 2026-09-13 en coupant unpkg : l'encre d'un bouton passe de
``oklab(…)`` à ``rgb(0, 0, 0)`` et le document perd une feuille de style.
C'est exactement ce qu'avait rapporté ``probe_datatable_filter`` au milieu
d'un run complet — toutes les couleurs à ``rgb(0, 0, 0)`` — et ça explique
que la rouge se déplaçait d'un probe à l'autre : sous contention, 84
probes tapent des centaines de fois le même CDN.

Un test qui échoue parce qu'un site tiers est lent ne dit rien sur le
code. Il coûte même plus qu'il ne rapporte : il apprend à ne pas croire
la suite.

Pourquoi la règle porte sur l'APPEL et pas sur le résultat
-----------------------------------------------------------

Vérifier qu'aucune page ne sollicite unpkg demanderait un navigateur,
donc cette gate vivrait dans une suite lente — celle-là même qu'elle
protège. L'appel à ``use_local_tailwind()``, lui, se lit dans la source :
c'est un contrôle statique, dans le run rapide, qui rougit avant qu'on
lance quoi que ce soit.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

from tests.consistency._discovery import REPO_ROOT, parsed_sources

PROBES_DIR: Final[Path] = REPO_ROOT / "tests" / "probes"

#: 84 probes + 52 bancs + le socle le 2026-09-13.
PROBES_FLOOR: Final[int] = 100

#: Preuve de morsure : le lecteur d'appels, sur ses deux versants.
MUTATION_PROOF = "test_the_call_reader_still_bites"


def calls_in(tree: ast.AST) -> set[str]:
    """Les fonctions appelées par leur nom nu dans ce module."""
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def benches() -> list[object]:
    """Les bancs qui SERVENT une page, c'est-à-dire ceux qui ont un port.

    Ancré sur ``bench_port`` et non sur le nom du fichier : un banc sans
    serveur — il en existe, des modules de données partagés entre deux
    probes — n'a pas de compilateur à servir, et l'exiger de lui ferait
    une gate qu'on apprend à contourner.
    """
    return [
        s
        for s in parsed_sources(PROBES_DIR, floor=PROBES_FLOOR)
        if s.path.name.startswith("bench_")
        and "bench_port" in calls_in(s.tree)
    ]


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher sur la DÉCOUVERTE : 60 bancs servent une page le
    2026-09-13. Sans ce seuil, « tous servent leur compilateur » se dirait
    sur une liste vide."""
    trouves = benches()
    assert len(trouves) >= 50, (
        f"seulement {len(trouves)} bancs à serveur découverts — le lecteur "
        f"d'appels ne voit plus `bench_port`, donc cette gate ne juge plus "
        f"personne."
    )


@pytest.mark.parametrize("bench", benches(), ids=lambda s: s.path.name)
def test_a_bench_serves_its_own_compiler(bench: object) -> None:
    """Chaque banc à serveur appelle ``use_local_tailwind()``."""
    assert "use_local_tailwind" in calls_in(bench.tree), (  # type: ignore[attr-defined]
        f"{bench.path.name} sert une page sans servir son compilateur.\n"  # type: ignore[attr-defined]
        f"  Sa page ira le chercher chez unpkg.com — 276 Ko et deux "
        f"allers-retours par chargement — et le jour où ce tiers broncher"
        f"a, le probe rendra toutes les couleurs en `rgb(0, 0, 0)` et "
        f"accusera un composant.\n"
        f"  Ajoute, juste avant de démarrer le serveur :\n"
        f"      from tests.probes._serve import use_local_tailwind\n"
        f"      use_local_tailwind()"
    )


def test_the_call_reader_still_bites() -> None:
    """Les deux versants du lecteur.

    Il cherche un appel par NOM NU : une mention en commentaire, en
    docstring ou en import ne compte pas — seul l'appel compte, parce que
    seul l'appel agit.
    """
    vu = calls_in(ast.parse("def f():\n    use_local_tailwind()\n"))
    assert "use_local_tailwind" in vu

    absent = calls_in(
        ast.parse(
            "from tests.probes._serve import use_local_tailwind\n"
            "x = 'use_local_tailwind'  # nomme, jamais appele\n"
        )
    )
    assert "use_local_tailwind" not in absent, (
        "le lecteur prend un import ou une chaîne pour un appel : un banc "
        "qui nomme la fonction sans l'appeler passerait."
    )

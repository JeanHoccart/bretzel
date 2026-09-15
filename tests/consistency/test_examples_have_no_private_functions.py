"""Gate : aucune fonction d'``examples/`` ne porte le préfixe ``_``.

Le défaut qu'elle ferme
-----------------------
La règle 6 du CLAUDE.md est écrite depuis longtemps — « ``_`` prefix
interdit sur les fonctions dans le code utilisateur du playground /
exemples ; ``_xxx`` reste OK pour le framework interne ». Le corpus la
contredisait à **99 fonctions**, et la doc de gabarit la contredisait
elle aussi : ``playground-pattern.md`` PRESCRIVAIT ``_build_preview`` et
``_control``.

Deux conventions concurrentes pour la même chose, chacune adossée à un
document du dépôt — 66 pages écrivaient ``_control``, 8 écrivaient
``control``. C'est exactement le « d'un composant à l'autre tu changes
les façons de faire » que ce dépôt cherche à éliminer, et aucune
relecture ne l'aurait vu : chaque page est cohérente AVEC ELLE-MÊME.

Arbitré le 2026-09-06 : la règle 6 gagne, le gabarit est corrigé.

Pourquoi ``examples/`` et pas ``bretzel/``
------------------------------------------
Le préfixe dit « n'appelle pas ça depuis dehors ». Dans le framework
c'est une frontière réelle. Dans une app, il n'y a pas de dehors : le
module N'EST PAS une bibliothèque, et le préfixe ne fait qu'ajouter du
bruit à un nom que personne n'importera. Les CLASSES gardent le droit au
préfixe (``_Source`` dans ``examples/docs``) — la règle nomme les
fonctions.

Ce que la gate NE dit pas
-------------------------
Rien sur les fonctions IMBRIQUÉES, ni sur les méthodes : elle ne lit que
le niveau module, là où vit la notion d'API d'un fichier.
"""

from __future__ import annotations

import ast

import pytest

from tests.consistency._discovery import REPO_ROOT

EXAMPLES = REPO_ROOT / "examples"


def private_functions(source: str) -> tuple[str, ...]:
    """Les ``def _x`` de NIVEAU MODULE — le détecteur, isolé.

    ``__dunder__`` sort : ce n'est pas un privé, c'est un protocole.
    """
    return tuple(
        node.name
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("_")
        and not node.name.startswith("__")
    )


def example_sources() -> list[tuple[str, str]]:
    return [
        (str(path.relative_to(EXAMPLES)).replace("\\", "/"),
         path.read_text(encoding="utf-8-sig"))
        for path in sorted(EXAMPLES.rglob("*.py"))
    ]


# ── Les planchers ─────────────────────────────────────────────────────


def test_the_sweep_reads_the_examples() -> None:
    """Sans lui, un chemin cassé rendrait la gate verte sur zéro fichier."""
    found = example_sources()
    assert len(found) >= 200, (
        f"seulement {len(found)} fichier(s) Python lu(s) sous {EXAMPLES} "
        f"— il y en avait 300 le 2026-09-06. Le balayage est cassé."
    )


def test_the_reader_finds_functions() -> None:
    """Second plancher : l'extracteur voit encore des ``def``.

    Un ``private_functions`` qui rendrait toujours le tuple vide passe
    le plancher ci-dessus et rend l'assertion verte partout.
    """
    total = sum(
        sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for node in ast.parse(source).body
        )
        for _page, source in example_sources()
    )
    assert total >= 500, (
        f"seulement {total} fonction(s) de niveau module trouvée(s) dans "
        f"tout `examples/`. L'extracteur est cassé."
    )


# ── L'assertion ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("page", "source"), example_sources(), ids=lambda v: v if "\n" not in v else ""
)
def test_no_example_function_is_private(page: str, source: str) -> None:
    private = private_functions(source)
    assert not private, (
        f"`examples/{page}` définit {', '.join(private)} — un préfixe "
        f"`_` sur une fonction d'app.\n"
        f"  Règle 6 du CLAUDE.md. Le préfixe dit « n'appelle pas ça "
        f"depuis dehors » : dans une app, il n'y a pas de dehors, et le "
        f"nom ne fait que porter du bruit.\n"
        f"  Si le nom nu est déjà pris dans le fichier, c'est le nom "
        f"qu'il faut choisir mieux — `_format` est devenu "
        f"`format_result`, `_n` est devenu `feature_node`."
    )


# ── La morsure ────────────────────────────────────────────────────────


def test_the_detector_catches_a_private_function() -> None:
    """Mutation : le détecteur voit la forme fautive, et elle seule."""
    assert private_functions("def _control(label): ...") == ("_control",)
    assert private_functions("async def _load(): ...") == ("_load",)

    # Le versant licite — un détecteur qui rougit sur tout est aussi
    # inutile qu'un détecteur aveugle.
    assert private_functions("def control(label): ...") == ()
    assert private_functions("class X:\n    def _method(self): ...") == ()
    assert private_functions("def outer():\n    def _inner(): ...") == ()
    assert private_functions("def __init_subclass__(): ...") == ()

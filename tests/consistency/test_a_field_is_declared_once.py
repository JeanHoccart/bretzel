"""Gate : un champ d'état se déclare par ``field()``, et par rien d'autre.

Décidé le 2026-09-05. Jusque-là il y avait deux orthographes pour un
résultat **rigoureusement identique** — vérifié : ``n: int = 0`` et
``n: int = field(default=0)`` produisent le même défaut, le même type, la
même URL. Deux façons d'écrire une chose obligent un lecteur à savoir
laquelle porte quoi ; et surtout, une option de champ n'a nulle part où
se poser sur la forme courte, donc chaque déclaration nouvelle devait
s'inventer un TYPE (``Counter``, ``Amount``…) et grossir la surface
publique. Avec un appel, elles s'ajoutent en paramètres.

Ce que la migration a représenté, mesuré le jour même : **403
déclarations** réécrites mécaniquement, sur 1 507 — les 1 104 autres
passaient déjà par ``field()``.

**Pourquoi une gate alors que la métaclasse REFUSE déjà** : elle refuse à
l'import, donc seulement pour un module que quelqu'un importe. Un état
déclaré dans un fichier qu'aucune suite ne charge passerait entre les
gouttes et n'exploserait qu'en production, au premier rendu de sa page.
Ici, c'est lu sans rien exécuter.

⚠️ Deux formes ne sont PAS des champs et sortent du balayage : un nom
préfixé ``_`` (privé, la métaclasse le saute) et une annotation
``ClassVar`` (c'est précisément la façon standard de dire « ceci n'est
pas un champ d'instance » — et jusqu'au 2026-09-05 la métaclasse la
promouvait quand même, donc une constante de classe était persistée,
diffée, et envoyée au navigateur).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    PACKAGE_DIR,
    PACKAGE_FLOOR,
    ParsedSource,
    parsed_sources,
)

REPO_ROOT: Final[Path] = PACKAGE_DIR.parent
EXAMPLES_DIR: Final[Path] = REPO_ROOT / "examples"

#: ``ClassVar[…]`` en tête d'annotation, avec ou sans préfixe de module —
#: la même reconnaissance que la métaclasse, et pour la même raison : les
#: annotations sont du TEXTE ici.
_CLASS_VAR_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:\w+\.)?ClassVar\b")


def _sources() -> list[ParsedSource]:
    return parsed_sources(PACKAGE_DIR, floor=PACKAGE_FLOOR) + parsed_sources(
        EXAMPLES_DIR, floor=EXAMPLES_FLOOR
    )


def _is_state_class(node: ast.ClassDef) -> bool:
    """Une classe qui hérite d'un ``…State``.

    Reconnaissance par le NOM de base, comme les autres gates du dossier :
    résoudre l'héritage demanderait d'importer, ce qu'une gate statique ne
    fait pas.
    """
    return any("State" in ast.unparse(b) for b in node.bases)


def _is_field_call(value: ast.expr | None) -> bool:
    if not isinstance(value, ast.Call):
        return False
    return "field" in ast.unparse(value.func)


def declarations() -> tuple[list[str], int]:
    """``(les déclarations nues, le nombre de déclarations par field())``.

    Les deux dans la même passe : le second est le contrôle POSITIF, sans
    lequel un détecteur cassé rendrait « zéro contrevenant » — ce qui se
    lit exactement comme « tout est propre ».
    """
    nues: list[str] = []
    par_appel = 0
    for source in _sources():
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.ClassDef) or not _is_state_class(node):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign):
                    continue
                if not isinstance(stmt.target, ast.Name):
                    continue
                if stmt.target.id.startswith("_"):
                    continue
                if _CLASS_VAR_RE.match(ast.unparse(stmt.annotation)):
                    continue
                if _is_field_call(stmt.value):
                    par_appel += 1
                else:
                    nues.append(
                        f"{source.path.relative_to(REPO_ROOT).as_posix()}"
                        f":{stmt.lineno} — {node.name}.{stmt.target.id}"
                    )
    return nues, par_appel


def test_the_sweep_is_not_vacuous() -> None:
    """① Le plancher, lu depuis la découverte de CETTE gate."""
    assert len(_sources()) >= PACKAGE_FLOOR + EXAMPLES_FLOOR


def test_no_field_is_declared_without_field() -> None:
    """② L'interdiction."""
    nues, _ = declarations()
    assert not nues, (
        "Ces champs sont déclarés sans `field()` :\n  "
        + "\n  ".join(nues)
        + "\n\nUne seule forme : `nom: type = field(default=…)`. C'est là "
        "que vivent `default_factory`, `url` et `merge`, et il n'y a pas "
        "de seconde façon de le faire. La métaclasse le refuse déjà à "
        "l'import — cette gate attrape le module que personne n'importe."
    )


def test_the_sweep_actually_finds_declarations() -> None:
    """③ Le contrôle POSITIF.

    L'interdiction seule passerait sur un balayage qui ne reconnaît plus
    une classe d'état — le cas mesuré ailleurs dans ce dossier, où un
    détecteur cherchait un nom que deux modules sur vingt-deux
    utilisaient.
    """
    _, par_appel = declarations()
    assert par_appel >= 1_000, (
        f"seulement {par_appel} déclarations par `field()` trouvées — le "
        f"balayage ou la reconnaissance des classes d'état a cassé "
        f"(1 507 mesurées le 2026-09-05)."
    )


def test_the_detector_still_bites() -> None:
    """④ La mutation, trois versants."""
    coupable = ast.parse("class S(AppState):\n    n: int = 0\n")
    innocent = ast.parse("class S(AppState):\n    n: int = field(default=0)\n")
    constante = ast.parse("class S(AppState):\n    N: ClassVar[int] = 3\n")

    def nues_de(tree: ast.Module) -> list[str]:
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_state_class(node):
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign):
                    continue
                if _CLASS_VAR_RE.match(ast.unparse(stmt.annotation)):
                    continue
                if not _is_field_call(stmt.value):
                    out.append(stmt.target.id)  # type: ignore[union-attr]
        return out

    assert nues_de(coupable) == ["n"]
    assert nues_de(innocent) == []
    assert nues_de(constante) == [], (
        "une ``ClassVar`` est signalée comme un champ nu — or ce n'est pas "
        "un champ du tout, et la métaclasse la saute."
    )

"""Aucune clause ``from … import (…)`` ne lie deux fois le même nom.

Le problème qu'elle ferme
-------------------------
Douze fichiers de ``bretzel/components/`` portaient exactement la même
faute au 2026-09-07 : ``theme_context`` écrit **deux fois** dans la même
clause d'import, toujours en TÊTE, avant une liste par ailleurs triée.
Douze fois le même geste, donc une automatisation, pas une inattention.

Rien ne la révélait :

- **à l'exécution**, elle est inerte — Python lie le nom deux fois au
  même objet, aucune erreur, aucun coût mesurable ;
- **à la lecture**, elle est invisible : ces clauses font dix à vingt
  lignes, et le doublon se lit comme le début de la liste ;
- **côté outillage**, Ruff la voit (``F811`` + ``I001``) mais personne ne
  le lance sur ``bretzel/`` — il y remonte 153 constats, dont ceux-ci
  étaient noyés. Ni ``bretzel check`` ni aucune gate de ce répertoire ne
  la cherchait.

Un import en double n'est jamais load-bearing : la seule forme utile de
répétition, ``from x import a, a as b``, lie deux noms DIFFÉRENTS et
reste licite ici (la clé lue est ``asname or name``). Deux clauses
séparées vers le même module le restent aussi — la règle est par clause.

Ce que cette gate ne voit PAS
------------------------------
1. Le nom re-lié par DEUX clauses distinctes (``from a import x`` puis
   ``from b import x``), qui est un vrai écrasement — mais qui, lui, est
   parfois délibéré (un repli conditionnel). C'est ``F811`` de Ruff.
2. L'ORDRE dans la clause. Le nettoyage du 2026-09-07 a remis les noms à
   leur place alphabétique en passant, mais c'est ``I001``, et
   ``bretzel/`` en porte encore 25.

Les deux appartiennent au même chantier, écrit dans ``.claude/work/todo.md``
sous « Ruff n'est pas exécutable » : rendre Ruff opposable sur
``bretzel/`` par une base cliquetée fermerait cette gate ET ses 129
voisines. Elle est écrite en attendant, pour la seule classe qui n'a
aucune lecture licite.
"""

from __future__ import annotations

import ast
import functools

from tests.consistency._discovery import (
    PACKAGE_DIR,
    PACKAGE_FLOOR,
    REPO_ROOT,
    parsed_sources,
)


@functools.lru_cache(maxsize=1)
def import_clauses() -> tuple[tuple[str, ast.ImportFrom], ...]:
    """``(chemin lisible, clause)`` pour tout ``from … import …`` du paquet.

    Une seule extraction, partagée par le détecteur et par le contrôle
    positif. Écrite ici plutôt que deux fois : si la population surveillée
    se rétrécit un jour, le contrôle positif doit rétrécir AVEC elle —
    sinon il continue de borner l'ancienne forme et le vert ne dit plus
    rien de ce que la branche voit.
    """
    return tuple(
        (source.path.relative_to(REPO_ROOT).as_posix(), node)
        for source in parsed_sources(PACKAGE_DIR, floor=PACKAGE_FLOOR)
        for node in ast.walk(source.tree)
        if isinstance(node, ast.ImportFrom)
    )


def repeated_in(node: ast.ImportFrom) -> list[str]:
    """Les noms que CETTE clause lie deux fois.

    Le détecteur, extrait pour être mutable. La clé est
    ``asname or name`` : c'est ce que la clause **lie**, donc
    ``import a, a as b`` n'est pas un doublon et ``import a as x, b as x``
    en est un.
    """
    seen: set[str] = set()
    repeats: list[str] = []
    for alias in node.names:
        bound = alias.asname or alias.name
        if bound in seen:
            repeats.append(bound)
        seen.add(bound)
    return repeats


def offenders() -> list[str]:
    return [
        f"{path}:{node.lineno} — {name}"
        for path, node in import_clauses()
        for name in repeated_in(node)
    ]


def test_the_sweep_is_not_vacuous() -> None:
    """Deux planchers, parce qu'ils bornent deux choses différentes.

    Le premier borne la POPULATION lue et lit la découverte de cette
    gate — pas un ``rglob`` frais, sans quoi débrancher le balayage
    laisserait « zéro contrevenant » tout vert (432 fichiers le
    2026-09-07). Le second borne ce que la BRANCHE voit : une gate qui
    n'examinerait plus que des clauses à un seul nom ne trouverait aucun
    doublon en n'ayant pas pu en trouver, et ça se lit exactement comme
    « tout est propre » (609 clauses à plusieurs noms le même jour).
    """
    assert len(parsed_sources(PACKAGE_DIR, floor=PACKAGE_FLOOR)) >= PACKAGE_FLOOR
    multi = [node for _, node in import_clauses() if len(node.names) > 1]
    assert len(multi) >= 200


def test_no_import_clause_repeats_a_name() -> None:
    duplicates = offenders()
    assert not duplicates, (
        "Une clause d'import lie deux fois le même nom :\n  "
        + "\n  ".join(duplicates)
        + "\n\nC'est inerte à l'exécution et invisible en revue, donc ça "
        "s'accumule : douze fichiers portaient le même doublon "
        "(`theme_context`) avant le 2026-09-07. Retire la ligne en trop "
        "et laisse le nom à sa place alphabétique."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des clauses fabriquées.

    Le versant licite compte autant : ``a as b`` lie un AUTRE nom, et
    deux clauses vers le même module sont l'idiom qu'emploient six
    fichiers de ``components/`` (l'import renommé ``… as _foo`` que Ruff
    isole dans sa propre clause). Un détecteur qui les rougirait serait
    retiré dans la semaine.
    """

    def clauses(src: str) -> list[ast.ImportFrom]:
        return [
            n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)
        ]

    (coupable,) = clauses("from m import (\n    a,\n    a,\n    b,\n)\n")
    assert repeated_in(coupable) == ["a"]

    (collision,) = clauses("from m import a as x, b as x\n")
    assert repeated_in(collision) == ["x"]

    for licite in (
        "from m import a, a as b\n",
        "from m import a\nfrom m import (\n    b as _b,\n)\n",
        "from m import a, b, c\n",
        "from m import a as a\n",
    ):
        assert not [n for c in clauses(licite) for n in repeated_in(c)], licite

"""Gate — un composant ne se contredit pas sur ses propres ClassVar.

**La forme de dette la plus chère du dépôt, mesurée.** Le CLAUDE.md la
nomme : « une docstring qui se contredit 50 lignes plus loin » est plus
coûteuse qu'une docstring vague, parce qu'elle est *crédible* — elle cite
une valeur exacte, dans la syntaxe du code, à côté du code.

Le cas qui a produit cette gate (audit du 2026-08-13) : ``signature_pad``
déclarait ``BINDABLE_PROPS = ("value",)`` et deux de ses commentaires
affirmaient ``BINDABLE_PROPS = ()`` — l'un dix lignes sous la
déclaration, l'autre dans le docstring de ``.clear()`` où il servait de
PRÉMISSE à un raisonnement (« aucune écriture write-through possible :
la valeur ne vit pas dans une binding »). La conclusion était juste, la
prémisse fausse ; un lecteur qui s'y fiait aurait cru la prop
non-bindable. ``.claude/work/todo.md`` avait déjà recopié l'affirmation.

Ce que la gate vérifie : quand la prose cite ``<CLASSVAR> = <littéral>``,
le littéral doit être une valeur réellement déclarée **par la classe qui
possède cette prose**.

⚠️ **La comparaison est par CLASSE, pas par fichier**, et ce n'est pas un
raffinement : 11 fichiers du dépôt déclarent DEUX valeurs différentes du
même ClassVar (``navbar.py`` : ``Navbar = ()`` et ``NavbarItem =
("active","badge","disabled")``). En comparant par fichier, une prose
affirmant ``BINDABLE_PROPS = ()`` à propos de ``NavbarItem`` passait —
la forme signature_pad exactement, dans les huit plus gros composants du
dépôt. Une prose de docstring de MODULE, elle, n'a pas de classe
englobante : elle est comparée à l'ensemble des valeurs du fichier, parce
qu'un docstring de module parle légitimement du composant principal.
"""

from __future__ import annotations

import ast
import functools
import re
import tokenize
from pathlib import Path

import pytest

from tests.consistency._discovery import (
    COMPONENTS_DIR,
    assert_sweep_is_not_vacuous,
    parsed_sources,
)

#: Preuve de morsure : contrôle POSITIF — assez de fichiers déclarent réellement la prose
#: que la gate confronte.
MUTATION_PROOF = "test_the_sweep_reads_something"

#: Les ClassVar dont une valeur mal citée induit en erreur sur le CONTRAT
#: du composant (ce qu'on peut lui binder, ce qu'il dispatche, ce qu'il
#: expose en impératif). ``THEME``/``THEME_KEY`` sont hors périmètre :
#: leur valeur ne se cite pas en tuple.
_TRACKED = ("BINDABLE_PROPS", "IMPERATIVE", "EVENTS", "NAMED_SLOTS",
            "ICON_SLOTS")

_CITATION = re.compile(
    r"\b(?P<name>" + "|".join(_TRACKED) + r")\s*=\s*(?P<value>\([^)]*\))"
)

#: Plancher de non-vacuité — le nombre de fichiers qui DÉCLARENT un
#: ClassVar suivi, pas le nombre de citations trouvées.
#:
#: ⚠️ La première version comptait les citations, plancher 7 sur une
#: population de 7. Deux défauts, tous deux réels : (1) six des sept sont
#: des ``BINDABLE_PROPS = ()`` en docstring de module, c'est-à-dire la
#: redite du défaut de ``Component`` que ``test_no_classvar_restates_the_
#: default`` existe pour supprimer — un nettoyage légitime aurait fait
#: rougir cette gate pour une raison étrangère à toute contradiction ;
#: (2) le plancher mesurait la POPULATION, qui peut fondre à zéro sans
#: rien casser, au lieu de la DÉCOUVERTE, qui est ce que « le balayage
#: lit-il encore quelque chose ? » demande vraiment.
_MIN_DECLARING_FILES = 60

#: Plancher du balayage composants, aligne sur ``_SWEEP_FLOOR``.
_COMPONENTS_FLOOR = 180


#: ⚠️ Ce module lisait ses sources avec ``errors="ignore"``, puis rendait
#: ``None`` sur ``SyntaxError``. Deux façons d'être aveugle plutôt qu'une :
#: le premier MANGE silencieusement les octets qu'il ne sait pas décoder
#: (donc peut couper une prose au milieu d'une citation), le second fait
#: sortir le fichier du balayage sans un mot. Remplacés par la primitive
#: partagée, qui lit en ``utf-8-sig`` et LÈVE — cf.
#: ``_discovery.parsed_sources``.


def _prose(path: Path, tree: ast.Module) -> list[tuple[str, str | None]]:
    """``(texte, nom de la classe propriétaire ou None)``.

    ``None`` = prose de module (docstring de module, commentaire hors
    classe) : elle parle du fichier, donc on la compare à tout le fichier.
    """
    out: list[tuple[str, str | None]] = []

    # Les commentaires n'existent pas dans l'AST : on les rattache à la
    # classe dont ils tombent dans les lignes.
    spans: list[tuple[int, int, str]] = [
        (node.lineno, getattr(node, "end_lineno", node.lineno), node.name)
        for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    ]

    def owner(lineno: int) -> str | None:
        for start, end, name in spans:
            if start <= lineno <= end:
                return name
        return None

    with path.open("rb") as fh:
        try:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type == tokenize.COMMENT:
                    out.append((tok.string, owner(tok.start[0])))
        except (tokenize.TokenError, SyntaxError, IndentationError):
            pass

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                out.append((doc, node.name))
        elif isinstance(node, (ast.Module, ast.FunctionDef,
                               ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                lineno = getattr(node, "lineno", 0)
                out.append((doc, owner(lineno) if lineno else None))
    return out


def _declared(tree: ast.Module) -> dict[tuple[str | None, str], list[tuple]]:
    """``{(classe, ClassVar): [valeurs]}`` + ``(None, ClassVar)`` = union.

    L'entrée ``None`` sert la prose de module, qui n'a pas de classe
    englobante mais parle légitimement du composant du fichier.
    """
    out: dict[tuple[str | None, str], list[tuple]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                targets = [stmt.target]
            elif isinstance(stmt, ast.Assign):
                targets = stmt.targets
            else:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id not in _TRACKED:
                    continue
                try:
                    value = ast.literal_eval(stmt.value)
                except (ValueError, SyntaxError):
                    continue
                if isinstance(value, tuple):
                    out.setdefault((node.name, target.id), []).append(value)
                    out.setdefault((None, target.id), []).append(value)
    return out


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[tuple, int]:
    """``(citations, nombre de fichiers déclarant un ClassVar suivi)``.

    Le préfiltre textuel avant tout AST est ce qui rend ce balayage
    tenable : seuls ~9 fichiers sur 256 contiennent la forme
    ``NAME = (...)`` en clair (une déclaration annotée —
    ``BINDABLE_PROPS: ClassVar[…] = (…)`` — ne matche pas ``_CITATION``),
    donc on économise 256 ``ast.parse`` + ``tokenize`` complets. Mesuré :
    3,7× sur le temps de collecte, pour une sortie identique.
    """
    found = []
    declaring = 0
    for source in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR):
        path, text, tree = source.path, source.text, source.tree
        declared = _declared(tree)
        if declared:
            declaring += 1
        if not declared or not _CITATION.search(text):
            continue
        for prose, owner in _prose(path, tree):
            for match in _CITATION.finditer(prose):
                name = match.group("name")
                expected = declared.get((owner, name))
                if expected is None:
                    # La prose parle d'un ClassVar que cette classe (ou ce
                    # fichier) ne déclare pas — rien à comparer.
                    continue
                try:
                    cited = ast.literal_eval(match.group("value"))
                except (ValueError, SyntaxError):
                    continue
                if isinstance(cited, tuple):
                    found.append((path, owner, name, cited, expected))
    return tuple(found), declaring


def test_the_sweep_reads_something() -> None:
    assert_sweep_is_not_vacuous()
    _, declaring = _scan()
    assert declaring >= _MIN_DECLARING_FILES, (
        f"seulement {declaring} fichiers composant déclarent un ClassVar "
        f"suivi (91 mesurés le 2026-08-13) — le parsing ou la découverte "
        f"a cassé, et cette gate passerait alors sur n'importe quelle "
        f"contradiction."
    )


@pytest.mark.parametrize(
    "path,owner,name,cited,expected",
    _scan()[0],
    ids=[f"{p.stem}:{o or 'module'}:{n}" for p, o, n, _, _ in _scan()[0]],
)
def test_prose_does_not_contradict_the_declaration(
    path: Path, owner: str | None, name: str, cited: tuple,
    expected: list[tuple],
) -> None:
    assert any(set(cited) == set(value) for value in expected), (
        f"{path.name} ({owner or 'prose de module'}) — la prose affirme "
        f"`{name} = {cited!r}`, la déclaration dit {expected!r}.\n"
        f"  Une valeur exacte citée dans la syntaxe du code, à côté du "
        f"code, est CRUE : c'est la forme de doc fausse la plus chère du "
        f"dépôt (cf. le docstring de cette gate).\n"
        f"  Corrige la prose, ou la déclaration si c'est elle qui a tort."
    )

"""Aucune classe de couleur n'est assemblée à la main.

``f"bg-{color}"`` produit une classe qui n'existe **littéralement dans
aucune source**. Le compilateur Tailwind de PROD ne génère que ce qu'il
trouve écrit ; le mode DEV, lui, compile depuis le DOM **vivant** et la
voit déjà résolue. D'où la forme du bug : **correct en dev, mort en prod,
HTML identique des deux côtés, aucune erreur** — la classe de défaut la
plus coûteuse de ce dépôt (memory ``assembled_tailwind_class_dev_only``).

⚠️ **Cette gate a rétréci le 2026-08-30, et elle a GAGNÉ en valeur.**

Elle s'appelait ``test_safelist_covers_theme_shapes`` et portait cinq
tests autour d'un mécanisme qui n'existe plus : les gabarits
``{bg_color}``, dont la safelist calculait la clôture forme × couleur.
Cette clôture est déposée (phase 5 du chantier des jetons) — un thème
écrit maintenant ``bg-(--bz-bg)``, une classe complète que le compilateur
voit.

Ce qui reste est le seul test dont le sujet SURVIT, et il compte plus
qu'avant : la clôture **rattrapait** les classes assemblées, sans que
personne le sache. Mesuré le jour de la dépose — deux d'entre elles ne
marchaient qu'en dev depuis toujours (`f"bg-{tint}/15"` dans la démo
carousel du playground, et le `Gauge` d'``examples/ecosysteme``), et
elles sont tombées avec la clôture. C'est pourquoi le balayage couvre
maintenant ``examples/`` **et** ``bretzel/`` : le premier des deux
défauts vivait dans un exemple.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import bretzel.components
from tests.consistency._discovery import REPO_ROOT

_COMPONENTS_DIR = Path(bretzel.components.__file__).parent
_EXAMPLES_DIR = REPO_ROOT / "examples"


_COLOR_UTILITIES = (
    "bg", "text", "border", "ring", "fill", "stroke", "outline",
    "accent", "caret", "decoration", "from", "via", "to",
)
_ENDS_WITH_COLOR_UTILITY = re.compile(
    rf"\b(?:{'|'.join(_COLOR_UTILITIES)})-$"
)


def _handrolled_color_classes(tree: ast.AST) -> list[tuple[int, str]]:
    """Repère ``f"bg-{color}"`` & co. — une classe couleur assemblée à la main.

    On travaille sur l'AST et pas sur le texte : un ``text-{color}`` dans
    une docstring décrit le mécanisme, il ne l'enfreint pas. Seule une
    vraie f-string (``JoinedStr``) construit une classe à l'exécution.

    Le critère : un morceau littéral qui se termine par un préfixe
    d'utilitaire couleur, immédiatement suivi d'une interpolation dont le
    nom parle de couleur. Le filtre sur le nom écarte ``f"text-{size}"``
    (``text-sm`` est une taille de police, pas une couleur) sans rater le
    cas visé, où la variable s'appelle toujours ``color`` / ``*_color``.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for literal, following in zip(node.values, node.values[1:]):
            if not (
                isinstance(literal, ast.Constant)
                and isinstance(literal.value, str)
                and isinstance(following, ast.FormattedValue)
            ):
                continue
            if not _ENDS_WITH_COLOR_UTILITY.search(literal.value):
                continue
            names = {
                n.id.lower()
                for n in ast.walk(following.value)
                if isinstance(n, ast.Name)
            } | {
                n.attr.lower()
                for n in ast.walk(following.value)
                if isinstance(n, ast.Attribute)
            }
            if any("color" in name for name in names):
                prefix = literal.value.rsplit(" ", 1)[-1]
                found.append((node.lineno, f"{prefix}{{{'/'.join(sorted(names))}}}"))
    return found


#: Les fichiers balayés le 2026-08-30 : 272 sous ``bretzel/components``
#: plus les exemples. Le plancher laisse de la marge pour une
#: réorganisation sans laisser passer un balayage mort.
_SOURCES_FLOOR = 250


def _iter_sources() -> list[tuple[Path, str]]:
    """Les sources Python du catalogue ET des exemples.

    ``examples/`` est dans le balayage depuis le 2026-08-30 : le premier
    des deux défauts réels trouvés ce jour-là y vivait, et aucune gate ne
    le regardait.
    """
    out: list[tuple[Path, str]] = []
    for root in (_COMPONENTS_DIR, _EXAMPLES_DIR):
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            out.append((path, path.read_text(encoding="utf-8-sig")))
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la DÉCOUVERTE de cette gate.

    Sans lui, un ``rglob`` qui cesse de trouver quoi que ce soit rendrait
    l'interdiction verte en ne testant rien.
    """
    seen = _iter_sources()
    assert len(seen) >= _SOURCES_FLOOR, (
        f"seulement {len(seen)} sources balayées (plancher "
        f"{_SOURCES_FLOOR}) — le balayage est cassé, la gate ne teste "
        "plus rien."
    )


def test_no_color_class_is_assembled_by_hand() -> None:
    offenders: dict[str, str] = {}
    for path, text in _iter_sources():
        for line_no, snippet in _handrolled_color_classes(ast.parse(text)):
            offenders[f"{path.relative_to(REPO_ROOT).as_posix()}:{line_no}"] = snippet
    assert not offenders, (
        "Classes de couleur assemblées à la main : "
        f"{offenders}.\n"
        "Une classe assemblée n'existe dans aucune source, donc le "
        "compilateur de prod ne la génère pas — elle ne marche qu'en dev, "
        "où il scanne le DOM vivant.\n"
        "  Le remède depuis les paliers : écrire la classe ENTIÈRE "
        "(``bg-(--bz-bg)``) et laisser la classe-PONT porter la couleur. "
        "``bz-c-<couleur>`` peut, elle, être assemblée : ses règles sont "
        "générées, pas compilées depuis les sources."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un gabarit couleur ASSEMBLÉ est encore reconnu.

    Une f-string ``f"bg-{color}/10"`` court-circuite ``resolve_slot`` et
    n'existe en toutes lettres nulle part : elle ne sera stylée en prod
    que par coïncidence. Le détecteur repère l'utilitaire de couleur
    laissé ouvert juste avant l'interpolation.
    """
    for offending in ("bg-", "text-", "ring-offset-" [:5], "border-"):
        assert _ENDS_WITH_COLOR_UTILITY.search(offending), (
            f"{offending!r} devrait être vu comme un utilitaire ouvert"
        )
    for licit in ("bg-primary", "rounded-", "p-"):
        assert not _ENDS_WITH_COLOR_UTILITY.search(licit), (
            f"{licit!r} : faux positif"
        )

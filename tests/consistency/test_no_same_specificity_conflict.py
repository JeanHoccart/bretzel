"""Deux utilitaires Tailwind de même famille ne se disputent pas une racine.

``relative`` et ``fixed`` sont deux utilitaires de **même spécificité**
(0,1,0). Quand les deux atterrissent sur le même élément, le vainqueur
est le **dernier de la feuille compilée** — pas le dernier de l'attribut
``class``, pas celui qu'on a écrit en dernier dans le thème. L'ordre de
la feuille est décidé par Tailwind, pas par nous : le résultat n'est donc
pas contrôlable, seulement observable.

Pourquoi une gate, et pas quatre commentaires
----------------------------------------------
Le 2026-08-15, la même faute a frappé **quatre fois en une session**, à
chaque fois avec un symptôme différent et aucun lien apparent :

======================  ==========================================
conflit                 ce qu'on voyait
======================  ==========================================
``h-screen`` / ``h-full``   sidebar de 720px dans une boîte de 380,
                            footer hors cadre
``relative`` / ``fixed``    le mode ``overlay`` restait dans le flux
                            et ne se fermait pas
``z-40`` / ``z-50``         la sidebar passait SOUS son propre fond
                            assombri — tout devenait flou
======================  ==========================================

(La quatrième — une ligne de nav sans ``text-*``, donc héritant du
``text-base`` du navigateur — est une ABSENCE, pas un conflit : elle
n'est pas couverte ici.)

Trois occurrences, trois diagnostics repartis de zéro, trois heures. Le
symptôme ne ressemble jamais à la cause, et c'est précisément ce qui rend
la classe coûteuse : on cherche un bug de logique là où il y a un
arbitrage de cascade.

Ce que la gate lit
------------------
Elle **compose statiquement** ce que ``render()`` compose à l'exécution :
le slot ``root`` d'un thème, plus chaque entrée de chacune de ses tables
d'axe (``variants``, ``collapse``, ``widths``, ``sizes``, ``colors``…).
Un rendu par défaut ne verrait qu'UNE combinaison ; la lecture statique
les voit toutes, y compris celle qui n'est montée par aucun exemple —
ce qui est exactement le cas qui a mordu.

Le découpage par PRÉFIXE DE VARIANTE est ce qui rend la règle utilisable :
``hidden`` et ``md:flex`` ne se disputent rien (deux conditions
différentes, c'est l'idiome responsive), ``w-64`` et
``data-[open=false]:w-0`` non plus (c'est tout le mécanisme de repli).
Seules deux valeurs de la MÊME famille sous le MÊME préfixe s'affrontent.
"""

from __future__ import annotations

import ast
import re
from itertools import product

import pytest

from tests.consistency._discovery import ParsedSource, theme_sources

_THEMES = theme_sources()

#: Les familles retenues : celles dont deux valeurs sont franchement
#: EXCLUSIVES et n'ont aucun idiome de superposition légitime.
#:
#: Volontairement absentes : ``p-`` / ``m-`` (le couple raccourci + axe,
#: ``p-0 px-2``, est un idiome courant et voulu), les couleurs (``bg-`` et
#: ``bg-{bg_color}`` se superposent par variante), ``rounded-``. Les y
#: ajouter noierait la gate sous des faux positifs et on la débrancherait.
_FAMILIES: dict[str, re.Pattern[str]] = {
    "position": re.compile(r"^(static|relative|absolute|fixed|sticky)$"),
    "display": re.compile(
        r"^(block|inline-block|inline|flex|inline-flex|grid|inline-grid"
        r"|table|contents|hidden|flow-root)$"
    ),
    "z-index": re.compile(r"^z-(auto|\d+|\[.+\])$"),
    "height": re.compile(r"^h-(auto|full|screen|dvh|svh|lvh|min|max|fit|px|\d+(\.\d+)?|\[.+\])$"),
    "width": re.compile(r"^w-(auto|full|screen|min|max|fit|px|\d+(\.\d+)?|\[.+\])$"),
    "font-size": re.compile(r"^text-(xs|sm|base|lg|xl|\d?xl)$"),
    "font-weight": re.compile(
        r"^font-(thin|extralight|light|normal|medium|semibold|bold"
        r"|extrabold|black)$"
    ),
}

#: Un plancher de DÉCOUVERTE : combien de thèmes exposent un slot ``root``
#: composable. Si le lecteur cesse d'aboutir, la gate passerait au vert en
#: ne comparant rien — c'est arrivé DEUX fois en l'écrivant (les thèmes
#: sont des ``AnnAssign``, pas des ``Assign``), et c'est ce plancher qui
#: l'a dit les deux fois. Mesuré le 2026-08-15 : 66 thèmes, 280 paires
#: `root` × entrée d'axe effectivement comparées.
_ROOT_FLOOR = 40


def _split_variant(token: str) -> tuple[str, str]:
    """``"md:data-[open=false]:w-16"`` → ``("md:data-[open=false]:", "w-16")``.

    On coupe au DERNIER ``:`` hors crochets — un sélecteur arbitraire
    (``data-[open=false]:``) en contient, et couper au premier écraserait
    la variante qui distingue justement les deux règles.
    """
    depth = last = 0
    for i, ch in enumerate(token):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == ":" and depth == 0:
            last = i + 1
    return token[:last], token[last:]


def _family(utility: str) -> str | None:
    for name, pattern in _FAMILIES.items():
        if pattern.match(utility):
            return name
    return None


def _conflicts(classes: str) -> list[tuple[str, str, list[str]]]:
    """``(préfixe, famille, valeurs)`` pour chaque affrontement."""
    seen: dict[tuple[str, str], set[str]] = {}
    for token in classes.split():
        if not token or "{" in token:  # gabarit de couleur non résolu
            continue
        prefix, utility = _split_variant(token)
        family = _family(utility)
        if family is None:
            continue
        seen.setdefault((prefix, family), set()).add(utility)
    return [
        (prefix, family, sorted(values))
        for (prefix, family), values in seen.items()
        if len(values) > 1
    ]


def _root_and_axes(theme: ParsedSource) -> tuple[str, dict[str, str]] | None:
    """Le slot ``root`` d'un thème + les entrées de ses TABLES D'AXE.

    ⚠️ La structure compte, et une lecture à plat ne suffit pas. Un
    ``theme.py`` contient :

    - ``"slots"`` → un dict dont chaque entrée habille un élément
      DIFFÉRENT (``root``, ``label``, ``icon``, ``panel``…). Ces
      chaînes-là ne se rencontrent jamais.
    - à côté, des tables d'AXE (``variants``, ``collapse``, ``widths``,
      ``sizes``, ``colors``…) dont ``render()`` concatène UNE entrée avec
      ``root``. Ce sont elles, et elles seules, qui peuvent lui disputer
      un utilitaire.

    ``_discovery.theme_slot_strings`` aplatit tous les dicts et perd cette
    distinction : l'utiliser ici composait ``root`` avec ``panel``,
    ``label`` et le reste, et sortait 33 conflits imaginaires sur 67
    thèmes. D'où ce lecteur dédié, qui descend la structure.
    """
    for node in theme.tree.body:
        # ⚠️ ``AnnAssign`` autant que ``Assign``. Les thèmes du dépôt
        # s'écrivent TOUS ``X: dict[str, Any] = {...}``, donc ne tester
        # que ``Assign`` ne trouvait rien du tout — le plancher de
        # non-vacuité l'a signalé immédiatement, ce pour quoi il est là.
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        root: str | None = None
        axes: dict[str, str] = {}
        for key, value in zip(
            node.value.keys, node.value.values, strict=False
        ):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if not isinstance(value, ast.Dict):
                continue
            pairs = {
                k.value: v.value
                for k, v in zip(value.keys, value.values, strict=False)
                if isinstance(k, ast.Constant)
                and isinstance(v, ast.Constant)
                and isinstance(v.value, str)
            }
            if key.value == "slots":
                root = pairs.get("root")
            else:
                axes.update(
                    {f"{key.value}.{k}": v for k, v in pairs.items()}
                )
        if root is not None:
            return root, axes
    return None


_CASES = [
    (theme, pair) for theme in _THEMES if (pair := _root_and_axes(theme))
]


def test_root_sweep_is_not_vacuous() -> None:
    """Le lecteur de slot ``root`` doit RÉELLEMENT aboutir.

    Ancré sur la découverte, pas sur le nombre de fichiers : un thème
    reformaté ou un extracteur AST cassé ferait tomber la liste à zéro,
    et la gate deviendrait verte en ne comparant plus rien.
    """
    assert len(_CASES) >= _ROOT_FLOOR, (
        f"Seuls {len(_CASES)} thèmes exposent un slot ``root`` lisible "
        f"(plancher {_ROOT_FLOOR}). Le lecteur a cessé d'aboutir — la gate "
        f"ne compare plus rien."
    )


@pytest.mark.parametrize(
    "theme,pair", _CASES, ids=[t.path.parent.name for t, _ in _CASES]
)
def test_no_same_specificity_conflict(
    theme: ParsedSource, pair: tuple[str, dict[str, str]]
) -> None:
    root, axes = pair
    problems: list[str] = []

    for found in _conflicts(root):
        prefix, family, values = found
        problems.append(
            f"slot `root` seul : {values} ({family}, préfixe "
            f"{prefix or '<aucun>'!r})"
        )

    for (name, extra), _ in product(axes.items(), [None]):
        for prefix, family, values in _conflicts(f"{root} {extra}"):
            # Déjà signalé sur le root seul : ne pas le répéter N fois.
            if any(f"({family}, préfixe {prefix or '<aucun>'!r})" in p
                   for p in problems):
                continue
            problems.append(
                f"`root` composé avec `{name}` : {values} ({family}, "
                f"préfixe {prefix or '<aucun>'!r})"
            )

    assert not problems, (
        f"{theme.path.parent.name} : deux utilitaires de MÊME famille et MÊME "
        f"préfixe se disputent la racine.\n"
        + "".join(f"  - {p}\n" for p in problems)
        + "\nIls ont la même spécificité, donc le vainqueur est le dernier "
        "de la feuille Tailwind COMPILÉE — pas celui que tu as écrit en "
        "dernier. Le résultat n'est pas contrôlable, seulement observable, "
        "et le symptôme ne ressemble jamais à la cause (une sidebar 720px "
        "dans une boîte de 380, un panneau qui reste dans le flux, un "
        "élément flouté sous son propre voile — trois fois le même bug, "
        "trois diagnostics repartis de zéro).\n"
        "Correctif : sortir l'utilitaire du slot `root` et le poser dans "
        "la table d'axe, UNE valeur par entrée — c'est ce qu'on a fait "
        "pour `position` et `z-index` de la sidebar."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : deux utilitaires de MÊME famille et MÊME variante sont vus.

    C'est l'ordre de la FEUILLE Tailwind qui les départage, pas l'ordre
    du ``class=`` — donc la couleur rendue n'est pas celle que le thème
    croit choisir. Si le classifieur de famille cessait de reconnaître,
    l'interdiction passerait sur les 72 thèmes sans rien voir.
    """
    # Les familles retenues sont celles dont deux valeurs se contredisent
    # franchement — hauteur, largeur, display… pas la couleur.
    assert _conflicts("h-10 h-12"), "deux hauteurs nues devraient s'affronter"
    assert _conflicts("flex block"), "deux display nus devraient s'affronter"

    assert not _conflicts("h-10 md:h-12"), (
        "deux variantes DIFFÉRENTES ne s'affrontent pas — faux positif"
    )
    assert not _conflicts("h-10 text-sm"), (
        "deux familles différentes ne s'affrontent pas — faux positif"
    )

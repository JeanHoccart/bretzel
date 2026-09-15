"""Une zone appelée DANS une autre déclare au moins ce que l'autre déclare.

Le fait gardé
--------------
``render/partials.py`` ne réexpédie pas une zone qu'un fragment déjà
rendu contient : le drain appelle ``_zone_ids_inside(root, among=seen)``
et marque le résultat ``covered``. La zone imbriquée **voyage dans le
HTML de son conteneur**, et elle y voyage à chaque fois qu'il part —
quels que soient ses propres ``deps``.

D'où la règle, qui porte sur la DÉCLARATION et pas sur le placement :

    deps(conteneur) ⊆ deps(imbriquée)

Une zone qui déclare moins que son conteneur ment sur ses re-rendus.
Elle repart sur des états qu'elle n'a pas nommés, et rien ne le dit :
le HTML est correct, la page est juste, l'octet est payé.

Ce que ça a coûté, mesuré
--------------------------
``examples/ecole`` — `/plan/1`, le 2026-09-13. ``panneau_plan``
(``deps=[AnneeVue, VuePlan, PlanRev]``) appelait ``dialogue_trace``
(``[TraceDraft]``) et ``dialogue_contrainte`` (``[ContrainteDraft,
VuePlan]``). Vider une place renvoyait **248 ko**, dont **67 ko de
dialogues FERMÉS** — les deux avaient pourtant été sortis des ``deps``
du panneau pour que leur brouillon ne redessine plus la salle. Le
découplage ne joue que dans un sens : les SORTIR des ``deps`` empêche
le dialogue de redessiner la salle, les APPELER dedans fait repartir le
dialogue avec elle.

Le balayage a trouvé la même forme cinq fois de plus, dans quatre
fichiers que personne n'avait rapprochés : ``emploi_du_temps.grille``,
``reglages.bloc_annee``, ``reglages.bloc_periodes``,
``crm.activity_feed``, ``playground.events_panel``. Deux d'entre eux
déclaraient même le brouillon du dialogue imbriqué (``HoraireDraft``,
``PeriodeDraft``) sans jamais le lire — ouvrir le dialogue redessinait
le panneau entier.

Les deux remèdes, et comment on choisit
----------------------------------------
- **la sortir** — pour un overlay (dialogue, tiroir), qui ne tient pas
  sa place dans le flux : on l'appelle depuis la page. C'est le seul
  remède qui rende les octets ;
- **déclarer** — pour de l'UI en ligne, qui a sa place là où elle est
  (le formulaire de note au bas d'un fil, un journal de clics entre une
  table et son HTML). Rien ne change à l'exécution ; la déclaration
  cesse d'être fausse, et le prochain lecteur voit le coût.

Ce que cette gate ne voit PAS
------------------------------
L'imbrication est résolue **dans un seul fichier** : une zone qui en
appellerait une autre importée d'un module voisin échappe au balayage.
C'est délibéré et mesuré — résoudre par nom à travers le dépôt donnait
trois faux positifs immédiats (``tests/runtime_js/test_a_burst_of_
mutations_is_one_refetch.py`` a une aide locale ``_zone`` qui porte le
nom d'une zone d'ailleurs), et un faux positif sur une règle de
déclaration se paie en confiance. La forme réelle du défaut est
same-file — un panneau et son dialogue vivent dans la même feature.

Sont aussi hors de portée les appels indirects : une zone passée en
``partial``, rangée dans un dict, ou appelée par une fonction d'aide
qu'un conteneur appelle. Le détecteur lit un appel ``nom()`` dans le
corps, pas un flot de données.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    REPO_ROOT,
    parsed_sources,
)

#: Les racines qui DÉCLARENT des zones — mêmes que
#: ``test_a_zone_takes_no_parameter``, et pour la même raison :
#: ``bretzel/`` fournit le décorateur et ne s'en sert pas.
_ROOTS = (
    (REPO_ROOT / "examples", EXAMPLES_FLOOR),
    (REPO_ROOT / "tests", 200),
)

#: Combien de zones le lecteur AST doit voir. 328 au 2026-09-13 ; le
#: plancher borne, il ne fige pas.
_ZONES_FLOOR = 250

#: Combien d'IMBRICATIONS il doit encore reconnaître. Ce second
#: plancher n'est pas un doublon du premier : le balayage peut lire ses
#: 328 zones pendant que la BRANCHE qui cherche les appels imbriqués
#: rend zéro — et « aucune zone ne déclare moins que son conteneur » se
#: lit alors exactement comme « tout est propre ». C'est la pathologie
#: du 2026-08-24 (``test_framework_words_go_through_the_table``), et
#: elle guette toute gate qui code en dur un identifiant : ici
#: ``refreshable``, et le nom de la fonction appelée. 10 imbrications
#: licites au 2026-09-13, dont 6 dans ``tests/integration``.
_NESTINGS_FLOOR = 6


@dataclass(frozen=True)
class _Zone:
    node: ast.FunctionDef | ast.AsyncFunctionDef
    deps: frozenset[str]


@dataclass(frozen=True)
class _Nesting:
    path: Path
    lineno: int
    parent: str
    parent_deps: frozenset[str]
    child: str
    child_deps: frozenset[str]

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.lineno} "
            f"{self.parent}{sorted(self.parent_deps)} appelle "
            f"{self.child}{sorted(self.child_deps)} "
            f"— non déclaré : {sorted(self.parent_deps - self.child_deps)}"
        )


def _declared_deps(deco: ast.expr) -> frozenset[str]:
    """Les noms d'états dans ``deps=[...]``, vides pour un décorateur nu.

    ``broadcast=`` n'est pas lu : il désigne le canal SSE vers les
    AUTRES clients, pas le drain local — et c'est le drain local qui
    fait voyager une zone dans son conteneur.
    """
    if not isinstance(deco, ast.Call):
        return frozenset()
    for kw in deco.keywords:
        if kw.arg == "deps" and isinstance(kw.value, ast.List | ast.Tuple):
            return frozenset(
                getattr(e, "id", None) or getattr(e, "attr", None) or "?"
                for e in kw.value.elts
            )
    return frozenset()


def _zones_of(tree: ast.Module) -> dict[str, _Zone]:
    """Les zones d'un module, par nom.

    Reconnaît les deux écritures du décorateur (nu et appelé) et les
    deux accès (``refreshable`` / ``qqch.refreshable``), comme
    ``test_a_zone_takes_no_parameter`` — les deux lecteurs doivent voir
    la même population, sinon l'un des deux garde moins que l'autre.
    """
    found: dict[str, _Zone] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for deco in node.decorator_list:
            target = deco.func if isinstance(deco, ast.Call) else deco
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name == "refreshable":
                found[node.name] = _Zone(node, _declared_deps(deco))
                break
    return found


def _nestings_in(path: Path, tree: ast.Module) -> list[_Nesting]:
    """Chaque appel ``enfant()`` trouvé dans le corps d'une zone.

    La récursion (``zone()`` dans ``zone``) est écartée : elle n'est pas
    une imbrication de zones, et aucune n'existe dans le dépôt.
    """
    zones = _zones_of(tree)
    out: list[_Nesting] = []
    for nom, zone in zones.items():
        for call in ast.walk(zone.node):
            if not isinstance(call, ast.Call):
                continue
            cible = getattr(call.func, "id", None)
            if cible is None or cible == nom or cible not in zones:
                continue
            out.append(_Nesting(
                path=path, lineno=call.lineno, parent=nom,
                parent_deps=zone.deps, child=cible,
                child_deps=zones[cible].deps,
            ))
    return out


def _offenders_in(path: Path, tree: ast.Module) -> list[_Nesting]:
    """Le DÉTECTEUR, extrait pour être mutable."""
    return [n for n in _nestings_in(path, tree)
            if not n.parent_deps <= n.child_deps]


def _all_zones() -> dict[Path, dict[str, _Zone]]:
    return {
        source.path: _zones_of(source.tree)
        for root, floor in _ROOTS
        for source in parsed_sources(root, floor=floor)
    }


def _all_nestings() -> list[_Nesting]:
    return [
        nesting
        for root, floor in _ROOTS
        for source in parsed_sources(root, floor=floor)
        for nesting in _nestings_in(
            source.path.relative_to(REPO_ROOT), source.tree)
    ]


def test_the_zone_sweep_is_not_vacuous() -> None:
    """Le premier plancher : le lecteur voit-il encore des zones ?"""
    trouvees = sum(len(z) for z in _all_zones().values())
    assert trouvees >= _ZONES_FLOOR, (
        f"seulement {trouvees} zones ``@refreshable`` trouvées "
        f"(>= {_ZONES_FLOOR} attendues) — c'est ``_zones_of`` qui est "
        f"cassé, pas la population qui a fondu. Vérifie-le avant de "
        f"croire qu'aucune zone imbriquée ne sous-déclare."
    )


def test_the_detector_finds_the_real_nestings() -> None:
    """Le second plancher, et c'est LUI qui compte ici.

    Un balayage complet peut nourrir une branche vide : si
    ``_nestings_in`` cessait de reconnaître un appel, l'interdiction
    resterait verte en ne regardant rien.
    """
    nestings = _all_nestings()
    assert len(nestings) >= _NESTINGS_FLOOR, (
        f"seulement {len(nestings)} imbrications zone-dans-zone trouvées "
        f"(>= {_NESTINGS_FLOOR} attendues). Le dépôt en a des LICITES — "
        f"``tests/integration/test_a_nested_zone_ships_once.py`` en pose "
        f"six exprès. En trouver zéro veut dire que ``_nestings_in`` ne "
        f"reconnaît plus les appels, pas que plus personne n'imbrique."
    )


def test_no_nested_zone_declares_less_than_its_container() -> None:
    """L'interdiction."""
    fautifs = [
        str(n) for n in _all_nestings()
        if not n.parent_deps <= n.child_deps
    ]
    assert not fautifs, (
        "Ces zones sont appelées dans une autre et déclarent MOINS "
        "qu'elle :\n  " + "\n  ".join(fautifs) + "\n\n"
        "Une zone imbriquée voyage dans le HTML de son conteneur "
        "(`render/partials.py`, `_zone_ids_inside`), donc elle repart à "
        "chaque fois qu'il repart — y compris sur les états qu'elle n'a "
        "pas nommés. Deux remèdes :\n"
        "  • un OVERLAY (dialogue, tiroir) : appelle-le depuis la page "
        "plutôt que depuis la zone. C'est le seul qui rende les octets — "
        "67 ko par geste sur `ecole/plan` le 2026-09-13 ;\n"
        "  • de l'UI EN LIGNE, qui a sa place là où elle est : ajoute "
        "les `deps` du conteneur aux siens. Rien ne change à "
        "l'exécution, la déclaration cesse d'être fausse."
    )


@pytest.mark.parametrize(
    ("parent_deps", "child_deps", "forme"),
    [
        ("[A, B]", "[C]", "disjointes — le cas d'ecole/plan"),
        ("[A, B]", "[A]", "il en manque une"),
        ("[A]", "", "enfant impératif dans un conteneur déclaratif"),
    ],
)
def test_the_detector_bites_on_a_fabricated_nesting(
    parent_deps: str, child_deps: str, forme: str
) -> None:
    """Le versant ILLICITE, sur des modules fabriqués."""
    enfant = (f"@refreshable(deps={child_deps})" if child_deps
              else "@refreshable")
    tree = ast.parse(
        f"@refreshable(deps={parent_deps})\n"
        f"def conteneur():\n"
        f"    enfant()\n"
        f"\n"
        f"{enfant}\n"
        f"def enfant():\n"
        f"    pass\n"
    )
    fautifs = _offenders_in(Path("fabrique.py"), tree)
    assert len(fautifs) == 1, f"{forme} : {fautifs}"
    assert fautifs[0].parent == "conteneur", forme
    assert fautifs[0].child == "enfant", forme


@pytest.mark.parametrize(
    ("parent_deps", "child_deps", "forme"),
    [
        ("[A, B]", "[A, B]", "mêmes deps — l'enfant ne paie rien de plus"),
        ("[A]", "[A, B]", "l'enfant en déclare plus : le détail d'une liste"),
        ("", "[A]", "conteneur impératif : il ne repart sur aucun état"),
        ("", "", "les deux impératifs"),
    ],
)
def test_the_detector_spares_a_nesting_that_declares_enough(
    parent_deps: str, child_deps: str, forme: str
) -> None:
    """Le versant LICITE — celui qui mesure les faux positifs.

    C'est ce versant qui a trouvé les deux seuls bugs de gate du dépôt.
    Le troisième cas est le plus important : un conteneur SANS ``deps``
    ne repart sur aucun état, donc rien n'oblige son enfant à déclarer
    quoi que ce soit — une règle qui l'exigerait quand même
    interdirait la zone impérative, qui est une forme livrée.
    """
    parent = (f"@refreshable(deps={parent_deps})" if parent_deps
              else "@refreshable")
    enfant = (f"@refreshable(deps={child_deps})" if child_deps
              else "@refreshable")
    tree = ast.parse(
        f"{parent}\n"
        f"def conteneur():\n"
        f"    enfant()\n"
        f"\n"
        f"{enfant}\n"
        f"def enfant():\n"
        f"    pass\n"
    )
    assert not _offenders_in(Path("fabrique.py"), tree), forme


def test_the_reader_sees_both_spellings_of_the_decorator() -> None:
    """``@refreshable`` nu ET ``@x.refreshable`` — la FORME, pas le nom.

    Le détecteur code en dur un identifiant ; s'il ne connaissait qu'une
    orthographe, une moitié du dépôt sortirait du balayage sans que rien
    ne rougisse. Contrôle positif, sur les deux écritures réellement
    présentes dans le dépôt.
    """
    for source, forme in (
        ("@refreshable\ndef z(): pass\n", "nu"),
        ("@refreshable(deps=[A])\ndef z(): pass\n", "appelé"),
        ("@bretzel.refreshable(deps=[A])\ndef z(): pass\n", "qualifié"),
    ):
        assert "z" in _zones_of(ast.parse(source)), (
            f"``_zones_of`` ne reconnaît plus le décorateur {forme}"
        )


def test_the_drain_still_ships_a_nested_zone_inside_its_parent() -> None:
    """La RAISON de la règle, lue à la source.

    Si le drain se mettait à expédier une zone imbriquée séparément, un
    enfant cesserait de repartir avec son conteneur — et exiger qu'il
    déclare les ``deps`` de celui-ci deviendrait faux. On lit donc le
    mécanisme plutôt que de supposer qu'il n'a pas bougé, comme
    ``test_a_zone_takes_no_parameter`` lit l'appel nu.
    """
    chemin = REPO_ROOT / "bretzel" / "render" / "partials.py"
    arbre = ast.parse(chemin.read_text(encoding="utf-8-sig"))

    appels = [
        node for node in ast.walk(arbre)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "_zone_ids_inside"
    ]
    assert appels, (
        "``_zone_ids_inside`` n'est plus appelé dans render/partials.py. "
        "Soit le drain ne déduplique plus les zones imbriquées — et "
        "alors une zone enfant part DEUX fois, ce qui est un autre "
        "défaut — soit le mécanisme a changé de nom. Dans les deux cas, "
        "relis la règle avant de croire que cette gate garde encore "
        "quelque chose."
    )

    couvre = [
        node for node in ast.walk(arbre)
        if isinstance(node, ast.Attribute)
        and node.attr == "add"
        and getattr(node.value, "id", None) == "covered"
    ]
    assert couvre, (
        "plus rien n'alimente ``covered`` dans render/partials.py : le "
        "résultat de ``_zone_ids_inside`` ne sert plus à taire la zone "
        "imbriquée. C'est exactement l'hypothèse sur laquelle repose "
        "cette gate."
    )

"""Gate — ce qu'une app écrit n'atteint jamais l'INTÉRIEUR de Bretzel.

Le défaut qu'elle ferme (findings [2] et [22], 2026-08-23)
-----------------------------------------------------------
Deux frictions du CRM avaient la même forme, et une seule cause : **une
capacité existe, mais sa seule écriture possible viole l'anti-règle 1 du
charter.**

``Query`` — le type qu'un handler de datatable doit NOMMER pour écrire sa
signature — n'avait aucune porte publique. Ses jumeaux en avaient une
(``Move`` depuis ``bretzel.components``, ``DatatableState`` depuis
``bretzel``), lui non : **neuf** call-sites plongeaient dans
``bretzel.components.data.datatable.query``, dont six hors du framework.

``app.config._auth_key`` — la clé dérivée que la garde d'auth doit
vérifier — était un attribut **privé**, sur le chemin le plus sensible
d'une app. ``todo.md`` le notait dès le 2026-08-14 avec la prédiction
« tout le monde va le copier » ; le CRM, premier exemple à se connecter,
l'a copiée.

Les deux sont réparés. Ce que cette gate garde, c'est la **classe** — et
elle a payé avant d'être écrite : le balayage a trouvé **deux asymétries
de plus**, de la forme exacte de ``Query``. ``DEFAULT_PALETTE_NAMES``
n'avait pas de porte pendant que son voisin ``SEMANTIC_COLOR_NAMES`` en
avait une, et ``SANDBOX_BASELINE`` — la valeur par DÉFAUT de
``ui.iframe(sandbox=)`` — non plus.

L'invariant
-----------
Sous ``examples/`` (le corpus de « comment une app s'écrit »), aucun
fichier :

1. n'importe depuis un **sous-module** de ``bretzel``. Une porte publique
   est ``bretzel`` ou ``bretzel.<couche>`` — le ``__init__`` d'un module.
   Plus profond, c'est la plongée que l'anti-règle 1 interdit ;
2. ne lit un attribut **privé** sur quoi que ce soit d'autre que ``self``.

Une plongée n'est jamais la faute de l'exemple : c'est le signe qu'il
manque une porte. La gate rougit du côté de l'app, la correction est du
côté du framework.

Ce qu'elle n'affirme PAS
-------------------------
Que la porte soit bien PLACÉE, ni que le nom soit documenté (c'est
``test_docs_coverage``), ni que la surface soit classée (c'est
``test_public_surface_is_classified``, qui garde les noms DÉJÀ sur une
façade — le complément exact de celle-ci, qui attrape ceux qui n'y sont
pas du tout).

⚠️ Le balayage s'arrête à ``examples/``. ``tests/`` a le droit de plonger
— un test unitaire vise l'intérieur par construction — et le framework
aussi entre ses propres fichiers (l'anti-règle 1 autorise explicitement
les imports profonds à l'INTÉRIEUR d'un module).
"""

from __future__ import annotations

import ast
import pathlib

from tests.consistency._discovery import EXAMPLES_FLOOR, parsed_sources

_EXAMPLES = pathlib.Path(__file__).resolve().parents[2] / "examples"

#: Les portes publiques : le paquet, et le ``__init__`` de chaque couche.
#: Tout ce qui a un point de plus est un sous-module.
_DOORS = frozenset(
    {
        "bretzel",
        "bretzel.cli",
        "bretzel.components",
        "bretzel.core",
        "bretzel.introspect",
        "bretzel.lint",
        "bretzel.render",
        "bretzel.runtime",
        "bretzel.server",
        "bretzel.state",
        "bretzel.theme",
    }
)


#: **Les plongées DÉCLARÉES**, chacune avec sa raison. Une table nommée
#: et pas un plafond chiffré : « pas plus d'une » laisserait passer « une
#: qui sort, une qui rentre » (cf. ``gates.md`` § Rattraper est permis).
#:
#: Chaque entrée est une dette ouverte, pas une permission : si un
#: deuxième usager apparaît, c'est le signe qu'il faut une porte.
_DECLARED_DIVES: dict[str, str] = {
    # VIDE depuis le 2026-09-07, et c'est le bon état : aucune app
    # n'importe plus l'intérieur d'une couche. La seule entrée —
    # ``bretzel.components.base``, pour le paquet tiers d'exemple
    # ``ecosysteme`` — est partie avec l'app, dans l'élagage des
    # exemples. La question qu'elle portait (ouvrir ``Component`` et
    # ``reactive_prop`` en API publique d'auteur) n'a plus de demandeur ;
    # elle se reposera si un exemple en refait la demande.
}


def _is_a_dive(module: str) -> bool:
    """``module`` désigne-t-il l'intérieur d'une couche ?

    Extrait pour être mutable — c'est le détecteur, pas le balayage.
    Il ignore la table des déclarations : elle est appliquée par les
    tests, pour que ``test_the_declared_dives_are_still_real`` puisse
    voir ce qui n'y tombe PLUS.
    """
    if not (module == "bretzel" or module.startswith("bretzel.")):
        return False
    return module not in _DOORS


def _dived_modules() -> list[tuple[str, str]]:
    """``(fichier:ligne, module)`` pour chaque plongée, déclarée ou non."""
    found: list[tuple[str, str]] = []
    for src in parsed_sources(_EXAMPLES, floor=EXAMPLES_FLOOR):
        for node in ast.walk(src.tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                if node.module and _is_a_dive(node.module):
                    found.append((f"{src.path.name}:{node.lineno}", node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_a_dive(alias.name):
                        found.append((f"{src.path.name}:{node.lineno}", alias.name))
    return sorted(found)


def deep_imports() -> list[str]:
    """Les plongées NON déclarées — ce que la gate interdit."""
    return [
        f"{where} → {module}"
        for where, module in _dived_modules()
        if module not in _DECLARED_DIVES
    ]


def private_reads() -> list[str]:
    """Les ``x._nom`` sur autre chose que ``self``.

    ``self._x`` est l'idiome Python normal d'un objet sur lui-même ; ce
    qu'on interdit, c'est de lire l'intérieur d'un objet qu'on n'a pas
    écrit. Un exemple n'a que des objets du framework sous la main.
    """
    found: list[str] = []
    for src in parsed_sources(_EXAMPLES, floor=EXAMPLES_FLOOR):
        for node in ast.walk(src.tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not node.attr.startswith("_") or node.attr.startswith("__"):
                continue
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                continue
            found.append(f"{src.path.name}:{node.lineno} → .{node.attr}")
    return sorted(found)


def test_the_sweep_is_not_vacuous() -> None:
    """① Le plancher, lu sur LA découverte de cette gate."""
    seen = parsed_sources(_EXAMPLES, floor=EXAMPLES_FLOOR)
    assert len(seen) >= EXAMPLES_FLOOR, (
        f"seulement {len(seen)} fichiers d'exemple parsés : la gate "
        f"jugerait sur un échantillon et ne trouverait aucune plongée."
    )
    # Et qu'elle voit VRAIMENT des imports de bretzel — sinon un
    # ``parsed_sources`` qui rendrait des arbres vides passerait aussi.
    doors = sum(
        1
        for src in seen
        for node in ast.walk(src.tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] == "bretzel"
    )
    assert doors >= 100, (
        f"seulement {doors} imports de `bretzel` vus dans les exemples : "
        f"les arbres sont vides ou mal parsés."
    )


def test_no_example_dives_below_a_public_door() -> None:
    """② L'interdiction — l'app écrit ce que la façade expose."""
    offenders = deep_imports()
    assert not offenders, (
        "un exemple importe depuis l'intérieur d'une couche :\n  "
        + "\n  ".join(offenders)
        + "\n\nCe n'est PAS la faute de l'exemple — c'est qu'il manque une "
        "porte. Exporte le nom depuis le `__init__` de sa couche (comme "
        "`Query` et `apply_query` le 2026-08-23), puis réécris l'import. "
        "Si le nom n'a rien à faire dans une app, c'est l'exemple qu'il "
        "faut corriger."
    )


def test_the_declared_dives_are_still_real() -> None:
    """La table ne pourrit pas — elle refuse les DEUX écarts.

    Une entrée qui ne correspond plus à rien fait croire à une dette
    qu'on a déjà payée, et la prochaine plongée vers le même module
    passerait sous son couvert.
    """
    dived = {module for _, module in _dived_modules()}
    stale = sorted(set(_DECLARED_DIVES) - dived)
    assert not stale, (
        f"la table déclare des plongées qui n'existent plus : {stale}. "
        f"Retire l'entrée — sinon elle couvrira la prochaine."
    )


def test_no_example_reads_a_private_attribute() -> None:
    """② bis — et surtout pas sur le chemin de la sécurité."""
    offenders = private_reads()
    assert not offenders, (
        "un exemple lit un attribut privé du framework :\n  "
        + "\n  ".join(offenders)
        + "\n\nC'est la forme qu'avait `app.config._auth_key` avant que "
        "`auth.user_id` existe. Si une app a besoin de la "
        "valeur, elle a besoin d'une fonction publique qui la lit pour elle."
    )


def test_the_detector_still_bites() -> None:
    """③ La mutation, dans les DEUX sens.

    Le versant licite compte autant : un détecteur qui refuserait
    ``bretzel.components`` rendrait la gate rouge sur tout le corpus, et
    on la débrancherait au lieu de la lire.
    """
    # Ce qui DOIT mordre — les quatre plongées réellement rencontrées.
    for dive in (
        "bretzel.components.data.datatable.query",
        "bretzel.theme.tokens",
        "bretzel.state.scopes.client",
        "bretzel.components.primitives.iframe",
    ):
        assert _is_a_dive(dive), f"{dive} devrait être vu comme une plongée"

    # Ce qui doit être ÉPARGNÉ — les portes, et tout ce qui n'est pas nous.
    for door in (
        "bretzel",
        "bretzel.components",
        "bretzel.state",
        "bretzel.theme",
        "bretzel.render",
        "bretzel.server",
    ):
        assert not _is_a_dive(door), f"{door} EST une porte publique"
    for foreign in (
        "fastapi.testclient",
        "examples.crm.core.db",
        "sqlite3",
        "bretzelade.truc",
    ):
        assert not _is_a_dive(foreign), f"{foreign} n'est pas de nous"

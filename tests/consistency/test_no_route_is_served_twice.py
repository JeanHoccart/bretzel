"""Gate : dans une app, deux pages ne servent jamais la même route.

Ce qu'elle garde
-----------------
``@page`` MARQUE la fonction ; l'enregistrement arrive dans
``app.include(...)``. Rien, dans cette chaîne, ne refuse deux marques
sur le même chemin : la seconde écrase la première, et **c'est l'ordre
des arguments d'``include`` qui décide** laquelle gagne. Cet ordre n'est
écrit nulle part et ne se voit sur aucune page — les deux rendent 200.

Mesuré le 2026-09-03 dans ``examples/docs`` : **trois routes étaient
servies deux fois** (``/browser``, ``/capabilities``, ``/tree``), une
vraie page et un stub généré, parce que la liste des chapitres livrés
était recopiée à la main à côté de la vérité. Aucune suite ne l'a vu ;
c'est en refondant la navigation que c'est sorti.

Pourquoi par app et pas globalement
------------------------------------
``/`` existe dans les 21 exemples, et c'est normal : chaque app a son
accueil. Le conflit n'a de sens qu'À L'INTÉRIEUR d'une app.

Les DEUX façons de monter une page, et il faut les deux
--------------------------------------------------------
1. **Le décorateur**, dans la feature : ``@page("/how")`` ou
   ``@page(PATH, layout=shell)``. C'est ce que fait ``examples/docs``.
2. **L'appel direct**, dans une liste centrale :
   ``page(feat.PATH, layout=shell)(feat.page)``. C'est ce que fait
   ``examples/playground`` — la plus grosse app du dépôt, avec ses
   ``PAGES`` dans ``app/routes.py``.

⚠️ La première version de cette gate ne lisait que les décorateurs. Elle
rendait donc **zéro route pour le playground** et serait restée verte en
ne regardant rien — alors qu'une liste centrale est justement l'endroit
où deux lignes pour le même ``PATH`` passent inaperçues.

Lu à l'AST, donc sans monter les 21 apps — et une app qui casserait à
l'import resterait vérifiée.
"""

from __future__ import annotations

import ast
import collections
import pathlib

from tests.consistency._discovery import ParsedSource, parsed_sources

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"

#: Preuve de morsure : contrôle POSITIF — le lecteur voit encore des
#: routes, et sait distinguer une route écrite d'une route citée.
MUTATION_PROOF = "test_the_route_sweep_finds_code_not_prose"

#: Le nombre de routes vues au gel, toutes apps et toutes formes
#: confondues. Plancher : un lecteur cassé rendrait zéro conflit en ne
#: regardant rien.
_ROUTES_AT_FREEZE = 143

#: Le nombre de fichiers ``.py`` sous ``examples/`` au gel. Passé à
#: ``parsed_sources``, qui LÈVE sur un fichier illisible au lieu de le
#: laisser sortir du balayage sans un mot.
_FILES_AT_FREEZE = 150

#: Les ``@page`` que le lecteur ne sait PAS résoudre, et qu'il ne faut
#: donc pas avaler en silence : deux ``@page(LOGIN_PATH)`` dont la
#: constante est IMPORTÉE d'un autre module. La résoudre demanderait
#: d'importer, ce que cette gate refuse de faire (une app cassée doit
#: rester vérifiée).
#:
#: **Cliquet : ce nombre ne remonte pas.** Une troisième forme non
#: résolue serait un trou dans le balayage, pas un détail.
_UNRESOLVED_AT_FREEZE = 2


def _sources() -> list[ParsedSource]:
    """Tous les ``.py`` d'``examples/``, lus et parsés — sans exception.

    ⚠️ Le lecteur PARTAGÉ, et c'est le point : il lit en ``utf-8-sig``
    et LÈVE sur un fichier illisible. Ma première version attrapait
    ``SyntaxError`` et rendait une liste vide, donc un fichier cassé
    sortait du balayage sans un mot — la maladie exacte qui a caché
    ``bretzel/render/__init__.py`` à sept gates pendant des mois.
    """
    return parsed_sources(EXAMPLES, floor=_FILES_AT_FREEZE)


def _app_de(source: ParsedSource) -> str:
    return source.path.relative_to(EXAMPLES).parts[0]


def _routes_decorees(source: ParsedSource) -> list[tuple[str, str]]:
    """Les routes montées par DÉCORATEUR — la forme d'``examples/docs``.

    Deux écritures : ``@page("/how")`` en littéral, et ``@page(PATH, …)``
    où ``PATH`` est une constante du module.

    ⚠️ On lit les DÉCORATEURS, pas le texte. Un ``'@page("/tarifs")'``
    écrit dans une chaîne — l'exemple pédagogique de
    ``examples/docs/features/structure.py`` — n'est pas une route, et un
    lecteur au motif textuel le prenait pour telle.
    """
    constantes: dict[str, str] = {}
    for noeud in source.tree.body:
        if isinstance(noeud, ast.Assign) and isinstance(noeud.value, ast.Constant):
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and isinstance(noeud.value.value, str):
                    constantes[cible.id] = noeud.value.value

    trouvees: list[tuple[str, str]] = []
    for noeud in ast.walk(source.tree):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            if not (isinstance(deco, ast.Call)
                    and isinstance(deco.func, ast.Name)
                    and deco.func.id == "page"
                    and deco.args):
                continue
            premier = deco.args[0]
            if isinstance(premier, ast.Constant) and isinstance(premier.value, str):
                trouvees.append((premier.value, noeud.name))
            elif isinstance(premier, ast.Name) and premier.id in constantes:
                trouvees.append((constantes[premier.id], noeud.name))
    return trouvees


def _paths_par_module() -> dict[tuple[str, str], str]:
    """``(app, nom de fichier sans .py)`` → sa constante ``PATH``.

    Sert à résoudre ``page(button.PATH, …)`` écrit dans une liste
    centrale : l'AST voit un accès d'attribut sur un module importé, et
    la valeur vit dans l'autre fichier. La clé porte l'app pour que deux
    apps puissent avoir chacune leur ``home.PATH``.
    """
    table: dict[tuple[str, str], str] = {}
    for source in _sources():
        for noeud in source.tree.body:
            if (isinstance(noeud, ast.Assign)
                    and isinstance(noeud.value, ast.Constant)
                    and isinstance(noeud.value.value, str)):
                for cible in noeud.targets:
                    if isinstance(cible, ast.Name) and cible.id == "PATH":
                        table[(_app_de(source), source.path.stem)] = noeud.value.value
    return table


def _routes_appelees(source: ParsedSource,
                     paths: dict[tuple[str, str], str]) -> list[tuple[str, str]]:
    """Les routes montées par APPEL direct — ``page(x.PATH, …)(x.page)``.

    La forme du playground. On ne résout que ``<module>.PATH``, qui est
    la convention du dépôt ; tout autre argument reste non résolu et
    tombe dans le cliquet anti-avalement.
    """
    app = _app_de(source)
    trouvees: list[tuple[str, str]] = []
    for noeud in ast.walk(source.tree):
        if not (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Call)
                and isinstance(noeud.func.func, ast.Name)
                and noeud.func.func.id == "page"
                and noeud.func.args):
            continue
        premier = noeud.func.args[0]
        if (isinstance(premier, ast.Attribute) and premier.attr == "PATH"
                and isinstance(premier.value, ast.Name)):
            route = paths.get((app, premier.value.id))
            if route is not None:
                trouvees.append((route, f"{premier.value.id}.page"))
    return trouvees


def _par_app() -> dict[str, list[tuple[str, str, str]]]:
    """``app`` → ``[(route, fichier, fonction)]``, les deux formes."""
    paths = _paths_par_module()
    out: dict[str, list[tuple[str, str, str]]] = collections.defaultdict(list)
    for source in _sources():
        app = _app_de(source)
        for route, fonction in _routes_decorees(source):
            out[app].append((route, source.path.name, fonction))
        for route, fonction in _routes_appelees(source, paths):
            out[app].append((route, source.path.name, fonction))
    return dict(out)


def _decorateurs_non_resolus() -> list[str]:
    """Les ``@page`` que le lecteur voit sans pouvoir en tirer la route.

    Un balayage qui saute quelque chose DOIT le dire : c'est la
    différence entre « aucun conflit » et « je n'ai pas regardé ».
    """
    orphelins: list[str] = []
    for source in _sources():
        resolus = {fonction for _route, fonction in _routes_decorees(source)}
        for noeud in ast.walk(source.tree):
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in noeud.decorator_list:
                if (isinstance(deco, ast.Call)
                        and isinstance(deco.func, ast.Name)
                        and deco.func.id == "page"
                        and noeud.name not in resolus):
                    orphelins.append(
                        f"{source.path.relative_to(EXAMPLES)}:{noeud.name}"
                    )
    return sorted(orphelins)


def test_the_route_sweep_finds_code_not_prose() -> None:
    """Plancher de non-vacuité, ancré sur la DÉCOUVERTE de cette gate.

    Sans lui, un lecteur qui rendrait zéro route ferait passer
    l'interdiction au vert en ne regardant rien. Et le versant LICITE —
    la route citée dans une chaîne — est celui qui attrape un lecteur
    trop gourmand, c'est-à-dire le bug corrigé une heure plus tôt dans
    la gate voisine.
    """
    apps = _par_app()
    total = sum(len(v) for v in apps.values())
    assert total >= _ROUTES_AT_FREEZE // 2, (
        f"seulement {total} routes lues dans examples/ contre "
        f"{_ROUTES_AT_FREEZE} au gel — le lecteur AST est probablement "
        f"cassé."
    )
    assert "docs" in apps and "playground" in apps, (
        f"les DEUX formes doivent être vues : ``examples/docs`` décore, "
        f"``examples/playground`` monte par appel. Vues : {sorted(apps)}"
    )
    # Le versant licite : ``structure.py`` CITE ``@page("/tarifs")`` dans
    # une chaîne pédagogique. Ce n'est pas une route, et la confondre
    # avec une vraie est exactement l'erreur qu'un lecteur textuel fait.
    routes_docs = {r for r, _f, _fn in apps["docs"]}
    assert "/tarifs" not in routes_docs, (
        "``/tarifs`` n'est PAS une route : c'est un exemple écrit dans "
        "une chaîne de `examples/docs/features/structure.py`. Le lecteur "
        "lit du texte au lieu de lire du code."
    )


def test_no_page_decorator_is_swallowed() -> None:
    """Ce que le lecteur ne sait pas lire est COMPTÉ, pas ignoré."""
    orphelins = _decorateurs_non_resolus()
    assert len(orphelins) <= _UNRESOLVED_AT_FREEZE, (
        f"{len(orphelins)} décorateurs ``@page`` non résolus, contre "
        f"{_UNRESOLVED_AT_FREEZE} au gel :\n  "
        + "\n  ".join(orphelins)
        + "\n  Une forme d'écriture neuve n'est pas un détail : c'est "
        "un trou dans le balayage, donc un conflit de route qui "
        "passerait inaperçu. Étends ``_routes_decorees``."
    )


def test_no_route_is_served_twice() -> None:
    """Deux ``@page`` sur le même chemin, dans la même app."""
    conflits: list[str] = []
    for app, entrees in sorted(_par_app().items()):
        compte = collections.Counter(route for route, _f, _fn in entrees)
        for route, n in sorted(compte.items()):
            if n > 1:
                qui = ", ".join(
                    f"{f}:{fn}" for r, f, fn in entrees if r == route
                )
                conflits.append(f"{app} → {route} servie {n}× ({qui})")
    assert not conflits, (
        "route(s) servie(s) plusieurs fois dans la même app :\n  "
        + "\n  ".join(conflits)
        + "\n  Rien ne refuse deux marques sur le même chemin : la "
        "seconde écrase la première, et c'est l'ORDRE des arguments "
        "d'``app.include`` qui décide — un classement écrit nulle part, "
        "et invisible puisque les deux rendent 200."
    )

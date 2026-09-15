"""Règle : une zone qui écoute pour le compte d'une zone IMBRIQUÉE.

Le silence qu'elle ferme
------------------------

Rien ne casse, et c'est pire qu'une panne : **ça marche, dix fois trop
cher**. ::

    @refreshable(deps=[TraceDraft])
    def dialogue_trace() -> None:        # lit TraceDraft : c'est sa vie
        ...

    @refreshable(deps=[VuePlan, PlanRev, TraceDraft])
    def panneau_plan() -> None:
        ...                              # ne lit jamais TraceDraft
        dialogue_trace()                 # …mais appelle celui qui le lit

``TraceDraft`` est le brouillon d'un dialogue, et le dialogue est **déjà
une zone** : il se rafraîchit tout seul. Le déclarer chez la parente veut
dire *« quand on ouvre le dialogue, redessine tout le panneau »*.

Mesuré sur ``examples/ecole`` le 2026-09-12 : ouvrir « Tracer la salle »
— mettre un booléen à vrai — coûtait **679 ms et 15 451 octets**, parce
que la réponse contenait la salle entière, toutes les places, toutes les
vignettes de glisser et la liste d'attente. Sans la dépendance de trop :
**20 ms et 3 094 octets**. Trente fois moins, pour le même écran.

Ce qui rend la faute facile à commettre : le dialogue est ÉCRIT dans le
corps de la zone parente, donc déclarer sa dépendance au même endroit
paraît cohérent. La forme ne rappelle pas que l'enfant est autonome.

Ce que la règle exige — les TROIS conditions
----------------------------------------------

1. la zone déclare ``X`` dans ses ``deps=`` ;
2. **son corps ne lit jamais ``X``**, ni directement ni par un helper
   ordinaire du module (le balayage suit les appels) ;
3. **une zone qu'elle APPELLE lit ``X``**.

⚠️ **La troisième condition n'est pas un raffinement, c'est la règle.**
Sans elle, le constat tombe sur le patron le plus courant du dépôt : un
JETON DE RÉVISION. Une écriture en base ne touche aucun état typé, donc
rien ne se rafraîchit ; le remède documenté est un ``AppState`` compteur
(``ContactsRev``, ``PlanRev``) qu'on incrémente à l'écriture et qu'on
déclare en dépendance — **et que personne ne lit, jamais**. Mesuré sur
``examples/`` : la version « déclaré et non lu » rendait une trentaine de
constats, et ils étaient tous ce patron-là. Une règle qui condamne
l'idiome recommandé ne mesure pas ce qu'elle croit.

⚠️ Ce que la règle ne dit PAS
------------------------------

Qu'une zone parente ne doive jamais partager une dépendance avec son
enfant. Si elle la LIT aussi, les deux ont raison — c'est la condition 2
qui tranche, et elle se lit sur le code.

Elle ne voit pas au-delà du module : une zone imbriquée importée
d'ailleurs n'est pas reconnue comme zone, donc le cas est silencieux
plutôt que faux.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

#: Le nom de la règle, tel qu'il s'affiche dans un constat.
RULE = "zone-qui-ecoute-trop"

_MARKS = frozenset({"refreshable"})

_Func = ast.FunctionDef | ast.AsyncFunctionDef


def _decorator_call(func: _Func) -> ast.Call | None:
    for deco in func.decorator_list:
        if not isinstance(deco, ast.Call):
            continue
        target = deco.func
        name = (
            target.attr
            if isinstance(target, ast.Attribute)
            else target.id
            if isinstance(target, ast.Name)
            else None
        )
        if name in _MARKS:
            return deco
    return None


def _declared_deps(call: ast.Call) -> list[ast.Name]:
    for kw in call.keywords:
        if kw.arg == "deps" and isinstance(kw.value, ast.List | ast.Tuple):
            return [e for e in kw.value.elts if isinstance(e, ast.Name)]
    return []


def _names_read(func: _Func) -> set[str]:
    """Les noms lus dans le CORPS — décorateurs exclus.

    ⚠️ ``ast.walk`` sur la fonction descend aussi dans sa liste de
    décorateurs, donc chaque nom de ``deps=[…]`` s'y retrouverait lu par
    lui-même et la règle serait muette sur 100 % des cas. Mesuré : elle
    l'était, sur son propre cas d'école.
    """
    return {
        n.id
        for stmt in func.body
        for n in ast.walk(stmt)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }


def _reachable(
    start: _Func, functions: dict[str, _Func], zones: frozenset[str]
) -> tuple[set[str], set[str]]:
    """``(noms lus, zones appelées)`` depuis ``start``.

    Le parcours suit les helpers ordinaires et **s'arrête aux zones** —
    ce qu'une zone imbriquée lit lui appartient. Les zones rencontrées
    sont rendues à part : ce sont elles qui décident du constat.
    """
    lus: set[str] = set()
    enfants: set[str] = set()
    a_faire = [start]
    vues = {start.name}
    while a_faire:
        courante = a_faire.pop()
        noms = _names_read(courante)
        lus |= noms
        for nom in noms:
            if nom in zones and nom != start.name:
                enfants.add(nom)
                continue
            suivante = functions.get(nom)
            if suivante is None or nom in vues:
                continue
            vues.add(nom)
            a_faire.append(suivante)
    return lus, enfants


def check(module: Module) -> list[Finding]:
    """Les dépendances qu'une zone porte pour le compte d'une autre."""
    functions: dict[str, _Func] = {}
    zones: set[str] = set()
    for node in ast.walk(module.tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions[node.name] = node
            if _decorator_call(node) is not None:
                zones.add(node.name)

    gelees = frozenset(zones)
    portee = {nom: _reachable(functions[nom], functions, gelees) for nom in gelees}

    findings: list[Finding] = []
    for nom in sorted(gelees):
        deco = _decorator_call(functions[nom])
        if deco is None:  # pragma: no cover — `zones` le garantit
            continue
        lus, enfants = portee[nom]
        for dep in _declared_deps(deco):
            if dep.id in lus:
                continue
            porteurs = sorted(e for e in enfants if dep.id in portee[e][0])
            if not porteurs:
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=dep.lineno,
                    message=(
                        f"`{nom}` déclare `{dep.id}` sans jamais le lire, "
                        f"pour le compte de `{porteurs[0]}()` — qui est une "
                        f"zone et le déclare déjà."
                    ),
                    hint=(
                        "Une zone imbriquée se rafraîchit toute seule : la "
                        "parente n'a besoin de suivre que l'EFFET, par un "
                        "jeton de révision. La dépendance de trop ne LÈVE "
                        "pas et ne s'affiche pas — elle rend la zone "
                        "entière à chaque frappe dans l'enfant (mesuré : "
                        "679 ms et 15 ko au lieu de 20 ms et 3 ko). "
                        f"Retire `{dep.id}` des `deps=` de `{nom}`."
                    ),
                )
            )
    return findings

"""Règle : un total d'``AppState`` incrémenté sans être déclaré additif.

Le silence qu'elle ferme
------------------------

``stats.vues += 1`` lit 5, calcule 6, et le commit envoie « mets 6 ».
Deux requêtes qui ont lu 5 envoient toutes les deux « mets 6 » : il en
manque un. Déclarer ``field(default=0, merge="add")`` fait envoyer
l'ÉCART, que le magasin applique lui-même — et les deux comptent.

Rien ne signale l'oubli. Mesuré le 2026-09-04 : seul devant son écran,
un développeur ne le rencontre JAMAIS, parce que ses requêtes sont
séquentielles — chacune lit ce que la précédente a écrite. Il faut deux
onglets qui cliquent ensemble, ou deux utilisateurs. La faute attend
donc la production, et là elle ne lève pas non plus : un compteur
avance simplement moins vite que les clics.

Pourquoi ``AppState`` SEULEMENT
--------------------------------

Parce que ``+=`` ne veut pas dire « total ». ``state.page += 1`` est un
CHOIX — « la page suivante » —, et le déclarer additif produirait la
page 7 quand deux onglets vont à la 3 et à la 5. Le signal n'est donc
pas l'opérateur, c'est le **partage** : un ``AppState`` est unique pour
tout le processus, donc un nombre qu'on y incrémente est un compte
collectif, jamais la position de quelqu'un.

Les autres portées sont volontairement HORS de la règle, et ce n'est pas
qu'elles soient à l'abri :

- ``SessionState`` et ``UserState`` sont partagés entre les onglets d'un
  même navigateur, donc la perte y est réelle — mais un « + 1 » y est
  aussi souvent une pagination ou un réglage qu'un total, et signaler
  les deux ferait du bruit là où la règle doit faire du signal ;
- ``PageState`` ne vit que le temps d'un rendu ; deux clics rapides sur
  la même page peuvent se chevaucher, mais ce qu'on y perd meurt avec
  l'onglet.

Mesuré sur ``examples/`` le 2026-09-05 : 45 incréments sur un
``AppState``, 4 sur une session, 2 sur une page. La portée qui compte
est aussi celle où le motif est le plus fréquent.

Ce que la règle ne peut pas voir
---------------------------------

Un état passé en ARGUMENT (``def bump(s: Stats): s.vues += 1``) : il
faudrait un vrai flot de données. Le détecteur remonte d'un cran — il
connaît les constructions directes (``Stats().vues += 1``) et les
variables locales assignées depuis un état (``s = Stats()``), ce qui
couvre les deux orthographes du dépôt. Le dire ici plutôt que laisser
croire à l'exhaustivité.

La règle est **pure** : un module, des constats. Elle ne connaît ni
corpus, ni plancher.
"""

from __future__ import annotations

import ast
from functools import lru_cache

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "compteur-partage-non-declare"

#: Les opérations qui ACCUMULENT. ``*=`` et le reste n'en sont pas : leur
#: écart dépend de la valeur lue, donc l'additivité ne les sauverait pas.
_ACCUMULATORS = (ast.Add, ast.Sub)


@lru_cache(maxsize=1)
def _app_state_names() -> frozenset[str]:
    """Les classes ``AppState`` publiques, dérivées et non recopiées.

    Une table de noms écrite à la main dérive du code qu'elle juge —
    c'est la règle du dossier.
    """
    import inspect

    import bretzel
    import bretzel.state as state_module
    from bretzel.state.scopes.server import ServerState

    names = set()
    for module in (bretzel, state_module):
        for name in dir(module):
            obj = getattr(module, name, None)
            if (
                inspect.isclass(obj)
                and issubclass(obj, ServerState)
                and getattr(obj, "__scope__", None) == "app"
            ):
                names.add(name)
    return frozenset(names)


def _base_names(node: ast.ClassDef) -> set[str]:
    """Les noms de base écrits, ``module.Classe`` réduit à ``Classe``."""
    names: set[str] = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _local_app_states(tree: ast.Module) -> dict[str, dict[str, ast.expr | None]]:
    """``{classe d'app: {champ: la valeur de sa déclaration}}``.

    On garde la déclaration entière et pas seulement le nom : c'est elle
    qui dira si ``merge="add"`` est déjà là. Les classes sont lues dans
    l'ordre du fichier, donc une base locale est connue avant ses filles.
    """
    connues = _app_state_names()
    etats: dict[str, dict[str, ast.expr | None]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not (_base_names(node) & (connues | set(etats))):
            continue
        champs: dict[str, ast.expr | None] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                champs[stmt.target.id] = stmt.value
        etats[node.name] = champs
    return etats


def _declares_add(valeur: ast.expr | None) -> bool:
    """La déclaration porte-t-elle ``merge="add"`` ?"""
    if not isinstance(valeur, ast.Call):
        return False
    return any(
        kw.arg == "merge"
        and isinstance(kw.value, ast.Constant)
        and kw.value.value == "add"
        for kw in valeur.keywords
    )


def _state_of(cible: ast.Attribute, locales: dict[str, str]) -> str | None:
    """La classe d'état derrière ``X.champ``, ou ``None``.

    Deux orthographes, et ce sont celles du dépôt :
    ``Stats().vues`` (construction directe) et ``s.vues`` où ``s`` vient
    d'un ``s = Stats()`` plus haut dans la même fonction.
    """
    porteur = cible.value
    if isinstance(porteur, ast.Call) and isinstance(porteur.func, ast.Name):
        return porteur.func.id
    if isinstance(porteur, ast.Name):
        return locales.get(porteur.id)
    return None


def _locals_bound_to_a_state(func: ast.AST, connues: set[str]) -> dict[str, str]:
    """``{nom local: classe d'état}`` pour les ``s = Stats()`` de la fonction."""
    lies: dict[str, str] = {}
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        cible, valeur = node.targets[0], node.value
        if not isinstance(cible, ast.Name):
            continue
        if isinstance(valeur, ast.Call) and isinstance(valeur.func, ast.Name):
            if valeur.func.id in connues:
                lies[cible.id] = valeur.func.id
        # ``await Stats.load()`` — l'autre porte d'entrée
        elif isinstance(valeur, ast.Await) and isinstance(valeur.value, ast.Call):
            appel = valeur.value
            if (
                isinstance(appel.func, ast.Attribute)
                and appel.func.attr == "load"
                and isinstance(appel.func.value, ast.Name)
                and appel.func.value.id in connues
            ):
                lies[cible.id] = appel.func.value.id
    return lies


def check(module: Module) -> list[Finding]:
    """Les totaux d'``AppState`` incrémentés sans déclaration additive."""
    etats = _local_app_states(module.tree)
    if not etats:
        return []
    connues = set(etats)

    findings: list[Finding] = []
    for func in ast.walk(module.tree):
        if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        locales = _locals_bound_to_a_state(func, connues)
        for node in ast.walk(func):
            if not isinstance(node, ast.AugAssign):
                continue
            if not isinstance(node.op, _ACCUMULATORS):
                continue
            if not isinstance(node.target, ast.Attribute):
                continue
            classe = _state_of(node.target, locales)
            if classe not in etats:
                continue
            champ = node.target.attr
            if champ not in etats[classe]:
                continue
            if _declares_add(etats[classe][champ]):
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=(
                        f"`{classe}.{champ}` est incrémenté en place, et "
                        f"`{classe}` est un `AppState` — donc UN objet pour "
                        f"tout le serveur. Le champ n'est pas déclaré "
                        f"additif : deux requêtes qui lisent le même nombre "
                        f"écrivent le même nombre, et un incrément se perd."
                    ),
                    hint=(
                        f"Déclare `{champ}: … = field(default=0, "
                        f'merge="add")`. Le commit enverra l\'ÉCART, que le '
                        f"magasin applique lui-même — deux clics simultanés "
                        f"compteront tous les deux. Si ce nombre n'est PAS "
                        f"un total mais une position ou un réglage, laisse-le "
                        f"tel quel : le dernier qui écrit a alors raison."
                    ),
                )
            )
    return findings

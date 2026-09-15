"""Règle : un `ServerState` construit dans un corps ``async def``.

Le silence qu'elle ferme, et il n'est silencieux QU'EN DEV
----------------------------------------------------------

``MonEtat()`` est un constructeur : il ne peut pas attendre. Quand le
backend se lit aussi en synchrone — c'est le cas de ``MemoryBackend``,
donc de toute app lancée sans ``redis_url`` — l'hydratation se fait sur
place et tout marche. Quand il ne lit qu'en ``await`` (Redis), le
registre passe par un thread du pool… et un corps ``async def`` ne
tourne PAS dans ce thread, il tourne sur la boucle, où attendre gèlerait
le worker entier. ``StateRegistry`` lève donc
:class:`~bretzel.state.StateHydrationError` plutôt que de rendre des
valeurs par défaut que le commit de fin de requête écraserait
par-dessus les vraies.

Conséquence : **la même ligne marche en dev et lève en prod**, le jour
où quelqu'un pose ``redis_url``. C'est la classe de panne la plus chère
de ce dépôt — celle qui attend le déploiement pour se montrer, comme la
classe Tailwind assemblée (``rules/tailwind.py``). D'où une règle
statique : elle rend le verdict en dev, sans backend, sans exécuter
quoi que ce soit.

Le geste correct est écrit dans le message : ``etat = await
MonEtat.load()``, ou repasser le corps en ``def`` — le framework le
délestera sur un thread, où ``MonEtat()`` marche tel quel.

⚠️ Ce que cette règle ne voit PAS
----------------------------------

Elle lit **un** module et suit la LEXIQUE, pas les appels. Une
construction rangée dans un helper synchrone appelé depuis l'``async
def`` lui échappe entièrement — et c'est le cas réel qui a motivé la
règle : ``examples/crm/features/import_screen.py`` fait
``judge(rows, visible_owner())`` dans un handler ``async``, et c'est
``visible_owner()``, dans un AUTRE fichier, qui construit l'état.
Suivre ça demanderait un graphe d'appels inter-modules, que le corpus de
``bretzel.lint`` ne construit pas (une règle voit un
:class:`~bretzel.lint.corpus.Module`, un seul).

Elle attrape donc la FORME directe, pas la chaîne. C'est écrit ici pour
qu'on ne lise pas son silence comme un acquittement.

Ce qu'elle épargne, et pourquoi c'est la moitié qui compte
-----------------------------------------------------------

- ``await MonEtat.load()`` — un appel d'ATTRIBUT, jamais un nom nu :
  c'est la porte prévue, elle ne peut pas être confondue.
- Un ``ClientState`` : il ne touche aucun backend, sa valeur arrive
  dans le corps de la requête. Le construire sur la boucle est gratuit.
- Un ``def`` imbriqué dans un ``async def`` compte quand même comme
  « sur la boucle » : le framework ne délestera pas une fonction locale
  que l'auteur appelle lui-même.
"""

from __future__ import annotations

import ast
from functools import lru_cache

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "etat-construit-sur-la-boucle"


@lru_cache(maxsize=1)
def _server_state_names() -> frozenset[str]:
    """Les classes d'état SERVEUR publiques, dérivées et non recopiées.

    Dérivées, parce qu'une table de noms écrite à la main dérive du code
    qu'elle juge — c'est la règle du dossier. Le
    filtre est ``ServerState`` et pas ``State`` — un ``ClientState`` n'a
    pas de backend à attendre, donc rien à refuser.
    """
    import inspect

    import bretzel
    import bretzel.state as state_module
    from bretzel.state.scopes.server import ServerState

    names = set()
    for module in (bretzel, state_module):
        for name in dir(module):
            obj = getattr(module, name, None)
            if inspect.isclass(obj) and issubclass(obj, ServerState):
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


def _local_server_states(tree: ast.Module) -> set[str]:
    """Les états serveur déclarés DANS ce module.

    Une app dérive volontiers un état de base commun ; ne reconnaître
    que les classes du framework raterait toute la seconde génération.
    Les classes sont lues dans l'ordre du fichier, donc une base locale
    est connue avant ses filles — l'ordre d'écriture de Python.
    """
    known = _server_state_names()
    local: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _base_names(node) & (known | local):
            local.add(node.name)
    return local


def check(module: Module) -> list[Finding]:
    """Les constructions d'état serveur faites depuis la boucle."""
    names = _server_state_names() | _local_server_states(module.tree)

    findings: list[Finding] = []
    for func in ast.walk(module.tree):
        if not isinstance(func, ast.AsyncFunctionDef):
            continue
        for node in ast.walk(func):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            built = node.func.id
            if built not in names:
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=(
                        f"`{built}()` est construit dans `{func.name}`, qui est "
                        f"`async def` — donc sur la boucle, où l'état ne peut "
                        f"pas s'hydrater si le backend lit par le réseau."
                    ),
                    hint=(
                        f"Écris `etat = await {built}.load()`, ou repasse "
                        f"`{func.name}` en `def` (le framework le délestera sur "
                        f"un thread, où `{built}()` marche tel quel). En "
                        f"mémoire la ligne actuelle marche ; avec `redis_url` "
                        f"elle lève — c'est une faute qui attend la prod."
                    ),
                )
            )
    return findings

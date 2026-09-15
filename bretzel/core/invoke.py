"""Appeler du code d'APPLICATION sans jamais bloquer la boucle.

Un handler d'action, un corps de page, un corps de zone ``@refreshable``,
le ``rows=`` d'un export, la fonction d'un ``@download``, la callback
d'une porte ``@auth.door``, un hook de cycle de vie — tout ça est écrit
par l'auteur de l'app, et le framework l'appelle. Le principe 7 du
charter dit « async-only », mais l'idiome réel du produit est le
contraire : mesuré le 2026-09-04, ``examples/`` porte **1 659 ``def``
pour 16 ``async def``** — parce que ``state.counter += 1`` n'a rien à
attendre, et qu'exiger un ``async`` pour ça serait une cérémonie vide.

Une fonction ``def`` appelée telle quelle depuis une coroutine tourne
**dans le thread de la boucle**. Tant qu'elle ne fait qu'arithmétique
sur l'état, c'est le bon choix. Le jour où elle appelle une base de
données synchrone, ``requests.get`` ou ``time.sleep``, elle gèle
l'``event loop`` du worker : plus aucune requête HTTP servie, plus de
heartbeat SSE, pour TOUS les autres utilisateurs — et rien ne lève,
rien ne s'affiche, la panne se lit comme « le serveur est tombé ».

D'où :func:`call_without_blocking`. Une ``async def`` est attendue
directement ; **toute autre** est délestée sur le threadpool que
Starlette utilise déjà (``anyio.to_thread``), comme le fait FastAPI
d'une route non-async. Le développeur n'a rien à déclarer, et il n'y a
donc rien à OUBLIER de déclarer — c'est le point : le mode d'échec
qu'on remplace est invisible jusqu'à la production.

**Ce que ça coûte**, mesuré en A/B alterné dans le même process le
2026-09-04 : le saut de thread vaut **0,19 ms** (p95 0,78) contre
0,003 ms pour l'appel direct, sur un aller-retour d'action minimal qui
en pèse **2,90** (p95 5,02). Un rendu de page en paie un par corps —
chaque layout de la chaîne, la page, puis le rabattage de l'arbre — soit
trois pour une page à un layout ; les zones ``@refreshable`` que le
corps appelle, elles, sont gratuites : elles tournent dans le thread de
leur appelant.

**Pourquoi pas ``starlette.concurrency.run_in_threadpool``**, qui fait
exactement ces deux lignes : parce qu'il faudrait importer le framework
web dans la couche 0. On reproduit donc son corps délibérément — s'il
change de façon d'entrer dans le pool, cette copie doit suivre.
:func:`_is_async_callable` duplique de même le ``is_async_callable`` de
``starlette._utils``, dont le module est **privé** : c'est un choix, pas
un oubli.

**Ce que ça change pour les ``ContextVar``** : ``anyio`` COPIE le
contexte courant dans le thread, donc tout ce que le framework a posé
avant l'appel (le contexte de rendu, le registre d'état, la file de
tâches de fond) se lit normalement. En revanche un ``set()`` fait DANS
le thread ne remonte pas. Aucun de nos ``ContextVar`` n'est concerné :
ils sont tous posés puis restaurés par un gestionnaire de contexte
équilibré, et l'état qui doit survivre à l'appel vit sur des OBJETS
(``RenderContext``, ``StateRegistry``), que le thread mute pour de bon.

⚠️ **Ce que ça change pour la CONCURRENCE, et il faut le lire.** Un
``def`` était jusqu'ici sérialisé par construction : la boucle étant
mono-thread, deux handlers ne pouvaient pas s'exécuter en même temps.
Ils le peuvent maintenant, jusqu'à 40 de front. Le ``state.counter += 1``
qui sert d'exemple ci-dessus est une lecture puis une écriture : sur un
:class:`~bretzel.state.AppState` partagé, deux requêtes simultanées
peuvent désormais perdre un incrément **à l'intérieur d'un même
worker**, là où il fallait avant deux workers pour ça. Ce n'est pas une
régression du délestage — la même perte existait déjà entre deux
processus, et le manque de verrou optimiste au commit est suivi à part
dans ``.claude/work/todo.md`` — mais le délestage la rend atteignable
en local, donc reproductible.

**Le plafond devient le pool**, 40 threads par défaut chez ``anyio`` :
41 handlers bloquants simultanés font attendre le 41ᵉ. C'est le
compromis standard, et il reste sans commune mesure avec une boucle
gelée — là, c'est TOUT le worker qui s'arrête, y compris les requêtes
qui n'ont rien demandé.

``anyio`` arrive avec starlette : ce module n'ajoute aucune dépendance
(même raison qu'à ``server/oauth.py``).
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

import anyio.to_thread

__all__ = ["call_without_blocking"]


def _is_async_callable(fn: Any) -> bool:
    """``True`` si appeler ``fn`` rend une coroutine à attendre.

    ``iscoroutinefunction`` déballe les ``functools.partial`` tout seul
    (un handler à arguments liés en est un). Le second test couvre les
    callables qui ne sont pas des fonctions — un objet dont le
    ``__call__`` est ``async`` ; ça lui évite un saut de thread inutile,
    la correction étant de toute façon assurée par le ``iscoroutine``
    de :func:`call_without_blocking`.
    """
    return inspect.iscoroutinefunction(fn) or inspect.iscoroutinefunction(
        getattr(fn, "__call__", None)  # noqa: B004 — on veut l'attribut
    )


async def call_without_blocking(
    fn: Callable[..., Any], /, *args: Any, **kwargs: Any
) -> Any:
    """Appeler ``fn`` et rendre son résultat, boucle jamais bloquée.

    - ``async def`` → attendue sur la boucle, aucun saut de thread ;
    - tout le reste → délesté sur le threadpool partagé de Starlette.

    Une fonction synchrone qui RETOURNE un awaitable (elle relaie une
    coroutine construite ailleurs) est encore attendue ici : l'objet
    coroutine n'appartient à aucun thread, seul son ``await`` compte.
    """
    if _is_async_callable(fn):
        return await fn(*args, **kwargs)
    result = await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))
    if inspect.iscoroutine(result):
        result = await result
    return result

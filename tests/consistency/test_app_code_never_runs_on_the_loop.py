"""Gate : le code d'APPLICATION n'est jamais appelé sur la boucle.

Un handler d'action, un corps de page, un corps de zone
``@refreshable``, le ``rows=`` d'un export, la fonction d'un
``@download``, la callback d'une porte ``@auth.door``, un hook de cycle
de vie — tout ça est écrit par l'auteur de l'app. Le framework l'appelle
depuis une coroutine, et jusqu'au 2026-09-04 il le faisait **inline** ::

    result = handler(*args, **kwargs)
    if inspect.iscoroutine(result):
        await result

Un ``def`` bloquant — base synchrone, ``requests.get``, ``time.sleep`` —
gelait alors l'``event loop`` du worker pour toute sa durée : plus une
seule requête servie, plus un heartbeat SSE, pour TOUS les utilisateurs
connectés. Rien ne levait, rien ne s'affichait. La panne se lit comme
« le serveur est tombé », ce qui envoie chercher ailleurs.

Le remède est un point de passage unique —
:func:`bretzel.core.call_without_blocking` — qui attend une ``async def``
et délestre tout le reste sur le threadpool de Starlette. Cette gate
protège les deux moitiés de ce remède :

1. **la forme interdite ne revient pas.** « J'appelle, puis j'awaite si
   c'est une coroutine » est exactement le geste qui bloque, et il est
   assez naturel pour être ré-écrit par distraction. Il ne doit exister
   que dans ``core/invoke.py``, plus deux exceptions nommées ;
2. **les points d'entrée sont ceux qu'on croit.** Une interdiction seule
   resterait verte si quelqu'un supprimait les appels — la table
   ci-dessous les nomme, dans les deux sens : un site qui disparaît
   rougit, un site neuf doit être déclaré (donc décidé).

⚠️ **Ce que ce détecteur NE voit pas**, et il faut le savoir avant de le
croire exhaustif : un site qui appelle du code d'app **sans jamais
interroger le résultat** ne porte aucune des deux orthographes et reste
invisible. C'est ainsi que la callback d'une porte ``@auth.door``
(``server/oauth.py``) a échappé au premier jet — elle est
contractuellement synchrone, donc rien à interroger. La table
``_ENTRY_POINTS`` est ce qui rattrape cette moitié-là, et elle est
écrite à la main : elle confirme ce qui a été fait, elle ne peut pas
signaler ce qui a été oublié.

⚠️ ``iscoroutinefunction`` n'est PAS visé, et c'est délibéré : trois
sites l'utilisent pour REFUSER une ``async def`` à la décoration
(``@auth.source``, ``@auth.door``, un middleware utilisateur) et un
quatrième pour marquer une zone une fois pour toutes. Interroger le
callable est licite ; c'est l'appeler d'abord et regarder ensuite qui ne
l'est pas.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.consistency._discovery import (
    PACKAGE_DIR,
    PACKAGE_FLOOR,
    ParsedSource,
    parsed_sources,
    source_of,
)

#: Le module autorisé à porter la forme est celui qui la remplace.
#: Les deux autres sont des exceptions, chacune avec sa raison.
_ISCOROUTINE_ALLOWED: dict[str, str] = {
    "core/invoke.py": (
        "le point de passage lui-même — il relaie une fonction sync qui "
        "RETOURNE un awaitable"
    ),
    "server/lifecycle.py": (
        "``aclose()``/``close()`` d'un backend d'état : du code de "
        "BIBLIOTHÈQUE (redis) appelé à l'arrêt, pas du code d'app, et le "
        "contrat SSEBroker autorise les deux formes"
    ),
    "components/data/datatable/datatable.py": (
        "un REFUS, pas une attente : ``render()`` est synchrone par "
        "contrat, donc un ``rows=`` coroutine y est fermé et signalé "
        "par ``ComponentUsageError``. Le ``rows=`` SYNCHRONE, lui, ne "
        "tourne plus sur la boucle — c'est le rabattage qui est délesté, "
        "un cran au-dessus (``render/pipeline.py``, ``render/partials.py``)"
    ),
}

#: Les points d'entrée du code d'application, nommés. Une table et non un
#: compte : « au moins quatre » laisserait passer « un qui sort, un qui
#: rentre » (cf. ``.claude/bretzel/gates.md``).
_ENTRY_POINTS: dict[str, str] = {
    "server/routing/actions.py": "le handler d'une action",
    "server/app.py": (
        "le rapatriement des scripts tiers au premier appel ASGI, en dev "
        "— quatre téléchargements réseau, donc un proxy lent bloquerait "
        "le démarrage entier du worker"
    ),
    "render/pipeline.py": (
        "le corps d'une page et de ses layouts, puis le rabattage de "
        "l'arbre — où les ``render=`` et ``rows=`` d'app se rappellent"
    ),
    "render/partials.py": (
        "le corps d'une zone rendue seule (OOB / refetch SSE), et son "
        "rabattage"
    ),
    "server/lifecycle.py": "les hooks de cycle de vie déclarés par l'app",
    "server/routing/datatable.py": "le ``rows=`` d'un export CSV",
    "server/routing/downloads.py": "la fonction d'un ``@download``",
    "server/oauth.py": "la callback d'une porte ``@auth.door``",
}

_HELPER = "call_without_blocking"


def _relative(path: Path) -> str:
    return path.relative_to(PACKAGE_DIR).as_posix()


def _sources() -> list[ParsedSource]:
    return parsed_sources(PACKAGE_DIR, floor=PACKAGE_FLOOR)


#: Les deux orthographes de « j'ai appelé, est-ce que ça s'attend ? ».
#: Le premier jet de cette gate ne connaissait que ``iscoroutine`` — et
#: ratait donc les TROIS sites qui écrivent ``isawaitable``, exactement la
#: pathologie que ``gates.md`` décrit : une gate qui code en dur un
#: identifiant devient muette sans rougir quand le mot change.
_AFTER_THE_CALL: frozenset[str] = frozenset({"iscoroutine", "isawaitable"})


def _is_iscoroutine_call(node: ast.AST) -> bool:
    """``inspect.iscoroutine(x)`` / ``asyncio.iscoroutine(x)`` / ``isawaitable(x)``…

    Le nom est comparé ENTIER : ``iscoroutinefunction`` interroge le
    callable AVANT de l'appeler, ce qui est le geste licite.
    """
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr in _AFTER_THE_CALL
    return isinstance(fn, ast.Name) and fn.id in _AFTER_THE_CALL


def blocking_shapes() -> list[str]:
    """Les sites qui appellent d'abord et regardent ensuite."""
    return [
        f"{_relative(s.path)}:{node.lineno}"
        for s in _sources()
        if _relative(s.path) not in _ISCOROUTINE_ALLOWED
        for node in ast.walk(s.tree)
        if _is_iscoroutine_call(node)
    ]


def helper_call_sites() -> set[str]:
    """Les fichiers qui APPELLENT :func:`call_without_blocking`.

    Un import n'est pas un appel : ``core/__init__.py``, qui le
    ré-exporte, ne remonte donc pas ici — c'est voulu, il ne s'en sert
    pas.
    """
    return {
        _relative(s.path)
        for s in _sources()
        for node in ast.walk(s.tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == _HELPER
    }


def test_the_sweep_is_not_vacuous() -> None:
    """① Le plancher, lu depuis la découverte de CETTE gate.

    C'est ``parsed_sources`` qui lève en premier si le balayage se
    rétrécit — cette ligne le redit pour que la gate porte SON plancher
    en clair plutôt que de le déléguer à une lecture partagée.
    """
    assert len(_sources()) >= PACKAGE_FLOOR


def test_no_module_calls_first_and_awaits_after() -> None:
    """② L'interdiction."""
    offenders = blocking_shapes()
    assert not offenders, (
        "Ces sites appellent un callable puis awaitent son résultat s'il "
        "est une coroutine — une fonction SYNCHRONE y tourne donc dans le "
        "thread de la boucle, et un appel bloquant gèle le worker "
        "entier :\n  " + "\n  ".join(offenders) + "\n\nPasse par "
        "``from bretzel.core import call_without_blocking``. Si ce site "
        "n'appelle PAS du code d'application, ajoute-le à "
        "``_ISCOROUTINE_ALLOWED`` avec sa raison."
    )


def test_every_entry_point_still_goes_through_the_helper() -> None:
    """③ Le contrôle POSITIF — dans les deux sens.

    Une interdiction seule reste verte sur un framework qui n'appellerait
    plus rien. C'est ce test qui dit que les quatre portes existent, et
    qu'une cinquième ne s'ouvre pas sans être écrite.
    """
    measured = helper_call_sites()
    declared = set(_ENTRY_POINTS)
    assert measured == declared, (
        f"points d'entrée mesurés {sorted(measured)} ≠ déclarés "
        f"{sorted(declared)}.\n"
        "  • un site qui MANQUE : le code d'application y est redevenu "
        "bloquant, ou le point d'entrée a été supprimé ;\n"
        "  • un site EN TROP : légitime, mais déclare-le dans "
        "``_ENTRY_POINTS`` avec ce qu'il appelle — un point d'entrée non "
        "écrit est un point d'entrée que personne ne saura relire."
    )


def test_the_detector_still_bites() -> None:
    """④ La mutation, deux versants.

    Le versant licite compte autant : c'est lui qui dirait que la gate va
    se mettre à rougir sur les refus de ``async def`` à la décoration.
    """
    guilty = ast.parse(
        "import inspect\n"
        "def f(h):\n"
        "    r = h()\n"
        "    if inspect.iscoroutine(r):\n"
        "        pass\n"
    )
    innocent = ast.parse(
        "import inspect\n"
        "def f(h):\n"
        "    if inspect.iscoroutinefunction(h):\n"
        "        raise TypeError\n"
        "    return h()\n"
    )
    assert any(_is_iscoroutine_call(n) for n in ast.walk(guilty))
    assert not any(_is_iscoroutine_call(n) for n in ast.walk(innocent))

    # Les DEUX orthographes, comptées séparément : celle qui manquait au
    # premier jet ne rougissait pas, elle se taisait.
    other = ast.parse("x = inspect.isawaitable(h())")
    assert any(_is_iscoroutine_call(n) for n in ast.walk(other))

    # Et le détecteur reconnaît un cas RÉEL : la seule exception nommée
    # porte bien la forme, sinon l'allowlist protège un site mort.
    lifecycle = source_of(PACKAGE_DIR / "server" / "lifecycle.py")
    assert any(_is_iscoroutine_call(n) for n in ast.walk(lifecycle.tree)), (
        "``server/lifecycle.py`` ne porte plus la forme qu'on lui pardonne "
        "— retire-le de ``_ISCOROUTINE_ALLOWED`` plutôt que de garder une "
        "exception qui ne couvre plus rien."
    )

"""Gate : un ``on_*`` câblé en action serveur est DÉCLARÉ dans ``EVENTS``.

Le défaut qu'elle ferme
-----------------------
``EVENTS`` n'est pas de la métadonnée. Un event déclaré, c'est la
promesse des **trois formes** que tout ``on_*`` du framework accepte :
un callable serveur, une chaîne d'expression cliente, ou une liste des
deux. Un composant qui câble une action sans déclarer son event fait
donc une promesse qu'il ne tient pas — et il la trahit MAL.

Mesuré le 2026-09-06, sur trois composants livrés :

    ui.table(…, on_item_click="alert(1)")   → TypeError: the first
    ui.bar_chart(…, on_item_click="alert(1)")  argument must be
    ui.pie_chart(…, on_item_click="alert(1)")  callable

Un ``TypeError`` remonté NU depuis ``functools.partial`` : il ne nomme
ni le composant, ni la prop, ni ce qu'il fallait passer. Les trois
avaient recopié le même ``partial`` + ``register_action``, donc le même
trou — c'est ce qui a donné ``item_action_attrs``, le routeur partagé.

⚠️ **Ce n'est PAS ce que la surface publique laissait voir.**
``bretzel describe`` liste bien ``on_item_click`` pour les deux graphiques : il
lit la SIGNATURE, pas ``EVENTS``. Un lecteur de la fiche voyait donc un
event parfaitement normal, et découvrait le trou à l'exécution. C'est
exactement pourquoi cette asymétrie mérite une gate plutôt qu'une
relecture : elle est invisible des deux côtés qu'on inspecte
d'habitude.

Ce que la gate NE dit pas
-------------------------
« Ce composant aurait dû avoir un event. » C'est du sens, pas de la
forme, et aucune machine ne le décide. Ce qui se mesure, c'est
l'asymétrie entre ce qui est CÂBLÉ et ce qui est ANNONCÉ — le fichier
appelle ``register_action`` et son ``__init__`` nomme un ``on_<x>``
absent de ``EVENTS``.

Portée honnête
--------------
Elle ne regarde que les ``on_*`` **keyword-only nommés dans
l'__init__**. Un handler passé par ``**kwargs`` est routé par le socle,
qui exige déjà la déclaration (``cross_check_events``) — ce chemin-là
est gardé ailleurs, et c'est justement pour ça que le trou vivait dans
les composants qui routent À LA MAIN.
"""

from __future__ import annotations

import ast
import functools

import pytest

from tests.consistency._discovery import (
    component_sources,
    public_component_classes,
    ui_name_of,
)

#: Les DEUX marques d'un câblage manuel : le composant enregistre
#: lui-même son action au lieu de laisser le socle le faire depuis
#: ``**kwargs``.
#:
#: Deux et pas une, parce que la forme a changé sous la gate pendant
#: qu'on l'écrivait : `item_action_attrs` est le routeur partagé extrait
#: des quatre composants concernés, et une fois converti un composant
#: n'appelle plus `register_action` en direct. Ne garder que l'ancienne
#: marque aurait rendu la gate aveugle à ceux qui font bien — donc
#: aveugle à la population entière, à terme.
_WIRES_BY_HAND = ("register_action(", "item_action_attrs(")


@functools.lru_cache(maxsize=1)
def _by_name() -> dict[str, type]:
    return {c.__name__: c for c in public_component_classes()}


def declared_on_params(node: ast.ClassDef) -> set[str]:
    """Les ``on_*`` que l'``__init__`` de cette classe nomme.

    Keyword-only uniquement : c'est la forme de tout paramètre public de
    ce dépôt, et un positionnel serait un autre sujet.
    """
    for item in node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            return {
                a.arg for a in item.args.kwonlyargs if a.arg.startswith("on_")
            }
    return set()


@functools.lru_cache(maxsize=1)
def wired_but_undeclared() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """``(nom de classe, events câblés non déclarés)`` — le constat."""
    out: list[tuple[str, tuple[str, ...]]] = []
    known = _by_name()
    for path in component_sources():
        source = path.read_text(encoding="utf-8-sig")
        if not any(mark in source for mark in _WIRES_BY_HAND):
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.ClassDef) or node.name not in known:
                continue
            # ``EVENTS`` absent = le défaut hérité, ``()``. C'est le cas
            # qui comptait : les trois fautifs ne le déclaraient pas du
            # tout, donc un détecteur qui exige la ligne les rate.
            declared = set(getattr(known[node.name], "EVENTS", ()) or ())
            missing = {
                p.removeprefix("on_") for p in declared_on_params(node)
            } - declared
            if missing:
                out.append((node.name, tuple(sorted(missing))))
    return tuple(out)


# ── Plancher ──────────────────────────────────────────────────────────
#
# Il lit la DÉCOUVERTE de CETTE gate — combien de composants elle a
# vraiment ouverts et parsés — et non une population recomptée depuis
# son propre glob, qui resterait verte le jour où le balayage se
# débranche.


@functools.lru_cache(maxsize=1)
def _inspected() -> tuple[int, int]:
    """``(fichiers câblant à la main, classes publiques trouvées dedans)``."""
    files = 0
    classes = 0
    known = _by_name()
    for path in component_sources():
        source = path.read_text(encoding="utf-8-sig")
        if not any(mark in source for mark in _WIRES_BY_HAND):
            continue
        files += 1
        classes += sum(
            1
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ClassDef) and node.name in known
        )
    return files, classes


def test_the_sweep_finds_components_that_wire_by_hand() -> None:
    files, classes = _inspected()
    assert files >= 4, (
        f"seulement {files} fichier(s) de composant portent l'une de "
        f"{_WIRES_BY_HAND} — la marque du câblage manuel a changé de "
        f"forme, et cette gate ne garde plus rien. Retrouve-la AVANT de "
        f"croire l'asymétrie disparue."
    )
    assert classes >= 4, (
        f"{files} fichiers balayés mais {classes} classe(s) publique(s) "
        f"reconnue(s) dedans — la correspondance nom de classe → "
        f"composant public est cassée."
    )


def test_the_reader_finds_the_on_params() -> None:
    """Second plancher : l'extracteur de paramètres voit encore quelque
    chose.

    Sans lui, un `declared_on_params` rendant toujours l'ensemble vide
    rendrait la gate verte sur tout le catalogue — l'exacte pathologie
    « verte parce qu'elle ne regarde rien ».
    """
    seen: set[str] = set()
    known = _by_name()
    for path in component_sources():
        source = path.read_text(encoding="utf-8-sig")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef) and node.name in known:
                seen |= declared_on_params(node)
    assert len(seen) >= 10, (
        f"seulement {len(seen)} nom(s) de handler distinct(s) trouvé(s) "
        f"dans les __init__ du catalogue : {sorted(seen)}. L'extracteur "
        f"est cassé."
    )


# ── L'assertion ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cls_name", "missing"),
    wired_but_undeclared() or [("<aucun>", ())],
    ids=lambda v: v if isinstance(v, str) else ",".join(v),
)
def test_a_wired_handler_is_declared(cls_name: str, missing: tuple[str, ...]) -> None:
    if cls_name == "<aucun>":
        return
    ui_name = ui_name_of(_by_name()[cls_name])
    assert not missing, (
        f"`ui.{ui_name}` câble une action serveur depuis "
        f"{', '.join('on_' + m for m in missing)}, absent de son "
        f"`EVENTS`.\n"
        f"  Déclarer l'event n'est pas de la métadonnée : c'est la "
        f"promesse des TROIS formes qu'accepte tout `on_*` du framework "
        f"— un callable, une chaîne d'expression cliente, ou une liste "
        f"des deux. Sans la déclaration, la chaîne lève un `TypeError` "
        f"nu depuis `functools.partial`.\n"
        f"  Le routage par ÉLÉMENT (une ligne, une barre, une part, un "
        f"nœud) passe par `item_action_attrs` — le socle, lui, poserait "
        f"l'`hx-post` sur la racine.\n"
        f"  Cf. `.claude/work/audit-declaration-2026-09-06.md`."
    )


def test_the_gate_would_catch_an_undeclared_handler() -> None:
    """Mutation : le détecteur reconnaît la forme fautive, et elle seule.

    Fabriquée en mémoire — le versant fautif ET le versant licite, parce
    qu'un détecteur qui rougit sur tout est aussi inutile qu'un
    détecteur aveugle.
    """
    faulty = ast.parse(
        "class X:\n"
        "    def __init__(self, *, on_item_click=None, size=None): ...\n"
    )
    node = next(n for n in ast.walk(faulty) if isinstance(n, ast.ClassDef))
    assert declared_on_params(node) == {"on_item_click"}

    licit = ast.parse("class Y:\n    def __init__(self, *, size=None): ...\n")
    node = next(n for n in ast.walk(licit) if isinstance(n, ast.ClassDef))
    assert declared_on_params(node) == set()

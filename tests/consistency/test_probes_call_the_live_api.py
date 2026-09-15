"""Aucun script de ``tests/probes/`` n'appelle une API qui n'existe plus.

Pourquoi cette gate existe (mesuré le 2026-08-19)
-------------------------------------------------
``tests/probes/`` est le SEUL étage qui regarde vraiment le rendu — la
suite *visual* a été supprimée le 2026-08-16, et ``tests/audit/`` ne juge
que des mesures déterministes. Mais ``probes/`` n'est **pas collecté par
pytest** (les fichiers s'appellent ``probe_*.py`` / ``bench_*.py``, pas
``test_*.py``), donc rien ne les exécute tant qu'un humain ne le fait pas.

Ce qui arrive quand personne ne les lance a été mesuré en les lançant
tous, une fois : **17 rouges sur 52**, et **9 d'entre eux mouraient de la
MÊME ligne** — ``default_shell(mode="dev")``, alors que le paramètre
``mode`` avait été remplacé par ``browser_css: bool``. Un ``TypeError``
au premier appel, donc zéro mesure, donc neuf probes muets depuis le
changement de signature. Le dépôt croyait avoir un étage visuel ; il
avait neuf scripts qui plantaient avant d'ouvrir Chromium.

Ce que la gate affirme, et ce qu'elle n'affirme pas
---------------------------------------------------
Elle vérifie **statiquement** que chaque appel à un symbole importé
depuis ``bretzel`` se lie à la signature actuelle (``bind_partial``).
Elle ne lance aucun navigateur et n'affirme rien sur ce que le probe
MESURE — un probe peut être vert ici et faux au fond. Elle ferme
exactement la classe qui a tué les neuf : **le probe ne démarre même
pas**.

Les composants (``ui.*``) sont hors de portée par construction : ils
absorbent leurs kwargs universels via ``**kwargs``, donc leur signature
accepte tout et ``bind_partial`` ne peut rien dire. C'est voulu — la
gate ne parle que des fonctions à signature fermée.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from typing import Any

from tests.consistency._discovery import (
    PROBES_DIR,
    PROBES_FLOOR,
    ParsedSource,
    parsed_sources,
)


def probe_sources() -> list[ParsedSource]:
    """Les scripts de ``tests/probes/``, lus par le lecteur PARTAGÉ."""
    return parsed_sources(PROBES_DIR, floor=PROBES_FLOOR)


def _bretzel_bindings(tree: ast.Module) -> dict[str, str]:
    """``nom local -> chemin pointé`` pour les ``from bretzel… import X``.

    Seul le niveau module est lu : un import dans une fonction sert à
    casser un cycle, pas à écrire une ligne d'appel qu'on relit.
    """
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("bretzel"):
            for alias in node.names:
                if alias.name != "*":
                    out[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return out


def _resolve(dotted: str) -> Any:
    module, _, name = dotted.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _mismatch(func: Any, call: ast.Call) -> str | None:
    """Le message d'erreur si ``call`` ne se lie pas à ``func``, sinon ``None``.

    Un ``*args`` / ``**kwargs`` au call-site rend la liaison indécidable
    statiquement : on s'abstient plutôt que d'inventer un verdict.
    """
    if any(a for a in call.args if isinstance(a, ast.Starred)):
        return None
    if any(k.arg is None for k in call.keywords):
        return None
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return None
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
        return None
    try:
        signature.bind_partial(*[None] * len(call.args),
                               **{k.arg: None for k in call.keywords})
    except TypeError as exc:
        return f"{exc} — signature actuelle : {signature}"
    return None


def offenders() -> list[str]:
    """Les appels d'un probe à une signature framework qui a bougé."""
    out: list[str] = []
    for source in probe_sources():
        bindings = _bretzel_bindings(source.tree)
        if not bindings:
            continue
        for node in ast.walk(source.tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            dotted = bindings.get(node.func.id)
            if dotted is None:
                continue
            try:
                func = _resolve(dotted)
            except (ImportError, AttributeError) as exc:
                out.append(f"{source.path.name}:{node.lineno} — "
                           f"``{dotted}`` n'existe plus ({type(exc).__name__})")
                continue
            problem = _mismatch(func, node)
            if problem is not None:
                out.append(f"{source.path.name}:{node.lineno} — "
                           f"``{node.func.id}(…)`` : {problem}")
    return out


def checked_calls() -> int:
    """Combien d'appels la gate a réellement examinés."""
    total = 0
    for source in probe_sources():
        bindings = _bretzel_bindings(source.tree)
        total += sum(
            1 for node in ast.walk(source.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in bindings
        )
    return total


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la découverte de CETTE gate, pas une source fraîche.

    Deux planchers, parce qu'il y a deux façons de vider ce balayage :
    ne plus trouver de fichier, et n'y reconnaître aucun appel (un
    ``_bretzel_bindings`` cassé rendrait la gate verte sur 97 fichiers).
    """
    assert len(probe_sources()) >= PROBES_FLOOR
    assert checked_calls() >= 100, (
        f"seulement {checked_calls()} appels examinés — la reconnaissance "
        f"des imports est cassée, et « aucun probe n'appelle une API morte » "
        f"serait affirmé sans avoir rien lu (254 le 2026-08-19)."
    )


def test_no_probe_calls_a_dead_api() -> None:
    found = offenders()
    assert not found, (
        "Des scripts de ``tests/probes/`` appellent une API qui a changé. "
        "Ils lèvent un ``TypeError`` avant d'ouvrir Chromium, donc ils ne "
        "mesurent RIEN — et comme pytest ne les collecte pas, personne ne "
        "le voit :\n  " + "\n  ".join(found)
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants : le motif interdit, et son jumeau LICITE."""
    from bretzel.render.shell import default_shell

    dead = ast.parse('f(body, envelope_json="", page_uuid="x", mode="dev")')
    live = ast.parse('f(body, envelope_json="", page_uuid="x", browser_css=True)')
    dead_call = dead.body[0].value  # type: ignore[attr-defined]
    live_call = live.body[0].value  # type: ignore[attr-defined]

    assert _mismatch(default_shell, dead_call) is not None, (
        "le détecteur ne mord plus sur ``mode=`` — le paramètre exact qui "
        "a tué 9 probes."
    )
    assert _mismatch(default_shell, live_call) is None, (
        "le détecteur mord sur l'appel CORRECT — il rendrait la gate "
        "impossible à verdir, donc destinée à être débranchée."
    )

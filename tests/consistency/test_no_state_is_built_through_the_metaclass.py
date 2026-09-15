"""Le framework ne construit jamais un état par ``cls(...)`` pour l'hydrater.

``MonEtat(...)`` est **intercepté** par ``_StateMeta.__call__``, qui ne
construit pas : il consulte le registre de la requête, rend l'instance
cachée si elle existe, et sinon va LIRE le magasin. C'est exactement ce
qu'il faut pour du code d'app — et exactement ce qu'il ne faut pas pour
du code de framework qui tient déjà les données.

Ce que la forme fautive produit, mesuré le 2026-09-06 sur la
``State.from_dict`` supprimée depuis :

- si l'état est en cache, ``cls(key=key)`` rend **l'instance vivante de
  la requête**, et le ``_apply_fields`` qui suit l'écrase. Un état à 7
  valait 99 après l'appel, et tout ``MonEtat()`` ultérieur voyait 99.
  L'appelant croyait fabriquer une copie ;
- sinon, il paie un aller-retour au magasin pour hydrater un objet que
  la ligne suivante remplace — et depuis la boucle avec Redis, cette
  lecture **lève** ``StateHydrationError``, dont le message recommande
  ``await MonEtat.load()``, un conseil qui n'a aucun sens là.

La forme juste est ``type.__call__(cls, key=key)`` : elle court-circuite
la métaclasse, ce que ``StateRegistry._build`` fait déjà. Le versant
licite de la mutation ci-dessous s'assure qu'elle n'est pas confondue
avec la fautive.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_STATE_DIR = Path(__file__).resolve().parents[2] / "bretzel" / "state"

#: Le plancher : en dessous, le balayage ne lit plus le module qu'il croit.
_FLOOR = 8


def state_sources() -> list[tuple[Path, ast.Module]]:
    """La DÉCOUVERTE de cette gate — lue une fois, par le plancher ET
    par l'interdiction, pour qu'un balayage débranché ne reste pas vert."""
    out = []
    for path in sorted(_STATE_DIR.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        out.append((path, ast.parse(path.read_text("utf-8-sig"))))
    return out


def _hydrating_constructions(tree: ast.Module) -> list[int]:
    """Les lignes où l'on CONSTRUIT par ``cls(...)`` puis hydrate.

    Le motif complet, pas seulement l'appel : ``cls(...)`` seul est
    légitime partout (c'est l'API que le code d'app utilise). Ce qui est
    fautif, c'est de le faire pour poser des données qu'on tient déjà —
    et ça se voit à l'``_apply_fields`` sur le même nom.
    """
    fautifs: list[int] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # nom de variable → ligne de sa construction par ``cls(...)``
        construits: dict[str, int] = {}
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "cls"
            ):
                construits[node.targets[0].id] = node.lineno
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_apply_fields"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in construits
            ):
                fautifs.append(construits[node.func.value.id])
    return fautifs


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher. Une interdiction passe parfaitement sur zéro fichier."""
    sources = state_sources()
    assert len(sources) >= _FLOOR, (
        f"{len(sources)} fichier(s) lus dans bretzel/state/ — le balayage "
        f"ne voit plus le module qu'il croit surveiller."
    )
    assert any(
        "_apply_fields" in p.read_text("utf-8-sig") for p, _ in sources
    ), "``_apply_fields`` a disparu : la gate cherche un motif éteint."


def test_no_framework_code_hydrates_through_the_metaclass() -> None:
    """L'interdiction."""
    fautifs = [
        f"{p.relative_to(_STATE_DIR.parent.parent)}:{ligne}"
        for p, tree in state_sources()
        for ligne in _hydrating_constructions(tree)
    ]
    assert not fautifs, (
        "Ces endroits construisent un état par `cls(...)` puis l'hydratent :\n"
        + "\n".join(f"  {f}" for f in fautifs)
        + "\n\n`cls(...)` passe par la métaclasse, qui rend l'instance "
        "CACHÉE de la requête — donc `_apply_fields` écrase l'état vivant "
        "au lieu de remplir un objet neuf. Écris "
        "`type.__call__(cls, key=key)`, comme `StateRegistry._build`."
    )


def test_the_detector_bites_and_spares() -> None:
    """La mutation, dans les deux sens.

    Le versant licite compte autant : un détecteur qui attraperait aussi
    ``type.__call__`` interdirait la forme JUSTE, et la gate rougirait
    sur le seul endroit qui fait bien.
    """
    fautif = ast.parse(
        "def f(cls, data):\n"
        "    inst = cls(key='k')\n"
        "    inst._apply_fields(data)\n"
    )
    assert _hydrating_constructions(fautif) == [2]

    licite = ast.parse(
        "def f(cls, data):\n"
        "    inst = type.__call__(cls, key='k')\n"
        "    inst._apply_fields(data)\n"
    )
    assert not _hydrating_constructions(licite), (
        "le détecteur attrape `type.__call__`, qui est la forme correcte"
    )

    # Construire sans hydrater n'est pas le motif : c'est l'API normale.
    normal = ast.parse("def f(cls):\n    return cls(key='k')\n")
    assert not _hydrating_constructions(normal)


@pytest.mark.anyio
async def test_hydrating_does_not_touch_the_live_instance() -> None:
    """Le versant comportemental — celui qui a révélé le défaut.

    La gate AST protège la forme ; celle-ci protège la propriété. Les
    deux servent : une troisième orthographe du même piège échapperait à
    la première et pas à la seconde.
    """
    from bretzel.state import SessionState, field
    from bretzel.state.persistence.memory import MemoryBackend
    from bretzel.state.registry import StateRegistry, use_registry

    class Panier(SessionState):
        n: int = field(default=0)

    registre = StateRegistry(backend=MemoryBackend(), session_id="s")
    with use_registry(registre):
        vivant = Panier()
        vivant.n = 7
        # Le geste public d'hydratation depuis un dict.
        copie = type.__call__(Panier, key="autre")
        copie._apply_fields({"n": 99})
        assert copie is not vivant, (
            "hydrater a rendu l'instance vivante de la requête"
        )
        assert vivant.n == 7, (
            f"l'état vivant vaut {vivant.n} : hydrater l'a écrasé, ce qui "
            f"est exactement le défaut que `from_dict` produisait."
        )

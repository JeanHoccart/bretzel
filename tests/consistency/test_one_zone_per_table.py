"""Gate : une zone de rafraîchissement ne surveille qu'UN état de table.

Une zone se re-rend quand **n'importe lequel** de ses ``deps`` bouge.
Réunir plusieurs :class:`DatatableState` dans une seule ``deps=`` fait
donc payer, à chaque clic sur l'une des tables, le re-rendu de toutes
les autres — tri, recherche, filtres, pager, lignes compris.

Signalé par l'utilisateur comme « dès que je change de page ça charge
dans tous les sens » (2026-08-07), et la cause était dans l'exemple, pas
dans le composant ::

    @refreshable(deps=[SizeSmQuery, SizeMdQuery, SizeLgQuery])
    def size_ladder_panel() -> None:
        for size, query in SIZE_LADDER:
            ui.datatable(state=query, ...)

Trois tableaux complets reconstruits pour un clic sur l'un des trois.

⚠️ **Ce n'est PAS une interdiction de ``deps`` multiples.** Une zone a
souvent de bonnes raisons d'en surveiller plusieurs — l'aperçu du
playground serveur lit sa configuration ET sa pagination, et il DOIT se
re-rendre sur les deux. Ce que la gate refuse est plus étroit : deux
états qui portent chacun la requête de LEUR table, donc deux tables qui
se re-rendent l'une pour l'autre sans jamais avoir besoin l'une de
l'autre.

La détection est dynamique (on importe le module et on regarde si le nom
désigne bien une sous-classe de ``DatatableState``) parce qu'un nom seul
ne dit pas sa nature : ``deps=[Clicks, EventsQuery]`` mêle un state
ordinaire et un state de table, et c'est légitime.
"""

from __future__ import annotations

import ast
import importlib
import pathlib

import pytest

from bretzel.components import DatatableState
from tests.consistency._discovery import EXAMPLES_FLOOR, parsed_sources

#: Preuve de morsure : controle POSITIF — le balayage des zones trouve de vraies zones
#: decorees dans les exemples ; sans lui l'interdiction porterait sur
#: une liste vide.
MUTATION_PROOF = "test_the_sweep_is_not_vacuous"

_EXAMPLES = pathlib.Path(__file__).resolve().parents[2] / "examples"


def _zones() -> list[tuple[str, int, str, list[str]]]:
    """``(fichier, ligne, nom, états de table surveillés)`` par zone."""
    out: list[tuple[str, int, str, list[str]]] = []
    for source in parsed_sources(_EXAMPLES, floor=EXAMPLES_FLOOR):
        path, tree = source.path, source.tree
        module = None
        dotted = path.relative_to(_EXAMPLES.parent).with_suffix("")
        try:
            module = importlib.import_module(str(dotted).replace("\\", ".")
                                             .replace("/", "."))
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                name = (getattr(deco.func, "attr", None)
                        or getattr(deco.func, "id", None))
                if name != "refreshable":
                    continue
                for kw in deco.keywords:
                    if kw.arg != "deps" or not isinstance(kw.value, ast.List):
                        continue
                    tables = []
                    for elt in kw.value.elts:
                        if not isinstance(elt, ast.Name):
                            continue
                        obj = getattr(module, elt.id, None)
                        if (isinstance(obj, type)
                                and issubclass(obj, DatatableState)):
                            tables.append(elt.id)
                    out.append((str(path), node.lineno, node.name, tables))
    return out


ZONES = _zones()


@pytest.mark.parametrize(
    "path,line,name,tables", ZONES,
    ids=[f"{z[2]}:{z[1]}" for z in ZONES],
)
def test_zone_watches_at_most_one_table_state(
    path: str, line: int, name: str, tables: list[str]
) -> None:
    assert len(tables) <= 1, (
        f"{path}:{line} — {name}() surveille {len(tables)} états de "
        f"table ({', '.join(tables)}). Une zone se re-rend dès qu'UN de "
        f"ses deps bouge, donc un clic sur l'une de ces tables "
        f"reconstruit toutes les autres : lignes, en-têtes, filtres et "
        f"pager compris. Découpe en une zone par table — le contenu "
        f"commun peut vivre dans une fonction ordinaire appelée par "
        f"chacune."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Une découverte muette passerait pour un corpus sain."""
    assert len(ZONES) >= 40, len(ZONES)
    assert any(t for _, _, _, t in ZONES), (
        "aucune zone ne surveille d'état de table — la détection "
        "dynamique a cessé de résoudre les noms, donc la gate ne "
        "regarde plus rien."
    )

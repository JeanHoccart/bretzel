"""``Datatable`` — public surface of the datatable package.

:class:`~bretzel.state.Query` sort par cette porte, la même que
:class:`~bretzel.components.Move` — le type qu'un handler d'app doit
**nommer** pour écrire sa signature (``def load(q: Query)``). Elle voyage
avec :func:`apply_query`, qui est du composant : cinq des six call-sites
du dépôt les importent sur la même ligne.

:class:`~bretzel.state.datatable.DatatableState` sort par ici aussi, et
c'est délibéré : écrire un tableau demande le composant, son état,
``Query`` et ``apply_query``, et c'est UNE tâche. Le FICHIER, lui, est
descendu dans ``bretzel/state/datatable/`` le 2026-08-29 — il ne
dépendait de rien de cette couche — mais un déplacement de fichier n'est
pas un déménagement de porte. Il sortait de ``from bretzel import
DatatableState``, au premier étage, où il était le seul état de
composant.
"""

from bretzel.components.data.datatable.datatable import Datatable, apply_query
from bretzel.components.data.datatable.theme import DATATABLE_THEME
from bretzel.state.datatable import DatatableState, Query

__all__ = [
    "Datatable",
    "DatatableState",
    "DATATABLE_THEME",
    "Query",
    "apply_query",
]

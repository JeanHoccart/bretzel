"""Le schéma d'état d'un tableau et le message transmis à ses lecteurs.

- :class:`DatatableState` conserve les filtres, le tri et la pagination.
- :class:`Query` est le message immuable remis au callable ``rows=``.

Ces types vivent dans la couche ``state`` et sont aussi réexportés par
``bretzel.components`` pour accompagner ``ui.datatable`` et ``apply_query``.
:class:`~bretzel.state.LiveConnection` est un autre schéma fourni par le
framework ; les schémas ne dépendent pas de la couche ``components``.
"""

from bretzel.state.datatable.query import Query
from bretzel.state.datatable.state import DatatableState

__all__ = [
    "DatatableState",
    "Query",
]

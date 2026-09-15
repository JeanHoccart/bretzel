"""``Query`` — what the reader asked for, handed to a rows callable.

``ui.datatable(rows=…)`` takes two shapes :

- a **list** — the component searches, filters, sorts and pages it in
  Python. Zero handlers, and it covers most internal tools.
- a **callable** — you own the pipeline. It receives one of these and
  returns ``(rows, total)`` ::

      def load_issues(q: Query) -> tuple[list, int]:
          rows = Issue.query
          if q.search:
              rows = rows.filter(Issue.title.ilike(f"%{q.search}%"))
          for key, values in q.filters.items():
              rows = rows.filter(getattr(Issue, key).in_(values))
          if q.sort_key:
              rows = rows.order_by(q.order_by(Issue))
          total = rows.count()
          if not q.for_export:
              rows = rows.offset(q.offset).limit(q.per_page)
          return list(rows), total

The typed parameter is the same idiom as a typed form handler
(``def save(form: MyForm)``) and as the ``Move`` the drag primitive will
hand its ``on_move`` — one shape to learn for the whole framework.

**``for_export`` is why this object exists rather than four kwargs.** A
CSV must contain every matching row, not the twenty on screen, so the
export path sends the same query with paging switched off. A callable
that ignores the flag silently exports one page — hence the flag rides
*inside* the query, where it is impossible not to see.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Query:
    """One reader's view of a table : what to match, how to order, which slice.

    Frozen : a callable that mutated its query would change what the
    component believes it rendered.
    """

    #: Column key to order by. Empty string = source order.
    sort_key: str = ""
    #: ``"asc"`` / ``"desc"`` — only meaningful while ``sort_key`` is set.
    sort_dir: str = "asc"
    #: 1-indexed, to pair with ``ui.pagination``.
    page: int = 1
    per_page: int = 20
    #: Global search box, already stripped. Match it case-insensitively
    #: against whatever columns make sense for your source.
    search: str = ""
    #: ``{column_key: [selected values]}`` — only columns the reader
    #: actually narrowed appear. An absent key means "no filter", which
    #: is NOT the same as an empty list (that one matches nothing).
    filters: dict[str, list[str]] = field(default_factory=dict)
    #: ``True`` on the CSV path. Ignore it and you export one page.
    for_export: bool = False

    @property
    def offset(self) -> int:
        """Rows to skip — ``0`` when exporting, since paging is off."""
        return 0 if self.for_export else (max(1, self.page) - 1) * self.per_page

    @property
    def descending(self) -> bool:
        """Sugar for the ``reverse=`` / ``.desc()`` argument."""
        return self.sort_dir == "desc"

    def matches_filters(self, read: Any) -> bool:
        """Whether a row passes every active column filter.

        ``read`` is a ``(key) -> value`` accessor for one row. Exposed so
        a callable working over an in-memory source can reuse the exact
        comparison the component applies (stringified equality against
        the selected values), rather than guess at it.
        """
        for key, selected in self.filters.items():
            if not selected:
                return False
            if str(read(key)) not in selected:
                return False
        return True

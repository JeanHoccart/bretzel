"""The JS subterm shared by the windowing generators.

``limit_each(limit=)`` and ``paginate_each(page=)`` accept the same
shape — a literal integer OR a :class:`ClientBinding` — and render it in
the same client expression. Both modules carried an identical private
copy of it (``_limit_ref`` / ``_page_ref``, audit F53): two twin helpers
in the same family, free to diverge.

``Component.path_of`` did not cover the need: it only knows the binding
branch, not the integer fallback nor the parenthesising.
"""

from __future__ import annotations

from bretzel.state.scopes.client import ClientBinding


def window_ref(value: ClientBinding | int) -> str:
    """``value`` as a parenthesised JS subexpression.

    Parenthesised because the result is interpolated into a wider
    expression (an index comparison): without parentheses, a binding
    rendered as ``a || b`` would change the host expression's
    precedence.

    ``binding_path()`` is polymorphic — a ``ClientExpression`` already
    carries its prefix, a plain ``ClientBinding`` gets it added (cf.
    ``filter_each._query_js``).
    """
    if isinstance(value, ClientBinding):
        return f"({value.binding_path()})"
    return f"({int(value)})"


__all__ = ["window_ref"]

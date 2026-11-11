"""What the generators that hide rows on the client share.

``limit_each(limit=)`` and ``paginate_each(page=)`` accept the same
shape — a literal integer OR a :class:`ClientBinding` — and render it in
the same client expression.

``Component.path_of`` does not cover the need: it only knows the binding
branch, not the integer fallback nor the parenthesising.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from bretzel.render.iteration import _extract_key, key_segment
from bretzel.state.scopes.client import ClientBinding, ClientExpression


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


def shown_while(
    items: Iterable[Any],
    key: str | Callable[[Any], Any] | None,
    condition: Callable[[int, Any], str],
) -> Iterator[Any]:
    """Yield each item inside a wrapper shown while ``condition(index, item)``,
    a client expression, holds. The caller's loop body lands in the wrapper."""
    from bretzel.components import ui  # lazy : ui namespace is this package

    for index, item in enumerate(items):
        expr = ClientExpression(condition(index, item))
        with key_segment(_extract_key(item, key, index)), ui.vstack(visible=expr, gap="none"):
            yield item


__all__ = ["shown_while", "window_ref"]

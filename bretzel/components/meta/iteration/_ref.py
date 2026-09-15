"""Le sous-terme JS commun aux générateurs de fenêtrage.

``limit_each(limit=)`` et ``paginate_each(page=)`` acceptent le même
shape — un entier littéral OU une :class:`ClientBinding` — et le rendent
dans la même expression client. Les deux modules en portaient une copie
privée identique (``_limit_ref`` / ``_page_ref``, audit F53) : deux
helpers jumeaux dans la même famille, libres de diverger.

``Component.path_of`` ne couvrait pas le besoin : il ne connaît que la
branche binding, pas le repli entier ni le parenthésage.
"""

from __future__ import annotations

from bretzel.state.scopes.client import ClientBinding


def window_ref(value: ClientBinding | int) -> str:
    """``value`` en sous-expression JS parenthésée.

    Parenthésée parce que le résultat est interpolé dans une expression
    plus large (une comparaison d'index) : sans parenthèses, un binding
    rendu en ``a || b`` changerait la précédence de l'expression hôte.

    ``binding_path()`` est polymorphe — une ``ClientExpression`` porte
    déjà son préfixe, une ``ClientBinding`` simple se le voit ajouter
    (cf. ``filter_each._query_js``).
    """
    if isinstance(value, ClientBinding):
        return f"({value.binding_path()})"
    return f"({int(value)})"


__all__ = ["window_ref"]

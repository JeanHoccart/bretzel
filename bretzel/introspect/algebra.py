"""L'algèbre de binding client Python→JS — lue ET exécutée.

``state.x > 3`` devient ``… > 3`` dans un ``bz-show``. Cette
correspondance ne vivait qu'en prose, donc elle pouvait pourrir. Ce module
lit chaque opérateur / helper de ``ClientBinding`` vivant **et l'exécute
contre une sonde** pour capturer le JS réellement émis — c'est le gain
anti-rouille : l'exemple montré **est** la sortie réelle, pas une chaîne
recopiée à la main.

``ClientExpression`` hérite toute la surface — mais elle **redéfinit les
six mutateurs pour lever**, donc lire ``ClientBinding`` seul ne couvre pas
SA surface : la lecture est paramétrée par la classe, et les opérations
qu'une classe refuse ne figurent pas dans sa fiche.
"""

from __future__ import annotations

import inspect
from functools import cache

from bretzel.introspect.methods import describe_method_surface
from bretzel.introspect.model import CATEGORY_UNCLASSIFIED, AlgebraOp

# nom → (catégorie, « comment on l'écrit en Python ») — affichage seul.
_ALGEBRA_DISPLAY: dict[str, tuple[str, str]] = {
    "__eq__": ("comparaison", "x == y"),
    "__ne__": ("comparaison", "x != y"),
    "__lt__": ("comparaison", "x < y"),
    "__le__": ("comparaison", "x <= y"),
    "__gt__": ("comparaison", "x > y"),
    "__ge__": ("comparaison", "x >= y"),
    "eq": ("comparaison", "x.eq(y)"),
    "ne": ("comparaison", "x.ne(y)"),
    "lt": ("comparaison", "x.lt(y)"),
    "le": ("comparaison", "x.le(y)"),
    "gt": ("comparaison", "x.gt(y)"),
    "ge": ("comparaison", "x.ge(y)"),
    "between": ("comparaison", "x.between(lo, hi)"),
    "__add__": ("arithmétique", "x + y"),
    "__radd__": ("arithmétique", "y + x"),
    "__sub__": ("arithmétique", "x - y"),
    "__rsub__": ("arithmétique", "y - x"),
    "__mul__": ("arithmétique", "x * y"),
    "__rmul__": ("arithmétique", "y * x"),
    "__truediv__": ("arithmétique", "x / y"),
    "__floordiv__": ("arithmétique", "x // y"),
    "__mod__": ("arithmétique", "x % y"),
    "__neg__": ("arithmétique", "-x"),
    "__abs__": ("arithmétique", "abs(x)"),
    "__round__": ("arithmétique", "round(x, n)"),
    "to_fixed": ("arithmétique", "x.to_fixed(n)"),
    "__invert__": ("logique", "~x"),
    "__and__": ("logique", "x & y"),
    "__or__": ("logique", "x | y"),
    "not_": ("logique", "x.not_()"),
    "then_else": ("logique", "cond.then_else(a, b)"),
    "length": ("liste", "x.length()"),
    "contains": ("liste", "x.contains(v)"),
    "join": ("liste", "x.join(sep)"),
    "toggle": ("mutation", "x.toggle()"),
    "increment": ("mutation", "x.increment(n)"),
    "decrement": ("mutation", "x.decrement(n)"),
    "set": ("mutation", "x.set(v)"),
    "push": ("mutation", "x.push(v)"),
    "clear": ("mutation", "x.clear()"),
}

_ALGEBRA_DUNDERS = frozenset(n for n in _ALGEBRA_DISPLAY if n.startswith("__"))

# Seule la plomberie NON-dunder a besoin d'être écartée explicitement —
# ``describe_method_surface`` drope déjà tout dunder absent
# d'``include_dunders``, donc __init__ / __bool__ / __repr__ n'arrivent
# jamais jusqu'ici.
_ALGEBRA_SKIP = frozenset({"serialize_path", "binding_path"})

_CATEGORY_ORDER = {
    "comparaison": 0,
    "arithmétique": 1,
    "logique": 2,
    "liste": 3,
    "mutation": 4,
    CATEGORY_UNCLASSIFIED: 5,
}

# Les deux opérateurs binaires dont le second membre doit être un BINDING
# et non un littéral — ``x & 3`` n'a pas de sens, ``x & y`` si.
_BINARY_ON_BINDINGS = frozenset({"__and__", "__or__"})


def describe_client_algebra(cls: type | None = None) -> tuple[AlgebraOp, ...]:
    """Lit l'algèbre Python→JS d'une classe de binding, vivante.

    ``cls`` vaut ``ClientBinding`` par défaut — l'algèbre complète, ce que
    la doc vivante affiche.

    **Passer une sous-classe rend SA surface effective, et c'est
    load-bearing.** ``ClientExpression`` hérite les trente-quatre
    opérateurs et **redéfinit les six mutateurs pour LEVER**
    (``ReactivityError`` : une expression n'a pas de champ où écrire).
    Une fiche construite sur la classe de base annonçait donc
    ``x.toggle()`` avec son JS, sur la seule classe qui le refuse.

    Une méthode absente d':data:`_ALGEBRA_DISPLAY` sort en
    :data:`CATEGORY_UNCLASSIFIED` — la vue la montre quand même (rien
    n'est perdu) et ``test_docs_coverage`` rougit, pour qu'un mainteneur
    classe le nouvel opérateur exprès.
    """
    from bretzel.state import ClientBinding

    return _describe_client_algebra(cls or ClientBinding)


@cache
def _describe_client_algebra(cls: type) -> tuple[AlgebraOp, ...]:
    """Worker mis en cache — clé sur la classe, donc un dev-reload (nouvel
    objet classe) produit une nouvelle entrée, exactement comme le cache
    reload-safe de :func:`describe_state`. Sans lui, la boucle de 40
    sondes se rejouerait à chaque rendu de page."""
    probe, other = _probes(cls)
    ops = [
        AlgebraOp(
            name=method.name,
            category=category,
            python=python,
            js=js,
            returns_label=method.returns_label,
            doc=method.doc,
        )
        for method in describe_method_surface(
            cls, include_dunders=_ALGEBRA_DUNDERS, skip=_ALGEBRA_SKIP, inherited=True
        )
        for category, python in [
            _ALGEBRA_DISPLAY.get(method.name, (CATEGORY_UNCLASSIFIED, f"x.{method.name}(…)"))
        ]
        # Une opération que CETTE classe refuse n'est pas listée. La garder
        # sans JS se lirait « la sonde n'a pas su » ; la garder avec serait
        # un mensonge. L'absence est la seule lecture juste — et le refus
        # lui-même porte son message d'erreur, qui explique mieux que nous.
        for js, refused in [_probe_js(probe, other, method.name)]
        if not refused
    ]
    return tuple(sorted(ops, key=lambda o: (_CATEGORY_ORDER.get(o.category, 9), o.name)))


def _probes(cls: type) -> tuple[object, object]:
    """Deux instances de ``cls`` à qui poser les opérateurs.

    Les deux formes de construction du module d'état sont essayées dans
    l'ordre : celle d'un binding (quatre champs nommés) puis celle d'une
    expression (une source JS). Sans ceci, sonder ``ClientExpression``
    levait à la CONSTRUCTION, hors du ``try`` de la sonde.
    """
    try:
        return (
            cls(class_name="State", instance_key="default", field_name="x", value=0),
            cls(class_name="State", instance_key="default", field_name="y", value=0),
        )
    except TypeError:
        return cls("$bz.state.State.default.x"), cls("$bz.state.State.default.y")


def _probe_js(probe: object, other: object, name: str) -> tuple[str | None, bool]:
    """Appelle ``name`` sur la sonde et capture le JS émis.

    Rend ``(js, refusé)``. L'arité est lue sur la signature vivante (pas
    de table par méthode) : un opérateur logique binaire reçoit un second
    binding, les autres binaires un littéral, les ternaires deux
    littéraux. Best-effort — rend ``None`` si la forme ne colle pas, donc
    une méthode neuve ne casse jamais la page, elle s'affiche juste sans
    exemple.

    ``refusé`` distingue le second cas du premier : une classe qui LÈVE
    exprès (:class:`~bretzel.state.ReactivityError`) ne rate pas la
    sonde, elle répond non — et une opération refusée n'a rien à faire
    dans la fiche de la classe qui la refuse.
    """
    from bretzel.state import ReactivityError

    try:
        method = getattr(probe, name)
        required = [
            p
            for p in inspect.signature(method).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if not required:
            result = method()
        elif len(required) == 1:
            result = method(other if name in _BINARY_ON_BINDINGS else 3)
        else:
            result = method(1, 10)
    except ReactivityError:
        return None, True
    except Exception:
        return None, False
    if hasattr(result, "serialize_path"):
        return result.serialize_path(), False
    return (result if isinstance(result, str) else None), False

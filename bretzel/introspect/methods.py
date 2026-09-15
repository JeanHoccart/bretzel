"""La surface d'appelables d'un ESPACE DE NOMS — la primitive générique.

Certaines APIs **sont** leur surface de méthodes : le DSL d'opérateurs de
``ClientBinding``, un registre de décorateurs, tout builder fluent. Cette
primitive la lit vivante — nom, signature, retour, docstring — sans rien
savoir de ce qu'elle lit. Les couches spécialisées l'enrichissent
(cf. :mod:`bretzel.introspect.algebra`).

**Un espace de noms, pas une classe.** Le sujet réel est « un porteur
d'attributs + une liste de noms » : ``auth`` et ``oauth`` sont des
*modules* exportés au premier étage, et leur surface se lit exactement
comme celle d'une classe. Écrire la boucle une seconde fois pour eux
aurait donné deux sites de construction de :class:`MethodInfo` à tenir
synchronisés — c'est ce que la première version de
:mod:`bretzel.introspect.symbols` faisait.

**La réutiliser avant de relister à la main les appelables de quoi que ce
soit.**
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable

from bretzel.introspect._signature import describe_callable, type_label
from bretzel.introspect.model import MethodInfo


def describe_method_surface(
    cls: type,
    *,
    include_dunders: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
    inherited: bool = False,
) -> tuple[MethodInfo, ...]:
    """Tout ce qu'on peut appeler sur ``cls`` comme API publique.

    Par défaut, lit ``cls.__dict__`` — les méthodes PROPRES, pas la
    plomberie héritée d'``object``.

    ``inherited=True`` remonte la MRO (``object`` exclu) et rend la
    surface **effective** : ce qu'un appelant obtient réellement par
    ``getattr``, la définition la plus dérivée gagnant. Sans ce mode,
    ``ClientExpression`` — qui hérite trente-deux opérateurs et n'en
    redéfinit que six — avait une surface de six méthodes, ce qui n'est
    la réponse à aucune question qu'on lui pose.
    """
    return describe_namespace_surface(
        cls,
        _public_names(cls, inherited=inherited),
        include_dunders=include_dunders,
        skip=skip,
    )


def describe_namespace_surface(
    owner: object,
    names: Iterable[str],
    *,
    include_dunders: frozenset[str] = frozenset(),
    skip: frozenset[str] = frozenset(),
) -> tuple[MethodInfo, ...]:
    """Les appelables de ``names`` lus sur ``owner``, dans cet ordre.

    Garde les noms sans underscore, plus tout dunder explicitement nommé
    dans ``include_dunders`` (un DSL d'opérateurs veut ``__gt__`` dans sa
    surface), et écarte ce qui est dans ``skip``. Les signatures sont lues
    via :func:`describe_callable`, donc un paramètre renommé suit sans
    édition.
    """
    out: list[MethodInfo] = []
    for name in names:
        if name in skip or not _is_wanted(name, include_dunders):
            continue
        attr = getattr(owner, name, None)
        if not callable(attr):
            continue
        try:
            info = describe_callable(attr)
        except (TypeError, ValueError):
            continue
        out.append(
            MethodInfo(
                name=name,
                params=info.params,
                returns_label=return_label(attr),
                doc=info.doc,
            )
        )
    return tuple(out)


def _is_wanted(name: str, include_dunders: frozenset[str]) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return name in include_dunders
    return not name.startswith("_")


def _public_names(cls: type, *, inherited: bool) -> tuple[str, ...]:
    """Les noms à lire sur ``cls``, dédupliqués, la MRO dans l'ordre.

    ``dict.fromkeys`` plutôt qu'un ``set`` : l'ordre de déclaration est
    l'ordre d'affichage de la fiche, et la première occurrence en
    remontant la MRO est la définition qui gagne — la même que celle que
    ``getattr`` rendra.
    """
    if not inherited:
        return tuple(vars(cls))
    seen: dict[str, None] = {}
    for klass in cls.__mro__:
        if klass is object:
            continue
        seen.update(dict.fromkeys(vars(klass)))
    return tuple(seen)


def return_label(fn: object) -> str:
    try:
        annotation = inspect.signature(fn).return_annotation
    except (TypeError, ValueError):
        return "—"
    if annotation is inspect.Signature.empty:
        return "—"
    return type_label(annotation)

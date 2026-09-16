"""La fiche d'un symbole public qui n'est **pas** un ``ui.*``.

``describe`` savait tout dire de ``ui.button`` et rien de ``@page``. Sur
les 157 noms publics des sept modules, il ne rendait qu'une ligne
d'index — nom, nature, résumé coupé à 62 caractères — et ``describe page``
répondait « ``ui.page`` n'existe pas », ce qui est faux et oriente vers la
mauvaise conclusion. Une IA en tirait que ``@page`` existe sans jamais
pouvoir l'appeler.

**Rien n'est relisté ici.** La population ET son classement viennent de
:func:`~bretzel.introspect.modules.describe_module` — le même
:class:`~bretzel.introspect.model.SurfaceSymbol` qui alimente l'index — et
les quatre lectures de détail sont les primitives existantes appliquées
selon la nature du symbole. Ce module est un aiguillage, pas un cinquième
moteur.
"""

from __future__ import annotations

import importlib
import inspect
from functools import cache
from types import MappingProxyType

from bretzel.introspect._signature import describe_callable
from bretzel.introspect.algebra import describe_client_algebra
from bretzel.introspect.methods import describe_method_surface, describe_namespace_surface
from bretzel.introspect.model import MethodInfo, SurfaceSymbol, SymbolDetail
from bretzel.introspect.modules import describe_module, module_names, value_summary
from bretzel.introspect.state import describe_state


@cache
def _table() -> MappingProxyType[str, tuple[tuple[str, SurfaceSymbol], ...]]:
    """Nom public → ``((module, sa ligne d'index), …)``, ordre de lecture.

    Lit :func:`describe_module`, donc la population, la nature et la
    catégorie sont celles de l'index — une seule définition de « la
    surface publique d'un module couvert ». Les recalculer ici aurait
    laissé deux expressions de la même règle, et un classement recopié a
    déjà dérivé une fois dans ce dépôt pour exactement cette raison.

    Rendu en lecture seule : c'est un cache partagé par tous les
    appelants, et une mutation par mégarde corromprait tous les suivants.
    """
    rows: dict[str, list[tuple[str, SurfaceSymbol]]] = {}
    for module_name in module_names():
        for symbol in describe_module(module_name).symbols:
            rows.setdefault(symbol.name, []).append((module_name, symbol))
    return MappingProxyType({name: tuple(found) for name, found in rows.items()})


@cache
def symbol_owners() -> MappingProxyType[str, tuple[str, ...]]:
    """Nom public → les modules qui l'exportent, dans l'ordre de lecture.

    ``page``, ``refresh``, ``Feature`` et les ``*Error`` sortent de deux
    modules à la fois — le même objet ré-exporté par la façade. Le premier
    module de la liste est celui d'où on l'importe en pratique (``bretzel``
    vient en tête de :data:`~bretzel.introspect.modules.SECTIONS`), les
    suivants sont des chemins d'import également valides.
    """
    return MappingProxyType(
        {name: tuple(module for module, _ in rows) for name, rows in _table().items()}
    )


@cache
def symbol_names() -> tuple[str, ...]:
    """Tous les noms décrivables hors ``ui.*``, triés."""
    return tuple(sorted(_table()))


def describe_symbol(name: str) -> SymbolDetail:
    """La fiche d'un symbole public d'un module du framework.

    ``name`` s'écrit nu (``page``) ou qualifié (``bretzel.render.page``) —
    la forme qualifiée est ce qu'un traceback affiche, l'exiger dans un
    sens ou dans l'autre serait une friction gratuite.
    """
    bare, forced = _split(name)
    exported = _table().get(bare, ())
    rows = tuple(row for row in exported if row[0] == forced) if forced else exported
    if not rows:
        raise KeyError(f"`{name}` is not exported by any framework module")

    home, indexed = rows[0]
    value = getattr(importlib.import_module(home), bare)
    is_class = isinstance(value, type)
    # UN seul appel : c'est aussi le prédicat « est-ce une constante ? », et
    # son ``repr`` sur une grande valeur n'est pas gratuit.
    summary = value_summary(value)

    return SymbolDetail(
        name=bare,
        module=home,
        exported_by=tuple(module for module, _ in exported),
        also_known_as=_also_known_as(bare),
        category=indexed.category,
        kind=indexed.kind,
        # Une constante n'a pas de docstring : ``inspect.getdoc`` y rendrait
        # celle de son TYPE, le bruit que ``value_summary`` élimine déjà.
        doc=None if summary is not None else _docstring(value),
        signature=_signature(value),
        methods=_surface(value),
        value_repr=summary,
        algebra=describe_client_algebra(value) if is_class and _is_algebra(value) else (),
        state=_state(value) if is_class else None,
    )


def _also_known_as(bare: str) -> tuple[str, ...]:
    """Les autres surfaces qui portent ce nom.

    Un seul cas aujourd'hui, et il est piégeur : ``text`` est le composant
    ``ui.text`` **et** ``bretzel.render.text``, le mot du framework rendu
    dans la langue de l'app. Porté par la DONNÉE et non par le texte rendu,
    pour que les deux fiches le disent et que le JSON le porte aussi —
    :mod:`bretzel.introspect.model` promet que texte et JSON ne peuvent pas
    diverger, et une note collée au rendu aurait rendu cette promesse
    fausse d'exactement une ligne.
    """
    from bretzel.introspect.components import ui_symbol_names

    return (f"ui.{bare}",) if bare in ui_symbol_names() else ()


def _split(name: str) -> tuple[str, str | None]:
    """``bretzel.render.page`` → ``("page", "bretzel.render")``.

    Le module forcé n'est retenu que s'il est couvert : ``a.b.c`` sur un
    module inconnu retombe sur le nom nu, qui donnera l'erreur utile.
    """
    module, _, bare = name.rpartition(".")
    return (bare, module) if module in module_names() else (name, None)


def _docstring(value: object) -> str | None:
    """La docstring ENTIÈRE — c'est la différence avec l'index."""
    doc = inspect.getdoc(value)
    return doc.strip() if doc else None


def _signature(value: object):
    """La signature vivante, ou ``None`` quand elle n'apprend rien.

    Deux cas rendent ``None``. Un objet dont ``inspect`` ne sait pas lire
    la signature — un module, une constante : best-effort assumé, la fiche
    s'affiche sans plutôt que d'échouer entière. Et une signature
    **entièrement** en ``*args, **kwargs`` : les cinq classes de portée
    héritent celle d'``object``, et l'afficher sous « Paramètres »
    donnerait ``args`` et ``kwargs`` pour des noms de paramètres, ce qui
    est pire que se taire.

    ``info.params and all(…)`` : ``all(())`` vaut ``True``, donc sans
    l'opérande de gauche toute fonction SANS paramètre perdrait sa
    signature — et « zéro paramètre » est une réponse.
    """
    try:
        info = describe_callable(value)
    except (TypeError, ValueError):
        return None
    if info.params and all(p.kind in ("*args", "**kwargs") for p in info.params):
        return None
    return info


def _surface(value: object) -> tuple[MethodInfo, ...]:
    """Ce qu'on peut appeler SUR le symbole.

    Une classe rend ses méthodes publiques — sauf une classe d'algèbre,
    dont les opérateurs sont rendus par
    :attr:`~bretzel.introspect.model.SymbolDetail.algebra` avec leur forme
    Python et le JS émis, ce que la surface de méthodes ne porte pas.

    Un module rend son ``__all__``. ``auth`` et ``oauth`` sont des modules
    exportés au premier étage — sans ceci, leur fiche montrait la docstring
    et **rien d'appelable**, alors que ``auth.login`` est exactement ce
    qu'on vient y chercher. Lire ``vars()`` à la place donnerait 17 noms
    pour 6 : tout ce que le module importe.
    """
    if isinstance(value, type):
        return () if _is_algebra(value) else describe_method_surface(value)
    if not inspect.ismodule(value):
        return ()
    return describe_namespace_surface(value, getattr(value, "__all__", ()) or ())


def _is_algebra(cls: type) -> bool:
    """La classe **est**-elle son algèbre d'opérateurs ?

    Dérivé de l'héritage et non d'une liste de noms : ``ClientExpression``
    descend de ``ClientBinding``. C'est la CLASSE qui est passée à
    :func:`~bretzel.introspect.algebra.describe_client_algebra`, et non sa
    base — sans quoi la fiche de ``ClientExpression`` annonçait, JS à
    l'appui, les six mutateurs qu'elle redéfinit pour LEVER.
    """
    from bretzel.state import ClientBinding

    return issubclass(cls, ClientBinding)


def _state(cls: type):
    """La portée et les champs, si c'en est une classe d'état.

    Sur les cinq classes de base (``PageState``… ``ClientState``) les
    champs sont vides et c'est la **portée** qui porte toute
    l'information — la question qu'on se pose devant ``UserState`` est
    « combien de temps ça vit », pas « quels champs ».
    """
    from bretzel.state import ClientState, ServerState

    return describe_state(cls) if issubclass(cls, ServerState | ClientState) else None

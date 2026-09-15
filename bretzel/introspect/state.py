"""Les classes d'état, lues vivantes.

Portée / persistance, chaque champ avec son type, son défaut et ses
validateurs, les computed. C'est le miroir anti-rouille du chapitre État
de la doc vivante : ajouter un champ, câbler un validateur ou changer un
défaut se reflète au prochain rendu, sans une édition ici.

⚠️ Ce module décrit **une classe donnée**. Décrire le *module*
``bretzel.state`` lui-même — les quatre portées serveur, ``field`` /
``computed`` / ``validator``, et quel backend de persistance sert quelle
portée — appartient à l'item 3 du chantier et n'est **pas** ici. Ne pas
lire l'absence de ces sections comme « ce n'est pas introspectable ».
"""

from __future__ import annotations

import inspect
import typing
from functools import cache

from bretzel.introspect._signature import REQUIRED_LABEL, type_label
from bretzel.introspect.model import FieldInfo, StateInfo


@cache
def describe_state(cls: type) -> StateInfo:
    """Lit une sous-classe d'état vivante.

    Mise en cache sur ``cls`` : une classe d'état est immuable pour la
    durée du process, donc ``get_type_hints`` (la partie coûteuse) tourne
    une fois par classe et non une fois par rendu. En dev ``reload=True``,
    une édition produit un nouvel objet classe → une nouvelle clé de
    cache, donc le miroir reflète toujours le code tel qu'écrit.
    """
    from bretzel.state import MISSING, ClientState
    from bretzel.state.url import (
        AddressableFieldError,
        addressable_fields,
        would_publish,
    )

    is_client = issubclass(cls, ClientState)

    try:
        hints = typing.get_type_hints(cls)
    except Exception:
        hints = dict(getattr(cls, "__annotations__", {}))

    declared = cls._all_fields()  # {name: Field} — les field(...) seulement
    validators = getattr(cls, "__validators__", {}) or {}
    computed = getattr(cls, "__computed__", {}) or {}

    field_infos: list[FieldInfo] = []
    for name, hint in hints.items():
        # La métaclasse d'état range sa comptabilité en ClassVars dunder
        # (__validators__, __computed__, __scope__, __persist__) — cette
        # garde unique les écarte toutes en gardant les champs utilisateur.
        if name.startswith("__"):
            continue

        field_infos.append(
            FieldInfo(
                name=name,
                type_label=type_label(hint),
                default_label=_default_label(cls, name, declared, MISSING),
                validators=tuple(v.fn.__name__ for v in validators.get(name, [])),
            )
        )

    persist = getattr(cls, "__persist__", "memory") if is_client else None
    scope_label = f"persist={persist!r}" if is_client else getattr(cls, "__scope__", "?")

    # L'adressage se lit en DEUX temps parce qu'il se déclare en deux
    # temps : ``field(url="tri")`` NOMME, ``addressable=True`` ALLUME.
    # Ne rendre que l'effectif ferait disparaître les noms d'un
    # ``DatatableState`` non allumé — or c'est exactement là qu'un
    # lecteur les cherche, puisque sa sous-classe n'en écrit aucun.
    #
    # Les DEUX lectures viennent de ``state/url.py``, qui porte la règle.
    # La recopier ici pour la moitié « nommé » a tenu une heure : elle
    # sautait la validation, donc la fiche conseillait une déclaration
    # qui lève.
    url_error: str | None = None
    try:
        url_params = tuple(addressable_fields(cls).items())
        url_named = tuple(would_publish(cls).items())
    except AddressableFieldError as refus:
        # Une déclaration refusée lève au rendu, donc l'app ne tourne
        # pas — mais c'est ici qu'on vient comprendre POURQUOI, et une
        # fiche muette se lirait comme « cet état ne publie rien ».
        url_params, url_named, url_error = (), (), str(refus)

    return StateInfo(
        name=cls.__name__,
        family="ClientState" if is_client else "ServerState",
        scope=scope_label,
        persist=persist,
        doc=inspect.getdoc(cls),
        fields=tuple(field_infos),
        computed=tuple(computed.keys()),
        whole_validators=len(validators.get(None, [])),
        url_params=url_params,
        url_named=url_named,
        url_error=url_error,
    )


def _default_label(cls: type, name: str, declared: dict, missing: object) -> str:
    """Le défaut d'un champ, qu'il vienne d'un ``field(...)`` ou d'une
    annotation nue dont la valeur vit en attribut de classe dans la MRO."""
    if name in declared:
        field = declared[name]
        factory = getattr(field, "default_factory", None)
        if factory not in (None, missing):
            return f"{getattr(factory, '__name__', 'factory')}() (factory)"
        if field.default is missing:
            return REQUIRED_LABEL
        return repr(field.default)

    for klass in cls.__mro__:
        if name in vars(klass):
            return repr(vars(klass)[name])
    return REQUIRED_LABEL

"""Le catalogue ``ui.*`` — lu vivant, jamais recopié.

C'est la colonne anti-rouille du catalogue : ajouter une prop, câbler un
event, livrer une méthode impérative se reflète ici au prochain appel,
sans une édition. Un catalogue d'API recopié à la main double la sortie de
``bretzel describe``, donc il dérive plus vite qu'il ne sert
— c'est la leçon du skill ``bretzel-api``, supprimé le 2026-08-01 pour
avoir nommé deux composants inexistants et en avoir omis six livrés.

⚠️ **La source de vérité d'un composant est ``__reactive_props__`` moins
``SEALED_PROPS``, jamais ``inspect.signature(__init__)``.** Voir
:func:`_component_params` : les deux fautes possibles — cacher une prop
qui marche, annoncer une prop qui lève — envoient le même lecteur dans le
mur, et ce module les a commises toutes les deux le même jour.
"""

from __future__ import annotations

import inspect
from functools import cache

from bretzel.components.base import size_vocabulary
from bretzel.components.base.component import RESERVED_KWARGS
from bretzel.introspect._signature import (
    REQUIRED_LABEL,
    default_label,
    describe_callable,
    type_label,
)
from bretzel.introspect.model import (
    SOURCE_REACTIVE_PROP,
    ComponentInfo,
    HelperInfo,
    ParamInfo,
)

# ``RESERVED_KWARGS`` est un RÉ-EXPORT, pas une copie. Cette liste a existé
# en cinq exemplaires jusqu'au 2026-08-16 et deux avaient dérivé ; la
# source est désormais unique, dans le socle. Les kwargs universels sont
# volontairement absents des fiches — les répéter sur 104 entrées serait du
# bruit, et la règle est « pas de kwargs universels dans la signature
# d'API » (memory ``feedback_no_universal_kwargs_in_signature``).
# L'émetteur texte les annonce **une fois**, en tête d'index.
__all__ = ("RESERVED_KWARGS",)

# La nature d'un symbole ``ui.*`` qui n'est PAS un composant.
#
# ⚠️ C'était une table de 8 noms recopiée à la main jusqu'au 2026-08-16, et
# elle avait DÉJÀ dérivé à la naissance : ``drag_each`` manquait (classé
# « helper » alors qu'il est dans la même famille que les cinq listés) et
# ``abort`` était une clé morte (il n'y a pas d'``ui.abort`` — ``abort``
# vit dans ``bretzel.server.errors``). Dans le module dont la docstring
# cite le skill supprimé pour « deux noms inexistants, six omis ». La
# famille d'itération se DÉRIVE désormais de son ``__all__``.
_ITERATION_KIND = "iteration"

_DECLARED_HELPER_KINDS: dict[str, str] = {
    "notification": "fire-and-forget",
    "column": "descripteur",
}

HELPER_FALLBACK_KIND = "helper"


def helper_kind(ui_name: str) -> str:
    """La nature d'un symbole ``ui.*`` qui n'est pas un composant."""
    from bretzel.components.meta import iteration

    if ui_name in iteration.__all__:
        return _ITERATION_KIND
    return _DECLARED_HELPER_KINDS.get(ui_name, HELPER_FALLBACK_KIND)


def ui_symbol_names() -> tuple[str, ...]:
    """Tout symbole ``ui.<name>`` public, en ordre de déclaration."""
    from bretzel.components import ui

    return tuple(n for n in vars(type(ui)) if not n.startswith("_"))


@cache
def ui_name_of_class() -> dict[type, str]:
    """Classe de composant → son nom d'appel ``ui.*``.

    Lue sur le namespace ``ui`` lui-même, donc par IDENTITÉ. La version
    par orthographe (``cls.__name__.lower() == ui_name``) a vécu une
    heure et ratait **37 noms sur 48** : elle reconnaissait ``Button`` →
    ``button`` et manquait ``AccordionItem`` → ``accordion_item``,
    ``DatePicker`` → ``date_picker``, tout ce qui porte un underscore.
    Une carte qui ne couvre que les noms d'un seul mot est pire qu'une
    absence de carte : elle se vérifie très bien sur l'exemple qu'on a
    en tête.
    """
    from bretzel.components import ui

    return {
        value: name
        for name in ui_symbol_names()
        for value in [getattr(ui, name, None)]
        if isinstance(value, type)
    }


def _reactive_param(descriptor: object) -> ParamInfo:
    """Traduit un ``ReactivePropDescriptor`` en paramètre d'appel.

    ``kind="keyword-only"`` est exact et non approximatif : la prop arrive
    par ``**kwargs`` puis est routée par ``split_kwargs`` vers le seau des
    props réactives — elle n'est jamais positionnelle.

    Le défaut n'est PAS lu via ``resolve_default()`` : celui-ci *appelle*
    la factory, et une fiche n'a pas à exécuter du code applicatif pour
    s'afficher. Les trois cas restent donc explicites.
    """
    from bretzel.components.base.reactive_prop import MISSING

    if getattr(descriptor, "default_factory", None) is not None:
        default = "<factory>"
    elif getattr(descriptor, "default", MISSING) is not MISSING:
        default = default_label(descriptor.default)
    else:
        default = REQUIRED_LABEL

    return ParamInfo(
        name=descriptor.name,
        kind="keyword-only",
        type_label=type_label(getattr(descriptor, "declared_type", None)),
        default_label=default,
        source=SOURCE_REACTIVE_PROP,
    )


def _component_params(cls: type) -> tuple[ParamInfo, ...]:
    """Tout ce qu'on peut passer à l'appel, moins les kwargs universels.

    Deux sources, dans cet ordre :

    1. les paramètres **explicites** de l'``__init__`` — ils portent
       l'annotation et le défaut choisis par l'auteur, donc ils gagnent ;
    2. les **props réactives** de la classe, moins ses ``SEALED_PROPS``.

    (2) n'est pas un filet de sécurité, c'est le cœur du correctif.
    ``HStack`` retire ``justify``/``wrap`` de son ``__init__`` pour offrir
    une API réduite **mais les hérite de ``Flex`` comme props réactives** —
    donc ``ui.hstack(justify="between")`` marche. Lire le seul ``__init__``
    le déclarait indisponible, et un lecteur se rabattait sur
    ``classes="justify-between"`` : un contournement, exactement ce que ce
    module existe pour empêcher.

    ⚠️ **La soustraction de ``SEALED_PROPS`` est aussi load-bearing que
    l'union.** La première version de ce correctif n'avait que l'union et
    commettait la faute au signe opposé : elle annonçait
    ``ui.hstack(direction="col")``, qui **lève** (l'axe est l'identité du
    raccourci). Une fiche qui promet un paramètre refusé est aussi fausse
    qu'une fiche qui en cache un qui marche. Les deux sens sont gardés par
    ``tests/consistency/test_introspect_sees_inherited_props.py``, qui
    vérifie **en plus** qu'une prop scellée est vraiment refusée — sinon
    ``SEALED_PROPS`` deviendrait le moyen le plus court de faire taire la
    gate.
    """
    try:
        info = describe_callable(cls.__init__)
    except (ValueError, TypeError):
        signature_params: tuple[ParamInfo, ...] = ()
    else:
        signature_params = tuple(p for p in info.params if p.kind != "**kwargs")

    seen = {p.name for p in signature_params}
    seen.update(getattr(cls, "SEALED_PROPS", ()))
    reactive = getattr(cls, "__reactive_props__", None) or {}
    from_props = tuple(
        _reactive_param(descriptor)
        for name, descriptor in sorted(reactive.items())
        if name not in seen
    )
    return signature_params + from_props


def _handler_kwargs(params: tuple[ParamInfo, ...], events: tuple[str, ...]) -> tuple[str, ...]:
    """Les ``on_<event>=`` réellement acceptés — cf. ``ComponentInfo``.

    L'union est écrite dans CE sens (params d'abord) parce que
    ``cross_check_events`` garantit déjà ``events`` ⊆ params, à la
    définition de classe : la seconde moitié ne devrait jamais rien
    ajouter. On la garde quand même — elle coûte une ligne, et elle est ce
    qui fera remonter le jour où le socle perdrait cette garantie, plutôt
    que de perdre des events en silence.
    """
    from_params = [p.name for p in params if p.name.startswith("on_")]
    return tuple(dict.fromkeys(from_params + [f"on_{e}" for e in events]))


@cache
def _theme_vocabulary(cls: type) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Les noms que ``Theme(components={<clé>: …})`` accepte pour ``cls``.

    Le **cinquième** contrat introspectable, et le dernier arrivé : les
    quatre autres (``BINDABLE_PROPS``, ``EVENTS``, ``NAMED_SLOTS``,
    ``IMPERATIVE``) étaient lus ici depuis le début, le thème non — d'où
    l'impossibilité, jusqu'au 2026-08-16, d'écrire la moindre règle disant
    « ``crad`` n'est pas un composant » ou « ``rooot`` n'est pas un slot ».

    Un groupe dont la valeur n'est pas un dict est **scalaire** (16 cas
    mesurés) : il est listé avec zéro clé, ce qui le distingue d'une table
    vide et évite de chercher des clés là où il n'y en a pas.
    """
    theme = getattr(cls, "THEME", None)
    if not isinstance(theme, dict):
        return ()
    return tuple(
        # ``str(k)`` et non ``k`` : une clé de groupe n'est pas toujours une
        # chaîne. ``Heading.THEME["level_sizes"]`` est indexé par les
        # ENTIERS 1..6 (``level=`` est un int, cf. ``bretzel describe`` :
        # « accepte int, PAS string »). Sans la coercition, ce champ
        # annonçait ``tuple[str, ...]`` en portant des ints, et
        # ``bretzel describe heading`` levait un ``TypeError`` au
        # ``", ".join`` — livré cassé le 2026-08-16, rattrapé le jour même
        # par la gate qui rend les 104 fiches.
        (group, tuple(sorted(map(str, value))) if isinstance(value, dict) else ())
        for group, value in sorted(theme.items())
    )


#: Les props que le SOCLE résout par leur valeur, dans une table du thème
#: (``compose_class``). Deux, pas plus : les 24 autres groupes-tables sont
#: lus par le ``render`` de chaque composant, avec sa propre
#: correspondance prop → groupe, qu'aucune règle générale ne recompose.
_VALUE_ADDRESSED: tuple[str, ...] = ("variant", "size")


def prop_vocabulary() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``variant`` / ``size`` → valeurs acceptées.

    Le pendant de :func:`theme_vocabulary`, mais indexé par **prop** et non
    par groupe de thème — parce que les deux ne coïncident pas :
    ``variant`` lit bien les clés de ``variants``, tandis que ``size``
    demande la résolution des deux imbrications (cf.
    :attr:`ComponentInfo.size_values`).

    Un ensemble vide veut dire « pas de table, on ne juge pas » — trois
    composants acceptent ``variant=`` sans table (``bar_chart``,
    ``file_upload``, ``pie_chart``) et ``radio_group`` fait de même pour
    ``size=``.
    """
    out: dict[str, dict[str, frozenset[str]]] = {}
    for info in describe_components():
        if not isinstance(info, ComponentInfo) or not info.theme_key:
            continue
        entry = out.setdefault(info.theme_key, {})
        variants = dict(info.theme).get("variants", ())
        entry["variant"] = entry.get("variant", frozenset()) | frozenset(variants)
        entry["size"] = entry.get("size", frozenset()) | frozenset(info.size_values)
    return out


def theme_vocabulary() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``groupe`` → clés — ce que ``Theme(components={…})``
    peut nommer.

    Trois consommateurs, une seule dérivation : la règle de lint qui juge
    le vocabulaire, celle qui juge les valeurs de ``variant=``, et la
    validation au démarrage qui LÈVE. Les deux règles la construisaient
    chacune de son côté avant le 2026-08-16 — deux copies de la même
    boucle, donc deux façons de finir par ne plus dire la même chose que
    le runtime, et c'est le lint qu'on aurait cru.

    Indexé par ``THEME_KEY`` et non par le nom ``ui.*`` : huit composants
    diffèrent, et trois écrivent sous la clé d'un AUTRE
    (``sidebar_section`` → ``sidebar``). Les classes qui partagent une clé
    partagent le même objet ``THEME``, donc l'union est sans ambiguïté.
    """
    out: dict[str, dict[str, frozenset[str]]] = {}
    for info in describe_components():
        if not isinstance(info, ComponentInfo) or not info.theme_key:
            continue
        groups = out.setdefault(info.theme_key, {})
        for group, keys in info.theme:
            groups[group] = frozenset(keys)
    return out


def theme_shapes() -> dict[str, dict[str, dict[str, str]]]:
    """``THEME_KEY`` → groupe → clé → ``"str"`` ou ``"dict"`` — la FORME
    que le thème LIVRÉ donne à chaque entrée.

    Le pendant de :func:`theme_vocabulary`, qui rend les *noms* : ici on
    rend ce que ces noms valent, réduit à ce qui est décidable
    statiquement. Une surcharge qui garde le nom et change la forme
    n'est pas une extension du thème, c'est une faute — et c'est
    exactement le trou par lequel elle passe aujourd'hui, puisque
    ``theme-vocabulaire-inconnu`` exempte volontairement les groupes
    adressés par une valeur (y ajouter une clé est la façon supportée de
    déclarer sa propre variante).

    Ce que la forme décide, mesuré le 2026-09-10 sur ``ui.button`` :

    - écrire un **dict** là où le thème livre une **chaîne** fait
      disparaître TOUS les jetons du palier (``h-10 px-4 text-sm gap-2``
      → rien). Le composant rend nu, en 200, avec du HTML valide ;
    - écrire une **chaîne** là où il livre un **dict** lève
      ``AttributeError: 'str' object has no attribute 'get'`` au rendu —
      une levée qui ne nomme ni le thème, ni le composant, ni la clé.

    Seuls les groupes qui SONT des tables sont décrits : un groupe
    scalaire (16 cas, cf. :func:`_theme_vocabulary`) n'a pas d'entrées,
    donc pas de forme à comparer, et il est absent plutôt que vide.

    ⚠️ ``str(k)`` sur les clés, pour la même raison qu'en face :
    ``Heading.THEME["level_sizes"]`` est indexé par les ENTIERS 1..6.
    """
    from bretzel.components import ui

    out: dict[str, dict[str, dict[str, str]]] = {}
    for ui_name in sorted(ui_symbol_names()):
        cls = getattr(ui, ui_name)
        if not isinstance(cls, type):
            continue
        theme_key = getattr(cls, "THEME_KEY", "") or ""
        theme = getattr(cls, "THEME", None)
        if not theme_key or not isinstance(theme, dict):
            continue
        groups = out.setdefault(theme_key, {})
        for group, table in theme.items():
            if not isinstance(table, dict):
                continue
            entries = groups.setdefault(str(group), {})
            for key, value in table.items():
                entries[str(key)] = "dict" if isinstance(value, dict) else "str"
    return out


def describe_component(ui_name: str, cls: type) -> ComponentInfo:
    """Lit une sous-classe de ``Component`` : famille, tag, paramètres, et
    les CINQ contrats introspectables (``BINDABLE_PROPS`` / ``EVENTS`` /
    ``NAMED_SLOTS`` / ``IMPERATIVE`` / le vocabulaire de ``THEME``) plus
    ``AUTONAME_FROM`` et ``THEME_KEY``."""
    module = getattr(cls, "__module__", "") or ""
    parts = module.split(".")
    family = parts[2] if len(parts) > 2 and parts[1] == "components" else "?"

    raw_bindable = getattr(cls, "BINDABLE_PROPS", None)
    params = _component_params(cls)
    events = tuple(getattr(cls, "EVENTS", ()) or ())

    return ComponentInfo(
        ui_name=ui_name,
        class_name=cls.__name__,
        family=family,
        tag=getattr(cls, "DEFAULT_TAG", "div"),
        is_container=bool(getattr(cls, "IS_CONTAINER", True)),
        doc=inspect.getdoc(cls),
        params=params,
        bindable=tuple(raw_bindable or ()),
        bindable_audited=raw_bindable is not None,
        two_way=tuple(getattr(cls, "TWO_WAY_PROPS", ()) or ()),
        events=events,
        handler_kwargs=_handler_kwargs(params, events),
        named_slots=tuple(getattr(cls, "NAMED_SLOTS", ()) or ()),
        imperative=tuple(getattr(cls, "IMPERATIVE", ()) or ()),
        autoname_from=getattr(cls, "AUTONAME_FROM", None),
        theme_key=getattr(cls, "THEME_KEY", "") or "",
        theme=_theme_vocabulary(cls),
        size_values=tuple(sorted(size_vocabulary(getattr(cls, "THEME", None)))),
    )


def describe_ui_symbol(ui_name: str) -> ComponentInfo | HelperInfo:
    """Classe un symbole ``ui.<name>`` et le lit vivant.

    Les composants reçoivent la fiche de contrat complète ; les helpers
    (each / notification / column…) une fiche signature + docstring.
    """
    from bretzel.components import ui
    from bretzel.components.base.component import Component

    value = getattr(ui, ui_name)
    if isinstance(value, type) and issubclass(value, Component):
        return describe_component(ui_name, value)

    try:
        info = describe_callable(value)
        params, doc = info.params, info.doc
    except (TypeError, ValueError):
        params, doc = (), None
    return HelperInfo(
        ui_name=ui_name,
        kind=helper_kind(ui_name),
        params=params,
        doc=doc,
    )


def describe_components() -> tuple[ComponentInfo | HelperInfo, ...]:
    """Tout le catalogue ``ui.*``, trié par nom."""
    return tuple(describe_ui_symbol(n) for n in sorted(ui_symbol_names()))

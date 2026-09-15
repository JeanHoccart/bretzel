"""Les types métier qu'un champ d'état peut porter, et comment ils voyagent.

Un état se persiste en JSON — c'est ce que le magasin sait écrire, et le
refus du pickle est délibéré (RCE). Or les types du quotidien d'une app
métier n'y entrent pas : ``date``, ``Decimal``, ``UUID``, un ``Enum``.
Ce module dit comment chacun s'écrit et se relit.

Une table, deux usages
----------------------

La même table sert à ENCODER avant l'écriture et à DÉCODER à la lecture,
et le décodage est aussi ce qui coerce la chaîne d'un formulaire. Deux
tables auraient divergé au premier type ajouté.

Elle est indexée par TYPE et non par champ : un ``Decimal`` s'écrit
pareil partout, donc le déclarer une fois suffit. C'est aussi ce qui
laisse l'annotation porter l'information — ``montant: Decimal`` se lit
sans rien de plus dans ``field()``.

⚠️ Ne pas confondre avec ``merge=``. L'annotation dit ce que la valeur
EST, ``field()`` dit comment elle se COMPORTE : un ``Decimal`` est un
montant quel que soit son usage, tandis qu'un ``int`` est additif ou non
selon ce que l'app en fait — aucun type standard ne peut le dire.

"""

from __future__ import annotations

import datetime as _dt
import decimal
import types as _pytypes
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Literal, Union, get_args, get_origin

__all__ = ["register_type"]


@dataclass(frozen=True, slots=True)
class _Codec:
    """Comment un type s'écrit en JSON et se relit.

    ``subclasses`` dit que ce codec vaut aussi pour les HÉRITIERS du type
    inscrit. Son ``decode`` reçoit alors un argument de plus — la classe
    concrète —, seule information que la table ne porte pas.
    """

    encode: Callable[[Any], Any]
    decode: Callable[..., Any]
    subclasses: bool = False


#: Les types que ``json`` sait déjà écrire. Rien à encoder pour eux.
_JSON_NATIVE: Final[frozenset[type]] = frozenset(
    {str, int, float, bool, type(None), list, dict}
)

#: Les natifs SCALAIRES — ceux qui sortent de l'encodage sans même être
#: parcourus. ``list`` et ``dict`` en sont exclus : leurs éléments, eux,
#: peuvent demander un codec.
_JSON_SCALAR: Final[frozenset[type]] = frozenset(
    {str, int, float, bool, type(None)}
)

#: Type → codec. Peuplée par :func:`register_type`, y compris pour les
#: six que le framework connaît d'origine (juste en dessous).
_CODECS: dict[type, _Codec] = {}


def register_type(
    cls: type,
    *,
    encode: Callable[[Any], Any],
    decode: Callable[..., Any],
    subclasses: bool = False,
) -> None:
    """Déclarer comment ``cls`` s'écrit en JSON et se relit.

    ``encode`` reçoit une valeur et rend quelque chose que ``json``
    accepte (au plus simple : une ``str``). ``decode`` fait le retour ::

        from decimal import Decimal
        from bretzel.state import register_type

        register_type(Money, encode=str, decode=Money.parse)

    Une fois déclaré, le type s'utilise nu dans l'annotation et
    ``field()`` ne reçoit rien de plus ::

        class Panier(SessionState):
            total: Money = field(default_factory=Money.zero)

    Les six types du quotidien — ``date``, ``datetime``, ``time``,
    ``Decimal``, ``UUID`` et toute sous-classe d'``Enum`` — sont déjà
    connus : une app n'appelle cette fonction que pour SES classes.

    ``subclasses=True`` étend le codec aux HÉRITIERS du type inscrit, et
    ``decode`` reçoit alors ``(brut, classe_concrète)`` ::

        register_type(Ref, encode=str,
                      decode=lambda brut, cible: cible(brut),
                      subclasses=True)   # couvre RefClient, RefFournisseur…

    C'est par cette porte qu'``Enum`` s'inscrit lui-même, en bas de ce
    module.

    ⚠️ **Un aller-retour doit rendre l'égal.** ``decode(encode(v)) == v``
    est ce que le framework suppose partout : la photo prise à la lecture
    est comparée à la valeur courante pour décider quels champs écrire
    (cf. :meth:`~bretzel.state.registry.StateRegistry.write_one`). Un
    codec qui perd de l'information ferait donc réécrire un champ à
    chaque requête, sans que rien ne le signale — c'est pour cette raison
    que ``Decimal`` s'encode en ``str`` et non en ``float``.
    """
    if not isinstance(cls, type):
        raise TypeError(
            f"register_type attend une CLASSE, reçu {cls!r}. La table est "
            f"indexée par type — c'est ce qui permet à l'annotation de "
            f"porter l'information, sans rien ajouter dans field()."
        )
    _CODECS[cls] = _Codec(encode=encode, decode=decode, subclasses=subclasses)


# ── Les six que le framework connaît ────────────────────────────────────
#
# L'ordre n'a pas d'importance ici — la table est indexée par type
# exact — mais la remarque vaut d'être écrite : une ``datetime`` EST une
# ``date`` en Python. ``encode_value`` remonte l'héritage et s'appuie sur
# l'ordre du MRO pour trouver la plus précise ; ``decode_value``, qui
# tient le type DÉCLARÉ, cherche exact.
register_type(_dt.datetime, encode=_dt.datetime.isoformat,
              decode=_dt.datetime.fromisoformat)
register_type(_dt.date, encode=_dt.date.isoformat,
              decode=_dt.date.fromisoformat)
register_type(_dt.time, encode=_dt.time.isoformat,
              decode=_dt.time.fromisoformat)
# ``str`` et non ``float`` : c'est toute la raison d'être de ``Decimal``.
# Passer par un flottant rendrait ``Decimal("0.1")`` différent de
# lui-même après un aller-retour, et le registre réécrirait le champ à
# chaque requête en croyant qu'il a changé.
register_type(decimal.Decimal, encode=str, decode=decimal.Decimal)
register_type(uuid.UUID, encode=str, decode=uuid.UUID)
# ``Enum`` est une FAMILLE : c'est le seul des six dont le type déclaré
# est un HÉRITIER de celui qu'on inscrit (``teinte: Couleur``, codec sur
# ``Enum``). Il passe donc par ``subclasses=True``, exactement comme le
# ferait la classe de base d'une app — et n'est plus un cas à part.
register_type(
    Enum,
    encode=lambda membre: membre.value,
    decode=lambda brut, cible: cible(brut),
    subclasses=True,
)


def _codec_for_declared(type_: Any) -> _Codec | None:
    """Le codec d'un type DÉCLARÉ, familles comprises.

    Exact d'abord, puis l'héritage — mais un ancêtre ne compte que s'il
    s'est déclaré ``subclasses=True``. Sans cette condition, déclarer un
    champ ``datetime`` retomberait sur le codec de ``date`` (une
    ``datetime`` EST une ``date``) et perdrait l'heure en silence.
    L'ordre du MRO fait le reste : le plus précis gagne.
    """
    if not isinstance(type_, type):
        return None
    codec = _CODECS.get(type_)
    if codec is not None:
        return codec
    for ancetre in type_.__mro__[1:]:
        codec = _CODECS.get(ancetre)
        if codec is not None and codec.subclasses:
            return codec
    return None


def encode_value(value: Any) -> Any:
    """Rendre ``value`` sous une forme que ``json`` accepte.

    Appelé par le registre AVANT de tendre quoi que ce soit au magasin —
    donc une seule fois, pour les deux backends. La mémoire et Redis voient
    ainsi la même représentation sérialisée.

    Descend dans les conteneurs, et son jumeau :func:`decode_value` en
    fait autant : c'est cette SYMÉTRIE qui permet d'écrire
    ``list[date]`` ou ``dict[str, Decimal]`` sans règle à retenir.

    Une valeur inconnue passe telle quelle : c'est au magasin de la
    refuser, avec le message qui nomme le champ.
    """
    # Sortie rapide sur ce que ``json`` écrit déjà, et c'est le cas de la
    # quasi-totalité des champs. Sans elle, chaque valeur payait une
    # remontée de MRO avant même de regarder la table. Mesuré le
    # 2026-09-06 : 381 ns → 168 ns par scalaire, et 387 µs → 137 µs sur
    # une liste de 1 000 chaînes, où l'encodeur « qui ne fait rien »
    # coûtait 6,7 fois ``json.dumps`` de la même liste.
    if type(value) in _JSON_SCALAR:
        return value
    # ⚠️ On remonte l'HÉRITAGE ici SANS exiger ``subclasses`` : à
    # l'encodage on tient une valeur concrète, pas un type déclaré, et le
    # framework fabrique lui-même des sous-classes de ``date``
    # (``_BoundDate``, posé sur une valeur lue pendant un rendu pour
    # qu'elle porte le nom de son champ). Recopier un champ date d'un
    # autre rangeait donc un objet que la table ne trouvait pas : il
    # partait nu au magasin, la mémoire l'acceptait, Redis levait.
    # L'ordre du MRO donne la bonne réponse sans arbitrage.
    for ancetre in type(value).__mro__:
        codec = _CODECS.get(ancetre)
        if codec is not None:
            return codec.encode(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        # ``tuple`` et ``set`` sortent en LISTE — json ne connaît qu'elle.
        # ``decode_value`` les reconstruit depuis le type déclaré, ce qui
        # est exactement ce qui permet de les accepter.
        return [encode_value(v) for v in value]
    if isinstance(value, dict):
        return {encode_value(k): encode_value(v) for k, v in value.items()}
    return value


def decode_value(type_: Any, raw: Any) -> Any:
    """Relire ``raw`` comme un ``type_``, ou le rendre inchangé.

    Sert DEUX chemins d'un coup, et c'est voulu : l'hydratation depuis le
    magasin et l'écriture d'un formulaire passent toutes deux par
    :meth:`Field.__set__`. Une ``date`` relue et une ``date`` saisie
    suivent donc exactement le même code.

    **Descend dans les conteneurs**, symétriquement à
    :func:`encode_value`. Tant qu'il ne le faisait pas, un ``list[date]``
    s'écrivait en ``["2026-01-01"]`` et se relisait en chaînes : le
    framework devait REFUSER ce champ à la déclaration, et c'était une
    règle de plus à retenir. La symétrie la supprime.
    """
    if raw is None or type_ is Any:
        # ⚠️ Any est une CLASSE depuis Python 3.11, donc il passe le
        # isinstance(type_, type) plus bas et fait lever
        # isinstance(raw, Any). C'est l'échappatoire déclarée : on ne
        # touche à rien, par définition.
        return raw
    origin = get_origin(type_)

    # ── Conteneurs : on décode les ÉLÉMENTS, puis on rebâtit ──────────
    if origin in (list, set, frozenset, tuple):
        args = [a for a in get_args(type_) if a is not Ellipsis]
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return raw
        if args and len(args) == 1:
            elements = [decode_value(args[0], v) for v in raw]
        elif args and origin is tuple:
            # ``tuple[date, date]`` : un type PAR position.
            elements = [
                decode_value(args[i], v) if i < len(args) else v
                for i, v in enumerate(raw)
            ]
        else:
            elements = list(raw)
        return origin(elements)
    if origin is dict:
        if not isinstance(raw, dict):
            return raw
        args = get_args(type_)
        if len(args) == 2:
            return {
                decode_value(args[0], k): decode_value(args[1], v)
                for k, v in raw.items()
            }
        return raw

    target = _unwrap_optional(type_)
    if target is None:
        return raw
    # « Déjà du bon type, on ne touche pas » — un handler qui écrit un
    # vrai ``date`` ne paie pas un aller-retour par chaîne.
    if isinstance(raw, target):
        return raw
    codec = _codec_for_declared(target)
    if codec is None:
        return raw
    # Une FAMILLE reçoit la classe concrète : c'est la seule information
    # que la table ne porte pas, et c'est ce qui permet à ``Enum`` de
    # s'inscrire par la porte publique au lieu d'être un cas à part.
    return codec.decode(raw, target) if codec.subclasses else codec.decode(raw)


def _unwrap_optional(type_: Any) -> Any:
    """``T | None`` → ``T``. Toute autre union rend ``None``.

    Même règle que la coercition scalaire (``_resolve_scalar_target``) :
    on ne déballe que lorsque ``None`` est le SEUL autre membre. Une
    union véritable n'a pas de cible unique, donc rien à décoder.
    """
    if isinstance(type_, type):
        return type_
    origin = get_origin(type_)
    if origin is Union or origin is _pytypes.UnionType:
        autres = [a for a in get_args(type_) if a is not type(None)]
        if len(autres) == 1 and isinstance(autres[0], type):
            return autres[0]
    return None


def is_storable(type_: Any) -> bool:
    """Le type déclaré peut-il ARRIVER jusqu'au magasin, ET en revenir ?

    Lu par la métaclasse pour refuser au DÉMARRAGE un champ qui ne
    pourrait pas se persister — plutôt qu'à la première écriture,
    c'est-à-dire en production, le magasin mémoire du dev l'ayant laissé
    passer.

    **Une seule règle, appliquée récursivement** : un type passe s'il a
    un codec (directement ou par sa famille), s'il est natif pour
    ``json``, si c'est un conteneur dont les éléments passent, une union
    dont les membres passent, un ``Literal`` de constantes — ou ``Any``,
    l'échappatoire assumée, où c'est le magasin qui arbitre.

    Il n'y a plus d'exception à retenir : ``list[date]``,
    ``dict[str, Decimal]``, ``tuple[date, date]`` et ``set[UUID]``
    passent, parce que l'encodage et le décodage descendent tous les deux
    dans les conteneurs depuis le 2026-09-06.
    """
    if type_ is None or type_ is Any:
        return True
    if isinstance(type_, type):
        return type_ in _JSON_NATIVE or _codec_for_declared(type_) is not None
    origin = get_origin(type_)
    if origin is Literal:
        return all(
            v is None or type(v) in _JSON_NATIVE for v in get_args(type_)
        )
    if origin is Union or origin is _pytypes.UnionType:
        return all(is_storable(a) for a in get_args(type_))
    if origin in (list, dict, tuple, set, frozenset):
        # ``tuple`` / ``set`` sortent en LISTE et sont RECONSTRUITS au
        # décodage depuis le type déclaré. Les refuser était une règle
        # de plus sans contrepartie.
        return all(
            a is Ellipsis or is_storable(a) for a in get_args(type_)
        )
    return False

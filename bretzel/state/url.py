"""Les champs d'état qu'une app rend **adressables** — l'URL comme état.

Un `PageState` vit dans un dictionnaire serveur indexé par un uuid de
rendu, **neuf à chaque navigation**. C'est ce qui fait qu'un filtre ne
survit ni à un changement de page ni au bouton retour : le retour refait
un vrai GET, obtient un uuid neuf, et arrive sur une URL qui ne dit rien
de la vue.

Ce module donne le seul remède qui tienne dans un framework
serveur-driven : **déclarer les champs dont l'URL fait foi.**

    class Issues(DatatableState, addressable=True):
        per_page: int = field(default=25)

    # /issues?tri=title&sens=desc&p=3

Une ligne. Les noms viennent du framework — ``DatatableState`` les porte
sur ses champs (``field(default="", url="tri")``) — et l'app décide
seulement de PUBLIER. Pour renommer, ou pour un état maison, le dict
reste :

    class Filters(PageState):
        status: str = field(default="all")
        URL = {"status": "statut"}

## Trois décisions, et pourquoi

**0. Le nommage et la DÉCISION sont séparés.** C'est ce qui permet
l'opt-in d'une ligne sans rien publier par accident : ``field(url=…)``
ne fait que *nommer*, ``addressable=True`` seul *allume*. Un champ que le
framework n'a pas nommé ne peut donc pas être allumé — c'est ainsi que
``filters`` reste hors de l'URL par construction, et pas par consigne.

**1. Opt-in, jamais automatique.** Le pont a déjà rencontré la version
automatique et l'a — à raison — traitée comme une fuite :
``05_bridge.js`` retire le magasin client des GET de navigation pour ne
pas produire ``?ColorScheme.default.mode=dark&HubFilter...``. La faute
n'était pas de mettre de l'état dans l'URL, c'était de **tout** y mettre.
Un champ déclaré est un champ **PUBLIC** : il part dans l'historique du
navigateur, dans les logs du serveur, et dans l'en-tête ``Referer`` de la
requête suivante. C'est pourquoi ``filters`` n'est adressable dans aucun
défaut du framework (décision du 2026-08-29) : c'est le champ le plus
susceptible de porter une donnée sensible.

⚠️ Si un filtre doit **survivre** sans être publié, ce n'est pas l'URL
qu'il faut, c'est la PORTÉE : ``class Issues(DatatableState,
scope="session")`` et il traverse les navigations, côté serveur, sans
rien exposer. Mesuré. Ni mécanisme neuf, ni mémoire navigateur à
bricoler.

**2. Le nom d'URL est ÉCRIT, pas dérivé du nom Python.** Trois raisons :
une URL est une API publique, donc un renommage de champ casserait des
favoris et des liens partagés ; ``?Issues.sort_key=title`` est
exactement la forme rejetée ci-dessus ; et deux tables sur une page
entrent en collision — un nom explicite force à trancher plutôt qu'à
subir.

**3. L'URL fait foi AU RENDU, et une mutation écrit les deux.** Comme
chaque mutation d'un champ déclaré pousse une URL neuve, les deux ne
peuvent pas diverger. Le ``page_id`` cesse d'être pertinent pour ces
champs-là — ce qui est précisément le but.

## Ce que ce module ne fait pas

Il ne connaît ni la requête ni la réponse : la couche ``state`` est sous
``render`` et ``server`` dans le DAG, et elle ne remonte pas. Les
paramètres lui **arrivent par valeur** (``StateRegistry(url_params=…)``,
comme ``page_id`` et ``session_id`` avant eux), et l'URL poussée est
composée par l'appelant. Ce fichier ne porte que le contrat et les deux
conversions.
"""

from __future__ import annotations

from typing import Any

from bretzel.core.errors import BretzelError
from bretzel.state.fields.descriptor import MISSING

#: « ce champ n'a pas de défaut » — distinct de ``None``, qui EST un
#: défaut légitime et doit donc disparaître de l'URL comme les autres.
_NO_DEFAULT: Any = object()

__all__ = [
    "AddressableFieldError",
    "addressable_fields",
    "apply_url_params",
    "collect_url_params",
    "would_publish",
]


class AddressableFieldError(BretzelError):
    """Déclaration ``URL`` invalide, ou deux états qui réclament le même nom."""


def _default_of(cls: Any, field_name: str) -> Any:
    """Le défaut déclaré du champ, ou ``_NO_DEFAULT`` s'il n'en a pas."""
    fld = cls._all_fields().get(field_name)
    if fld is None:
        return _NO_DEFAULT
    if fld.default_factory is not None:
        return fld.default_factory()
    default = getattr(fld, "default", _NO_DEFAULT)
    return _NO_DEFAULT if default is MISSING else default


def addressable_fields(cls: type) -> dict[str, str]:
    """``{nom de champ: nom de paramètre}`` déclaré par ``cls``.

    Vide — donc inerte — pour toute classe qui ne déclare rien, ce qui
    est le défaut de tout le framework.

    Lève sur une déclaration qui ne peut pas marcher, plutôt que de la
    laisser passer : un nom de champ inexistant ne produirait aucune
    erreur au rendu, juste une URL qui ne fait rien — le mode d'échec le
    plus coûteux à diagnostiquer.
    """
    # Deux sources, dans cet ordre — la seconde peut RENOMMER la première.
    #
    #   1. ``addressable=True`` sur la classe allume tout champ portant un
    #      ``field(url="…")``. C'est l'opt-in d'une ligne : le nommage
    #      vient du framework, la décision de publier vient de toi.
    #   2. ``URL = {champ: nom}`` renomme, ajoute, ou sert seule quand la
    #      classe n'a pas déclaré de noms par champ.
    #
    # Un champ SANS ``url=`` n'est jamais allumé par ``addressable=True``
    # — c'est ce qui fait que ``filters`` reste hors de l'URL sans qu'une
    # ligne de doc ait à le rappeler : le framework ne lui a pas donné de
    # nom, donc il n'y a rien à allumer.
    if getattr(cls, "__addressable__", False):
        return would_publish(cls)
    declared = _declared_map(cls)
    return _validated(cls, declared) if declared else {}


def would_publish(cls: type) -> dict[str, str]:
    """Ce qu'``addressable=True`` publierait — VALIDÉ, donc vrai.

    La même lecture que :func:`addressable_fields`, l'interrupteur forcé
    sur ON. Sert à qui doit montrer le nommage d'une classe qui ne
    publie pas encore (``describe``, et sa ligne « éteint »).

    ⚠️ **Elle valide.** La version qui se contentait de lire les ``url=``
    a vécu une heure : sur un état nommant un champ ``dict``, elle
    répondait « ``addressable=True`` publierait filtres→f » — un conseil
    qui LÈVE dès qu'on le suit, puisque c'est exactement ce que le garde
    des structures refuse. Une fiche qui décrit une déclaration
    impossible est pire que muette.
    """
    merged = {**_named_map(cls), **_declared_map(cls)}
    return _validated(cls, merged) if merged else {}


def _named_map(cls: Any) -> dict[str, str]:
    """Les champs que le framework a NOMMÉS — le nommage, pas la décision."""
    return {
        name: fld.url
        for name, fld in cls._all_fields().items()
        if getattr(fld, "url", None)
    }


def _declared_map(cls: Any) -> dict[str, str]:
    """Le ``URL = {…}`` de la classe, dont la FORME est vérifiée ici.

    Le contrôle vit dans le lecteur et non chez ses deux appelants : une
    déclaration mal formée doit se dire aussi bien à qui publie qu'à qui
    demande seulement ce qui serait publié.
    """
    declared = getattr(cls, "URL", None)
    if not declared:
        return {}
    if not isinstance(declared, dict):
        raise AddressableFieldError(
            f"{cls.__name__}.URL doit être un dict {{champ: nom d'URL}}, "
            f"pas un {type(declared).__name__}. Le nom d'URL s'écrit — il "
            f"n'est pas dérivé du nom Python, parce qu'une URL est une API "
            f"publique qu'un renommage de champ ne doit pas casser."
        )
    return dict(declared)


def _validated(cls: Any, declared: dict[str, str]) -> dict[str, str]:
    """Les mêmes gardes, quelle que soit la source de la déclaration.

    Extraite pour que ``addressable=True`` et ``URL = {…}`` ne puissent
    pas diverger : un champ inconnu, un nom vide, une collision interne
    ou une structure non sérialisable sont refusés des deux côtés.

    ⚠️ Ses messages ne disent plus « ``X.URL`` déclare » : depuis
    qu'elle sert aussi :func:`would_publish`, la faute peut venir d'un
    ``field(url=…)`` et désigner le dict ``URL`` enverrait chercher une
    ligne qui n'existe pas.
    """
    # ``_all_fields`` est l'énumération canonique d'un ``State`` — celle
    # que le registre diffe. Redeviner par ``dir()`` ramasserait
    # ``errors`` / ``to_dict`` et accepterait ``URL = {"to_dict": …}``.
    known = set(cls._all_fields())

    seen: dict[str, str] = {}
    for field_name, param in declared.items():
        if field_name not in known:
            raise AddressableFieldError(
                f"{cls.__name__} nomme {field_name!r} pour l'URL, qui n'est pas "
                f"un champ de cet état. Champs connus : "
                f"{sorted(known)}. Sans ce garde, l'URL ne ferait "
                f"simplement rien — sans lever, sans trace."
            )
        if not isinstance(param, str) or not param:
            raise AddressableFieldError(
                f"{cls.__name__} : le nom d'URL de {field_name!r} doit être un "
                f"nom de paramètre non vide, pas {param!r}."
            )
        if param in seen:
            raise AddressableFieldError(
                f"{cls.__name__} : {field_name!r} et {seen[param]!r} "
                f"réclament tous deux le paramètre {param!r}. Le dernier "
                f"écrirait l'autre en silence."
            )
        default = _default_of(cls, field_name)
        if isinstance(default, (dict, list, set, tuple)):
            raise AddressableFieldError(
                f"{cls.__name__} nomme {field_name!r} pour l'URL, dont la valeur "
                f"est un {type(default).__name__}. Une query ne porte que "
                f"des chaînes, et il n'existe pas encore de format pour "
                f"celle-là : la valeur d'URL remplacerait la structure par "
                f"une chaîne, et le premier `.get()` du composant "
                f"casserait — SANS que la déclaration n'ait rien signalé. "
                f"C'est le cas de `filters` sur un datatable. Il "
                f"redeviendra déclarable quand un encodage sera choisi ; "
                f"en attendant, adresse les champs SCALAIRES (tri, page, "
                f"recherche) et laisse le filtre vivre dans l'état."
            )
        seen[param] = field_name
    return dict(declared)


def _coerce(current: Any, raw: str) -> Any:
    """Le paramètre d'URL, ramené au type du champ.

    Une query n'a que des chaînes. On lit le type sur la valeur COURANTE
    plutôt que sur l'annotation : c'est ce dont dispose un état déjà
    construit, et ça suit un défaut changé sans redemander la classe.

    Best-effort et jamais levant — une URL est saisie par un humain et
    bricolée par des robots. Un ``?p=banane`` doit rendre la page, pas
    une 500 ; la valeur illisible est ignorée, donc le défaut tient.
    """
    if isinstance(current, bool):
        low = raw.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        return current
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            return current
    if isinstance(current, float):
        try:
            return float(raw)
        except ValueError:
            return current
    return raw


def apply_url_params(instance: Any, params: dict[str, str]) -> list[str]:
    """Semer les champs déclarés depuis ``params``. Rend les noms touchés.

    **Absent = on ne touche à rien.** C'est ce qui fait que la mécanique
    marche sur une action, dont l'URL ne porte aucune query : l'état
    garde ce qu'il avait, le handler le mute, et l'appelant pousse la
    nouvelle URL.

    ⚠️ À appeler AVANT la photo de référence du registre, sinon le
    semis se lit comme une mutation : l'état partirait ``dirty`` et
    pousserait une URL au premier rendu, sans que rien n'ait bougé.
    """
    if not params:
        return []
    touched: list[str] = []
    for field_name, param in addressable_fields(type(instance)).items():
        if param not in params:
            continue
        current = getattr(instance, field_name)
        value = _coerce(current, params[param])
        if value != current:
            setattr(instance, field_name, value)
        touched.append(field_name)
    return touched


def collect_url_params(instances: list[Any]) -> dict[str, str]:
    """``{paramètre: valeur}`` pour tous les champs déclarés de ``instances``.

    **Un champ à sa valeur par défaut n'apparaît pas.** C'est le pendant
    exact de la lecture (« absent = on ne touche à rien ») : les deux
    sens s'accordent, donc un aller-retour par l'URL est fidèle. Et ça
    évite qu'une table qu'on vient seulement de trier affiche
    ``?sort=name&dir=asc&p=1&q=`` — trois paramètres sur quatre pour
    dire « comme d'habitude ». Une URL doit se lire.

    Lève quand deux états d'une MÊME page réclament le même paramètre.
    Le contrôle est ici — donc par requête — et pas dans une table de
    noms réservés au niveau module : un registre global mutable est
    interdit (anti-règle 2), et surtout la collision n'est une faute que
    si les deux états se rencontrent VRAIMENT.
    """
    out: dict[str, str] = {}
    owner: dict[str, str] = {}
    for instance in instances:
        cls = type(instance)
        for field_name, param in addressable_fields(cls).items():
            if param in owner and owner[param] != cls.__name__:
                raise AddressableFieldError(
                    f"{cls.__name__} et {owner[param]} réclament tous deux "
                    f"le paramètre d'URL {param!r} sur la même page. L'un "
                    f"écraserait l'autre à chaque navigation. Donne à l'un "
                    f"des deux un nom distinct dans son ``URL = {{…}}``."
                )
            owner[param] = cls.__name__
            value = getattr(instance, field_name)
            if value == _default_of(cls, field_name):
                out.pop(param, None)
                continue
            out[param] = "" if value is None else str(value)
    return out

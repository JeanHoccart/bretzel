"""Les dataclasses de l'introspection — **et rien d'autre**.

Ce module ne contient **aucune logique**, volontairement. C'est le
*contrat* : un consommateur tiers (la doc vivante, un générateur, un
serveur MCP) importe ces types **en process** plutôt que de parser du
texte, et les émetteurs de :mod:`bretzel.introspect.emit` ne sont que des
projections de ces objets. Deux conséquences voulues :

- **texte et JSON ne peuvent pas diverger** — ils lisent la même donnée ;
- ajouter un champ ici le rend disponible aux deux d'un coup, et
  :data:`SCHEMA_VERSION` dit au consommateur que la forme a bougé.

:data:`SCHEMA_VERSION` suit le versionnement sémantique **de la forme des
dataclasses**, pas celle du framework : un champ ajouté → mineure, un
champ retiré ou renommé → majeure.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "2.0"

# Comment un paramètre atteint le composant. La distinction est
# *load-bearing*, pas cosmétique : voir ``_component_params`` — un
# composant peut retirer une prop de son ``__init__`` tout en l'héritant
# comme prop réactive, et l'appel reste valide.
SOURCE_SIGNATURE = "signature"
SOURCE_REACTIVE_PROP = "prop réactive"

#: La catégorie d'un symbole que personne n'a classé. Elle existe pour que
#: rien ne soit *perdu* — la vue montre quand même le symbole — pendant que
#: ``tests/consistency/test_docs_coverage.py`` rougit, ce qui force un
#: mainteneur à le classer **exprès**. C'est le cran d'arrêt : on n'élargit
#: pas une surface publique sans dire à quoi elle sert.
CATEGORY_UNCLASSIFIED = "autre"


@dataclass(frozen=True)
class ParamInfo:
    """Un paramètre acceptable à l'appel."""

    name: str
    kind: str  # "positionnel" | "keyword-only" | "*args" | "**kwargs"
    type_label: str
    default_label: str  # repr de la valeur, ou "— (requis)"
    source: str = SOURCE_SIGNATURE  # SOURCE_* ci-dessus


@dataclass(frozen=True)
class CallableInfo:
    """N'importe quel appelable lu à sa signature vivante."""

    name: str
    params: tuple[ParamInfo, ...]
    doc: str | None


@dataclass(frozen=True)
class ComponentInfo:
    """Une entrée ``ui.*`` qui est une sous-classe de ``Component``."""

    ui_name: str  # "button" — l'attribut sur ``ui``
    class_name: str  # "Button"
    family: str  # "actions"
    tag: str  # DEFAULT_TAG
    is_container: bool
    doc: str | None
    params: tuple[ParamInfo, ...]
    bindable: tuple[str, ...]  # BINDABLE_PROPS
    bindable_audited: bool  # False quand BINDABLE_PROPS vaut None
    #: Le sous-ensemble de ``bindable`` que le CLIENT écrit
    #: (``reactive_prop(writes=True)`` → ``TWO_WAY_PROPS``). La matrice du
    #: funnel notait ce sens à la main avec ``⇄`` / ``→`` ; c'est dérivable,
    #: donc ça n'a pas à être recopié.
    two_way: tuple[str, ...]
    events: tuple[str, ...]  # EVENTS (sans le préfixe ``on_``)
    #: Les ``on_<event>=`` réellement acceptés à l'appel. **Ce n'est pas
    #: ``events`` préfixé.** ``cross_check_events`` garantit à la
    #: définition de classe que tout ``EVENTS`` a son paramètre, donc
    #: ``events`` ⊆ ceci ; l'inclusion inverse est FAUSSE.
    #:
    #: ⚠️ L'exemple qui vivait ici — « ``table``, ``datatable``,
    #: ``bar_chart`` et ``pie_chart`` acceptent un clic sans le déclarer
    #: dans ``EVENTS`` » — était juste le 2026-08-16 et il ne l'est plus.
    #: Ce n'était pas une nuance d'introspection mais un TROU : sans
    #: déclaration, ces ``on_*`` n'acceptaient qu'un callable, là où tout
    #: ``on_*`` du framework accepte aussi une expression cliente ou une
    #: liste des deux. Trois des quatre le déclarent depuis le
    #: 2026-09-06 (cf. ``test_a_wired_event_is_declared``), et le
    #: quatrième, ``datatable``, reste le cas qui justifie ce champ :
    #: il accepte ``on_item_click=`` sans figurer dans son ``EVENTS``.
    #: Un consommateur qui lirait ``events`` seul aurait la réponse
    #: fausse, d'où ce champ : elle est calculée UNE fois, ici.
    handler_kwargs: tuple[str, ...]
    named_slots: tuple[str, ...]  # NAMED_SLOTS
    imperative: tuple[str, ...]  # IMPERATIVE
    autoname_from: str | None  # AUTONAME_FROM
    #: La clé sous laquelle ``Theme(components={…})`` adresse ce composant
    #: — ``THEME_KEY``, **pas** ``ui_name``. Huit composants diffèrent, et
    #: trois d'entre eux visent le thème d'un AUTRE : ``sidebar_section`` et
    #: ``sidebar_title`` écrivent tous deux sous ``"sidebar"``. Un
    #: consommateur qui déduirait la clé du nom ``ui.*`` se tromperait sur
    #: ces huit-là. Vide quand le composant n'a pas de thème adressable
    #: (``fragment``, ``outlet``, ``interval``, ``meta_tag``).
    theme_key: str
    #: Le **vocabulaire** du thème : ``(groupe, clés)``, trié. Les valeurs
    #: — les chaînes de classes Tailwind des 102 composants — n'y  count:components
    #: sont PAS : ce qu'un lecteur et une règle de lint ont besoin de
    #: savoir, c'est quels noms existent, pas ce qu'ils rendent (le code
    #: est là pour ça).
    #:
    #: ``clés`` vide distingue un groupe **scalaire** d'un groupe table :
    #: des groupes portent une valeur unique et non un dict (``hoverable``,
    #: ``sticky``, ``wrap``, ``palette``, ``icon_size``…). Les confondre
    #: ferait chercher des clés là où il n'y en a pas — donc inventer des
    #: faux positifs.
    #:
    #: Paires plutôt qu'un ``dict`` : tout le reste de ce modèle est en
    #: tuples, et un dict dans une dataclass ``frozen`` reste mutable —
    #: l'immuabilité serait annoncée sans être tenue. ``dict(info.theme)``
    #: au point de consommation.
    theme: tuple[tuple[str, tuple[str, ...]], ...]
    #: Les valeurs que ``size=`` accepte **réellement**, tables imbriquées
    #: absorbées. Ce n'est PAS ``dict(theme)["sizes"]`` : la plupart des
    #: tables du catalogue imbriquent leurs clés, et deux imbrications
    #: opposées coexistent — ``Checkbox`` indexe par taille
    #: (``{"sm": {<slot>}}``), ``DatePicker`` par slot
    #: (``{"input_field": {"sm"}}``). Un consommateur qui lirait les clés
    #: brutes conclurait que ``ui.date_picker(size="sm")`` est faux.
    #: Résolu par ``bretzel.components.base.size_vocabulary``.
    #:
    #: Vide = « on ne sait pas » et **jamais** « rien n'est valide » :
    #: ``radio_group`` accepte ``size=`` sans table, son ``render`` en fait
    #: autre chose.
    size_values: tuple[str, ...]


@dataclass(frozen=True)
class FieldInfo:
    """Un champ d'une classe d'état."""

    name: str
    type_label: str
    default_label: str  # "0" / "''" / "list() (factory)" / "— (requis)"
    validators: tuple[str, ...]  # les @validator posés sur CE champ


@dataclass(frozen=True)
class StateInfo:
    """Une classe d'état — serveur (4 portées) ou client."""

    name: str
    family: str  # "ServerState" | "ClientState"
    scope: str  # "page/session/user/app" | étiquette de persistance
    persist: str | None
    doc: str | None
    fields: tuple[FieldInfo, ...]
    computed: tuple[str, ...]
    whole_validators: int  # nombre de @validator au niveau instance
    #: ``(champ, nom de paramètre)`` — ce qui part VRAIMENT dans l'adresse.
    url_params: tuple[tuple[str, str], ...] = ()
    #: Les champs que le framework a NOMMÉS, allumés ou non. La
    #: différence avec le champ du dessus EST l'information : un
    #: ``DatatableState`` nomme cinq champs et n'en publie aucun tant
    #: qu'une sous-classe n'a pas écrit ``addressable=True``.
    url_named: tuple[tuple[str, str], ...] = ()
    #: Le message d'une déclaration ``URL`` refusée. Une fiche qui tait
    #: l'erreur laisserait lire « cet état ne publie rien », ce qui est
    #: la même sortie qu'une déclaration absente.
    url_error: str | None = None


@dataclass(frozen=True)
class MethodInfo:
    """Une méthode publique lue sur une classe."""

    name: str
    params: tuple[ParamInfo, ...]  # ``self`` retiré
    returns_label: str
    doc: str | None


@dataclass(frozen=True)
class AlgebraOp:
    """Une opération de l'algèbre de binding client, avec le JS qu'elle
    émet **réellement** — capturé par une sonde, pas recopié."""

    name: str
    category: str  # comparaison/arithmétique/logique/liste/mutation/autre
    python: str  # comment on l'écrit — "x > y"
    js: str | None  # le JS émis, capturé à l'exécution
    returns_label: str
    doc: str | None


@dataclass(frozen=True)
class ModuleSection:
    """La surface publique d'UN module du framework, classée par besoin.

    ``covered`` dit si la section a une table de classement écrite. Un
    module non couvert n'est pas *absent* du modèle — il est présent et
    déclaré non couvert, ce qui est la seule forme honnête : une section
    manquante en silence se lit comme « ça n'existe pas ».
    """

    name: str  # "bretzel.state"
    doc: str | None
    symbols: tuple[SurfaceSymbol, ...]
    covered: bool = True


@dataclass(frozen=True)
class SurfaceSymbol:
    """Un nom de ``bretzel.__all__``, classé par le besoin qu'il couvre."""

    name: str
    category: str
    kind: str  # "classe" / "fonction" / "décorateur" / "module" / "valeur"
    #: La ligne d'index. **``summary`` et non ``doc``** : pour une
    #: constante, c'est sa VALEUR et non de la prose — ``inspect.getdoc``
    #: y rendait la docstring de son type, et 46 lignes de l'index
    #: affichaient ``str(object='') -> str``. Le champ s'appelait ``doc``
    #: quand il ne portait que de la prose ; en changer le contenu sans
    #: en changer le nom aurait laissé un consommateur lire un ``repr``
    #: comme une phrase.
    summary: str | None


@dataclass(frozen=True)
class SymbolDetail:
    """La fiche d'un symbole public qui **n'est pas** un ``ui.*``.

    :class:`ComponentInfo` répondait pour les composants ; tout le reste —
    ``@page``, ``PageState``, ``ClientBinding``, ``ROUTE_ACTION`` — n'avait
    qu'une ligne d'index tronquée à 62 caractères, sans signature. Une IA
    y lisait que ``@page`` existe, jamais comment on l'appelle.

    Les champs facultatifs sont remplis **selon la nature du symbole**, et
    leur absence est une information : un ``valeur`` n'a pas de signature,
    une fonction n'a pas de méthodes. Aucun n'est un « à faire ».
    """

    name: str
    #: Le module d'où on l'importe en premier — l'ordre de
    #: :data:`~bretzel.introspect.modules.SECTIONS`, donc ``bretzel``
    #: d'abord : c'est ce que le site d'appel écrit vraiment.
    module: str
    #: Tous les modules qui l'exportent. ``page`` sort de ``bretzel`` ET de
    #: ``bretzel.render`` — le MÊME objet ré-exporté. Le taire ferait
    #: croire à deux symboles, ou à un seul chemin d'import légal.
    exported_by: tuple[str, ...]
    #: Les AUTRES surfaces qui portent ce nom. ``text`` est le seul cas :
    #: le composant ``ui.text`` et ``bretzel.render.text``, le mot du
    #: framework. Un champ et non une note collée au rendu — sinon la
    #: fiche du composant le dirait et celle du symbole non, et le JSON
    #: ne le porterait dans aucun des deux sens.
    also_known_as: tuple[str, ...]
    category: str  # le besoin qu'il couvre, cf. ``SurfaceSymbol``
    kind: str  # "classe" / "fonction" / "décorateur" / "valeur"
    doc: str | None  # la docstring ENTIÈRE, pas sa première ligne
    #: La signature vivante. Pour une classe, c'est celle de son
    #: constructeur — la fiche se lit comme le site d'appel.
    signature: CallableInfo | None
    methods: tuple[MethodInfo, ...]  # classes seulement
    #: La valeur d'une constante. C'est SA documentation : ``ROUTE_ACTION``
    #: ne se comprend qu'en lisant ``'/_bz/action'``, et ``inspect.getdoc``
    #: n'y rendait que la docstring de ``str``.
    value_repr: str | None
    #: L'algèbre Python→JS, pour les classes qui **sont** leur surface
    #: d'opérateurs (:class:`~bretzel.state.ClientBinding` et ses filles).
    #: ``describe_method_surface`` y rendrait les mêmes noms sans la forme
    #: Python ni le JS émis, ce qui est la moitié inutile de la réponse.
    algebra: tuple[AlgebraOp, ...]
    #: La portée et les champs, pour une classe d'état. Sur les cinq
    #: classes de base c'est la portée qui porte l'information — la seule
    #: chose qu'on veut savoir de ``PageState``.
    state: StateInfo | None


@dataclass(frozen=True)
class HelperInfo:
    """Une entrée ``ui.*`` qui n'est **pas** un composant.

    Le namespace ``ui`` est délibérément hétérogène : un générateur
    d'itération keyée (``ui.each``) et un helper de toast
    (``ui.notification``) voisinent avec ``ui.button``. On les classe par
    nature et on les lit honnêtement — un helper n'a ni props, ni events,
    ni slots, et on ne prétend pas le contraire.
    """

    ui_name: str
    kind: str  # cf. _HELPER_KINDS
    params: tuple[ParamInfo, ...]
    doc: str | None

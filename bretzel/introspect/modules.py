"""Les surfaces publiques des modules du framework, classées par besoin.

**Un lecteur, N tables — pas N modules.** ``bretzel.state``,
``bretzel.server``, ``bretzel.render``, ``bretzel.runtime``,
``bretzel.core`` et ``bretzel.theme`` posent exactement la même question
(« qu'est-ce qui existe ici, et à quoi ça sert ? ») ; en écrire un module
chacun aurait produit six copies d'une boucle sur ``__all__``. Ce qui
diffère d'un module à l'autre, ce n'est pas la lecture, c'est le
**classement**.

**Le classement par BESOIN, et non par type Python, est le point.** Savoir
que ``refresh`` est une fonction n'aide personne ; savoir qu'elle vit dans
« agir depuis un handler », à côté d'``abort`` et de ``redirect``, répond à
la vraie question — « j'ai un handler, qu'est-ce que je peux appeler ? ».

**La population n'est jamais recopiée** : elle vient de l'``__all__`` du
module. Seul le classement est écrit à la main, et c'est justement ce
qu'on veut forcer à décider — un nom ajouté sans entrée ici tombe en
:data:`CATEGORY_UNCLASSIFIED` et fait rougir
``tests/consistency/test_module_surfaces_are_classified.py``. On n'élargit
pas une surface publique sans dire à quoi elle sert.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from functools import cache
from types import MappingProxyType

from bretzel.introspect.model import (
    CATEGORY_UNCLASSIFIED,
    ModuleSection,
    SurfaceSymbol,
)

#: Un décorateur se reconnaît à son usage, pas à sa signature — la liste
#: est courte et stable, autant la nommer que la deviner mal.
_DECORATORS = frozenset(
    {
        "page",
        "layout",
        "error_page",
        "refreshable",
        "background",
        "idempotent",
        "computed",
        "validator",
    }
)

_ERROR = "rattraper une erreur"

_TOPLEVEL: dict[str, str] = {
    "Bretzel": "monter l'application",
    "BretzelConfig": "monter l'application",
    "Feature": "monter l'application",
    # La PWA est de la CONFIGURATION d'app, pas un composant :
    # elle se passe à ``Bretzel(pwa=…)`` et décrit l'app au
    # système (nom, icône, fenêtre propre), pas au navigateur.
    "PWA": "monter l'application",
    "PWAIcon": "monter l'application",
    "page": "déclarer un routable",
    "layout": "déclarer un routable",
    "error_page": "déclarer un routable",
    "refreshable": "déclarer un routable",
    # Un ``@download`` EST un routable — le seul qui ne rende pas une
    # page mais un fichier. Sa réponse ne peut pas passer par le
    # pipeline d'action (le bridge l'avalerait en ``<bz-patch>``).
    "download": "déclarer un routable",
    # Un point d'accès chacun, cf. test_handler_helpers_have_one_home.py
    "abort": "agir depuis un handler",
    "redirect": "agir depuis un handler",
    "push_url": "agir depuis un handler",
    "background": "agir depuis un handler",
    "idempotent": "agir depuis un handler",
    "refresh": "agir depuis un handler",
    # Elle fait REDEMANDER la page au navigateur — une action sur la
    # réponse, pas un re-rendu de zone comme ``refresh`` juste au-dessus.
    "reload": "agir depuis un handler",
    # Les VERBES clients (2026-09-01). Un besoin à part, et le nommer
    # est ce que la gate exige : ils n'agissent ni sur la réponse ni sur
    # l'arbre, ils déclenchent une action du NAVIGATEUR. Leur place sur
    # ``bretzel`` plutôt que sur ``ui`` est un arbitrage utilisateur du
    # même jour — ce qui FAIT quelque chose est ici, ce qui EST quelque
    # chose est sur ``ui``.
    "copy": "agir dans le navigateur",
    "print_page": "agir dans le navigateur",
    "fullscreen": "agir dans le navigateur",
    "share": "agir dans le navigateur",
    "vibrate": "agir dans le navigateur",
    "ui": "rendre",
    "state": "déclarer un état",
    # La langue résolue de CETTE requête — lue depuis un corps de rendu,
    # comme ``Screen()`` juste en dessous.
    "Language": "rendre",
    "Screen": "rendre",
    # La troisième lecture d'ambiance, avec ``Screen`` et ``Language`` :
    # elles répondent toutes à « que sait-on de CE lecteur ? ». Elle vit
    # dans ``theme`` (socle) et se ré-exporte ici pour que les trois
    # s'importent du même endroit — jusqu'au 2026-08-29 il fallait
    # connaître ``bretzel.theme`` pour lire le mode de couleur.
    "ColorScheme": "rendre",
    # Quatrième et dernière lecture d'ambiance. Elle vit dans ``state``
    # parce que c'est un ``ClientState`` que le runtime écrit — mais elle
    # se lit comme ses trois sœurs, et s'importe donc d'ici comme elles.
    "LiveConnection": "rendre",
    # L'identité ENTIÈRE tient dans ces deux modules depuis le
    # 2026-08-29 : les verbes impératifs et les deux déclarations
    # (``@auth.source`` / ``@auth.door``), qui étaient au top-level.
    "auth": "savoir qui est là",
    "oauth": "savoir qui est là",
    "BretzelError": _ERROR,
    "AuthRequiredError": _ERROR,
    "FeatureError": _ERROR,
    "__version__": "métadonnée du paquet",
}

_STATE: dict[str, str] = {
    # Les quatre portées serveur — l'héritage EST la hiérarchie de durée.
    "ServerState": "déclarer un état serveur",
    "PageState": "déclarer un état serveur",
    "SessionState": "déclarer un état serveur",
    "UserState": "déclarer un état serveur",
    "AppState": "déclarer un état serveur",
    # Le cinquième scope, côté navigateur.
    "ClientState": "déclarer un état client",
    "LiveConnection": "déclarer un état client",
    "field": "déclarer un champ",
    "register_type": "déclarer un champ",
    "computed": "déclarer un champ",
    "validator": "déclarer un champ",
    "form_value": "lire un état ailleurs",
    # L'algèbre : ce qu'on compose pour un `bz-show` / un `visible=`.
    "ClientBinding": "composer côté client",
    "ClientExpression": "composer côté client",
    "FormError": _ERROR,
    "ReactivityError": _ERROR,
    "ScopeConfigError": _ERROR,
    "StateHydrationError": _ERROR,
    "AuthRequiredError": _ERROR,
    "LockTimeoutError": _ERROR,
}

_SERVER: dict[str, str] = {
    "Bretzel": "monter l'application",
    "BretzelConfig": "monter l'application",
    "Feature": "monter l'application",
    # La PWA est de la CONFIGURATION d'app, pas un composant :
    # elle se passe à ``Bretzel(pwa=…)`` et décrit l'app au
    # système (nom, icône, fenêtre propre), pas au navigateur.
    "PWA": "monter l'application",
    "PWAIcon": "monter l'application",
    # La carte d'app : contrat déclaré ↔ réalité dérivée. Pas un devtool —
    # elle alimente le composant carte au runtime.
    "describe_app": "introspecter la carte d'app",
    "AppGraph": "introspecter la carte d'app",
    "abort": "agir depuis un handler",
    "redirect": "agir depuis un handler",
    "push_url": "agir depuis un handler",
    "background": "agir depuis un handler",
    "idempotent": "agir depuis un handler",
    "reload": "agir depuis un handler",
    "BretzelError": _ERROR,
    "AuthRequiredError": _ERROR,
    "ConfigError": _ERROR,
    "FeatureError": _ERROR,
}

_RENDER: dict[str, str] = {
    "page": "déclarer un routable",
    "layout": "déclarer un routable",
    "error_page": "déclarer un routable",
    "refreshable": "déclarer un routable",
    # Un ``@download`` EST un routable — le seul qui ne rende pas une
    # page mais un fichier. Sa réponse ne peut pas passer par le
    # pipeline d'action (le bridge l'avalerait en ``<bz-patch>``).
    "download": "déclarer un routable",
    "render_page": "rendre",
    "render_partial": "rendre",
    "default_shell": "rendre",
    "shell_sources": "rendre",
    "serialize_html": "rendre",
    "refresh": "rafraîchir une zone",
    "drain_refresh_queue": "rafraîchir une zone",
    "RefreshableHandle": "rafraîchir une zone",
    "zone_ids_watching": "rafraîchir une zone",
    "text": "dire un mot du framework",
    "plural": "dire un mot du framework",
    "template": "dire un mot du framework",
    "DEFAULT_TEXTS": "dire un mot du framework",
    "resolve_texts": "dire un mot du framework",
    # La LANGUE, pas les mots : ``Language().code`` est ce par quoi une
    # app traduit SES chaînes, que le framework ne connaît pas ;
    # ``Language.set`` est le sélecteur.
    "Language": "choisir la langue",
    "negotiate_language": "choisir la langue",
    "resolve_language": "choisir la langue",
    "LanguageTables": "choisir la langue",
    "TextsError": _ERROR,
    "RenderContext": "lire le contexte de rendu",
    "current_context": "lire le contexte de rendu",
    "maybe_current_context": "lire le contexte de rendu",
    "use_context": "lire le contexte de rendu",
    "current_iteration_key": "lire le contexte de rendu",
    "PageMeta": "métadonnée d'un routable",
    "LayoutMeta": "métadonnée d'un routable",
    "ErrorMeta": "métadonnée d'un routable",
    "RenderResult": "métadonnée d'un routable",
    "BretzelApp": "métadonnée d'un routable",
    "state_qualname": "métadonnée d'un routable",
    "fuse_or_wrap": "composer des attributs",
    "FusionConflict": "composer des attributs",
    "DEFAULT_HTMX_URL": "constante",
    # Les trois scripts tiers rapatriés en local. Publics parce que la
    # couche serveur les sert (elle passe par l'API de `render`, pas par
    # le sous-module) et qu'une garde d'auth doit pouvoir les nommer.
    "ROUTE_VENDOR": "servir les scripts tiers en local",
    "ROUTE_ICONS": "servir les scripts tiers en local",
    "VendoredAsset": "servir les scripts tiers en local",
    "cached_name": "servir les scripts tiers en local",
    "ensure_vendored": "servir les scripts tiers en local",
    "downloadable_assets": "servir les scripts tiers en local",
    "icon_payload": "servir les scripts tiers en local",
    "vendored_assets": "servir les scripts tiers en local",
    "vendored_is_available": "servir les scripts tiers en local",
    "vendored_local_path": "servir les scripts tiers en local",
}

_RUNTIME: dict[str, str] = {
    # Les VERBES clients (2026-09-01). Un besoin à part, et le nommer
    # est ce que la gate exige : ils n'agissent ni sur la réponse ni sur
    # l'arbre, ils déclenchent une action du NAVIGATEUR. Leur place sur
    # ``bretzel`` plutôt que sur ``ui`` est un arbitrage utilisateur du
    # même jour — ce qui FAIT quelque chose est ici, ce qui EST quelque
    # chose est sur ``ui``.
    "copy": "agir dans le navigateur",
    "print_page": "agir dans le navigateur",
    "fullscreen": "agir dans le navigateur",
    "share": "agir dans le navigateur",
    "vibrate": "agir dans le navigateur",
    # Le vocabulaire `bz-*` — l'idiom du framework côté client. Un
    # composant compose avec ceux-là ; il n'écrit ni `hx-` ni `fetch`.
    "BZ_ON_PREFIX": "vocabulaire des directives bz-*",
    "BZ_MODEL_PREFIX": "vocabulaire des directives bz-*",
    "BZ_ATTR_PREFIX": "vocabulaire des directives bz-*",
    "BZ_CLASS_PREFIX": "vocabulaire des directives bz-*",
    "BZ_TEXT_PREFIX": "vocabulaire des directives bz-*",
    "BZ_SHOW_PREFIX": "vocabulaire des directives bz-*",
    "BZ_IF_PREFIX": "vocabulaire des directives bz-*",
    "BZ_FOR_PREFIX": "vocabulaire des directives bz-*",
    "BZ_DATA_PREFIX": "vocabulaire des directives bz-*",
    "BZ_INIT_PREFIX": "vocabulaire des directives bz-*",
    "BZ_EFFECT_PREFIX": "vocabulaire des directives bz-*",
    "BZ_REF_PREFIX": "vocabulaire des directives bz-*",
    "BZ_TELEPORT_PREFIX": "vocabulaire des directives bz-*",
    "BZ_ID_ATTR": "attribut de transport",
    "BZ_STATE_ATTR": "attribut de transport",
    "DATA_BZ_SIG": "attribut de transport",
    "DATA_BZ_TS": "attribut de transport",
    "DATA_SUBSCRIBE_STATE": "attribut de transport",
    "DATA_SUBSCRIBE_URL": "attribut de transport",
    "SERVERSYNC_KEY": "attribut de transport",
    "SINK_ELEMENT_ID": "attribut de transport",
    "WIRE_ID_SEP": "attribut de transport",
    "HEADER_PROTOCOL": "en-tête HTTP",
    "HEADER_BZ_SIG": "en-tête HTTP",
    "HEADER_BZ_TS": "en-tête HTTP",
    "HEADER_PAGE_ID": "en-tête HTTP",
    "HEADER_CSRF": "en-tête HTTP",
    # Les URLs vivent ici et arrivent au client par l'enveloppe — le
    # runtime.js n'en code aucune en dur (anti-règle 3).
    "ROUTE_PREFIX": "route du runtime",
    "ROUTE_RUNTIME_JS": "route du runtime",
    "ROUTE_THEME_CSS": "route du runtime",
    "ROUTE_STYLE_CSS": "route du runtime",
    "ROUTE_ICONS": "route du runtime",
    "ROUTE_VENDOR": "route du runtime",
    "is_public_asset_path": "route du runtime",
    "ROUTE_ACTION": "route du runtime",
    "ROUTE_SSE": "route du runtime",
    "ROUTE_REFETCH": "route du runtime",
    # Le classement ouvert/fermé de ces routes, pour une garde
    # d'auth d'app. Gaté par test_framework_routes_are_classified.
    "PUBLIC_ASSET_ROUTES": "route du runtime",
    "Envelope": "enveloppe et patch",
    "Patch": "enveloppe et patch",
    "build_envelope": "enveloppe et patch",
    "build_patch": "enveloppe et patch",
    "serialize_envelope": "enveloppe et patch",
    "serialize_patch": "enveloppe et patch",
    "parse_client_payload": "enveloppe et patch",
    "default_endpoints": "enveloppe et patch",
    "outlet_id_for": "enveloppe et patch",
    "ENVELOPE_TAG_NAME": "enveloppe et patch",
    "PATCH_TAG_NAME": "enveloppe et patch",
    "PROTOCOL_VERSION": "version de protocole",
    "check_compat": "version de protocole",
    "check_protocol_compat": "version de protocole",
    "parse_major": "version de protocole",
    # Le SEUL événement SSE : « l'état X est sale ». Le serveur ne pousse
    # jamais de HTML par ce canal, il pousse un signal.
    "SSE_EVENT_STATE_DIRTY": "temps réel (SSE)",
}

_CORE: dict[str, str] = {
    "Node": "arbre de rendu",
    "Element": "arbre de rendu",
    # Suffixés ``Node`` le 2026-08-29 : ``Text``/``Html``/``Fragment``
    # étaient les trois SEULS noms de toute la surface publique à
    # désigner deux objets différents (un nœud d'arbre ici, un
    # composant dans ``bretzel.components``). Le suffixe n'est pas
    # une invention : les cinq fichiers qui devaient déjà lever
    # l'ambiguïté aliasaient tous vers ces noms-là.
    "TextNode": "arbre de rendu",
    "HtmlNode": "arbre de rendu",
    "FragmentNode": "arbre de rendu",
    "VOID_ELEMENTS": "arbre de rendu",
    "serialize": "arbre de rendu",
    "serialize_attrs": "arbre de rendu",
    "escape_html": "échapper",
    "escape_attr": "échapper",
    "escape_js": "échapper",
    "IdGenerator": "identité d'un nœud",
    "hash_segment": "identité d'un nœud",
    # Ce qui rend « muter l'état re-rend le sous-arbre » possible.
    "DependencyTracker": "suivre les dépendances",
    "Observer": "suivre les dépendances",
    "TRACKER": "suivre les dépendances",
    "EventPayload": "transporter un événement",
    "BretzelError": _ERROR,
    "CircularDependencyError": _ERROR,
    # Le framework appelle du code d'APP depuis une coroutine — un ``def``
    # y bloquerait la boucle, donc il est délesté sur le threadpool.
    "call_without_blocking": "appeler du code d'application",
}

_THEME: dict[str, str] = {
    "Theme": "déclarer un thème",
    "ColorScheme": "déclarer un thème",
    "IconConfig": "déclarer un thème",
    "ScrollbarConfig": "déclarer un thème",
    "SEMANTIC_COLOR_NAMES": "constante",
    "DEFAULT_PALETTE_NAMES": "constante",
    "FONT_SLOT_NAMES": "constante",
    "SHAPE_SLOT_NAMES": "constante",
    "TEXT_SLOT_NAMES": "constante",
    "DEFAULT_SPACING_PX": "constante",
    "ThemeError": _ERROR,
}

#: Ce que ``bretzel.components`` exporte SANS que ce soit le catalogue.
#: Des objets-valeur qu'on nomme dans une signature (``Series``, ``Move``,
#: ``GraphNode``), une constante, et deux fonctions. Ils voyagent avec un
#: composant sans en être un, donc aucun mécanisme de composant ne les
#: décrit — et l'exemption qui protégeait le catalogue les avalait avec
#: lui. Les 102 classes de composant, elles, ne sont PAS ici : elles sont
#: filtrées, pas oubliées (cf. :func:`describe_module`).
_COMPONENTS: dict[str, str] = {
    "Column": "décrire un tableau",
    "apply_query": "décrire un tableau",
    "Series": "décrire un graphique",
    "Reference": "décrire un graphique",
    "GraphNode": "décrire un diagramme",
    "GraphEdge": "décrire un diagramme",
    "Track": "décrire une piste de média",
    "Move": "réagir à un glisser-déposer",
    # Ré-exportés — leur fiche vit AUSSI sous ``bretzel.state.datatable``,
    # et ``SymbolDetail.exported_by`` le dit sur chacune. Le classement
    # est le MÊME des deux côtés : deux besoins pour un objet unique se
    # lirait comme deux objets.
    "DatatableState": "déclarer un état serveur",
    "Query": "recevoir la demande du lecteur",
    "ui": "appeler un composant",
    "dynamic_responsive_classes": "déclarer au compilateur CSS",
    "SANDBOX_BASELINE": "constante",
}

#: Les deux noms d'un tableau. Ils sortent par ``bretzel.components``,
#: dont la surface EST le catalogue ``ui.*`` et qui est exempté à ce
#: titre (``test_module_surfaces_are_classified``) — mais ces deux-là
#: n'en font pas partie : ce sont un ÉTAT et un MESSAGE, décrits par
#: aucun mécanisme de composant. L'exemption les avalait, et
#: ``describe DatatableState`` répondait donc « n'est ni dans les
#: composants ni les modules » sur la classe que toute table
#: sous-classe. On classe leur module d'origine, pas leur porte : deux
#: entrées, et pas 115.
_DATATABLE: dict[str, str] = {
    "DatatableState": "déclarer un état serveur",
    "Query": "recevoir la demande du lecteur",
}

#: ``bretzel.probe`` — la couche 7 qui PILOTE l'app en marche.
#:
#: ⚠️ **Absente jusqu'au 2026-09-12, et c'est un trou qu'on paie en
#: greps.** ``describe probe`` répondait « n'est ni dans les composants
#: ``ui.*`` ni les modules », en ajoutant honnêtement « il s'importe
#: pourtant ». Résultat mesuré en montant ``examples/ecole`` : pour
#: écrire un probe il a fallu ouvrir ``_probe.py`` — la signature de
#: ``probe()`` (y a-t-il un ``strict=`` ? non ; un ``size=`` ? oui) et
#: celle de ``Probe.requests``.
#:
#: Le motif d'exclusion de l'outillage — *« ``describe`` sert à écrire
#: une app, pas à se lire lui-même »* — ne couvre pas ce paquet. On
#: n'écrit pas un probe pour lire le framework : on l'écrit pour juger
#: SON app, exactement comme on écrit une page. C'est d'ailleurs le
#: moment où l'on a le moins envie d'ouvrir un fichier du framework.
#:
#: ``cli``, ``introspect`` et ``lint`` restent dehors, eux : on ne les
#: appelle pas depuis le code d'une app.
_PROBE: dict[str, str] = {
    "probe": "piloter l'app en marche",
    "Probe": "piloter l'app en marche",
    "Window": "piloter l'app en marche",
    "Net": "piloter l'app en marche",
    "Box": "piloter l'app en marche",
    "ProbeFailedError": _ERROR,
    "ElementNotFoundError": _ERROR,
    "DropMissedError": _ERROR,
    "ScopeNotReadableError": _ERROR,
}

#: module → table de classement. L'ordre est l'ordre de lecture : on monte
#: l'app, on déclare son état, on rend, puis on descend vers le transport.
SECTIONS: dict[str, dict[str, str]] = {
    "bretzel": _TOPLEVEL,
    "bretzel.state": _STATE,
    "bretzel.state.datatable": _DATATABLE,
    "bretzel.components": _COMPONENTS,
    "bretzel.server": _SERVER,
    "bretzel.render": _RENDER,
    "bretzel.theme": _THEME,
    "bretzel.runtime": _RUNTIME,
    "bretzel.core": _CORE,
    "bretzel.probe": _PROBE,
}


def module_names() -> tuple[str, ...]:
    """Les modules qui ont une table de classement."""
    return tuple(SECTIONS)


#: Les paquets d'OUTILLAGE, hors du balayage ci-dessous. ``describe``
#: sert à écrire une app, pas à se lire lui-même ; et importer
#: ``bretzel.lint`` d'ici retirerait la garantie qui le rend arrachable
#: (contrat ``lint-stays-extractable`` de ``.importlinter``).
_TOOLING = frozenset({"cli", "introspect", "lint"})


@cache
def public_owners() -> MappingProxyType[str, str]:
    """Nom public → le paquet qui l'exporte, sur toute la surface d'app.

    **Non filtrée** : les 102 classes du catalogue en font partie, alors
    même qu'aucune section ne les liste. C'est la seule lecture qui
    répond à « ce nom s'importe-t-il ? », et c'est cette question que le
    message d'introuvable doit trancher — ``Button`` s'importe, quoi que
    dise la table.

    ⚠️ Le filtrer sur ``SECTIONS`` a coûté une régression le jour même :
    couvrir ``bretzel.components`` a sorti ses 102 classes de ce
    balayage, et ``describe Button`` a cessé de renvoyer vers
    ``describe button``. Une lecture « ce qui reste » se vide dès qu'on
    répare ce qui manquait.

    Découverte, pas écrite : une façade neuve y entre sans édition ici,
    et ``test_a_public_name_is_never_reported_missing`` rougit si elle
    en sort.
    """
    import bretzel

    out: dict[str, str] = {}
    for found in pkgutil.iter_modules(bretzel.__path__):
        if found.name in _TOOLING:
            continue
        module = importlib.import_module(f"bretzel.{found.name}")
        for symbol in getattr(module, "__all__", ()):
            out.setdefault(symbol, module.__name__)
    return MappingProxyType(out)


def uncovered_owners() -> MappingProxyType[str, str]:
    """Ceux de :func:`public_owners` qu'aucune section ne classe.

    Ce que le message d'introuvable doit dire autrement : pas de fiche,
    donc on nomme la porte d'import. Vide aujourd'hui — les treize noms
    hors catalogue de ``bretzel.components`` sont classés depuis le
    2026-09-06 — et gardée pour la façade suivante, qui arrivera sans
    table.
    """
    return MappingProxyType({
        symbol: owner
        for symbol, owner in public_owners().items()
        if owner not in SECTIONS
    })


def describe_module(name: str) -> ModuleSection:
    """Lit l'``__all__`` d'un module et classe chaque nom par besoin.

    **Une classe du CATALOGUE est retirée de la population**, et jamais
    en silence : la fiche de ``Button`` est celle d'``ui.button``, avec
    ses props, ses events, ses slots et son impératif. En faire aussi un
    symbole de module produirait une seconde fiche, plus pauvre, sous un
    nom qu'on peut taper.

    C'est la raison qui exemptait ``bretzel.components`` de tout
    classement, et elle était vraie — pour ses 102 classes. Elle avalait
    avec elles les treize noms qui ne sont PAS du catalogue : des
    objets-valeur qu'on nomme dans une signature, une constante, deux
    fonctions. Le filtre garde la raison et rend les treize.

    ⚠️ Un nom ré-exporté n'est PAS filtré : ``page`` sort de ``bretzel``
    et de ``bretzel.render``, et les deux sections le listent — c'est
    ``SymbolDetail.exported_by`` qui rend l'information (« Aussi dans »).
    La version qui filtrait les ré-exports a vécu deux minutes et
    supprimait 22 fiches, dont ``page`` : les deux moitiés se filtraient
    l'une l'autre.

    Le filtre est DÉRIVÉ — identité sur le namespace ``ui`` — donc il ne
    peut pas pourrir comme une liste écrite à la main.
    """
    module = importlib.import_module(name)
    categories = SECTIONS.get(name, {})
    exported = tuple(
        symbol
        for symbol in getattr(module, "__all__", ())
        if symbol not in _catalogue_names(name)
    )

    symbols = tuple(
        SurfaceSymbol(
            name=symbol,
            category=categories.get(symbol, CATEGORY_UNCLASSIFIED),
            kind=kind_of(value, symbol),
            summary=summarize(value),
        )
        for symbol in exported
        for value in [getattr(module, symbol, None)]
    )
    return ModuleSection(
        name=name,
        doc=first_doc_line(module),
        symbols=tuple(sorted(symbols, key=_reading_order(categories))),
        covered=bool(categories),
    )


@cache
def _catalogue_names(name: str) -> frozenset[str]:
    """Les noms de ``name`` qui SONT une classe du catalogue ``ui.*``.

    Par identité, jamais par orthographe : ``AccordionItem`` est
    ``ui.accordion_item``, et une comparaison de chaînes rate tout ce
    qui porte un underscore — 37 noms sur 48, mesuré.
    """
    from bretzel.introspect.components import ui_name_of_class

    module = importlib.import_module(name)
    catalogue = ui_name_of_class()
    return frozenset(
        symbol
        for symbol in getattr(module, "__all__", ())
        for value in [getattr(module, symbol, None)]
        if isinstance(value, type) and value in catalogue
    )


def _reading_order(categories: dict[str, str]):
    """Trie par ORDRE DE LECTURE, pas par alphabet.

    Les tables ci-dessus sont écrites dans l'ordre où on rencontre les
    besoins — on monte l'app, on déclare son état, on agit, on rend, puis
    on descend vers le transport. Cet ordre est une information, et le
    perdre au profit de l'alphabet ferait ouvrir ``bretzel.state`` sur
    « composer côté client » plutôt que sur les quatre portées serveur.

    Le rang d'une catégorie est donc son rang de **première apparition**
    dans la table : l'ordre n'a pas à être maintenu séparément, il est
    déjà dans la façon dont la table est écrite.
    """
    ranks: dict[str, int] = {}
    for category in categories.values():
        ranks.setdefault(category, len(ranks))
    unclassified = len(ranks) + 1
    return lambda s: (ranks.get(s.category, unclassified), s.name)


def describe_modules() -> tuple[ModuleSection, ...]:
    """Toutes les sections couvertes, dans l'ordre de lecture."""
    return tuple(describe_module(name) for name in SECTIONS)


def describe_toplevel_surface() -> tuple[SurfaceSymbol, ...]:
    """``bretzel.__all__`` classé — la surface qu'on rencontre en premier.

    Conservée comme entrée nommée parce que c'est la surface que la doc
    vivante affiche en propre ; c'est un cas particulier de
    :func:`describe_module`, pas un second moteur.
    """
    return describe_module("bretzel").symbols


def kind_of(value: object, name: str) -> str:
    if inspect.ismodule(value):
        return "module"
    if isinstance(value, type):
        return "classe"
    if callable(value):
        return "décorateur" if name in _DECORATORS else "fonction"
    return "valeur"


def first_doc_line(value: object) -> str | None:
    doc = inspect.getdoc(value)
    return doc.strip().splitlines()[0] if doc else None


def value_summary(value: object) -> str | None:
    """La valeur d'une constante — **son** résumé, pas celui de son type.

    ``inspect.getdoc`` sur une constante rend la docstring de sa CLASSE :
    les 42 constantes ``str`` du framework s'affichaient toutes
    ``str(object='') -> str``, et ``DEFAULT_TEXTS`` « dict() -> new empty
    dictionary ». 46 lignes d'index qui ne disaient rien, là où la seule
    chose qu'on veut savoir d'un ``ROUTE_ACTION`` est sa valeur.

    Les ensembles sont **triés** avant d'être rendus : l'ordre
    d'itération d'un ``frozenset`` de chaînes dépend de
    ``PYTHONHASHSEED``, donc le laisser passer ferait bouger
    ``bretzel describe`` d'un process à l'autre et clignoter sa gate de
    fraîcheur.

    ``None`` pour un objet quelconque (``TRACKER``, ``ui``) : là, la
    docstring de sa classe **est** le bon résumé, et son ``repr`` porte
    une adresse mémoire.
    """
    if isinstance(value, frozenset | set):
        body = ", ".join(repr(v) for v in sorted(value, key=repr))
        return f"{type(value).__name__}({{{body}}})" if body else f"{type(value).__name__}()"
    if value is None or isinstance(value, str | bytes | int | float | tuple | list | dict):
        return repr(value)
    return None


def summarize(value: object) -> str | None:
    """La ligne d'index d'un symbole : sa valeur si c'en est une, sinon la
    première ligne de sa docstring."""
    return value_summary(value) or first_doc_line(value)

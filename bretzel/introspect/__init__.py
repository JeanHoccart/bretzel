"""Couche 7 — le framework se décrit lui-même, et ne peut pas mentir.

Ce module lit le code **installé** au moment où on l'interroge. C'est ce
qui le distingue d'un catalogue d'API : il n'y a rien à maintenir, donc
rien à faire dériver. C'est aussi pourquoi il est livré DANS le framework
et ne peut pas vivre dans un paquet séparé — un décalage de version entre
le descripteur et le décrit le ferait mentir, ce qui est précisément la
maladie qu'il soigne.

Trois entrées de haut niveau :

- :func:`index` — une ligne par symbole ``ui.*``, toute la surface.
- :func:`describe` — la fiche complète d'un symbole, en texte, à la demande.
- :func:`resolve` — la MÊME résolution, rendue en dataclass. C'est elle
  qu'un consommateur appelle : le CLI en tire son ``--json``, et l'ordre
  des étages (module → composant → symbole) n'est écrit que là.

⚠️ **La sortie des émetteurs est en UTF-8**, arrows et guillemets
compris. Un consommateur qui l'écrit sur un flux possède son encodage —
sur une console Windows (cp1252) un ``print`` nu lève. Le CLI le fait
pour lui (``bretzel.cli.main``) ; un script maison doit le faire aussi.

Et les lecteurs par section, pour un consommateur qui compose lui-même :
:func:`describe_state`, :func:`describe_client_algebra`,
:func:`describe_toplevel_surface`, :func:`describe_method_surface`,
:func:`describe_callable`.

Le contrat pour un consommateur tiers (doc vivante, générateur, serveur
MCP) est :mod:`bretzel.introspect.model` : on importe les dataclasses **en
process**, on ne parse pas la sortie texte.

L'absence d'une section spécialisée dans la sortie textuelle ne signifie
pas que le symbole est absent de la résolution générale.
"""

from __future__ import annotations

import contextlib
import importlib

from bretzel.introspect._signature import describe_callable
from bretzel.introspect.algebra import describe_client_algebra
from bretzel.introspect.capabilities import (
    CAPABILITIES,
    Capability,
    capability_names,
    render_capabilities,
)
from bretzel.introspect.components import (
    RESERVED_KWARGS,
    describe_component,
    describe_components,
    describe_ui_symbol,
    prop_vocabulary,
    theme_shapes,
    theme_vocabulary,
    ui_name_of_class,
    ui_symbol_names,
)
from bretzel.introspect.emit.text import (
    render_detail,
    render_index,
    render_module,
    render_symbol,
)
from bretzel.introspect.methods import describe_method_surface
from bretzel.introspect.model import (
    CATEGORY_UNCLASSIFIED,
    SCHEMA_VERSION,
    SOURCE_REACTIVE_PROP,
    SOURCE_SIGNATURE,
    AlgebraOp,
    CallableInfo,
    ComponentInfo,
    FieldInfo,
    HelperInfo,
    MethodInfo,
    ModuleSection,
    ParamInfo,
    StateInfo,
    SurfaceSymbol,
    SymbolDetail,
)
from bretzel.introspect.modules import (
    describe_module,
    describe_modules,
    describe_toplevel_surface,
    module_names,
    public_owners,
)
from bretzel.introspect.package_tree import (
    ModuleInfo,
    PackageNode,
    SymbolLine,
    describe_package,
    package_names,
    render_package,
    render_tree,
    walk,
)
from bretzel.introspect.state import describe_state
from bretzel.introspect.symbols import (
    describe_symbol,
    symbol_names,
    symbol_owners,
)
from bretzel.introspect.theme_sheet import theme_sheet

__all__ = (
    "CAPABILITIES",
    "CATEGORY_UNCLASSIFIED",
    "Capability",
    "capability_names",
    "render_capabilities",
    "RESERVED_KWARGS",
    "SCHEMA_VERSION",
    "SOURCE_REACTIVE_PROP",
    "SOURCE_SIGNATURE",
    "AlgebraOp",
    "CallableInfo",
    "ComponentInfo",
    "FieldInfo",
    "ModuleInfo",
    "ModuleSection",
    "PackageNode",
    "SymbolLine",
    "describe_package",
    "package_names",
    "render_package",
    "render_tree",
    "walk",
    "HelperInfo",
    "MethodInfo",
    "ParamInfo",
    "StateInfo",
    "SurfaceSymbol",
    "SymbolDetail",
    "describe",
    "describe_callable",
    "describe_client_algebra",
    "describe_component",
    "describe_components",
    "describe_method_surface",
    "describe_module",
    "describe_modules",
    "describe_state",
    "describe_symbol",
    "describe_toplevel_surface",
    "prop_vocabulary",
    "theme_sheet",
    "theme_shapes",
    "theme_vocabulary",
    "describe_ui_symbol",
    "index",
    "module_names",
    "render_detail",
    "render_index",
    "render_module",
    "render_symbol",
    "resolve",
    "symbol_names",
    "symbol_owners",
    "ui_symbol_names",
)


def index() -> str:
    """Toute la surface ``ui.*``, une ligne par symbole."""
    return render_index()


def resolve(name: str) -> ModuleSection | ComponentInfo | HelperInfo | SymbolDetail:
    """Le symbole désigné par ``name``, sous sa forme dataclass.

    **L'ordre des étages vit ICI et nulle part ailleurs.** Il était écrit
    trois fois — dans ``describe``, dans le CLI pour ``--json``, et dans
    le message d'erreur — et les trois avaient déjà divergé : ``--json``
    ignorait l'étage module, donc ``describe bretzel.core --json`` levait
    et ``describe bretzel.state --json`` répondait la fiche d'un AUTRE
    symbole (``state``, ré-exporté par ``bretzel``). C'est exactement la
    divergence que ce chantier venait fermer, réintroduite par une copie.

    Trois natures de nom :

    - un module couvert (``bretzel.state``) → sa surface classée ;
    - **tout autre PAQUET** (``bretzel.components.inputs``) → son arbre
      et les docstrings que les dossiers portent déjà. Ajouté le
      2026-09-02 : il y a 117 paquets sous ``bretzel/`` et sept étaient
      décrits, parce que la table est écrite à la main. L'arbre, lui, se
      lit ;
    - un composant (``button`` ou ``ui.button`` — le site d'appel réel
      porte le préfixe, l'exiger serait une friction gratuite) ;
    - **tout autre symbole public** (``page``, ``PageState``,
      ``ClientBinding``, ``ROUTE_ACTION``), nu ou qualifié.

    Le préfixe ``ui.`` force la deuxième famille : c'est la seule façon
    de demander le composant quand un nom est porté par les deux
    surfaces.
    """
    if name in module_names():
        return describe_module(name)

    # Un paquet NON classé — testé après la table, qui est plus précise
    # quand elle existe (elle groupe par besoin, l'arbre non).
    #
    # ⚠️ Ce test APRÈS la table a un effet qu'il faut connaître :
    # ``describe bretzel`` rend la SURFACE (45 lignes), pas l'arbre
    # (117). Les deux existent, la table gagne, et c'est voulu — on
    # demande « bretzel » pour savoir ce qu'on écrit, pas comment les
    # dossiers sont rangés. ``render_module`` ajoute donc une ligne qui
    # dit où trouver l'autre, sans quoi l'arbre serait masqué en
    # silence pour les sept modules classés.
    if name.startswith("bretzel.") or name == "bretzel":
        with contextlib.suppress(ValueError):
            return describe_package(name)

    symbol = name.removeprefix("ui.")
    if symbol in ui_symbol_names():
        return describe_ui_symbol(symbol)
    if not name.startswith("ui."):
        with contextlib.suppress(KeyError):
            return describe_symbol(name)
    raise KeyError(_unknown_message(name))


def describe(name: str) -> str:
    """La fiche complète d'un symbole du framework, en texte.

    Un rendu de ce que :func:`resolve` a trouvé — la résolution n'est pas
    refaite ici.

    ⚠️ **Une seule exception, et elle est délibérée** : ``capabilities``
    ne passe PAS par :func:`resolve`, parce que ce n'est pas un symbole.
    C'est la seule réponse du module qui ne se déduit d'aucune lecture
    du code — une capacité traverse cinq dossiers, donc ni l'arbre, ni
    la table par besoin, ni le catalogue ``ui.*`` ne peuvent la former.
    Elle est écrite à la main et ANCRÉE : cf.
    :mod:`bretzel.introspect.capabilities`.
    """
    if name == "capabilities":
        return render_capabilities()
    found = resolve(name)
    if isinstance(found, ModuleSection):
        rendu = render_module(found)
        # Le renvoi vers l'arbre — cf. l'avertissement de ``resolve``.
        with contextlib.suppress(ValueError):
            noeud = describe_package(name)
            if noeud.children:
                rendu += (
                    f"\n  ({len(walk(noeud))} packages below — "
                    f"use ``describe {name}.<folder>`` to inspect the tree)\n"
                )
        return rendu
    if isinstance(found, SymbolDetail):
        return render_symbol(found)
    if isinstance(found, PackageNode):
        return render_package(found)
    return render_detail(found) + _homonym_note(found.ui_name)


def _homonym_note(ui_name: str) -> str:
    """Signale qu'un nom de composant désigne AUSSI un symbole de module.

    Un seul cas aujourd'hui, et il est piégeur : ``text`` est le composant
    ``ui.text`` **et** ``bretzel.render.text``, le mot du framework rendu
    dans la langue de l'app. Le nom nu résout vers le composant — c'est
    l'usage dominant — mais s'arrêter là ferait de l'autre un symbole
    qu'on ne peut trouver qu'en sachant déjà qu'il existe.

    Le sens inverse est porté par
    :attr:`~bretzel.introspect.model.SymbolDetail.also_known_as`, donc la
    fiche du symbole nomme le composant sans passer par ici.
    """
    owners = symbol_owners().get(ui_name, ())
    if not owners:
        return ""
    paths = ", ".join(f"{module}.{ui_name}" for module in owners)
    return f"\n\nNamesake   {paths}   (`describe {owners[0]}.{ui_name}`)"


def _unknown_message(name: str) -> str:
    """Le message d'un nom introuvable — il doit dire OÙ on a cherché.

    L'ancien répondait « ``ui.page`` n'existe pas » pour ``page``, ce qui
    est vrai et trompeur : le symbole existe, ailleurs. Un lecteur en
    concluait que le décorateur n'existait pas.
    """
    forced_ui = name.startswith("ui.")
    symbol = name.removeprefix("ui.")
    known_ui = ui_symbol_names()
    scopes = "the `ui.*` components" if forced_ui else "the `ui.*` components or modules"
    pool = set(known_ui) if forced_ui else set(known_ui) | set(symbol_names())
    near = sorted(n for n in pool if (symbol in n or n in symbol) and n != symbol)[:6]
    hint = f" Similar names: {', '.join(near)}." if near else ""
    return (
        f"`{name}` was not found among {scopes} "
        f"({len(known_ui)} components, {len(symbol_names())} module symbols)."
        f"{_where_it_lives(symbol)}"
        f"{hint} `index()` lists them all, and `describe capabilities` "
        f"shows what the framework can do."
    )


def _where_it_lives(symbol: str) -> str:
    """Où le nom vit, quand il vit quelque part que la table ignore.

    Deux façons d'exister sans avoir de fiche, et les deux se sont
    présentées le 2026-09-06 :

    - le CATALOGUE — ``Button`` est la classe de ``ui.button``, et
      ``AccordionItem`` celle d'``ui.accordion_item``. Le voisinage par
      sous-chaîne ne les trouve pas (il compare à la casse), donc le
      message renvoyait « n'existe pas » sur un nom qu'on peut importer.
      La correspondance se lit par IDENTITÉ sur le namespace ``ui`` —
      pas sur l'orthographe, qui rate tout ce qui porte un underscore ;
    - la PORTE — ``DatatableState`` s'exporte par ``bretzel.components``,
      un paquet sans table de classement.

    Dire « n'existe pas » d'un nom importable est la faute la plus chère
    du lot : elle est CRÉDIBLE, et elle fait renoncer.
    """
    owner = public_owners().get(symbol)
    if owner is None:
        return ""
    value = getattr(importlib.import_module(owner), symbol, None)
    catalogue = ui_name_of_class().get(value) if isinstance(value, type) else None
    if catalogue is not None:
        return f" It is the class behind `ui.{catalogue}`: `describe {catalogue}`."
    return (
        f" It can still be imported with `from {owner} import {symbol}`, but "
        f"{owner} has no category table and therefore no detail page."
    )

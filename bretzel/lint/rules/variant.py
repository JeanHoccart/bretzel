"""Règle : une valeur de ``variant=`` / ``size=`` qu'aucune table ne porte.

Le silence qu'elle ferme
------------------------

``compose_class`` résout ces deux props **par leur valeur**, dans une table
du thème (``bretzel/components/base/component.py``) ::

    variant_template = theme.get("variants", {}).get(variant_value)
    if variant_template:
        parts.append(...)

Un manque n'est pas une erreur : c'est un ``None``, un ``if`` qui ne prend
pas, et une classe de moins. Mesuré le 2026-08-16 sur
``ui.button(variant="does-not-exist")`` : le bouton rend **sans aucune
classe de variante** — ni fond, ni bordure, ni ombre. Il reste dans le flux,
il est cliquable, il n'a simplement plus l'air d'un bouton. Aucune erreur,
aucun attribut suspect dans le HTML.

Pourquoi ces deux props, et pas les 24 autres groupes-tables
-------------------------------------------------------------

``variant`` et ``size`` sont les **seules** que le socle résout lui-même,
pour tous les composants, par un chemin unique. ``widths``, ``gaps``,
``paddings``, ``ratios``, ``sides``… sont lus par le ``render`` de chaque
composant, avec sa propre correspondance prop → groupe. Les déduire d'une
règle de pluriel serait une table écrite à la main dans un linter,
c'est-à-dire la chose qui dérive du code qu'elle juge (même refus que
:mod:`bretzel.lint.rules.kwargs`).

⚠️ ``size=`` a coûté un détour, et il vaut d'être connu
--------------------------------------------------------

La symétrie avec ``variant`` est tentante — ``compose_class`` fait
``theme["sizes"].get(size_value)`` — mais lire les clés brutes de la table
est **faux** : sur les 44 tables ``sizes`` du catalogue, 33 sont
imbriquées, et deux imbrications OPPOSÉES y coexistent —

- ``Checkbox`` : ``{"sm": {<slot>: classes}}`` — clés = tailles ;
- ``DatePicker`` : ``{"input_field": {"sm": classes}}`` — clés = **slots**.

Une première version de cette règle a donc signalé
``ui.date_picker(size="sm")``, qui est parfaitement correct. Le
vocabulaire vient maintenant de :attr:`ComponentInfo.size_values`, résolu
par ``bretzel.components.base.size_vocabulary`` — qui absorbe les deux
étages en s'appuyant sur :data:`~bretzel.components.base.SIZE_SCALE`,
l'échelle canonique. Celle-ci n'existait pas dans ``bretzel/`` avant le
2026-08-16 : elle était recopiée cinq fois dans ``tests/``, ce qui aurait
fait de toute lecture d'ici une sixième copie.

⚠️ Quatre composants acceptent la prop **sans** avoir de table :
``bar_chart``, ``file_upload`` et ``pie_chart`` pour ``variant=``,
``radio_group`` pour ``size=``. Leur ``render`` en fait autre chose. Sans
la garde « pas de vocabulaire → on ne juge pas », chacun de leurs
call-sites serait un faux positif immédiat.

Noter que le vocabulaire de ``size`` n'est PAS le même partout :
``Heading`` et ``Text`` portent l'échelle typographique (``xs`` à
``8xl``), ``Avatar`` étend à ``2xl``. La règle lit le vocabulaire du
composant visé, jamais une échelle globale.

Ce qu'elle NE signale pas, et pourquoi c'est vital
---------------------------------------------------

Une variante que l'**application** déclare. ``Theme(components={"button":
{"variants": {"brand": …}}})`` suivi de ``ui.button(variant="brand")``
fonctionne (vérifié), et c'est le chemin recommandé pour dévier du thème
livré. Or ce thème vit presque toujours dans un autre fichier que ses
call-sites — donc une règle qui ne lirait que son propre module
condamnerait la forme qu'on recommande.

D'où la lecture du **corpus du passage** (:func:`bretzel.lint.corpus.current`) :
le vocabulaire jugé est l'union de ce que le framework livre et de ce que
l'app déclare **n'importe où sous les chemins analysés**. Hors ``run`` le
corpus est vide et la règle se rabat sur le module courant — elle dégrade,
elle ne ment pas.

⚠️ **La limite honnête** : un thème construit dynamiquement (dict assemblé,
chargé d'un fichier, importé d'un paquet non analysé) reste invisible. La
règle lit des dicts littéraux. C'est la frontière de tout ce qui est
statique, pas un défaut réparable ici — ``bretzel check --deep`` verrait le
thème monté.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from bretzel.lint.corpus import Module, current, derived
from bretzel.lint.report import Finding
from bretzel.lint.rules._theme_calls import component_maps, dict_items

RULE = "valeur-hors-table"

#: Les props que le socle résout par leur valeur. Le vocabulaire de
#: chacune vient de ``introspect.prop_vocabulary()``, qui sait que
#: ``variant`` lit les clés de ``variants`` alors que ``size`` demande la
#: résolution des deux imbrications.
_RESOLVED_BY_THE_CORE: tuple[str, ...] = ("variant", "size")

#: Le groupe de thème sous lequel une valeur MAISON se déclare. Distinct
#: du vocabulaire lu : `size` se lit résolu (deux imbrications absorbées)
#: mais se déclare, comme tout le reste, sous `sizes`.
_GROUP_OF: dict[str, str] = {"variant": "variants", "size": "sizes"}


def _shipped() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``variant`` / ``size`` → valeurs livrées.

    Lu depuis :func:`bretzel.introspect.prop_vocabulary`, indexé par PROP
    et non par groupe de thème — les deux ne coïncident pas, ``size``
    demandant la résolution des deux imbrications. Le pendant par groupe
    (:func:`~bretzel.introspect.theme_vocabulary`) sert, lui, à
    :mod:`bretzel.lint.rules.theme` et à la validation au démarrage.

    Indexé par ``THEME_KEY`` pour s'unir sans friction au vocabulaire
    déclaré par l'app, qui s'écrit sous cette clé-là.

    ⚠️ Pour CETTE règle, l'index par clé est aujourd'hui **indiscernable**
    d'un index par nom ``ui.*``, et la mutation qui l'inverse ne rougit
    nulle part — mesuré le 2026-08-16 plutôt que supposé. Des 8 composants
    portant une table ``variants``, un seul a une clé différente de son nom
    (``navbar_section`` → ``navbar``), et son frère ``navbar`` remplit déjà
    cette entrée avec le **même** objet ``THEME``.

    C'est écrit et non corrigé par un test tordu : la distinction devient
    porteuse le jour où un composant à variantes écrit sous une clé
    qu'aucun frère ne possède — et ce jour-là, l'index par nom donnerait un
    faux positif sur chacun de ses call-sites.
    """
    from bretzel.introspect import prop_vocabulary

    return prop_vocabulary()


def _ui_name_to_theme_key() -> dict[str, str]:
    """``ui.<nom>`` → sa clé de thème. Huit composants diffèrent."""
    from bretzel.introspect import ComponentInfo, describe_components

    return {
        info.ui_name: info.theme_key
        for info in describe_components()
        if isinstance(info, ComponentInfo) and info.theme_key
    }


def _declared_in(tree: ast.Module) -> dict[str, dict[str, set[str]]]:
    """Ce que les ``Theme(components={…})`` littéraux de cet arbre ajoutent.

    Le nœud de la clé, deuxième élément rendu par ``dict_items``, ne sert
    pas ici : cette règle agrège un VOCABULAIRE et ne situe rien.
    """
    out: dict[str, dict[str, set[str]]] = {}
    for components in component_maps(tree):
        for theme_key, _, comp_value in dict_items(components):
            groups = out.setdefault(theme_key, {})
            for group, _, group_value in dict_items(comp_value):
                groups.setdefault(group, set()).update(
                    key for key, _, _ in dict_items(group_value)
                )
    return out


def _merge(
    into: dict[str, dict[str, set[str]]], trees: Sequence[ast.Module]
) -> dict[str, dict[str, set[str]]]:
    """Verse les déclarations de ``trees`` dans ``into`` (muté et rendu)."""
    for tree in trees:
        for theme_key, groups in _declared_in(tree).items():
            target = into.setdefault(theme_key, {})
            for group, keys in groups.items():
                target.setdefault(group, set()).update(keys)
    return into


def _declared_everywhere(module: Module) -> dict[str, dict[str, set[str]]]:
    """L'union des déclarations de thème du corpus du passage.

    Le module courant est inclus explicitement : hors ``run`` le corpus est
    vide, et une règle appelée seule doit rester juste sur ce qu'elle voit.

    L'union est la MÊME pour les N modules d'un passage, donc elle est
    dérivée une fois (:func:`~bretzel.lint.corpus.derived`) et non une fois
    par module — sans quoi la règle est quadratique, ce qu'elle a été
    jusqu'au 2026-08-27 pour 56 s sur ``examples/``. Le seul cas qui sort
    de la mémoire est un module ABSENT du corpus : on repart alors d'une
    copie, pour ne pas polluer la dérivation partagée avec un arbre qui
    n'en fait pas partie.
    """
    corpus = current()
    if not corpus:
        return _merge({}, [module.tree])

    shared = derived(
        f"{RULE}.declared", lambda: _merge({}, [m.tree for m in current()])
    )
    if any(m.tree is module.tree for m in corpus):
        return shared
    return _merge(
        {key: {g: set(v) for g, v in groups.items()} for key, groups in shared.items()},
        [module.tree],
    )


def check(module: Module) -> list[Finding]:
    """Les valeurs qu'aucune table — livrée ou déclarée — ne porte."""
    calls = [
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ui"
        and any(kw.arg in _RESOLVED_BY_THE_CORE for kw in node.keywords)
    ]
    if not calls:
        return []

    shipped = _shipped()
    keys = _ui_name_to_theme_key()
    declared = _declared_everywhere(module)

    findings: list[Finding] = []
    for call in calls:
        ui_name = call.func.attr  # type: ignore[union-attr]
        theme_key = keys.get(ui_name)
        if theme_key is None:
            continue  # helper, ou symbole inconnu : `kwargs-inconnu` s'en charge
        for kw in call.keywords:
            prop = kw.arg or ""
            if prop not in _RESOLVED_BY_THE_CORE:
                continue
            if not isinstance(kw.value, ast.Constant) or not isinstance(
                kw.value.value, str
            ):
                continue  # valeur calculée : hors de portée d'une lecture statique
            known = shipped.get(theme_key, {}).get(prop, frozenset())
            if not known:
                # Pas de table du tout — le composant consomme la prop
                # autrement (`bar_chart`, `file_upload`, `pie_chart` pour
                # `variant`, `radio_group` pour `size`). On ne juge pas ce
                # qu'on ne comprend pas.
                continue
            group = _GROUP_OF[prop]
            allowed = known | declared.get(theme_key, {}).get(group, set())
            value = kw.value.value
            if value in allowed:
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=kw.value.lineno,
                    message=(
                        f"`ui.{ui_name}({prop}={value!r})` : aucune entrée "
                        f"`{value}` dans la table `{group}`."
                    ),
                    hint=(
                        f"Valeurs livrées : {', '.join(sorted(known))}. "
                        f"Le socle résout `{prop}=` dans `{group}` et "
                        f"IGNORE un manque — le composant rend sans la "
                        f"classe, sans erreur. Pour une valeur maison, "
                        f"déclare-la : "
                        f'Theme(components={{{theme_key!r}: {{{group!r}: '
                        f"{{{value!r}: …}}}}}})."
                    ),
                )
            )
    return findings

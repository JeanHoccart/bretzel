"""Règle : un nom de ``Theme(components={…})`` que rien ne lit.

Le silence qu'elle ferme
------------------------

La couche thème n'a jamais refusé une clé. Mesuré le 2026-08-16, sur
``main`` :

- ``Theme(components={"crad": {...}})`` — accepté. Le composant n'existe
  pas, la surcharge n'atteint jamais rien.
- ``Theme(components={"card": {"slotz": {...}}})`` — accepté. Le groupe
  n'existe pas.
- ``Theme(components={"card": {"slots": {"rooot": "..."}}})`` — accepté.
  ``Card`` compose ``root``, jamais ``rooot``.

Dans les trois cas le résultat est identique : **rien ne change**, sans
erreur, sans avertissement, sans trace dans le HTML. C'est le symptôme
qu'on attribue à son cache navigateur pendant une demi-heure avant de
soupçonner sa propre faute de frappe.

Pourquoi une règle et pas une levée
------------------------------------

Lever à la construction changerait le comportement d'applications
existantes : comme le silence est total aujourd'hui, personne ne sait si
son thème porte une clé morte. Le lint **constate** — il ne casse rien, et
il voit sans exécuter, donc il voit aussi le thème d'un module jamais
importé. La levée reste ouverte, inscrite dans ``.claude/work/todo.md``.

Ce qu'elle ne signale PAS, et c'est délibéré
--------------------------------------------

**Les clés inconnues des groupes adressés par une VALEUR de prop**
(``variants``, ``sizes``, ``paddings``, ``widths``, ``gaps``…). Y ajouter
une entrée est une **fonctionnalité**, pas une faute : c'est le chemin
par lequel une app déclare sa propre variante, et il marche —
``Theme(components={"button": {"variants": {"brand": "…"}}})`` suivi de
``ui.button(variant="brand")`` rend la variante (vérifié). Les signaler
condamnerait le seul moyen propre de dévier du thème livré.

**Les clés de ``slots``, elles, sont signalées** : un slot n'est pas
adressé par une valeur d'utilisateur mais composé par le code du
composant (``compose_class("root")``). Un nom que le composant ne compose
jamais est mort par construction — il n'y a aucun appel qui pourrait le
réveiller.

La règle est **pure** : un module, l'index d'API, des constats. Elle ne
connaît ni corpus, ni plancher.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding
from bretzel.lint.rules._theme_calls import component_maps, dict_items

RULE = "theme-vocabulaire-inconnu"

#: Le seul groupe dont on juge les CLÉS. Cf. le docstring : ailleurs, une
#: clé neuve est la façon supportée d'étendre le thème.
_KEYED_GROUP = "slots"


def _index() -> dict[str, dict[str, frozenset[str]]]:
    """``THEME_KEY`` → ``groupe`` → clés connues.

    Lu depuis :func:`bretzel.introspect.theme_vocabulary`, la source unique
    que partagent les deux règles de thème ET la validation au démarrage.
    Une table de noms écrite à la main dans un linter est exactement ce qui
    dérive du code qu'elle prétend juger — et deux dérivations parallèles
    en sont la version lente.
    """
    from bretzel.introspect import theme_vocabulary

    return theme_vocabulary()


def check(module: Module) -> list[Finding]:
    """Les noms de thème que rien ne lira."""
    findings: list[Finding] = []
    calls = list(component_maps(module.tree))
    if not calls:
        return findings

    index = _index()
    for components in calls:
        for comp_name, comp_key_node, comp_value in dict_items(components):
            groups = index.get(comp_name)
            if groups is None:
                findings.append(
                    Finding(
                        rule=RULE,
                        path=module.path,
                        line=comp_key_node.lineno,
                        message=(
                            f"`Theme(components={{{comp_name!r}: …}})` : aucun "
                            f"composant n'a cette clé de thème."
                        ),
                        hint=(
                            "La clé est `THEME_KEY`, pas toujours le nom `ui.*` "
                            "— `sidebar_section` s'écrit sous `'sidebar'`. "
                            "`bretzel describe <nom>` la donne."
                        ),
                    )
                )
                continue
            findings.extend(
                _check_groups(module, comp_name, groups, comp_value)
            )
    return findings


def _check_groups(
    module: Module,
    comp_name: str,
    groups: dict[str, tuple[str, ...]],
    comp_value: ast.expr,
) -> list[Finding]:
    findings: list[Finding] = []
    for group, group_key_node, group_value in dict_items(comp_value):
        if group not in groups:
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=group_key_node.lineno,
                    message=(
                        f"`Theme(components={{{comp_name!r}: {{{group!r}: …}}}})` : "
                        f"`{comp_name}` n'a pas de groupe `{group}`."
                    ),
                    hint=(
                        f"Ses groupes : {', '.join(sorted(groups)) or '(aucun)'}. "
                        f"`bretzel describe {comp_name}` les liste."
                    ),
                )
            )
            continue
        if group != _KEYED_GROUP:
            # Ailleurs, une clé neuve étend le thème — c'est supporté.
            continue
        known = groups[group]
        for slot, slot_key_node, _ in dict_items(group_value):
            if slot not in known:
                findings.append(
                    Finding(
                        rule=RULE,
                        path=module.path,
                        line=slot_key_node.lineno,
                        message=(
                            f"`{comp_name}` ne compose aucun slot `{slot}` — "
                            f"la surcharge n'atteindra rien."
                        ),
                        hint=(
                            f"Ses slots : {', '.join(known) or '(aucun)'}. "
                            f"Un slot est composé par le code du composant, "
                            f"donc un nom qu'il ignore est mort : rien ne peut "
                            f"le réveiller depuis l'app."
                        ),
                    )
                )
    return findings

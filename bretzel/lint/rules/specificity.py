"""Règle : une classe de ``classes=`` que la MÊME prop pose déjà.

Le silence qu'elle ferme
------------------------

``ui.vstack`` émet ``justify-start`` sans qu'on lui demande rien : la prop
``justify`` a un défaut, et un défaut émet. Écrire ::

    ui.vstack(gap="none", align="start", classes="h-full w-full justify-center px-3")

met donc **deux** ``justify-*`` sur le même élément ::

    <div class="flex flex-col items-start justify-start gap-0 h-full w-full justify-center px-3">

Les deux sélecteurs ont la même spécificité, donc c'est l'ordre de la
**feuille** Tailwind qui les départage — pas l'ordre de l'attribut
``class``, que tout le monde lit d'abord. Mesuré le 2026-09-06 sur
``examples/playground/features/diagram/ui.py`` : ``justify-start`` gagnait, le
contenu restait collé en haut alors que le code disait « centre ».

C'est le mode d'échec préféré du dépôt : rien ne lève, rien ne manque dans
le HTML, et une **relecture des classes ne voit rien** — les deux sont là,
toutes les deux correctes, toutes les deux voulues par quelqu'un. Même
mécanique que le « survol une ligne sur deux » de
``bretzel/components/data/table/theme.py`` (« hover vs striped
specificity »), où deux règles de spécificité égale se départagent par la
source.

La faute s'est produite **deux fois de suite** dans le même fichier
(commits ``9cdd7627`` puis ``db1b574c``), ce qui est la définition d'une
faute facile et invisible.

La table prop → famille est DÉRIVÉE, jamais recopiée
-----------------------------------------------------

Un linter qui porterait sa propre table ``justify → justify-*`` dériverait
du code qu'il juge — même refus que :mod:`bretzel.lint.rules.kwargs` et
:mod:`bretzel.lint.rules.variant`. Ici tout vient du composant vivant :

- ``THEME_TABLES`` donne **prop → groupe de thème** (déclaré sur
  :class:`~bretzel.components.layout.flex.flex.Flex`, gardé par
  ``test_a_flex_family_declares_every_table``) ;
- le groupe donne les **classes réellement émises**, donc le préfixe de la
  famille et la valeur de prop qui produit chacune ;
- ``__reactive_props__`` donne le **défaut**, c'est-à-dire ce qui est émis
  quand l'appel ne passe rien.

Une prop dont le composant change le défaut change donc la règle sans
qu'on la touche : ``HStack.align`` vaut ``center`` là où ``Flex.align``
vaut ``stretch``, et les deux sont lus, pas supposés.

⚠️ **Portée : les composants qui déclarent ``THEME_TABLES``** — les cinq de
la famille flex (``flex``, ``vstack``, ``hstack``, ``pane``, ``viewport``).
Les autres écrivent la correspondance prop → groupe dans leur ``render``,
où aucune lecture statique ne va la chercher ; ``ui.grid(gap=…)`` et
``ui.carousel(gap=…)`` sont donc hors de portée jusqu'à ce qu'ils la
déclarent. Écrit plutôt que deviné : mesuré le 2026-09-06, ni ``grid``, ni
``carousel``, ni ``resizable`` n'a un seul ``classes=`` de cette famille
dans le dépôt — l'angle mort ne coûte aujourd'hui rien, et le jour où il
coûtera, c'est ``THEME_TABLES`` qu'il faut poser, pas une table ici.

Ce qu'elle ne signale PAS, et c'est le cœur du réglage
------------------------------------------------------

``classes=`` **est** l'échappatoire légitime, et une règle qui la
condamnerait en gros se ferait désactiver le premier jour. La famille est
donc fermée sur ce que la prop sait dire : les classes que la table émet,
plus le préfixe suivi d'une de ses **clés** (c'est ainsi que
``justify-center`` en fait partie, alors que le thème rend
``[justify-content:safe_center]`` — un centrage ``safe``).

Trois conséquences mesurées :

- ``justify-normal`` / ``items-normal`` : hors table, aucune valeur de prop
  ne les rend → **jamais signalés**, c'est de l'échappatoire ;
- ``flex-1`` sur un ``ui.flex`` : la famille de ``direction`` est
  exactement ``flex-row|flex-col|flex-row-reverse|flex-col-reverse``, pas
  ``flex-*`` → épargné (le préfixe seul aurait fait quatre faux positifs
  par app) ;
- ``md:justify-center``, ``justify-center!``, ``[justify-content:…]`` :
  écarts **délibérés** de spécificité ou de portée, qui gagnent pour de
  bon → jamais signalés.

Angle mort assumé : ``gap-3`` (un palier hors table) se bat vraiment avec
le ``gap-4`` du défaut, et n'est pas signalé — il n'existe comme valeur
d'aucune prop, donc le signaler reviendrait à refuser l'échappatoire.

Mesure avant livraison
-----------------------

2026-09-06 : **21 constats** sur ``examples/``, **0** sur
``tests/e2e/apps``, **0** dans ``bretzel/``. Les 21 étaient tous le même
motif — un ``justify-*`` de ``classes=`` contre le ``justify-start`` du
défaut, dont sept pages d'erreur « centrées » qui ne l'étaient pas. Tous
corrigés en passant à la prop ; ``examples/`` est à zéro et gelé par
``test_lint_baseline_on_examples``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import cache
from typing import Any

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "classe-doublee-par-une-prop"

#: Les kwargs dont la valeur atterrit dans l'attribut ``class``.
_CLASS_KWARGS = ("classes", "class_")

#: Un caractère qui sort une classe du jugement. ``:`` = un variant
#: (``md:``, ``hover:``) donc une autre portée ET un autre rang dans la
#: feuille ; ``[`` / ``]`` = une valeur arbitraire, écrite exprès ; ``!`` =
#: l'important de Tailwind, c'est-à-dire un écart assumé qui gagne. Aucun
#: des trois n'est le doublon silencieux que cette règle cherche.
_DELIBERATE = "[]:!"


@dataclass(frozen=True)
class _Family:
    """Ce qu'une prop pose sur l'élément, vu depuis les classes."""

    prop: str
    #: classe → la valeur de prop qui la rend. C'est la famille.
    members: dict[str, str]
    #: valeur de prop → la classe (ou les classes) qu'elle rend.
    emits: dict[str, str]
    #: Ce que la prop rend quand l'appel ne passe rien. Vide = elle n'émet
    #: rien par défaut (``grow``), donc aucun conflit à supposer.
    default: str


def _deliberate(token: str) -> bool:
    return any(c in token for c in _DELIBERATE)


def _family_members(table: dict[str, Any]) -> dict[str, str]:
    """Les classes que ``table`` sait rendre, indexées par valeur de prop.

    Le préfixe se DÉDUIT des classes émises et doit être unique : un
    groupe qui mélangerait deux préfixes n'a pas de « famille » au sens de
    cette règle, et on préfère ne rien dire que dire n'importe quoi.

    Les clés de la table sont ensuite recollées au préfixe, ce qui rattrape
    les valeurs que le thème rend autrement qu'en utilitaire nommé —
    ``center`` rend ``[justify-content:safe_center]``, mais
    ``justify-center`` appartient bien à la famille.
    """
    emitted = {
        token
        for value in table.values()
        for token in str(value).split()
        if "-" in token and not _deliberate(token)
    }
    prefixes = {token.split("-", 1)[0] for token in emitted}
    if len(prefixes) != 1:
        return {}
    prefix = f"{prefixes.pop()}-"

    members: dict[str, str] = {}
    for key, value in table.items():
        for token in str(value).split():
            if token in emitted:
                members.setdefault(token, str(key))
        members.setdefault(f"{prefix}{key}", str(key))
    return members


@cache
def _families_of(cls: type) -> tuple[_Family, ...]:
    """Les familles de classes que les props de ``cls`` pilotent.

    Vide pour tout composant qui ne déclare pas ``THEME_TABLES`` — la
    correspondance prop → groupe vit alors dans son ``render``, hors de
    portée d'une lecture statique.
    """
    tables = getattr(cls, "THEME_TABLES", None)
    theme = getattr(cls, "THEME", None)
    if not isinstance(tables, dict) or not isinstance(theme, dict):
        return ()

    props = getattr(cls, "__reactive_props__", None) or {}
    families: list[_Family] = []
    for prop, group in sorted(tables.items()):
        table = theme.get(group)
        if not isinstance(table, dict):
            # Groupe scalaire (``wrap`` est la chaîne ``flex-wrap``) : pas
            # une famille, et poser deux fois la même classe ne fait rien.
            continue
        members = _family_members(table)
        if not members:
            continue
        default = getattr(props.get(prop), "default", None)
        families.append(
            _Family(
                prop=prop,
                members=members,
                emits={str(k): str(v) for k, v in table.items()},
                default=default if isinstance(default, str) else "",
            )
        )
    return tuple(families)


def _judged() -> dict[str, tuple[_Family, ...]]:
    """``ui.<nom>`` → ses familles, pour les composants qu'on sait lire."""
    from bretzel.components import ui
    from bretzel.components.base.component import Component
    from bretzel.introspect import ui_symbol_names

    out: dict[str, tuple[_Family, ...]] = {}
    for name in ui_symbol_names():
        value = getattr(ui, name, None)
        if not (isinstance(value, type) and issubclass(value, Component)):
            continue
        families = _families_of(value)
        if families:
            out[name] = families
    return out


def _constant_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _finding(
    module: Module,
    call: ast.Call,
    ui_name: str,
    family: _Family,
    token: str,
    keywords: dict[str, ast.expr],
) -> Finding | None:
    """Le constat, ou ``None`` si la prop n'émet rien ici.

    Le ``None`` est load-bearing : une prop dont le défaut est vide
    (``grow``) ne pose aucune classe tant que l'appel ne lui en donne pas,
    donc il n'y a rien à départager. Une valeur passée mais **calculée**
    retombe sur le défaut : quoi qu'elle vaille, le socle rend soit sa
    classe, soit celle du défaut — dans les deux cas une classe de cette
    famille, donc le conflit tient.
    """
    passed = _constant_str(keywords.get(family.prop))
    value = passed or family.default
    if not value:
        return None

    posed = family.emits.get(value, f"la classe de `{family.prop}={value!r}`")
    origin = "passé ici" if passed else "son défaut"
    wanted = family.members[token]

    if posed == token:
        message = (
            f"`ui.{ui_name}(classes=…)` répète `{token}` : la prop "
            f"`{family.prop}=` la pose déjà ({origin})."
        )
        hint = (
            f"Retire `{token}` de `classes=` — `{family.prop}={value!r}` "
            f"suffit, et c'est lui qui reste vrai si le thème change."
        )
    else:
        message = (
            f"`ui.{ui_name}(classes=…)` pose `{token}` sur le MÊME élément "
            f"que la prop `{family.prop}=`, qui émet déjà `{posed}` "
            f"({origin}). Deux classes de même spécificité : c'est l'ordre "
            f"de la FEUILLE Tailwind qui tranche, pas celui de l'attribut "
            f"`class` — le HTML porte les deux et rien ne dit laquelle a "
            f"gagné."
        )
        hint = (
            f"Écris `{family.prop}={wanted!r}` : c'est la valeur qui rend "
            f"`{token}`. `classes=` ne sert qu'à ce qu'aucune prop ne "
            f"couvre."
        )
    return Finding(
        rule=RULE,
        path=module.path,
        line=call.lineno,
        message=message,
        hint=hint,
    )


def check(module: Module) -> list[Finding]:
    """Les classes de ``classes=`` qu'une prop du même appel pose déjà."""
    calls = [
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "ui"
    ]
    if not calls:
        return []

    judged = _judged()
    findings: list[Finding] = []
    for call in calls:
        ui_name = call.func.attr  # type: ignore[union-attr]
        families = judged.get(ui_name)
        if not families:
            continue
        keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
        written = next(
            (
                text
                for name in _CLASS_KWARGS
                if (text := _constant_str(keywords.get(name)))
            ),
            None,
        )
        if not written:
            continue

        for token in written.split():
            if _deliberate(token):
                continue
            for family in families:
                if token not in family.members:
                    continue
                found = _finding(module, call, ui_name, family, token, keywords)
                if found is not None:
                    findings.append(found)
    return findings

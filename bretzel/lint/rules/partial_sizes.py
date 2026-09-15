"""Règle : un thème qui retaille UNE PARTIE des contrôles de formulaire.

Le silence qu'elle ferme
------------------------

Une table de tailles écrite à la main est une liste de composants qu'on a
pensé à citer, et **rien ne dit qu'elle est complète** ::

    Theme(components={
        "input":    {"sizes": {"md": {"input": "h-8 px-3"}}},
        "select":   {"sizes": {"md": {"trigger": "h-8 px-3"}}},
        "combobox": {...},
        # date_picker, number_input, time_picker… : absents
    })

Les composants cités descendent, les autres gardent le défaut. Mesuré sur
``examples/ecole`` le 2026-09-12 : **quatre hauteurs de champ texte sur un
même écran — 30, 32, 36 et 38 px**, et un formulaire de trois contrôles
côte à côte en montrait trois. C'est un utilisateur qui l'a vu sur une
capture d'écran ; rien d'autre ne pouvait le dire.

Pourquoi les règles existantes ne l'attrapent pas
--------------------------------------------------

:mod:`bretzel.lint.rules.sizes` compare les ``size=`` **déclarés aux
call-sites** : ici ils sont tous au défaut, et d'accord entre eux. C'est
le THÈME qui les sépare, en aval. Et
``tests/runtime_js/test_form_controls_share_one_height.py`` mesure la
parité des hauteurs **avec le thème livré** — une app qui pose le sien
sort de sa portée.

L'invariant défendu est le même que celui de cette gate, et c'est lui qui
rend ``size=`` utilisable : à palier égal, un contrôle de formulaire fait
une hauteur. Une surcharge partielle le casse en silence.

Ce que la règle lit
--------------------

Les clés d'un ``Theme(components={…})`` qui portent un ``sizes``, et la
famille de contrôles **découverte** par
:func:`~bretzel.introspect.describe_components` — jamais une table écrite
ici. Un dix-neuvième champ entre donc tout seul dans la règle, comme il
entre dans :mod:`bretzel.lint.rules.sizes`.

⚠️ **Et les contrôles que le CORPUS utilise vraiment.** C'est ce qui
sépare un constat actionnable d'un bruit : un thème n'a aucune raison de
retailler un ``ui.otp_input`` qu'aucun écran n'affiche, et le lui
reprocher ferait d'une règle utile une liste à rallonge. Le corpus du
passage est lu par :func:`bretzel.lint.corpus.derived`, donc une seule
fois quels que soient le nombre de modules.

Mesuré sur ce dépôt : sans ce filtre, la règle réclame quatorze
composants au preset du kanban ; avec, elle en nomme deux — et ce sont
exactement les deux qu'il affiche.

Si le thème en retaille au moins un et en oublie au moins un que l'app
montre, c'est un constat, qui NOMME les manquants.

⚠️ Ce que la règle ne dit PAS
------------------------------

Qu'il faille retailler tout le monde. La sortie recommandée est l'INVERSE
— ne nommer personne, et déplacer la BASE de l'échelle : toute l'échelle
d'espacement de Tailwind dérive de ``--spacing``, que ``Theme(spacing=…)``
porte depuis le 2026-09-13 (avant, il fallait passer par ``css=``, ce qui
n'était pas ce à quoi cette porte sert). Un jeton au lieu de N tables,
donc une couverture qui n'est plus une liste et ne peut plus être
partielle. Et le défaut livré est DÉJÀ celui d'un outil : une table de
tailles qui ne fait que resserrer n'a probablement plus lieu d'être.

Elle ne juge pas non plus une surcharge qui ne touche pas ``sizes``
— couleurs, rayons, slots : celles-là ne déplacent aucune hauteur.

Ni le cas d'un thème SANS corpus — une règle exercée sur un module seul
n'a pas d'usage à lire, et juge alors la famille entière. C'est le sens
sûr : hors ``run``, mieux vaut un constat de trop qu'un silence.
"""

from __future__ import annotations

import ast
import pathlib

from bretzel.lint import corpus
from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

#: Le nom de la règle, tel qu'il s'affiche dans un constat.
RULE = "palier-de-taille-a-moitie-surcharge"


def _famille() -> frozenset[str]:
    """Les contrôles de formulaire qui doivent partager une hauteur.

    Lue vivante par introspection : la famille ``inputs`` restreinte à ce
    qui porte un vocabulaire de ``size``. C'est le même corpus que
    :mod:`bretzel.lint.rules.sizes`, et pour la même raison — une table
    recopiée dans un linter dérive du code qu'elle juge.
    """
    from bretzel.introspect import ComponentInfo, describe_components

    return frozenset(
        info.ui_name
        for info in describe_components()
        if isinstance(info, ComponentInfo)
        and info.family == "inputs"
        and info.size_values
    )


def _theme_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "Theme")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "Theme")
        )
    ]


def _module_dicts(tree: ast.AST) -> dict[str, ast.Dict]:
    """Les constantes de module qui valent un littéral de dict.

    ``Theme(components=COMPONENTS)`` est l'idiome de ce dépôt — les deux
    presets d'``examples/`` l'écrivaient ainsi jusqu'au 2026-09-13, où
    l'échelle est passée au framework et où ils ont été supprimés. Une
    règle qui n'accepte que le dict EN LIGNE serait verte sur tout le
    corpus réel, ce qui est la forme la plus coûteuse de faux négatif :
    elle a l'air de marcher.
    """
    out: dict[str, ast.Dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        cibles = node.targets if isinstance(node, ast.Assign) else [node.target]
        for cible in cibles:
            if isinstance(cible, ast.Name):
                out[cible.id] = node.value
    return out


def _resized(call: ast.Call, connus: dict[str, ast.Dict]) -> tuple[set[str], int]:
    """Les composants dont ce ``Theme`` redéfinit les ``sizes``."""
    for kw in call.keywords:
        if kw.arg != "components":
            continue
        valeur_kw = kw.value
        if isinstance(valeur_kw, ast.Name):
            valeur_kw = connus.get(valeur_kw.id)
        if not isinstance(valeur_kw, ast.Dict):
            continue
        noms: set[str] = set()
        for cle, valeur in zip(valeur_kw.keys, valeur_kw.values, strict=False):
            if not (isinstance(cle, ast.Constant) and isinstance(cle.value, str)):
                continue
            if not isinstance(valeur, ast.Dict):
                continue
            if any(
                isinstance(k, ast.Constant) and k.value == "sizes"
                for k in valeur.keys
            ):
                noms.add(cle.value)
        return noms, call.lineno
    return set(), call.lineno


def _app_root(theme: pathlib.Path) -> pathlib.Path | None:
    """Le dossier d'app auquel ce thème appartient, ou ``None``.

    Reconnu par la présence d'un ``main.py`` DANS LE CORPUS — pas sur le
    disque : une règle statique ne doit rien découvrir que le passage
    n'ait pas déjà lu. On remonte depuis le thème et on s'arrête au
    premier dossier qui en porte un.

    ⚠️ Sans ce découpage, la règle est inutile sur un dépôt à plusieurs
    apps : balayer ``examples/`` d'un coup met le playground dans le même
    sac, et le playground exerce TOUS les composants — donc tout thème
    devrait tout retailler. Mesuré : 14 composants réclamés au preset du
    kanban, contre 2 une fois l'app délimitée. La version large avait
    l'air plus stricte et ne servait à rien.
    """
    dossiers = {
        m.path.resolve().parent
        for m in corpus.current()
        if m.path.name == "main.py"
    }
    for parent in theme.resolve().parents:
        if parent in dossiers:
            return parent
    return None


def _utilises(theme: pathlib.Path) -> frozenset[str]:
    """Les ``ui.<nom>`` appelés dans l'app à laquelle ce thème appartient.

    Dérivé une fois par app et par passage (cf.
    :func:`bretzel.lint.corpus.derived`) : la règle tourne sur chaque
    module, la question ne change pas.
    """
    racine = _app_root(theme)
    if racine is None:
        return frozenset()

    def build() -> frozenset[str]:
        return frozenset(
            node.func.attr
            for m in corpus.current()
            if racine in m.path.resolve().parents
            for node in ast.walk(m.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "ui"
        )

    return corpus.derived(f"partial_sizes.ui_calls:{racine}", build)


def check(module: Module) -> list[Finding]:
    """Les thèmes qui retaillent une partie de la famille seulement."""
    famille = _famille()
    if not famille:  # pragma: no cover — l'introspection est gatée ailleurs
        return []
    montres = _utilises(module.path)
    if montres:
        famille = frozenset(famille & montres)

    findings: list[Finding] = []
    connus = _module_dicts(module.tree)
    for call in _theme_calls(module.tree):
        retailles, line = _resized(call, connus)
        touches = retailles & famille
        if not touches:
            continue
        oublies = sorted(famille - retailles)
        if not oublies:
            continue
        findings.append(
            Finding(
                rule=RULE,
                path=module.path,
                line=line,
                message=(
                    f"ce thème retaille {len(touches)} contrôle(s) de "
                    f"formulaire et en laisse {len(oublies)} au défaut — "
                    f"{', '.join(oublies[:4])}"
                    + (" …" if len(oublies) > 4 else "")
                    + "."
                ),
                hint=(
                    "À palier égal, deux contrôles doivent faire une "
                    "hauteur : c'est ce qui rend `size=` utilisable. Une "
                    "table partielle casse l'invariant sans rien lever "
                    "(mesuré : quatre hauteurs de champ sur un écran). "
                    "Plutôt que d'allonger la liste, déplace la BASE de "
                    'l\'échelle : Theme(spacing="0.1875rem"). Toute '
                    "l'échelle Tailwind en dérive, donc rien ne peut être "
                    "oublié — et le défaut livré est déjà celui d'un outil, "
                    "donc une table qui ne fait que resserrer est peut-être "
                    "devenue inutile."
                ),
            )
        )
    return findings

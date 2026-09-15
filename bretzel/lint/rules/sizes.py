"""Règle : des contrôles de formulaire FRÈRES à des tailles différentes.

Le silence qu'elle ferme
------------------------

Rien ne casse. Aucune classe ne manque, aucun attribut n'est inerte, la
page rend à 200 et l'app marche. Deux champs côte à côte n'ont simplement
pas la même hauteur ::

    with ui.grid(cols=2):
        with ui.form_field(label="Période"):
            ui.date_range_picker(size="sm")     # h-8 → 32 px
        with ui.form_field(label="Type"):
            ui.select(...)                       # défaut md → 40 px

Huit pixels. C'est le genre d'écart qu'une revue de code ne voit pas —
les deux lignes sont correctes prises séparément, et le défaut n'existe
que dans leur *voisinage*. Mesuré sur ce dépôt le 2026-08-23 : deux
fautes réelles, dont une trouvée par un utilisateur sur une capture
d'écran et l'autre jamais vue par personne.

Ce que la règle considère comme un voisinage
---------------------------------------------

Les conteneurs **de ligne** : ``ui.grid``, ``ui.hstack``, ``ui.form``.
Pas ``ui.vstack``, et c'est mesuré, pas supposé. Sur ``examples/`` ::

    {grid, hstack, form}           180 groupes uniformes,  2 mélangés
    {grid, hstack, form, vstack}   401 groupes uniformes, 22 mélangés

Les 20 constats supplémentaires sont tous des faux positifs de la même
espèce : ``ui.vstack`` est le conteneur de PAGE de ce dépôt, donc un
groupe avale une carte entière d'un banc — trente contrôles qui ne se
touchent jamais à l'écran. Un voisinage qui contient toute la page n'est
pas un voisinage.

Le balayage ne redescend pas dans un conteneur imbriqué : deux lignes
distinctes sont deux groupes, pas un.

Pourquoi les défauts sont RÉSOLUS
----------------------------------

``ui.select(size="md")`` et ``ui.select()`` rendent le même HTML. Traiter
« absent » comme une valeur à part entière produirait un constat sur du
code correct — c'est la moitié qui coûte (cf.
``test_lint_rules_are_not_vacuous``). Le défaut est donc lu sur la
**classe**, par le descripteur ``reactive_prop``, jamais deviné.

Une taille calculée (``size=state.taille``) est hors de portée d'une
lecture statique : le contrôle est ignoré, il ne compte ni comme
d'accord ni comme en désaccord.

La famille jugée
-----------------

Les composants de la famille ``inputs`` qui portent un vocabulaire de
``size`` — **découverts** par :func:`~bretzel.introspect.describe_components`,
jamais listés ici. Un dix-neuvième champ y entre tout seul. C'est le même
refus que :mod:`bretzel.lint.rules.variant` oppose aux tables écrites à la
main dans un linter : elles dérivent du code qu'elles jugent.

⚠️ Ce que la règle ne dit PAS
------------------------------

Qu'un ``size=`` égal donne une hauteur égale. C'est un fait de moteur de
rendu, pas de texte — les cinq pickers ont rendu 2 px de trop pendant
toute la vie du dépôt **en écrivant le même token** que les autres. Aucun
linter ne peut voir ça ; c'est
``tests/runtime_js/test_form_controls_share_one_height.py`` qui le garde.

Et elle n'a pas d'échappatoire. Un mélange délibéré — un banc qui compare
deux tailles côte à côte — se gèle dans
``test_lint_baseline_on_examples``, avec sa raison, comme les six appels
``ui.html`` non littéraux du playground.
"""

from __future__ import annotations

import ast
import collections

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "tailles-melangees"

#: Les conteneurs de LIGNE. Le choix est mesuré — cf. la docstring.
_ROW_CONTAINERS: frozenset[str] = frozenset({"grid", "hstack", "form"})


def _judged() -> dict[str, str]:
    """``ui.<nom>`` → sa taille par défaut, pour la famille ``inputs``.

    Lu vivant : la famille vient de l'introspection, le défaut du
    descripteur ``reactive_prop`` porté par la classe. Rien n'est recopié
    ici, donc rien ne peut diverger du catalogue.
    """
    from bretzel.components import ui as ui_ns
    from bretzel.components.base.component import Component
    from bretzel.introspect import ComponentInfo, describe_components

    out: dict[str, str] = {}
    for info in describe_components():
        if not isinstance(info, ComponentInfo):
            continue
        if info.family != "inputs" or not info.size_values:
            continue
        cls = getattr(ui_ns, info.ui_name, None)
        if not (isinstance(cls, type) and issubclass(cls, Component)):
            continue
        for base in cls.__mro__:
            descriptor = vars(base).get("size")
            default = getattr(descriptor, "default", None)
            if isinstance(default, str):
                out[info.ui_name] = default
                break
    return out


def _ui_name(node: ast.AST) -> str | None:
    """``ui.input(...)`` → ``"input"``, sinon ``None``."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "ui"
    ):
        return func.attr
    return None


def _resolved_size(call: ast.Call, ui_name: str, defaults: dict[str, str]) -> str | None:
    """La taille EFFECTIVE de cet appel, ou ``None`` si illisible."""
    for kw in call.keywords:
        if kw.arg != "size":
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
        return None  # calculée : hors de portée d'une lecture statique
    return defaults.get(ui_name)


def _controls_under(
    node: ast.AST, judged: dict[str, str]
) -> list[tuple[ast.Call, str]]:
    """Les contrôles de CE voisinage — sans redescendre dans un conteneur
    imbriqué, qui est une autre ligne et donc un autre groupe."""
    found: list[tuple[ast.Call, str]] = []
    for child in ast.iter_child_nodes(node):
        name = _ui_name(child)
        if name in judged:
            found.append((child, name))  # type: ignore[arg-type]
            continue
        if name in _ROW_CONTAINERS:
            continue
        found.extend(_controls_under(child, judged))
    return found


def check(module: Module) -> list[Finding]:
    """Un constat par voisinage dont les contrôles ne s'accordent pas."""
    rows = [
        node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.With)
        and any(_ui_name(item.context_expr) in _ROW_CONTAINERS for item in node.items)
    ]
    if not rows:
        return []

    judged = _judged()
    findings: list[Finding] = []

    for row in rows:
        found = [c for stmt in row.body for c in _controls_under(stmt, judged)]
        sized = [
            (call, name, size)
            for call, name in found
            if (size := _resolved_size(call, name, judged)) is not None
        ]
        if len(sized) < 2:
            continue
        tally = collections.Counter(size for _, _, size in sized)
        if len(tally) < 2:
            continue

        # Qui est en tort ? Seulement s'il y a une majorité STRICTE. Sur
        # une égalité 1–1 — la forme exacte de la faute du CRM — désigner
        # un coupable est arbitraire : `most_common` rendait le premier
        # inséré, donc la règle accusait le champ correct. On nomme alors
        # les deux et on laisse l'auteur trancher.
        ranked = tally.most_common()
        strict = len(ranked) > 1 and ranked[0][1] > ranked[1][1]

        if strict:
            majority = ranked[0][0]
            guilty = [(c, n, sz) for c, n, sz in sized if sz != majority]
            line = guilty[0][0].lineno
            named = ", ".join(f"`ui.{n}`={sz!r}" for _, n, sz in guilty[:3])
            message = (
                f"{named} voisine(nt) {tally[majority]} contrôle(s) à "
                f"{majority!r} dans le même conteneur."
            )
        else:
            line = sized[0][0].lineno
            seen: list[str] = []
            for _, n, sz in sized:
                label = f"`ui.{n}`={sz!r}"
                if label not in seen:
                    seen.append(label)
            message = (
                "des contrôles frères n'ont pas la même taille : "
                + ", ".join(seen[:4])
                + ("…" if len(seen) > 4 else "")
                + "."
            )

        findings.append(
            Finding(
                rule=RULE,
                path=module.path,
                line=line,
                message=message,
                hint=(
                    "Des champs frères à des tailles différentes ne "
                    "s'alignent pas : chaque palier est une hauteur "
                    "distincte, et l'écart ne se voit que sur la page "
                    "rendue. Mets-les à la même taille — ou sépare-les, "
                    "un conteneur imbriqué est un autre voisinage. Un "
                    "défaut compte comme sa valeur : "
                    f"`ui.{sized[0][1]}()` vaut "
                    f"{judged.get(sized[0][1], '?')!r}."
                ),
            )
        )
    return findings

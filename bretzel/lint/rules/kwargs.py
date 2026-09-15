"""Règle : un kwarg passé à ``ui.*`` que le composant n'accepte pas.

**Pourquoi cette règle existe encore alors que le socle refuse.**
Jusqu'au 2026-08-16, ``split_kwargs`` avait un catch-all muet : un kwarg
inconnu partait dans le DOM en attribut inerte. Mesuré sur ``examples/``
le 2026-08-01 : **44 kwargs morts, 10 familles**, dont
``ui.input(label="…")`` sur **22 sites** rendant
``<input label="Display name">`` — aucun libellé affiché.

Le socle **lève** désormais (cf. ``attrs.py`` § échappatoire déclarée), ce
qui rend cette règle redondante… à l'exécution seulement. Elle garde deux
raisons d'être, et elles comptent :

1. **Elle voit sans exécuter.** Un composant dans une branche jamais
   empruntée, une page rarement rendue, un chemin derrière un ``if`` —
   le socle ne lèvera que le jour où quelqu'un passe par là. La règle
   lit le call-site, donc elle le voit tout de suite.
2. **Elle voit ce que le socle ne PEUT pas voir.** La validité d'un
   attribut HTML dépend du tag rendu, que ``split_kwargs`` ne connaît pas
   (``tag=`` est retiré avant). ``ui.button(href=…)`` sans ``tag="a"``
   passe le socle et reste inerte ; la règle, elle, connaît le call-site
   entier.

La règle est **pure** : elle prend un module et l'index d'API, elle ne
connaît ni corpus ni plancher (cf. :mod:`bretzel.lint.corpus`).
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "kwargs-inconnu"

#: L'échappatoire HTML brute n'est PAS redéclarée ici : elle est lue sur le
#: socle (:func:`bretzel.components.base.attrs.is_declared_raw_attr`), qui
#: la fait respecter à l'exécution depuis le 2026-08-16. Une seule table,
#: un seul comportement — sinon le lint et le runtime finiraient par ne
#: plus dire la même chose, et c'est le lint qu'on croirait.
#:
#: ``hx_`` est ajouté ici seul : le socle le refuse (il n'admet que la
#: forme à tiret), donc il serait signalé comme kwarg inconnu — mais
#: :mod:`bretzel.lint.rules.transport` le diagnostique MIEUX, en disant ce
#: qui manque vraiment (la signature HMAC). Un problème, un constat.
_TRANSPORT_PREFIXES = ("hx_", "hx-")

#: Sentinelle : le symbole existe mais n'est pas jugeable ici.
#:
#: Un objet dédié, et pas un ``frozenset()`` vide comparé par identité :
#: CPython ne garantit pas qu'il n'internera jamais le frozenset vide, et
#: un composant qui n'accepterait rien deviendrait alors indistinguable
#: d'un helper — silencieusement, dans le sens qui NE signale rien.
_NOT_JUDGED: object = object()


def _accepted(ui_name: str) -> frozenset[str] | object | None:
    """Ce que ``ui.<name>`` accepte.

    ``None`` = le symbole n'existe pas. :data:`_NOT_JUDGED` = il existe
    mais **on ne le juge pas** : les helpers (``ui.each``,
    ``ui.notification``, ``ui.column``…) ont leur propre contrat et lèvent
    d'eux-mêmes sur un kwarg inconnu — les passer à la moulinette du
    catch-all produirait des faux positifs sur ceux qui déclarent
    ``**kwargs``, pour un gain nul puisqu'ils ne sont pas silencieux.
    Le catch-all raw-HTML, lui, est une affaire de composants.
    """
    from bretzel.introspect import (
        RESERVED_KWARGS,
        ComponentInfo,
        describe_ui_symbol,
        ui_symbol_names,
    )

    if ui_name not in ui_symbol_names():
        return None
    info = describe_ui_symbol(ui_name)
    if not isinstance(info, ComponentInfo):
        return _NOT_JUDGED
    return frozenset(
        {p.name for p in info.params}
        | set(RESERVED_KWARGS)
        | set(info.handler_kwargs)
        | set(info.named_slots)
    )


def _is_raw_attr(name: str) -> bool:
    from bretzel.components.base.attrs import (
        is_declared_raw_attr,
        is_passthrough_attr,
    )

    return (
        is_passthrough_attr(name)
        or is_declared_raw_attr(name)
        or name.startswith(_TRANSPORT_PREFIXES)
    )


def check(module: Module) -> list[Finding]:
    """Les kwargs qu'aucun composant appelé ici ne lit."""
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "ui"
        ):
            continue
        accepted = _accepted(func.attr)
        if accepted is None:
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=node.lineno,
                    message=f"`ui.{func.attr}` n'existe pas.",
                    hint="`bretzel describe --index` liste la surface réelle.",
                )
            )
            continue
        if accepted is _NOT_JUDGED:
            continue
        for keyword in node.keywords:
            if not keyword.arg or _is_raw_attr(keyword.arg):
                continue
            if keyword.arg not in accepted:
                findings.append(
                    Finding(
                        rule=RULE,
                        path=module.path,
                        line=keyword.lineno,
                        message=(
                            f"`ui.{func.attr}({keyword.arg}=…)` : le composant "
                            f"ne lit pas ce kwarg — il partira dans le DOM en "
                            f"attribut inerte, sans erreur ni effet."
                        ),
                        hint=(
                            f"`bretzel describe {func.attr}` montre ce qu'il "
                            f"accepte ; pour un attribut HTML voulu, "
                            f"`attrs={{...}}`."
                        ),
                    )
                )
    return findings

"""Lecture d'une signature Python vivante — la primitive partagée.

Sortie de ``examples/docs/lib/introspect.py`` le 2026-08-16, en même temps
que le reste du moteur : tant qu'il vivait dans un exemple, ni le
framework, ni un CLI, ni un outillage tiers ne pouvait en dépendre (un
module de ``bretzel/`` ne peut pas importer ``examples/``).

Nommé ``_signature`` et non ``_labels`` — il ne porte pas que des
étiquettes, il porte :func:`describe_callable`, que toutes les sections de
:mod:`bretzel.introspect` réutiliseront (state, config, server…). Le
réutiliser AVANT de relister à la main les paramètres d'un appelable.
"""

from __future__ import annotations

import inspect
from functools import cache

from bretzel.introspect.model import CallableInfo, ParamInfo

_PARAM_KIND_LABELS = {
    inspect.Parameter.POSITIONAL_ONLY: "positionnel",
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "positionnel",
    inspect.Parameter.KEYWORD_ONLY: "keyword-only",
    inspect.Parameter.VAR_POSITIONAL: "*args",
    inspect.Parameter.VAR_KEYWORD: "**kwargs",
}

REQUIRED_LABEL = "— (requis)"


def type_label(hint: object) -> str:
    """Étiquette compacte et lisible pour un type résolu."""
    if hint is None:
        return "?"
    name = getattr(hint, "__name__", None)
    if name:
        return name
    return str(hint).replace("typing.", "")


def default_label(value: object) -> str:
    """Étiquette d'une valeur par défaut déjà connue (hors signature)."""
    return repr(value)


@cache
def describe_callable(fn: object) -> CallableInfo:
    """Lit la signature vivante d'un appelable.

    Mis en cache sur ``fn`` : une signature est fixe pour la durée du
    process. ``self`` est retiré — la fiche se lit comme le site d'appel.
    """
    sig = inspect.signature(fn)
    params: list[ParamInfo] = []
    for name, p in sig.parameters.items():
        if name == "self":
            continue
        annotation = p.annotation
        label = type_label(annotation) if annotation is not inspect.Parameter.empty else "—"
        if p.default is not inspect.Parameter.empty:
            default = default_label(p.default)
        elif p.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            default = ""
        else:
            default = REQUIRED_LABEL
        params.append(
            ParamInfo(
                name=name,
                kind=_PARAM_KIND_LABELS.get(p.kind, "?"),
                type_label=label,
                default_label=default,
            )
        )

    return CallableInfo(
        name=getattr(fn, "__name__", repr(fn)),
        params=tuple(params),
        doc=inspect.getdoc(fn),
    )

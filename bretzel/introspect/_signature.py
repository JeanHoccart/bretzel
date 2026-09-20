"""Reading a live Python signature — the shared primitive.

Taken out of ``examples/docs/lib/introspect.py`` on 2026-08-16, at the
same time as the rest of the engine: as long as it lived in an example,
neither the framework, nor a CLI, nor third-party tooling could depend on
it (a module in ``bretzel/`` cannot import ``examples/``).

Named ``_signature`` and not ``_labels`` — it carries more than labels,
it carries :func:`describe_callable`, which every section of
:mod:`bretzel.introspect` will reuse (state, config, server…). Reuse it
BEFORE re-listing a callable's parameters by hand.
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
    """A compact, readable label for a resolved type."""
    if hint is None:
        return "?"
    name = getattr(hint, "__name__", None)
    if name:
        return name
    return str(hint).replace("typing.", "")


def default_label(value: object) -> str:
    """The label of an already-known default value (outside a signature)."""
    return repr(value)


@cache
def describe_callable(fn: object) -> CallableInfo:
    """Read a callable's live signature.

    Cached on ``fn``: a signature is fixed for the process's lifetime.
    ``self`` is removed — the card reads like the call site.
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

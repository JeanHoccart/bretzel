"""The deep tier — the one that IMPORTS the application.

The static rules read files; these read a **mounted** app. That is what
lets them answer questions no AST can settle: "is this routable covered
by a Feature?", "does this contract match the real imports?". In
exchange, they run the user's code — hence the separate flag, and hence
the fact that it will never be the default.

**The input contract** is that of every ASGI runner
(``uvicorn my_app.main:app``): ``module:attribute``. Reusing it rather
than inventing a syntax spares having to learn one, and it is already in
the fingers of whoever starts the server.

Both lints have existed since 2026-07-05 in :mod:`bretzel.server` and ran
**only at startup**, as WARN on stdout. Nothing allowed running them cold,
nor turning them into an exit code. That is all this module adds: an
entry point and a translation into
:class:`~bretzel.lint.report.Finding`.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from bretzel.lint.report import Finding, Report

RULE_UNDECLARED = "routable-non-declare"
RULE_DRIFT = "contrat-derive"

#: What we accept as a target. Aligned with the ASGI runners.
TARGET_SYNTAX = "module:attribut  (ex. `examples.mad.main:app`)"


def load_app(target: str) -> tuple[object, Path]:
    """Import ``module:attribute`` and return the object.

    Returns ``(object, the module's file)`` — the file serves to anchor
    the findings on something openable. A map finding has no line (it is
    about a contract, not an expression), but it has at least a file, and
    "``<app>``" opens nothing.

    It calls nothing: a Bretzel app's ``include()`` run at the module's
    import, so the ``Feature`` and the routables are already collected
    when the object exists. We do NOT start the server — the lifespan
    would do far more than read.
    """
    if ":" not in target:
        raise ValueError(
            f"invalid target `{target}` — expected {TARGET_SYNTAX}. "
            f"`--deep` needs a MOUNTED application, not paths: the "
            f"questions it asks (\"is this routable covered?\") have no "
            f"answer in an isolated file."
        )
    module_name, _, attribute = target.partition(":")
    module = importlib.import_module(module_name)
    origin = Path(getattr(module, "__file__", "") or f"<{module_name}>")
    try:
        return getattr(module, attribute), origin
    except AttributeError:
        exported = [n for n in vars(module) if not n.startswith("_")]
        raise ValueError(
            f"`{module_name}` does not expose `{attribute}`. Available: {sorted(exported)[:10]}."
        ) from None


def run_deep(target: str) -> Report:
    """The map lints on the app designated by ``module:attribute``."""
    app, origin = load_app(target)
    return lint_app(app, origin=origin, label=target)


def lint_app(app: object, *, origin: Path, label: str = "l'app") -> Report:
    """The core, separated from the import.

    Separated on purpose: a gate must be able to build an app in memory
    and check that both lints see it, without going through a module on
    disk nor touching ``sys.path``. A lint that can only be exercised
    through its entry point ends up untested.
    """
    from bretzel.server.feature import dependency_drift, undeclared_provides

    features = getattr(app, "features", ())
    if not features:
        raise ValueError(
            f"`{label}` exposes no `Feature` — either it is not a Bretzel "
            f"application, or it does not use Features. The two map lints "
            f"then have nothing to arbitrate, and an app with no contract "
            f"has no business being lectured."
        )

    report = Report(rules_run=(RULE_UNDECLARED, RULE_DRIFT), files_scanned=1)
    module_path = origin

    for name, route in undeclared_provides(features, getattr(app, "routables", ())):
        report.findings.append(
            Finding(
                rule=RULE_UNDECLARED,
                path=module_path,
                line=0,
                message=(
                    f"`{name}` ({route or 'no route'}) is mounted but "
                    f"declared by no Feature — it runs, and the map does not "
                    f"see it. The skeleton lies by omission."
                ),
                hint="Add it to a Feature's `provides`.",
            )
        )

    for drift in dependency_drift(features):
        if drift.missing:
            report.findings.append(
                Finding(
                    rule=RULE_DRIFT,
                    path=module_path,
                    line=0,
                    message=(
                        f"la feature `{drift.feature}` importe "
                        f"{list(drift.missing)} without declaring them."
                    ),
                    hint="Add them to its `uses` / `reads`.",
                )
            )
        if drift.stale:
            report.findings.append(
                Finding(
                    rule=RULE_DRIFT,
                    path=module_path,
                    line=0,
                    message=(
                        f"the feature `{drift.feature}` declares "
                        f"{list(drift.stale)} but never imports them."
                    ),
                    hint="Remove them from its contract — a stale contract lies.",
                )
            )

    report.findings.sort(key=lambda f: (f.rule, f.message))
    return report

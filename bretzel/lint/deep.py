"""L'étage profond — celui qui IMPORTE l'application.

Les règles statiques lisent des fichiers ; celles-ci lisent une app
**montée**. C'est ce qui leur permet de répondre à des questions qu'aucun
AST ne peut trancher : « ce routable est-il couvert par une Feature ? »,
« ce contrat correspond-il aux imports réels ? ». En échange, elles
exécutent le code de l'utilisateur — d'où le drapeau séparé, et d'où le
fait que ce ne sera jamais le défaut.

**Le contrat d'entrée** est celui de tous les runners ASGI
(``uvicorn mon_app.main:app``) : ``module:attribut``. Le réutiliser plutôt
que d'inventer une syntaxe évite d'avoir à l'apprendre, et il est déjà
dans les doigts de qui lance le serveur.

Les deux lints existent depuis le 2026-07-05 dans :mod:`bretzel.server` et
tournaient **uniquement au startup**, en WARN sur stdout. Rien ne
permettait de les lancer à froid, ni d'en faire un code de sortie. C'est
tout ce que ce module ajoute : un point d'entrée et une traduction en
:class:`~bretzel.lint.report.Finding`.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from bretzel.lint.report import Finding, Report

RULE_UNDECLARED = "routable-non-declare"
RULE_DRIFT = "contrat-derive"

#: Ce qu'on accepte comme cible. Aligné sur les runners ASGI.
TARGET_SYNTAX = "module:attribut  (ex. `examples.mad.main:app`)"


def load_app(target: str) -> tuple[object, Path]:
    """Importe ``module:attribut`` et rend l'objet.

    Rend ``(objet, fichier du module)`` — le fichier sert à ancrer les
    constats sur quelque chose d'ouvrable. Un constat de carte n'a pas de
    ligne (il porte sur un contrat, pas sur une expression), mais il a au
    moins un fichier, et « ``<app>`` » n'ouvre rien.

    N'appelle rien : les ``include()`` d'une app Bretzel s'exécutent à
    l'import du module, donc les ``Feature`` et les routables sont déjà
    collectés quand l'objet existe. On ne démarre PAS le serveur — le
    lifespan ferait bien plus que lire.
    """
    if ":" not in target:
        raise ValueError(
            f"cible `{target}` invalide — attendu {TARGET_SYNTAX}. "
            f"`--deep` a besoin d'une application MONTÉE, pas de chemins : "
            f"les questions qu'il pose (« ce routable est-il couvert ? ») "
            f"n'ont pas de réponse dans un fichier isolé."
        )
    module_name, _, attribute = target.partition(":")
    module = importlib.import_module(module_name)
    origin = Path(getattr(module, "__file__", "") or f"<{module_name}>")
    try:
        return getattr(module, attribute), origin
    except AttributeError:
        exported = [n for n in vars(module) if not n.startswith("_")]
        raise ValueError(
            f"`{module_name}` n'expose pas `{attribute}`. Disponibles : {sorted(exported)[:10]}."
        ) from None


def run_deep(target: str) -> Report:
    """Les lints de carte sur l'app désignée par ``module:attribut``."""
    app, origin = load_app(target)
    return lint_app(app, origin=origin, label=target)


def lint_app(app: object, *, origin: Path, label: str = "l'app") -> Report:
    """Le cœur, séparé de l'import.

    Séparé exprès : une gate doit pouvoir fabriquer une app en mémoire et
    vérifier que les deux lints la voient, sans passer par un module sur
    disque ni toucher à ``sys.path``. Un lint qu'on ne peut exercer que
    par son point d'entrée finit non testé.
    """
    from bretzel.server.feature import dependency_drift, undeclared_provides

    features = getattr(app, "features", ())
    if not features:
        raise ValueError(
            f"`{label}` n'expose aucune `Feature` — soit ce n'est pas une "
            f"application Bretzel, soit elle n'utilise pas les Features. "
            f"Les deux lints de carte n'ont alors rien à arbitrer, et une "
            f"app sans contrat n'a pas à se faire sermonner."
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
                    f"`{name}` ({route or 'sans route'}) est monté mais "
                    f"déclaré par aucune Feature — il tourne, et la carte ne "
                    f"le voit pas. Le squelette ment par omission."
                ),
                hint="Ajoute-le aux `provides` d'une Feature.",
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
                        f"{list(drift.missing)} sans le déclarer."
                    ),
                    hint="Ajoute-les à ses `uses` / `reads`.",
                )
            )
        if drift.stale:
            report.findings.append(
                Finding(
                    rule=RULE_DRIFT,
                    path=module_path,
                    line=0,
                    message=(
                        f"la feature `{drift.feature}` déclare "
                        f"{list(drift.stale)} mais ne l'importe jamais."
                    ),
                    hint="Retire-les de son contrat — un contrat périmé ment.",
                )
            )

    report.findings.sort(key=lambda f: (f.rule, f.message))
    return report

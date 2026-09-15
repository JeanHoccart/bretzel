"""Règle : une app ne pilote pas le transport à la main.

Le charter (CLAUDE.md, principe 2) tient la frontière transport en
runtime-only. Une app déclare un handler ``on_<event>=`` et le socle émet
le POST **signé** (HMAC + horodatage + snapshot d'état client) via
``action_attrs``. Écrire un ``hx-post`` à la main produit une requête qui
n'a rien de tout ça : elle sera refusée, ou pire, elle contournera une
protection qu'on croyait acquise.

Deux formes, parce que les deux atteignent le DOM :

- le kwarg ``hx_post=…`` — le socle a un passthrough déclaré pour ``hx-``,
  donc il part verbatim et **ne lève pas** ;
- la clé ``attrs={"hx-post": …}`` — même chemin, autre orthographe.

Quelques composants du framework pilotent le swap engine directement, et
c'est assumé : la liste est gelée dans
``tests/consistency/test_raw_htmx_stays_in_the_allowlist.py``, avec la
règle du charter — « un nouveau composant qui en aurait besoin doit
d'abord pousser l'usage dans un helper runtime ». **Cette permission est
celle du framework, pas celle des apps** : une app n'a aucun helper à
écrire, elle a un handler à déclarer.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "transport-a-la-main"

_HINT = (
    "Déclare `on_<event>=mon_handler` : le socle pose le `hx-post` avec sa "
    "signature HMAC. Un POST écrit à la main n'en a pas."
)


def _hx_name(raw: str) -> str | None:
    """``hx_post`` / ``hx-post`` → ``hx-post``. Sinon ``None``."""
    normalised = raw.replace("_", "-")
    return normalised if normalised.startswith("hx-") else None


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg and (attr := _hx_name(keyword.arg)):
                findings.append(_finding(module, keyword.value.lineno, attr))
            if keyword.arg == "attrs" and isinstance(keyword.value, ast.Dict):
                for key in keyword.value.keys:
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and (attr := _hx_name(key.value))
                    ):
                        findings.append(_finding(module, key.lineno, attr))
    return findings


def _finding(module: Module, line: int, attr: str) -> Finding:
    return Finding(
        rule=RULE,
        path=module.path,
        line=line,
        message=(
            f"`{attr}` écrit à la main : la requête partira SANS la signature "
            f"HMAC ni les en-têtes de protocole que le socle ajoute."
        ),
        hint=_HINT,
    )

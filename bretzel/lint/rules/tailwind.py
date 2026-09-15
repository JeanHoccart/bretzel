"""Règle : une classe Tailwind **assemblée** n'existe qu'en dev.

Le mode d'échec le plus vicieux du dépôt, et le seul qui produise un HTML
**identique** des deux côtés. Le compilateur Tailwind de prod scanne les
*sources* : une classe qui n'apparaît nulle part en toutes lettres n'est
jamais générée. En dev, le compilateur navigateur scanne le *DOM*, où la
classe est déjà résolue — donc tout marche.

``classes=f"bg-{color}-500"`` produit un ``class="bg-tomato-500"`` correct
dans les deux cas. En dev il est stylé. En prod la règle CSS n'existe pas,
et rien — ni le HTML, ni la console, ni un test de rendu — ne le dit.

⚠️ **La règle ne PROUVE pas une rupture, elle signale une dépendance
invisible.** Ses six occurrences d'``examples/``, mesurées le 2026-08-16,
produisaient des classes (``bg-primary/15``, ``font-medium``…) qui
existaient par ailleurs dans les sources — donc bien générées, par
coïncidence. La coïncidence était la clôture couleur de la safelist ; la
phase 5 du chantier des jetons l'a déposée, et elles ont cessé d'exister.
C'est ce que la règle rend visible : le call-site ne suffit plus à savoir
si le style existera. Les six sont réécrites, ``examples/`` en compte
**zéro** depuis le 2026-09-05 (gelé par
``test_lint_baseline_on_examples``).

**Le critère est précis, pour ne pas hurler à tort.** On ne signale que
lorsqu'un morceau littéral **complète** une classe, c'est-à-dire quand il
précède une interpolation sans espace :

- ``f"bg-{c}-500"`` → littéral ``"bg-"``, pas d'espace final → **signalé** ;
- ``f"p-4 {extra}"`` → le littéral finit par un espace, ``extra`` apporte
  ses propres classes entières → ignoré ;
- ``f"{base} p-4"`` → rien ne précède l'interpolation → ignoré.

Le framework, lui, a le droit d'écrire des gabarits (``ring-{c}/40``) :
ils passent par ``resolve_slot`` et sont récoltés dans la safelist par
``dynamic_color_shapes``. **Une app n'a pas ce pont** — d'où une règle
plus stricte ici que la gate ``test_safelist_covers_theme_shapes``.
"""

from __future__ import annotations

import ast

from bretzel.lint.corpus import Module
from bretzel.lint.report import Finding

RULE = "classe-tailwind-assemblee"

#: Les kwargs dont la valeur atterrit dans un attribut ``class``.
_CLASS_KWARGS = frozenset({"classes", "class_"})


#: Les préfixes de classe que Bretzel GÉNÈRE lui-même, et qu'on a donc le
#: droit d'assembler.
#:
#: ``bz-c-<couleur>`` est une classe-PONT : sa règle est écrite par
#: ``theme/bridges.py``, pas compilée depuis les sources. Le compilateur
#: Tailwind n'a rien à en faire, donc l'argument entier de cette règle —
#: « la classe finale n'apparaît en toutes lettres nulle part » — ne
#: s'applique pas.
#:
#: ⚠️ C'est même l'idiome RECOMMANDÉ depuis les paliers : le remède au
#: ``f"bg-{color}/10"`` que cette règle attrape est précisément
#: ``bg-(--bz-bg)`` plus ``f"bz-c-{color}"``. Sans cette exemption, la
#: règle refuserait sa propre solution — mesuré le 2026-08-30 sur la page
#: ``/theme-studio`` du playground.
_GENERATED_PREFIXES = ("bz-c-",)


def _completes_a_class(node: ast.JoinedStr) -> bool:
    """Un littéral colle-t-il à une interpolation, sans espace ?"""
    for literal, following in zip(node.values, node.values[1:], strict=False):
        if not (
            isinstance(literal, ast.Constant)
            and isinstance(literal.value, str)
            and isinstance(following, ast.FormattedValue)
        ):
            continue
        text = literal.value
        if not text or text.endswith((" ", "\t", "\n")):
            continue
        if text.rsplit(" ", 1)[-1].startswith(_GENERATED_PREFIXES):
            continue
        return True
    return False


def check(module: Module) -> list[Finding]:
    findings: list[Finding] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg not in _CLASS_KWARGS:
                continue
            if not isinstance(keyword.value, ast.JoinedStr):
                continue
            if not _completes_a_class(keyword.value):
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    path=module.path,
                    line=keyword.value.lineno,
                    message=(
                        f"`{keyword.arg}=` reçoit une f-string qui COMPLÈTE une "
                        f"classe : la classe finale n'apparaît en toutes lettres "
                        f"nulle part ici. Elle ne sera stylée en prod que si une "
                        f"AUTRE source la contient par hasard — et si ce n'est "
                        f"pas le cas, rien ne le dira : le HTML est identique en "
                        f"dev, où le compilateur scanne le DOM déjà résolu."
                    ),
                    hint=(
                        "Écris les classes entières et choisis-en une "
                        "(`'bg-red-500' if danger else 'bg-green-500'`), ou "
                        "mets le scalaire en safelist."
                    ),
                )
            )
    return findings

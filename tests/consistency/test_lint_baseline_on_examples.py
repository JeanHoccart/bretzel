"""Gate : la population que `bretzel.lint` voit dans `examples/` est FIGÉE.

`test_examples_pass_real_kwargs` exige **zéro** constat pour la règle des
kwargs inconnus, parce qu'un kwarg mort n'a jamais de bonne raison
d'exister. Les quatre autres règles ne peuvent pas demander ça : elles
signalent des **formes légitimes mais coûteuses**, pas des fautes. Le
playground démontre `ui.html` — six appels non littéraux y sont le sujet
de la page, pas un oubli.

D'où la même forme que `test_ui_html_call_sites_are_listed` et
`test_raw_htmx_stays_in_the_allowlist` : **on gèle le couple (fichier,
règle) → nombre**. Ajouter une occurrence rougit, ce qui force la question
à être posée plutôt que subie. En retirer une rougit aussi, sinon la liste
pourrit et finit par autoriser plus que la réalité — le défaut même
qu'elle corrige.

Ce que la baseline dit, entrée par entrée, est dans `_BASELINE`. Une
entrée sans raison serait juste une gate qu'on a fait taire.
"""

from __future__ import annotations

import collections
import pathlib

from bretzel.lint import run
from bretzel.lint.rules import STATIC

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "gèle un COUPLE (fichier, règle) → nombre mesuré par `bretzel.lint` "
    "; le détecteur est celui des règles, gardé par "
    "`test_lint_rules_are_not_vacuous`"
)

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_EXAMPLES = _ROOT / "examples"

#: ``(chemin, règle) → nombre``, mesuré le 2026-08-16. Chaque entrée porte
#: sa raison — c'est ce qui distingue une baseline d'un silence.
_BASELINE: dict[tuple[str, str], int] = {
    # Le banc `ui.html` : les six appels non littéraux SONT le sujet de la
    # page (contenu piloté par l'état, pour démontrer la primitive).
    ("examples/playground/features/html.py", "non-literal-html"): 6,
    # ⚠️ **`assembled-tailwind-class` n'a plus AUCUNE entrée** — la
    # dernière est sortie le 2026-09-05. Cinq y figuraient : carousel (1)
    # et todo/stats (2), sorties le 2026-08-30, puis resizable (2) et la
    # carte d'app (1). Toutes disaient « la classe produite
    # (`bg-primary/15`, `font-bold`…) existe par ailleurs dans les
    # sources, générée par coïncidence ». La coïncidence était la clôture
    # couleur de la safelist ; la phase 5 du chantier des jetons l'a
    # déposée, et ces classes ont cessé d'exister en prod. Les teintes de
    # `resizable` sont passées en palier + pont (`bg-(--bz-bg)` +
    # `bz-c-<teinte>`, comme son jumeau `carousel`), le poids de la carte
    # d'app en classes entières (`_WEIGHT_CLASS`).
    #
    # Une occurrence neuve doit donc être CORRIGÉE, pas inscrite : aucune
    # forme légitime n'a été trouvée sur les 364 fichiers d'`examples/`.
    # `hx-include` sur le banc combobox : pilotage direct du swap engine,
    # la famille que `test_raw_htmx_stays_in_the_allowlist` gèle côté
    # framework. Ici c'est un banc qui démontre ce pilotage.
    ("examples/playground/features/combobox.py", "hand-written-transport"): 1,
    # Deux bancs comparent DÉLIBÉRÉMENT deux tailles côte à côte : la
    # cellule de droite est étiquetée « cellule étroite », et montrer
    # qu'un picker s'y adapte EST le sujet de la démonstration. C'est la
    # seule forme légitime de mélange trouvée sur les 180 groupes de
    # contrôles frères d'`examples/`.
    ("examples/playground/features/month_picker.py", "mixed-sizes"): 1,
    ("examples/playground/features/week_picker.py", "mixed-sizes"): 1,
}


def _measured() -> dict[tuple[str, str], int]:
    report = run([_EXAMPLES])
    assert report.files_scanned > 0, f"aucun fichier balayé sous {_EXAMPLES}"
    return dict(
        collections.Counter(
            (f.path.resolve().relative_to(_ROOT).as_posix(), f.rule) for f in report.findings
        )
    )


def test_every_rule_is_represented_or_silent() -> None:
    """Plancher : on connaît les règles que la baseline couvre.

    Une règle absente de la baseline doit être absente parce qu'elle ne
    trouve rien, pas parce qu'elle a cessé de tourner. Ce test ne peut pas
    le prouver seul — il fixe le décor : la liste des règles est
    énumérable, donc une règle disparue se voit.
    """
    known = set(STATIC)
    baselined = {rule for _, rule in _BASELINE}
    assert baselined <= known, (
        f"la baseline cite des règles inconnues : {sorted(baselined - known)}. "
        f"Une règle renommée ou supprimée laisse une entrée morte, qui "
        f"autorise silencieusement une population qu'on ne mesure plus."
    )


def test_the_population_has_not_moved() -> None:
    measured = _measured()
    added = {k: n for k, n in measured.items() if _BASELINE.get(k, 0) != n}
    removed = {k: n for k, n in _BASELINE.items() if measured.get(k, 0) != n}
    if not added and not removed:
        return

    def _fmt(entries: dict[tuple[str, str], int]) -> str:
        return "\n".join(
            f"      {path}  [{rule}] ×{n}" for (path, rule), n in sorted(entries.items())
        )

    raise AssertionError(
        "la population vue par `bretzel.lint` sous `examples/` a bougé.\n"
        f"  mesuré, absent ou différent de la baseline :\n{_fmt(added)}\n"
        f"  attendu par la baseline, plus mesuré ainsi :\n{_fmt(removed)}\n\n"
        "  Si c'est une occurrence NEUVE : lis le constat, corrige-le, ou "
        "inscris-le ici AVEC sa raison.\n"
        "  Si tu en as retiré une : retire aussi son entrée, sinon la "
        "baseline autorise plus que la réalité."
    )

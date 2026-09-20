"""Gate : `check --deep` voit une carte qui ment, et se tait quand elle est juste.

Les deux lints de carte existent depuis le 2026-07-05 mais tournaient
**uniquement au startup**, en WARN sur stdout : rien ne permettait de les
lancer à froid, ni d'en faire un code de sortie. `run_deep` ajoute ce
point d'entrée — et un point d'entrée sans gate serait exactement le
genre d'outil qui pourrit sans bruit (31 benchs sur 40 sont morts comme
ça dans ce dépôt).

**Le piège propre à cette gate** : `examples/mad` et `examples/flat` sont
gardés PROPRES par `test_dependency_drift_clean_on_real_examples`. Vérifier
`--deep` sur eux ne prouve donc rien — un lint débranché passerait à
l'identique. Il faut une carte qui ment **exprès**, construite ici.

On exerce `lint_app` et non `run_deep` : le cœur est séparé de l'import
justement pour qu'une gate puisse fabriquer une app en mémoire, sans
module sur disque ni `sys.path` bricolé.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bretzel import Bretzel, Feature, page, ui
from bretzel.lint import lint_app
from bretzel.lint.deep import RULE_DRIFT, RULE_UNDECLARED

#: Preuve de morsure : une carte d'app FABRIQUÉE avec un routable orphelin doit produire un
#: constat ; `test_a_clean_map_produces_nothing` garde l'autre sens.
MUTATION_PROOF = "test_an_undeclared_routable_is_seen"

_ORIGIN = Path(__file__)


@page("/gate-declared", title="Déclarée")
def _declared_page() -> None:  # pragma: no cover — jamais rendue
    ui.text("déclarée")


@page("/gate-orphan", title="Orpheline")
def _orphan_page() -> None:  # pragma: no cover — jamais rendue
    ui.text("montée, déclarée par personne")


def _app(*, with_orphan: bool, stale: tuple[str, ...] = ()) -> Bretzel:
    app = Bretzel(title="Gate", secret_key="gate-secret-change-me", debug=True)
    app._features.append(
        Feature(
            name="gate_home",
            kind="page",
            provides=[_declared_page],
            reads=list(stale),
        )
    )
    app._pages.append(_declared_page)
    if with_orphan:
        app._pages.append(_orphan_page)
    return app


def test_a_clean_map_produces_nothing() -> None:
    """Sens 1 — pas de faux positif sur une carte honnête."""
    report = lint_app(_app(with_orphan=False), origin=_ORIGIN)
    assert report.exit_code == 0, (
        f"une carte sans dérive produit {len(report.findings)} constat(s) :\n{report.format()}"
    )


def test_an_undeclared_routable_is_seen() -> None:
    """Sens 2a — un routable monté hors de toute Feature."""
    findings = lint_app(_app(with_orphan=True), origin=_ORIGIN).findings
    assert [f for f in findings if f.rule == RULE_UNDECLARED], (
        "une page montée et déclarée par aucune Feature passe inaperçue — "
        "elle tourne, et la carte ment par omission."
    )


def test_a_stale_contract_is_seen() -> None:
    """Sens 2b — un contrat qui déclare ce qu'il n'importe jamais."""
    app = _app(with_orphan=False, stale=("FantomeQuiNExistePas",))
    findings = lint_app(app, origin=_ORIGIN).findings
    assert [f for f in findings if f.rule == RULE_DRIFT], (
        "une feature déclare un `reads` qu'elle n'importe jamais et le lint "
        "ne le dit pas — le contrat peut mentir sans conséquence, ce qui est "
        "précisément ce que ces deux lints existent pour empêcher."
    )


def test_an_app_without_features_is_refused_not_silently_green() -> None:
    """Le cas vide ne doit PAS ressembler à un succès.

    Une app sans `Feature` n'a rien à arbitrer — mais rendre « OK, aucun
    constat » lui donnerait l'apparence d'avoir été vérifiée. On refuse,
    en disant pourquoi.
    """
    bare = Bretzel(title="Nue", secret_key="gate-secret-change-me")
    with pytest.raises(ValueError, match="exposes no `Feature`"):
        lint_app(bare, origin=_ORIGIN)


def test_the_findings_point_at_an_openable_file() -> None:
    """Un constat de carte n'a pas de ligne — il a au moins un fichier.

    La première version rendait ``<app>:0``, qui n'ouvre rien. Un outil
    dont on ne peut pas suivre la sortie se lit une fois puis s'ignore.
    """
    findings = lint_app(_app(with_orphan=True), origin=_ORIGIN).findings
    assert findings, "le cas fabriqué ne produit aucun constat"
    for finding in findings:
        assert finding.path.exists(), (
            f"`{finding.path}` n'est pas un fichier ouvrable — le constat pointe dans le vide."
        )

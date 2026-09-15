"""Permanent visual audit — every component must stay green.

Single-source-of-truth gate : ``tests/audit/checklist.py`` declares
every shipped component ; this test runs the audit driver against the
whole catalogue and asserts 100 % pass.

When a new component lands :
    1. Add a ``ComponentSpec`` entry in ``tests/audit/checklist.py``.
    2. ``py -m tests.audit.driver <name>`` should report PASS.
    3. This test then catches any regression on subsequent edits.

This test is heavier than ``tests/unit/`` (spins uvicorn + Chromium)
so it lives under ``tests/runtime_js/`` and is the place to run before
shipping a component, not on every save.

**Coût : 9 minutes**, mesuré deux fois le 2026-08-31 (8 min 59 et
9 min 01, 75 cas, second run entièrement vert).

⚠️ **Il coûtait 52 minutes jusqu'à ce jour-là**, et ce n'était pas le
prix du navigateur. Mesuré probe par probe :
``probe_server_props_drive_dom`` faisait **88 à 92 % du total** — 46 s
sur 52 pour ``button``, 30 s sur 33 pour ``badge`` — pendant que les
sept autres probes tenaient ensemble en moins de 3 s. La cause était un
``setTimeout(1500)`` INCONDITIONNEL dans ``_flip_control`` après chaque
manipulation de contrôle : à ~2 000 manipulations sur le catalogue, la
suite passait cinquante minutes à ne rien faire.

Remplacé par une attente sur l'ÉTAT (cf. ``interaction.py``), et le
gain est deux fois : ``-n 4`` devient tenable par-dessus.

**Ce que l'heure de trop coûtait vraiment.** Une suite qui demande une
heure ne se lance pas, donc elle ne dit rien. Le 2026-08-30, la
migration des rayons a renommé ``rounded-md`` et ``rounded-xl`` ; les
sélecteurs d'ancrage de ``badge`` et ``card`` dans ``checklist.py`` ont
cessé de désigner quoi que ce soit le jour même, et il a fallu vingt-
quatre heures pour l'apprendre. Gardé depuis par
``tests/consistency/test_an_audit_selector_still_matches_something.py``,
qui est dans le run rapide.

    py -m pytest -m audit -n 4 -q                  # tout l'audit, 9 min
    py -m pytest -m audit -q -k button             # un composant
    py -m tests.audit.driver <nom>                 # hors pytest
"""

from __future__ import annotations

import pytest

from tests.audit.checklist import COMPONENT_SPECS, ComponentSpec
from tests.audit.driver import run_audit
from tests.audit.harness import audit_server

#: Marqueur propre — lu par ``conftest.py``, qui n'ajoute alors PAS
#: ``browser``. Les deux marqueurs restent disjoints.
pytestmark = pytest.mark.audit


# Single-session uvicorn — spinning one per component would explode
# wall clock + port pressure. ``module``-scoped fixture so a single
# server hosts every audit in this file.
@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def _all_specs():
    out: list[ComponentSpec] = []
    for specs in COMPONENT_SPECS.values():
        out.extend(specs)
    return out


@pytest.mark.parametrize(
    "spec", _all_specs(), ids=lambda s: f"{s.name}_audit",
)
def test_component_audit_clean(spec: ComponentSpec, base_url: str) -> None:
    """Every shipped component passes its applicable audit probes.

    The probes that apply depend on the ``ComponentSpec`` flags
    (``has_color_axis`` / ``has_size_axis`` / ``color_at_rest`` /
    ``is_interactive``). When a probe FAILS, the failure detail
    references the trap from ``traps.md`` so the diff to fix is
    obvious.
    """
    report = run_audit(spec, base_url)
    if report.error:
        pytest.fail(f"{spec.name} audit threw : {report.error}")
    if report.failed:
        lines = [f"{spec.name} audit found {len(report.failed)} issue(s) :"]
        for f in report.failed:
            lines.append(f"  - {f['name']} : {f['detail'][:250]}")
        pytest.fail("\n".join(lines))

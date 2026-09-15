"""Gate : the ``_serverSync`` scope marker is single-sourced.

``_serverSync`` lists the ``bz-data`` scope keys a ``@refreshable`` morph
must re-adopt from the freshly-rendered attr (server wins), vs the
client-owned keys ``absorb`` preserves. Its literal used to be hardcoded
in ~11 component emit sites AND the JS scope reader (``03_scope.js``) —
a rename on one side silently stops that control re-adopting its server
value on refresh (traps.md § "Input lié-serveur ne reflète PAS…").

Now single-sourced in ``protocol.SERVERSYNC_KEY``, mirrored into
``runtime.js`` by ``test_python_js_mirror`` (so a Python↔JS rename fails
at commit), and emitted via ``base/_wiring.server_sync_marker`` or by
interpolating the constant. This gate catches the remaining drift vector :
a component re-hardcoding the literal in a rendered string instead of
using the constant. It flags string LITERALS only (AST) — mentions in
comments and docstrings are fine.
"""

from __future__ import annotations

import ast
from pathlib import Path

from bretzel.runtime import SERVERSYNC_KEY
from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    code_string_literals,
    component_sources,
)

_COMPONENTS = Path(__file__).resolve().parents[2] / "bretzel" / "components"


def _literal_marker_lines(py: Path) -> list[int]:
    """Line numbers where ``_serverSync`` appears in a real string literal.

    Excludes comments (invisible to the AST) and bare string statements
    — docstrings included. Le filtre vit dans ``_discovery`` depuis
    qu'une seconde gate en a eu besoin ; il était recopié ici.

    Le fichier est relu à la main plutôt que pris dans le balayage
    mémoïsé : ``test_the_detector_still_bites`` nourrit cette fonction
    d'une source FABRIQUÉE, écrite hors du dépôt.
    """
    return [
        node.lineno
        for node in code_string_literals(ast.parse(py.read_text(encoding="utf-8")))
        if SERVERSYNC_KEY in node.value
    ]


def test_the_sweep_visits_the_components() -> None:
    """Plancher de non-vacuité — le test ci-dessous est une interdiction."""
    assert_sweep_is_not_vacuous()


def test_no_component_hardcodes_serversync_literal() -> None:
    offenders = {}
    for py in component_sources():
        lines = _literal_marker_lines(py)
        if lines:
            offenders[str(py.relative_to(_COMPONENTS.parent.parent))] = lines
    assert not offenders, (
        f"These component modules hardcode the '{SERVERSYNC_KEY}' literal in "
        f"a rendered string — emit it via base/_wiring.server_sync_marker or "
        f"interpolate SERVERSYNC_KEY, so a protocol rename can't strand one "
        f"control's server re-adoption: {offenders}"
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un ``_serverSync`` en littéral est reconnu, pas en prose.

    La gate interdit de retaper la clé à la main. Le détecteur doit donc
    distinguer une CHAÎNE de code d'une mention en docstring ou en
    commentaire — sinon il accuserait la documentation qui explique le
    mécanisme.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.py"
        probe.write_text(
            '"""Docstring qui parle de _serverSync."""\n'
            "# commentaire _serverSync\n"
            'MARK = "_serverSync"\n',
            encoding="utf-8",
        )
        lines = _literal_marker_lines(probe)
    assert lines == [3], (
        f"seul le littéral de la ligne 3 devrait être vu, trouvé {lines} — "
        f"docstring et commentaire ne sont pas du code"
    )

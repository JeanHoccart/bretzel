"""Le scope ``current_path`` est déclaré à UN seul endroit.

Trois navs partagent un signal : ``current_path``, que chacune expose dans son
propre ``bz-data``. La redondance des SCOPES est voulue (une navbar doit
marcher sur une page sans sidebar) ; celle du LITTÉRAL ne l'était pas.

La clé est porteuse, et c'est ce qui rend la copie coûteuse :
``apply_partial_nav`` écrit ``current_path = "…"`` en **identifiant nu** (il
résout dans le scope du parent), et ``current_path_resync_init`` compare
``current_path !== p``. Renommer la clé dans une seule des copies tuait donc
le surlignage de CETTE nav-là, en silence, sans erreur JS.

Mesuré le 2026-08-09 : quatre copies, dont deux en concaténation de chaînes
côté sidebar — pendant que l'autre moitié du mécanisme (le resync) était,
elle, partagée depuis toujours dans ``_wiring.py``. Même classe que la memory
``project_scope_literal_debt`` (le même littéral recopié 5× sur
Tabs/Pagination/Accordion/Stepper/Carousel).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.consistency._discovery import (
    PACKAGE_FLOOR,
    parsed_sources,
    source_of,
)

#: Preuve de morsure : contrôle POSITIF — la regex trouve encore les appelants réels du
#: helper.
MUTATION_PROOF = "test_the_gate_finds_scope_consumers"

_BRETZEL = Path(__file__).resolve().parents[2] / "bretzel"
_AUTHOR = _BRETZEL / "components" / "navigation" / "_wiring.py"

_LITERAL = "current_path: window.location.pathname"
_CALL = re.compile(r"\bcurrent_path_scope\s*\(")


def _sources() -> list[Path]:
    return [s.path for s in parsed_sources(_BRETZEL, floor=PACKAGE_FLOOR)]


def test_the_gate_finds_scope_consumers() -> None:
    """Plancher de non-vacuité. L'assertion ci-dessous est une INTERDICTION —
    « personne d'autre n'écrit ce littéral ». Elle passerait tout aussi bien
    si le helper était mort et le mécanisme parti ailleurs : le ``rglob`` ne
    signale pas sa propre panne. On vérifie donc que le helper est bien
    APPELÉ par plusieurs composants."""
    callers = {
        p.parent.name for p in _sources()
        if p != _AUTHOR and _CALL.search(source_of(p).text)
    }
    assert len(callers) >= 3, (
        f"seulement {sorted(callers)} appellent `current_path_scope()`. Les "
        f"trois navs (navbar / sidebar / bottom_bar) devraient l'utiliser — "
        f"soit le mécanisme a bougé, soit la découverte est cassée, et "
        f"l'interdiction ci-dessous ne protège plus rien."
    )


def test_only_the_helper_writes_the_scope_literal() -> None:
    authors = [
        p.relative_to(_BRETZEL).as_posix()
        for p in _sources()
        if _LITERAL in p.read_text(encoding="utf-8")
    ]
    expected = [_AUTHOR.relative_to(_BRETZEL).as_posix()]
    assert authors == expected, (
        f"le littéral `{_LITERAL}` est écrit dans {authors}, or il ne doit "
        f"l'être que dans {expected}.\n"
        f"  La clé est lue en identifiant NU par `apply_partial_nav` "
        f"(`current_path = \"…\"`) et par le resync — la renommer dans une "
        f"seule copie tue le surlignage de cette nav sans une erreur.\n"
        f"  Utilise `current_path_scope(extra=…)` : `extra` reçoit les "
        f"champs propres au composant, comme le fait la sidebar avec son "
        f"`open` et son tooltip de rail."
    )

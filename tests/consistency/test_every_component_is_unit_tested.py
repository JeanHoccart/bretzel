"""Gate — tout composant public est exercé par au moins un test unitaire.

**Pourquoi ça a manqué.** La famille drag-and-drop a shippé le 2026-08-10
avec trois suites ``tests/runtime_js/`` et **zéro** test unitaire. Or les
suites navigateur ne tournent pas dans le sous-ensemble rapide — celui que
`CLAUDE.md` et `creating-a-component.md` désignent comme la *definition of
done*. Pendant trois jours, `pytest tests/unit tests/integration
tests/consistency` a donc validé un composant dont il ne rendait jamais la
surface Python. Trouvé à l'audit du 2026-08-13, pas par un test.

Le trou était invisible à l'œil pour une raison précise : `dropzone`
APPARAÎT dans ``tests/unit`` — comme valeur du ``variant=`` de
``file_upload``. Un grep sur le nom disait « couvert ». C'est pourquoi la
gate cherche une **construction** (``ui.x(``) ou le **nom de classe**
(``Dropzone``), jamais le nom nu.

**Ce que la gate ne prétend pas.** Elle ne mesure aucune qualité de test :
un composant nommé une fois passe. C'est un plancher de PRÉSENCE, le seul
niveau où un contrôle mécanique est honnête. Il suffit à attraper le cas
réel — « personne n'a écrit de fichier du tout ».
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import pytest

from tests.consistency._discovery import parsed_sources, public_component_classes

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "cherche le NOM de chaque composant dans le corpus des tests "
    "unitaires ; `test_the_sweep_reads_something` garde le corpus, et "
    "un nom de classe n'a pas d'orthographe alternative à rater"
)

_UNIT = Path(__file__).resolve().parents[1] / "unit"

#: 154 fichiers sous tests/unit le 2026-08-19.
_UNIT_FLOOR = 100

#: Mesuré le 2026-08-13 : 91 composants publics, 0 non couvert. Le
#: plancher garde la DÉCOUVERTE, pas la couverture — une gate qui
#: n'inspecte plus aucun composant affirme « zéro trou » avec la même
#: sérénité qu'une gate qui les a tous lus.
_MIN_COMPONENTS = 80


@functools.lru_cache(maxsize=1)
def _unit_sources() -> str:
    return "\n".join(
        s.text for s in parsed_sources(_UNIT, floor=_UNIT_FLOOR)
    )


@functools.lru_cache(maxsize=1)
def _unit_symbols() -> tuple[frozenset[str], frozenset[str]]:
    """``(identifiants, noms construits via ``ui.x(...)``)`` — UNE passe.

    La version d'origine relançait deux ``re.search`` sur le blob de
    1,2 Mio pour CHACUN des 91 tests paramétrés : **2,4 s mesurées**, soit
    un tiers du coût des trois gates neuves de cet audit. Un motif
    ``\\bNom\\b`` n'a pas de préfixe littéral, donc le moteur parcourt
    tout le corpus à chaque appel. L'index construit une fois rend le même
    verdict sur les 91 (vérifié, zéro divergence) pour 0,14 s.
    """
    blob = _unit_sources()
    return (
        frozenset(re.findall(r"[A-Za-z_]\w*", blob)),
        frozenset(re.findall(r"\bui\.(\w+)\s*\(", blob)),
    )


def _ui_name(cls: type) -> str:
    """``Dropzone`` → ``dropzone``. Le nom sous lequel ``ui`` l'expose."""
    from bretzel.components import _UI

    for name, value in vars(_UI).items():
        if value is cls:
            return name
    # Inatteignable par construction : `cls` VIENT de `vars(_UI)`. On lève
    # plutôt que de deviner — un `cls.__name__.lower()` rendrait
    # `bottombaritem` pour `BottomBarItem`, donc un `ui.bottombaritem(`
    # que personne n'écrit jamais, donc une gate affaiblie EN SILENCE.
    raise AssertionError(f"{cls.__name__} n'est pas exposé sur `ui`")


def _is_exercised(cls: type) -> bool:
    words, calls = _unit_symbols()
    # Le nom de CLASSE (CamelCase, sans ambiguïté possible avec une
    # valeur de kwarg) ou une construction explicite via le namespace.
    return cls.__name__ in words or _ui_name(cls) in calls


def test_the_sweep_reads_something() -> None:
    found = public_component_classes()
    assert len(found) >= _MIN_COMPONENTS, (
        f"seulement {len(found)} composants publics découverts (91 le "
        f"2026-08-13) — la découverte a cassé, la gate ne garde plus rien."
    )
    assert _unit_sources().strip(), (
        f"aucune source lue sous {_UNIT} — le chemin a bougé."
    )


@pytest.mark.parametrize(
    "cls", public_component_classes(), ids=lambda c: c.__name__
)
def test_component_is_exercised_by_a_unit_test(cls: type) -> None:
    assert _is_exercised(cls), (
        f"{cls.__name__} n'est jamais construit dans `tests/unit` — ni "
        f"par son nom de classe, ni par `ui.{_ui_name(cls)}(`.\n"
        f"  Les suites navigateur ne comptent pas : elles ne tournent pas "
        f"dans le sous-ensemble rapide, qui est la definition of done du "
        f"dépôt. C'est exactement comme ça que `dropzone` et `draggable` "
        f"ont vécu trois jours sans aucun test de leur rendu Python.\n"
        f"  Écris `tests/unit/components/<groupe>/test_<nom>.py` — "
        f"structure du render, attributs de contrat, refus attendus."
    )

"""Gate — chacun des dix `kind=` de `Feature` est exercé par une app.

Le framework VALIDE le kind d'une feature (`FEATURE_KINDS`, refus à la
construction) et la doc vivante l'ENSEIGNE (`examples/docs/features/
structure.py` lit la même constante). Personne ne vérifiait qu'un kind
soit encore *utilisé* quelque part.

**Ce que ça a coûté, et pourquoi cette gate existe.** Le 2026-09-10,
l'élagage des exemples est arrivé sur `examples/mad`. Mesuré à ce
moment-là : il était le SEUL à déclarer `facade`, `job` et `layout`, et
les deux premiers n'existaient nulle part ailleurs dans le dépôt, pas
même en fixture de test. Le supprimer aurait laissé trois kinds que le
framework propose, que la doc enseigne, et qu'aucune app n'exerce —
donc sur lesquels `check --deep` n'aurait plus rien eu à arbitrer. Rien
n'aurait rougi.

Les trois ont été repris dans `examples/crm` (`geo`, `nightly_hygiene`,
`analyse_nav`), et cette gate est ce qui empêche de les reperdre au
prochain élagage. C'est la règle 8 du charter : un invariant réparé sans
gate redérive, et celui-ci a failli disparaître dans le diff même qui
l'a nommé.

**À l'AST, pas au grep.** Les docstrings de ces features CITENT leur
propre kind (``Feature ``kind="job"``, en prose) — un lecteur textuel
compterait la mention comme une déclaration, et la gate resterait verte
sur une app qui n'a plus que sa documentation.
"""

from __future__ import annotations

import ast

import pytest

from bretzel.server import FEATURE_KINDS
from tests.consistency._discovery import (
    EXAMPLES_FLOOR,
    REPO_ROOT,
    ParsedSource,
    parsed_sources,
)

#: Preuve de morsure : contrôle POSITIF — la découverte trouve vraiment
#: des `Feature(...)`, donc un « tous couverts » n'est pas un verdict
#: rendu sur zéro déclaration.
MUTATION_PROOF = "test_the_sweep_finds_declarations"

_EXAMPLES = REPO_ROOT / "examples"

#: Plancher de déclarations. 33 mesurées le 2026-09-10 ; le seuil laisse
#: la place à un élagage sans laisser passer un balayage cassé.
_DECLARATION_FLOOR = 20


def _sources() -> list[ParsedSource]:
    return parsed_sources(_EXAMPLES, floor=EXAMPLES_FLOOR)


def _kind_of(call: ast.Call) -> str | None:
    """Le `kind=` d'un appel `Feature(...)`, s'il est littéral."""
    target = call.func
    name = getattr(target, "attr", None) or getattr(target, "id", None)
    if name != "Feature":
        return None
    for keyword in call.keywords:
        if keyword.arg == "kind" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            return value if isinstance(value, str) else None
    return None


def _declarations() -> dict[str, set[str]]:
    """``kind → {apps qui le déclarent}``."""
    found: dict[str, set[str]] = {}
    for source in _sources():
        try:
            app = source.path.relative_to(_EXAMPLES).parts[0]
        except ValueError:  # pragma: no cover — hors d'`examples/`
            continue
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Call) and (kind := _kind_of(node)):
                found.setdefault(kind, set()).add(app)
    return found


def test_the_sweep_finds_declarations() -> None:
    """Plancher — ancré sur la DÉCOUVERTE, pas sur la population."""
    total = sum(len(apps) for apps in _declarations().values())
    assert total >= _DECLARATION_FLOOR, (
        f"seulement {total} couples (kind, app) trouvés sous {_EXAMPLES} "
        f"(≥ {_DECLARATION_FLOOR} attendus, 33 mesurés le 2026-09-10) — le "
        f"balayage ne lit plus les `Feature(...)`, donc l'assertion "
        f"ci-dessous ne protège plus rien."
    )


@pytest.mark.parametrize("kind", sorted(FEATURE_KINDS))
def test_a_kind_the_framework_offers_is_exercised(kind: str) -> None:
    apps = _declarations().get(kind, set())
    assert apps, (
        f"aucune app d'`examples/` ne déclare `kind={kind!r}`.\n\n"
        f"Le framework le propose et `examples/docs` l'enseigne, donc un "
        f"lecteur va le chercher et ne trouvera rien à lire. Et "
        f"`bretzel check --deep` n'a plus de cas réel à arbitrer dessus.\n\n"
        f"Soit une app le reprend — c'est ce qu'a fait `examples/crm` le "
        f"2026-09-10 pour `facade`, `job` et `layout` quand `mad` est "
        f"parti — soit le kind sort de `FEATURE_KINDS`. Le laisser "
        f"orphelin est la seule option qui ment."
    )


def test_no_kind_is_declared_outside_the_framework_list() -> None:
    """Le versant licite — une app ne peut pas inventer un kind.

    Le refus vit déjà dans `Feature.__post_init__`, mais il ne se
    déclenche qu'à la CONSTRUCTION : une feature jamais incluse par un
    `main` ne lève jamais. Ici on lit le source, donc on la voit.
    """
    inconnus = sorted(set(_declarations()) - set(FEATURE_KINDS))
    assert not inconnus, (
        f"ces `kind=` ne sont pas dans `FEATURE_KINDS` : {inconnus}. "
        f"Valides : {', '.join(sorted(FEATURE_KINDS))}."
    )

"""Un composant qui DESSINE un contrôle directionnel expose la méthode.

Pagination rendait ses deux chevrons « page précédente / page suivante »
et n'offrait à personne le moyen de les déclencher : ``IMPERATIVE`` vide,
alors que Stepper et Carousel — même archétype, un index borné — déclarent
tous deux ``("set", "next", "prev")``.

Pourquoi les gates existantes ne pouvaient PAS l'attraper
----------------------------------------------------------
Les deux gardent ``IMPERATIVE`` dans les deux sens d'un ensemble… vide.

- ``test_imperative_classvar_is_complete`` parcourt l'AST des méthodes
  publiques qui appellent ``_dispatch_command`` et exige qu'elles soient
  déclarées. Pagination n'en définissait aucune : la boucle ne tournait
  pas, le fichier passait **à vide**.
- ``tests/unit/components/test_imperative_classvar.py`` construit sa
  population en ``[c for c in … if c.IMPERATIVE]`` — Pagination était
  écartée avant la première assertion.

Aucune ne demandait ce que l'archétype DOIT. Celle-ci le demande, en
partant de l'affordance rendue plutôt que d'une liste de noms : c'est le
seul fait observable qui distingue « ce composant a une notion de
direction » de « ce composant n'en a pas ».

Effet de bord qui rendait l'omission coûteuse : ``_needs_identity()`` est
DÉRIVÉ de ``IMPERATIVE`` (``component.py``). Sans la ClassVar, une
pagination sans binding ni handler ne rendait aucun ``id`` — donc même un
dispatch écrit à la main aurait échoué en silence.

⚠️ Portée assumée
------------------
La détection lit les libellés LITTÉRAUX du module. Deux angles morts
connus, tous deux inoffensifs aujourd'hui :

- DatePicker / DateRangePicker RENDENT « Previous month » / « Next month »
  hérités du Calendar qu'ils embarquent, sans exposer de méthode. C'est la
  même omission, mais l'affordance n'est pas écrite dans leur module :
  la traiter demande de concevoir leur surface impérative, ce qui est un
  ajout d'API, pas une réparation. Noté dans ``.claude/work/todo.md``.
"""

from __future__ import annotations

import inspect
import pathlib
import re

import pytest

from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    component_sources,
    public_component_classes,
)

#: Preuve de morsure : contrôle POSITIF — les trois composants directionnels connus sont
#: encore reconnus.
MUTATION_PROOF = "test_the_sweep_finds_the_known_directional_components"

# « Previous … » / « Next … » dans un libellé accessible — écrit en dur,
# OU sous forme de clé de texte (``text("pagination.previous")``) depuis
# que les mots du framework passent par une table. Ne chercher que le
# littéral rendait la gate aveugle à Pagination sans rien casser
# d'autre : c'est son plancher qui l'a dit, pas son interdiction.
_LABEL = re.compile(
    r"[\"'](?:(Previous|Next)\s+\w+|[\w.]*\.(previous|next)(?:_\w+)?)[\"']"
)
# Le libellé dit « Previous », la méthode s'appelle `prev` (ou
# `prev_month`) : on compare des DIRECTIONS, pas des noms. C'est ce qui
# permet à la règle de tenir sur toute la famille sans imposer un nom.
_PREFIX = {"previous": "prev", "next": "next"}

def _module_index() -> dict[pathlib.Path, list[type]]:
    """Le module source → les composants publics qu'il définit.

    ``inspect.getfile`` et NON ``Path(cls.__module__.replace(".", "/"))`` :
    le second produit un chemin RELATIF, que ``.resolve()`` ancre sur le
    répertoire COURANT. Lancé d'ailleurs que la racine du dépôt, il ne
    croisait plus les chemins absolus de ``component_sources()`` — les trois
    cas réels se skippaient et la gate passait verte en n'exigeant rien.
    C'est exactement la vacuité que le plancher est censé rendre impossible,
    et le plancher ne la voyait pas : il validait ``_CASES`` (correct) sans
    jamais vérifier que la JOINTURE résolvait. Les deux sont corrigés.
    """
    index: dict[pathlib.Path, list[type]] = {}
    for cls in public_component_classes():
        index.setdefault(
            pathlib.Path(inspect.getfile(cls)).resolve(), []
        ).append(cls)
    return index


_BY_MODULE = _module_index()


def _directional_modules() -> list[tuple[pathlib.Path, set[str]]]:
    """Les modules qui écrivent un libellé directionnel, + ses directions."""
    out: list[tuple[pathlib.Path, set[str]]] = []
    for path in component_sources():
        found = {
            (literal or key).lower()
            for literal, key in _LABEL.findall(path.read_text(encoding="utf-8"))
        }
        if found:
            out.append((path, found))
    return out


_CASES = _directional_modules()
_IDS = [p.stem for p, _d in _CASES]


@pytest.mark.parametrize("path,directions", _CASES, ids=_IDS)
def test_rendered_direction_has_an_imperative_method(
    path: pathlib.Path, directions: set[str]
) -> None:
    classes = _BY_MODULE.get(path, [])
    if not classes:
        pytest.skip(f"{path.name} n'expose aucun composant public")

    declared: set[str] = set()
    for cls in classes:
        declared |= set(getattr(cls, "IMPERATIVE", ()) or ())

    missing = {
        d for d in directions
        if not any(name.startswith(_PREFIX[d]) for name in declared)
    }
    assert not missing, (
        f"{path.name} dessine un contrôle {sorted(directions)} mais aucun "
        f"composant public du module n'expose la méthode correspondante "
        f"(manque : {sorted(missing)} ; déclaré : {sorted(declared)}).\n\n"
        f"Un composant qui rend l'affordance et la refuse à l'extérieur "
        f"force l'appelant à simuler un clic. Le nom n'a pas à être exact — "
        f"`prev`/`next` (Pagination, Stepper, Carousel) comme "
        f"`prev_month`/`next_month` (Calendar) satisfont la règle — mais la "
        f"direction doit être pilotable.\n\n"
        f"Rappel : `_needs_identity()` dérive de `IMPERATIVE`. Sans la "
        f"ClassVar, le composant peut ne rendre aucun `id`, et le dispatch "
        f"échoue alors EN SILENCE."
    )


def test_the_sweep_finds_the_known_directional_components() -> None:
    """Plancher de non-vacuité (règle 8 du CLAUDE.md).

    Un balayage qui ne trouve plus aucun libellé passerait vert en
    n'exigeant rien. On nomme donc les modules attendus : si l'un d'eux
    disparaît de la population, c'est le DÉTECTEUR qu'il faut réparer,
    pas la gate qu'il faut croire.
    """
    assert_sweep_is_not_vacuous()
    found = {p.stem for p, _d in _CASES}
    assert {"calendar", "carousel", "pagination"} <= found, (
        f"le balayage ne trouve plus les modules directionnels connus — "
        f"vu {sorted(found)}. Le motif de libellé a probablement changé "
        f"(il cherche un « Previous … » / « Next … » littéral)."
    )
    # …et la JOINTURE doit résoudre. Mesuré avant correction, lancé depuis le
    # parent du dépôt : « 1 passed, 3 skipped » — les trois cas se skippaient
    # et CE test passait quand même. Un plancher qui ne garde que la moitié
    # amont de la gate ne garde rien.
    unresolved = [p.name for p, _d in _CASES if not _BY_MODULE.get(p)]
    assert not unresolved, (
        f"aucun composant public rattaché à {unresolved} — la jointure "
        f"classe→fichier ne résout plus, donc les cas se SKIPPENT et la gate "
        f"ne vérifie rien. Vérifie `_module_index()` avant de la croire."
    )

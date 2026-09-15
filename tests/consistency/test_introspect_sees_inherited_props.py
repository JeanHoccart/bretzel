"""Gate : la fiche `describe` montre les props qui MARCHENT, et elles seules.

Deux fautes symétriques, toutes deux mesurées le 2026-08-16, toutes deux
livrées le même jour :

1. **Cacher une prop qui marche.** Le moteur lisait
   ``inspect.signature(cls.__init__)`` et ratait les props réactives
   héritées. ``HStack`` retire ``justify``/``wrap`` de son ``__init__``
   pour offrir une API réduite mais les hérite de ``Flex`` — donc
   ``ui.hstack(justify="between")`` marche, et la fiche disait le
   contraire.
2. **Annoncer une prop qui lève.** Le correctif de (1), en unissant
   simplement les deux déclarations, s'est mis à annoncer
   ``ui.hstack(direction="col")`` — qui lève un ``TypeError`` (l'axe est
   l'identité du raccourci). Même faute, signe opposé.

**Les deux envoient le même lecteur dans le mur**, et aucune n'échoue
bruyamment : la première produit un contournement
(``classes="justify-between"``), la seconde une exception à l'exécution.

D'où les trois tests ci-dessous, dont le dernier est le seul qui ne peut
pas être trompé : **``SEALED_PROPS`` doit VRAIMENT refuser**. Sans lui, y
inscrire un nom deviendrait un moyen commode de faire taire la gate.

Les attentes sont dérivées **du socle** (``__reactive_props__``,
``SEALED_PROPS``), jamais du module testé — une gate qui recompte depuis
sa propre source reste verte quand on débranche le balayage (memory
``project_gate_floors_must_read_the_gate_source``).

Mutations qui doivent rougir :
- retirer le bloc ``from_props`` de ``_component_params`` → test 3 ;
- retirer la ligne ``seen.update(SEALED_PROPS)`` → test 4 ;
- déclarer une prop utilisable dans ``SEALED_PROPS`` → test 5.
"""

from __future__ import annotations

import inspect

import pytest

from bretzel.introspect import describe_component
from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    public_component_classes,
    ui_name_of,
)

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "compare la fiche `describe` aux props RÉELLEMENT acceptées, et "
    "`test_a_sealed_prop_really_is_refused` exécute le refus : deux "
    "vérifications directes, aucun motif"
)

#: Le plancher vaut **1 et non 4**, à dessein : il ne protège pas la
#: population (4 composants aujourd'hui) mais l'EXISTENCE du cas dur.
#: Retirer un raccourci de layout est une évolution d'API légitime ;
#: n'en avoir plus AUCUN voudrait dire que le test ci-dessous passerait à
#: l'identique avec le moteur fautif, donc qu'il ne prouve plus rien.
_HARD_CASE_FLOOR = 1


def _reactive_prop_names(cls: type) -> set[str]:
    return set(getattr(cls, "__reactive_props__", None) or {})


def _sealed(cls: type) -> set[str]:
    return set(getattr(cls, "SEALED_PROPS", ()))


def _init_param_names(cls: type) -> set[str]:
    try:
        return set(inspect.signature(cls.__init__).parameters) - {"self", "kwargs"}
    except (TypeError, ValueError):  # pragma: no cover — aucun composant connu
        return set()


def _carded(cls: type) -> set[str]:
    return {p.name for p in describe_component(ui_name_of(cls), cls).params}


def _hard_cases() -> dict[type, set[str]]:
    """Les composants dont une prop réactive est absente de l'``__init__``
    sans être scellée — la population que seul le correctif attrape."""
    return {
        cls: hidden
        for cls in public_component_classes()
        if (hidden := _reactive_prop_names(cls) - _init_param_names(cls) - _sealed(cls))
    }


def test_sweep_is_not_vacuous() -> None:
    assert_sweep_is_not_vacuous()
    assert public_component_classes(), "aucun composant public découvert"


def test_the_hard_case_still_exists() -> None:
    """Plancher de non-vacuité — ancré sur la DÉCOUVERTE."""
    assert len(_hard_cases()) >= _HARD_CASE_FLOOR, (
        "plus aucun composant ne porte de prop réactive utilisable absente "
        "de son `__init__` — `test_every_usable_prop_is_on_the_card` "
        "passerait désormais à l'identique avec le moteur fautif, donc il "
        "ne prouve plus rien. Soit l'API a changé (mets à jour le plancher "
        "avec la mesure), soit le balayage est cassé."
    )


@pytest.mark.parametrize("cls", public_component_classes(), ids=lambda c: c.__name__)
def test_every_usable_prop_is_on_the_card(cls: type) -> None:
    """Faute n°1 — rien d'utilisable ne manque à la fiche."""
    missing = sorted(_reactive_prop_names(cls) - _sealed(cls) - _carded(cls))
    assert not missing, (
        f"{cls.__name__} accepte {missing} (props réactives déclarées sur la "
        f"classe, non scellées) mais sa fiche ne les montre pas. Un lecteur "
        f"les croira indisponibles et écrira un contournement `classes=...`."
    )


@pytest.mark.parametrize("cls", public_component_classes(), ids=lambda c: c.__name__)
def test_no_sealed_prop_is_advertised(cls: type) -> None:
    """Faute n°2 — rien de refusé n'est annoncé."""
    advertised = sorted(_sealed(cls) & _carded(cls))
    assert not advertised, (
        f"{cls.__name__} annonce {advertised} sur sa fiche alors que "
        f"`SEALED_PROPS` les refuse. Un lecteur écrira l'appel et prendra "
        f"une exception — une fiche qui promet un paramètre refusé est "
        f"aussi fausse qu'une fiche qui en cache un qui marche."
    )


@pytest.mark.parametrize(
    "cls",
    [c for c in public_component_classes() if _sealed(c)],
    ids=lambda c: c.__name__,
)
def test_a_sealed_prop_really_is_refused(cls: type) -> None:
    """L'anti-abus, et le seul test qu'on ne peut pas tromper.

    ``SEALED_PROPS`` retire des noms de la fiche. Si personne ne vérifiait
    que le socle les refuse VRAIMENT, y inscrire un nom deviendrait le
    moyen le plus court de faire taire
    `test_every_usable_prop_is_on_the_card` — et on aurait reconstruit la
    faute n°1 avec une bénédiction écrite.

    On vérifie sans contexte de rendu : les refus scellés lèvent dans
    l'``__init__`` du composant, AVANT le ``super().__init__()`` qui a
    besoin d'un contexte. Un ``RuntimeError`` « No render context » veut
    donc dire que le kwarg est passé — c'est-à-dire qu'il n'est PAS refusé.
    """
    for name in sorted(_sealed(cls)):
        with pytest.raises((TypeError, ValueError)) as caught:
            cls(**{name: "x"})
        assert "render context" not in str(caught.value), (
            f"{cls.__name__} déclare `{name}` scellée, mais l'appel a "
            f"traversé jusqu'au rendu — le kwarg n'est pas refusé. Retire-la "
            f"de SEALED_PROPS (elle marche, donc elle doit être sur la "
            f"fiche) ou pose le refus dans l'`__init__`."
        )

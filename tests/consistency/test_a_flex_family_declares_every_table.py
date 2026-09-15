"""Gate : un thème de la famille flex déclare une table par prop non scellée.

Le défaut que ça ferme
-----------------------
``ui.flex`` résout ses six props dans des tables de son thème
(``directions``, ``gaps``, ``grows``…). Mais ``ui.pane`` et
``ui.viewport`` ont chacun **leur propre** ``THEME`` — la convention du
dépôt veut qu'un thème soit auto-suffisant, « pour qu'un override n'ait
jamais à deviner d'où vient une valeur ».

Trois copies, donc, et la lecture est un ``theme.get(<groupe>, {})``
suivi d'un ``.get(<valeur>, "")``. Un groupe oublié dans UNE des copies
rend donc la chaîne vide : la prop devient un **kwarg mort** sur ce
composant-là seulement, sans erreur, sans warning, avec un HTML
parfaitement valide. C'est le mode d'échec dominant de ce dépôt, et il
s'est présenté le 2026-08-25 en ajoutant ``grow=`` : la table avait été
écrite dans ``FLEX_THEME`` et pas dans les deux autres, donc
``ui.pane(grow="16rem")`` rendait exactement comme ``ui.pane()``.

``ui.pane`` SCELLE ``wrap`` (``SEALED_PROPS``), et son thème n'a
légitimement aucun groupe ``wrap``. La règle est donc « une table par
prop **non scellée** » — sans quoi la gate exigerait un vocabulaire pour
une prop que le composant refuse à l'appel.

Ce que la gate lit, et pourquoi de là
--------------------------------------
``Flex.THEME_TABLES`` — la correspondance prop → groupe, déclarée dans le
CODE et lue par le rendu. Une gate qui dresserait sa propre liste de
groupes resterait verte le jour où le rendu en lit un septième
(memory ``project_gate_floors_must_read_the_gate_source``). Le plancher
verrouille l'autre bout : la table doit couvrir **exactement** les props
réactives déclarées sur ``Flex``, donc en retirer une entrée pour faire
taire la gate rougit le plancher.

Pourquoi ce n'est PAS ``test_a_flex_container_spaces_its_children``
--------------------------------------------------------------------
La gate voisine tient le même invariant — « une prop sans table rend la
chaîne vide en silence » — mais pour ``gap`` seulement, et par un
mécanisme qui **ne se généralise pas** : elle trouve la prop en lisant
``inspect.signature(cls.__init__)``. Or ``grow`` n'apparaît dans AUCUNE
signature de la famille sauf celle de ``Flex`` — ``hstack``, ``vstack``,
``pane`` et ``viewport`` le reçoivent par ``**kwargs``. Parametrer la
gate voisine sur ``(prop, groupe)`` déclarerait donc quatre « tables sans
prop » qui n'existent pas.

Les deux populations diffèrent aussi, et dans les deux sens : la voisine
balaie le catalogue entier (``grid`` et ``carousel`` ont une table
``gaps`` sans hériter de ``Flex``), celle-ci balaie la famille par le
MRO. Elles se recouvrent sur ``gap`` et ne se remplacent pas.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.reactive_prop import ReactivePropDescriptor
from bretzel.components.layout.flex.flex import Flex
from tests.consistency._discovery import public_component_classes, ui_name_of


def family() -> list[tuple[str, type]]:
    """Les composants publics qui résolvent leurs props par les tables de
    :class:`Flex` — donc tous ceux qui héritent d'elle."""
    return sorted(
        ((ui_name_of(cls), cls) for cls in public_component_classes()
         if issubclass(cls, Flex)),
        key=lambda pair: pair[0],
    )


def missing_tables(cls: type) -> list[tuple[str, str]]:
    """``(prop, groupe)`` que ce thème devrait déclarer et ne déclare pas.

    Le DÉTECTEUR de la gate, isolé pour que les deux tests de mutation
    l'attaquent directement au lieu de refabriquer un composant.
    """
    theme = getattr(cls, "THEME", None)
    if not isinstance(theme, dict):
        return []
    sealed = set(getattr(cls, "SEALED_PROPS", ()))
    return [
        (prop, group)
        for prop, group in Flex.THEME_TABLES.items()
        if prop not in sealed and group not in theme
    ]


#: Évalué une fois : le décorateur de paramétrage en avait besoin deux
#: fois (les cas ET leurs identifiants).
_FAMILY = family()


# ── Planchers ─────────────────────────────────────────────────────────

def test_the_sweep_finds_the_whole_family() -> None:
    """Cinq membres mesurés le 2026-08-25 : flex, hstack, pane, viewport,
    vstack. Le seuil laisse de la marge sans laisser passer un balayage
    qui ne trouverait plus personne."""
    found = family()
    assert len(found) >= 5, (
        f"la famille flex ne compte plus que {len(found)} membres "
        f"({[name for name, _ in found]}) — vérifie la découverte avant de "
        f"croire que cette gate passe."
    )


def test_the_map_covers_every_reactive_prop_of_flex() -> None:
    """Le plancher qui compte vraiment : ``THEME_TABLES`` doit couvrir
    EXACTEMENT les props réactives de ``Flex``.

    Sans lui, retirer une entrée de la table ferait taire la gate ET le
    rendu du même geste — une prop resterait acceptée à l'appel et
    n'émettrait plus rien, ce qui est précisément le défaut gardé.
    """
    declared = {
        name for name, value in vars(Flex).items()
        if isinstance(value, ReactivePropDescriptor)
    }
    assert declared == set(Flex.THEME_TABLES), (
        f"Flex.THEME_TABLES et les props réactives de Flex ont divergé.\n"
        f"  props sans groupe : {sorted(declared - set(Flex.THEME_TABLES))}\n"
        f"  groupes sans prop : {sorted(set(Flex.THEME_TABLES) - declared)}"
    )


# ── L'interdiction ────────────────────────────────────────────────────

@pytest.mark.parametrize("name,cls", _FAMILY, ids=[n for n, _ in _FAMILY])
def test_every_unsealed_prop_has_its_table(name: str, cls: type) -> None:
    missing = missing_tables(cls)
    assert not missing, (
        f"ui.{name} accepte des props qu'il ne peut pas résoudre : "
        f"{[f'{prop}= -> THEME[{group!r}]' for prop, group in missing]}.\n"
        f"Le rendu fait ``theme.get(<groupe>, {{}})`` puis "
        f"``.get(<valeur>, '')`` — un groupe absent rend la chaîne vide, "
        f"donc le kwarg est MORT sur ce composant sans que rien ne le "
        f"dise. Recopie le groupe dans son THEME (les thèmes de ce dépôt "
        f"sont auto-suffisants), ou scelle la prop via SEALED_PROPS."
    )


def test_the_family_shares_one_grows_table() -> None:
    """Les copies disent la même chose.

    Trois thèmes portent ``grows`` ; recopiés et non partagés, ils
    peuvent diverger. Un ``ui.pane(grow="20rem")`` qui donnerait une
    autre base qu'un ``ui.hstack(grow="20rem")`` serait invisible à toute
    lecture d'un seul fichier.
    """
    tables = {
        name: cls.THEME["grows"]
        for name, cls in family()
        if "grows" in getattr(cls, "THEME", {})
    }
    assert len(tables) >= 3, f"seulement {len(tables)} tables ``grows`` trouvées"
    reference = Flex.THEME["grows"]
    diverged = {name: t for name, t in tables.items() if t != reference}
    assert not diverged, (
        f"la table ``grows`` a divergé entre les copies : {sorted(diverged)}"
    )


def test_every_grow_class_is_whole() -> None:
    """Une valeur de ``grows`` est une classe ENTIÈRE, jamais un gabarit.

    ⚠️ Ce test a d'abord vérifié que chaque jeton existait dans
    ``tailwind_corpus()`` — et c'était **vacueux par construction** : le
    corpus glob ``bretzel/**/*.py``, donc il contient le fichier de thème
    d'où le jeton est lu. Il rendait vrai quoi qu'il arrive. Le versant
    « la classe émise existe dans les sources » est couvert catalogue
    entier par ``test_emitted_classes_exist_in_source``, qui balaie le
    HTML du playground — et la page ``/flex`` y démontre maintenant
    ``grow=``, donc ces classes-là y passent pour de vrai.

    Ce qui reste ici n'est pas vacueux : un ``{`` dans la valeur voudrait
    dire un gabarit à résoudre (``bg-{bg_color}``), donc une classe qui
    n'existe qu'après substitution et que seule la safelist peut couvrir.
    """
    for key, value in Flex.THEME["grows"].items():
        assert "{" not in value, (
            f"``grows[{key!r}]`` porte un gabarit à résoudre ({value!r}) — "
            f"cette table est faite de classes entières, sinon la safelist "
            f"devrait la couvrir (cf. ``theme/tailwind.py``)."
        )


# ── Preuve que le détecteur mord, dans les DEUX sens ──────────────────

def test_the_detector_bites_on_a_missing_table() -> None:
    """Le versant ILLICITE : un thème amputé est vu."""

    class AmputatedPane(Flex):
        THEME = {k: v for k, v in Flex.THEME.items() if k != "grows"}

    assert ("grow", "grows") in missing_tables(AmputatedPane)


def test_the_detector_stays_quiet_on_a_sealed_prop() -> None:
    """Le versant LICITE, et c'est lui qui a trouvé les deux seuls bugs de
    gate du dépôt : un détecteur qui rougit sur un cas correct est aussi
    cassé qu'un détecteur aveugle.

    ``ui.pane`` n'a PAS de groupe ``wrap`` et c'est juste — il scelle la
    prop. La gate doit se taire.
    """

    class SealedWrap(Flex):
        THEME = {k: v for k, v in Flex.THEME.items() if k != "wrap"}
        SEALED_PROPS = ("wrap",)

    assert missing_tables(SealedWrap) == []

    # …et le scellement ne doit pas excuser les AUTRES groupes.
    class SealedWrapButAlsoAmputated(SealedWrap):
        THEME = {k: v for k, v in SealedWrap.THEME.items() if k != "gaps"}

    assert ("gap", "gaps") in missing_tables(SealedWrapButAlsoAmputated)

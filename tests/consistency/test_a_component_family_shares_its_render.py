"""Gate : une famille de composants a UN rendu, pas un par membre.

Ce que la mesure a montré (2026-08-19)
----------------------------------------
Quatre familles, quatre fois la même histoire — deux composants qui ne
se ressemblent pas, ce sont deux composants qui SONT le même rendu,
paramétré par une poignée de valeurs :

===========================  =========  ==========  ====================
paire                        render     identiques  ce qui les sépare
===========================  =========  ==========  ====================
``month_picker`` / ``week``  130 / 125  107 (82 %)  7 valeurs
``dialog`` / ``drawer``      181 / 176  139 (76 %)  3 classes de style
``dropdown`` / ``popover``    99 / 103   75 (75 %)  4 valeurs
``checkbox`` / ``switch``    137 / 113   86 (62 %)  les nœuds visuels
===========================  =========  ==========  ====================

⚠️ **Et à chaque fois, une bonne part de l'écart restant n'était pas du
code : c'étaient les commentaires.** La même mécanique — pourquoi le
backdrop porte le clic et pas le conteneur, pourquoi un scope local doit
se resynchroniser quand la valeur est backée serveur, pourquoi une case
décochée ne soumet rien — y était expliquée deux fois, avec des mots
différents et à des niveaux de détail différents. Un lecteur ne pouvait
donc pas savoir si les deux membres se comportent pareil sans relire les
deux. C'est le coût que la duplication fait payer AVANT d'avoir produit
le moindre bug.

Ce que la gate exige
---------------------
Chaque famille a un module qui POSSÈDE son rendu, et un ou deux appels
qui la **signent** — le geste qu'on ne fait que quand on assemble
soi-même. Le composant qui les appelle est donc un membre qui a réécrit
le rendu de sa famille : c'est autorisé seulement pour ce qui le faisait
déjà au 2026-08-19, déclaré AVEC sa raison.

Le prochain membre passe par le rendu de sa famille, ou fait rougir
cette gate — ce qui est le but : la question se pose au moment de
l'écrire, pas à la troisième copie.

⚠️ Ce qu'elle ne dit PAS
-------------------------
Que les rendus partagés soient corrects. Ce qui l'a prouvé, c'est autre
chose, et c'est plus fort qu'un probe visuel pour un refactor : le HTML
rendu est **byte-identique** avant/après — 10 cas pour les pickers, 9
pour les modaux, 6 pour les ancrés, 6 pour les cochables. Si l'octet ne
bouge pas, le pixel ne peut pas bouger.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

import pytest

from tests.consistency._discovery import COMPONENTS_DIR, PACKAGE_FLOOR, parsed_sources


@dataclass(frozen=True)
class Family:
    """Une famille : qui possède le rendu, ce qui le signe, qui déroge."""

    owner: str
    """Nom du fichier qui porte le rendu partagé."""

    markers: frozenset[str]
    """Appels qu'on ne fait QUE quand on assemble le rendu soi-même."""

    hand_rolled: dict[str, str] = field(default_factory=dict)
    """``fichier -> raison`` de ne pas (encore) passer par le rendu."""


_FAMILIES: dict[str, Family] = {
    "picker ancré": Family(
        owner="_picker_field.py",
        markers=frozenset({"relocate_field_events", "calendar_picker_scope"}),
        hand_rolled={
            "date_picker.py": "table de tailles en forme INVERSÉE (sizes[slot][size])",
            "date_range_picker.py": "idem, plus deux valeurs (début / fin) dans un scope",
            "time_picker.py": "pas de <bz-calendar> — son panneau est une liste d'heures",
            "color_picker.py": (
                "même raison que time_picker, un cran plus loin : son "
                "panneau est une grille de PASTILLES, et sa valeur n'est "
                "ni une date ni une heure — il n'y a donc ni calendrier à "
                "monter ni miroir de granularité à câbler. Il réutilise "
                "en revanche les FABRIQUES du module (hidden_carrier, "
                "trigger_button, clear_button, anchored_panel, "
                "relocate_field_events), qui sont l'essentiel du partage"
            ),
        },
    ),
    "overlay modal": Family(
        owner="_modal.py",
        markers=frozenset({"modal_root_effect"}),
        hand_rolled={
            "sidebar.py": (
                "sa forme `overlay` est un modal, mais elle n'est qu'un des "
                "trois modes du composant (fixed / rail / overlay) — elle n'a "
                "ni backdrop à elle ni panneau séparé du reste"
            ),
        },
    ),
    "overlay ancré": Family(
        owner="_anchored.py",
        markers=frozenset({"anchored_trigger_wrapper"}),
        hand_rolled={
            "combobox.py": (
                "panneau ancré, mais son déclencheur EST son champ de saisie : "
                "il n'y a pas de composant `trigger=` à envelopper"
            ),
        },
    ),
    "cochable": Family(
        owner="_checkable.py",
        markers=frozenset({"checked_command_listeners"}),
    ),
}

#: Les modules qui POSSÈDENT du câblage partagé : ils ont le droit de
#: nommer n'importe quel marqueur, c'est leur travail.
_OWNERS = frozenset({f.owner for f in _FAMILIES.values()} | {"_wiring.py"})


def calls_in(tree: ast.AST, markers: frozenset[str]) -> set[str]:
    """Les marqueurs réellement APPELÉS — un import ne suffit pas."""
    return {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (name := getattr(node.func, "id", None)) in markers
    }


def members_rerolling(family: Family) -> list[str]:
    """Les modules qui assemblent eux-mêmes le rendu de cette famille."""
    return sorted(
        source.path.name
        for source in parsed_sources(COMPONENTS_DIR, floor=PACKAGE_FLOOR // 2)
        if source.path.name not in _OWNERS
        and calls_in(source.tree, family.markers)
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : chaque marqueur désigne encore une fonction réelle, et
    le module qui possède le rendu l'appelle bien.

    Un marqueur renommé rendrait la gate verte sur zéro reconnaissance —
    et le prochain membre recopierait ses 139 lignes sans un mot.
    """
    for name, family in _FAMILIES.items():
        owner_src = next(
            s for s in parsed_sources(COMPONENTS_DIR, floor=PACKAGE_FLOOR // 2)
            if s.path.name == family.owner
        )
        used = calls_in(owner_src.tree, family.markers)
        assert used == family.markers, (
            f"famille « {name} » : {sorted(family.markers - used)} n'est "
            f"plus appelé par {family.owner}. Soit le rendu partagé ne "
            f"câble plus ce qui définit la famille, soit le marqueur a été "
            f"renommé — dans les deux cas la gate ne reconnaît plus rien."
        )


@pytest.mark.parametrize(
    ("family_name", "module"),
    [(n, m) for n, f in _FAMILIES.items() for m in sorted(f.hand_rolled)],
    ids=lambda v: v if isinstance(v, str) else str(v),
)
def test_a_declared_exception_still_rerolls(family_name: str, module: str) -> None:
    """Une entrée périmée autorise plus que la réalité."""
    assert module in members_rerolling(_FAMILIES[family_name]), (
        f"{module} n'assemble plus le rendu « {family_name} » à la main — "
        f"retire son entrée. Une table qui garde des noms périmés finit par "
        f"couvrir un composant qu'elle n'a jamais examiné."
    )


@pytest.mark.parametrize("family_name", sorted(_FAMILIES), ids=lambda n: n)
def test_no_new_member_rerolls_the_family_render(family_name: str) -> None:
    family = _FAMILIES[family_name]
    offenders = [
        m for m in members_rerolling(family) if m not in family.hand_rolled
    ]
    assert not offenders, (
        f"{offenders} assemble(nt) le rendu « {family_name} » à la main.\n"
        f"  Mesuré le 2026-08-19 sur quatre familles : entre 62 % et 82 % "
        f"des lignes de `render()` étaient IDENTIQUES d'un membre à "
        f"l'autre — et une bonne part de ce qui les distinguait n'était "
        f"pas du code, c'étaient des commentaires expliquant la même "
        f"mécanique différemment.\n"
        f"  Passe par `{family.owner}`. Il prend des classes DÉJÀ "
        f"composées : les chaînes de style restent chez toi."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un APPEL est vu, un import du même nom ne l'est pas.

    Le second cas compte autant que le premier : plusieurs modules
    importent ces helpers pour les re-exporter ou les documenter. Une
    gate qui compte les imports accuserait des innocents, et on la ferait
    taire en gonflant la table des exceptions — c'est-à-dire en la vidant
    de son sens.
    """
    markers = frozenset({"modal_root_effect", "checked_command_listeners"})

    appelle = ast.parse(
        "def render(self):\n"
        "    attrs['bz-effect'] = modal_root_effect(open_expr)\n"
        "    attrs.update(checked_command_listeners())\n"
    )
    assert calls_in(appelle, markers) == markers, (
        "le détecteur ne voit plus les appels qu'il existe pour interdire."
    )

    importe = ast.parse(
        "from bretzel.components.base._wiring import modal_root_effect\n"
        "__all__ = ['modal_root_effect']\n"
    )
    assert not calls_in(importe, markers), (
        "le détecteur compte un IMPORT comme un assemblage à la main — il "
        "accuserait tout module qui ré-exporte le helper."
    )

"""Une page de composant porte les cartes que sa surface EXIGE.

`.claude/bretzel/playground-pattern.md` fixe le gabarit : sept sections,
jusqu'à dix cartes, et la liste de celles qui sont obligatoires se DÉDUIT
du composant — ``EVENTS`` non vide impose *Server events* et *Client
events*, ``BINDABLE_PROPS`` impose *Client playground*, ``IMPERATIVE``
impose *External controls — the 3 modes*.

Pourquoi une gate et pas seulement la doc
------------------------------------------

Parce que la doc a déjà été lue et le gabarit quand même raté : la page
``color_picker`` livrée le 2026-08-30 avait cinq cartes sur neuf, et
``test_playground_demos_the_api`` est restée VERTE — elle vérifie que
chaque *paramètre* est démontré quelque part, pas que la page a la forme
qui permet de le juger. Une page sans *Client playground* ne montre nulle
part ce que le binding émet ; sans *Server events*, aucun handler ne part
jamais. Le trou n'est pas cosmétique : il retire au banc ce qui en fait un
banc.

Ce qui compte comme carte présente
-----------------------------------

Un ``ui.heading("<titre>", level=2)`` dont le titre est le nom canonique,
ou le nom canonique suivi d'un tiret cadratin. Badge et Banner écrivent
``"Server events — on_close"`` : le suffixe NOMME l'événement câblé, il
informe au lieu de diluer, et deux pages l'utilisent déjà. Refuser ce
suffixe imposerait un diff cosmétique à des pages correctes.

``_BASELINE`` est **vide** : les neuf trous que cette gate a trouvés à sa
naissance ont été comblés le jour même. Elle reste là parce que l'assert
est une égalité STRICTE — combler un trou sans retirer son entrée fait
échouer la gate, donc une exemption ne peut pas pourrir en silence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.consistency._discovery import (
    parsed_sources,
    public_component_classes,
)

#: Preuve de morsure : re-mesure chaque exemption. Une entrée dont le
#: composant, la page ou la RÈGLE n'existe plus doit sortir, sinon la
#: baseline couvre un fantôme et laisse passer le vrai cas.
MUTATION_PROOF = "test_the_baseline_has_no_ghost"

_FEATURES = (
    Path(__file__).resolve().parents[2] / "examples" / "playground" / "features"
)

#: Plancher du balayage du playground — **96 fichiers** mesurés le
#: 2026-08-30, contre 200 la veille : la famille ``/matrix`` (65
#: fichiers) et ``datatable_solo`` ont été supprimées. Le seuil garde la
#: même marge relative — il doit rougir si le chemin casse, pas si on
#: réorganise.
_FEATURES_FLOOR = 80

#: Plancher de DÉCOUVERTE : combien de composants ont une page dédiée.
#: **69 sur 101** re-mesurés le 2026-08-31 (le « 74 » écrit ici la veille
#: n'a jamais été vérifié). C'est ce nombre-là qu'il faut ancrer, pas le
#: nombre de fichiers : débrancher la résolution page↔composant laisse le
#: balayage de fichiers intact et rendrait la gate vide en silence.
#:
#: ⚠️ **Les 32 autres sont sautés en silence, et c'est une limite
#: connue.** La résolution est exacte sur le nom : ``RadioGroup`` vit sur
#: ``radio.py``, ``ToggleButton`` sur ``toggle_group.py``, ``Viewport`` et
#: ``Pane`` sur ``screen.py`` — aucun n'est trouvé. L'écrasante majorité
#: sont des enfants (``SidebarItem``, ``Tab``, ``Step``…) qui vivent
#: légitimement sur la page de leur parent, donc une liste déclarée serait
#: surtout du bruit. Ce qui rattrape le trou : ``test_playground_demos_the_api``
#: rougit si un paramètre cesse d'être démontré QUELQUE PART, donc une
#: page perdue ne passe pas inaperçue — elle passe juste inaperçue *ici*.
_PAGED_FLOOR = 65

#: Les cartes toujours dues, quelle que soit la surface du composant.
_ALWAYS = ("Reference", "Edge cases", "A11y", "Server playground")

#: Les cartes dues SOUS CONDITION, et l'attribut de classe qui la porte.
#: Le titre de §7 est canonique — « External triggers » et autres
#: variantes sont refusées par construction, puisque seul ce libellé-ci
#: est cherché.
_CONDITIONAL: tuple[tuple[str, str], ...] = (
    ("EVENTS", "Server events"),
    ("EVENTS", "Client events"),
    ("BINDABLE_PROPS", "Client playground"),
    ("IMPERATIVE", "External controls — the 3 modes"),
)

#: Zéro. Les neuf trous mesurés le 2026-08-30 ont été comblés le jour
#: même — la baseline reste, vide, parce qu'une gate sans exemption
#: possible pousse le prochain à renommer une carte plutôt qu'à
#: l'écrire. Y ajouter une ligne est un choix explicite, pas un défaut.
_BASELINE: frozenset[tuple[str, str]] = frozenset()


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _sources() -> dict[Path, ast.Module]:
    return {s.path: s.tree for s in parsed_sources(_FEATURES, floor=_FEATURES_FLOOR)}


_TREES = _sources()


def _page_trees(cls: type) -> list[ast.Module]:
    """Les arbres de la page dédiée du composant, ou ``[]`` s'il n'en a pas.

    Deux formes, celles du gabarit : un fichier ``<nom>.py``, ou un
    paquet ``<nom>/`` quand la page a dépassé sa taille — auquel cas les
    cartes vivent dans ``ui.py`` et il faut lire tout le dossier.
    """
    stem = _snake(cls.__name__)
    single = _FEATURES / f"{stem}.py"
    if single in _TREES:
        return [_TREES[single]]
    folder = _FEATURES / stem
    return [tree for path, tree in _TREES.items() if folder in path.parents]


def card_titles(tree: ast.AST) -> set[str]:
    """Les titres de carte d'un arbre : ``ui.heading(<str>, level=2)``.

    En AST et pas en texte : un titre qui traverse deux lignes, chose
    courante dans ces pages, échappe à toute expression régulière — et un
    ``level=2`` cherché à part créditerait le mauvais appel.
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "heading"):
            continue
        level = next(
            (k.value for k in node.keywords if k.arg == "level"), None
        )
        if not (isinstance(level, ast.Constant) and level.value == 2):
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if isinstance(value, str):
                out.add(re.sub(r"\s+", " ", value).strip())
    return out


def required_cards(cls: type) -> set[str]:
    """Les cartes que la surface du composant rend obligatoires."""
    due = set(_ALWAYS)
    for attribute, card in _CONDITIONAL:
        if getattr(cls, attribute, ()):
            due.add(card)
    return due


def missing_cards(cls: type, present: set[str]) -> set[str]:
    """Ce qui manque — un titre suffixé d'un tiret cadratin compte."""
    return {
        card
        for card in required_cards(cls)
        if not any(
            title == card or title.startswith(f"{card} —")
            for title in present
        )
    }


def _measured() -> tuple[dict[str, set[str]], dict[str, type]]:
    """``({composant: cartes manquantes}, {composant: classe})``."""
    gaps: dict[str, set[str]] = {}
    paged: dict[str, type] = {}
    for cls in public_component_classes():
        trees = _page_trees(cls)
        if not trees:
            continue
        paged[cls.__name__] = cls
        present: set[str] = set()
        for tree in trees:
            present |= card_titles(tree)
        if lacking := missing_cards(cls, present):
            gaps[cls.__name__] = lacking
    return gaps, paged


_GAPS, _PAGED = _measured()


def test_the_sweep_is_not_vacuous() -> None:
    """Le plancher lit la DÉCOUVERTE, pas la population.

    Compter les fichiers ne dirait rien : débrancher ``_page_trees``
    laisserait 200 fichiers lus et zéro composant jugé. On ancre donc sur
    le nombre de composants EFFECTIVEMENT reliés à une page, et sur le
    fait que chaque règle conditionnelle a trouvé quelqu'un à qui
    s'appliquer — une règle qui ne s'applique à personne est morte.
    """
    assert len(_PAGED) >= _PAGED_FLOOR, (
        f"{len(_PAGED)} composants reliés à une page du playground, "
        f"plancher {_PAGED_FLOOR} — la résolution page↔composant est "
        "probablement cassée."
    )
    for attribute, card in _CONDITIONAL:
        concerned = [
            name for name, cls in _PAGED.items() if getattr(cls, attribute, ())
        ]
        assert len(concerned) >= 5, (
            f"la règle « {attribute} → {card} » ne concerne que "
            f"{len(concerned)} composant(s) : elle ne juge plus rien."
        )
    with_cards = sum(
        1
        for cls in _PAGED.values()
        if any(card_titles(t) for t in _page_trees(cls))
    )
    assert with_cards >= _PAGED_FLOOR, (
        f"{with_cards} pages seulement rendent un titre de carte : "
        "l'extracteur est cassé, pas les pages."
    )


def test_every_component_page_carries_its_mandatory_cards() -> None:
    measured = frozenset(
        (name, card) for name, cards in _GAPS.items() for card in cards
    )
    surplus = sorted(measured - _BASELINE)
    stale = sorted(_BASELINE - measured)
    detail = ["le gabarit de `.claude/bretzel/playground-pattern.md` n'est "
              "pas tenu."]
    if surplus:
        detail.append("  cartes obligatoires ABSENTES, hors baseline :")
        detail += [f"      {n} — carte « {c} »" for n, c in surplus]
    if stale:
        detail.append("  entrées de baseline désormais comblées — à "
                      "retirer :")
        detail += [f"      {n} — carte « {c} »" for n, c in stale]
    assert measured == _BASELINE, "\n".join(detail)


def test_the_baseline_has_no_ghost() -> None:
    """Chaque exemption est re-mesurée : composant, page, ET règle.

    Une entrée peut pourrir de trois façons — le composant disparaît, sa
    page disparaît, ou sa surface change au point que la carte n'est plus
    due. Les trois laisseraient la baseline couvrir un fantôme, donc
    absorber en silence un VRAI trou apparu ailleurs.
    """
    for name, card in sorted(_BASELINE):
        cls = _PAGED.get(name)
        assert cls is not None, (
            f"baseline fantôme : « {name} » n'a plus de page dédiée."
        )
        assert card in required_cards(cls), (
            f"baseline fantôme : la carte « {card} » n'est plus due à "
            f"« {name} » — sa surface a changé."
        )


@pytest.mark.parametrize(
    "source, expected",
    [
        # Le versant ILLICITE : une carte due qui manque est vue.
        ('ui.heading("Reference", level=2)', {"Edge cases", "A11y",
                                              "Server playground"}),
        # Le versant LICITE, celui qui trouve les bugs de gate : le
        # suffixe « — on_close » de Badge/Banner compte, et un titre de
        # niveau 3 homonyme ne compte PAS pour une carte.
        (
            'ui.heading("Reference", level=2)\n'
            'ui.heading("Edge cases", level=2)\n'
            'ui.heading("A11y", level=2)\n'
            'ui.heading("Server playground", level=2)',
            set(),
        ),
        (
            'ui.heading("Reference", level=3)\n'
            'ui.heading("Edge cases", level=2)\n'
            'ui.heading("A11y", level=2)\n'
            'ui.heading("Server playground", level=2)',
            {"Reference"},
        ),
    ],
)
def test_the_reader_bites_both_ways(source: str, expected: set[str]) -> None:
    class _Leaf:
        EVENTS: tuple[str, ...] = ()
        BINDABLE_PROPS: tuple[str, ...] = ()
        IMPERATIVE: tuple[str, ...] = ()

    assert missing_cards(_Leaf, card_titles(ast.parse(source))) == expected


def test_a_suffixed_title_counts_for_its_card() -> None:
    """Le cas réel derrière la tolérance : ``"Server events — on_close"``.

    Écrit sans elle, la gate exigerait de Badge et Banner un renommage
    qui RETIRE une information — quel événement la carte câble.
    """
    class _Emitter:
        EVENTS = ("close",)
        BINDABLE_PROPS: tuple[str, ...] = ()
        IMPERATIVE: tuple[str, ...] = ()

    source = (
        'ui.heading("Reference", level=2)\n'
        'ui.heading("Edge cases", level=2)\n'
        'ui.heading("A11y", level=2)\n'
        'ui.heading("Server playground", level=2)\n'
        'ui.heading("Server events — on_close", level=2)\n'
        'ui.heading("Client events — on_close", level=2)'
    )
    assert missing_cards(_Emitter, card_titles(ast.parse(source))) == set()

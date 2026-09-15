"""Gate : la règle bindable n'est énoncée qu'à UN endroit.

« Cette prop mérite-t-elle un binding client ? » est la décision la plus
structurante de l'écriture d'un composant. Elle était **énoncée en entier
dans quatre fichiers** du funnel — ``client-reactive-surface.md``,
``components.md``, ``kwarg-routing.md``, ``creating-a-component.md``.

Quatre copies dérivent à quatre vitesses, et c'est arrivé : la version de
``kwarg-routing.md`` admettait encore un critère (« l'état reflète une
source externe : websocket, polling, sync API ») qui n'existe nulle part
dans la règle figée le 2026-07-16. Un lecteur qui tombait sur cette page
appliquait une règle que le dépôt avait abandonnée.

L'invariant gardé : les **trois étiquettes de verdict** de la règle
(``⇄ two-way`` / ``→ one-way`` / ``∅ statique``) ne se rencontrent
ensemble que dans le fichier qui possède la règle. Un fichier qui la
re-énonce les porte forcément toutes les trois ; une page qui s'y réfère
n'en cite au plus qu'une ou deux.

**Portée honnête.** On ne mesure pas la *justesse* d'une paraphrase, ni la
duplication de prose en général — on empêche la seule duplication qui a
prouvé qu'elle dérive. Une matrice a parfaitement le droit d'utiliser
``one-way`` comme valeur de colonne : c'est le triplet complet qui
signale une ré-énonciation.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pytest

_FUNNEL = Path(__file__).resolve().parents[2] / ".claude" / "bretzel"

# Le fichier qui POSSÈDE la règle. Le seul autorisé à porter le triplet.
_OWNER = "client-reactive-surface.md"

# Les étiquettes de verdict, à la lettre. Les symboles nus (``∅`` seul,
# ``one-way`` seul) ne comptent pas : une colonne de matrice les porte
# légitimement.
_VERDICT_LABELS = ("⇄ two-way", "→ one-way", "∅ statique")


@functools.lru_cache(maxsize=1)
def _funnel_docs() -> tuple[Path, ...]:
    return tuple(sorted(_FUNNEL.glob("*.md")))


def _labels_in(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [label for label in _VERDICT_LABELS if label in text]


def test_discovery_non_trivial() -> None:
    """Plancher de population : la gate balaie bien un funnel peuplé.

    Le pendant du test ci-dessous. Celui-là garde le *contenu* (le
    propriétaire énonce encore la règle), celui-ci garde la *population* —
    un glob cassé rendrait l'interdiction verte sur zéro fichier.
    """
    assert len(_funnel_docs()) >= 15, (
        f"seulement {len(_funnel_docs())} fichiers de funnel balayés (25 le "
        f"2026-08-01) — le glob est cassé, l'interdiction ne porte plus sur "
        f"rien."
    )


def test_the_detector_still_finds_the_rule_in_its_owner() -> None:
    """Contrôle POSITIF : le détecteur trouve encore la règle là où elle
    DOIT être.

    C'est la forme de preuve que prend une gate dont le détecteur est une
    liste d'étiquettes : plutôt que fabriquer une violation, on vérifie
    qu'il reconnaît le cas connu. Sans ça, renommer les étiquettes ferait
    passer l'interdiction sur zéro fichier — verte parce qu'elle ne
    cherche plus rien.
    """
    owner = _FUNNEL / _OWNER
    assert owner.exists(), f"{_OWNER} a disparu — la règle a changé de maison ?"
    missing = sorted(set(_VERDICT_LABELS) - set(_labels_in(owner)))
    assert not missing, (
        f"{_OWNER} n'énonce plus la règle avec {missing} — soit les "
        f"étiquettes ont été renommées (mets `_VERDICT_LABELS` à jour), "
        f"soit la règle a déménagé (mets `_OWNER` à jour). En l'état la "
        f"gate ne garde plus rien."
    )


@pytest.mark.parametrize(
    "doc", [p for p in _funnel_docs() if p.name != _OWNER], ids=lambda p: p.name
)
def test_no_other_file_restates_the_rule(doc: Path) -> None:
    found = _labels_in(doc)
    assert len(found) < len(_VERDICT_LABELS), (
        f"`{doc.name}` porte les trois verdicts de la règle bindable "
        f"({found}) — donc il la RÉ-ÉNONCE.\n"
        f"  Quatre copies ont dérivé à quatre vitesses jusqu'au "
        f"2026-08-01 ; l'une admettait un critère abandonné depuis le "
        f"2026-07-16.\n"
        f"  Renvoie vers `{_OWNER}` § *La règle* et ne garde ici que ce "
        f"qui est PROPRE à cette page (une conséquence, une matrice, un "
        f"exemple)."
    )

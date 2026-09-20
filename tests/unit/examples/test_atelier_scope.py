"""Le périmètre d'une tâche d'atelier se lit sur ce qu'elle TOUCHE.

Pourquoi ces tests-là
----------------------
L'utilisateur a ouvert l'atelier le 2026-09-12 et vu onze tâches rangées
dans ``app:ecole``, dont celle qui a SUPPRIMÉ ``examples/ecole``. La
mesure n'était pas fausse par hasard : deux choses pesaient dans le vote
sans être des sujets de travail.

- **l'aiguille d'une recherche**. ``grep -rln "examples/ecole" .`` balaie
  le dépôt entier ; le motif nommait l'app, donc la tâche lui était
  attribuée. Même faute sous sa forme outil : le ``pattern`` d'un
  ``Grep`` était lu comme une cible et son ``path`` ignoré ;
- **le brouillon**. Un script jetable écrit pour mesurer le socle parle
  du socle. Il gagnait quand même, par nombre : 178 tâches sur 276
  rangées « brouillon » avaient un vrai sujet dans leurs propres
  écritures.

Chaque test porte donc les DEUX versants — ce que la règle doit refuser,
et ce qu'elle ne doit surtout pas emporter au passage. Une règle qui
coupe trop rendrait toutes les tâches « autre », et ça se verrait moins
qu'un faux positif.
"""

from __future__ import annotations

import pytest

from examples.atelier.core.ingest import target_of
from examples.atelier.core.scope import (
    APP,
    DOC,
    FRAMEWORK,
    SCRATCH,
    TESTS,
    dominant,
    scope_of,
    scopes_in,
    without_needles,
)

#: La commande réelle qui a fait ranger « non je préfère crm » dans
#: ``app:ecole`` — premier appel de la tâche 1228 de la base.
CHERCHE_ECOLE = (
    'grep -rln "examples[./]ecole\\|examples/ecole\\|probe_ecole" '
    "--include=*.py --include=*.md -- ."
)


def test_le_motif_cherche_ne_compte_pas_comme_cible():
    """Chercher le nom d'une app ne travaille pas sur cette app."""
    assert f"{APP}ecole" not in scopes_in(CHERCHE_ECOLE)


@pytest.mark.parametrize(
    "commande, attendu",
    [
        # Le dossier balayé reste une cible : il est APRÈS le motif.
        ('grep -rn "hstack" bretzel/components/layout/stack.py', FRAMEWORK),
        ("grep -c . tests/consistency/test_gates.py", TESTS),
        # Sans recherche, rien ne change.
        ("sed -n '1,50p' examples/crm/main.py", f"{APP}crm"),
        ("py -m pytest tests/unit/test_state.py", TESTS),
        ("cat .claude/work/todo.md", DOC),
    ],
)
def test_la_coupe_n_emporte_pas_les_vraies_cibles(commande, attendu):
    """Le versant licite : sans lui, la règle pourrait tout couper.

    C'est le plancher de cette gate. Une :func:`without_needles` qui
    renverrait la chaîne vide passerait le test du dessus et ne dirait
    plus rien de personne.
    """
    assert attendu in scopes_in(commande)


def test_seul_le_motif_est_coupe():
    """La coupe est chirurgicale : le reste de la commande survit."""
    coupe = without_needles(CHERCHE_ECOLE)
    assert "--include=*.py" in coupe
    assert "examples/ecole" not in coupe


def test_le_grep_outil_vise_son_chemin_pas_son_motif():
    """Même règle, forme outil — c'était l'autre moitié de la faute."""
    entree = {"pattern": "examples/ecole", "path": "bretzel/components"}
    assert scope_of(target_of("Grep", entree)) == FRAMEWORK
    # Un Grep sans chemin ne vise rien plutôt que de viser son motif.
    assert target_of("Grep", {"pattern": "examples/ecole"}) == ""
    # Les autres outils gardent leur cible habituelle.
    assert target_of("Write", {"file_path": "examples/crm/main.py"}) == (
        "examples/crm/main.py"
    )


def test_le_brouillon_ne_gagne_que_seul():
    """Un jetable est un moyen ; il ne devient un sujet que s'il est tout."""
    assert dominant([SCRATCH] * 9 + [FRAMEWORK]) == FRAMEWORK
    assert dominant([SCRATCH, SCRATCH]) == SCRATCH
    # Et il ne fait pas gagner « autre » : sans lui il resterait un vote.
    assert dominant([SCRATCH] * 3 + [TESTS, DOC, DOC]) == DOC


def test_le_vote_reste_majoritaire_hors_brouillon():
    """Le reste de l'arbitrage est inchangé — c'est le plus fréquent."""
    assert dominant([FRAMEWORK, FRAMEWORK, TESTS]) == FRAMEWORK
    assert dominant([]) == "other"

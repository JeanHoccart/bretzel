"""L'import d'``examples/ecole` : les deux temps, et le piège n° 5.

Le piège n° 5 est le plus visible du cahier — *« apparier les photos par
POSITION : chaque visage sur son voisin dès qu'un élève est parti »* — et
c'est le seul qu'un test peut prouver en une ligne. Les autres constats
portent sur la règle qui rend l'écran sûr : **rien n'entre en base avant
qu'on ait regardé**.
"""

from __future__ import annotations

from examples.ecole.features.annees import annee_en_cours
from examples.ecole.features.import_data import (
    analyser,
    cle_de,
    lire_csv,
    sans_accents,
)

# ── EF-J6 · sans accents ni casse, mais deux champs DISTINCTS ────────

def test_la_comparaison_ignore_les_accents_et_la_casse() -> None:
    """*« "courty leane" doit retrouver "COURTY Léane". »*"""
    assert cle_de("COURTY", "Léane") == cle_de("courty", "leane")
    assert sans_accents("Noël") == "noel"


def test_le_nom_et_le_prenom_restent_distincts() -> None:
    """EF-C7 : *« un élève qui s'appelle LEA de son nom ne doit pas se
    confondre avec une Léa de prénom »*. La clé les sépare par un
    caractère qui n'apparaît dans aucun nom."""
    assert cle_de("Lea", "Martin") != cle_de("Martin", "Lea")


# ── Le format déposé ──────────────────────────────────────────────────

def test_deux_separateurs_sont_acceptes() -> None:
    lignes = lire_csv("COURTY;Léane\nVALLOIS,Malo")
    assert [(li["nom"], li["prenom"]) for li in lignes] == [
        ("COURTY", "Léane"), ("VALLOIS", "Malo")]


def test_une_ligne_illisible_devient_une_erreur_et_non_un_saut() -> None:
    """EF-J7 : *« ce qu'on ne reconnaît pas est DIT, pas deviné »*. Une
    ligne sautée disparaîtrait de l'écran, et le professeur croirait
    l'avoir importée."""
    lignes = lire_csv("COURTY;Léane\nMALO\n")
    assert len(lignes) == 2
    assert lignes[1]["erreur"]


def test_une_entete_est_ignoree() -> None:
    assert len(lire_csv("Nom;Prénom\nCOURTY;Léane")) == 1


# ── EF-J1, EF-J3 · analyser n'écrit rien, et refuse ce qui doit ──────

def test_analyser_nechrit_rien_et_refuse_une_classe_deja_pleine() -> None:
    """EF-J3 : *« un second passage y dupliquerait la liste entière »*.

    Le refus est rendu dans le RÉSULTAT, pas levé : l'écran doit pouvoir
    montrer la liste ET le refus en même temps, pour que le professeur
    voie ce qu'il aurait importé.
    """
    from examples.ecole.core.db import init_db, scalar

    init_db()
    annee = annee_en_cours()
    avant = scalar("SELECT COUNT(*) FROM eleves")
    resultat = analyser(annee["id"], "6e2", "COURTY;Léane")
    assert resultat["refus"], "une classe pleine doit refuser l'import"
    assert scalar("SELECT COUNT(*) FROM eleves") == avant


def test_un_doublon_dans_le_fichier_est_signale() -> None:
    from examples.ecole.core.db import init_db

    init_db()
    annee = annee_en_cours()
    resultat = analyser(annee["id"], "6eNEUVE",
                        "COURTY;Léane\nCOURTY;Leane")
    assert len(resultat["erreurs"]) == 2
    assert all("double" in li["erreur"] for li in resultat["erreurs"])


def test_un_code_vide_est_refuse() -> None:
    from examples.ecole.core.db import init_db

    init_db()
    assert analyser(annee_en_cours()["id"], "  ", "A;B")["refus"]

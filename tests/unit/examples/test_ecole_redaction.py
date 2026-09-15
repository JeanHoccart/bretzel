"""La fabrique d'appréciations d'``examples/ecole`` tient ses six règles.

Pourquoi un fichier à part
---------------------------
``core/redaction.py`` est pur : on lui donne ce qu'on sait d'un élève,
elle rend un texte. C'est la partie de l'app la plus dense en règles
métier — EF-E4 à EF-E8, EF-F3, EF-F4 — et la seule qu'on puisse épingler
sans monter quoi que ce soit.

Les tests sont écrits sur les NUANCES, comme ceux des règles
transverses : la limite de 400 caractères est facile, l'ORDRE dans lequel
on coupe ne l'est pas ; un palier de moyenne est facile, le fait qu'il
commence à 13 et pas à 12 est ce que le cahier a payé.
"""

from __future__ import annotations

from examples.ecole.core.redaction import (
    LIMITE,
    MINIMUM_POUR_PARLER,
    bilan,
    choisir_conclusion,
    moins_repetitive,
    palier_de,
    proportion_dite,
    rediger,
    tendance,
)

#: Quatre observations favorables, pour un texte complet.
TOUT_COCHE = {
    "Comportement": ("adopte un comportement exemplaire", 1),
    "Travail": ("travaille avec régularité", 1),
    "Participation": ("participe volontiers", 1),
    "Matériel, ponctualité": ("a toujours son matériel", 1),
}


# ── EF-E7 · les paliers de moyenne ────────────────────────────────────

def test_le_palier_solide_commence_a_treize_et_pas_a_douze() -> None:
    """Le cahier donne la raison du seuil : *« 12 est une moyenne juste
    satisfaisante, pas "solide" »*. C'est la seule borne de cette table
    qui ait été discutée, donc la seule qui mérite un test."""
    assert palier_de(12.0) == "convenables"
    assert palier_de(12.9) == "convenables"
    assert palier_de(13.0) == "solides"


def test_les_quatre_paliers_se_lisent_du_haut_vers_le_bas() -> None:
    assert palier_de(18.0) == "très bons"
    assert palier_de(15.0) == "très bons"
    assert palier_de(9.0) == "convenables"
    assert palier_de(8.9) == "fragiles"


def test_une_moyenne_absente_na_pas_de_palier() -> None:
    """Pas de note n'est pas zéro : un trimestre sans devoir ne vaut pas
    « fragile »."""
    assert palier_de(None) is None


# ── EF-E4 · la limite et l'ordre de sacrifice ─────────────────────────

def test_le_texte_ne_depasse_jamais_la_limite() -> None:
    texte = rediger(trimestre=1, observations=TOUT_COCHE, moyenne=14.0,
                    moyenne_precedente=11.0,
                    competences="Les compétences expérimentales sont "
                                "solidement acquises, en particulier la "
                                "mesure et l'exploitation des résultats.")
    assert len(texte) <= LIMITE


def test_ce_quon_coupe_dabord_est_le_materiel_pas_le_comportement() -> None:
    """**L'ordre de sacrifice EST la règle** (EF-E4) : *jamais le
    travail, jamais le comportement, jamais la conclusion*.

    Un texte qu'on raccourcirait en coupant la phrase la plus longue
    serait plus court et faux — c'est exactement ce que ce test
    interdit.
    """
    long = ("Les compétences expérimentales sont solidement acquises, en "
            "particulier la mesure, l'exploitation des résultats et la "
            "rédaction du compte rendu, ce qui est remarquable à ce niveau.")
    texte = rediger(trimestre=1, observations=TOUT_COCHE, moyenne=14.0,
                    moyenne_precedente=11.0, competences=long)
    assert len(texte) <= LIMITE
    assert "comportement exemplaire" in texte
    assert "régularité" in texte
    # Le matériel est le premier sacrifié, la conclusion n'est jamais
    # touchée.
    assert "matériel" not in texte
    assert texte.rstrip().endswith((".", "…"))


def test_le_noyau_survit_meme_a_une_coupe_maximale() -> None:
    texte = rediger(trimestre=1, observations=TOUT_COCHE, moyenne=5.0,
                    competences="x" * 500)
    assert len(texte) <= LIMITE
    assert "comportement" in texte.lower()


# ── EF-E6 · celle qui répète le moins ─────────────────────────────────

def test_entre_deux_formulations_on_prend_celle_qui_repete_le_moins() -> None:
    """*« C'est ce qui évite "des résultats solides […] un ensemble
    solide". »*"""
    choisie = moins_repetitive(
        ("Un ensemble solide et régulier.", "Une progression nette."),
        "Les résultats sont solides et la régularité est là.",
    )
    assert choisie == "Une progression nette."


def test_a_egalite_la_premiere_lemporte() -> None:
    """Le choix ne doit changer quelque chose que quand il compte :
    sinon, la formulation par défaut reste."""
    assert moins_repetitive(("Alpha.", "Bravo."), "") == "Alpha."


# ── EF-E5 · une formulation par trimestre ─────────────────────────────

def test_le_meme_niveau_ne_donne_pas_la_meme_phrase_aux_trois_trimestres() -> None:
    textes = {
        rediger(trimestre=t, observations={
            "Comportement": ("adopte un comportement exemplaire", 1)},
            moyenne=None)
        for t in (1, 2, 3)
    }
    assert len(textes) == 3, textes


# ── EF-E8 · la conclusion dépend de ce qui domine ─────────────────────

def test_le_comportement_prime_sur_tout_le_reste() -> None:
    assert choisir_conclusion({"Comportement": 4}, "très bons",
                              "hausse") == "comportement"


def test_le_defaut_dorganisation_vient_ensuite() -> None:
    assert choisir_conclusion({"Comportement": 1, "Travail": 3},
                              "solides", "hausse") == "organisation"


def test_puis_la_tendance_entre_trimestres() -> None:
    assert choisir_conclusion({"Comportement": 1}, "solides",
                              "baisse") == "baisse"


def test_et_a_defaut_les_seules_notes() -> None:
    assert choisir_conclusion({}, "très bons", None) == "bon"
    assert choisir_conclusion({}, "fragiles", None) == "faible"


def test_un_ecart_de_bruit_nest_pas_une_tendance() -> None:
    """Deux dixièmes de point ne sont pas « des progrès nets »."""
    assert tendance(12.2, 12.0) == "stable"
    assert tendance(12.6, 12.0) == "hausse"
    assert tendance(11.4, 12.0) == "baisse"
    assert tendance(12.0, None) is None


# ── EF-F3, EF-F4 · le bilan de classe ─────────────────────────────────

def test_une_difficulte_nest_nommee_quau_dela_dune_proportion() -> None:
    assert proportion_dite(0.35) == "plusieurs"
    assert proportion_dite(0.30) == "plusieurs"
    assert proportion_dite(0.20) == "quelques"
    assert proportion_dite(0.10) is None


def test_en_dessous_de_cinq_moyennes_on_ne_parle_pas_de_niveau() -> None:
    """EF-F4 : *« deux fiches sur trente donneraient "la grande
    majorité", ce qui est faux »*."""
    texte = bilan(moyennes=[12.0, 14.0], teintes_par_critere={})
    assert "Trop peu de moyennes" in texte
    assert "moyenne)" not in texte


def test_a_partir_de_cinq_moyennes_le_niveau_se_dit() -> None:
    moyennes = [12.0] * MINIMUM_POUR_PARLER
    texte = bilan(moyennes=moyennes, teintes_par_critere={})
    assert "convenables" in texte


def test_le_bilan_part_de_ce_qui_domine_et_nuance_ensuite() -> None:
    """EF-F2 : *« un bilan de classe se lit en salle des professeurs ; il
    doit être juste sans être accablant »*. La difficulté arrive donc
    APRÈS le constat d'ensemble, jamais en première phrase."""
    texte = bilan(moyennes=[14.0, 15.0, 13.0, 16.0, 7.0, 6.0],
                  teintes_par_critere={})
    phrases = [p for p in texte.split(". ") if p]
    assert "difficulté" not in phrases[0]
    assert "difficulté" in texte

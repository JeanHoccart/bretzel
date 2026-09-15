"""Les règles transverses d'``examples/ecole`` tiennent hors de tout écran.

Pourquoi ces tests-là, et pas d'autres
---------------------------------------
Le cahier des charges de l'app (``.claude/work/ecole-cahier-des-charges.md``)
liste quatorze pièges **mesurés** dans les applications d'origine.
Quatre d'entre eux sont la même faute : une règle métier recalculée dans
un écran, avec une nuance oubliée. Les tests ci-dessous sont donc écrits
sur la nuance, jamais sur le cas facile :

- **piège n° 2** — l'alternance A/B calculée sur les NUMÉROS de semaine
  ISO s'inverse en janvier une année sur cinq. Le test traverse un
  1ᵉʳ janvier ;
- **piège n° 3** — un décompte de séances qui ne déduit pas les vacances
  franchit son seuil deux semaines trop tôt ;
- **RT-4** — un trimestre sans date de fin n'est pas une panne ;
- **RT-1** — une écriture visant une autre année est refusée, et le refus
  LÈVE plutôt que de rendre un booléen qu'on peut oublier de lire.

Le dernier a besoin d'une base, donc d'une fixture — c'est le seul de ce
fichier qui ne soit pas une fonction pure.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from examples.ecole.core.domain import (
    blocs_du_jour,
    competences_de,
    cycle_propose,
    est_jour_de_classe,
    est_un_tp,
    jour_et_date,
    lire_saisie,
    lundi_de,
    niveau_du_code,
    periode_sans_classe,
    periodes_de_travail,
    semaine_ab,
    semaines_touchees,
    sont_de_vraies_vacances,
    trimestre_de,
)

#: Un lundi de rentrée, pris comme référence de semaine A.
LUNDI_REF = date(2026, 8, 31)


# ── RT-5 · l'alternance se compte en jours, pas en numéros ────────────

def test_la_semaine_de_reference_porte_la_lettre_a() -> None:
    assert semaine_ab(LUNDI_REF, LUNDI_REF) == "A"


def test_toute_la_semaine_de_reference_porte_la_lettre_a() -> None:
    """Un mercredi et un samedi sont dans la MÊME semaine que leur lundi."""
    for decalage in range(6):
        assert semaine_ab(LUNDI_REF + timedelta(days=decalage), LUNDI_REF) == "A"


def test_la_semaine_suivante_porte_la_lettre_b() -> None:
    assert semaine_ab(LUNDI_REF + timedelta(days=7), LUNDI_REF) == "B"


def test_lalternance_ne_sinverse_pas_en_janvier() -> None:
    """**Piège n° 2.** Le passage d'année ne doit rien changer.

    La semaine ISO recommence à 1 au 1ᵉʳ janvier, et une année sur cinq
    en compte 53 : un écart calculé sur les numéros inverse alors A et B
    à partir de janvier. Ici on vérifie la seule propriété qui compte —
    deux lundis distants d'un nombre PAIR de semaines portent la même
    lettre — sur trente semaines consécutives, ce qui traverse le
    1ᵉʳ janvier quoi qu'il arrive.
    """
    for semaine in range(30):
        jour = LUNDI_REF + timedelta(weeks=semaine)
        attendu = "A" if semaine % 2 == 0 else "B"
        assert semaine_ab(jour, LUNDI_REF) == attendu, jour


def test_une_semaine_anterieure_a_la_reference_alterne_aussi() -> None:
    """La semaine d'AVANT la référence est une B, pas une A.

    Le cas se produit pour de vrai : la date de référence est un lundi de
    septembre, et la pré-rentrée est la semaine d'avant. Une division
    entière qui tronquerait vers zéro rendrait « A » des deux côtés.
    """
    assert semaine_ab(LUNDI_REF - timedelta(days=7), LUNDI_REF) == "B"
    assert semaine_ab(LUNDI_REF - timedelta(days=14), LUNDI_REF) == "A"


def test_sans_date_de_reference_lalternance_est_indeterminee() -> None:
    """RT-4 : on ne rend pas « A » par défaut, on rend « on ne sait pas »."""
    assert semaine_ab(LUNDI_REF, None) is None


def test_le_lundi_dun_lundi_est_lui_meme() -> None:
    assert lundi_de(LUNDI_REF) == LUNDI_REF


# ── RT-6 · le décompte saute les vacances et les fériés ───────────────

TOUSSAINT = ("Toussaint", date(2026, 10, 24), date(2026, 11, 8))
FERIE = ("Armistice", date(2026, 11, 11), date(2026, 11, 11))
PERIODES = [TOUSSAINT, FERIE]


def test_un_jour_de_vacances_porte_le_nom_de_sa_periode() -> None:
    assert periode_sans_classe(date(2026, 10, 26), PERIODES) == "Toussaint"


def test_les_deux_bornes_sont_incluses() -> None:
    """EF-A5 : début et fin sont le premier et le DERNIER jour sans classe."""
    assert periode_sans_classe(date(2026, 10, 24), PERIODES) == "Toussaint"
    assert periode_sans_classe(date(2026, 11, 8), PERIODES) == "Toussaint"
    assert periode_sans_classe(date(2026, 11, 9), PERIODES) is None


def test_un_jour_ferie_est_une_periode_dun_seul_jour() -> None:
    """Même table, même règle (EF-A4)."""
    assert periode_sans_classe(date(2026, 11, 11), PERIODES) == "Armistice"


def test_un_jour_de_vacances_nest_pas_un_jour_de_classe() -> None:
    """**Piège n° 3.** La grille est un emploi du temps TYPE : elle place
    la classe au lundi sans savoir que ce lundi tombe à la Toussaint."""
    lundi_de_vacances = date(2026, 10, 26)
    assert lundi_de_vacances.weekday() == 0
    assert not est_jour_de_classe(lundi_de_vacances, PERIODES)


def test_le_samedi_est_un_jour_de_classe_et_le_dimanche_non() -> None:
    """La grille va du lundi au SAMEDI (EF-B1)."""
    assert est_jour_de_classe(date(2026, 9, 12), PERIODES)      # samedi
    assert not est_jour_de_classe(date(2026, 9, 13), PERIODES)  # dimanche


# ── RT-4 · une date qui manque n'est pas une panne ────────────────────

FIN_ANNEE = date(2027, 7, 5)


def test_les_trois_trimestres_se_lisent_par_leur_fin_seule() -> None:
    fins = {1: date(2026, 12, 4), 2: date(2027, 3, 12), 3: date(2027, 6, 26)}
    assert trimestre_de(date(2026, 9, 15), fins, FIN_ANNEE) == 1
    assert trimestre_de(date(2026, 12, 4), fins, FIN_ANNEE) == 1
    assert trimestre_de(date(2026, 12, 5), fins, FIN_ANNEE) == 2
    assert trimestre_de(date(2027, 4, 1), fins, FIN_ANNEE) == 3


def test_un_trimestre_sans_fin_court_jusqua_la_fin_de_lannee() -> None:
    """RT-4, dans sa forme la plus courante : en septembre, la date du
    troisième trimestre n'est pas encore connue."""
    fins = {1: date(2026, 12, 4), 2: date(2027, 3, 12), 3: None}
    assert trimestre_de(date(2027, 6, 20), fins, FIN_ANNEE) == 3


def test_un_tableau_de_trimestres_entierement_vide_repond_quand_meme() -> None:
    assert trimestre_de(date(2026, 9, 15), {}, FIN_ANNEE) == 1


def test_une_date_hors_de_lannee_na_pas_de_trimestre() -> None:
    assert trimestre_de(date(2027, 8, 20), {}, FIN_ANNEE) is None


# ── RT-3 · le cycle décide, jamais le code de la classe ───────────────

@pytest.mark.parametrize("code,niveau", [
    ("6e2", "6e"), ("5e1", "5e"), ("4e12", "4e"), ("3e5", "3e"),
    ("2°GT1", "2°GT"), ("1°S1", "1°"), ("T°S2", "T°"),
])
def test_un_code_de_classe_donne_son_niveau(code: str, niveau: str) -> None:
    assert niveau_du_code(code) == niveau


def test_un_code_inconnu_ne_leve_pas() -> None:
    """Un établissement peut nommer une classe autrement ; elle
    n'apparaît alors dans aucune ligne de progression, et c'est tout."""
    assert niveau_du_code("ULIS") == ""


def test_le_cycle_se_propose_depuis_le_niveau() -> None:
    assert cycle_propose("4e") == "college"
    assert cycle_propose("2°GT") == "lycee"
    assert cycle_propose("") == "college"


def test_le_cycle_decide_du_nombre_de_competences() -> None:
    """Sept au collège, cinq au lycée (EF-D3)."""
    assert len(competences_de("college", "TP")) == 7
    assert len(competences_de("lycee", "TP")) == 5


def test_un_devoir_sur_copie_ecarte_ce_qui_ne_se_juge_pas_sur_copie() -> None:
    codes = [c for c, _ in competences_de("college", "DS")]
    assert "REA" not in codes and "AUT" not in codes
    assert "ANA" in codes


# ── EF-A7 · le jour de la semaine précède la date ─────────────────────

def test_le_jour_precede_la_date() -> None:
    assert jour_et_date(date(2026, 10, 16)) == "ven 16/10"


# ── EF-A9, EF-A10 · les périodes de travail ───────────────────────────

RENTREE_2026 = date(2026, 9, 1)
JUIN_2027 = date(2027, 7, 5)


def test_une_semaine_se_compte_en_lundis_touches() -> None:
    """EF-A10 : *« une période qui commence un mardi et finit un vendredi
    occupe la semaine entière dans la tête de celui qui la vit »*.

    Quatre jours divisés par sept donneraient zéro — juste pour une
    calculette, faux pour tout le monde.
    """
    mardi, vendredi = date(2026, 9, 8), date(2026, 9, 11)
    assert (vendredi - mardi).days == 3
    assert semaines_touchees(mardi, vendredi) == 1


def test_une_periode_a_cheval_sur_deux_semaines_en_compte_deux() -> None:
    assert semaines_touchees(date(2026, 9, 11), date(2026, 9, 14)) == 2


def test_seules_les_vraies_vacances_coupent_lannee() -> None:
    """EF-A9 : un férié, un pont, une journée banalisée tombent DANS une
    période de travail — ils ne la coupent pas."""
    assert sont_de_vraies_vacances(date(2026, 10, 24), date(2026, 11, 8))
    assert not sont_de_vraies_vacances(date(2026, 11, 11), date(2026, 11, 11))
    assert not sont_de_vraies_vacances(date(2026, 5, 14), date(2026, 5, 15))


def test_sept_jours_pile_ne_coupent_pas() -> None:
    """La borne, dans le sens où elle mord : sept jours, c'est la semaine
    entière — on est encore dans le même morceau d'année."""
    assert not sont_de_vraies_vacances(date(2026, 10, 24), date(2026, 10, 30))
    assert sont_de_vraies_vacances(date(2026, 10, 24), date(2026, 10, 31))


def test_un_ferie_ne_cree_pas_une_periode_de_travail_de_plus() -> None:
    """Le cœur d'EF-A9, et la faute qu'il ferme : compter toutes les
    lignes de la table donnerait ici quatre périodes au lieu de deux."""
    periodes = [
        ("Toussaint", date(2026, 10, 24), date(2026, 11, 8)),
        ("Armistice", date(2026, 11, 11), date(2026, 11, 11)),
        ("Journée pédagogique", date(2026, 10, 16), date(2026, 10, 16)),
    ]
    morceaux = periodes_de_travail(periodes, RENTREE_2026, JUIN_2027)
    assert [m[0] for m in morceaux] == [1, 2]
    assert morceaux[0][1] == RENTREE_2026
    assert morceaux[0][2] == date(2026, 10, 23)
    assert morceaux[1][1] == date(2026, 11, 9)
    assert morceaux[1][2] == JUIN_2027


def test_une_annee_sans_vacances_est_une_seule_periode() -> None:
    morceaux = periodes_de_travail([], RENTREE_2026, JUIN_2027)
    assert len(morceaux) == 1
    assert morceaux[0][3] == semaines_touchees(RENTREE_2026, JUIN_2027)


def test_les_periodes_se_decoupent_meme_en_desordre() -> None:
    """L'appelant n'a pas à trier : un découpage sur une liste en
    désordre n'a aucun sens, et un appelant qui devrait s'en souvenir
    finit par l'oublier."""
    desordre = [
        ("Février", date(2027, 2, 13), date(2027, 2, 28)),
        ("Toussaint", date(2026, 10, 24), date(2026, 11, 8)),
    ]
    morceaux = periodes_de_travail(desordre, RENTREE_2026, JUIN_2027)
    assert [m[0] for m in morceaux] == [1, 2, 3]
    assert morceaux[1][1] == date(2026, 11, 9)


# ── EF-B7, EF-B8 · lire une case de grille ────────────────────────────

CONNUS = frozenset({"3e4", "4e2", "2°GT2", "6e2"})


def test_ce_qui_suit_le_code_est_une_salle() -> None:
    """**Le piège n° 1**, et c'est le plus cher du cahier : prendre « ce
    qui suit le code » pour une nature a fait disparaître 31 créneaux sur
    43 du cahier de texte le jour où les salles ont été saisies. Le
    défaut est « c'est un cours »."""
    assert lire_saisie("3e4 (L)", CONNUS) == ("3e4", "", "L")
    assert lire_saisie("3e4 - L", CONNUS) == ("3e4", "", "L")
    assert lire_saisie("2°GT2 (134)", CONNUS) == ("2°GT2", "", "134")


def test_seuls_les_mots_de_la_liste_sont_des_natures() -> None:
    assert lire_saisie("4e2 - HVC", CONNUS) == ("4e2", "HVC", "")
    assert lire_saisie("4e2 - HVC - C209", CONNUS) == ("4e2", "HVC", "C209")


def test_le_decoupage_exige_une_classe_deja_existante() -> None:
    """EF-B8 : *un établissement qui nommerait ses classes « 2nde - 4 »
    verrait sinon ses codes amputés sans prévenir*."""
    assert lire_saisie("2nde - 4", CONNUS) == ("2nde - 4", "", "")


def test_un_code_seul_reste_un_code() -> None:
    assert lire_saisie("  6e2  ", CONNUS) == ("6e2", "", "")
    assert lire_saisie("", CONNUS) == ("", "", "")


# ── EF-B9, EF-B10 · les blocs et les TP ───────────────────────────────

#: Les bornes semées : la pause de midi fait 85 minutes, la récréation
#: de l'après-midi 15, et les autres écarts 0 à 5.
BORNES_JOUR = {
    1: ("08:15", "09:10"), 2: ("09:15", "10:10"), 3: ("10:10", "11:05"),
    4: ("11:10", "12:05"), 5: ("13:30", "14:25"), 6: ("14:30", "15:25"),
    7: ("15:40", "16:35"), 8: ("16:40", "17:35"),
}


def case(code: str, nature: str = "", salle: str = "") -> dict:
    return {"code": code, "nature": nature, "salle": salle}


def test_deux_heures_de_suite_font_un_bloc() -> None:
    blocs = blocs_du_jour({1: case("6e2"), 2: case("6e2")}, BORNES_JOUR)
    assert len(blocs) == 1
    assert (blocs[0]["debut"], blocs[0]["fin"]) == (1, 2)


def test_la_recreation_ne_coupe_pas_un_bloc() -> None:
    """Quinze minutes entre la 6ᵉ et la 7ᵉ heure : c'est une récréation,
    et EF-B9 dit qu'elle ne coupe pas."""
    blocs = blocs_du_jour({6: case("3e2"), 7: case("3e2")}, BORNES_JOUR)
    assert len(blocs) == 1


def test_la_pause_de_midi_coupe_un_bloc() -> None:
    """Quatre-vingt-cinq minutes : au-delà de trente, c'est la pause de
    midi, et deux heures de part et d'autre ne sont pas un bloc."""
    blocs = blocs_du_jour({4: case("3e2"), 5: case("3e2")}, BORNES_JOUR)
    assert len(blocs) == 2


def test_une_heure_a_nature_ne_se_fond_pas_dans_le_bloc_voisin() -> None:
    blocs = blocs_du_jour(
        {5: case("4e3"), 6: case("4e3", nature="HVC")}, BORNES_JOUR)
    assert len(blocs) == 2
    assert blocs[1]["nature"] == "HVC"


def test_un_changement_de_salle_ne_coupe_rien_et_les_deux_se_voient() -> None:
    blocs = blocs_du_jour(
        {1: case("6e2", salle="C209"), 2: case("6e2", salle="L")},
        BORNES_JOUR)
    assert len(blocs) == 1
    assert blocs[0]["salles"] == ["C209", "L"]


def test_deux_classes_differentes_ne_se_reunissent_pas() -> None:
    blocs = blocs_du_jour({1: case("6e2"), 2: case("5e1")}, BORNES_JOUR)
    assert len(blocs) == 2


def test_trois_heures_de_suite_font_un_tp() -> None:
    """EF-B10 : rien n'est saisi ni stocké, la règle se LIT dans la
    grille. Et EF-K12 exige qu'il n'y ait qu'une définition dans toute
    l'application — c'est celle-ci."""
    blocs = blocs_du_jour(
        {5: case("3e2"), 6: case("3e2"), 7: case("3e2")}, BORNES_JOUR)
    assert len(blocs) == 1
    assert est_un_tp(blocs[0])


def test_deux_heures_ne_font_pas_un_tp() -> None:
    blocs = blocs_du_jour({1: case("6e2"), 2: case("6e2")}, BORNES_JOUR)
    assert not est_un_tp(blocs[0])


def test_trois_heures_a_nature_ne_font_pas_un_tp() -> None:
    """« Trois HVC de suite » n'est pas un travail pratique."""
    trois = {r: case("4e3", nature="HVC") for r in (5, 6, 7)}
    blocs = blocs_du_jour(trois, BORNES_JOUR)
    assert len(blocs) == 1
    assert not est_un_tp(blocs[0])


# ── RT-1 · la barrière ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def base_semee():
    """La base de l'app, semée une fois. RT-1 se teste sur des données."""
    from examples.ecole.core.db import init_db

    init_db()
    from examples.ecole.features import annees

    return annees


def test_lannee_en_cours_est_unique(base_semee) -> None:
    en_cours = [a for a in base_semee.toutes_les_annees() if a["en_cours"]]
    assert len(en_cours) == 1


def test_ecrire_dans_lannee_en_cours_est_permis(base_semee) -> None:
    base_semee.garde_ecriture(base_semee.annee_en_cours()["id"])


def test_ecrire_dans_une_autre_annee_leve(base_semee) -> None:
    """RT-1 : *« une saisie faite par erreur dans l'année d'avant
    passerait sinon inaperçue »*. Une levée, pas un booléen — un refus
    qu'on peut ignorer en oubliant de lire une valeur de retour n'est pas
    une barrière."""
    autres = [a for a in base_semee.toutes_les_annees() if not a["en_cours"]]
    assert autres, "le jeu semé doit porter une seconde année (RT-1)"
    with pytest.raises(base_semee.AnneeEnConsultationError):
        base_semee.garde_ecriture(autres[0]["id"])


def test_le_seed_porte_les_volumes_annonces() -> None:
    """Le § 13 du cahier annonce des volumes RÉELS, et c'est ce qui charge
    le framework. Un seed qui maigrirait en silence ferait mentir toutes
    les mesures faites dessus.

    ⚠️ **On compte ce que la FABRIQUE produit, pas ce que la base
    contient.** La première version lisait la base semée, et elle a rougi
    dès qu'un probe a tracé une salle : trente-six places au lieu de
    trente. C'est juste — l'app avait bien écrit — et ça ne mesurait plus
    le seed. Une gate qui dépend de l'usage qu'on fait de l'app n'est
    plus une gate.
    """
    from examples.ecole.core.seed import build_seed

    volumes = {table: len(lignes) for table, lignes in build_seed()}
    assert volumes["annees"] == 2
    assert volumes["classes"] == 16
    assert volumes["eleves"] == 473
    assert volumes["inscriptions"] == 473
    assert volumes["horaires"] == 16
    assert volumes["creneaux"] == 54
    assert volumes["salles_plan"] == 25
    assert volumes["places"] == 732
    assert volumes["gabarits_salle"] == 3
    assert volumes["vacances"] == 9
    # EF-E5 : une formulation par niveau ET par trimestre — vingt-quatre
    # niveaux, trois trimestres.
    assert volumes["phrases"] == 72

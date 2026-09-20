"""core/seed — the demonstration set factory. Deterministic.

**Invented names, no real data.** The specification's § 3.3 boundary is
absolute: nothing that lives in the teacher's applications — not a name,
not a photo, not a comment — appears here. The volumes, on the other
hand, are those of their database, measured on 2026-09-12 (§ 13), because
it is the volume that loads the framework and not the plausibility of the
names.

No global ``random``: a local ``Random(GRAINE)``, so two machines get the
same database and an identifier quoted in a test is still the same
tomorrow.

The set is built AROUND today
------------------------------
:data:`RENTREE` is deduced from today's date. The current year therefore
always contains today — without which the week's grid would open on
holidays and the lesson log would propose nothing. ``init_db`` files
:data:`RENTREE` beside the seed's version and rebuilds the database when
it changes: the set renews itself, once a year.

Two accepted departures from § 13, and they are here to be re-read
-------------------------------------------------------------------
1. **Twelve terms, not three.** EF-A3 requires a grid of *three numbers ×
   two cycles* — that is six rows per year, twelve for two. The "3" of
   § 13 counts a single cycle of a single year. The rule wins over the
   inventory.
2. **The checks are not in § 13**, and some are needed: EF-C1 asks for a
   "to review" mark on a class's tile, and an empty column does not show
   the function. Twenty-five are seeded, some already done — EF-H3 says
   nothing is erased.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta

from examples.ecole.core.domain import (
    BORNES,
    COMPETENCES,
    CRITERES,
    NIVEAUX_CRITERE,
    cycle_propose,
    est_jour_de_classe,
    lundi_de,
    niveau_du_code,
    rang_du_niveau,
)

#: Fixed. Change the seed and every identifier changes.
GRAINE = 20260912

#: The calendar year of the current school year. Read once at import.
RENTREE: int = (
    date.today().year if date.today().month >= 8 else date.today().year - 1
)

#: The teacher's timetable, current year: ten classes, two cycles. The
#: label is the one the school prints, the code the one the teacher types
#: into their grid (EF-B6).
CLASSES_EN_COURS: tuple[tuple[str, str, int], ...] = (
    ("6e2", "Sixième 2", 30),
    ("5e1", "Cinquième 1", 29),
    ("5e4", "Cinquième 4", 31),
    ("4e1", "Quatrième 1", 28),
    ("4e3", "Quatrième 3", 30),
    ("3e2", "Troisième 2", 27),
    ("3e5", "Troisième 5", 30),
    ("2°GT1", "Seconde générale 1", 32),
    ("2°GT4", "Seconde générale 4", 31),
    ("T°S2", "Terminale spécialité 2", 32),
)

#: LAST year's timetable. It exists to prove RT-1: it is fully readable
#: and refuses every write.
CLASSES_PASSEES: tuple[tuple[str, str, int], ...] = (
    ("6e1", "Sixième 1", 29),
    ("5e3", "Cinquième 3", 28),
    ("4e2", "Quatrième 2", 30),
    ("3e1", "Troisième 1", 29),
    ("2°GT2", "Seconde générale 2", 28),
    ("1°S1", "Première spécialité 1", 29),
)

#: The current year's typical grid: ``(day, rank, week, code, nature,
#: room)``. Written by hand rather than drawn at random, because it must
#: EXERCISE three rules the acceptance checks on screen:
#:
#: - a **block** of two consecutive hours (Monday s1-s2 in 6e2);
#: - a **practical**, three hours in a row with the same class (Monday
#:   s5-s6-s7 in 3e2; Thursday s2-s3-s4 in 2°GT4). The 15-minute break
#:   between s6 and s7 does not cut the block, the lunch break does
#:   (EF-B9);
#: - a **nature**, which does not merge into the neighbouring block and
#:   does not go to the lesson log (Tuesday s6, ``HVC`` in 4e3).
#:
#: ⚠️ The room is a ROOM, never a nature — that is trap no. 1, and ``L``
#: (the laboratory) is precisely the entry that had made 31 slots out of
#: 43 vanish.
GRILLE_EN_COURS: tuple[tuple[int, int, str, str, str, str], ...] = (
    # lundi
    (0, 1, "A", "6e2", "", "C209"), (0, 2, "A", "6e2", "", "C209"),
    (0, 4, "A", "4e1", "", "C209"),
    (0, 5, "A", "3e2", "", "L"), (0, 6, "A", "3e2", "", "L"),
    (0, 7, "A", "3e2", "", "L"),
    (0, 1, "B", "6e2", "", "C209"), (0, 2, "B", "6e2", "", "C209"),
    (0, 4, "B", "4e1", "", "C209"),
    # mardi
    (1, 1, "A", "5e1", "", "C209"), (1, 2, "A", "5e1", "", "C209"),
    (1, 3, "A", "2°GT1", "", "L"), (1, 4, "A", "2°GT1", "", "L"),
    (1, 5, "A", "4e3", "", "C209"), (1, 6, "A", "4e3", "HVC", ""),
    (1, 1, "B", "5e1", "", "C209"), (1, 2, "B", "5e1", "", "C209"),
    # mercredi
    (2, 1, "A", "3e5", "", "C209"), (2, 2, "A", "3e5", "", "C209"),
    (2, 3, "A", "6e2", "", "C209"),
    (2, 1, "B", "3e5", "", "C209"), (2, 2, "B", "3e5", "", "C209"),
    # jeudi
    (3, 2, "A", "2°GT4", "", "L"), (3, 3, "A", "2°GT4", "", "L"),
    (3, 4, "A", "2°GT4", "", "L"),
    (3, 2, "B", "2°GT4", "", "L"), (3, 3, "B", "2°GT4", "", "L"),
    # vendredi
    (4, 1, "A", "5e4", "", "C209"), (4, 2, "A", "5e4", "", "C209"),
    (4, 5, "A", "T°S2", "", "L"), (4, 6, "A", "T°S2", "", "L"),
    (4, 7, "A", "4e1", "", "C209"),
    (4, 1, "B", "5e4", "", "C209"), (4, 2, "B", "5e4", "", "C209"),
)

#: Last year's grid — shorter, it is only there to be looked at.
GRILLE_PASSEE: tuple[tuple[int, int, str, str, str, str], ...] = (
    (0, 1, "A", "6e1", "", "C209"), (0, 2, "A", "6e1", "", "C209"),
    (0, 4, "A", "4e2", "", "C209"), (0, 5, "A", "4e2", "", "C209"),
    (1, 1, "A", "5e3", "", "C209"), (1, 2, "A", "5e3", "", "C209"),
    (1, 3, "A", "3e1", "", "L"), (1, 4, "A", "3e1", "", "L"),
    (2, 1, "A", "2°GT2", "", "L"), (2, 2, "A", "2°GT2", "", "L"),
    (3, 2, "A", "1°S1", "", "L"), (3, 3, "A", "1°S1", "", "L"),
    (0, 1, "B", "6e1", "", "C209"), (0, 2, "B", "6e1", "", "C209"),
    (1, 1, "B", "5e3", "", "C209"), (1, 2, "B", "5e3", "", "C209"),
    (2, 1, "B", "2°GT2", "", "L"), (2, 2, "B", "2°GT2", "", "L"),
    (3, 2, "B", "1°S1", "", "L"), (3, 3, "B", "1°S1", "", "L"),
)

#: Zone B's four holidays, as day offsets from the start of the school
#: year, then five isolated days — a public holiday, a bridge day, a
#: staff day. **Same table, same rule** (EF-A4): a public holiday is a
#: one-day period, and it is what makes the working periods' blue line
#: cut only on REAL holidays (EF-A9).
VACANCES: tuple[tuple[str, int, int], ...] = (
    ("Toussaint", 54, 69),
    ("Noël", 110, 125),
    ("Février", 166, 181),
    ("Pâques", 222, 237),
    ("Journée pédagogique", 45, 45),
    ("Armistice", 71, 71),
    ("Lundi de Pâques", 245, 245),
    ("Pont de l'Ascension", 267, 268),
    ("Fête du Travail", 242, 242),
)

#: A check's common reasons (EF-H2) — it is set in a single gesture,
#: otherwise it is a note one does not take.
MOTIFS: tuple[str, ...] = (
    "cahier incomplet", "cahier mal tenu", "travail non fait",
    "exercice à refaire", "signature des parents",
)

#: The syllabus chapters, per level. Four to five per level, with their
#: sessions — it is what the progression (EF-L1) and the lesson log
#: (EF-K2) read.
PROGRAMME: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "6e": (
        ("Les états physiques de la matière", (
            "Solide, liquide, gaz", "Les changements d'état",
            "La masse se conserve", "Le volume, lui, varie",
            "Évaluation et correction")),
        ("L'eau dans notre environnement", (
            "Le cycle de l'eau", "Mélanges et solutions",
            "La filtration", "La décantation")),
        ("Les circuits électriques", (
            "La lampe et la pile", "Le circuit en boucle",
            "Conducteurs et isolants", "Le court-circuit",
            "Sécurité électrique")),
        ("Lumière et ombres", (
            "Sources de lumière", "La propagation rectiligne",
            "Ombre propre, ombre portée", "Les phases de la Lune")),
    ),
    "5e": (
        ("Organisation de la matière", (
            "Molécules et atomes", "Les corps purs",
            "Mélanges homogènes", "Les techniques de séparation")),
        ("Circuits en série et en dérivation", (
            "Le circuit en série", "Le circuit en dérivation",
            "L'intensité du courant", "Les mesures à l'ampèremètre")),
        ("La lumière, sources et propagation", (
            "Sources primaires et diffusantes", "La vitesse de la lumière",
            "Les distances dans l'Univers")),
        ("Masse, volume, masse volumique", (
            "Mesurer une masse", "Mesurer un volume",
            "La masse volumique", "Flotte ou coule ?",
            "Travaux pratiques de synthèse")),
    ),
    "4e": (
        ("Les transformations chimiques", (
            "Transformation physique ou chimique ?", "La combustion du carbone",
            "L'équation de réaction", "La conservation des atomes",
            "Les tests d'identification")),
        ("La tension électrique", (
            "La tension aux bornes d'une pile", "Le voltmètre",
            "Tension en série", "Tension en dérivation")),
        ("La lumière et les couleurs", (
            "La décomposition de la lumière blanche",
            "Synthèse additive", "Les filtres colorés")),
        ("Poids et masse", (
            "Distinguer poids et masse", "Le dynamomètre",
            "La relation P = m × g", "Poids sur la Lune")),
    ),
    "3e": (
        ("Les ions et le pH", (
            "La conduction dans les solutions", "Les ions en solution",
            "La mesure du pH", "Acides et bases", "Dilution d'une solution")),
        ("L'énergie et ses conversions", (
            "Les formes d'énergie", "Les chaînes énergétiques",
            "Puissance et énergie", "La facture d'électricité")),
        ("Mouvement et vitesse", (
            "Décrire un mouvement", "Calculer une vitesse",
            "La relativité du mouvement", "Les distances de freinage")),
        ("La gravitation universelle", (
            "L'attraction gravitationnelle", "Le système solaire",
            "Les satellites")),
        ("Les matériaux et leurs propriétés", (
            "Familles de matériaux", "Recyclage et cycle de vie",
            "Les alliages")),
    ),
    "2°GT": (
        ("Constitution de la matière", (
            "L'atome et son noyau", "L'élément chimique",
            "Les ions monoatomiques", "La classification périodique",
            "Les molécules et leurs liaisons", "Évaluation de chapitre")),
        ("Mouvements et interactions", (
            "Le référentiel", "Le vecteur vitesse",
            "Le principe d'inertie", "Les forces et leurs effets")),
        ("Ondes et signaux", (
            "Les lois de la réflexion", "La réfraction",
            "Les lentilles minces", "L'œil et la vision")),
        ("Solutions et concentrations", (
            "Préparer une solution", "La dilution",
            "Le dosage par étalonnage", "Travaux pratiques : loi de Beer")),
    ),
    "1°": (
        ("Suivi d'une transformation", (
            "L'avancement d'une réaction", "Le réactif limitant",
            "Le titrage colorimétrique", "Exploitation d'un dosage")),
        ("Les forces et le travail", (
            "Le travail d'une force", "L'énergie cinétique",
            "L'énergie potentielle", "Le théorème de l'énergie cinétique")),
        ("Ondes mécaniques", (
            "La périodicité d'une onde", "Longueur d'onde et célérité",
            "Les ondes sonores", "Le niveau d'intensité sonore")),
        ("Structure des entités organiques", (
            "Les groupes caractéristiques", "Les familles fonctionnelles",
            "La spectroscopie infrarouge")),
    ),
    "T°": (
        ("Cinétique et catalyse", (
            "Le suivi temporel", "Le temps de demi-réaction",
            "Les facteurs cinétiques", "La catalyse")),
        ("Les équilibres chimiques", (
            "Le quotient de réaction", "La constante d'équilibre",
            "Les titrages pH-métriques", "Les solutions tampons")),
        ("Mouvement dans un champ", (
            "La deuxième loi de Newton", "Le mouvement dans un champ uniforme",
            "Le mouvement des satellites", "Les lois de Kepler")),
        ("La modélisation de l'évolution", (
            "Les équations différentielles", "La méthode d'Euler",
            "Les oscillateurs mécaniques", "La résolution numérique",
            "Travaux pratiques de synthèse")),
    ),
}

_PRENOMS: tuple[str, ...] = (
    "Léane", "Malo", "Anaïs", "Timéo", "Jeanne", "Sacha", "Maëlle", "Ilan",
    "Romane", "Aymeric", "Solène", "Nolan", "Capucine", "Ewen", "Lilou",
    "Baptiste", "Océane", "Corentin", "Ambre", "Gaspard", "Noémie", "Tristan",
    "Éline", "Maxence", "Faustine", "Léandre", "Sidonie", "Aurélien",
    "Perrine", "Kilian", "Garance", "Marceau", "Héloïse", "Swann", "Clémence",
    "Titouan", "Alix", "Naël", "Élisa", "Brice", "Maïwenn", "Loris",
    "Séverine", "Yoann", "Coline", "Melvin", "Apolline", "Eliott", "Tiphaine",
    "Arthus", "Nine", "Jonas", "Lise", "Aurèle", "Maud", "Ronan", "Flavie",
    "Damien", "Josselin", "Marine",
)

_NOMS: tuple[str, ...] = (
    "Courty", "Vallois", "Delahaye", "Brémont", "Lachaud", "Perceval",
    "Mazière", "Gourvennec", "Tissier", "Beaulieu", "Roquefort", "Malandain",
    "Verdier", "Cazaux", "Lhermitte", "Paumier", "Dreyfus", "Bonnefoy",
    "Sauvage", "Trémoulet", "Vasseur", "Quilliot", "Lestrade", "Arnoux",
    "Feuillade", "Combarieu", "Nadaud", "Salvat", "Ferrandin", "Bourguignon",
    "Léotard", "Chastel", "Kerjean", "Mounier", "Tavernier", "Ruaud",
    "Delpech", "Ambroise", "Vignal", "Sarrazin", "Hautefeuille", "Loiselle",
    "Béranger", "Mortier", "Cassagne", "Ginestet", "Pouliquen", "Valadon",
    "Escoffier", "Thibaudeau",
)

_PROFS: tuple[str, ...] = (
    "Mme Ferrandin", "M. Kerjean", "Mme Valadon", "M. Delpech",
    "Mme Bonnefoy", "M. Arnoux", "Mme Sarrazin", "M. Mounier",
)

_PRECISIONS: tuple[str, ...] = (
    "suit une rééducation orthophonique",
    "à placer près du tableau",
    "dispense partielle d'EPS",
    "tiers-temps aux évaluations",
    "arrivé en cours d'année",
)

_NOMS_EVAL: tuple[str, ...] = (
    "Contrôle n°1", "Contrôle n°2", "Interrogation rapide",
    "TP noté : mesures", "Devoir maison", "Oral de restitution",
    "Bilan de chapitre", "Évaluation de fin de trimestre",
)

_GABARITS: tuple[tuple[str, list[int], list[int], int], ...] = (
    ("Salle standard C209", [6, 6, 6, 6, 6], [2, 4], 60),
    ("Laboratoire L (îlots)", [4, 4, 4, 4], [2], 100),
    ("Petite salle 134", [5, 5, 5, 4], [3], 50),
)


def iso(jour: date) -> str:
    """A date in ISO — the format stored everywhere in this database."""
    return jour.isoformat()


def build_seed() -> list[tuple[str, list[tuple]]]:
    """``[(table, rows), …]`` in the order the foreign keys require. A
    single function, called once."""
    rng = random.Random(GRAINE)

    debut_en_cours = date(RENTREE, 9, 1)
    fin_en_cours = date(RENTREE + 1, 7, 5)
    debut_passee = date(RENTREE - 1, 9, 1)
    fin_passee = date(RENTREE, 7, 5)

    # ── Years ────────────────────────────────────────────────────────
    #
    # ``lundi_ref`` is the MONDAY of the first week of term, and it is
    # the anchor of the whole alternation (RT-5). Last year carries one
    # too: without it its grid would return "we do not know", which is
    # correct but shows nothing.
    annees = [
        (1, f"{RENTREE}-{RENTREE + 1}", iso(debut_en_cours),
         iso(fin_en_cours), 1, iso(lundi_de(debut_en_cours))),
        (2, f"{RENTREE - 1}-{RENTREE}", iso(debut_passee),
         iso(fin_passee), 0, iso(lundi_de(debut_passee))),
    ]

    # ── Classes ──────────────────────────────────────────────────────
    classes: list[tuple] = []
    par_code: dict[tuple[int, str], int] = {}
    effectifs: dict[int, int] = {}
    for annee_id, service in ((1, CLASSES_EN_COURS), (2, CLASSES_PASSEES)):
        for rang, (code, libelle, effectif) in enumerate(service):
            classe_id = len(classes) + 1
            niveau = niveau_du_code(code)
            classes.append((
                classe_id, annee_id, code, libelle, cycle_propose(niveau),
                niveau, rang_du_niveau(niveau) * 10 + rang,
                _PROFS[rang % len(_PROFS)],
            ))
            par_code[(annee_id, code)] = classe_id
            effectifs[classe_id] = effectif

    # ── Pupils and enrolments ────────────────────────────────────────
    #
    # One enrolment per pupil: nobody changes class in the seeded set.
    # The movements (EF-C5) are batch 4; what the schema must prove here
    # is that a pupil IS NOT in a class — they are ENROLLED in it, on a
    # date (RT-2).
    eleves: list[tuple] = []
    inscriptions: list[tuple] = []
    eleves_de: dict[int, list[int]] = {}
    for classe_id, annee_id, code, *_ in classes:
        debut = debut_en_cours if annee_id == 1 else debut_passee
        eleves_de[classe_id] = []
        for _ in range(effectifs[classe_id]):
            eleve_id = len(eleves) + 1
            amenagement = (
                rng.choice(("PAP", "PPS", "PAI", "PPRE"))
                if rng.random() < 0.08 else ""
            )
            eleves.append((
                eleve_id,
                rng.choice(_NOMS),
                rng.choice(_PRENOMS),
                iso(date(RENTREE - 11 - rang_du_niveau(niveau_du_code(code)),
                         rng.randint(1, 12), rng.randint(1, 28))),
                "",                                   # photo : initiales
                amenagement,
                1 if rng.random() < 0.06 else 0,      # vue fragile
                1 if rng.random() < 0.11 else 0,      # gaucher
                rng.choice(_PRECISIONS) if rng.random() < 0.07 else "",
            ))
            eleves_de[classe_id].append(eleve_id)
            inscriptions.append((
                len(inscriptions) + 1, eleve_id, classe_id, iso(debut), None,
                # The practical half-group only exists at lycée
                # (EF-G12): at collège the class comes whole.
                (len(eleves_de[classe_id]) % 2) + 1
                if code[0] in "21T" else None,
            ))

    # ── Horaires et grille ───────────────────────────────────────────
    horaires: list[tuple] = []
    horaire_de: dict[tuple[int, int], int] = {}
    for annee_id in (1, 2):
        for rang, (debut_h, fin_h) in enumerate(BORNES, start=1):
            horaires.append((len(horaires) + 1, annee_id, rang, debut_h, fin_h))
            horaire_de[(annee_id, rang)] = len(horaires)

    creneaux: list[tuple] = []
    for annee_id, grille in ((1, GRILLE_EN_COURS), (2, GRILLE_PASSEE)):
        for jour, rang, semaine, code, nature, salle in grille:
            creneaux.append((
                len(creneaux) + 1, annee_id, jour, horaire_de[(annee_id, rang)],
                semaine, par_code[(annee_id, code)], nature, salle,
            ))

    # Two exceptional hours on the current year: one EXTRA hour (on a
    # FREE cell) and one CANCELLATION (on an OCCUPIED cell). It is the
    # only way of showing EF-B11's rule — a free cell offers only an
    # addition, an occupied cell only a cancellation — on a
    # freshly-seeded database.
    #
    # ⚠️ **Both dates are chosen so as to break no block**, and it is not
    # cosmetic. The first version put them sixteen days after the start
    # of term, on rank 3 of a Thursday: they fell in the MIDDLE of
    # 2°GT4's practical (s2-s3-s4) and cut it in two. The behaviour was
    # correct — an exception wins over the typical grid — but the seeded
    # set then showed only one of the two practicals it claims to set,
    # and it was the probe that saw it.
    lundi_5 = lundi_de(debut_en_cours) + timedelta(weeks=5)
    exceptionnelles = [
        # Tuesday, last hour: free in both weeks.
        (1, 1, iso(lundi_5 + timedelta(days=1)), horaire_de[(1, 8)],
         par_code[(1, "4e1")], "C209"),
        # Monday of the following week, first hour: 6e2 is there in
        # BOTH weeks, so the cancellation is sure to show.
        (2, 1, iso(lundi_5 + timedelta(weeks=1)), horaire_de[(1, 1)],
         None, ""),
    ]

    # ── Terms and holidays ───────────────────────────────────────────
    #
    # The ends differ PER CYCLE: at lycée the first term ends earlier
    # (RT-3). The current year's third is left EMPTY — an empty cell is
    # normal (RT-4), and it is the real state of a database in
    # September.
    trimestres: list[tuple] = []
    fins = {
        "college": (95, 195),
        "lycee": (88, 188),
    }
    for annee_id, depart, fin_annee in ((1, debut_en_cours, fin_en_cours),
                                        (2, debut_passee, fin_passee)):
        for cycle, (t1, t2) in fins.items():
            for numero, decalage in ((1, t1), (2, t2), (3, None)):
                fin = None if decalage is None else iso(
                    depart + timedelta(days=decalage))
                if numero == 3 and annee_id == 2:
                    fin = iso(fin_annee - timedelta(days=28))
                trimestres.append(
                    (len(trimestres) + 1, annee_id, cycle, numero, fin))

    vacances = [
        (i + 1, 1, libelle, iso(debut_en_cours + timedelta(days=d)),
         iso(debut_en_cours + timedelta(days=f)))
        for i, (libelle, d, f) in enumerate(VACANCES)
    ]
    periodes = [
        (libelle, debut_en_cours + timedelta(days=d),
         debut_en_cours + timedelta(days=f))
        for libelle, d, f in VACANCES
    ]

    # ── Skills ───────────────────────────────────────────────────────
    competences: list[tuple] = []
    comp_de: dict[tuple[str, str], int] = {}
    for cycle, liste in COMPETENCES.items():
        for rang, (code, libelle) in enumerate(liste, start=1):
            competences.append(
                (len(competences) + 1, cycle, code, libelle, rang))
            comp_de[(cycle, code)] = len(competences)

    # ── Observation criteria ─────────────────────────────────────────
    criteres: list[tuple] = []
    niveaux_critere: list[tuple] = []
    niveaux_de: dict[str, list[int]] = {}
    for rang, libelle in enumerate(CRITERES, start=1):
        criteres.append((rang, rang, libelle))
        niveaux_de[libelle] = []
        for n_rang, court, long_, teinte in NIVEAUX_CRITERE[libelle]:
            niveaux_critere.append((
                len(niveaux_critere) + 1, rang, n_rang, court, long_, teinte))
            niveaux_de[libelle].append(len(niveaux_critere))

    # ── Assessments, marks, corrections ──────────────────────────────
    #
    # Forty assessments, about thirty marks each: it is the volume that
    # makes batch 5's bulk entry realistic.
    # ── EF-E5's sentences ────────────────────────────────────────────
    #
    # One wording PER TERM for each level: *"the same observation does
    # not give the same sentence in the first and the third"*. The
    # level's long label is the CORE; it is `core/redaction.py`'s factory
    # that sets it inside the term's frame. Writing seventy-two whole
    # sentences by hand here would make them diverge from the frames at
    # the first touch-up.
    phrases: list[tuple] = []
    for libelle, ids in niveaux_de.items():
        for position, niveau_id in enumerate(ids):
            long = NIVEAUX_CRITERE[libelle][position][2]
            for trimestre in (1, 2, 3):
                phrases.append(
                    (len(phrases) + 1, niveau_id, trimestre, long))

    evaluations: list[tuple] = []
    notes: list[tuple] = []
    corrections: list[tuple] = []
    for classe_id, annee_id, *_ in classes:
        depart = debut_en_cours if annee_id == 1 else debut_passee
        combien = 3 if annee_id == 1 else 1
        if annee_id == 1 and classe_id % 3 == 0:
            combien = 4
        for i in range(combien):
            eval_id = len(evaluations) + 1
            trimestre = min(3, i + 1)
            jour = depart + timedelta(days=25 + i * 55)
            bareme = float(rng.choice((10, 20, 20, 20, 40)))
            evaluations.append((
                eval_id, classe_id, trimestre,
                _NOMS_EVAL[(eval_id - 1) % len(_NOMS_EVAL)],
                rng.choice(("DS", "IE", "TP", "Maison")),
                iso(jour), bareme, float(rng.choice((1, 1, 2, 3))),
                iso(jour + timedelta(days=6)) if i == 0 else None,
                None,
            ))
            for eleve_id in eleves_de[classe_id]:
                absent = 1 if rng.random() < 0.04 else 0
                valeur = None if absent else round(
                    min(bareme, max(0.0, rng.gauss(bareme * 0.62,
                                                   bareme * 0.17))), 1)
                notes.append(
                    (len(notes) + 1, eval_id, eleve_id, absent, valeur))
        # One correction to report per batch of five classes: the list
        # is only cleared when the teacher says they have done it
        # (EF-D8), so it must exist before the first screen.
        if annee_id == 1 and classe_id % 5 == 0:
            corrections.append((
                len(corrections) + 1, evaluations[-1][0],
                eleves_de[classe_id][0], 8.0, 11.5,
                iso(date.today() - timedelta(days=2)),
            ))

    # ── Observation sheets ───────────────────────────────────────────
    #
    # Every class of the current year in the first term, plus about a
    # hundred pupils of last year in the third: ~400 sheets, and two
    # different terms so the selector means something.
    fiches: list[tuple] = []
    fiches_niveaux: list[tuple] = []

    def poser_fiche(eleve_id: int, classe_id: int, trimestre: int) -> None:
        fiche_id = len(fiches) + 1
        fiches.append((fiche_id, eleve_id, classe_id, trimestre, "", 0))
        for rang, libelle in enumerate(CRITERES, start=1):
            choix = niveaux_de[libelle]
            # Weighted towards the favourable ranks: a class where half
            # the pupils "disrupt the lesson" looks like nothing and
            # would skew batch 6's summary.
            place = min(len(choix) - 1, int(abs(rng.gauss(0, 1.6))))
            fiches_niveaux.append((fiche_id, rang, choix[place]))

    reste = 100
    for classe_id, annee_id, *_ in classes:
        for eleve_id in eleves_de[classe_id]:
            if annee_id == 1:
                poser_fiche(eleve_id, classe_id, 1)
            elif reste > 0:
                poser_fiche(eleve_id, classe_id, 3)
                reste -= 1

    # ── Seating plan ─────────────────────────────────────────────────
    #
    # Twenty-five rooms for sixteen classes: nine classes have two
    # (EF-G11 — a class taught in two rooms has two plans). Seven rooms
    # of thirty seats and eighteen of twenty-nine make § 13's 732 seats.
    salles: list[tuple] = []
    places: list[tuple] = []
    separations: list[tuple] = []
    devants: list[tuple] = []
    for indice, (classe_id, *_) in enumerate(classes):
        combien = 2 if indice < 9 else 1
        for ordre in range(combien):
            salle_id = len(salles) + 1
            salles.append((
                salle_id, classe_id,
                "C209" if ordre == 0 else "Laboratoire L", ordre, None, 0,
            ))
            longueurs = [6, 6, 6, 6, 6] if salle_id <= 7 else [6, 6, 6, 6, 5]
            assis = list(eleves_de[classe_id]) if ordre == 0 else []
            for rangee, longueur in enumerate(longueurs, start=1):
                for colonne in range(1, longueur + 1):
                    places.append((
                        len(places) + 1, salle_id, rangee, colonne,
                        assis.pop(0) if assis else None,
                        1 if colonne % 2 == 1 else 0,
                        # An aisle is a CORRIDOR: the same column on
                        # every row (EF-G4, trap no. 6), never in front
                        # of the first seat (EF-G5).
                        60 if colonne in (3, 5) else 0,
                    ))
        # The constraints are attached to the CLASS (EF-G10).
        liste = eleves_de[classe_id]
        if len(liste) >= 4:
            separations.append(
                (len(separations) + 1, classe_id, liste[0], liste[1]))
        for eleve_id in liste:
            indice_eleve = eleve_id - 1
            if eleves[indice_eleve][5] or eleves[indice_eleve][6]:
                devants.append((len(devants) + 1, classe_id, eleve_id))

    gabarits = [
        (i + 1, nom, json.dumps(rangees), json.dumps(allees), largeur)
        for i, (nom, rangees, allees, largeur) in enumerate(_GABARITS)
    ]

    # ── Checks ───────────────────────────────────────────────────────
    verifications: list[tuple] = []
    for classe_id, annee_id, *_ in classes:
        if annee_id != 1:
            continue
        for i in range(rng.randint(1, 4)):
            eleve_id = rng.choice(eleves_de[classe_id])
            pose = date.today() - timedelta(days=rng.randint(1, 20))
            verifications.append((
                len(verifications) + 1, eleve_id, classe_id,
                rng.choice(MOTIFS), iso(pose),
                iso(pose + timedelta(days=2)) if i % 3 == 2 else None,
            ))

    # ── Chapters, sessions, lesson log, session sheets ───────────────
    chapitres: list[tuple] = []
    seances: list[tuple] = []
    seances_de: dict[int, list[tuple[int, str]]] = {}
    for niveau, liste in PROGRAMME.items():
        for rang, (titre, titres_seances) in enumerate(liste, start=1):
            chapitre_id = len(chapitres) + 1
            chapitres.append((chapitre_id, niveau, titre, rang))
            seances_de[chapitre_id] = []
            for numero, titre_seance in enumerate(titres_seances, start=1):
                seances.append(
                    (len(seances) + 1, chapitre_id, numero, titre_seance))
                seances_de[chapitre_id].append((numero, titre_seance))

    chapitres_de_niveau: dict[str, list[int]] = {}
    for chapitre_id, niveau, *_ in chapitres:
        chapitres_de_niveau.setdefault(niveau, []).append(chapitre_id)

    # The entries go back from the start of term to today, day by day,
    # skipping holidays and public holidays (RT-6). An hour with a
    # NATURE has no session to record (EF-K7) — so it does not enter.
    cahier: list[tuple] = []
    creneaux_par_jour: dict[tuple[int, str], list[tuple]] = {}
    for _id, annee_id, jour_semaine, _h, semaine, classe_id, nature, _s in creneaux:
        if annee_id != 1 or nature:
            continue
        creneaux_par_jour.setdefault((jour_semaine, semaine), []).append(
            (classe_id,))

    lundi_ref = lundi_de(debut_en_cours)
    avancement: dict[int, int] = {}
    jour = debut_en_cours
    aujourdhui = date.today()
    while jour <= aujourdhui and len(cahier) < 150:
        if est_jour_de_classe(jour, periodes):
            ecart = (lundi_de(jour) - lundi_ref).days // 7
            semaine = "A" if ecart % 2 == 0 else "B"
            vus: set[int] = set()
            for (classe_id,) in creneaux_par_jour.get(
                    (jour.weekday(), semaine), ()):
                if classe_id in vus:
                    continue
                vus.add(classe_id)
                niveau = classes[classe_id - 1][5]
                liste = chapitres_de_niveau.get(niveau, [])
                if not liste:
                    continue
                rang = avancement.get(classe_id, 0)
                chapitre_id = liste[(rang // 4) % len(liste)]
                numero, titre = seances_de[chapitre_id][
                    rang % len(seances_de[chapitre_id])]
                avancement[classe_id] = rang + 1
                cahier.append((
                    len(cahier) + 1, classe_id, iso(jour), chapitre_id,
                    numero, titre,
                    f"Séance {numero} : {titre}.",
                    "Terminer les exercices du cahier." if numero % 2 else "",
                    iso(jour + timedelta(days=1)) if numero % 3 else None,
                ))
        jour += timedelta(days=1)

    # EF-M3: the sheet is attached by TITLE, never by number.
    fiches_seance: list[tuple] = []
    notes_fiche: list[tuple] = []
    for chapitre_id, _niveau, titre, _rang in chapitres[:40]:
        numero, titre_seance = seances_de[chapitre_id][0]
        fiche_id = len(fiches_seance) + 1
        fiches_seance.append((
            fiche_id, chapitre_id, titre_seance,
            f"Introduction du chapitre « {titre} ». Compter 15 minutes "
            f"de mise en route.",
        ))
        notes_fiche.append((
            len(notes_fiche) + 1, fiche_id, "preparer",
            "Sortir le matériel la veille.",
            iso(debut_en_cours + timedelta(days=chapitre_id)),
        ))
        if chapitre_id % 2 == 0:
            notes_fiche.append((
                len(notes_fiche) + 1, fiche_id, "reflexions",
                "Trop long de dix minutes ; couper la deuxième activité.",
                iso(debut_en_cours + timedelta(days=chapitre_id + 30)),
            ))

    return [
        ("annees", annees),
        ("classes", classes),
        ("eleves", eleves),
        ("inscriptions", inscriptions),
        ("horaires", horaires),
        ("creneaux", creneaux),
        ("heures_exceptionnelles", exceptionnelles),
        ("trimestres", trimestres),
        ("vacances", vacances),
        ("competences", competences),
        ("criteres", criteres),
        ("niveaux_critere", niveaux_critere),
        ("phrases", phrases),
        ("evaluations", evaluations),
        ("notes", notes),
        ("corrections_a_reporter", corrections),
        ("fiches", fiches),
        ("fiches_niveaux", fiches_niveaux),
        ("salles_plan", salles),
        ("places", places),
        ("separations", separations),
        ("devants", devants),
        ("gabarits_salle", gabarits),
        ("verifications", verifications),
        ("chapitres", chapitres),
        ("seances_chapitre", seances),
        ("cahier", cahier),
        ("fiches_seance", fiches_seance),
        ("notes_fiche", notes_fiche),
    ]

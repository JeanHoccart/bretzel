"""core/domain — le vocabulaire métier et les huit règles transverses.

Aucun import de ``bretzel`` ici, et c'est délibéré : ce module est la
partie de l'app qu'on peut relire sans rien savoir du framework. Il
porte le § 4 (glossaire) et le § 6 (règles transverses) du cahier des
charges, et rien d'autre.

**Pourquoi les règles vivent ici et pas dans les écrans.** RT-8 dit
qu'une règle métier tient *quel que soit l'écran*. Une règle écrite dans
un écran est une règle qu'un second écran redécouvrira de travers — le
cahier documente quatorze pièges payés dans l'application d'origine, et
quatre d'entre eux (n° 1, 2, 3, 4) sont exactement cela : une règle
recalculée sur place, avec une nuance oubliée.

Les cinq règles calculatoires sont ici, chacune en une fonction :

=====  =====================================================  =====================
règle  ce qu'elle dit                                         la fonction
=====  =====================================================  =====================
RT-3   le CYCLE décide, jamais le code de la classe           :func:`cycle_propose`
RT-4   une date qui manque n'est pas une panne                :func:`trimestre_de`
RT-5   l'alternance A/B se compte en JOURS entre deux lundis  :func:`semaine_ab`
RT-6   le décompte saute les vacances et les fériés           :func:`periode_sans_classe`
EF-L3  un niveau rapproche une classe d'un chapitre           :func:`niveau_du_code`
=====  =====================================================  =====================

RT-1 (l'année en cours est la seule qu'on écrit) et RT-2 (rien ne
s'efface qui porte de l'histoire) ne sont pas des calculs : la première
est une garde, elle vit dans ``features/annees.py`` ; la seconde est une
forme de schéma — une inscription DATÉE plutôt qu'une ligne qu'on
supprime — et elle vit dans ``core/db.py``.

RT-7 (ce qui est proposé n'est jamais imposé) et RT-8 (une règle tient
quel que soit l'écran) sont des règles de conception : elles ne
s'écrivent pas, elles se tiennent.
"""

from __future__ import annotations

from datetime import date, timedelta

# ── Le glossaire, en constantes ───────────────────────────────────────

#: Les deux cycles. Ils décident du nombre de compétences, des dates de
#: trimestre et de ce qu'on propose à l'écran (RT-3).
CYCLES: dict[str, str] = {"college": "Collège", "lycee": "Lycée"}

#: Les niveaux, dans l'ordre de la progression. C'est aussi l'ordre de
#: tri : ``NIVEAUX.index(niveau)`` est le rang.
#:
#: ⚠️ Ils sont écrits comme le professeur écrit ses codes de classe —
#: « 2°GT2 », « 1°S1 » — parce que :func:`niveau_du_code` les reconnaît
#: par PRÉFIXE (EF-L3). Une table qui dirait « seconde » ne rapprocherait
#: rien.
NIVEAUX: tuple[str, ...] = ("6e", "5e", "4e", "3e", "2°GT", "1°", "T°")

#: Le cycle de chaque niveau. Sert UNE fois — à la création d'une classe
#: (cf. :func:`cycle_propose`). Ce n'est pas un chemin de lecture.
CYCLE_DU_NIVEAU: dict[str, str] = {
    "6e": "college", "5e": "college", "4e": "college", "3e": "college",
    "2°GT": "lycee", "1°": "lycee", "T°": "lycee",
}

#: Les compétences évaluées, par cycle : sept au collège, cinq au lycée
#: (EF-D3). Le nombre vient du CYCLE, jamais du code de la classe.
COMPETENCES: dict[str, tuple[tuple[str, str], ...]] = {
    "college": (
        ("APP", "S'approprier"),
        ("ANA", "Analyser / Raisonner"),
        ("REA", "Réaliser"),
        ("VAL", "Valider"),
        ("COM", "Communiquer"),
        ("AUT", "Être autonome, faire preuve d'initiative"),
        ("DEM", "Pratiquer une démarche scientifique"),
    ),
    "lycee": (
        ("APP", "S'approprier"),
        ("ANA", "Analyser / Raisonner"),
        ("REA", "Réaliser"),
        ("VAL", "Valider"),
        ("COM", "Communiquer"),
    ),
}

#: Les compétences qui ne se jugent PAS sur une copie (EF-D3). Un devoir
#: sur table ne peut pas évaluer le geste au poste de travail.
HORS_COPIE: frozenset[str] = frozenset({"REA", "AUT"})

#: Les types d'évaluation.
TYPES_EVALUATION: tuple[str, ...] = ("DS", "IE", "TP", "Oral", "Projet",
                                     "Maison")

#: Ceux qui se font sur copie, et qui écartent donc :data:`HORS_COPIE`.
TYPES_SUR_COPIE: frozenset[str] = frozenset({"DS", "IE", "Maison"})

#: Les NATURES — ce qui fait qu'une heure n'est pas un cours. La liste
#: est fermée, et c'est tout le piège n° 1 : **tout ce qui n'est pas
#: là-dedans est une SALLE** (EF-B7). L'inverse a fait disparaître 31
#: créneaux sur 43 du cahier de texte le jour où les salles ont été
#: saisies.
NATURES: tuple[str, ...] = ("HVC",)

#: Les aménagements d'un élève (EF-C4).
AMENAGEMENTS: tuple[str, ...] = ("PAP", "PPS", "PAI", "PPRE")

#: Les six jours de la grille, du lundi au samedi (EF-B1). L'index dans
#: ce tuple EST le numéro de jour stocké — ``date.weekday()`` donne le
#: même, ce qui évite une table de correspondance.
JOURS: tuple[str, ...] = ("lundi", "mardi", "mercredi", "jeudi",
                          "vendredi", "samedi")

#: Les trois lettres du jour, pour « ven 16/10 » (EF-A7).
JOURS_COURTS: tuple[str, ...] = ("lun", "mar", "mer", "jeu", "ven", "sam",
                                 "dim")

#: Les huit bornes d'une journée, en heures de 55 minutes. Ce sont les
#: valeurs SEMÉES : elles se règlent ensuite pour toute l'année dans la
#: première colonne de la grille (EF-B3).
#:
#: ⚠️ Les cours ne commencent pas à l'heure ronde. Quatre départs cités
#: par le cahier — 10 h 10, 11 h 10, 13 h 30, 15 h 40 — sont ici tels
#: quels : une table arrondie rendrait la grille fausse à l'œil du seul
#: qui la connaisse par cœur.
BORNES: tuple[tuple[str, str], ...] = (
    ("08:15", "09:10"),
    ("09:15", "10:10"),
    ("10:10", "11:05"),
    ("11:10", "12:05"),
    ("13:30", "14:25"),
    ("14:30", "15:25"),
    ("15:40", "16:35"),
    ("16:40", "17:35"),
)

#: Les quatre vacances de la zone B, dans l'ordre de l'année. L'écran
#: des réglages les PROPOSE, remplies ou non, **sans créer de lignes
#: vides à l'avance** (EF-A4) : une proposition est une ligne à l'écran,
#: pas une ligne en base.
VACANCES_ZONE_B: tuple[str, ...] = ("Toussaint", "Noël", "Février",
                                    "Pâques")

#: Les quatre critères d'observation, dans l'ordre du bulletin (§ 5.3).
CRITERES: tuple[str, ...] = ("Comportement", "Travail", "Participation",
                             "Matériel, ponctualité")

#: Les niveaux de chaque critère : ``(rang, court, long, teinte)``.
#: Rang 1 = le plus favorable. La teinte va de 1 à 4 — 1-2 favorable ou
#: neutre, 3-4 signale une difficulté (EF-E1).
#:
#: Sept pour Comportement et Travail, six pour Participation, quatre
#: pour Matériel : les comptes viennent du cahier, pas d'une symétrie.
NIVEAUX_CRITERE: dict[str, tuple[tuple[int, str, str, int], ...]] = {
    "Comportement": (
        (1, "Exemplaire", "adopte un comportement exemplaire", 1),
        (2, "Très bon", "se comporte très bien en cours", 1),
        (3, "Correct", "a un comportement correct", 2),
        (4, "Inégal", "a un comportement inégal selon les séances", 2),
        (5, "Bavard", "se laisse souvent aller au bavardage", 3),
        (6, "Perturbateur", "perturbe le déroulement du cours", 4),
        (7, "Inacceptable", "adopte une attitude inacceptable en classe", 4),
    ),
    "Travail": (
        (1, "Très soutenu", "fournit un travail très soutenu", 1),
        (2, "Régulier", "travaille avec régularité", 1),
        (3, "Correct", "fournit un travail correct", 2),
        (4, "Irrégulier", "fournit un travail irrégulier", 2),
        (5, "Insuffisant", "fournit un travail insuffisant", 3),
        (6, "Très faible", "ne fournit presque aucun travail personnel", 4),
        (7, "Nul", "ne travaille pas", 4),
    ),
    "Participation": (
        (1, "Très active", "participe très activement à l'oral", 1),
        (2, "Active", "participe volontiers", 1),
        (3, "Correcte", "participe correctement", 2),
        (4, "Discrète", "reste discret à l'oral", 2),
        (5, "Passive", "reste passif pendant les séances", 3),
        (6, "Absente", "ne participe jamais", 4),
    ),
    "Matériel, ponctualité": (
        (1, "Impeccable", "a toujours son matériel et arrive à l'heure", 1),
        (2, "Correct", "a le plus souvent son matériel", 2),
        (3, "Oublis", "oublie fréquemment son matériel", 3),
        (4, "Récurrent", "vient sans matériel et arrive en retard", 4),
    ),
}


# ── RT-3 · Le cycle décide, jamais le code de la classe ───────────────

def niveau_du_code(code: str) -> str:
    """Le niveau qu'un code de classe désigne — « 3e1 » → « 3e ».

    **L'unique façon de rapprocher une classe d'un niveau** dans toute
    l'application (EF-L3). Le tableau de progression s'en sert pour
    ranger cinq classes sous un chapitre ; la création d'une classe s'en
    sert pour remplir sa colonne ``niveau``.

    Le plus long préfixe gagne — sans quoi « 1° » mordrait avant
    « 1°STL » si l'ordre de :data:`NIVEAUX` changeait un jour. Rend
    ``""`` quand rien ne correspond, ce qui n'est pas une panne : un
    établissement peut nommer une classe autrement, et c'est alors elle
    qui n'apparaît dans aucune ligne de progression.
    """
    candidats = [n for n in NIVEAUX if code.startswith(n)]
    return max(candidats, key=len) if candidats else ""


def rang_du_niveau(niveau: str) -> int:
    """La place du niveau dans la progression — pour le TRI."""
    return NIVEAUX.index(niveau) if niveau in NIVEAUX else len(NIVEAUX)


def cycle_propose(niveau: str) -> str:
    """Le cycle qu'on PROPOSE pour un niveau, à la création d'une classe.

    ⚠️ **C'est le seul endroit de l'app où un cycle se dérive**, et le
    mot « propose » est le contrat : la valeur est écrite une fois dans
    la colonne ``classes.cycle``, et tous les écrans lisent ensuite la
    COLONNE. Redeviner le cycle en lisant « 2°GT2 » au moment d'afficher
    est l'erreur que RT-3 nomme — elle marche jusqu'au jour où un
    établissement nomme ses secondes autrement.

    Le défaut est ``college`` : c'est le cycle de la majorité des
    classes, et une classe mal classée se corrige à l'écran.
    """
    return CYCLE_DU_NIVEAU.get(niveau, "college")


def competences_de(
    cycle: str, type_evaluation: str
) -> tuple[tuple[str, str], ...]:
    """Les compétences proposées pour une évaluation (EF-D3).

    Le CYCLE donne la liste — sept au collège, cinq au lycée — et le
    TYPE en retire celles qui ne se jugent pas sur une copie.
    """
    toutes = COMPETENCES.get(cycle, COMPETENCES["college"])
    if type_evaluation in TYPES_SUR_COPIE:
        return tuple((c, lib) for c, lib in toutes if c not in HORS_COPIE)
    return toutes


# ── RT-5 · L'alternance se compte en JOURS entre deux lundis ──────────

def lundi_de(jour: date) -> date:
    """Le lundi de la semaine de ``jour``."""
    return jour - timedelta(days=jour.weekday())


def semaine_ab(jour: date, lundi_ref: date | None) -> str | None:
    """``"A"``, ``"B"``, ou ``None`` quand l'alternance est indéterminée.

    **Piège n° 2, payé pour de vrai** : calculée sur les NUMÉROS de
    semaine ISO, l'alternance s'inverse en janvier une année sur cinq —
    celles qui comptent 53 semaines. On compte donc l'écart en JOURS
    entre deux lundis, ce qui ne connaît ni les numéros ni les années.

    ``lundi_ref`` vide rend ``None`` et **ce n'est pas une panne**
    (RT-4) : c'est une année dont la date de référence n'a pas encore
    été saisie. L'écran doit le DIRE — « on ne sait pas » — plutôt que
    d'inventer une lettre (EF-A11, dernier paragraphe).
    """
    if lundi_ref is None:
        return None
    ecart = (lundi_de(jour) - lundi_de(lundi_ref)).days // 7
    return "A" if ecart % 2 == 0 else "B"


# ── RT-6 · Le décompte saute les vacances et les fériés ───────────────

def periode_sans_classe(
    jour: date, periodes: list[tuple[str, date, date]]
) -> str | None:
    """Le libellé de la période qui couvre ``jour``, ou ``None``.

    Une période est ``(libellé, premier jour SANS classe, dernier jour
    SANS classe)`` — les deux bornes sont incluses (EF-A5). Les périodes
    peuvent se chevaucher ; la première qui couvre gagne, et l'ordre
    d'entrée fait donc foi.

    **Piège n° 3** : la grille est un emploi du temps TYPE, elle place
    la classe au lundi sans savoir que ce lundi tombe à la Toussaint.
    Tout décompte de séances passe par ici, sinon le seuil est franchi
    deux semaines trop tôt.
    """
    for libelle, debut, fin in periodes:
        if debut <= jour <= fin:
            return libelle
    return None


def est_jour_de_classe(
    jour: date, periodes: list[tuple[str, date, date]]
) -> bool:
    """Un jour ouvré hors vacances et hors férié. Le dimanche n'en est pas.

    Le samedi, si : la grille va du lundi au samedi (EF-B1), et une
    classe peut y avoir cours.
    """
    if jour.weekday() == 6:
        return False
    return periode_sans_classe(jour, periodes) is None


# ── Les périodes de travail — EF-A9, EF-A10 ───────────────────────────

#: Au-delà de combien de jours une période SANS CLASSE coupe l'année en
#: deux périodes de travail. *« Seules les vraies vacances coupent ; un
#: férié, un pont, une journée banalisée tombent DANS une période »*
#: (EF-A9). Sept jours, c'est la semaine entière : en dessous, on est
#: encore dans le même morceau d'année.
SEUIL_VRAIES_VACANCES = 7


def sont_de_vraies_vacances(debut: date, fin: date) -> bool:
    """Cette période coupe-t-elle l'année (EF-A9) ?"""
    return (fin - debut).days + 1 > SEUIL_VRAIES_VACANCES


def semaines_touchees(debut: date, fin: date) -> int:
    """Le nombre de LUNDIS touchés, jamais les jours divisés par sept.

    *« Une période qui commence un mardi et finit un vendredi occupe la
    semaine entière dans la tête de celui qui la vit »* (EF-A10). Quatre
    jours divisés par sept donneraient zéro semaine, ce qui est faux pour
    tout le monde sauf pour une calculette.
    """
    return ((lundi_de(fin) - lundi_de(debut)).days // 7) + 1


def periodes_de_travail(
    periodes: list[tuple[str, date, date]], debut: date, fin: date
) -> list[tuple[int, date, date, int]]:
    """Découpe l'année en morceaux de travail : ``(n°, début, fin, semaines)``.

    Seules les VRAIES vacances coupent (EF-A9). Un férié, un pont, une
    journée banalisée tombent donc à l'intérieur d'un morceau, ce qui est
    exactement ce que le professeur vit : la semaine du 11 novembre est
    une semaine de la période 1, amputée d'un jour.

    Les périodes sont triées ici plutôt que par l'appelant : le découpage
    n'a aucun sens sur une liste en désordre, et un appelant qui devrait
    s'en souvenir finit par l'oublier.
    """
    coupures = sorted(
        (d, f) for _lib, d, f in periodes if sont_de_vraies_vacances(d, f)
    )
    morceaux: list[tuple[int, date, date, int]] = []
    curseur = debut
    for coupure_debut, coupure_fin in coupures:
        if coupure_debut > curseur:
            borne = min(coupure_debut - timedelta(days=1), fin)
            morceaux.append((len(morceaux) + 1, curseur, borne,
                             semaines_touchees(curseur, borne)))
        curseur = max(curseur, coupure_fin + timedelta(days=1))
    if curseur <= fin:
        morceaux.append((len(morceaux) + 1, curseur, fin,
                         semaines_touchees(curseur, fin)))
    return morceaux


# ── La grille — les blocs, les TP, la saisie d'une case ───────────────

#: Au-delà de combien de minutes une pause COUPE un bloc. *« Une
#: récréation ne coupe pas un bloc, la pause de midi si »* (EF-B9). Le
#: seuil est en minutes et pas « la pause du midi », parce que les bornes
#: horaires se règlent pour l'année (EF-B3) : c'est l'écart RÉEL entre
#: deux heures qui décide, jamais le rang de la case.
SEUIL_PAUSE_MINUTES = 30

#: Combien d'heures de suite avec la même classe font un TP (EF-B10).
#:
#: ⚠️ **C'est l'UNIQUE définition du TP dans l'application**, et EF-K12 le
#: demande explicitement : la grille qui réunit trois cases et le cahier
#: de texte qui annonce « TP de trois heures » doivent dire la même
#: chose. Deux définitions divergeraient le jour où l'une des deux
#: apprendrait un cas particulier.
TAILLE_TP = 3


def minutes_de(horaire: str) -> int:
    """``"08:15"`` → 495. Pour comparer deux bornes sans objet ``time``."""
    heures, _, mins = horaire.partition(":")
    return int(heures) * 60 + int(mins)


def blocs_du_jour(
    cases: dict[int, dict], bornes: dict[int, tuple[str, str]]
) -> list[dict]:
    """Réunit les heures consécutives d'une même classe (EF-B9).

    Rend une liste de blocs ``{debut, fin, code, nature, salles}`` où
    ``debut`` et ``fin`` sont des rangs d'horaire (inclus). Les quatre
    règles du cahier, et chacune est un test :

    - des cases **consécutives** de la **même classe** se réunissent ;
    - une **récréation ne coupe pas**, la **pause de midi si** — c'est
      :data:`SEUIL_PAUSE_MINUTES`, mesuré sur les bornes réelles ;
    - une heure à **nature** ne se fond pas dans le bloc voisin : « HVC »
      n'est pas un cours, et le réunir avec le cours d'avant ferait
      disparaître la frontière que le cahier de texte lit ;
    - un changement de **salle ne coupe rien**. Le bloc garde alors les
      DEUX salles — les cacher ferait afficher la première pour deux
      heures qui ne sont pas au même endroit.
    """
    blocs: list[dict] = []
    for rang in sorted(bornes):
        case = cases.get(rang)
        if case is None:
            continue
        if blocs:
            precedent = blocs[-1]
            pause = (minutes_de(bornes[rang][0])
                     - minutes_de(bornes[precedent["fin"]][1]))
            if (precedent["fin"] == rang - 1
                    and precedent["code"] == case["code"]
                    and precedent["nature"] == case["nature"]
                    and pause <= SEUIL_PAUSE_MINUTES):
                precedent["fin"] = rang
                if case["salle"] and case["salle"] not in precedent["salles"]:
                    precedent["salles"].append(case["salle"])
                continue
        blocs.append({
            "debut": rang, "fin": rang, "code": case["code"],
            "nature": case["nature"],
            "salles": [case["salle"]] if case["salle"] else [],
        })
    return blocs


def est_un_tp(bloc: dict) -> bool:
    """Trois heures de suite avec la même classe (EF-B10).

    Rien n'est saisi ni stocké : la règle se LIT dans la grille. Une
    heure à nature n'en est jamais un — « trois HVC de suite » n'est pas
    un travail pratique.
    """
    return (not bloc["nature"]
            and bloc["fin"] - bloc["debut"] + 1 >= TAILLE_TP)


def lire_saisie(
    texte: str, codes_connus: frozenset[str]
) -> tuple[str, str, str]:
    """``"4e2 - HVC - C209"`` → ``("4e2", "HVC", "C209")`` (EF-B7, EF-B8).

    **Le piège n° 1 du cahier tient dans une phrase** : *seuls les mots de
    la liste des natures retirent une heure du cahier de texte ; tout le
    reste est une salle*. L'inverse — prendre ce qui suit le code pour
    une nature — a fait disparaître **31 créneaux sur 43** le jour où les
    salles ont été saisies. Le défaut, ici, est donc « c'est un cours ».

    **Et le découpage n'a lieu que si le premier morceau désigne une
    classe DÉJÀ EXISTANTE** (EF-B8). Un établissement qui nommerait ses
    classes « 2nde - 4 » verrait sinon ses codes amputés sans prévenir :
    faute de reconnaître « 2nde », on garde la chaîne entière.

    Deux écritures sont acceptées pour la même chose, parce que les deux
    se tapent : ``3e4 (L)`` et ``3e4 - L``.
    """
    texte = texte.strip()
    if not texte:
        return "", "", ""

    morceaux: list[str]
    if texte.endswith(")") and "(" in texte:
        tete, _, queue = texte.rpartition("(")
        morceaux = [tete.strip(), queue[:-1].strip()]
    else:
        morceaux = [m.strip() for m in texte.split("-")]

    if len(morceaux) < 2 or morceaux[0] not in codes_connus:
        return texte, "", ""

    nature, salle = "", ""
    for morceau in morceaux[1:]:
        if not morceau:
            continue
        if morceau.upper() in NATURES:
            nature = morceau.upper()
        else:
            salle = morceau
    return morceaux[0], nature, salle


# ── RT-4 · Une date qui manque n'est pas une panne ────────────────────

def trimestre_de(
    jour: date, fins: dict[int, date | None], fin_annee: date
) -> int | None:
    """Le numéro de trimestre d'une date — ``None`` hors de l'année.

    Seule la FIN d'un trimestre se saisit ; le début est le lendemain du
    précédent (EF-A3). Un trimestre **sans fin court jusqu'à la fin de
    l'année** (RT-4), ce qui veut dire qu'un tableau de trimestres à
    moitié rempli répond quand même — c'est exactement le comportement
    qu'on veut en septembre, quand les dates du troisième ne sont pas
    connues.
    """
    for numero in (1, 2, 3):
        fin = fins.get(numero) or fin_annee
        if jour <= fin:
            return numero
    return None


# ── La moyenne — § 5.2 ────────────────────────────────────────────────

def moyenne_de(notes: list[tuple[float | None, float, float]]) -> float | None:
    """La moyenne d'un élève sur un trimestre, ou ``None``.

    ``notes`` est une liste de ``(valeur, barème, coefficient)``. La règle
    du § 5.2 en entier, et chacun de ses trois morceaux compte :

    - **pondérée par le coefficient** — un devoir sur table ne pèse pas
      une interrogation rapide ;
    - **chaque note ramenée sur 20 par son barème** — un TP sur 40 et une
      interrogation sur 10 ne s'additionnent pas autrement ;
    - **les absences ne comptent pas**. Elles ne valent pas zéro : une
      absence n'est pas une note, et la compter comme telle ferait
      chuter une moyenne pour une raison qui n'est pas un résultat.

    ``None`` quand il n'y a rien à moyenner — un trimestre sans note ne
    vaut pas zéro non plus.
    """
    total = 0.0
    poids = 0.0
    for valeur, bareme, coefficient in notes:
        if valeur is None or not bareme or not coefficient:
            continue
        total += (valeur / bareme) * 20.0 * coefficient
        poids += coefficient
    return round(total / poids, 2) if poids else None


# ── Affichage — la forme qui a tenu trois ans ─────────────────────────

def jour_et_date(jour: date) -> str:
    """« ven 16/10 » — le jour de la semaine PRÉCÈDE la date (EF-A7).

    *Poser une journée banalisée un mercredi ou un vendredi n'a pas le
    même prix* : une date nue oblige à faire le calcul de tête.
    """
    return f"{JOURS_COURTS[jour.weekday()]} {jour.day:02d}/{jour.month:02d}"


def rentree_de(jour: date) -> int:
    """L'année civile de la rentrée qui couvre ``jour``.

    Une année scolaire est à cheval sur deux années civiles : en juin
    2027 on est dans « 2026-2027 », en septembre 2027 dans « 2027-2028 ».
    La bascule est au 1er août — après le 31 juillet, la rentrée qui
    vient est celle de l'année civile en cours.
    """
    return jour.year if jour.month >= 8 else jour.year - 1

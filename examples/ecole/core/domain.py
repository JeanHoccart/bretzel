"""core/domain — the business vocabulary and the eight cross-cutting rules.

No ``bretzel`` import here, and that is deliberate: this module is the
part of the app one can re-read knowing nothing of the framework. It
carries § 4 (glossary) and § 6 (cross-cutting rules) of the
specification, and nothing else.

**Why the rules live here and not in the screens.** RT-8 says a business
rule holds *whatever the screen*. A rule written in a screen is a rule a
second screen will rediscover wrongly — the specification documents
fourteen traps paid for in the original application, and four of them
(no. 1, 2, 3, 4) are exactly that: a rule recomputed on the spot, with a
nuance forgotten.

The five computational rules are here, each in one function:

=====  =====================================================  =====================
rule   what it says                                           the function
=====  =====================================================  =====================
RT-3   the CYCLE decides, never the class code                :func:`cycle_propose`
RT-4   a missing date is not a failure                        :func:`trimestre_de`
RT-5   the A/B alternation counts in DAYS between two Mondays :func:`semaine_ab`
RT-6   the count skips holidays and public holidays           :func:`periode_sans_classe`
EF-L3  a level brings a class close to a chapter              :func:`niveau_du_code`
=====  =====================================================  =====================

RT-1 (the current year is the only one written) and RT-2 (nothing that
carries history is erased) are not computations: the first is a guard, it
lives in ``features/annees.py``; the second is a form of schema — a DATED
enrolment rather than a row one deletes — and it lives in ``core/db.py``.

RT-7 (what is proposed is never imposed) and RT-8 (a rule holds whatever
the screen) are design rules: they are not written, they are held.
"""

from __future__ import annotations

from datetime import date, timedelta

# ── Le glossaire, en constantes ───────────────────────────────────────

#: The two cycles. They decide the number of skills, the term dates and
#: what is proposed on screen (RT-3).
CYCLES: dict[str, str] = {"college": "Collège", "lycee": "Lycée"}

#: The levels, in progression order. It is also the sort order:
#: ``NIVEAUX.index(niveau)`` is the rank.
#:
#: ⚠️ They are written the way the teacher writes their class codes —
#: "2°GT2", "1°S1" — because :func:`niveau_du_code` recognises them by
#: PREFIX (EF-L3). A table saying "seconde" would bring nothing close.
NIVEAUX: tuple[str, ...] = ("6e", "5e", "4e", "3e", "2°GT", "1°", "T°")

#: Each level's cycle. Serves ONCE — when creating a class (cf.
#: :func:`cycle_propose`). It is not a read path.
CYCLE_DU_NIVEAU: dict[str, str] = {
    "6e": "college", "5e": "college", "4e": "college", "3e": "college",
    "2°GT": "lycee", "1°": "lycee", "T°": "lycee",
}

#: The skills assessed, per cycle: seven at collège, five at lycée
#: (EF-D3). The number comes from the CYCLE, never from the class code.
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

#: The skills that are NOT judged on a paper (EF-D3). A written test
#: cannot assess the gesture at the workbench.
HORS_COPIE: frozenset[str] = frozenset({"REA", "AUT"})

#: The assessment types.
TYPES_EVALUATION: tuple[str, ...] = ("DS", "IE", "TP", "Oral", "Projet",
                                     "Maison")

#: Those done on paper, which therefore exclude :data:`HORS_COPIE`.
TYPES_SUR_COPIE: frozenset[str] = frozenset({"DS", "IE", "Maison"})

#: The NATURES — what makes an hour something other than a lesson. The
#: list is closed, and it is the whole of trap no. 1: **anything not in
#: it is a ROOM** (EF-B7). The opposite made 31 slots out of 43 vanish
#: from the lesson log the day the rooms were entered.
NATURES: tuple[str, ...] = ("HVC",)

#: A pupil's accommodations (EF-C4).
AMENAGEMENTS: tuple[str, ...] = ("PAP", "PPS", "PAI", "PPRE")

#: The grid's six days, Monday to Saturday (EF-B1). The index in this
#: tuple IS the stored day number — ``date.weekday()`` gives the same,
#: which avoids a lookup table.
JOURS: tuple[str, ...] = ("lundi", "mardi", "mercredi", "jeudi",
                          "vendredi", "samedi")

#: The day's three letters, for "ven 16/10" (EF-A7).
JOURS_COURTS: tuple[str, ...] = ("lun", "mar", "mer", "jeu", "ven", "sam",
                                 "dim")

#: A day's eight boundaries, in 55-minute hours. These are the SEEDED
#: values: they are then set for the whole year in the grid's first
#: column (EF-B3).
#:
#: ⚠️ Lessons do not start on the round hour. Four start times quoted by
#: the specification — 10:10, 11:10, 13:30, 15:40 — are here as they are:
#: a rounded table would make the grid wrong to the eye of the only
#: person who knows it by heart.
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

#: Zone B's four holidays, in the year's order. The settings screen
#: PROPOSES them, filled in or not, **without creating empty rows in
#: advance** (EF-A4): a proposal is a row on screen, not a row in the
#: database.
VACANCES_ZONE_B: tuple[str, ...] = ("Toussaint", "Noël", "Février",
                                    "Pâques")

#: The four observation criteria, in report-card order (§ 5.3).
CRITERES: tuple[str, ...] = ("Comportement", "Travail", "Participation",
                             "Matériel, ponctualité")

#: Each criterion's levels: ``(rank, short, long, tint)``. Rank 1 = the
#: most favourable. The tint goes from 1 to 4 — 1-2 favourable or
#: neutral, 3-4 signals a difficulty (EF-E1).
#:
#: Seven for Comportement and Travail, six for Participation, four for
#: Matériel: the counts come from the specification, not from a symmetry.
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


# ── RT-3 · The cycle decides, never the class code ────────────────────

def niveau_du_code(code: str) -> str:
    """The level a class code names — "3e1" → "3e".

    **The only way of relating a class to a level** in the whole
    application (EF-L3). The progression table uses it to file five
    classes under a chapter; creating a class uses it to fill its
    ``niveau`` column.

    The longest prefix wins — without which "1°" would bite before
    "1°STL" if :data:`NIVEAUX`'s order ever changed. Returns ``""`` when
    nothing matches, which is not a failure: a school may name a class
    otherwise, and it is then that class that appears in no progression
    row.
    """
    candidats = [n for n in NIVEAUX if code.startswith(n)]
    return max(candidats, key=len) if candidats else ""


def rang_du_niveau(niveau: str) -> int:
    """The level's place in the progression — for SORTING."""
    return NIVEAUX.index(niveau) if niveau in NIVEAUX else len(NIVEAUX)


def cycle_propose(niveau: str) -> str:
    """The cycle PROPOSED for a level, when creating a class.

    ⚠️ **It is the app's only place where a cycle is derived**, and the
    word "propose" is the contract: the value is written once into the
    ``classes.cycle`` column, and every screen then reads the COLUMN.
    Re-guessing the cycle by reading "2°GT2" at display time is the error
    RT-3 names — it works until the day a school names its secondes
    otherwise.

    The default is ``college``: it is the cycle of most classes, and a
    misfiled class is corrected on screen.
    """
    return CYCLE_DU_NIVEAU.get(niveau, "college")


def competences_de(
    cycle: str, type_evaluation: str
) -> tuple[tuple[str, str], ...]:
    """The skills proposed for an assessment (EF-D3).

    The CYCLE gives the list — seven at collège, five at lycée — and the
    TYPE removes those that are not judged on a paper.
    """
    toutes = COMPETENCES.get(cycle, COMPETENCES["college"])
    if type_evaluation in TYPES_SUR_COPIE:
        return tuple((c, lib) for c, lib in toutes if c not in HORS_COPIE)
    return toutes


# ── RT-5 · The alternation counts in DAYS between two Mondays ────────

def lundi_de(jour: date) -> date:
    """The Monday of ``jour``'s week."""
    return jour - timedelta(days=jour.weekday())


def semaine_ab(jour: date, lundi_ref: date | None) -> str | None:
    """``"A"``, ``"B"``, or ``None`` when the alternation is undetermined.

    **Trap no. 2, paid for real**: computed on ISO week NUMBERS, the
    alternation inverts in January one year in five — those with 53
    weeks. So we count the gap in DAYS between two Mondays, which knows
    neither numbers nor years.

    An empty ``lundi_ref`` returns ``None`` and **that is not a failure**
    (RT-4): it is a year whose reference date has not been entered yet.
    The screen must SAY so — "we do not know" — rather than invent a
    letter (EF-A11, last paragraph).
    """
    if lundi_ref is None:
        return None
    ecart = (lundi_de(jour) - lundi_de(lundi_ref)).days // 7
    return "A" if ecart % 2 == 0 else "B"


# ── RT-6 · The count skips holidays and public holidays ──────────────

def periode_sans_classe(
    jour: date, periodes: list[tuple[str, date, date]]
) -> str | None:
    """The label of the period covering ``jour``, or ``None``.

    A period is ``(label, first day WITHOUT class, last day WITHOUT
    class)`` — both bounds are inclusive (EF-A5). Periods may overlap;
    the first that covers wins, so the entry order is authoritative.

    **Trap no. 3**: the grid is a TYPICAL timetable, it places the class
    on Monday without knowing that Monday falls in the Toussaint break.
    Every session count goes through here, otherwise the threshold is
    crossed two weeks too early.
    """
    for libelle, debut, fin in periodes:
        if debut <= jour <= fin:
            return libelle
    return None


def est_jour_de_classe(
    jour: date, periodes: list[tuple[str, date, date]]
) -> bool:
    """A working day outside holidays and public holidays. Sunday is not
    one.

    Saturday is: the grid runs from Monday to Saturday (EF-B1), and a
    class may have lessons there.
    """
    if jour.weekday() == 6:
        return False
    return periode_sans_classe(jour, periodes) is None


# ── The working periods — EF-A9, EF-A10 ───────────────────────────────

#: Beyond how many days a period WITHOUT CLASS cuts the year into two
#: working periods. *"Only real holidays cut; a public holiday, a bridge
#: day, a staff day fall INSIDE a period"* (EF-A9). Seven days is the
#: whole week: below that, we are still in the same piece of the year.
SEUIL_VRAIES_VACANCES = 7


def sont_de_vraies_vacances(debut: date, fin: date) -> bool:
    """Does this period cut the year (EF-A9)?"""
    return (fin - debut).days + 1 > SEUIL_VRAIES_VACANCES


def semaines_touchees(debut: date, fin: date) -> int:
    """The number of MONDAYS touched, never the days divided by seven.

    *"A period starting on a Tuesday and ending on a Friday occupies the
    whole week in the head of whoever lives it"* (EF-A10). Four days
    divided by seven would give zero weeks, which is wrong for everybody
    except a calculator.
    """
    return ((lundi_de(fin) - lundi_de(debut)).days // 7) + 1


def periodes_de_travail(
    periodes: list[tuple[str, date, date]], debut: date, fin: date
) -> list[tuple[int, date, date, int]]:
    """Cut the year into working pieces: ``(no., start, end, weeks)``.

    Only REAL holidays cut (EF-A9). A public holiday, a bridge day, a
    staff day therefore fall inside a piece, which is exactly what the
    teacher lives: the week of 11 November is a week of period 1, one day
    short.

    The periods are sorted here rather than by the caller: the cutting
    makes no sense on an unordered list, and a caller who had to remember
    it ends up forgetting.
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


# ── The grid — the blocks, the practicals, entering a cell ───────────

#: Beyond how many minutes a break CUTS a block. *"A break does not cut
#: a block, the lunch break does"* (EF-B9). The threshold is in minutes
#: and not "the lunch break", because the time boundaries are set for the
#: year (EF-B3): it is the REAL gap between two hours that decides, never
#: the cell's rank.
SEUIL_PAUSE_MINUTES = 30

#: How many hours in a row with the same class make a practical (EF-B10).
#:
#: ⚠️ **It is the application's ONLY definition of a practical**, and
#: EF-K12 asks for it explicitly: the grid that joins three cells and the
#: lesson log announcing "a three-hour practical" must say the same
#: thing. Two definitions would diverge the day one of them learned a
#: special case.
TAILLE_TP = 3


def minutes_de(horaire: str) -> int:
    """``"08:15"`` → 495. To compare two boundaries without a ``time``
    object."""
    heures, _, mins = horaire.partition(":")
    return int(heures) * 60 + int(mins)


def blocs_du_jour(
    cases: dict[int, dict], bornes: dict[int, tuple[str, str]]
) -> list[dict]:
    """Join the consecutive hours of the same class (EF-B9).

    Returns a list of blocks ``{debut, fin, code, nature, salles}`` where
    ``debut`` and ``fin`` are time-slot ranks (inclusive). The
    specification's four rules, and each is a test:

    - **consecutive** cells of the **same class** join;
    - a **break does not cut**, the **lunch break does** — it is
      :data:`SEUIL_PAUSE_MINUTES`, measured on the real boundaries;
    - an hour with a **nature** does not merge into the neighbouring
      block: "HVC" is not a lesson, and joining it with the previous
      lesson would erase the boundary the lesson log reads;
    - a change of **room cuts nothing**. The block then keeps BOTH rooms
      — hiding them would show the first for two hours that are not in
      the same place.
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
    """Three hours in a row with the same class (EF-B10).

    Nothing is entered or stored: the rule is READ from the grid. An hour
    with a nature is never one — "three HVC in a row" is not a practical.
    """
    return (not bloc["nature"]
            and bloc["fin"] - bloc["debut"] + 1 >= TAILLE_TP)


def lire_saisie(
    texte: str, codes_connus: frozenset[str]
) -> tuple[str, str, str]:
    """``"4e2 - HVC - C209"`` → ``("4e2", "HVC", "C209")`` (EF-B7, EF-B8).

    **The specification's trap no. 1 fits in one sentence**: *only the
    words in the list of natures remove an hour from the lesson log;
    everything else is a room*. The opposite — taking what follows the
    code for a nature — made **31 slots out of 43** vanish the day the
    rooms were entered. So the default here is "it is a lesson".

    **And the split only happens if the first piece names an ALREADY
    EXISTING class** (EF-B8). A school naming its classes "2nde - 4"
    would otherwise see its codes truncated without warning: failing to
    recognise "2nde", we keep the whole string.

    Two spellings are accepted for the same thing, because both get
    typed: ``3e4 (L)`` and ``3e4 - L``.
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


# ── RT-4 · A missing date is not a failure ────────────────────────────

def trimestre_de(
    jour: date, fins: dict[int, date | None], fin_annee: date
) -> int | None:
    """A date's term number — ``None`` outside the year.

    Only a term's END is entered; the start is the day after the previous
    one (EF-A3). A term **with no end runs to the end of the year**
    (RT-4), which means a half-filled table of terms still answers — it
    is exactly the behaviour wanted in September, when the third term's
    dates are not known.
    """
    for numero in (1, 2, 3):
        fin = fins.get(numero) or fin_annee
        if jour <= fin:
            return numero
    return None


# ── La moyenne — § 5.2 ────────────────────────────────────────────────

def moyenne_de(notes: list[tuple[float | None, float, float]]) -> float | None:
    """A pupil's average over a term, or ``None``.

    ``notes`` is a list of ``(value, scale, coefficient)``. The whole of
    § 5.2's rule, and each of its three parts counts:

    - **weighted by the coefficient** — a written test does not weigh the
      same as a quick quiz;
    - **each mark brought back to 20 by its scale** — a practical out of
      40 and a quiz out of 10 do not add up otherwise;
    - **absences do not count**. They are not worth zero: an absence is
      not a mark, and counting it as one would drop an average for a
      reason that is not a result.

    ``None`` when there is nothing to average — a term with no mark is
    not worth zero either.
    """
    total = 0.0
    poids = 0.0
    for valeur, bareme, coefficient in notes:
        if valeur is None or not bareme or not coefficient:
            continue
        total += (valeur / bareme) * 20.0 * coefficient
        poids += coefficient
    return round(total / poids, 2) if poids else None


# ── Display — the form that held for three years ──────────────────────

def jour_et_date(jour: date) -> str:
    """"ven 16/10" — the weekday PRECEDES the date (EF-A7).

    *Putting a staff day on a Wednesday or a Friday does not cost the
    same*: a bare date forces you to work it out in your head.
    """
    return f"{JOURS_COURTS[jour.weekday()]} {jour.day:02d}/{jour.month:02d}"


def rentree_de(jour: date) -> int:
    """The calendar year of the school year covering ``jour``.

    A school year straddles two calendar years: in June 2027 we are in
    "2026-2027", in September 2027 in "2027-2028". The switch is on 1
    August — after 31 July, the coming school year is that of the current
    calendar year.
    """
    return jour.year if jour.month >= 8 else jour.year - 1

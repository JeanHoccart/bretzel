"""core/redaction — the factory for comments and class summaries.

Pure Python, no database, no ``bretzel``: give it what is known about a
pupil, it returns a text. That is what allows testing it without mounting
anything, and it is the app's densest part in business rules — EF-E2 to
EF-E8 and EF-F1 to EF-F4 fit in it entirely.

The four rules that decide the text's SHAPE
--------------------------------------------
**EF-E4 — never more than 400 characters, and the order of sacrifice is
written down.** Every sentence carries a priority; beyond the limit, the
least essential fall — *never the work, never the behaviour, never the
conclusion*. It is an ordered list, not a sort by length: cutting the
longest sentence would give a shorter text and a false one.

**EF-E5 — one wording per term.** The same observation does not give the
same sentence in the first and the third: *"adopte un comportement
exemplaire"* becomes *"aura été exemplaire d'un bout à l'autre"*. The
frames are in :data:`CADRES`.

**EF-E6 — between two wordings, the one that REPEATS LEAST** what
precedes. It is what avoids *"des résultats solides […] un ensemble
solide"* — and it is measurable: we count the words already used.

**EF-E7 — the average thresholds**, and the specification gives the
reason for the threshold: *"12 is a just-satisfactory average, not
'solid' — the 'solid results' step only starts at 13"*.

What the factory does NOT do
-----------------------------
It never decides to overwrite a text. EF-E3 — *"as soon as the teacher
writes their own text, the application never rewrites it again"* — is a
STORAGE rule (the ``ecrite_main`` flag), not a writing one. The factory
is called or it is not.
"""

from __future__ import annotations

#: EF-E4's limit, in characters.
LIMITE = 400

#: EF-E4's order of SACRIFICE, from most protected to most sacrificial.
#: These are sentence keys; the READING order is :data:`ORDRE_LECTURE`.
#: The two differ, and that is the point: we cut by importance, we read
#: by narrative.
SACRIFICE: tuple[str, ...] = (
    "travail", "comportement", "resultats", "conclusion", "evolution",
    "participation", "competences", "materiel",
)

#: The order in which the sentences kept are read.
ORDRE_LECTURE: tuple[str, ...] = (
    "comportement", "travail", "participation", "materiel", "resultats",
    "competences", "evolution", "conclusion",
)

#: EF-E7's steps: ``(floor, word)``. Read from the top down.
#:
#: ⚠️ The "solides" step starts at **13** and not at 12, and the
#: specification gives the reason: *"12 is a just-satisfactory average"*.
#: Lowering that threshold would write "solides" on report cards where it
#: would be false, and nobody would catch it.
PALIERS: tuple[tuple[float, str], ...] = (
    (15.0, "très bons"),
    (13.0, "solides"),
    (9.0, "convenables"),
    (0.0, "fragiles"),
)

#: EF-E5's frames: per criterion and per term, TWO wordings. The second
#: exists for EF-E6 — with no choice, there is nothing to decide between.
#: ``{}`` receives the long label of the level ticked.
CADRES: dict[str, tuple[tuple[str, str], ...]] = {
    "Comportement": (
        ("Élève qui {}.", "{}."),
        ("Ce trimestre encore, {}.", "{}."),
        ("Aura, d'un bout à l'autre de l'année, montré qu'il {}.", "{}."),
    ),
    "Travail": (
        ("{}.", "Sur le plan du travail, {}."),
        ("{}.", "Côté travail, {}."),
        ("Sur l'ensemble de l'année, {}.", "{}."),
    ),
    "Participation": (
        ("À l'oral, {}.", "{}."),
        ("{}.", "En classe, {}."),
        ("Tout au long de l'année, {}.", "{}."),
    ),
    "Matériel, ponctualité": (
        ("{}.", "Enfin, {}."),
        ("{}.", "On note aussi qu'il {}."),
        ("{}.", "Il reste qu'il {}."),
    ),
}

#: The RESULTS sentences, per step. Two per step, for EF-E6.
RESULTATS: dict[str, tuple[str, ...]] = {
    "très bons": ("Les résultats sont très bons ({moyenne} de moyenne).",
                  "Une moyenne de {moyenne} vient confirmer l'ensemble."),
    "solides": ("Les résultats sont solides ({moyenne} de moyenne).",
                "La moyenne s'établit à {moyenne}, ce qui est un bon niveau."),
    "convenables": ("Les résultats sont convenables ({moyenne}).",
                    "La moyenne atteint {moyenne}."),
    "fragiles": ("Les résultats restent fragiles ({moyenne}).",
                 "Avec {moyenne} de moyenne, les acquis sont encore fragiles."),
}

#: The PROGRESS sentences between two terms.
EVOLUTION: dict[str, tuple[str, ...]] = {
    "hausse": ("Les progrès par rapport au trimestre précédent sont nets.",
               "L'évolution depuis le trimestre dernier est encourageante."),
    "baisse": ("Le niveau a baissé depuis le trimestre précédent.",
               "On note un fléchissement par rapport au trimestre dernier."),
    "stable": ("Le niveau se maintient.",
               "La régularité est là d'un trimestre à l'autre."),
}

#: EF-E8's conclusions, by what DOMINATES.
CONCLUSIONS: dict[str, tuple[str, ...]] = {
    "comportement": ("Un changement d'attitude est la première chose à "
                     "obtenir.",
                     "C'est d'abord sur l'attitude qu'il faut agir."),
    "organisation": ("Davantage de méthode et de régularité changerait tout.",
                     "Il faut gagner en organisation."),
    "hausse": ("À poursuivre dans cette direction.",
               "Il faut continuer ainsi."),
    "baisse": ("Un sursaut est nécessaire dès le trimestre prochain.",
               "Il faut se ressaisir rapidement."),
    "bon": ("Ensemble très satisfaisant.", "Trimestre réussi."),
    "moyen": ("Trimestre correct, à consolider.",
              "L'essentiel est là, il reste à confirmer."),
    "faible": ("Il faut se remettre au travail sans attendre.",
               "Des efforts soutenus sont attendus."),
}

#: Beyond which TINT a criterion signals a difficulty (EF-E1).
TEINTE_DIFFICULTE = 3


def palier_de(moyenne: float | None) -> str | None:
    """EF-E7's word for an average, or ``None`` if there is none."""
    if moyenne is None:
        return None
    for plancher, mot in PALIERS:
        if moyenne >= plancher:
            return mot
    return PALIERS[-1][1]


def tendance(moyenne: float | None, precedente: float | None) -> str | None:
    """``"hausse"``, ``"baisse"``, ``"stable"`` — or nothing to say.

    A half-point threshold: below it, two averages differing by 0.2 would
    make it write "des progrès nets" for measurement noise.
    """
    if moyenne is None or precedente is None:
        return None
    ecart = moyenne - precedente
    if ecart >= 0.5:
        return "hausse"
    if ecart <= -0.5:
        return "baisse"
    return "stable"


#: On how many letters two words are compared for EF-E6.
#:
#: ⚠️ **Five, and not the whole word.** The first version compared exact
#: words, and it missed precisely the example the specification gives:
#: "solide" is not "solides", so *"des résultats solides […] un ensemble
#: solide"* got through. A test said so before anybody read a report
#: card. Five letters also catch "régulier" / "régularité", which is the
#: same phenomenon.
RACINE_COMPAREE = 5


def racine(mot: str) -> str:
    """A word's start, to compare "solide" and "solides"."""
    return mot.strip(".,;:!?'«»…").lower()[:RACINE_COMPAREE]


def moins_repetitive(candidates: tuple[str, ...], deja: str) -> str:
    """EF-E6 — the one that repeats least what precedes.

    *"It is what avoids 'des résultats solides […] un ensemble
    solide'."* We compare the STEMS of the words of more than four
    letters already used; on a tie, the first wins, which keeps the
    default wording when the choice changes nothing.
    """
    deja_dites = {racine(m) for m in deja.split() if len(m) > 4}

    def repetitions(phrase: str) -> int:
        return sum(1 for m in phrase.split()
                   if len(m) > 4 and racine(m) in deja_dites)

    return min(candidates, key=repetitions)


def choisir_conclusion(niveaux: dict[str, int], palier: str | None,
                       sens: str | None) -> str:
    """EF-E8 — the conclusion depends on what DOMINATES.

    The order of the tests IS the rule, and it reads as the
    specification writes it: *"the behaviour if it is the subject, the
    lack of organisation if it prevails, the trend between terms
    otherwise, and failing that the marks alone"*.

    ``niveaux`` gives each ticked criterion's TINT (1-4).
    """
    if niveaux.get("Comportement", 0) >= TEINTE_DIFFICULTE:
        return "comportement"
    if (niveaux.get("Matériel, ponctualité", 0) >= TEINTE_DIFFICULTE
            or niveaux.get("Travail", 0) >= TEINTE_DIFFICULTE):
        return "organisation"
    if sens in ("hausse", "baisse"):
        return sens
    if palier in ("très bons", "solides"):
        return "bon"
    if palier == "convenables":
        return "moyen"
    return "faible"


def rediger(
    *,
    trimestre: int,
    observations: dict[str, tuple[str, int]],
    moyenne: float | None,
    moyenne_precedente: float | None = None,
    competences: str = "",
) -> str:
    """EF-E2's comment, under EF-E4's 400 characters.

    ``observations``: ``criterion → (long label of the level, tint)``.

    The sentences are composed in READING order, then cut in SACRIFICE
    order: the two lists are different and that is intended. Cutting the
    longest would give a shorter text and a false one.
    """
    cadre_index = min(max(trimestre, 1), 3) - 1
    phrases: dict[str, str] = {}
    deja = ""

    for critere, (long, _teinte) in observations.items():
        cadres = CADRES.get(critere)
        if not cadres:
            continue
        gabarit = moins_repetitive(cadres[cadre_index], deja)
        phrase = gabarit.format(long)
        phrases[cle_de(critere)] = phrase[0].upper() + phrase[1:]
        deja += " " + phrase

    palier = palier_de(moyenne)
    if palier:
        gabarit = moins_repetitive(RESULTATS[palier], deja)
        phrases["resultats"] = gabarit.format(moyenne=f"{moyenne:.1f}")
        deja += " " + phrases["resultats"]

    sens = tendance(moyenne, moyenne_precedente)
    if sens:
        phrases["evolution"] = moins_repetitive(EVOLUTION[sens], deja)
        deja += " " + phrases["evolution"]

    if competences:
        phrases["competences"] = competences
        deja += " " + competences

    teintes = {c: t for c, (_l, t) in observations.items()}
    phrases["conclusion"] = moins_repetitive(
        CONCLUSIONS[choisir_conclusion(teintes, palier, sens)], deja)

    return assembler(phrases)


def cle_de(critere: str) -> str:
    """The name of the sentence a criterion carries, for both orders —
    the sacrifice one and the reading one."""
    return {
        "Comportement": "comportement",
        "Travail": "travail",
        "Participation": "participation",
        "Matériel, ponctualité": "materiel",
    }.get(critere, critere.lower())


def assembler(phrases: dict[str, str]) -> str:
    """Cut until it fits under :data:`LIMITE`, in sacrifice order.

    We remove starting from the END of :data:`SACRIFICE` — the last of
    the list is the most sacrificial — and we never go below the core:
    work, behaviour, conclusion.
    """
    gardees = dict(phrases)
    sacrifiables = [c for c in reversed(SACRIFICE)
                    if c not in ("travail", "comportement", "conclusion")]
    for cle in sacrifiables:
        texte = " ".join(gardees[c] for c in ORDRE_LECTURE if c in gardees)
        if len(texte) <= LIMITE:
            return texte
        gardees.pop(cle, None)
    texte = " ".join(gardees[c] for c in ORDRE_LECTURE if c in gardees)
    return texte if len(texte) <= LIMITE else texte[:LIMITE - 1].rsplit(
        " ", 1)[0] + "…"


# ── The class summary — EF-F1 to EF-F4 ────────────────────────────────

#: EF-F3's thresholds: a difficulty is only named beyond a proportion.
#: Below it, it exists and is not said — naming two pupils out of thirty
#: as a trait of the class would be false.
SEUIL_PLUSIEURS = 0.30
SEUIL_QUELQUES = 0.15

#: EF-F4: **below five, we do not speak.** *"Two sheets out of thirty
#: would give 'the vast majority', which is false."*
MINIMUM_POUR_PARLER = 5


def proportion_dite(part: float) -> str | None:
    """"plusieurs", "quelques", or nothing at all (EF-F3)."""
    if part >= SEUIL_PLUSIEURS:
        return "plusieurs"
    if part >= SEUIL_QUELQUES:
        return "quelques"
    return None


def bilan(
    *,
    moyennes: list[float],
    teintes_par_critere: dict[str, list[int]],
) -> str:
    """EF-F1's class profile, and it STARTS from what dominates (EF-F2).

    *"A class summary is read in the staff room; it must be fair without
    being damning."* So the difficulty arrives as a NUANCE, after the
    overall observation, and never as the subject of the first sentence.
    """
    morceaux: list[str] = []

    if len(moyennes) >= MINIMUM_POUR_PARLER:
        moyenne = sum(moyennes) / len(moyennes)
        palier = palier_de(moyenne)
        morceaux.append(
            f"Classe dont les résultats d'ensemble sont {palier} "
            f"({moyenne:.1f} de moyenne)."
        )
        en_dessous = sum(1 for m in moyennes if m < 9)
        dit = proportion_dite(en_dessous / len(moyennes))
        if dit:
            morceaux.append(
                f"{dit.capitalize()} élèves restent cependant en difficulté."
            )
    else:
        morceaux.append(
            "Trop peu de moyennes pour décrire un niveau d'ensemble."
        )

    coches = max((len(v) for v in teintes_par_critere.values()), default=0)
    if coches >= MINIMUM_POUR_PARLER:
        difficile = teintes_par_critere.get("Comportement", [])
        part = (sum(1 for t in difficile if t >= TEINTE_DIFFICULTE)
                / len(difficile)) if difficile else 0.0
        dit = proportion_dite(part)
        morceaux.append(
            f"L'ambiance de travail est bonne dans l'ensemble ; "
            f"{dit} élèves la perturbent." if dit
            else "L'ambiance de travail est bonne."
        )
    else:
        morceaux.append(
            "Trop peu de fiches cochées pour décrire l'ambiance de travail."
        )

    return " ".join(morceaux)

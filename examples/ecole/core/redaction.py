"""core/redaction — la fabrique d'appréciations et de bilans.

Pur Python, aucune base, aucun ``bretzel`` : on lui donne ce qu'on sait
d'un élève, elle rend un texte. C'est ce qui permet de la tester sans
monter quoi que ce soit, et c'est la partie de l'app la plus dense en
règles métier — EF-E2 à EF-E8 et EF-F1 à EF-F4 y tiennent en entier.

Les quatre règles qui décident de la FORME du texte
----------------------------------------------------
**EF-E4 — jamais plus de 400 caractères, et l'ordre de sacrifice est
écrit.** Chaque phrase porte une priorité ; au-delà de la limite, les
moins essentielles tombent — *jamais le travail, jamais le comportement,
jamais la conclusion*. C'est une liste ordonnée, pas un tri par longueur :
couper la phrase la plus longue donnerait un texte plus court et faux.

**EF-E5 — une formulation par trimestre.** La même observation ne donne
pas la même phrase au premier et au troisième : *« adopte un comportement
exemplaire »* devient *« aura été exemplaire d'un bout à l'autre »*. Les
cadres sont dans :data:`CADRES`.

**EF-E6 — entre deux formulations, celle qui RÉPÈTE LE MOINS** ce qui
précède. C'est ce qui évite *« des résultats solides […] un ensemble
solide »* — et c'est mesurable : on compte les mots déjà employés.

**EF-E7 — les paliers de moyenne**, et le cahier donne la raison du
seuil : *« 12 est une moyenne juste satisfaisante, pas "solide" — le
palier "résultats solides" ne commence qu'à 13 »*.

Ce que la fabrique NE fait pas
-------------------------------
Elle ne décide jamais d'écraser un texte. EF-E3 — *« dès que le
professeur écrit son propre texte, l'application ne le réécrit plus
jamais »* — est une règle de STOCKAGE (le drapeau ``ecrite_main``), pas
de rédaction. La fabrique est appelée ou ne l'est pas.
"""

from __future__ import annotations

#: La limite d'EF-E4, en caractères.
LIMITE = 400

#: L'ordre de SACRIFICE d'EF-E4, du plus gardé au plus sacrifiable. Ce
#: sont des clés de phrase ; l'ordre de LECTURE, lui, est celui de
#: :data:`ORDRE_LECTURE`. Les deux diffèrent, et c'est le point : on
#: coupe par importance, on lit par déroulé.
SACRIFICE: tuple[str, ...] = (
    "travail", "comportement", "resultats", "conclusion", "evolution",
    "participation", "competences", "materiel",
)

#: L'ordre dans lequel les phrases retenues se lisent.
ORDRE_LECTURE: tuple[str, ...] = (
    "comportement", "travail", "participation", "materiel", "resultats",
    "competences", "evolution", "conclusion",
)

#: Les paliers d'EF-E7 : ``(plancher, mot)``. Lus du haut vers le bas.
#:
#: ⚠️ Le palier « solides » commence à **13** et pas à 12, et le cahier
#: en donne la raison : *« 12 est une moyenne juste satisfaisante »*.
#: Descendre ce seuil ferait écrire « solides » sur des bulletins où ce
#: serait faux, et personne ne le relèverait.
PALIERS: tuple[tuple[float, str], ...] = (
    (15.0, "très bons"),
    (13.0, "solides"),
    (9.0, "convenables"),
    (0.0, "fragiles"),
)

#: Les cadres d'EF-E5 : par critère et par trimestre, DEUX formulations.
#: La seconde existe pour EF-E6 — sans choix, il n'y a rien à départager.
#: ``{}`` reçoit le libellé long du niveau coché.
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

#: Les phrases de RÉSULTATS, par palier. Deux par palier, pour EF-E6.
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

#: Les phrases d'ÉVOLUTION entre deux trimestres.
EVOLUTION: dict[str, tuple[str, ...]] = {
    "hausse": ("Les progrès par rapport au trimestre précédent sont nets.",
               "L'évolution depuis le trimestre dernier est encourageante."),
    "baisse": ("Le niveau a baissé depuis le trimestre précédent.",
               "On note un fléchissement par rapport au trimestre dernier."),
    "stable": ("Le niveau se maintient.",
               "La régularité est là d'un trimestre à l'autre."),
}

#: Les conclusions d'EF-E8, par ce qui DOMINE.
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

#: Au-delà de quelle TEINTE un critère signale une difficulté (EF-E1).
TEINTE_DIFFICULTE = 3


def palier_de(moyenne: float | None) -> str | None:
    """Le mot d'EF-E7 pour une moyenne, ou ``None`` s'il n'y en a pas."""
    if moyenne is None:
        return None
    for plancher, mot in PALIERS:
        if moyenne >= plancher:
            return mot
    return PALIERS[-1][1]


def tendance(moyenne: float | None, precedente: float | None) -> str | None:
    """``"hausse"``, ``"baisse"``, ``"stable"`` — ou rien à dire.

    Un demi-point de seuil : en dessous, deux moyennes qui diffèrent de
    0,2 feraient écrire « des progrès nets » pour du bruit de mesure.
    """
    if moyenne is None or precedente is None:
        return None
    ecart = moyenne - precedente
    if ecart >= 0.5:
        return "hausse"
    if ecart <= -0.5:
        return "baisse"
    return "stable"


#: Sur combien de lettres on compare deux mots pour EF-E6.
#:
#: ⚠️ **Cinq, et pas le mot entier.** La première version comparait des
#: mots exacts, et elle ratait précisément l'exemple que le cahier
#: donne : « solide » n'est pas « solides », donc *« des résultats
#: solides […] un ensemble solide »* passait. Un test l'a dit avant que
#: quiconque lise un bulletin. Cinq lettres attrapent aussi
#: « régulier » / « régularité », ce qui est le même phénomène.
RACINE_COMPAREE = 5


def racine(mot: str) -> str:
    """Le début d'un mot, pour comparer « solide » et « solides »."""
    return mot.strip(".,;:!?'«»…").lower()[:RACINE_COMPAREE]


def moins_repetitive(candidates: tuple[str, ...], deja: str) -> str:
    """EF-E6 — celle qui répète le moins ce qui précède.

    *« C'est ce qui évite "des résultats solides […] un ensemble
    solide". »* On compare les RACINES des mots de plus de quatre
    lettres déjà employés ; à égalité, la première l'emporte, ce qui
    garde la formulation par défaut quand le choix ne change rien.
    """
    deja_dites = {racine(m) for m in deja.split() if len(m) > 4}

    def repetitions(phrase: str) -> int:
        return sum(1 for m in phrase.split()
                   if len(m) > 4 and racine(m) in deja_dites)

    return min(candidates, key=repetitions)


def choisir_conclusion(niveaux: dict[str, int], palier: str | None,
                       sens: str | None) -> str:
    """EF-E8 — la conclusion dépend de ce qui DOMINE.

    L'ordre des tests EST la règle, et il se lit comme le cahier l'écrit :
    *« le comportement s'il est le sujet, le défaut d'organisation s'il
    prime, la tendance entre trimestres sinon, et à défaut les seules
    notes »*.

    ``niveaux`` donne la TEINTE de chaque critère coché (1-4).
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
    """L'appréciation d'EF-E2, sous les 400 caractères d'EF-E4.

    ``observations`` : ``critère → (libellé long du niveau, teinte)``.

    Les phrases sont composées dans l'ordre de LECTURE, puis coupées dans
    l'ordre de SACRIFICE : les deux listes sont différentes et c'est
    voulu. Couper la plus longue donnerait un texte plus court et faux.
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
    """Le nom de la phrase que porte un critère, pour les deux
    ordres — celui du sacrifice et celui de la lecture."""
    return {
        "Comportement": "comportement",
        "Travail": "travail",
        "Participation": "participation",
        "Matériel, ponctualité": "materiel",
    }.get(critere, critere.lower())


def assembler(phrases: dict[str, str]) -> str:
    """Coupe jusqu'à tenir sous :data:`LIMITE`, dans l'ordre de sacrifice.

    On retire à partir de la FIN de :data:`SACRIFICE` — la dernière de la
    liste est la plus sacrifiable — et on ne descend jamais en dessous du
    noyau : travail, comportement, conclusion.
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


# ── Le bilan de classe — EF-F1 à EF-F4 ────────────────────────────────

#: Les seuils d'EF-F3 : une difficulté n'est nommée qu'au-delà d'une
#: proportion. En dessous, elle existe et ne se dit pas — nommer deux
#: élèves sur trente comme un trait de la classe serait faux.
SEUIL_PLUSIEURS = 0.30
SEUIL_QUELQUES = 0.15

#: EF-F4 : **en dessous de cinq, on ne parle pas.** *« Deux fiches sur
#: trente donneraient "la grande majorité", ce qui est faux. »*
MINIMUM_POUR_PARLER = 5


def proportion_dite(part: float) -> str | None:
    """« plusieurs », « quelques », ou rien du tout (EF-F3)."""
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
    """Le profil de classe d'EF-F1, et il PART de ce qui domine (EF-F2).

    *« Un bilan de classe se lit en salle des professeurs ; il doit être
    juste sans être accablant. »* La difficulté arrive donc en NUANCE,
    après le constat d'ensemble, et jamais comme sujet de la première
    phrase.
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

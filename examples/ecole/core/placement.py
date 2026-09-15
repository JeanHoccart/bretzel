"""core/placement — asseoir une classe. Pur Python, testable seul.

EF-G7 et EF-G9. Deux choses, et la seconde est la seule de l'application
qui ait le droit d'être aléatoire.

EF-G9 — la répartition, dans l'ordre où le cahier l'écrit
----------------------------------------------------------
1. **les élèves à mettre devant d'abord**, dans les deux premières
   rangées, *de préférence la première* — qu'ils y soient pour un
   aménagement, une vue fragile ou un choix manuel : **les trois se
   cumulent** ;
2. **tout premier remplissage** : par ordre alphabétique, en partant du
   FOND de la salle. *« C'est prévisible, et un premier plan n'a pas
   encore de raison d'être mélangé. »* ;
3. **sinon** : tirage au sort, plusieurs essais pour éviter d'asseoir
   côte à côte deux élèves à séparer.

**Jamais d'échec bloquant.** Au pire, le tirage qui viole le moins de
paires est retenu, et les conflits restants sont SIGNALÉS. Un plan qu'on
refuse de rendre laisse le professeur sans plan du tout ; un plan
imparfait qui se dit se corrige en deux glissers.

EF-G7 — une table est CALCULÉE, pas saisie
-------------------------------------------
*« Une table est deux élèves côte à côte : ils partagent une rangée avec
des colonnes consécutives. »* Il n'y a pas d'entité « table » (EF-G1) ;
l'allée qui sépare est ce qui coupe.
"""

from __future__ import annotations

import random
from itertools import pairwise

#: Combien de tirages on tente avant de garder le moins mauvais.
#: Vingt : au-delà, le gain mesuré sur trente élèves et trois paires est
#: nul, et le geste doit rester instantané.
ESSAIS = 20

#: Jusqu'à quelle rangée « devant » veut dire devant (EF-G9).
RANGEES_DEVANT = 2


def tables_de(places: list[dict]) -> list[tuple[int, int]]:
    """Les paires ``(place_a, place_b)`` qui forment une table (EF-G7).

    Deux places font une table quand elles sont sur la MÊME rangée, à des
    colonnes consécutives, et qu'**aucune allée ne les sépare** : c'est
    l'allée qui coupe, puisqu'il n'existe pas d'entité « table ».
    """
    par_rangee: dict[int, list[dict]] = {}
    for place in places:
        par_rangee.setdefault(place["rangee"], []).append(place)

    paires: list[tuple[int, int]] = []
    for rangee in par_rangee.values():
        rangee.sort(key=lambda p: p["colonne"])
        for gauche, droite in pairwise(rangee):
            if droite["colonne"] != gauche["colonne"] + 1:
                continue
            if droite["allee_avant"]:
                continue
            paires.append((gauche["id"], droite["id"]))
    return paires


def voisins_de(places: list[dict]) -> dict[int, set[int]]:
    """``place → places qui partagent sa table`` — l'entrée des conflits."""
    voisins: dict[int, set[int]] = {p["id"]: set() for p in places}
    for gauche, droite in tables_de(places):
        voisins[gauche].add(droite)
        voisins[droite].add(gauche)
    return voisins


def conflits(assises: dict[int, int], places: list[dict],
             separations: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Les paires à séparer qui se retrouvent quand même à la même table.

    ``assises`` : ``place_id → eleve_id``. Rend les paires d'ÉLÈVES en
    conflit, pas les places : c'est ce que l'écran doit nommer.
    """
    par_place = voisins_de(places)
    a_separer = {frozenset(paire) for paire in separations}
    trouves: set[frozenset] = set()
    for place_id, eleve_id in assises.items():
        for voisin in par_place.get(place_id, ()):
            autre = assises.get(voisin)
            if autre and frozenset({eleve_id, autre}) in a_separer:
                trouves.add(frozenset({eleve_id, autre}))
    return [tuple(sorted(paire)) for paire in trouves]


def repartir(
    *,
    eleves: list[dict],
    places: list[dict],
    devants: set[int],
    separations: list[tuple[int, int]],
    premier_remplissage: bool,
    graine: int | None = None,
) -> dict[int, int]:
    """Assied la classe. Rend ``place_id → eleve_id``.

    ``eleves`` doit porter ``id``, ``nom``, ``prenom``, ``amenagement``,
    ``vue_fragile`` — les trois raisons d'être devant SE CUMULENT avec le
    choix manuel de ``devants``.

    ``graine`` rend le tirage reproductible ; c'est ce qui permet de
    tester « au pire, le moins mauvais » sans écrire un test qui passe
    une fois sur trois.
    """
    libres = sorted(places, key=lambda p: (p["rangee"], p["colonne"]))
    if not libres or not eleves:
        return {}

    a_devant = [
        e for e in eleves
        if e["id"] in devants or e.get("amenagement")
        or e.get("vue_fragile")
    ]
    autres = [e for e in eleves if e not in a_devant]

    # Les places du devant, la première rangée EN PREMIER — c'est
    # « de préférence la première » d'EF-G9.
    devant = [p for p in libres if p["rangee"] <= RANGEES_DEVANT]
    reste = [p for p in libres if p["rangee"] > RANGEES_DEVANT]

    if premier_remplissage:
        # *« Par ordre alphabétique, en partant du fond de la salle. »*
        # Prévisible, et un premier plan n'a pas de raison d'être mélangé.
        autres = sorted(autres, key=lambda e: (e["nom"].lower(),
                                               e["prenom"].lower()))
        reste = sorted(reste, key=lambda p: (-p["rangee"], p["colonne"]))
        return asseoir_les_deux_groupes(a_devant, autres, devant, reste)

    tirage = random.Random(graine)
    meilleur: dict[int, int] = {}
    meilleur_cout = None
    for _ in range(ESSAIS):
        melanges = list(autres)
        tirage.shuffle(melanges)
        devant_melange = list(a_devant)
        tirage.shuffle(devant_melange)
        essai = asseoir_les_deux_groupes(devant_melange, melanges, devant, reste)
        cout = len(conflits(essai, places, separations))
        if meilleur_cout is None or cout < meilleur_cout:
            meilleur, meilleur_cout = essai, cout
        if cout == 0:
            break
    return meilleur


def asseoir_les_deux_groupes(
    a_devant: list[dict], autres: list[dict],
    devant: list[dict], reste: list[dict],
) -> dict[int, int]:
    """Pose les deux groupes sur les deux jeux de places, dans l'ordre.

    ⚠️ **Le gros de la classe part du FOND, pas de l'avant**, et c'est ce
    qui distingue cette fonction d'un remplissage naïf. EF-G9 dit deux
    choses en même temps : ceux qui doivent être devant y vont, et *« le
    tout premier remplissage se fait par ordre alphabétique **en partant
    du fond de la salle** »*. Une première version asseyait tout le monde
    à partir du premier rang : elle donnait le bon ORDRE alphabétique et
    la mauvaise MOITIÉ de la salle, ce qui ne se voit pas dans une liste
    et saute aux yeux sur un plan.

    Les débordements se croisent, et jamais on ne refuse d'asseoir :
    ce qui ne tient pas devant passe au fond, ce qui ne tient pas au fond
    remonte devant.
    """
    assises: dict[int, int] = {}
    file_devant = list(a_devant)
    file_autres = list(autres)

    for place in devant:
        if not file_devant:
            break
        assises[place["id"]] = file_devant.pop(0)["id"]

    for place in reste:
        if not file_autres:
            break
        assises[place["id"]] = file_autres.pop(0)["id"]

    # Ce qui reste debout prend les places encore libres, où qu'elles
    # soient. Le devant qui n'a pas tenu passe en premier : il reste plus
    # près du tableau que s'il partait tout au fond.
    en_attente = file_devant + file_autres
    for place in [*devant, *reste]:
        if not en_attente:
            break
        if place["id"] in assises:
            continue
        assises[place["id"]] = en_attente.pop(0)["id"]
    return assises


def rangees_du_gabarit(longueurs: list[int], allees: list[int],
                       largeur: int) -> list[dict]:
    """Le tracé d'EF-G2 : ``[{rangee, colonne, allee_avant}, …]``.

    ``allees`` donne les COLONNES devant lesquelles le passage s'ouvre —
    et c'est le piège n° 6 : *« une allée est un COULOIR, pas une case »*.
    Le stockage reste par place ; la décision est par colonne, donc elle
    s'applique à toutes les rangées où cette colonne existe (EF-G4).

    **La colonne 1 est refusée** (EF-G5) : une allée devant la première
    place ne sépare personne et décalerait la rangée entière.
    """
    ouvertes = {c for c in allees if c > 1}
    tracé: list[dict] = []
    for rangee, longueur in enumerate(longueurs, start=1):
        for colonne in range(1, longueur + 1):
            tracé.append({
                "rangee": rangee,
                "colonne": colonne,
                # EF-G6 : la largeur vaut pour TOUTE la salle — une salle
                # a un passage, pas dix largeurs.
                "allee_avant": largeur if colonne in ouvertes else 0,
            })
    return tracé

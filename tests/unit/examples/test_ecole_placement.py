"""Asseoir une classe : les règles d'EF-G qui se testent sans écran.

Deux pièges MESURÉS du cahier vivent ici, et ce sont les deux plus
coûteux du lot 7 :

- **n° 6** — *« une allée posée sur UNE PLACE et non sur la colonne : un
  passage ouvert sur trois rangées et fermé sur deux »*. Le tracé le
  ferme par construction ;
- **n° 7** — *« écrire la largeur d'allée en dur, déduite du cycle :
  c'est la SALLE qu'on décrit, pas le cycle »*. Une seule largeur, posée
  à l'appel.

Et la propriété qui compte plus que le résultat : **jamais d'échec
bloquant**. La répartition rend toujours un plan, même quand elle ne peut
pas tenir toutes les contraintes.
"""

from __future__ import annotations

from examples.ecole.core.placement import (
    RANGEES_DEVANT,
    conflits,
    rangees_du_gabarit,
    repartir,
    tables_de,
)


def place(place_id: int, rangee: int, colonne: int,
          allee: int = 0) -> dict:
    return {"id": place_id, "rangee": rangee, "colonne": colonne,
            "allee_avant": allee}


def eleve(eleve_id: int, nom: str, *, amenagement: str = "",
          vue_fragile: int = 0) -> dict:
    return {"id": eleve_id, "nom": nom, "prenom": "X",
            "amenagement": amenagement, "vue_fragile": vue_fragile}


#: Une rangée de six places, une allée avant la 3e et avant la 5e.
RANGEE = [place(1, 1, 1), place(2, 1, 2), place(3, 1, 3, allee=60),
          place(4, 1, 4), place(5, 1, 5, allee=60), place(6, 1, 6)]


# ── EF-G7 · une table est CALCULÉE ────────────────────────────────────

def test_deux_places_voisines_sans_allee_font_une_table() -> None:
    paires = tables_de(RANGEE)
    assert (1, 2) in paires
    assert (3, 4) in paires
    assert (5, 6) in paires


def test_une_allee_coupe_la_table() -> None:
    """Il n'y a pas d'entité « table » (EF-G1) : c'est l'allée qui coupe."""
    paires = tables_de(RANGEE)
    assert (2, 3) not in paires
    assert (4, 5) not in paires


def test_deux_rangees_differentes_ne_font_jamais_une_table() -> None:
    paires = tables_de([place(1, 1, 1), place(2, 2, 1)])
    assert paires == []


# ── EF-G4, EF-G5, EF-G6 · l'allée est un couloir ──────────────────────

def test_une_allee_souvre_sur_toute_la_colonne_entiere() -> None:
    """**Piège n° 6.** *« Un passage ouvert sur trois rangées et fermé sur
    deux ne ressemble à aucune salle réelle. »*"""
    trace = rangees_du_gabarit([4, 4, 4], allees=[3], largeur=60)
    en_troisieme = [p for p in trace if p["colonne"] == 3]
    assert len(en_troisieme) == 3
    assert all(p["allee_avant"] == 60 for p in en_troisieme)


def test_une_allee_devant_la_premiere_place_est_refusee() -> None:
    """EF-G5 : elle ne sépare personne et décalerait la rangée entière."""
    trace = rangees_du_gabarit([4], allees=[1, 3], largeur=60)
    premiere = next(p for p in trace if p["colonne"] == 1)
    assert premiere["allee_avant"] == 0


def test_seules_bougent_les_rangees_ou_la_colonne_existe() -> None:
    """Une rangée plus courte n'a pas de colonne 5 : rien à y ouvrir."""
    trace = rangees_du_gabarit([6, 3], allees=[5], largeur=60)
    assert [p["allee_avant"] for p in trace if p["rangee"] == 2] == [0, 0, 0]


def test_une_seule_largeur_pour_toute_la_salle() -> None:
    """**Piège n° 7** : c'est la salle qu'on décrit, pas le cycle."""
    trace = rangees_du_gabarit([6, 6], allees=[3, 5], largeur=80)
    largeurs = {p["allee_avant"] for p in trace if p["allee_avant"]}
    assert largeurs == {80}


# ── EF-G9 · la répartition ────────────────────────────────────────────

SALLE = [place(i, r, c) for i, (r, c) in enumerate(
    [(r, c) for r in range(1, 5) for c in range(1, 5)], start=1)]


def test_le_premier_remplissage_est_alphabetique_depuis_le_fond() -> None:
    """*« C'est prévisible, et un premier plan n'a pas encore de raison
    d'être mélangé. »*"""
    eleves = [eleve(1, "Zola"), eleve(2, "Balzac"), eleve(3, "Hugo")]
    assises = repartir(eleves=eleves, places=SALLE, devants=set(),
                       separations=[], premier_remplissage=True)
    par_place = {p["id"]: p for p in SALLE}
    places_occupees = sorted(assises, key=lambda pid: (
        -par_place[pid]["rangee"], par_place[pid]["colonne"]))
    assert [assises[pid] for pid in places_occupees] == [2, 3, 1]
    assert par_place[places_occupees[0]]["rangee"] == 4


def test_les_trois_raisons_detre_devant_se_cumulent() -> None:
    """EF-G9 : *« qu'ils y soient pour un aménagement, une vue fragile ou
    un choix manuel : les trois se cumulent »*."""
    eleves = [
        eleve(1, "Aaa"),
        eleve(2, "Bbb", amenagement="PAP"),
        eleve(3, "Ccc", vue_fragile=1),
        eleve(4, "Ddd"),
    ]
    assises = repartir(eleves=eleves, places=SALLE, devants={4},
                       separations=[], premier_remplissage=True)
    par_place = {p["id"]: p for p in SALLE}
    devant = {assises[pid] for pid in assises
              if par_place[pid]["rangee"] <= RANGEES_DEVANT}
    assert {2, 3, 4} <= devant


def test_le_tirage_evite_dasseoir_cote_a_cote_deux_eleves_a_separer() -> None:
    eleves = [eleve(i, f"N{i}") for i in range(1, 9)]
    assises = repartir(eleves=eleves, places=SALLE, devants=set(),
                       separations=[(1, 2)], premier_remplissage=False,
                       graine=7)
    assert conflits(assises, SALLE, [(1, 2)]) == []


def test_jamais_dechec_bloquant_meme_quand_cest_impossible() -> None:
    """*« Au pire le tirage qui viole le moins de paires est retenu, et
    les conflits restants sont signalés. »*

    Deux places côte à côte, deux élèves à séparer : c'est impossible. La
    fonction rend quand même un plan — un plan refusé laisserait le
    professeur sans rien.
    """
    deux = [place(1, 1, 1), place(2, 1, 2)]
    assises = repartir(eleves=[eleve(1, "A"), eleve(2, "B")], places=deux,
                       devants=set(), separations=[(1, 2)],
                       premier_remplissage=False, graine=1)
    assert len(assises) == 2
    assert conflits(assises, deux, [(1, 2)]) == [(1, 2)]


def test_une_salle_vide_ou_une_classe_vide_ne_leve_pas() -> None:
    assert repartir(eleves=[], places=SALLE, devants=set(), separations=[],
                    premier_remplissage=True) == {}
    assert repartir(eleves=[eleve(1, "A")], places=[], devants=set(),
                    separations=[], premier_remplissage=True) == {}


def test_plus_deleves_que_de_places_nen_perd_aucune() -> None:
    """Ce qui ne tient pas reste debout ; rien ne lève, et la salle est
    pleine."""
    eleves = [eleve(i, f"N{i:02d}") for i in range(1, 30)]
    assises = repartir(eleves=eleves, places=SALLE, devants=set(),
                       separations=[], premier_remplissage=True)
    assert len(assises) == len(SALLE)

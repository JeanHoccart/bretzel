"""kanban/donnees — le tableau, en mémoire, partagé par TOUT LE MONDE.

``AppState`` et pas ``SessionState`` : un tableau d'équipe est un objet
UNIQUE dont toutes les fenêtres parlent. C'est la portée qui fait de
l'app un outil collaboratif, pas un mécanisme de synchronisation écrit à
la main — et c'est la mécanique que cet exemple met en scène.

Aucune base de données : redémarrer le serveur remet le tableau à son
état de départ. Deux autres démos (``crm``, ``mad``) montrent
SQLite ; ici la source de vérité tient en mémoire, et c'est ce qui rend
la démonstration lisible en un fichier.

⚠️ **Les identifiants de la graine sont ÉCRITS, jamais tirés au sort.**
Un ``default_factory`` sur un état serveur est ré-évalué à chaque requête
tant qu'aucune mutation ne l'a persisté : un ``uuid4`` ici battrait des
identifiants neufs à chaque rendu, et le premier glisser viserait une
carte qui n'existe déjà plus.

**L'ordre dans une colonne est un ``rang`` flottant**, pas la position
dans la liste. Déposer entre deux cartes prend le milieu de leurs deux
rangs, donc une seule carte est réécrite — et c'est ce qui rend
``annuler`` trivial : restaurer une carte suffit, aucun voisin n'a bougé.
Le prix est écrit : après une trentaine de dépôts au même endroit, les
flottants n'ont plus de milieu à offrir. Une vraie app renumérote
(``examples/crm`` le fait) ; un tableau de démo n'en a pas le temps.
"""

from __future__ import annotations

import time
from typing import Any

from bretzel import Feature
from bretzel.state import AppState, field

#: Les colonnes, dans l'ordre du tableau, avec leur **limite d'en-cours**.
#: ``None`` = pas de limite. La limite est une règle du tableau, pas un
#: décor : elle refuse un dépôt, et c'est le serveur qui arbitre.
COLONNES: tuple[tuple[str, str, int | None], ...] = (
    ("a_faire", "À faire", None),
    ("en_cours", "En cours", 3),
    ("en_revue", "En revue", 2),
    ("fini", "Terminé", None),
)

CLES: tuple[str, ...] = tuple(cle for cle, _, _ in COLONNES)
LIBELLES: dict[str, str] = {cle: lib for cle, lib, _ in COLONNES}
LIMITES: dict[str, int | None] = {cle: lim for cle, _, lim in COLONNES}

#: L'équipe. La clé sert d'identité de session (« tu es… ») et d'assigné
#: sur une carte — deux rôles pour une table, parce que c'est la même
#: personne.
MEMBRES: tuple[tuple[str, str, str, str], ...] = (
    ("cam", "Camille Roux", "CR", "primary"),
    ("sam", "Samuel Diallo", "SD", "info"),
    ("noa", "Noa Berger", "NB", "warning"),
    ("lea", "Léa Marchand", "LM", "success"),
)

NOMS: dict[str, str] = {cle: nom for cle, nom, _, _ in MEMBRES}
INITIALES: dict[str, str] = {cle: ini for cle, _, ini, _ in MEMBRES}
COULEURS: dict[str, str] = {cle: coul for cle, _, _, coul in MEMBRES}

#: Les étiquettes disponibles, avec la couleur sémantique qui les rend.
ETIQUETTES: tuple[tuple[str, str, str], ...] = (
    ("bug", "Bug", "error"),
    ("ux", "UX", "info"),
    ("perf", "Perf", "warning"),
    ("doc", "Doc", "muted"),
    ("infra", "Infra", "success"),
)

LIB_ETIQUETTE: dict[str, str] = {cle: lib for cle, lib, _ in ETIQUETTES}
COUL_ETIQUETTE: dict[str, str] = {cle: coul for cle, _, coul in ETIQUETTES}


def tache(
    ident: str,
    colonne: str,
    titre: str,
    qui: str,
    etiquettes: tuple[str, ...] = (),
    echeance: str = "",
    points: int = 0,
    description: str = "",
    sous_taches: tuple[tuple[str, bool], ...] = (),
    commentaires: tuple[tuple[str, str], ...] = (),
) -> dict[str, Any]:
    """Une carte complète, avec ses défauts. Le ``rang`` vient après."""
    return {
        "id": ident,
        "colonne": colonne,
        "titre": titre,
        "qui": qui,
        "etiquettes": list(etiquettes),
        "echeance": echeance,
        "points": points,
        "description": description,
        "sous_taches": [{"texte": t, "fait": f} for t, f in sous_taches],
        "commentaires": [
            {"qui": q, "texte": t, "t": 0.0} for q, t in commentaires
        ],
        "rang": 0.0,
    }


#: La graine, colonne par colonne et dans l'ordre d'affichage. Un vrai
#: sprint d'équipe produit : assez de matière pour que le tableau déborde
#: en hauteur, ce qui est la seule façon de voir une colonne défiler.
GRAINE: tuple[dict[str, Any], ...] = (
    tache(
        "c01", "a_faire", "Écran de connexion : mot de passe oublié", "sam",
        ("ux",), "2026-09-18", 3,
        "Le lien existe mais renvoie une 404 depuis la refonte du routage. "
        "À rebrancher sur le nouveau flux de jetons à usage unique.",
        (("Rebrancher la route", False), ("Gabarit de courriel", False),
         ("Expiration à 30 min", False)),
    ),
    tache(
        "c02", "a_faire", "Journal d'audit exportable en CSV", "noa",
        ("infra", "doc"), "2026-09-25", 5,
        "Les clients grands comptes le demandent pour leurs audits "
        "internes. Une ligne par action, l'export tourne en tâche de fond.",
        (("Requête paginée", False), ("Écriture du fichier", False),
         ("Bouton et notification", False), ("Documenter le format", False)),
    ),
    tache(
        "c03", "a_faire", "Corriger le calcul de TVA sur les avoirs", "lea",
        ("bug",), "2026-09-15", 2,
        "Un avoir émis après un changement de taux applique le taux du "
        "jour, pas celui de la facture d'origine.",
        (("Reproduire sur un jeu réel", True), ("Corriger", False)),
        (("cam", "Signalé par deux clients cette semaine, à prioriser."),),
    ),
    tache(
        "c04", "a_faire", "Refonte de la page de tarifs", "cam",
        ("ux",), "", 8,
        "Trois plans au lieu de cinq, et le comparatif passe sous le pli. "
        "Maquettes validées, reste l'intégration.",
    ),
    tache(
        "c05", "a_faire", "Retirer la dépendance à moment.js", "noa",
        ("perf",), "", 3,
        "68 Ko pour formater trois dates. Le formatage natif suffit "
        "depuis qu'on ne supporte plus les vieux navigateurs.",
    ),
    tache(
        "c06", "a_faire", "Guide de démarrage en dix minutes", "sam",
        ("doc",), "2026-10-02", 5,
        "Le taux d'abandon à l'inscription se joue dans les cinq "
        "premières minutes. Un parcours écrit, testé sur trois personnes.",
    ),
    tache(
        "c07", "en_cours", "Fusion des comptes en double", "lea",
        ("bug", "infra"), "2026-09-12", 8,
        "Deux comptes créés avec la même adresse en majuscules et en "
        "minuscules. Il faut fusionner sans perdre l'historique.",
        (("Détection des doublons", True), ("Écran de fusion", True),
         ("Rejeu de l'historique", False)),
        (("noa", "La détection tourne, 412 paires trouvées en base."),
         ("lea", "Je prends l'écran de fusion, dispo demain.")),
    ),
    tache(
        "c08", "en_cours", "Cache des tableaux de bord", "noa",
        ("perf",), "2026-09-16", 5,
        "Le tableau de bord recalcule douze agrégats à chaque chargement. "
        "Un cache de cinq minutes suffit, invalidé à l'écriture.",
        (("Choisir la clé de cache", True), ("Invalidation", False)),
    ),
    tache(
        "c09", "en_cours", "Accessibilité du sélecteur de dates", "cam",
        ("ux", "bug"), "2026-09-19", 3,
        "Impossible d'atteindre le calendrier au clavier, et le lecteur "
        "d'écran annonce « bouton » sans dire quelle date.",
        (("Ordre de tabulation", True), ("Étiquettes ARIA", False),
         ("Test au lecteur d'écran", False)),
    ),
    tache(
        "c10", "en_revue", "Limitation de débit sur l'API publique", "sam",
        ("infra",), "2026-09-11", 5,
        "Cent requêtes par minute et par jeton, avec les en-têtes "
        "standard pour que les clients sachent où ils en sont.",
        (("Compteur en mémoire", True), ("En-têtes de quota", True),
         ("Documentation", True)),
        (("cam", "Relu, il manque juste le cas du jeton expiré."),),
    ),
    tache(
        "c11", "en_revue", "Traduction espagnole de l'interface", "lea",
        ("doc", "ux"), "", 8,
        "1 240 chaînes relues par une traductrice native. Reste à vérifier "
        "les débordements sur les libellés longs.",
        (("Extraction des chaînes", True), ("Relecture", True),
         ("Vérifier les débordements", False)),
    ),
    tache(
        "c12", "fini", "Migration vers le nouveau moteur de facturation",
        "noa", ("infra",), "", 13,
        "Bascule faite un dimanche matin, aucune interruption visible. "
        "L'ancien moteur reste lisible en lecture seule jusqu'en décembre.",
        (("Double écriture", True), ("Bascule", True), ("Nettoyage", True)),
    ),
    tache(
        "c13", "fini", "Connexion par Google et Microsoft", "cam",
        ("infra", "ux"), "", 8,
        "Les deux fournisseurs branchés, le compte existant est rattaché "
        "par l'adresse vérifiée.",
        (("Google", True), ("Microsoft", True), ("Rattachement", True)),
    ),
    tache(
        "c14", "fini", "Corriger l'export PDF tronqué au-delà de 40 pages",
        "sam", ("bug",), "", 3,
        "Le générateur coupait à la quarantième page sans rien dire. "
        "Le tampon était vidé trop tôt.",
        (("Reproduire", True), ("Corriger", True), ("Test de non-régression",
                                                    True)),
    ),
    tache(
        "c15", "fini", "Bandeau de consentement aux cookies", "lea",
        ("doc",), "", 2,
        "Refus par défaut, aucun traceur avant le clic. Validé par le "
        "cabinet.",
    ),
)


def copie(carte: dict[str, Any]) -> dict[str, Any]:
    """Une carte détachée de l'originale, listes imbriquées comprises.

    ⚠️ ``{**carte}`` ne suffit PAS : les trois listes resteraient
    partagées, donc l'instantané « avant » du journal changerait en même
    temps que la carte qu'il est censé garder — et annuler ne rendrait
    rien.
    """
    return {
        **carte,
        "etiquettes": list(carte["etiquettes"]),
        "sous_taches": [dict(s) for s in carte["sous_taches"]],
        "commentaires": [dict(c) for c in carte["commentaires"]],
    }


def semer() -> list[dict[str, Any]]:
    """La graine, avec un rang attribué PAR POSITION dans sa colonne.

    Les rangs partent de 1, 2, 3… donc il y a toujours un milieu libre
    entre deux voisins pour les premiers dépôts.
    """
    compteurs: dict[str, float] = dict.fromkeys(CLES, 0.0)
    cartes: list[dict[str, Any]] = []
    for modele in GRAINE:
        carte = copie(modele)
        compteurs[carte["colonne"]] += 1.0
        carte["rang"] = compteurs[carte["colonne"]]
        cartes.append(carte)
    return cartes


class Tableau(AppState):
    """Le tableau : ses cartes, et l'histoire de ce qui leur est arrivé.

    ``journal`` + ``curseur`` forment une pile d'annulation classique :
    le curseur compte les entrées APPLIQUÉES, annuler le recule, rétablir
    l'avance, et une action neuve tronque tout ce qui suivait. Chaque
    entrée porte la carte AVANT et APRÈS — restaurer un dictionnaire
    suffit, il n'y a pas de mouvement à rejouer à l'envers.

    L'histoire est celle du TABLEAU, pas celle d'une personne : sur un
    tableau partagé, n'importe qui peut défaire le dernier geste, et le
    journal dit qui l'avait fait.
    """

    cartes: list[dict[str, Any]] = field(default_factory=semer)
    journal: list[dict[str, Any]] = field(default_factory=list)
    curseur: int = field(default=0)


def carte_par_id(ident: str) -> dict[str, Any] | None:
    """La carte portant cet identifiant, ou ``None``."""
    for carte in Tableau().cartes:
        if carte["id"] == ident:
            return carte
    return None


def correspond(carte: dict[str, Any], qui: str, etiquette: str,
               texte: str) -> bool:
    """Est-ce que cette carte survit aux trois filtres du bandeau ?"""
    if qui != "tous" and carte["qui"] != qui:
        return False
    if etiquette != "toutes" and etiquette not in carte["etiquettes"]:
        return False
    if texte:
        cible = (carte["titre"] + " " + carte["description"]).casefold()
        if texte.casefold() not in cible:
            return False
    return True


def colonne_de(cle: str, qui: str = "tous", etiquette: str = "toutes",
               texte: str = "") -> list[dict[str, Any]]:
    """Les cartes VISIBLES d'une colonne, dans l'ordre des rangs.

    Les filtres sont appliqués ici, donc la même fonction sert au rendu
    et au calcul des voisins d'un dépôt. Les faire diverger reviendrait à
    insérer une carte entre deux voisins que le lecteur ne voyait pas.
    """
    return sorted(
        (c for c in Tableau().cartes
         if c["colonne"] == cle and correspond(c, qui, etiquette, texte)),
        key=lambda c: c["rang"],
    )


def occupation(cle: str) -> int:
    """Combien de cartes DANS la colonne — filtres exclus.

    Une limite d'en-cours compte le travail réel, pas ce qu'un filtre
    laisse voir. Masquer les cartes de quelqu'un d'autre ne libère pas
    de place.
    """
    return sum(1 for c in Tableau().cartes if c["colonne"] == cle)


def pleine(cle: str) -> bool:
    """La colonne refuse-t-elle une carte de plus ?"""
    limite = LIMITES.get(cle)
    return limite is not None and occupation(cle) >= limite


def avancement(carte: dict[str, Any]) -> tuple[int, int]:
    """Sous-tâches faites, sous-tâches en tout."""
    sous = carte["sous_taches"]
    return sum(1 for s in sous if s["fait"]), len(sous)


def entre(avant: float | None, apres: float | None) -> float:
    """Un rang libre entre deux voisins, l'un ou l'autre pouvant manquer."""
    if avant is None and apres is None:
        return 1.0
    if avant is None:
        return float(apres) - 1.0  # type: ignore[arg-type]
    if apres is None:
        return float(avant) + 1.0
    return (float(avant) + float(apres)) / 2.0


def depuis(instant: float) -> str:
    """« il y a 12 s » — dérivé à l'affichage, jamais stocké.

    Une date écrite dans l'état serait fausse la seconde d'après, et
    c'est exactement le genre de champ qu'on oublie de mettre à jour
    quand une nouvelle écriture arrive.
    """
    if not instant:
        return ""
    ecart = max(0, int(time.time() - instant))
    if ecart < 60:
        return f"il y a {ecart} s"
    if ecart < 3600:
        return f"il y a {ecart // 60} min"
    if ecart < 86400:
        return f"il y a {ecart // 3600} h"
    return f"il y a {ecart // 86400} j"


def echeance_lisible(valeur: str) -> str:
    """``2026-09-18`` → ``18/09``. Vide reste vide."""
    if not valeur or len(valeur) < 10:
        return ""
    return f"{valeur[8:10]}/{valeur[5:7]}"


feature = Feature(
    name="donnees", kind="data",
    provides=[Tableau, COLONNES, MEMBRES, ETIQUETTES, semer, copie,
              carte_par_id, colonne_de, occupation, pleine, correspond,
              avancement, entre, depuis, echeance_lisible],
)

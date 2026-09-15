"""core/seed — la fabrique du jeu de données. ~262 000 lignes, déterministe.

Appelé une seule fois par ``db.init_db()`` (marqueur ``SEED_VERSION``). Aucun
``random`` global : un ``Random(GRAINE)`` local, donc deux machines obtiennent
la même base, et un id de ligne cité dans un test reste le même demain.

**Pourquoi ces volumes.** 50 000 comptes, c'est le chiffre qui interdit à la
datatable de l'écran 2 le mode liste : le composant ne peut pas trier en
Python ce que la page ne charge pas. 120 000 contacts, c'est ce qui rend la
liste sélectionnable de l'écran 3 impossible à rendre d'un bloc. Tout le
chantier tient sur cette contrainte-là.
"""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta

from examples.crm.core.domain import (
    ACTIVITY_KEYS,
    COUNTRIES,
    DEMO_PASSWORD,
    INDUSTRIES,
    OWNERS,
    POSITION_STEP,
    SIZES,
    STAGE_KEYS,
    STATUS_KEYS,
    TODAY,
    login_for,
)
from examples.crm.core.security import hash_password

#: Fixe. Change de graine et tous les ids de la base changent.
GRAINE = 20260819

N_ACCOUNTS = 50_000
N_CONTACTS = 120_000
N_DEALS = 12_000
N_ACTIVITIES = 60_000
N_NOTES = 20_000

_ROOTS = (
    "Alto", "Borea", "Cedra", "Delvo", "Ectra", "Fabri", "Golia", "Helvi",
    "Ionis", "Jorva", "Kelvo", "Luma", "Movia", "Norda", "Olvia", "Prima",
    "Quadra", "Roska", "Selva", "Tavio", "Ultra", "Vanto", "Welda", "Xenia",
    "Yara", "Zelio", "Arca", "Brida", "Calto", "Doria", "Elvia", "Ferro",
    "Grano", "Hydra", "Indra", "Junia", "Korva", "Livo", "Meridi", "Nexo",
    "Orbia", "Palma", "Quilo", "Rovia", "Salta", "Terra", "Umbra", "Vesta",
    "Wilda", "Xanto", "Yolda", "Zarma", "Astra", "Brego", "Ciela", "Dorne",
    "Erial", "Fonta", "Grive", "Hosta",
)
_STEMS = (
    "tech", "logic", "mont", "flux", "corp", "labs", "soft", "prod",
    "gest", "form", "care", "med", "bat", "agro", "élec", "net",
    "data", "vision", "plus", "pro", "concept", "systems", "group", "partners",
    "services", "solutions", "industries", "consulting", "digital", "invest",
)
_SUFFIXES = ("SA", "SAS", "SARL", "& Cie", "Group", "France", "Europe",
             "International", "Holding", "", "", "")

_FIRST = (
    "Aïcha", "Marc", "Sofia", "Léa", "Tom", "Clara", "Hugo", "Nadia",
    "Julien", "Émilie", "Karim", "Chloé", "Antoine", "Fatou", "Louis",
    "Manon", "Yanis", "Camille", "Théo", "Inès", "Paul", "Sarah", "Nathan",
    "Zoé", "Lucas", "Amina", "Mathis", "Jade", "Gabriel", "Alice", "Rayan",
    "Louise", "Adam", "Anna", "Noah", "Eva", "Ismaël", "Julia", "Enzo",
    "Lina", "Victor", "Maya", "Samuel", "Nora", "Élias", "Rose", "Malik",
    "Iris", "Bastien", "Salomé",
)
_LAST = (
    "Benali", "Dubois", "Rossi", "Martin", "Nguyen", "Weiss", "Lefèvre",
    "Moreau", "Girard", "Bernard", "Fontaine", "Lacroix", "Petit", "Roux",
    "Vincent", "Fournier", "Morel", "Andre", "Mercier", "Blanc", "Guerin",
    "Boyer", "Garnier", "Chevalier", "Francois", "Legrand", "Gauthier",
    "Perrin", "Robin", "Clement", "Morin", "Dumont", "Lopez", "Fabre",
    "Berger", "Blanchard", "Marchand", "Duval", "Denis", "Dumas", "Rey",
    "Leroux", "Renaud", "Bertrand", "Colin", "Barbier", "Schmitt", "Aubert",
    "Charpentier", "Poirier",
)
_TITLES = (
    "Directeur des achats", "Responsable IT", "DAF", "Chef de projet",
    "Directrice générale", "Responsable qualité", "Acheteur", "DRH",
    "Responsable logistique", "Directeur technique", "Assistante de direction",
    "Responsable marketing", "Contrôleur de gestion", "Chargé d'affaires",
)
_DEAL_SUBJECTS = (
    "Renouvellement annuel", "Extension multi-sites", "Migration du parc",
    "Licences supplémentaires", "Contrat cadre", "Pilote sur 3 mois",
    "Refonte du poste de travail", "Module analytique", "Support premium",
    "Déploiement européen", "Passage à l'offre entreprise", "Audit + formation",
)
_ACTIVITY_SUBJECTS = {
    "call": ("Appel de découverte", "Point d'avancement", "Relance devis",
             "Appel de clôture", "Prise de contact"),
    "email": ("Envoi de la proposition", "Relance sans réponse",
              "Récapitulatif de réunion", "Envoi des CGV", "Réponse technique"),
    "meeting": ("Réunion de cadrage", "Démonstration produit",
                "Comité de pilotage", "Atelier besoins", "Revue de contrat"),
    "note": ("Compte rendu interne", "Contexte concurrentiel",
             "Budget confirmé", "Changement d'interlocuteur", "Point vigilance"),
    "task": ("Préparer le devis", "Envoyer les références",
             "Planifier la démo", "Valider la remise", "Relancer la semaine 38"),
}
_NOTE_BODIES = (
    "Interlocuteur réactif, préfère être joint le matin.",
    "Budget arbitré au niveau du groupe — décision en comité.",
    "A comparé avec deux concurrents, sensible au coût de migration.",
    "Renouvellement conditionné à la reprise de l'historique.",
    "Demande une clause de réversibilité dans le contrat cadre.",
    "Passage en revue annuelle prévu, garder le contact tiède.",
    "Le service achats impose un appel d'offres au-delà de 50 k€.",
    "Sponsor interne identifié : la direction technique.",
)

#: Poids des étapes : un pipeline réel n'est pas uniforme — il y a beaucoup
#: de pistes et peu de négociations en cours.
_STAGE_WEIGHTS = (30, 22, 16, 10, 14, 8)

_STATUS_WEIGHTS = (45, 30, 15, 10)


def iso_at(day_offset: int) -> str:
    """Une date ISO à ``day_offset`` jours de :data:`TODAY` (négatif = passé)."""
    return (TODAY + timedelta(days=day_offset)).isoformat()


def build_accounts(rng: random.Random) -> list[tuple]:
    rows = []
    for i in range(1, N_ACCOUNTS + 1):
        country, cities = rng.choice(COUNTRIES)
        size = rng.choice(SIZES)
        # L'ARR suit la taille : un « grand compte » à 900 € rendrait tout
        # tri par montant absurde à l'œil.
        floor = {"TPE": 1, "PME": 8, "ETI": 40, "Grand compte": 200}[size]
        name = (
            f"{rng.choice(_ROOTS)}"
            f"{rng.choice(_STEMS)} "
            f"{rng.choice(_SUFFIXES)}"
        ).strip()
        rows.append((
            i,
            name,
            rng.choice(INDUSTRIES),
            country,
            rng.choice(cities),
            size,
            rng.randint(floor, floor * 12) * 1_000,
            rng.choice(OWNERS),
            iso_at(-rng.randint(30, 2_200)),
        ))
    return rows


def build_contacts(rng: random.Random,
                   owner_of: dict[int, str]) -> list[tuple]:
    """Les contacts. ``owner_of`` = le propriétaire de chaque compte.

    ⚠️ Le propriétaire est RECOPIÉ sur la ligne, comme pour les affaires
    et les activités. Ici c'est une dénormalisation pure — un contact n'a
    pas de propriétaire à lui, il a celui de son compte — et elle existe
    pour que le cadrage n'oblige pas à joindre (cf. le schéma).
    """
    rows = []
    statuses = list(STATUS_KEYS)
    for i in range(1, N_CONTACTS + 1):
        first = rng.choice(_FIRST)
        last = rng.choice(_LAST)
        # L'id dans l'email : 4 800 combinaisons prénom/nom pour 120 000
        # contacts, donc les homonymes sont garantis — et une adresse doit
        # rester unique pour que « rechercher par email » ait un sens.
        slug = f"{first[:1]}.{last}{i}".lower().replace(" ", "")
        account_id = rng.randint(1, N_ACCOUNTS)
        rows.append((
            i,
            account_id,
            first,
            last,
            f"{slug}@exemple.fr",
            f"0{rng.randint(1, 7)} {rng.randint(10, 99)} "
            f"{rng.randint(10, 99)} {rng.randint(10, 99)} "
            f"{rng.randint(10, 99)}",
            rng.choice(_TITLES),
            rng.choices(statuses, weights=_STATUS_WEIGHTS, k=1)[0],
            owner_of[account_id],
            iso_at(-rng.randint(1, 1_500)),
        ))
    return rows


def build_deals(rng: random.Random, owner_of: dict[int, str]) -> list[tuple]:
    """Les affaires. ``owner_of`` = le propriétaire de chaque compte.

    ⚠️ Le propriétaire d'une affaire **suit celui de son compte**, il n'est
    pas tiré à part. Il l'était jusqu'au 2026-08-19, et c'était incohérent
    dès qu'on regardait un portefeuille : le pipeline d'un commercial
    contenait des affaires sur des comptes appartenant à quelqu'un d'autre,
    et « mes comptes » ne recoupait pas « mes affaires ». Sans compte
    connecté, personne ne s'en apercevait ; avec l'authentification, c'est
    la première chose qu'on voit.
    """
    rows = []
    stages = list(STAGE_KEYS)
    # ``position`` = le rang dans SA colonne de kanban. Compté par étape :
    # c'est ce que l'écran 1 réordonne, et deux cartes ne peuvent pas
    # partager un rang sans que le drop devienne ambigu.
    #
    # Pas de 1, 2, 3 mais un PAS de 64 : insérer entre deux cartes prend le
    # milieu de leurs deux rangs, et sur des entiers consécutifs il n'y a pas
    # de milieu — chaque déplacement forcerait à renuméroter la colonne
    # entière (~2 000 lignes) dès le premier geste.
    next_position = dict.fromkeys(stages, 0)
    for i in range(1, N_DEALS + 1):
        stage = rng.choices(stages, weights=_STAGE_WEIGHTS, k=1)[0]
        next_position[stage] += POSITION_STEP
        account_id = rng.randint(1, N_ACCOUNTS)
        rows.append((
            i,
            account_id,
            rng.choice(_DEAL_SUBJECTS),
            stage,
            rng.randint(2, 600) * 1_000,
            owner_of[account_id],
            iso_at(rng.randint(-120, 180)),
            next_position[stage],
            iso_at(-rng.randint(10, 400)),
        ))
    return rows


def build_activities(
    rng: random.Random, contacts: list[tuple], owner_of: dict[int, str]
) -> list[tuple]:
    """Les activités. Même règle que les affaires : le propriétaire suit le
    compte, pas le hasard (cf. :func:`build_deals`)."""
    rows = []
    kinds = list(ACTIVITY_KEYS)
    for i in range(1, N_ACTIVITIES + 1):
        contact = rng.choice(contacts)
        kind = rng.choice(kinds)
        subjects = _ACTIVITY_SUBJECTS[kind]
        rows.append((
            i,
            contact[0],                    # contact_id
            contact[1],                    # account_id — dénormalisé exprès :
                                           # la fiche compte agrège par compte
                                           # sans passer par une jointure.
            kind,
            rng.choice(subjects),
            iso_at(-rng.randint(0, 400)),
            owner_of[contact[1]],
        ))
    return rows


def build_users() -> list[tuple]:
    """Les sept comptes : les six commerciaux du jeu de données, plus une
    direction qui n'a pas de portefeuille et les voit tous.

    Le sel est **dérivé du login**, pas tiré au hasard : le semis doit
    rester déterministe (deux machines, la même base). C'est la seule
    entorse acceptable, et elle ne concerne que des comptes de
    démonstration — ``hash_password`` sans ``salt=`` reste aléatoire, et
    c'est ce que l'app utilise si elle crée un compte.

    ``owner`` est la clé de jointure avec les données : c'est le nom qui
    apparaît dans ``accounts.owner``. La direction n'en a pas.
    """
    people = [
        (i, login_for(name), name, "commercial", name)
        for i, name in enumerate(OWNERS, start=1)
    ]
    people.append((len(OWNERS) + 1, "direction", "Direction commerciale",
                   "directeur", ""))
    return [
        (uid, login, display, hash_password(
            DEMO_PASSWORD, salt=hashlib.sha256(login.encode()).digest()[:16]
        ), role, owner)
        for uid, login, display, role, owner in people
    ]


def build_notes(rng: random.Random) -> list[tuple]:
    return [
        (
            i,
            rng.randint(1, N_CONTACTS),
            rng.choice(_NOTE_BODIES),
            rng.choice(OWNERS),
            iso_at(-rng.randint(0, 500)),
        )
        for i in range(1, N_NOTES + 1)
    ]


def build_seed() -> list[tuple[str, list[tuple]]]:
    """``[(table, lignes), …]`` dans l'ordre d'insertion (clés étrangères).

    Renvoie tout d'un bloc plutôt qu'un générateur : ``executemany`` veut une
    séquence, et les activités doivent relire les contacts déjà tirés pour
    pointer un couple (contact, compte) qui existe.
    """
    rng = random.Random(GRAINE)
    accounts = build_accounts(rng)
    # Le propriétaire de chaque compte, indexé une fois. C'est LUI qui décide
    # de celui de ses contacts, de ses affaires et de ses activités — sinon
    # « mes comptes » ne recoupe pas « mes affaires », et un portefeuille ne
    # veut rien dire.
    owner_of = {row[0]: row[7] for row in accounts}
    contacts = build_contacts(rng, owner_of)
    return [
        ("users", build_users()),
        ("accounts", accounts),
        ("contacts", contacts),
        ("deals", build_deals(rng, owner_of)),
        ("activities", build_activities(rng, contacts, owner_of)),
        ("notes", build_notes(rng)),
    ]

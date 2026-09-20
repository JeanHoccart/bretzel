"""core/seed — the data set factory. ~262 000 rows, deterministic.

Called once by ``db.init_db()`` (``SEED_VERSION`` marker). No global
``random``: a local ``Random(SEED_RNG)``, so two machines get the same
database, and a row id quoted in a test is still the same tomorrow.

**Why these volumes.** 50 000 accounts is the figure that forbids screen
2's datatable the list mode: the component cannot sort in Python what
the page does not load. 120 000 contacts is what makes screen 3's
selectable list impossible to render in one go. The whole work rests on
that constraint.
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

#: Fixed. Change the seed and every id in the database changes.
SEED_RNG = 20260819

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
    "gest", "form", "care", "med", "build", "agro", "volt", "net",
    "data", "vision", "plus", "pro", "concept", "systems", "group", "partners",
    "services", "solutions", "industries", "consulting", "digital", "invest",
)
_SUFFIXES = ("SA", "SAS", "SARL", "& Cie", "Group", "France", "Europe",
             "International", "Holding", "", "", "")

_FIRST = (
    "Aicha", "Marc", "Sofia", "Lea", "Tom", "Clara", "Hugo", "Nadia",
    "Julien", "Emily", "Karim", "Chloe", "Antoine", "Fatou", "Louis",
    "Manon", "Yanis", "Camille", "Theo", "Ines", "Paul", "Sarah", "Nathan",
    "Zoe", "Lucas", "Amina", "Mathis", "Jade", "Gabriel", "Alice", "Rayan",
    "Louise", "Adam", "Anna", "Noah", "Eva", "Ismael", "Julia", "Enzo",
    "Lina", "Victor", "Maya", "Samuel", "Nora", "Elias", "Rose", "Malik",
    "Iris", "Bastien", "Salome",
)
_LAST = (
    "Benali", "Dubois", "Rossi", "Martin", "Nguyen", "Weiss", "Lefevre",
    "Moreau", "Girard", "Bernard", "Fontaine", "Lacroix", "Petit", "Roux",
    "Vincent", "Fournier", "Morel", "Andre", "Mercier", "Blanc", "Guerin",
    "Boyer", "Garnier", "Chevalier", "Francois", "Legrand", "Gauthier",
    "Perrin", "Robin", "Clement", "Morin", "Dumont", "Lopez", "Fabre",
    "Berger", "Blanchard", "Marchand", "Duval", "Denis", "Dumas", "Rey",
    "Leroux", "Renaud", "Bertrand", "Colin", "Barbier", "Schmitt", "Aubert",
    "Charpentier", "Poirier",
)
_TITLES = (
    "Head of purchasing", "IT manager", "CFO", "Project manager",
    "Managing director", "Quality manager", "Buyer", "HR director",
    "Logistics manager", "Technical director", "Executive assistant",
    "Marketing manager", "Financial controller", "Account manager",
)
_DEAL_SUBJECTS = (
    "Annual renewal", "Multi-site rollout", "Estate migration",
    "Extra licences", "Framework agreement", "Three-month pilot",
    "Desktop overhaul", "Analytics module", "Premium support",
    "European rollout", "Move to the enterprise plan", "Audit + training",
)
_ACTIVITY_SUBJECTS = {
    "call": ("Discovery call", "Progress check", "Chasing the quote",
             "Closing call", "First contact"),
    "email": ("Proposal sent", "Chaser, no reply",
              "Meeting summary", "Terms sent", "Technical answer"),
    "meeting": ("Scoping meeting", "Product demo",
                "Steering committee", "Requirements workshop",
                "Contract review"),
    "note": ("Internal write-up", "Competitive landscape",
             "Budget confirmed", "New point of contact", "Watch point"),
    "task": ("Prepare the quote", "Send the references",
             "Schedule the demo", "Approve the discount",
             "Chase in week 38"),
}
_NOTE_BODIES = (
    "Responsive contact, prefers to be called in the morning.",
    "Budget settled at group level — decided in committee.",
    "Compared us with two competitors, sensitive to migration cost.",
    "Renewal conditional on carrying the history over.",
    "Wants an exit clause in the framework agreement.",
    "Annual review coming up, keep the contact warm.",
    "Purchasing insists on a tender above 50 k\u20ac.",
    "Internal sponsor identified: the technical directorate.",
)

#: Stage weights: a real pipeline is not uniform — there are many leads
#: and few negotiations in flight.
_STAGE_WEIGHTS = (30, 22, 16, 10, 14, 8)

_STATUS_WEIGHTS = (45, 30, 15, 10)


def iso_at(day_offset: int) -> str:
    """An ISO date ``day_offset`` days from :data:`TODAY` (negative = past)."""
    return (TODAY + timedelta(days=day_offset)).isoformat()


def build_accounts(rng: random.Random) -> list[tuple]:
    rows = []
    for i in range(1, N_ACCOUNTS + 1):
        country, cities = rng.choice(COUNTRIES)
        size = rng.choice(SIZES)
        # The ARR follows the size: a "large account" at €900 would make
        # any sort by amount absurd to the eye.
        floor = {"Micro": 1, "Small": 8, "Mid-market": 40, "Enterprise": 200}[size]
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
    """The contacts. ``owner_of`` = each account's owner.

    ⚠️ The owner is COPIED onto the row, as for the deals and the
    activities. Here it is pure denormalisation — a contact has no owner
    of their own, they have their account's — and it exists so the
    scoping does not force a join (cf. the schema).
    """
    rows = []
    statuses = list(STATUS_KEYS)
    for i in range(1, N_CONTACTS + 1):
        first = rng.choice(_FIRST)
        last = rng.choice(_LAST)
        # The id in the email: 4 800 first-name/surname combinations for
        # 120 000 contacts, so homonyms are guaranteed — and an address
        # must stay unique for "search by email" to mean anything.
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
    """The deals. ``owner_of`` = each account's owner.

    ⚠️ A deal's owner **follows their account's**, it is not drawn
    separately. It was until 2026-08-19, and it was inconsistent as soon
    as one looked at a portfolio: a salesperson's pipeline contained
    deals on accounts belonging to somebody else, and "my accounts" did
    not overlap "my deals". With no signed-in account nobody noticed;
    with authentication, it is the first thing one sees.
    """
    rows = []
    stages = list(STAGE_KEYS)
    # ``position`` = the rank in ITS kanban column. Counted per stage:
    # it is what screen 1 reorders, and two cards cannot share a rank
    # without the drop becoming ambiguous.
    #
    # Not 1, 2, 3 but a STEP of 64: inserting between two cards takes the
    # midpoint of their two ranks, and on consecutive integers there is
    # no midpoint — every move would force renumbering the whole column
    # (~2 000 rows) from the very first gesture.
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
    """The activities. The same rule as the deals: the owner follows the
    account, not chance (cf. :func:`build_deals`)."""
    rows = []
    kinds = list(ACTIVITY_KEYS)
    for i in range(1, N_ACTIVITIES + 1):
        contact = rng.choice(contacts)
        kind = rng.choice(kinds)
        subjects = _ACTIVITY_SUBJECTS[kind]
        rows.append((
            i,
            contact[0],                    # contact_id
            contact[1],                    # account_id — denormalised on purpose:
                                           # the account sheet aggregates
                                           # per account without going
                                           # through a join.
            kind,
            rng.choice(subjects),
            iso_at(-rng.randint(0, 400)),
            owner_of[contact[1]],
        ))
    return rows


def build_users() -> list[tuple]:
    """The seven accounts: the data set's six salespeople, plus a
    directorate with no portfolio that sees them all.

    The salt is **derived from the login**, not drawn at random: the seed
    must stay deterministic (two machines, the same database). It is the
    only acceptable lapse, and it concerns only demonstration accounts —
    ``hash_password`` without ``salt=`` stays random, and that is what
    the app uses if it creates an account.

    ``owner`` is the join key with the data: it is the name appearing in
    ``accounts.owner``. Management has none.
    """
    people = [
        (i, login_for(name), name, "rep", name)
        for i, name in enumerate(OWNERS, start=1)
    ]
    people.append((len(OWNERS) + 1, "management", "Sales management",
                   "director", ""))
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
    """``[(table, rows), …]`` in insertion order (foreign keys).

    Returns everything in one go rather than a generator: ``executemany``
    wants a sequence, and the activities must re-read the contacts
    already drawn to point at a (contact, account) pair that exists.
    """
    rng = random.Random(SEED_RNG)
    accounts = build_accounts(rng)
    # Each account's owner, indexed once. It is THAT which decides the
    # owner of its contacts, its deals and its activities — otherwise "my
    # accounts" does not overlap "my deals", and a portfolio means
    # nothing.
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

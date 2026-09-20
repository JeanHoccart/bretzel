"""core/domain — the business vocabulary, in pure Python.

Neither a feature nor a state: constants, like ``core/theme.py``. The
seed writes them into the database, the screens read them back to paint
badges and filters. Having them in a single place is what guarantees a
datatable filter offers exactly the values that exist in the database —
a filter's domain in callable mode must be DECLARED, the component holds
no row to derive it from.
"""

from __future__ import annotations

from datetime import date

#: The data set's "today". A FROZEN date, not ``date.today()``: a seed
#: relative to the clock makes the database non-reproducible and drifts
#: the pipeline's due dates by one day per day.
TODAY = date(2026, 8, 19)

#: The gap between two neighbouring kanban ranks. The seed applies it,
#: and the reordering uses it again when it renumbers a stage: inserting
#: between two cards takes the midpoint of their ranks, and on
#: consecutive integers there is no midpoint.
POSITION_STEP = 64

# ── Pipeline stages (screen 1) ───────────────────────────────────────
# (key, label, semantic colour). The order IS the columns' order.
STAGES: tuple[tuple[str, str, str], ...] = (
    ("lead",      "Lead",         "muted"),
    ("qualified", "Qualified",    "info"),
    ("proposal",  "Proposal",     "primary"),
    ("negotiation", "Negotiation", "warning"),
    ("won",       "Won",          "success"),
    ("lost",      "Lost",         "error"),
)
STAGE_KEYS: tuple[str, ...] = tuple(k for k, _l, _c in STAGES)
STAGE_LABEL: dict[str, str] = {k: lbl for k, lbl, _c in STAGES}
STAGE_COLOR: dict[str, str] = {k: c for k, _l, c in STAGES}

#: The kanban's columns: "won" and "lost" leave the board — a pipeline
#: shows what is still in play.
OPEN_STAGES: tuple[str, ...] = ("lead", "qualified", "proposal", "negotiation")

# ── Contact statuses (screens 3 and 4) ───────────────────────────────
CONTACT_STATUS: dict[str, tuple[str, str]] = {
    "active":   ("Active",    "success"),
    "lead":     ("Prospect",  "warning"),
    "dormant":  ("Dormant",   "muted"),
    "churned":  ("Churned",   "error"),
}
STATUS_KEYS: tuple[str, ...] = tuple(CONTACT_STATUS)

# ── Accounts (screen 2) ──────────────────────────────────────────────
INDUSTRIES: tuple[str, ...] = (
    "Manufacturing", "Health", "Finance", "Logistics", "Retail",
    "Energy", "Education", "Construction", "Media", "Food & drink",
)
COUNTRIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("France",      ("Paris", "Lyon", "Lille", "Nantes", "Toulouse",
                     "Bordeaux")),
    ("Belgium",     ("Brussels", "Antwerp", "Ghent", "Liege")),
    ("Switzerland", ("Geneva", "Zurich", "Lausanne")),
    ("Canada",      ("Montreal", "Quebec City", "Ottawa")),
)
COUNTRY_KEYS: tuple[str, ...] = tuple(c for c, _cities in COUNTRIES)
SIZES: tuple[str, ...] = ("Micro", "Small", "Mid-market", "Enterprise")

# ── The calendar ─────────────────────────────────────────────────────
#: ⚠️ The four date components (`calendar`, `date_picker`,
#: `date_range_picker`, `month_picker`) render their months and days in
#: ENGLISH by default, and have no notion of locale — only the
#: ``month_names`` / ``weekday_names`` props. This app no longer passes
#: them, because its language IS that default; the gap they paper over is
#: still real, and still filed in ``.claude/work/todo.md``.
#:
#: The abbreviation for a time chart's axis, where "September" does not
#: fit.
MONTHS_SHORT: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# ── Who works here ───────────────────────────────────────────────────
OWNERS: tuple[str, ...] = (
    "Aicha Benali", "Marc Dubois", "Sofia Rossi", "Lea Martin",
    "Tom Nguyen", "Clara Weiss",
)

# ── Who may see what (screen 0: the sign-in) ─────────────────────────
#: The two roles. ``rep`` sees ONLY their portfolio; ``director`` sees
#: everything and can stand in for anybody.
#:
#: Two and not three: one more role is justified by a screen asking for
#: it, and none does. It is the same rule as for the four unarbitrated
#: components.
ROLES: dict[str, str] = {
    "rep": "Sales rep",
    "director": "Management",
}

#: The only public route. Here and not in the feature: ``main``'s
#: middleware reads it too, and a STRING in a ``provides`` is filed by
#: its ``__name__``, which it does not have (lesson of slice 2). A single
#: source, otherwise the guard and the page drift — and a guard that
#: drifts lets people through, or locks everybody out.
LOGIN_PATH = "/login"

#: The password of ALL the demonstration accounts. In clear here, hashed
#: in the database — it is a trial data set, and hiding it would protect
#: nothing while making the app unusable.
DEMO_PASSWORD = "bretzel"


def login_for(name: str) -> str:
    """``"Aicha Benali"`` → ``"a.benali"``. Without accents: a login gets
    typed.

    Here and not in ``core/seed.py``: it is a naming RULE, read by the
    seed AND by the sign-in page. Leaving it there made a page depend on
    the demonstration data factory.
    """
    import unicodedata

    first, _, last = name.partition(" ")
    plain = unicodedata.normalize("NFD", f"{first[:1]}.{last}")
    return "".join(c for c in plain if not unicodedata.combining(c)).lower()

# ── Import (screen 9) ────────────────────────────────────────────────
#: An accounts CSV's columns, in order. Here and not in the
#: ``import_data`` feature: two features read them, and a ``provides``
#: files its entries by ``__name__`` — which a tuple does not have
#: (lesson of slice 2, where the app map showed a node named "int"). The
#: vocabulary is not a feature surface, it is domain.
IMPORT_COLUMNS: tuple[str, ...] = (
    "name", "industry", "country", "city", "size", "arr", "owner",
)
#: An import's ceiling. Beyond it, the preview is no longer a preview and
#: the transaction becomes a long lock on a database the other screens
#: are reading.
IMPORT_MAX_ROWS = 500
IMPORT_EXAMPLE_CSV = (
    "name,industry,country,city,size,arr,owner\n"
    "Northway Retail Ltd,Retail,France,Lyon,Small,42000,Marc Dubois\n"
    "Northern Works,Manufacturing,Belgium,Ghent,Micro,9000,Sofia Rossi\n"
)

# ── Activities (screen 4) ────────────────────────────────────────────
ACTIVITY_KINDS: dict[str, tuple[str, str, str]] = {
    "call":    ("Call",     "phone",       "info"),
    "email":   ("Email",    "mail",        "primary"),
    "meeting": ("Meeting",  "users",       "success"),
    "note":    ("Note",     "sticky-note", "muted"),
    "task":    ("Task",     "check-check", "warning"),
}
ACTIVITY_KEYS: tuple[str, ...] = tuple(ACTIVITY_KINDS)


def activity_badge(kind: str) -> tuple[str, str, str]:
    """``(label, icon, colour)`` of an activity type, fallback included.

    The counterpart of :func:`status_badge` for the other vocabulary two
    screens paint — the same reason: an unseen type in the database must
    show the same way everywhere.
    """
    return ACTIVITY_KINDS.get(kind, (kind, "circle", "muted"))


def status_badge(status: str) -> tuple[str, str]:
    """``(label, colour)`` of a contact status, fallback included.

    Three screens paint this badge; the fallback on an unknown status
    must be the same everywhere, otherwise an unseen value in the
    database shows differently depending on the page showing it.
    """
    return CONTACT_STATUS.get(status, (status, "muted"))


def initials(first: str, last: str) -> str:
    """A contact's initials — used by screens 3/4's avatars."""
    return ((first[:1] or "?") + (last[:1] or "")).upper()


def euros(amount: int) -> str:
    """``120000`` → ``"120 k€"``. A column of amounts must fit in a 260 px
    kanban card, not show nine digits.

    The "bn€" step is not decorative: the 50 000 accounts' cumulative ARR
    is 20 billion, and without it the header showed "20139.2 M€".
    """
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} bn€".replace(".0 ", " ")
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f} M€".replace(".0 ", " ")
    if amount >= 1_000:
        return f"{amount // 1_000} k€"
    return f"{amount} €"

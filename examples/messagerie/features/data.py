"""messagerie/data — the mailbox, in memory, shared by everyone.

``AppState`` and not ``SessionState``: a mail client is a single object
every tab talks about. Moving a message in one tab must show in the other
— it is the scope that says so, not a synchronisation mechanism written
by hand.

No database, and that is this example's choice: three other demos
(`crm`, `mad`) show SQLite, none showed a shared in-memory state as the
source of truth of a whole app. The price is written down: restarting the
server puts the mailbox back to its starting state.

A message is a ``dict`` and not a dataclass, for the same reason as
``examples/chat``: what is demonstrated here is the transport of the
view, not domain modelling. A `dict` reads without opening a second file.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from bretzel.state import AppState, field

#: The four folders, in the order the column shows them. The key travels
#: in the URL (`?folder=archive`), so it is a public API: renaming it
#: would break shared links.
FOLDERS: tuple[tuple[str, str, str], ...] = (
    ("inbox", "Inbox", "inbox"),
    ("sent", "Sent", "send"),
    ("archive", "Archive", "archive"),
    ("trash", "Trash", "trash-2"),
)

#: The keys alone, to validate a hand-typed URL parameter.
KEYS = tuple(key for key, _, _ in FOLDERS)


#: The mailbox's background: older mail, written as a table because it
#: only serves to give VOLUME. ``recent_mail``'s eight detailed messages
#: carry the demonstration; these carry the density — without them the
#: list fits in half a screen and you see neither the scrolling nor what
#: the search really does.
#:
#: Order: OLDEST to newest. The identifiers are assigned by position in
#: :func:`seed`, not written here.
BACKGROUND: tuple[tuple[str, str, str, str, str, bool], ...] = (
    # (sender, address, subject, date, folder, read)
    ("Shield Trade Insurance", "contracts@shield-trade.com",
     "Your ten-year cover is up for renewal", "2 June", "archive", True),
    ("PlantHire Direct", "lille@planthire-direct.com",
     "Quote for a 12 m cherry picker", "5 June", "archive", True),
    ("Sofia Bendjelloul", "s.bendjelloul@flanders-concrete.com",
     "Pouring schedule — week 24", "11 June", "archive", True),
    ("Tax Office", "no-reply@tax-office.gov",
     "Your compliance certificate is available", "14 June", "archive",
     True),
    ("Thomas Lecomte", "t.lecomte@lecomte-timber.com",
     "Chasing: the roof frame take-off", "18 June", "trash", True),
    ("BuildBase", "orders@buildbase.com",
     "Order CP-88214 confirmed", "21 June", "archive", True),
    ("Élodie Vasseur", "e.vasseur@vasseur-practice.com",
     "Site visit report — section 3", "25 June", "archive", True),
    ("ConstructWeekly", "info@constructweekly.com",
     "New build rules: what changes on 1 July", "28 June", "trash", True),
    ("Karim Ferhati", "k.ferhati@ferhati-electrical.com",
     "Availability for the sub-distribution board", "1 July", "archive",
     True),
    ("Kerlouan Council", "planning@kerlouan-council.gov",
     "Further documents needed — PC 2026-0042", "3 July",
     "archive", True),
    ("Sofia Bendjelloul", "s.bendjelloul@flanders-concrete.com",
     "Pour postponed: weather", "8 July", "archive", True),
    ("ToolHire Co", "quotes@toolhire.com",
     "Your quote no. D-77120", "12 July", "trash", True),
    ("Thomas Lecomte", "t.lecomte@lecomte-timber.com",
     "Roof frame take-off — corrected version", "15 July", "archive", True),
    ("Meridian Insurance", "claims@meridian-insurance.com",
     "Claim filed: acknowledgement of receipt", "19 July",
     "archive", True),
    ("Élodie Vasseur", "e.vasseur@vasseur-practice.com",
     "Construction drawings — revision C", "23 July", "archive", True),
    ("Karim Ferhati", "k.ferhati@ferhati-electrical.com",
     "Invoice FE-2026-118", "27 July", "archive", True),
    ("Sofia Bendjelloul", "s.bendjelloul@flanders-concrete.com",
     "Delivery note — 14 m³", "30 July", "archive", True),
    ("BuildBase", "orders@buildbase.com",
     "Temporary shortage on the 20 block", "4 August", "inbox", True),
    ("Nolwenn Le Guen", "n.leguen@kerlouan-council.gov",
     "Public meeting on 20 August", "6 August", "inbox", True),
    ("Thomas Lecomte", "t.lecomte@lecomte-timber.com",
     "Visit moved to the 18th", "9 August", "inbox", True),
    ("Élodie Vasseur", "e.vasseur@vasseur-practice.com",
     "Cladding approved: chosen shade", "13 August", "inbox", True),
    ("Karim Ferhati", "k.ferhati@ferhati-electrical.com",
     "Chasing invoice FE-2026-118", "17 August", "inbox", True),
    ("Sofia Bendjelloul", "s.bendjelloul@flanders-concrete.com",
     "Pouring schedule — week 35", "20 August", "inbox", True),
    ("Shield Trade Insurance", "contracts@shield-trade.com",
     "Renewal: your 2027 payment plan", "24 August", "inbox", True),
    ("Kerlouan Council", "planning@kerlouan-council.gov",
     "Traffic order — Mill Street", "27 August", "inbox", True),
    ("BuildBase", "orders@buildbase.com",
     "Your order CP-90331 is ready", "30 August", "inbox", True),
    ("Élodie Vasseur", "e.vasseur@vasseur-practice.com",
     "Snags cleared on section 3", "2 September", "inbox", True),
    ("Thomas Lecomte", "t.lecomte@lecomte-timber.com",
     "Extra quote: purlin reinforcement", "4 September", "inbox", False),
)

#: The body of the background messages. Two sentences, derived from the
#: subject: they must READ in the preview without anybody having written
#: them one by one.
def generic_body(subject: str, sender: str) -> str:
    return (
        f"Hello,\n\n"
        f"Following up on our exchanges about “{subject.lower()}”, "
        f"here are the items you asked for.\n\n"
        f"Do say if any point deserves another look.\n\n"
        f"{sender}"
    )


def background() -> list[dict[str, Any]]:
    """The old mail, materialised from :data:`BACKGROUND`."""
    return [
        {
            "id": 0,  # assigned by position in ``seed``
            "folder": folder,
            "incoming": True,
            "sender": sender,
            "address": address,
            "subject": subject,
            "date": date,
            "read": read,
            "body": generic_body(subject, sender),
            "attachments": ["attachment.pdf"] if "nvoice" in subject else [],
        }
        for sender, address, subject, date, folder, read in BACKGROUND
    ]


def seed() -> list[dict[str, Any]]:
    """The mailbox at startup. Replayed at every server launch.

    The identifiers are assigned BY POSITION, oldest to newest: that is
    what makes "increasing id" mean "more recent", and therefore what
    lets ``free_id()`` put a new message at the head of the list without
    having to sort anything.
    """
    # ``recent_mail`` is written in the order it was drafted, not in
    # time order; its literal ``id`` values, though, are chronological.
    # We use them to put it back in order, then ALL the identifiers are
    # reassigned by position.
    ordered = [
        *background(),
        *sorted(recent_mail(), key=lambda m: m["id"]),
        *shed_thread(),
        *unanswered_thread(),
    ]
    for rank, message_ in enumerate(ordered, start=1):
        message_["id"] = rank
    return ordered


def shed_thread() -> list[dict[str, Any]]:
    """Five rounds with the same person, in the SAME thread.

    It is what makes the grouping visible: without a real exchange, a
    thread and a message look alike, and the list proves nothing. The
    subject stays "Re: The shed 3 drawings", so these messages fall into
    the thread Camille opened this morning.
    """
    exchange = (
        ("me", "me@northgate-works.com", "sent", "today, 09:41", True,
         "The slab has been poured since Friday, we are on schedule.\n\n"
         "The roof frame section, though, changes everything for the "
         "bearing: I have to go back to the engineers before ordering "
         "the steel."),
        ("Camille Roussel", "camille.roussel@northgate-works.com", "inbox",
         "today, 10:02", True,
         "Good news on the slab.\n\nFor the steel, wait for their answer "
         "on Monday — they were talking about redoing the load path, "
         "so it may still move by a section."),
        ("me", "me@northgate-works.com", "sent", "today, 10:20", True,
         "Understood, I am holding the order until Monday evening."),
        ("Camille Roussel", "camille.roussel@northgate-works.com", "inbox",
         "today, 10:47", True,
         "One more thing: the client is asking whether we can bring the "
         "cladding forward by a week. Do you have the schedule?"),
        ("Camille Roussel", "camille.roussel@northgate-works.com", "inbox",
         "today, 11:26", False,
         "Chasing — they need an answer before their meeting "
         "tomorrow morning."),
    )
    return [
        {
            "id": 0,  # assigned by position in ``seed``
            "folder": folder,
            "incoming": sender != "me",
            "sender": sender,
            "address": address,
            "subject": "Re: The shed 3 drawings",
            "date": date,
            "read": read,
            "body": body,
            "attachments": [],
        }
        for sender, address, folder, date, read, body in exchange
    ]


def unanswered_thread() -> list[dict[str, Any]]:
    """A sent message that never got a reply.

    It exists for a precise reason: it is the mailbox's ONLY purely
    outgoing thread, hence the only one exercising the rule "you do not
    mark unread what you wrote yourself". Without it, every thread in
    "Sent" also contains received mail — the thread is the unit, and it
    displays whole — and the rule would have no case to check it.
    """
    return [
        {
            "id": 0,  # assigned by position in ``seed``
            "folder": "sent",
            "incoming": False,
            "sender": "me",
            "address": "s.bendjelloul@flanders-concrete.com",
            "subject": "Is the concrete pump free",
            "date": "today, 11:40",
            "read": True,
            "body": (
                "Hello Sofia,\n\n"
                "Would you have a pump free on the morning of the 22nd? "
                "The volume is about 18 m³.\n\n"
                "Thanks in advance."
            ),
            "attachments": [],
        },
    ]


def recent_mail() -> list[dict[str, Any]]:
    """The eight detailed messages — the ones carrying the demonstration."""
    return [
        {
            "id": 8,
            "folder": "inbox",
            "incoming": True,
            "sender": "Camille Roussel",
            "address": "camille.roussel@northgate-works.com",
            "subject": "The shed 3 drawings",
            "date": "today, 09:14",
            "read": False,
            "body": (
                "Hello,\n\n"
                "Here are the revised drawings for shed 3. The span has "
                "gone from 12 to 14 metres, so the roof frame changes "
                "section — the engineers go over it again on "
                "Monday.\n\n"
                "Can you confirm the slab is poured before the 20th?"
            ),
            "attachments": ["shed-3-drawings-v4.pdf", "engineers-note.pdf"],
        },
        {
            "id": 6,
            "folder": "inbox",
            "incoming": True,
            "sender": "Farid Benali",
            "address": "f.benali@benali-haulage.com",
            "subject": "Delivery slot on Tuesday",
            "date": "today, 08:02",
            "read": False,
            "body": (
                "The lorry can come on Tuesday between 7 and 9 in the "
                "morning, or at the end of the day after 5.\n\n"
                "Tell me what suits you and I will hold the slot."
            ),
            "attachments": [],
        },
        {
            "id": 5,
            "folder": "inbox",
            "incoming": True,
            "sender": "Inès Marchand",
            "address": "ines@marchand-architects.com",
            "subject": "Minutes of the site meeting",
            "date": "yesterday, 18:37",
            "read": True,
            "body": (
                "Minutes of the meeting on the 4th:\n\n"
                "- the electrical connection is pushed back by a week;\n"
                "- the roof waterproofing has been signed off;\n"
                "- the joinery colour is still to be decided.\n\n"
                "Next meeting on the 18th, same time."
            ),
            "attachments": ["minutes-04.pdf"],
        },
        {
            "id": 4,
            "folder": "inbox",
            "incoming": True,
            "sender": "Accounts department",
            "address": "accounts@northgate-works.com",
            "subject": "Invoice 2026-0871 — past due",
            "date": "yesterday, 11:20",
            "read": True,
            "body": (
                "Invoice 2026-0871 has been due since 31 August.\n\n"
                "Please tell us whether payment has gone out, failing "
                "which we will chase the client directly."
            ),
            "attachments": ["invoice-2026-0871.pdf"],
        },
        {
            "id": 3,
            "folder": "inbox",
            "incoming": True,
            "sender": "Nolwenn Le Guen",
            "address": "n.leguen@kerlouan-council.gov",
            "subject": "Highway permit — acknowledgement of receipt",
            "date": "Monday, 15:05",
            "read": True,
            "body": (
                "Your application to occupy public land temporarily has "
                "been registered under number OTDP-2026-114.\n\n"
                "The case officer will come back to you within 15 days."
            ),
            "attachments": [],
        },
        {
            "id": 7,
            "folder": "sent",
            "incoming": False,
            "sender": "me",
            "address": "me@northgate-works.com",
            "subject": "Re: Delivery slot on Tuesday",
            "date": "today, 08:41",
            "read": True,
            "body": "The morning suits us, 7:30 if that is possible.",
            "attachments": [],
        },
        {
            "id": 2,
            "folder": "archive",
            "incoming": True,
            "sender": "Inès Marchand",
            "address": "ines@marchand-architects.com",
            "subject": "Planning permission — granted",
            "date": "12 August",
            "read": True,
            "body": (
                "The approval came through this morning, with no "
                "conditions.\n\n"
                "We can start the earthworks whenever you want."
            ),
            "attachments": ["permission-granted.pdf"],
        },
        {
            "id": 1,
            "folder": "trash",
            "incoming": True,
            "sender": "BuildWeekly",
            "address": "no-reply@buildweekly.com",
            "subject": "The 10 structural work trends of 2026",
            "date": "3 August",
            "read": True,
            "body": "You are receiving this message because you signed up.",
            "attachments": [],
        },
    ]


class Mailbox(AppState):
    """Every message, all folders together.

    A single field: a message's folder is a property OF the message, not
    a list per folder. That is what makes a move a one-character write
    and not a removal followed by an addition — hence what stops it
    leaving the message in two folders at once.
    """

    messages: list[dict[str, Any]] = field(default_factory=seed)


def folder_messages(key: str) -> list[dict[str, Any]]:
    """A folder's messages, newest to oldest.

    ⚠️ **The sort does NOT look at ``read``.** The first version put
    unread first: opening a message marked it read, so it changed group
    and **dropped to the bottom of the pile under the cursor**. No mail
    client does that, and for a good reason — a list's order must be
    stable under the act of reading it. Unread is signalled by
    appearance, never by position.
    """
    inside = [m for m in Mailbox().messages if m["folder"] == key]
    return sorted(inside, key=lambda m: -m["id"])


# ── Conversation threads ──────────────────────────────────────────────
#
# A mail client does not show messages, it shows EXCHANGES: ten rounds
# with the same person make ONE row, not ten. The grouping is done on the
# NORMALISED subject — it is what mail clients do when they have no
# ``References`` header to work with, and an example has no real headers.


def normalised_subject(subject: str) -> str:
    """"Re: Re: The drawings" and "The drawings" are the SAME thread."""
    bare = subject.strip()
    low = bare.lower()
    while low.startswith(("re:", "re :", "fw:", "fwd:")):
        bare = bare.split(":", 1)[1].strip()
        low = bare.lower()
    return bare.lower()


def thread_of(message: dict[str, Any]) -> str:
    """A message's thread key — a SLUG, because it travels in a URL.

    ``?thread=the-shed-3-drawings`` and not
    ``?thread=the+shed+3+drawings``. A key that goes into the address is
    a public API: it must read, be dictated over the phone and survive a
    copy-paste. Spaces have no place in it.
    """
    bare = unicodedata.normalize("NFKD", normalised_subject(message["subject"]))
    unaccented = "".join(c for c in bare if not unicodedata.combining(c))
    kept = [c if c.isalnum() else "-" for c in unaccented]
    return re.sub(r"-{2,}", "-", "".join(kept)).strip("-")


def folder_threads(key: str) -> list[dict[str, Any]]:
    """The threads visible in a folder, newest to oldest.

    A thread appears in a folder as soon as ONE of its messages is there,
    and it shows there WHOLE — my replies included, even though they live
    in "Sent". It is what Gmail does, and it is what makes an exchange
    readable: the first version kept only the current folder's messages,
    so you read four messages from the same person without the replies
    that separated them.

    ⚠️ Simplification on purpose: a message sent to the bin therefore
    takes its thread to the bin too. A real client separates the two; the
    example does not, because it would need a per-(thread, folder) state
    that teaches nothing more about Bretzel.

    Each thread returns a dictionary ready to display: its messages
    oldest to newest, the last one, the unread count, and the list of
    participants in the order they spoke.
    """
    here = {thread_of(m) for m in Mailbox().messages if m["folder"] == key}
    by_thread: dict[str, list[dict[str, Any]]] = {}
    for m in Mailbox().messages:
        tkey = thread_of(m)
        if tkey in here:
            by_thread.setdefault(tkey, []).append(m)

    threads = []
    for tkey, members in by_thread.items():
        members = sorted(members, key=lambda m: m["id"])
        last = members[-1]
        participants: list[str] = []
        for m in members:
            if m["sender"] not in participants:
                participants.append(m["sender"])
        threads.append({
            "thread": tkey,
            "messages": members,
            "last": last,
            "subject": short_subject(members[0]["subject"]),
            "unread": sum(1 for m in members
                          if m["incoming"] and not m["read"]),
            "participants": participants,
        })
    return sorted(threads, key=lambda t: -t["last"]["id"])


def short_subject(subject: str) -> str:
    """The thread's subject: the first message's, without its "Re:"."""
    bare = subject.strip()
    while bare.lower().startswith(("re:", "re :", "fw:", "fwd:")):
        bare = bare.split(":", 1)[1].strip()
    return bare


def thread_in_folder(key: str, tkey: str) -> dict[str, Any] | None:
    """The thread ``tkey`` in folder ``key``, or ``None``."""
    for thread in folder_threads(key):
        if thread["thread"] == tkey:
            return thread
    return None


def thread_text(thread: dict[str, Any]) -> str:
    """Everything the search bites on in a thread."""
    pieces = []
    for m in thread["messages"]:
        pieces += [m["sender"], m["address"], m["subject"], m["body"]]
    return " ".join(pieces)


def message_by_id(identifier: int) -> dict[str, Any] | None:
    """A message by its identifier, or ``None`` if it no longer exists."""
    for candidate in Mailbox().messages:
        if candidate["id"] == identifier:
            return candidate
    return None


def unread_count(key: str) -> int:
    """How many INCOMING messages are unread in this folder.

    The messages one wrote do not count: "Sent" showed an unread badge,
    which makes no sense — you have read what you have just written.
    """
    return sum(
        1 for m in Mailbox().messages
        if m["folder"] == key and m["incoming"] and not m["read"]
    )


def short_date(message: dict[str, Any]) -> str:
    """The list's date, DERIVED from the long date.

    ⚠️ It used to be a field copied into every message, and the message
    created by "Send" did not carry it: showing "Sent" raised a
    ``KeyError: 'short'``. A derivable value is not stored — deriving it
    makes the case impossible rather than rare.
    """
    long = message["date"]
    if long.startswith("today, "):
        return long.removeprefix("today, ")
    if long.startswith("yesterday"):
        return "yesterday"
    if "," in long:
        return long.split(",")[0]
    return long


def preview(message: dict[str, Any], size: int = 90) -> str:
    """The body's first line, for the list.

    A mail client without a preview does not read: the subject alone
    forces you to open to know what it is about. It is what every mail
    client does, and it is what distinguishes a list from a table.
    """
    flat = " ".join(message["body"].split())
    return flat if len(flat) <= size else flat[: size - 1].rstrip() + "…"


def free_id() -> int:
    """The next identifier, derived from the mailbox rather than counted.

    A counter on an ``AppState`` is a SHARED counter: two simultaneous
    sends would read it at the same value and the second would overwrite
    the first. Deriving it from the maximum makes it idempotent, and
    removes the need for a ``merge="add"`` nothing else here would
    justify.
    """
    return max((m["id"] for m in Mailbox().messages), default=0) + 1

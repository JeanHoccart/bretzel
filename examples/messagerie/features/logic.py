"""messagerie/logic — the handlers. They mutate, the display follows.

None touches the DOM and none returns HTML: they write into a state, and
the ``@refreshable`` zones depending on it re-render. Two of them write
into :class:`View`, so **the address changes too** — without a single
line asking for it, because ``View`` declares its addressable fields.

⚠️ **A collection is REASSIGNED, it is not mutated in place.**
``mailbox.messages[0]["read"] = True`` does write the value, but does not
change the list's identity: change detection sees nothing and the zone
does not re-render (`traps.md` § collection mutation). Hence the
rebuilding below, which remakes the list around the modified message.
"""

from __future__ import annotations

import re
from typing import Any

from bretzel.components import Move
from examples.messagerie.features.data import (
    KEYS,
    Mailbox,
    free_id,
    thread_in_folder,
    thread_of,
)
from examples.messagerie.features.state import Draft, Panel, View

#: The prefix of the ``name=`` of the folder column's drop zones. The
#: suffix is the folder's key, so ``to_zone`` is enough to know where the
#: message landed.
ZONE_FOLDER = "folder-"

#: The ``name=`` of the zone carrying the list. It is the SOURCE of the
#: drags, never their destination — one does not drop a message onto the
#: list it already comes from.
ZONE_LIST = "list"


def open_thread(tkey: str) -> None:
    """Show a THREAD, and mark all its incoming messages read.

    That is what a mail client does: opening a conversation reads it
    whole. Marking a single message would leave the thread "partly
    unread", a state nothing shows and nobody knows how to resolve.
    """
    view = View()
    if thread_in_folder(view.folder, tkey) is None:
        return
    view.opened = tkey
    mailbox = Mailbox()
    mailbox.messages = [
        {**m, "read": True} if thread_of(m) == tkey and m["incoming"] else m
        for m in mailbox.messages
    ]


def close_thread() -> None:
    """Close the displayed thread, without changing folder."""
    View().opened = ""


#: What looks like an address: an at sign, text on both sides, a dot in
#: the domain, and no space. DELIBERATELY permissive — the full grammar
#: (RFC 5322) accepts forms nobody writes, and an expression claiming to
#: implement it mostly rejects valid addresses. The real check on an
#: address is sending a message to it.
ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── The actions on the displayed message ──────────────────────────────
#
# All follow the same shape: read the current message, refuse if nothing
# is open, mutate, and let the zones re-render.


def toggle_read() -> None:
    """Mark the displayed thread unread, or read it all again.

    ⚠️ Acts only on INCOMING messages. "Mark unread" on what one wrote
    oneself makes no sense, and the toolbar only offers the button if the
    thread contains any — this guard is here so the rule lives in the
    domain and not only in the rendering.
    """
    view = View()
    thread = thread_in_folder(view.folder, view.opened)
    if thread is None:
        return
    incoming = [m for m in thread["messages"] if m["incoming"]]
    if not incoming:
        return
    target = thread["unread"] == 0  # all read → back to unread
    mailbox = Mailbox()
    mailbox.messages = [
        {**m, "read": not target}
        if thread_of(m) == view.opened and m["incoming"]
        else m
        for m in mailbox.messages
    ]


def file_into(target: str) -> None:
    """Move the WHOLE displayed thread to ``target``, and close it.

    The thread is the unit: archiving a conversation while leaving two of
    its messages in the inbox would make it reappear on the next line,
    and nobody would understand why.
    """
    view = View()
    thread = thread_in_folder(view.folder, view.opened)
    if thread is None or target not in KEYS:
        return
    mailbox = Mailbox()
    mailbox.messages = [
        {**m, "folder": target} if thread_of(m) == view.opened else m
        for m in mailbox.messages
    ]
    view.opened = ""


def on_drop(move: Move) -> None:
    """File a message in the folder it has just been dropped on.

    It is the RECEIVING zone that decides: the base layer calls the
    arrival zone's ``on_move``, so ``to_zone`` already carries the
    destination and this handler has nothing to guess.

    Refusing is doing nothing. The browser has already moved the card
    optimistically; a handler that does not mutate leaves the server
    re-render disagreeing with the DOM, and the morph puts it back. So
    there is no ``reject()`` to call.
    """
    if not move.to_zone.startswith(ZONE_FOLDER):
        return
    target = move.to_zone[len(ZONE_FOLDER) :]
    if target not in KEYS:
        return
    # ``item_key`` is the THREAD's key: a thread is what gets dragged, so
    # a whole thread is what changes folder.
    tkey = move.item_key
    mailbox = Mailbox()
    concerned = [m for m in mailbox.messages if thread_of(m) == tkey]
    if not concerned:
        return
    mailbox.messages = [
        {**m, "folder": target} if thread_of(m) == tkey else m
        for m in mailbox.messages
    ]
    # The thread leaves the displayed folder: the right panel can no
    # longer show it. Close it HERE rather than let the view point at an
    # absent thread — and the address follows.
    if View().opened == tkey:
        View().opened = ""


# ── Composing ─────────────────────────────────────────────────────────


def compose() -> None:
    """Open the compose panel, empty."""
    draft = Draft()
    draft.to = ""
    draft.subject = ""
    draft.body = ""
    unfold()


def quote(messages: list[dict[str, Any]]) -> str:
    """THE WHOLE thread quoted, newest first.

    ⚠️ Not only the last message. A reply by mail carries the history
    along — it is what lets the recipient re-read the exchange without
    opening their own mailbox, and it is what Outlook does by folding the
    thread back under the reply. The first version quoted only the
    message being replied to: on a six-round conversation, the reply
    arrived without its context.

    The body is rendered as markdown on display, so the ``>`` prefix is
    not decorative: it produces a real block quote. Two blank lines in
    front, so the cursor lands ABOVE the quote — it is every mail
    client's convention, and the opposite (writing under the quote) is
    what corporate mail has been blamed for these twenty years.
    """
    blocks = []
    for current in reversed(messages):
        lines = current["body"].splitlines()
        quoted = "\n".join(f"> {line}" if line else ">" for line in lines)
        # "X wrote (date)" and not "On {date}, X wrote": the dates in
        # this mailbox take three shapes ("today, 09:14", "yesterday,
        # 18:37", "12 August"), and the second turn of phrase gives "On
        # yesterday, 18:37, X wrote". The parenthesis works with all
        # three.
        blocks.append(
            f"{current['sender']} wrote ({current['date']}):\n{quoted}"
        )
    return "\n\n" + "\n\n".join(blocks)


def reply() -> None:
    """Open the panel, replying to the LAST message of the thread."""
    view = View()
    thread = thread_in_folder(view.folder, view.opened)
    if thread is None:
        return
    current = thread["last"]
    subject = current["subject"]
    draft = Draft()
    draft.to = current["address"]
    draft.subject = subject if subject.startswith("Re: ") else f"Re: {subject}"
    draft.body = quote(thread["messages"])
    unfold()


def unfold() -> None:
    """Open the panel at its normal size, with no error shown."""
    panel = Panel()
    panel.opened = True
    panel.size = "normal"
    panel.error = ""


def resize(size: str) -> None:
    """Put the panel into ``normal``, ``small`` or ``full``."""
    Panel().size = size


def close_compose() -> None:
    """Fold the panel away without recording anything."""
    panel = Panel()
    panel.opened = False
    panel.error = ""


def send() -> None:
    """Drop the draft into "Sent", then fold the panel away.

    The validation is here, on the SERVER, and not only in the input's
    ``type="email"``. The browser's native check is a comfort — it flags
    the mistake while typing — but it is bypassed: nothing stops the
    action being POSTed without going through the form. A handler that is
    authoritative cannot settle for what the client promises it.
    """
    draft = Draft()
    panel = Panel()
    subject = (draft.subject or "").strip()
    body = (draft.body or "").strip()
    recipient = (draft.to or "").strip()

    if not recipient:
        panel.error = "The recipient is missing."
        return
    if not ADDRESS.match(recipient):
        panel.error = f"“{recipient}” is not a valid address."
        return
    if not subject and not body:
        panel.error = "An empty message with no subject does not go out."
        return
    panel.error = ""

    mailbox = Mailbox()
    mailbox.messages = [
        *mailbox.messages,
        {
            "id": free_id(),
            "folder": "sent",
            "incoming": False,
            "sender": "me",
            "address": recipient,
            "subject": subject or "(no subject)",
            "date": "just now",
            "read": True,
            "body": body,
            "attachments": [],
        },
    ]

    draft.to = ""
    draft.subject = ""
    draft.body = ""
    panel.opened = False

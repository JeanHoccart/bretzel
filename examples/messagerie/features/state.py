"""messagerie/state — the view lives in the address.

This is THE mechanic this example stages, and it fits in three lines of
declaration.

A ``PageState`` lives in a server dictionary keyed by a render uuid,
**a new one at every navigation**. With nothing more, opening a message
then pressing the back arrow has no useful effect: the browser makes a
real GET again, gets a new uuid, and lands on an address that says
nothing about what was being looked at.

``URL = {…}`` declares the fields **the address is authoritative for**.
The base layer reads them back at render time and rewrites the address
bar at every mutation, with no navigation and no reload. From there,
three things work at once and none was coded: the link shares, the
bookmark finds the same view again, and the browser's arrows go back and
forth.

⚠️ **The URL name is written, not derived from the Python name.**
``opened`` is called ``thread`` in the address. A URL is a public API: if
it derived from the field's name, renaming an attribute would break links
already shared.

⚠️ **What is declared is PUBLIC** — browser history, server logs, the
next request's ``Referer`` header. Here the open folder and the read
message's identifier; the reply draft, for its part, is not part of it
and cannot be: it has no URL name.
"""

from __future__ import annotations

from bretzel.state import ClientState, PageState, field, validator


class View(PageState):
    """What is being looked at: a folder, and possibly a message.

    ``opened`` carries a THREAD's key, not a message's: what one opens in
    a mail client is a whole conversation. Empty = nothing open, and the
    right panel shows its empty state.

    A string rather than an integer, and it is the grouping that decides:
    a thread has no identity of its own in storage, it derives from the
    normalised subject. So the address becomes readable —
    ``?thread=the-shed-3-drawings`` — which is a happy side effect: a URL
    should read.
    """

    folder: str = field(default="inbox")
    opened: str = field(default="")

    URL = {"folder": "folder", "opened": "thread"}


class Filter(ClientState):
    """What is being searched for in the open folder.

    ``ClientState`` and not ``PageState``, because the filtering happens
    **in the browser**: ``ui.filter_each`` takes a ``ClientBinding`` and
    sets a ``bz-show`` per row. Typing therefore costs no request — no
    ``on_input``, no ``debounce``, no zone to re-render.

    ⚠️ **The trade-off cuts both ways, and it is chosen.** Client-side
    filtering requires ALL the rows to be in the DOM: at eight messages
    it is free, at five thousand it is a page that weighs. The day the
    mailbox grows, the answer is not to make this field cleverer — it is
    to filter on the server and paginate, which ``ui.datatable`` already
    does (``examples/crm``).

    ⚠️ **Nothing here is addressable, and that is a decision.** A field
    declared in ``URL = {…}`` is PUBLIC: browser history, server logs,
    the next request's ``Referer`` header. Which folder you are looking
    at says nothing sensitive; what you are searching for in your mailbox
    does. The framework holds the same line — ``filters`` is addressable
    in none of its defaults.
    """

    q: str = field(default="")


class Panel(PageState):
    """The compose panel's state: open? and at what size?

    A SERVER state and not a client one, unlike the draft it contains.
    The reason is the size: going from "normal" to "full screen" changes
    the container's classes, and a class does not bind on the client the
    way a value does. The panel is therefore a refreshable zone, and its
    textual content — that one — stays in a ``ClientState``, which is
    what makes it survive the re-render.
    """

    #: ``normal`` (bottom-right corner) · ``small`` (title bar only) ·
    #: ``full`` (centred, almost the whole screen).
    size: str = field(default="normal")
    opened: bool = field(default=False)

    #: What stops the send, in plain words. Empty = nothing to report.
    error: str = field(default="")

    @validator("size")
    def _size(cls, value: str) -> str:
        """A size outside the table falls back to ``normal``.

        The validator COERCES, it does not raise: the value comes from an
        app handler, not from user input — a typo here should return a
        usable panel, not an error page.
        """
        return value if value in ("normal", "small", "full") else "normal"


class Draft(ClientState):
    """The draft of the message being written.

    ``ClientState`` without ``send_to_server=False``: these values are
    born in the browser and must therefore travel up, otherwise the send
    handler would not know what to record. It is the exact
    counter-example of the ``View`` above — that one is written by the
    server and published in the address, this one is written by the human
    and never leaves the page until they click.
    """

    to: str = field(default="")
    subject: str = field(default="")
    body: str = field(default="")

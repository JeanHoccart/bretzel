"""messagerie/inbox — the three panels, the toolbar, composing.

Three independently scrolling regions, in a document that does not
scroll: the folders, the open folder's list, the message being read.
Each is a ``@refreshable`` zone — what you look at changes, or the
mailbox changes, and only the region concerned re-renders.

**Drag and drop goes from the list to a folder.** Every folder in the
left column is a ``ui.dropzone`` declaring ``accepts=["message"]``; the
list is the source zone. It is the RECEIVING zone that decides — the base
layer calls its ``on_move`` — so every folder wires the same handler and
``to_zone`` carries the destination.

An omitted ``accepts=`` would NOT mean "anything": a zone declaring
nothing receives only its own items. Receiving from elsewhere is an
opt-in, and it is what stops the list catching a card from an unrelated
zone.

⚠️ **No command appears on hover.** It is what Gmail and its kin do for
row actions, and it is unusable here: the author's browser reports
``hover``, ``any-hover`` and ``pointer:fine`` all three as ``false``. A
command reachable only by hovering does not exist for them. So the
actions live in the open message's toolbar, permanently visible.
"""

from __future__ import annotations

from functools import partial

from bretzel import page, refreshable, ui
from examples.messagerie.features.data import (
    FOLDERS,
    Mailbox,
    folder_threads,
    preview,
    short_date,
    thread_in_folder,
    thread_text,
    unread_count,
)
from examples.messagerie.features.logic import (
    ZONE_FOLDER,
    ZONE_LIST,
    close_compose,
    close_thread,
    compose,
    file_into,
    on_drop,
    open_thread,
    reply,
    resize,
    send,
    toggle_read,
)
from examples.messagerie.features.shell import shell
from examples.messagerie.features.state import (
    Draft,
    Filter,
    Panel,
    View,
)

#: The drag group. Only one in this app, but naming it is what lets the
#: folders receive: they declare ``accepts=[GROUP]``.
GROUP = "message"

#: The border separating two panels. Written here rather than in the
#: theme: it is a layout decision of THIS app, not of the component.
SEPARATOR = "border-r border-text/10"

#: ⚠️ **``grow=`` on a ``ui.pane`` sizes its CHILDREN**, not the panel:
#: the theme emits ``*:grow *:basis-64``. And ``flex-none`` is mandatory —
#: the theme sets ``flex-1``, so a lone ``w-56`` is overridden (measured:
#: 447 px instead of 240).
FOLDERS_COLUMN = "flex-none w-56 " + SEPARATOR
LIST_COLUMN = "flex-none w-[26rem] " + SEPARATOR


@refreshable(deps=[Mailbox, View])
def folders_column() -> None:
    """The four folders. Each one is also a drop target."""
    view = View()
    with ui.pane(padding="sm", gap="xs", classes=FOLDERS_COLUMN):
        for key, label, icon in FOLDERS:
            active = view.folder == key
            waiting = unread_count(key)
            with ui.dropzone(
                name=f"{ZONE_FOLDER}{key}",
                accepts=[GROUP],
                on_move=on_drop,
                color="primary",
                classes="rounded-full",
            ):
                # An ``href=``, not a handler — and it is this example's
                # mechanic that allows it. The folder LIVES in the
                # address, so going to it is an ordinary navigation: the
                # link shares, middle-click opens a tab, and the
                # browser's arrows work without a line being written.
                #
                # The bonus return: the absence of ``thread`` in the
                # address puts ``View().opened`` back to its default, so
                # changing folder closes the message on its own. No
                # handler that "remembers" to reset the state, no
                # possible oversight.
                with ui.card(
                    href=f"/?folder={key}",
                    padding="none",
                    classes=(
                        "border-0 shadow-none hover:shadow-none hover:top-0 "
                        "rounded-full px-4 py-2 "
                        + (
                            "bg-primary/15 font-semibold"
                            if active
                            else "bg-transparent hover:bg-text/5"
                        )
                    ),
                ):
                    with ui.hstack(align="center", gap="sm"):
                        ui.icon(icon, size="sm")
                        ui.text(label, size="sm", classes="flex-1")
                        if waiting:
                            ui.text(str(waiting), size="xs", weight="bold")


def no_result() -> None:
    """The SEARCH's empty state — rendered client side by filter_each."""
    ui.empty_state(
        "No result",
        description="No message contains what you are looking for.",
        icon="search-x",
        size="sm",
    )


@refreshable(deps=[Mailbox, View])
def list_column() -> None:
    """The open folder's THREADS — the SOURCE of the drags.

    A mail client does not list messages, it lists EXCHANGES: ten rounds
    with the same person make ONE row. The grouping is done on the
    normalised subject (``data.thread_of``), and it is the whole thread
    one opens, files and drags.

    ``ui.filter_each`` and not a hand-written filter: the framework
    provides the primitive, and it filters **in the browser**
    (``bz-show`` per row, a ``ClientBinding`` as input). Typing therefore
    costs no request, and the search's empty state is client side too.

    ⚠️ **The trade-off is chosen, not suffered.** Client-side filtering
    requires every row to be in the DOM. At forty-odd messages it is the
    right call — instant, zero round trip. At five thousand it would be a
    page that weighs: the answer is then to filter and paginate on the
    server, which ``ui.datatable`` already does.

    An explicit ``ui.draggable`` instead of ``ui.drag_each``: the two
    iterators do not compose — each wants to be the loop. The component,
    for its part, nests inside the wrapper ``filter_each`` places, and
    the drag engine accepts it: its docs say in so many words that an
    item need not be a direct child of its zone.
    """
    view = View()
    threads = folder_threads(view.folder)
    with ui.pane(padding="none", gap="none", classes=LIST_COLUMN):
        if not threads:
            ui.empty_state(
                "This folder is empty",
                description="Drag a conversation in from another folder.",
                icon="inbox",
                size="sm",
            )
            return
        with ui.dropzone(name=ZONE_LIST, classes="flex flex-col"):
            for thread in ui.filter_each(
                threads,
                query=Filter().q,
                text=thread_text,
                key=lambda t: t["thread"],
                empty=no_result,
            ):
                with ui.draggable(key=thread["thread"], group=GROUP):
                    thread_row(thread, opened=view.opened == thread["thread"])


def participants_summary(thread: dict) -> str:
    """Who speaks in this thread, in one short line.

    One: their name. Two: "A, B". More: "A, … B", the way mail clients do
    — the full list would always overflow.
    """
    names = thread["participants"]
    if len(names) <= 2:
        return ", ".join(names)
    return names[0] + ", … " + names[-1]


def thread_row(thread: dict, *, opened: bool) -> None:
    """A conversation, on three storeys: who, what, and the last word.

    ⚠️ **Not Gmail's SINGLE line**, and that is a consequence of the
    three-panel model. Gmail fits on one line because it has NO reading
    panel: its list takes the whole width. Here the column is 26 rem, and
    the same shape rendered "Highway p… — Yo…" — measured. Three-panel
    clients (Outlook, Apple Mail, Thunderbird) all stack on three
    storeys, for this reason.

    ⚠️ ``tag="button"``: without it, ``ui.card(on_click=…)`` renders a
    ``<div hx-post>`` with neither ``tabindex`` nor ``role`` — clickable
    with a mouse, **unreachable from the keyboard**.
    """
    last = thread["last"]
    unread = thread["unread"] > 0
    how_many = len(thread["messages"])
    with ui.card(
        tag="button",
        on_click=partial(open_thread, thread["thread"]),
        padding="none",
        classes=(
            "rounded-none border-0 border-b border-text/5 shadow-none "
            "hover:shadow-none hover:top-0 px-3 py-2 cursor-pointer "
            "border-l-2 "
            + (
                "bg-primary/10 border-l-primary"
                if opened
                else "bg-transparent border-l-transparent hover:bg-text/5"
            )
        ),
    ):
        with ui.hstack(align="start", gap="sm", classes="w-full text-left"):
            # The badge's gutter is ALWAYS there, occupied or not:
            # without it, a read thread and an unread one do not line up
            # and the eye reads a shift rather than a state.
            with ui.flex(justify="center", classes="w-2 shrink-0 pt-1.5"):
                if unread:
                    # A FILLED disc. The lucide icons are drawn as
                    # strokes: ``ui.icon("circle")`` renders a ring, which
                    # reads badly at 8 px.
                    ui.flex(classes="w-2 h-2 rounded-full bg-primary")

            # ``min-w-0`` is load-bearing: without it, a ``truncate``
            # child refuses to shrink below its content's width and
            # overflows the column.
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                with ui.hstack(justify="between", align="baseline", gap="sm"):
                    with ui.hstack(align="baseline", gap="xs",
                                   classes="min-w-0"):
                        ui.text(
                            participants_summary(thread),
                            size="sm",
                            weight="bold" if unread else "normal",
                            truncate=True,
                        )
                        # The count only shows from TWO up: a "1" on a
                        # single-message conversation would be noise on
                        # most rows.
                        if how_many > 1:
                            ui.text(str(how_many), size="xs", color="muted",
                                    classes="shrink-0")
                    ui.text(short_date(last), size="xs", color="muted",
                            classes="shrink-0")
                with ui.hstack(align="center", gap="xs"):
                    ui.text(
                        thread["subject"],
                        size="sm",
                        weight="semibold" if unread else "normal",
                        truncate=True,
                        classes="flex-1 min-w-0",
                    )
                    if any(m["attachments"] for m in thread["messages"]):
                        ui.icon("paperclip", size="xs", color="muted",
                                classes="shrink-0")
                ui.text(preview(last, 110), size="xs", color="muted",
                        truncate=True)


@refreshable(deps=[Mailbox, View])
def thread_panel() -> None:
    """The open thread: all its messages, NEWEST to oldest.

    ⚠️ The order is the reverse of the conversation's, and it is
    deliberate: what has just arrived is what one wants to read, and
    chronological order buries it at the bottom of a panel you have to
    scroll. It is Outlook's and Apple Mail's choice. Gmail keeps the
    narrative order but FOLDS the old ones — the other answer to the same
    problem, which needs a per-message folding state.
    """
    view = View()
    thread = thread_in_folder(view.folder, view.opened)
    with ui.pane(padding="none", gap="none"):
        if thread is None:
            with ui.flex(justify="center", align="center",
                         classes="h-full p-8"):
                ui.empty_state(
                    "No conversation open",
                    description=(
                        "Pick a conversation on the left. Its address is "
                        "written in the browser's bar: the link shares, "
                        "and the back arrow brings you here."
                    ),
                    icon="mail-open",
                )
            return

        toolbar(thread)

        with ui.vstack(gap="none", classes="px-6 py-5"):
            with ui.hstack(justify="between", align="start", gap="md"):
                with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                    ui.heading(thread["subject"], level=2, size="lg")
                    if len(thread["messages"]) > 1:
                        ui.text(str(len(thread["messages"])) + " messages",
                                size="xs", color="muted", classes="mt-1")
                # ⚠️ "Reply" AT THE TOP, because the thread is shown
                # newest to oldest: leaving it at the foot forced you to
                # scroll the whole conversation to reply to the message
                # you had just read, at the top. The button follows the
                # message it replies to.
                ui.button("Reply", icon_left="reply", variant="outline",
                          size="sm", on_click=reply, classes="shrink-0")

            for rank, current in enumerate(reversed(thread["messages"])):
                if rank:
                    ui.divider(classes="my-4")
                message_block(current)


def message_block(current: dict) -> None:
    """A message IN a thread: compact header, then the body."""
    with ui.vstack(gap="sm", classes="pt-4"):
        with ui.hstack(align="center", gap="md", classes="min-w-0"):
            ui.avatar(name=current["sender"], size="sm", classes="shrink-0")
            with ui.vstack(gap="none", classes="min-w-0 flex-1"):
                ui.text(current["sender"], size="sm", weight="semibold",
                        truncate=True)
                ui.text(current["address"], size="xs", color="muted",
                        truncate=True)
            ui.text(current["date"], size="xs", color="muted",
                    classes="shrink-0")

        ui.markdown(current["body"])

        if current["attachments"]:
            with ui.hstack(gap="sm", wrap=True, classes="pt-1"):
                for name in current["attachments"]:
                    with ui.card(padding="sm", color="surface"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.icon("file-text", size="sm", color="muted")
                            ui.text(name, size="sm")


def toolbar(thread: dict) -> None:
    """The displayed THREAD's actions. Always visible, never on hover."""
    folder = View().folder
    has_incoming = any(m["incoming"] for m in thread["messages"])
    with ui.hstack(
        justify="between", align="center", gap="sm",
        classes="px-4 py-2 border-b border-text/10 shrink-0",
    ):
        with ui.hstack(align="center", gap="xs"):
            ui.icon_button("arrow-left", variant="ghost", size="sm",
                           on_click=close_thread, tooltip="Back to the list")
            ui.icon_button(
                "archive", variant="ghost", size="sm",
                on_click=partial(file_into, "archive"),
                disabled=folder == "archive",
                tooltip="Archive the conversation",
            )
            ui.icon_button(
                "trash-2", variant="ghost", size="sm",
                on_click=partial(file_into, "trash"),
                disabled=folder == "trash",
                tooltip="Send the conversation to the bin",
            )
            ui.icon_button(
                "inbox", variant="ghost", size="sm",
                on_click=partial(file_into, "inbox"),
                disabled=folder == "inbox",
                tooltip="Put it back in the inbox",
            )
            # ⚠️ The button exists ONLY if the thread contains received
            # mail. "Mark unread" on what one wrote oneself makes no
            # sense — and the handler refuses it too, so the rule does not
            # live only in the rendering.
            if has_incoming:
                ui.icon_button(
                    "mail" if thread["unread"] == 0 else "mail-open",
                    variant="ghost", size="sm", on_click=toggle_read,
                    tooltip="Mark unread" if thread["unread"] == 0
                    else "Mark as read",
                )
        ui.icon_button("x", variant="ghost", size="sm", on_click=close_thread,
                       tooltip="Close")


#: The compose panel's three sizes, and each one's classes. A closed
#: table rather than assembled classes: a Tailwind class built by f-string
#: only exists in dev (the production compiler does not see it in the
#: source).
PANEL_SIZES: dict[str, str] = {
    "normal": "bottom-0 right-6 w-[30rem] max-w-[calc(100vw-3rem)]",
    "small": "bottom-0 right-6 w-80",
    "full": "bottom-0 right-0 left-0 mx-auto w-[min(64rem,calc(100vw-3rem))] "
            "top-16",
}


@refreshable(deps=[Panel])
def compose_panel() -> None:
    """The compose panel, anchored bottom right, in three sizes.

    **Not a ``ui.dialog``.** A modal takes the whole screen and forbids
    re-reading the mailbox while writing — which is exactly what one
    wants to do when replying. Every mail client anchors composing in a
    corner, without blocking the rest.

    **A refreshable zone, and not a client-side ``visible=``.** The size
    changes the container's CLASSES, and a class does not bind on the
    client the way a value binds. The draft's text, for its part, stays
    in a ``ClientState``: it therefore survives the re-render, which is
    exactly what one wants of a draft.
    """
    panel = Panel()
    if not panel.opened:
        return

    draft = Draft()
    small = panel.size == "small"
    full = panel.size == "full"

    with ui.vstack(
        gap="none",
        classes=(
            "fixed z-40 rounded-t-xl border border-text/10 bg-interface "
            "shadow-2xl " + PANEL_SIZES[panel.size]
        ),
    ):
        with ui.hstack(
            justify="between", align="center",
            classes=(
                "px-4 py-2.5 rounded-t-xl bg-text/5 border-b border-text/10"
            ),
        ):
            # The title follows the subject while typing, with no round
            # trip: ``draft.subject`` is a ``ClientState``, so the
            # comparison produces a JS expression and not a Python
            # boolean. Two texts each gated by the other's inverse — the
            # same idiom as ``examples/chat``'s bubbles.
            ui.text("New message", size="sm", weight="semibold",
                    visible=draft.subject == "")
            ui.text(draft.subject, size="sm", weight="semibold",
                    truncate=True, classes="min-w-0",
                    visible=draft.subject != "")
            with ui.hstack(align="center", gap="none", classes="shrink-0"):
                ui.icon_button(
                    "chevron-up" if small else "minus",
                    variant="ghost", size="sm",
                    on_click=partial(resize, "normal" if small else "small"),
                    tooltip="Enlarge" if small else "Shrink",
                )
                ui.icon_button(
                    "minimize-2" if full else "maximize-2",
                    variant="ghost", size="sm",
                    on_click=partial(resize, "normal" if full else "full"),
                    tooltip="Leave full screen" if full else "Full screen",
                )
                ui.icon_button("x", variant="ghost", size="sm",
                               on_click=close_compose, tooltip="Close")

        # Collapsed: the title bar ALONE. The body is not hidden, it is
        # not rendered — a hidden field would stay in the tab order, and
        # that is the accessibility defect this app already met with the
        # closed dialog.
        if small:
            return

        with ui.vstack(gap="sm", classes="px-4 py-3 flex-1 min-h-0"):
            if panel.error:
                ui.alert(panel.error, color="error")
            # ``type="email"`` gives the browser's NATIVE check — a
            # comfort while typing. It does not replace the handler's
            # validation: an action can arrive without going through the
            # form.
            ui.input(value=draft.to, placeholder="To",
                     type="email", icon_left="user", size="sm")
            ui.input(value=draft.subject, placeholder="Subject", size="sm")
            ui.textarea(value=draft.body, placeholder="Your message…",
                        rows=18 if full else 7, size="sm",
                        classes="flex-1 min-h-0" if full else "")
            ui.file_upload(label="Attachments", multiple=True,
                           max_files=3, size="sm")
            with ui.hstack(justify="between", align="center", gap="sm"):
                ui.button("Send", color="primary", size="sm",
                          icon_left="send", on_click=send)
                ui.icon_button("trash-2", variant="ghost", size="sm",
                               on_click=close_compose,
                               tooltip="Discard the draft")


@page("/", layout=shell, title="Mail")
def mailbox_page() -> None:
    folders_column()
    list_column()
    thread_panel()
    compose_panel()

    ui.button(
        "New message",
        color="primary",
        icon_left="pen-line",
        on_click=compose,
        classes="fixed bottom-6 left-6 z-30 shadow-lg rounded-full",
    )

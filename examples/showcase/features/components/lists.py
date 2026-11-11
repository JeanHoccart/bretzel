"""``/lists`` — the loops that keep identity, filter, paginate and reveal."""

from functools import partial

from bretzel import refreshable, ui
from bretzel.state import ClientState, PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Write the for loop, keep your markup: keyed rows, search as you "
           "type, pages and \"show more\", all in the browser.")


def invitations() -> list[dict]:
    return [
        {"id": "inv-81", "email": "priya@northwind.io", "role": "Admin",
         "sent": "2 days ago"},
        {"id": "inv-82", "email": "marco@lumen.studio", "role": "Editor",
         "sent": "yesterday"},
        {"id": "inv-83", "email": "hana@atlasfreight.com", "role": "Viewer",
         "sent": "3 hours ago"},
    ]


class Invites(PageState):
    pending: list = field(default_factory=invitations)


def revoke(invite_id: str) -> None:
    state = Invites()
    state.pending = [i for i in state.pending if i["id"] != invite_id]


def restore() -> None:
    Invites().pending = invitations()


@refreshable
def pending_invites() -> None:
    pending = Invites().pending
    if not pending:
        with ui.empty_state(title="No pending invitations", icon="mail-check"):
            ui.button("Restore the demo", variant="outline", size="sm",
                      on_click=restore)
        return
    for invite in ui.each(pending, key="id"):
        with ui.hstack(gap="md", justify="between", align="center"):
            with ui.hstack(gap="sm", align="center"):
                ui.avatar(name=invite["email"], size="sm", color="secondary")
                with ui.vstack(gap="none"):
                    ui.text(invite["email"], weight="medium")
                    ui.text(f"Invited {invite['sent']}", size="xs",
                            color="muted")
            with ui.hstack(gap="sm", align="center"):
                ui.badge(invite["role"], variant="soft", size="sm")
                ui.button("Revoke", variant="ghost", color="error", size="sm",
                          on_click=partial(revoke, invite["id"]))


def keyed_rows() -> None:
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.vstack(gap="md"):
        ui.heading("Pending invitations", level=3, size="md")
        pending_invites()


def members() -> list[dict]:
    return [
        {"id": 1, "name": "Ada Lovelace", "role": "Engineering manager",
         "team": "Platform"},
        {"id": 2, "name": "Grace Hopper", "role": "Staff engineer",
         "team": "Platform"},
        {"id": 3, "name": "Katherine Johnson", "role": "Data scientist",
         "team": "Analytics"},
        {"id": 4, "name": "Alan Turing", "role": "Security engineer",
         "team": "Infrastructure"},
        {"id": 5, "name": "Margaret Hamilton", "role": "Head of reliability",
         "team": "Infrastructure"},
        {"id": 6, "name": "Dorothy Vaughan", "role": "Analytics engineer",
         "team": "Analytics"},
        {"id": 7, "name": "Linus Pauling", "role": "Product designer",
         "team": "Design"},
    ]


class Directory(ClientState):
    query: str = field(default="")


def member_text(member: dict) -> str:
    return f"{member['name']} {member['role']} {member['team']}"


def no_member() -> None:
    ui.empty_state(title="No one matches", icon="search-x",
                   description="Try a name, a role or a team.")


def member_directory() -> None:
    directory = Directory()
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.vstack(gap="md"):
        ui.input(value=directory.query, placeholder="Search people, roles, teams",
                 icon_left="search", clearable=True)
        with ui.vstack(gap="sm"):
            for member in ui.filter_each(members(), query=directory.query,
                                         text=member_text, key="id",
                                         empty=no_member):
                with ui.hstack(gap="sm", align="center"):
                    ui.avatar(src=f"https://i.pravatar.cc/96?u={member['name']}",
                              name=member["name"], size="sm")
                    with ui.vstack(gap="none", classes="flex-1 min-w-0"):
                        ui.text(member["name"], weight="medium")
                        ui.text(member["role"], size="sm", color="muted")
                    ui.badge(member["team"], variant="soft", size="sm")


def activity() -> list[dict]:
    people = ["Ada", "Grace", "Katherine", "Alan", "Margaret", "Dorothy"]
    actions = [("merged", "git-merge", "PR #48{} · Faster CSV export"),
               ("commented on", "message-square", "Invoice INV-20{}"),
               ("deployed", "rocket", "release 3.{}.0 to production"),
               ("closed", "circle-check", "issue #91{} · Timezone drift")]
    return [
        {"id": n, "who": people[n % 6], "verb": actions[n % 4][0],
         "icon": actions[n % 4][1], "what": actions[n % 4][2].format(n % 10),
         "when": f"{n + 1}h ago"}
        for n in range(18)
    ]


class Feed(ClientState):
    page: int = field(default=1)


def activity_feed() -> None:
    feed = Feed()
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.vstack(gap="md"):
        ui.heading("Activity", level=3, size="md")
        with ui.vstack(gap="sm"):
            for event in ui.paginate_each(activity(), page=feed.page,
                                          per_page=5, key="id"):
                with ui.hstack(gap="sm", align="center"):
                    ui.icon(event["icon"], size="sm", color="primary")
                    with ui.vstack(gap="none", classes="flex-1 min-w-0"):
                        ui.text(f"{event['who']} {event['verb']} {event['what']}",
                                size="sm", truncate=True)
                    ui.text(event["when"], size="xs", color="muted")
        ui.pagination(value=feed.page, total_pages=4, size="sm",
                      classes="self-center")


def sellers() -> list[tuple[str, str, int]]:
    return [("Lumen Studio", "Design", 48200), ("Northwind", "Retail", 41800),
            ("Atlas Freight", "Logistics", 39100), ("Kinfolk & Co", "Retail", 31500),
            ("Helio Labs", "Biotech", 27400), ("Brightwave", "Media", 22900),
            ("Pinecone Bank", "Finance", 18700), ("Orbital Foods", "Food", 15200),
            ("Mosaic Health", "Health", 12800), ("Quill & Ink", "Publishing", 9600)]


def seller_name(seller: tuple[str, str, int]) -> str:
    return seller[0]


class Leaderboard(ClientState):
    limit: int = field(default=3)


def top_customers() -> None:
    board = Leaderboard()
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.vstack(gap="md"):
        with ui.hstack(justify="between", align="center", wrap=True):
            ui.heading("Top customers · September", level=3, size="md")
            with ui.hstack(gap="xs"):
                ui.button("Top 3", variant="outline", size="xs",
                          on_click=board.limit.set(3))
                ui.button("Top 10", variant="outline", size="xs",
                          on_click=board.limit.set(10))
        with ui.vstack(gap="sm"):
            for rank, (name, industry, revenue) in enumerate(
                    ui.limit_each(sellers(), limit=board.limit,
                                  key=seller_name), start=1):
                with ui.hstack(gap="sm", align="center"):
                    ui.badge(f"#{rank}", variant="soft", size="sm")
                    ui.text(name, weight="medium", classes="flex-1")
                    ui.text(industry, size="sm", color="muted")
                    ui.text(f"${revenue:,}", size="sm", weight="medium")


def comments() -> list[dict]:
    return [
        {"id": 1, "who": "Priya Raman", "text": "Shipped the new export. "
         "CSV of 40k rows now takes 3 seconds."},
        {"id": 2, "who": "Marco Rossi", "text": "Nice! Does it keep the "
         "column order from the table view?"},
        {"id": 3, "who": "Priya Raman", "text": "It does, hidden columns "
         "are left out too."},
        {"id": 4, "who": "Hana Sato", "text": "Customers on the Pro plan "
         "have been asking for this since March."},
        {"id": 5, "who": "Tom Becker", "text": "Adding it to the changelog "
         "for Thursday."},
        {"id": 6, "who": "Inès Moreau", "text": "I will update the empty "
         "state illustration to match."},
        {"id": 7, "who": "Marco Rossi", "text": "Closing the original "
         "ticket, thanks everyone."},
    ]


class Thread(ClientState):
    shown: int = field(default=3)


def comment_thread() -> None:
    thread = Thread()
    with ui.card(padding="md", classes="w-full max-w-xl"), ui.vstack(gap="md"):
        ui.heading("7 comments", level=3, size="md")
        with ui.vstack(gap="md"):
            for comment in ui.show_more(comments(), count=thread.shown, step=3,
                                        label="Show more comments", key="id"):
                with ui.hstack(gap="sm", align="start"):
                    ui.avatar(src=f"https://i.pravatar.cc/96?u={comment['who']}",
                              name=comment["who"], size="sm")
                    with ui.vstack(gap="none"):
                        ui.text(comment["who"], size="sm", weight="medium")
                        ui.text(comment["text"], size="sm")


def page() -> None:
    page_header("each", "Lists", SUMMARY)
    example("Rows that keep their identity", keyed_rows,
            uses=[invitations, Invites, revoke, restore, pending_invites],
            note="ui.each gives every row a stable key, so removing one on "
                 "the server leaves the others exactly as they were.")
    example("A searchable directory", member_directory,
            uses=[members, Directory, member_text, no_member],
            note="ui.filter_each hides what does not match as you type, "
                 "without a request, and shows empty= when nothing is left.")
    example("A paginated feed", activity_feed, uses=[activity, Feed],
            note="ui.paginate_each shows one window of the list; "
                 "ui.pagination moves it, all in the browser.")
    example("Top N", top_customers, uses=[sellers, seller_name, Leaderboard],
            note="ui.limit_each keeps the first N visible. Bind the limit and "
                 "a button can change it.")
    example("Show more", comment_thread, uses=[comments, Thread],
            note="ui.show_more reveals the rows step by step, and hides its "
                 "button once everything is shown.")

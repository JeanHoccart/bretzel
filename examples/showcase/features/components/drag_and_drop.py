"""``/drag-and-drop`` — cards you pick up and put somewhere else."""

from bretzel import refreshable, ui
from bretzel.components import Move
from bretzel.state import PageState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("Pick a card up, drop it elsewhere: the drop calls a Python "
           "handler with a typed Move, and the server decides.")


def starting_board() -> dict[str, list[dict]]:
    return {
        "backlog": [
            {"id": "t1", "title": "Dark mode for charts", "tag": "Design",
             "owner": "Hedy Lamarr"},
            {"id": "t2", "title": "Export invoices to CSV", "tag": "Billing",
             "owner": "Alan Turing"},
        ],
        "doing": [
            {"id": "t3", "title": "Faster customer search", "tag": "Search",
             "owner": "Grace Hopper"},
        ],
        "done": [
            {"id": "t4", "title": "SSO with Google", "tag": "Auth",
             "owner": "Ada Lovelace"},
        ],
    }


class Board(PageState):
    columns: dict = field(default_factory=starting_board)


def move_task(m: Move) -> None:
    board = Board()
    columns = {name: list(cards) for name, cards in board.columns.items()}
    card = columns[m.from_zone].pop(m.from_index)
    columns[m.to_zone].insert(m.to_index, card)
    board.columns = columns


def task_card(task: dict) -> None:
    with ui.card(padding="sm"), ui.vstack(gap="sm"):
        ui.text(task["title"], weight="medium", size="sm")
        with ui.hstack(justify="between"):
            ui.badge(task["tag"], variant="soft", size="sm")
            ui.avatar(name=task["owner"], size="xs", color="secondary")


@refreshable
def kanban() -> None:
    columns = Board().columns
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        for name, title in (("backlog", "Backlog"), ("doing", "In progress"),
                            ("done", "Done")):
            with ui.vstack(gap="sm"):
                with ui.hstack(gap="xs"):
                    ui.text(title, weight="semibold", size="sm")
                    ui.badge(str(len(columns[name])), size="xs", variant="soft")
                with ui.dropzone(name=name, accepts=["task"], on_move=move_task,
                                 color="success" if name == "done" else "primary",
                                 classes="min-h-40"), ui.vstack(gap="sm"):
                    for task in ui.drag_each(columns[name], group="task", key="id"):
                        task_card(task)


def board_example() -> None:
    kanban()


class Priorities(PageState):
    items: list = field(default_factory=lambda: [
        "Security review before launch",
        "Migrate billing to the new API",
        "Onboarding emails, round two",
        "Clean up unused feature flags",
    ])


def reorder(m: Move) -> None:
    state = Priorities()
    items = list(state.items)
    items.insert(m.to_index, items.pop(m.from_index))
    state.items = items


def is_pinned(item: str) -> bool:
    return item.startswith("Security")


@refreshable
def priority_list() -> None:
    with ui.dropzone(on_move=reorder, classes="w-full max-w-md"), ui.vstack(gap="xs"):
        for rank, item in enumerate(
            ui.drag_each(Priorities().items, handle=True, disabled=is_pinned),
            start=1,
        ):
            with ui.card(padding="sm"), ui.hstack(gap="sm"):
                ui.badge(str(rank), size="sm", variant="soft")
                ui.text(item, size="sm")
                if is_pinned(item):
                    ui.icon("pin", size="sm", color="muted")


def reorder_example() -> None:
    priority_list()


class Downloads(PageState):
    files: list = field(default_factory=lambda: [
        "Q3-report.pdf", "brand-kit.zip", "invoice-2041.pdf", "team-photo.jpg",
    ])
    archived: int = field(default=0)


def archive_file(m: Move) -> None:
    state = Downloads()
    state.files = [name for name in state.files if name != m.item_key]
    state.archived += 1


@refreshable
def downloads() -> None:
    state = Downloads()
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md", classes="w-full max-w-xl"):
        with ui.dropzone(name="files"), ui.vstack(gap="xs"):
            for name in ui.drag_each(state.files, group="file"):
                with ui.card(padding="sm"), ui.hstack(gap="sm"):
                    ui.icon("file", size="sm", color="muted")
                    ui.text(name, size="sm", truncate=True)
        with (
            ui.dropzone(name="archive", accepts=["file"], terminal=True,
                        locked=True, color="warning", on_move=archive_file,
                        classes="min-h-32"),
            ui.card(padding="md", classes="h-full"),
            ui.vstack(gap="xs", align="center", justify="center", classes="h-full"),
        ):
            ui.icon("archive", size="lg", color="warning")
            ui.text(f"Drop here to archive · {state.archived} so far",
                    size="sm", color="muted", align="center")


def archive_example() -> None:
    downloads()


def team() -> list[str]:
    return ["Ada Lovelace", "Grace Hopper", "Alan Turing", "Hedy Lamarr"]


class Review(PageState):
    reviewer: str = field(default="")
    approver: str = field(default="Grace Hopper")


def assign(m: Move) -> None:
    review = Review()
    if m.to_zone == "reviewer":
        review.reviewer = m.item_key
    else:
        review.approver = m.item_key


@refreshable
def review_roles() -> None:
    review = Review()
    with ui.vstack(gap="md", classes="w-full max-w-xl"):
        with ui.dropzone(name="team"), ui.hstack(gap="sm", wrap=True):
            for person in team():
                with (
                    ui.draggable(key=person, group="person"),
                    ui.card(padding="sm"),
                    ui.hstack(gap="xs"),
                ):
                    ui.avatar(name=person, size="xs")
                    ui.text(person, size="sm")
        with ui.grid(cols=2, gap="md"):
            for role, person in (("reviewer", review.reviewer),
                                 ("approver", review.approver)):
                with (
                    ui.dropzone(name=role, accepts=["person"], holds="one",
                                on_move=assign),
                    ui.card(padding="md", classes="h-full"),
                    ui.vstack(gap="xs", align="center"),
                ):
                    ui.text(role.capitalize(), size="xs", color="muted")
                    if person:
                        ui.avatar(name=person, size="md")
                        ui.text(person, size="sm", weight="medium")
                    else:
                        ui.icon("user-plus", size="xl", color="muted")
                        ui.text("Drop someone here", size="sm", color="muted")


def roles_example() -> None:
    review_roles()


def page() -> None:
    page_header("drag_and_drop", "Drag and drop", SUMMARY)
    example("A kanban board", board_example,
            uses=[starting_board, Board, move_task, task_card, kanban], full=True,
            note="Three dropzones share the group \"task\". A drop posts a Move "
                 "(item_key, from_zone, to_zone, indexes) to move_task, which "
                 "updates the board on the server.")
    example("Reorder a list", reorder_example,
            uses=[Priorities, reorder, is_pinned, priority_list],
            note="handle=True grabs by the grip only, and disabled= takes a "
                 "predicate: the pinned item cannot be picked up.")
    example("Drop to archive", archive_example,
            uses=[Downloads, archive_file, downloads],
            note="terminal=True makes a zone an action rather than a column: "
                 "the file never lands in it, the handler archives it.")
    example("Fill a role", roles_example,
            uses=[team, Review, assign, review_roles],
            note='holds="one" marks a slot for a single person; dropping '
                 "someone new replaces the current one. The team row uses "
                 "ui.draggable directly, in an ordinary loop.")

"""``/combobox`` — a select you can type into."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A select with a search box, for lists too long to scroll: type a "
           "few letters, pick one value or many.")

COUNTRIES = [
    ("ar", "Argentina"), ("au", "Australia"), ("at", "Austria"),
    ("be", "Belgium"), ("br", "Brazil"), ("ca", "Canada"), ("dk", "Denmark"),
    ("fi", "Finland"), ("fr", "France"), ("de", "Germany"), ("in", "India"),
    ("ie", "Ireland"), ("it", "Italy"), ("jp", "Japan"), ("mx", "Mexico"),
    ("nl", "Netherlands"), ("no", "Norway"), ("pl", "Poland"),
    ("pt", "Portugal"), ("es", "Spain"), ("se", "Sweden"),
    ("ch", "Switzerland"), ("gb", "United Kingdom"), ("us", "United States"),
]


def search_a_long_list() -> None:
    with ui.form_field(label="Country of residence", classes="max-w-xs"):
        ui.combobox(COUNTRIES, placeholder="Search 24 countries…")


SKILLS = [("python", "Python"), ("sql", "SQL"), ("figma", "Figma"),
          ("react", "React"), ("go", "Go"), ("k8s", "Kubernetes"),
          ("ml", "Machine learning"), ("copy", "Copywriting"),
          ("research", "User research")]


def several_values() -> None:
    with ui.form_field(label="Skills", hint="Used to suggest reviewers.",
                       classes="max-w-sm"):
        ui.combobox(SKILLS, multiple=True, bulk_actions=True,
                    value=["python", "sql"], placeholder="Add skills…",
                    empty_text="No skill with that name.")


PEOPLE = [("maya", "Maya Chen"), ("omar", "Omar Haddad"),
          ("lucia", "Lucía Romero"), ("tom", "Tom Becker"),
          ("aiko", "Aiko Tanaka"), ("sam", "Sam Okafor")]


def person_option(value, label):
    with ui.hstack(gap="sm") as row:
        ui.avatar(src=f"https://i.pravatar.cc/96?u={value}", name=label, size="xs")
        ui.text(label)
    return row


def assignee() -> None:
    with ui.form_field(label="Assignee", classes="max-w-xs"):
        ui.combobox(PEOPLE, value="omar", render=person_option,
                    placeholder="Assign to…")


ACCOUNTS = {
    "northwind": ("Northwind Traders", "Seattle", "€48,200 ARR", "Enterprise"),
    "lumen": ("Lumen Studio", "Lisbon", "€6,900 ARR", "Team"),
    "atlas": ("Atlas Freight", "Rotterdam", "€31,400 ARR", "Enterprise"),
    "kinfolk": ("Kinfolk & Co", "Copenhagen", "€1,200 ARR", "Starter"),
}


class PickedAccount(ClientState):
    account: str = field(default="northwind")


def live_pick() -> None:
    pick = PickedAccount()
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        ui.combobox([(key, row[0]) for key, row in ACCOUNTS.items()],
                    value=pick.account, placeholder="Find an account…")
        for key, (name, city, revenue, plan) in ACCOUNTS.items():
            with ui.hstack(gap="md", visible=pick.account == key):
                ui.avatar(name=name, size="lg", color="primary")
                with ui.vstack(gap="none"):
                    ui.text(name, weight="semibold", size="lg")
                    ui.text(f"{city} · {revenue}", color="muted")
                ui.badge(plan, variant="soft", classes="ml-auto")


LABELS = [("bug", "Bug"), ("feature", "Feature request"),
          ("billing", "Billing"), ("docs", "Documentation"),
          ("security", "Security")]


def custom_trigger() -> None:
    with ui.hstack(gap="md"):
        ui.text("Issue #4821 · Export fails on large workspaces", weight="medium")
        ui.combobox(LABELS, multiple=True, placeholder="Filter labels…",
                    trigger=ui.button("Labels", icon_left="tag", size="sm",
                                      variant="outline"))


def page() -> None:
    page_header("combobox", "Combobox", SUMMARY)
    example("Search a long list", search_a_long_list,
            note="Typing filters the options; accents and word order do not "
                 "matter.")
    example("Several values", several_values,
            note="multiple=True shows the picks as pills; empty_text is "
                 "what the panel says when nothing matches.")
    example("Options with avatars", assignee,
            note="render= draws each option — the search still runs on the "
                 "label.")
    example("A pick that updates the page", live_pick, uses=[PickedAccount],
            note="The value lives in a ClientState: the account card follows "
                 "the pick in the browser. Give on_change a Python function "
                 "when the server needs it.")
    example("Your own trigger", custom_trigger,
            note="trigger= replaces the field with any component — a small "
                 "button in a toolbar, here.")

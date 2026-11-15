"""Start with a mockup: describe a screen, see it, validate it, then wire it.

The mockup on this page is not a picture. ``repair_jobs`` is a real
Bretzel screen on invented data, rendered live, and the code shown under
it is read from this module by ``source_block`` — it is the code that
runs, so it cannot drift from what the reader sees.
"""

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import source_block

PATH = "/mockup"

JOBS = [
    {"customer": "Camille Martin", "bike": "City bike · Gazelle Esprit",
     "problem": "Rear derailleur bent, the chain skips under load",
     "status": "Waiting for parts", "price": 35.0},
    {"customer": "Thomas Leroy", "bike": "Road bike · Trek Domane AL 2",
     "problem": "Brake bleed front and rear, new pads, and a hydraulic hose "
                "that weeps at the lever after every long descent",
     "status": "In progress", "price": 82.5},
    {"customer": "Ana Silva", "bike": "Cargo bike · Urban Arrow Family",
     "problem": "Front puncture", "status": "Ready", "price": 18.0},
    {"customer": "Paul Dubois", "bike": "Kids' bike",
     "problem": "Yearly check before the holidays", "status": "Booked", "price": 30.0},
    {"customer": "Sofia Garnier", "bike": "E-bike · Moustache Samedi 28",
     "problem": "Motor error E-07 at start-up", "status": "In progress", "price": 64.0},
    {"customer": "Marc Fournier", "bike": "Gravel · Specialized Diverge",
     "problem": "Full service", "status": "Ready", "price": 145.0},
]
STATUS_COLORS = {"Booked": "muted", "In progress": "info",
                 "Waiting for parts": "warning", "Ready": "success"}


def price(amount: float) -> str:
    return f"€{amount:,.2f}"


def todays_jobs() -> list[dict]:
    """Invented for the mockup. Wiring replaces this body, and only it."""
    return JOBS


def nothing() -> None:
    ui.notification("Mockup: nothing is saved.")


def repair_jobs() -> None:
    """Today's repair jobs of a bike shop — the screen being decided."""
    jobs = todays_jobs()
    ready = [job for job in jobs if job["status"] == "Ready"]
    with ui.vstack(gap="lg"):
        with ui.hstack(justify="between", align="center", gap="md", wrap=True):
            with ui.vstack(gap="none"):
                ui.heading("Today's repairs", level=2)
                ui.text(f"{len(jobs)} bikes in the workshop", size="sm", color="muted")
            ui.button("New repair", icon_left="plus", on_click=nothing)
        with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
            ui.stat(label="Booked today", value=len(jobs))
            ui.stat(label="Ready to collect", value=len(ready))
            ui.stat(label="Expected today", value=price(sum(job["price"] for job in jobs)))
        with ui.vstack(gap="sm"):
            for job in jobs:
                with ui.card(padding="md"):
                    with ui.hstack(justify="between", align="center", gap="md", wrap=True):
                        # A minimum width: on a phone the status and the price
                        # wrap under the text instead of crushing it.
                        with ui.vstack(gap="xs", classes="min-w-48 flex-1"):
                            with ui.hstack(gap="sm", align="center", wrap=True):
                                ui.text(job["customer"], weight="medium")
                                ui.text(job["bike"], size="sm", color="muted")
                            ui.text(job["problem"], size="sm")
                        with ui.hstack(gap="sm", align="center", classes="shrink-0"):
                            ui.badge(job["status"], variant="soft",
                                     color=STATUS_COLORS[job["status"]])
                            ui.text(price(job["price"]), weight="medium",
                                    classes="tabular-nums")


def step(number: str, title: str, who: str, text: str) -> None:
    with ui.card():
        with ui.vstack(gap="sm"):
            with ui.hstack(gap="sm", align="center"):
                ui.badge(number, color="primary")
                ui.text(who, size="sm", color="muted")
            ui.heading(title, level=3)
            ui.text(text, color="muted", size="sm")


@page(PATH, layout=shell, title="Start with a mockup · Bretzel docs",
      description="The Bretzel workflow: describe a screen, get a real mockup on invented data built from the components the app ships, validate it on screenshots, then wire the same code.")
def mockup_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="xl"):
            with ui.vstack(gap="sm", classes="max-w-4xl"):
                with ui.hstack(align="center", gap="sm", wrap=True):
                    ui.badge("Workflow", color="primary", variant="soft")
                    ui.badge("Mockup first", color="muted", variant="outline")
                ui.heading("Start with a mockup", level=1, size="4xl")
                ui.text(
                    "Before any real logic exists, you see the screen. A Bretzel "
                    "mockup is a throwaway page on invented data, made of the very "
                    "components, theme and layout the finished screen will ship. "
                    "What you approve is what you get: nothing is redrawn when it "
                    "is wired.",
                    color="muted", size="lg",
                )

            with ui.grid(cols=2, gap="md", classes="max-lg:grid-cols-1"):
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.heading("Elsewhere", level=2, size="lg")
                        ui.text(
                            "A mockup is a picture. Someone redraws it in code, the "
                            "spacing drifts, a state nobody drew shows up, and the "
                            "screen you approved is not the one you get.",
                            color="muted",
                        )
                with ui.card(color="primary"):
                    with ui.vstack(gap="sm"):
                        ui.heading("In Bretzel", level=2, size="lg")
                        ui.text(
                            "The mockup is the screen's code, on invented data. "
                            "Validating it decides the layout, the words and the "
                            "components; wiring only replaces the data.",
                        )

            with ui.vstack(gap="md"):
                ui.heading("Four steps, one screen at a time", level=2)
                with ui.grid(cols=4, gap="md", classes="max-xl:grid-cols-2 max-md:grid-cols-1"):
                    step("1", "Describe", "You",
                         "Who opens the screen, what it shows, what can be done "
                         "from it. In your words, not in a spec.")
                    step("2", "Mock it", "Your agent",
                         "It writes the mockup on plausible data — a long label, "
                         "an empty case — and screenshots it in a real browser, "
                         "light and dark.")
                    step("3", "Validate", "You",
                         "Cards or a table? A missing column? A round or two on "
                         "screenshots, before a line of real logic exists.")
                    step("4", "Build it", "Your agent",
                         "Invented data becomes typed state and real queries. The "
                         "screen is checked against the mockup you approved.")

            with ui.vstack(gap="md"):
                ui.heading("A mockup, live on this page", level=2)
                ui.text(
                    "Not a screenshot: the screen below is rendered by Bretzel right "
                    "now, from the code under it. Click New repair — a mockup's "
                    "actions do nothing on purpose.",
                    color="muted",
                )
                with ui.card(padding="lg"):
                    repair_jobs()
                source_block(price, todays_jobs, nothing, repair_jobs)
                ui.text(
                    "JOBS is a list of six invented jobs, chosen to meet the cases "
                    "the real screen will: a long description, every status, a "
                    "price that needs its thousands separator one day.",
                    color="muted", size="sm",
                )

            with ui.vstack(gap="md"):
                ui.heading("Build it: only the data changes", level=2)
                ui.text(
                    "Once the screen is approved, the file moves into the app. "
                    "repair_jobs() is not touched: it called todays_jobs() on "
                    "invented data, it calls it on the database now.",
                    color="muted",
                )
                with ui.grid(cols=2, gap="md", classes="max-lg:grid-cols-1"):
                    with ui.vstack(gap="xs"):
                        ui.text("In the mockup", weight="semibold", size="sm")
                        ui.code(
                            "def todays_jobs() -> list[dict]:\n"
                            "    return JOBS          # invented\n",
                            lang="python",
                        )
                    with ui.vstack(gap="xs"):
                        ui.text("Wired", weight="semibold", size="sm")
                        ui.code(
                            "from bretzel.state import Topic, reads\n\n"
                            "REPAIRS = Topic(\"repairs\")\n\n\n"
                            "@reads(REPAIRS)\n"
                            "def todays_jobs() -> list[dict]:\n"
                            "    return db.fetch_all(\n"
                            "        \"select * from repairs where day = current_date\")\n",
                            lang="python",
                        )
                ui.text(
                    "New repair gets a real handler marked @writes(REPAIRS), and "
                    "every open screen that read the repairs follows. A change of "
                    "design goes back to the mockup, not into the wiring.",
                    color="muted", size="sm",
                )

            with ui.vstack(gap="md"):
                ui.heading("See it yourself", level=2)
                ui.text(
                    "A mockup is one file with its own app: mockups/repair_jobs.py holds "
                    "the four functions above, then a page and the app.",
                    color="muted",
                )
                ui.code(
                    "import sys\n\n"
                    "from bretzel import Bretzel, page, ui\n\n"
                    "# … JOBS, price(), todays_jobs(), nothing(), repair_jobs(), as above …\n\n\n"
                    "@page(\"/\", title=\"Today's repairs — mockup\")\n"
                    "def home() -> None:\n"
                    "    with ui.container(width=\"lg\", classes=\"py-8\"):\n"
                    "        repair_jobs()\n\n\n"
                    "app = Bretzel(title=\"Mockup\", secret_key=\"mockup-only-not-a-real-secret\", "
                    "mode=\"dev\")\n"
                    "app.include(sys.modules[__name__])\n",
                    lang="python",
                )
                ui.text(
                    "Three commands judge it, screenshot it, and let you click through it. "
                    "The probe needs its extra, installed once.",
                    color="muted",
                )
                ui.code(
                    "pip install \"bretzel[probe]\"\n"
                    "bretzel check mockups/repair_jobs.py\n"
                    "bretzel probe mockups.repair_jobs:app --out mockups/shots/repair_jobs\n"
                    "bretzel dev mockups.repair_jobs:app",
                    lang="bash",
                )
                ui.text(
                    "bretzel probe drives a real browser and writes the screenshots "
                    "in light and dark: that is what you validate.",
                    color="muted", size="sm",
                )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("With Claude Code, in plain words", level=2, size="lg")
                    ui.text(
                        "The Bretzel plugin brings this workflow to your agent: ask "
                        "for a screen, get the mockup and its screenshots, answer "
                        "with changes, then let it wire the screen. Its hook runs "
                        "bretzel check on every Python file the agent writes, once "
                        "bretzel is installed in the project, and hands the findings back.",
                        color="muted",
                    )
                    ui.code(
                        "claude plugin marketplace add JeanHoccart/bretzel\n"
                        "claude plugin install bretzel@bretzel",
                        lang="bash",
                    )
                    ui.text(
                        "“I run a small bike repair shop. Show me what a screen "
                        "listing today's repair jobs would look like before you "
                        "build anything.”",
                        size="sm",
                    )

            with ui.hstack(gap="sm", wrap=True):
                ui.button("Start in 5 minutes", href="/quickstart", icon_right="arrow-right")
                ui.button("Describe the UI", href="/describe", variant="outline")

"""``/page-utilities`` — the pieces that shape a page without drawing much."""

import asyncio

from bretzel import ui
from examples.showcase.app.layout import shell
from examples.showcase.lib.example import example, page_header

SUMMARY = ("The tab title, the share preview, where a page lands in its "
           "layout, wrapper-free groups and an in-flight indicator.")

PAGE_TITLE = "Page utilities — Bretzel UI"


MESSAGES = [("Lena Novak", "Safari date bug — fixed in #418", True),
            ("Stripe", "Payout of €4,280.00 is on its way", True),
            ("Idris Okafor", "Standup notes, Monday", True),
            ("Maya Chen", "New pricing page draft", False)]


def tab_title() -> None:
    unread = sum(1 for _sender, _subject, is_unread in MESSAGES if is_unread)
    ui.title(f"({unread}) {PAGE_TITLE}")
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="sm"):
        with ui.hstack(gap="sm"):
            ui.icon("inbox", color="primary")
            ui.text("Inbox", weight="medium")
            ui.badge(f"{unread} unread", color="error", variant="soft", size="sm")
        for sender, subject, is_unread in MESSAGES:
            with ui.hstack(gap="sm", classes="min-w-0"):
                ui.text(sender, size="sm", weight="semibold" if is_unread else "normal",
                        classes="w-32 shrink-0")
                ui.text(subject, size="sm", truncate=True, classes="min-w-0",
                        color=None if is_unread else "muted")


def share_preview() -> None:
    ui.meta_tag(property="og:title", content=PAGE_TITLE)
    ui.meta_tag(property="og:image",
                content="https://picsum.photos/seed/bretzel/1200/630")
    ui.meta_tag(name="twitter:card", content="summary_large_image")
    with ui.card(padding="none", classes="w-full max-w-md overflow-hidden"):
        ui.image("https://picsum.photos/seed/bretzel/1200/630",
                 alt="Share image for this page", ratio="wide")
        with ui.vstack(gap="none", classes="p-4"):
            ui.text("showcase.bretzel-py.dev", size="xs", color="muted")
            ui.text(PAGE_TITLE, weight="semibold")
            ui.text("How the link looks when pasted in Slack or on LinkedIn.",
                    size="sm", color="muted")


def layout_sketch() -> None:
    with (ui.card(padding="sm", classes="w-full max-w-2xl"),
          ui.hstack(gap="sm", align="stretch", classes="h-56")):
        with ui.vstack(gap="sm", classes="w-40 shrink-0"):
            ui.text("ui.sidebar", size="xs", color="muted", classes="font-mono")
            for width in ("80%", "60%", "70%", "50%"):
                ui.skeleton(variant="text", width=width, animated=False)
        with (ui.card(padding="md", classes="flex-1"),
              ui.vstack(gap="sm")):
            ui.text("ui.outlet()", weight="semibold", color="primary",
                    classes="font-mono")
            ui.text("Every page renders here.", size="sm", color="muted")
            ui.skeleton(variant="rectangle", height="5rem", animated=False)


PLANS = [{"customer": "Northwind Traders", "plan": "Business", "trial": False},
         {"customer": "Lumen Studio", "plan": "Team", "trial": True},
         {"customer": "Atlas Freight", "plan": "Starter", "trial": False}]


def plan_cell(value, row):
    with ui.fragment() as cell:
        ui.text(value, weight="medium")
        if row["trial"]:
            ui.badge("Trial", color="info", variant="soft", size="xs",
                     classes="ml-2")
    return cell


def fragment_demo() -> None:
    ui.table(columns=[ui.column("customer", label="Customer"),
                      ui.column("plan", label="Plan", render=plan_cell)],
             rows=PLANS, classes="w-full max-w-lg")


async def publish_changes() -> None:
    await asyncio.sleep(1.5)


def pending_demo() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.vstack(gap="none"):
            ui.text("Pricing page", weight="semibold")
            ui.text("3 unpublished changes", size="sm", color="muted")
        with ui.hstack(gap="sm", justify="between"):
            ui.text("Publishing to 3 regions…", size="sm", color="primary",
                    visible=ui.pending(publish_changes))
            ui.button("Publish", icon_left="upload-cloud", on_click=publish_changes,
                      loading=ui.pending(), classes="ml-auto")


def page() -> None:
    page_header(("title", "meta_tag", "outlet", "fragment", "pending"), "Page utilities", SUMMARY)
    example("A tab title from your data", tab_title,
            note="ui.title replaces the route's title with one computed while "
                 "the page renders — this very tab starts with the unread count.")
    example("The link preview", share_preview,
            note="ui.meta_tag adds a <meta> to the page's head: Open Graph "
                 "for LinkedIn and Slack, twitter:card for X.")
    example("Where a page lands", layout_sketch, uses=[shell],
            note="ui.outlet marks the spot in a layout where each page renders. "
                 "This site's own shell, in the code tab, puts it inside the "
                 "pane next to the sidebar.")
    example("A group without a wrapper", fragment_demo, uses=[plan_cell],
            note="ui.fragment gathers components into one value that renders "
                 "with no element around it — here, a table cell made of a "
                 "name and a badge.")
    example("An action in flight", pending_demo, uses=[publish_changes],
            note="ui.pending() is true while an action runs, after a 200 ms "
                 "grace so fast actions never flicker. Give it a handler to "
                 "follow that action from anywhere on the page.")

"""``/progress`` — how far along, at a glance."""

from bretzel import ui
from bretzel.state import ClientState, field
from examples.showcase.lib.example import example, page_header

SUMMARY = ("A bar for how much is done: any maximum, a label of your own, "
           "an indeterminate mode for when you cannot tell.")


def storage() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="md"):
        with ui.hstack(justify="between"):
            ui.heading("Storage", level=3, size="md")
            ui.button("Upgrade", size="xs", variant="soft")
        ui.progress(18.4, max=50, label="18.4 GB of 50 GB", show_label=True)
        ui.text("Attachments take up most of it. Old exports are removed "
                "after 90 days.", color="muted", size="sm")


def usage_by_resource() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        for resource, used, color in (("Seats", 34, "success"),
                                      ("API calls", 76, "warning"),
                                      ("Email sends", 98, "error"),
                                      ("Automations", 52, "info")):
            with ui.vstack(gap="xs"):
                with ui.hstack(justify="between"):
                    ui.text(resource, size="sm", weight="medium")
                    ui.text(f"{used}%", size="sm", color="muted")
                ui.progress(used, color=color)


def sizes() -> None:
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        for size in ("xs", "sm", "md", "lg", "xl"):
            ui.progress(64, size=size)


def indeterminate() -> None:
    with ui.card(padding="md", classes="w-full max-w-md"), ui.vstack(gap="sm"):
        ui.text("Preparing your export", weight="medium")
        ui.progress(indeterminate=True, size="sm")
        ui.text("We will email you the file when it is ready.", color="muted",
                size="sm")


class ContactImport(ClientState):
    done: int = field(default=1)


def live_import() -> None:
    done = ContactImport().done
    with ui.vstack(gap="md", classes="w-full max-w-md"):
        ui.progress(done, max=4, label=done * 250 + " of 1,000 contacts",
                    show_label=True)
        with ui.hstack(gap="sm", justify="end"):
            ui.button("Start over", variant="ghost", size="sm",
                      on_click=done.set(0))
            ui.button("Import next batch", size="sm", icon_left="upload",
                      disabled=done == 4, on_click=done.increment())


def page() -> None:
    page_header("progress", "Progress", SUMMARY)
    example("Storage quota", storage,
            note="max= sets the scale, label= says it in words.")
    example("Colours", usage_by_resource,
            note="Colour carries the verdict: plenty left, getting close, "
                 "almost out.")
    example("Sizes", sizes)
    example("Indeterminate", indeterminate,
            note="When the end is unknown, the bar moves instead of filling.")
    example("Driven by a state", live_import, uses=[ContactImport],
            note="value= and label= follow a ClientState field, so each click "
                 "moves the bar without a round trip. The same bar fed by a "
                 "server state moves when its zone re-renders.")

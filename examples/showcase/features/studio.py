"""``/studio`` — tune a theme live on a real screen, and leave with the code.

The page drives the ``Studio`` store that paints the WHOLE showcase: a
knob moved here repaints this preview, and every catalogue page after
it. Nothing goes to the server; the output is code — the ``Theme(...)``
to paste into ``core/theme.py``. Git is the persistence.
"""

from bretzel import ui
from bretzel.state import ClientExpression
from examples.showcase.lib.identities import IDENTITIES
from examples.showcase.lib.preview import sample_screen
from examples.showcase.lib.studio import (
    FONTS,
    SLOTS,
    Studio,
    export_expression,
    reset_expression,
)

SUMMARY = ("Pick an identity, then tune its colours, corners, stroke, density "
           "and type on a real screen — and copy the Theme() it makes.")

#: ``(label, store field, min, max, step)`` — the non-colour knobs.
SHAPES: list[tuple[str, str, float, float, float]] = [
    ("Containers radius (rem)", "box", 0.0, 2.0, 0.125),
    ("Controls radius (rem)", "field_", 0.0, 2.0, 0.125),
    ("Marks radius (rem)", "selector", 0.0, 1.0, 0.0625),
    ("Stroke (px)", "stroke", 0.0, 3.0, 0.5),
    ("Controls spacing (rem per step)", "spacing", 0.15, 0.3, 0.005),
    ("Inside containers (rem per step)", "space_box", 0.1, 0.375, 0.005),
    ("Between blocks (rem per step)", "space_gap", 0.1, 0.375, 0.005),
]


def identities_panel() -> None:
    with ui.vstack(gap="sm"):
        ui.text("Start from", size="sm", weight="semibold")
        with ui.hstack(gap="xs", wrap=True):
            for identity in IDENTITIES:
                ui.button(identity.name, variant="outline", size="sm",
                          on_click=identity.apply())


def colors_panel(settings: Studio) -> None:
    with ui.vstack(gap="sm"):
        with ui.hstack(justify="between"):
            ui.text("Colours", size="sm", weight="semibold")
            ui.text("light · dark", size="xs", color="muted")
        for name, role, _light, _dark in SLOTS:
            with ui.vstack(gap="xs"):
                with ui.hstack(gap="sm", align="baseline"):
                    ui.text(name, size="sm", weight="medium")
                    ui.text(role, size="xs", color="muted", truncate=True)
                with ui.grid(cols=2, gap="xs"):
                    # A theme colour is never empty: no clear cross.
                    ui.color_picker(value=getattr(settings, name), size="sm",
                                    clearable=False)
                    ui.color_picker(value=getattr(settings, f"d_{name}"), size="sm",
                                    clearable=False)


def shapes_panel(settings: Studio) -> None:
    with ui.vstack(gap="md"):
        ui.text("Shape & type", size="sm", weight="semibold")
        for label, attr, low, high, step in SHAPES:
            with ui.vstack(gap="xs"):
                ui.text(label, size="xs", color="muted")
                ui.slider(value=getattr(settings, attr), min=low, max=high,
                          step=step, size="sm")
        with ui.form_field(label="Font"):
            ui.select(options=[(stack, label) for label, stack in FONTS],
                      value=settings.font, size="sm")


def page() -> None:
    settings = Studio()
    with ui.vstack(gap="sm"):
        ui.heading("Theme studio", level=1, size="3xl")
        ui.text(
            "Everything here repaints in the browser, and follows you through "
            "the whole catalogue. When it looks right, copy the code at the "
            "bottom into core/theme.py.",
            size="lg", color="muted", classes="max-w-2xl",
        )

    with ui.grid(gap="lg", classes="lg:grid-cols-[22rem_minmax(0,1fr)] items-start"):
        with ui.card(padding="md", classes="lg:sticky lg:top-0"), ui.vstack(gap="lg"):
            identities_panel()
            ui.divider()
            colors_panel(settings)
            ui.divider()
            shapes_panel(settings)
            ui.divider()
            ui.button("Reset to the shipped theme", icon_left="rotate-ccw",
                      variant="ghost", size="sm", on_click=reset_expression())
        with ui.card(padding="lg"):
            sample_screen()

    with ui.vstack(gap="sm"):
        ui.heading("Your theme, as code", level=2, size="xl")
        ui.text("Paste it into core/theme.py and pass it to Bretzel(theme=…).",
                color="muted")
        ui.code(ClientExpression(export_expression()), lang="python")

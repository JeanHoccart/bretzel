"""``Stat`` test bench.

Cards, derived from the ClassVars (``playground-pattern.md`` § 8):

- **Reference** — one ``level=3`` per prop, each of its values: the value
  (number, text, none), ``unit``, ``max``, ``target`` (on a gauge, and
  without one), ``good`` (its closed table, up and down), ``delta``,
  ``description``.
- **Edge cases** — no value, past the range, below zero, the objective
  past the range or exactly met, a change of zero or with no way, the
  very long, the characters to escape, a component in a text slot.
- **Composability** — in grid cells narrower than it, side by side in a
  flex row, in a ``ui.pane`` of bounded height, inside a ``ui.card``,
  under ``tooltip=``.
- **A11y** — the ``role="meter"`` the page emits, read off the render.
- **Server playground** — every prop, escape hatch and modifier.

Omitted, and why:

- **Slots** — ``NAMED_SLOTS`` is empty: ``label`` / ``description`` are
  text slots that also take a component (shown in Edge cases).
- **Server events / Client events** — ``EVENTS`` is empty: a stat is
  read, not acted on.
- **Client playground** — ``BINDABLE_PROPS`` is empty: the value only
  moves when the server re-renders (``client-reactive-surface.md`` § La
  règle, step 3); no client driver exists in the apps.
- **External controls** — ``IMPERATIVE`` is empty.
- **Sizes / Colors** — neither axis exists: what the stat draws comes from
  what the app says the number means, not from a token.
"""

from __future__ import annotations

import re

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/stat"

#: The closed table of ``good=``.
GOODS = ["up", "down"]


class StatPlayground(PageState):
    label:       str = field(default="Copies typed")
    value:       str = field(default="19")
    unit:        str = field(default="")
    max:         str = field(default="24")
    target:      str = field(default="24")
    good:        str = field(default="up")
    delta:       str = field(default="3")
    description: str = field(default="Test of 12 November")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    extra_attrs: str = field(default="")
    style:       str = field(default="")
    # Universal modifiers.
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


def server_changed(state: StatPlayground) -> None:
    """The typed parameter receives the changed control's value."""


def number(typed: str) -> float | None:
    """A number typed in its field, or none."""
    try:
        return float(typed)
    except ValueError:
        return None


def parse_extra_attrs(blob: str) -> dict:
    """The ``extra_attrs`` textarea: one ``key=value`` per line."""
    result: dict = {}
    for raw in blob.splitlines():
        key, sep, value = raw.strip().partition("=")
        if sep and key.strip():
            result[key.strip()] = value.strip()
    return result


def build_preview(state: StatPlayground):
    """Map the playground state to ``ui.stat(...)`` kwargs."""
    kwargs: dict = {"good": state.good}
    value = number(state.value)
    # A text has no size: it takes neither a range nor an objective (the
    # stat would refuse them), so the two fields only apply to a number.
    if value is not None:
        for name in ("max", "target"):
            if number(getattr(state, name)) is not None:
                kwargs[name] = number(getattr(state, name))
    if state.unit:
        kwargs["unit"] = state.unit
    if state.delta:
        kwargs["delta"] = number(state.delta) if number(state.delta) is not None else state.delta
    if state.description:
        kwargs["description"] = state.description
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    attrs: dict = {}
    if state.aria_label:
        attrs["aria-label"] = state.aria_label
    attrs.update(parse_extra_attrs(state.extra_attrs))
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    if state.visible == "off":
        kwargs["visible"] = False
    shown = value if value is not None else (state.value or None)
    return ui.stat(state.label, shown, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = StatPlayground()
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("label"):
            ui.input(value=state.label, on_change=server_changed)
        with control("value (a number; a text; empty = None)"):
            ui.input(value=state.value, placeholder="19", on_change=server_changed)
        with control("unit"):
            ui.input(value=state.unit, placeholder="%", on_change=server_changed)
        with control("max (empty = no gauge; a number value only)"):
            ui.input(value=state.max, placeholder="24", on_change=server_changed)
        with control("target (empty = none; a number value only)"):
            ui.input(value=state.target, placeholder="24", on_change=server_changed)
        with control("good"):
            ui.select(value=state.good, on_change=server_changed,
                      options=[("up", "up (default)"), ("down", "down")])
        with control("delta (a number, or a text)"):
            ui.input(value=state.delta, placeholder="+12.4 %", on_change=server_changed)
        with control("description"):
            ui.input(value=state.description, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-stat",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Copies typed so far",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="opacity: 0.9",
                     on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="The test of 12 November",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible, on_change=server_changed,
                      options=[("on", "True (default)"), ("off", "False (skip render)")])
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=stat\ndata-kind=copies",
                        on_change=server_changed)
    ui.divider()
    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
        build_preview(state)
    ui.divider()
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


def meter_tag(markup: str) -> str:
    """The opening tag of a rendered stat's ``role="meter"``."""
    found = re.search(r'<div[^>]*role="meter"[^>]*>', markup)
    return found.group(0) if found else ""


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Stat", level=1)
        ui.text("A key figure. Nothing picks its shape: max= draws a gauge, "
                "target= the objective's mark — green reached, orange not —, "
                "good= says which way is better.", color="muted")

        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("One prop at a time, each of its values.", color="muted", size="sm")

            ui.heading("value — a number, a text, None", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("A number — the page writes it", 48240)
                ui.stat("A text — shown as written", "48 240,00 €")
                ui.stat("None — nothing yet", None)

            ui.heading("unit — none, a word, a percentage", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("No unit", 1284)
                ui.stat("A word", 4, unit="pupils")
                ui.stat("% — the language's shape", 71, unit="%")

            ui.heading("max — no range, a range", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("No max: a number alone", 12.4)
                ui.stat("max=20: a gauge, its scale", 12.4, max=20)

            ui.heading("target — on a gauge", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("No target: primary", 19, max=24)
                ui.stat("Reached: success", 22, max=24, target=20)
                ui.stat("Missed: warning", 19, max=24, target=24)

            ui.heading("target — without a range, said in a line", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("Reached", 52000, unit="€", target=50000)
                ui.stat("Missed", 48240, unit="€", target=50000)

            ui.heading("good — up, down", level=3)
            ui.text("The same value, objective and change; only good= differs.",
                    color="muted", size="xs")
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                for good in GOODS:
                    ui.stat(f'good="{good}"', 4, max=28, target=2, good=good, delta=-2)

            ui.heading("delta — a number, a text", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("A rise", 1284, delta=36)
                ui.stat("A fall", 1284, delta=-12)
                ui.stat("A text, its way by its sign", 48240, unit="€", delta="+12.4 %")

            ui.heading("description", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("Class average", 12.4, max=20, description="vs first term")
                ui.stat("Revenue", 48240, unit="€", description="vs August")

        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Inputs that break a key figure elsewhere.", color="muted", size="sm")

            ui.heading("No value yet, with a range", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("Class average", None, max=20)

            ui.heading("Past the range, below zero", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("23 out of 20 (a bonus)", 23, max=20, target=10)
                ui.stat("Below zero", -3, max=10)

            ui.heading("The objective past the range, exactly met", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("Target 12 out of 10", 8, max=10, target=12)
                ui.stat("Exactly on target", 60, unit="%", max=100, target=60)

            ui.heading("A change of zero, a change with no way", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("Zero", 12, delta=0)
                ui.stat("No sign", 12, delta="stable")

            ui.heading("Very long — label, value, description", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("A very long label that has to wrap on a narrow card",
                        1234567.89, unit="€", delta=1234.5,
                        description="And a description long enough to wrap too.")

            ui.heading("HTML-special characters (escaped)", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("<script>alert(1)</script>", "<b>12</b> & co",
                        delta="<i>+1</i>", description="</div> 1 < 2")

            ui.heading("A component in a text slot", level=3)
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat(ui.text("Average · test 2", weight="semibold", size="sm"), 12.4,
                        max=20, description=ui.link("See the copies", href="#copies"))

        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text("The stat in containers that would break it.",
                    color="muted", size="sm")

            ui.heading("In grid cells narrower than it", level=3)
            with ui.grid(cols=4, gap="sm", classes="max-w-md"):
                ui.stat("Average", 12.4, max=20, delta=0.8)
                ui.stat("Revenue", 48240, unit="€")
                ui.stat("Below 10", 4, unit="pupils", max=28, target=2, good="down")
                ui.stat("Churn", 2.1, unit="%", target=2, good="down")

            ui.heading("Side by side in a flex row", level=3)
            ui.text("An hstack centres its children: the shorter stat sits in the "
                    "middle. A grid row gives them one height (Reference above).",
                    color="muted", size="xs")
            with ui.hstack(gap="md"):
                ui.stat("Average", 12.4, max=20)
                ui.stat("Median", 12.5, max=20)
                ui.stat("To type", 5, description="Test of 12 November")

            ui.heading("In a ui.pane of bounded height — it scrolls", level=3)
            # The bounded height is set by the bench, never by the pane
            # (the recipe of /screen): the pane takes what is left.
            with (ui.card(padding="none", classes="h-56 max-w-sm flex flex-col"),
                  ui.pane(gap="sm", padding="sm")):
                ui.stat("Average", 12.4, max=20)
                ui.stat("Median", 12.5, max=20)
                ui.stat("Below 10", 4, unit="pupils", max=28, target=2, good="down")

            ui.heading("Inside ui.card", level=3)
            with ui.card(classes="max-w-md"), ui.vstack(gap="sm"):
                ui.heading("Test of 12 November", level=4)
                ui.stat("Copies typed", 19, max=24, target=24)

            ui.heading("Under tooltip=, in a grid row", level=3)
            ui.text("The tipped stat (the last) takes the row's height like its "
                    "neighbours — its wrapper is a one-cell grid.",
                    color="muted", size="xs")
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("Average", 12.4, max=20, description="vs first term")
                ui.stat("Median", 12.5, max=20)
                ui.stat("To type", 5, tooltip="Copies not typed yet")

        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text("The gauge is a role=\"meter\" — a measure in a known range, "
                    "not a task's progress. The tag below is read off this very "
                    "render: named by the label, its bounds, its value, and "
                    "aria-valuetext, the text the page shows. Without max= there "
                    "is no meter: the label and the number are read in order. A "
                    "stat takes no focus — there is nothing to act on.",
                    color="muted", size="sm")
            with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                ui.stat("Class average", 12.4, max=20, target=10)
            ui.code(meter_tag(serialize_html(
                ui.stat("Class average", 12.4, max=20, target=10))), lang="html")

        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text("Every prop wired to a control; the Emitted HTML follows.",
                    color="muted", size="sm")
            server_panel()

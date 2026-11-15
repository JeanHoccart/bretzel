"""``TagsInput`` test bench — the 10-card gabarit.

Props: ``value`` / ``options`` / ``render`` / ``pattern`` /
``placeholder`` / ``disabled`` / ``color`` / ``size`` / ``name``.
Events: ``change`` / ``focus`` / ``blur`` / ``search``.
``BINDABLE_PROPS = ("value", "disabled")``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression
from examples.playground.features.inspection import emitted_html_block
from examples.playground.features.tags_input.logic import (
    clear_log,
    log_blur,
    log_change,
    log_focus,
    log_search,
    matching_contacts,
    search_addresses,
    server_changed,
)
from examples.playground.features.tags_input.state import (
    COLORS,
    CONTACTS,
    EMAIL,
    SIZES,
    TAGS,
    AddressSearch,
    Recipients,
    TagsInputClient,
    TagsInputClientEvents,
    TagsInputEvents,
    TagsInputPlayground,
)

# ── Helpers ───────────────────────────────────────────────────────────


def contact_row(address: str, name: str) -> ui.hstack:
    """A suggestion: the person, then the address in grey. No ``size=`` on
    the texts: they follow the field's step."""
    with ui.hstack(gap="sm", align="center") as row:
        ui.avatar(name=name, size="xs", color="muted")
        with ui.vstack(gap="none"):
            ui.text(name)
            ui.text(address, color="muted")
    return row


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if line and "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def build_preview(state: TagsInputPlayground) -> dict:
    kwargs: dict = {
        "value": [v.strip() for v in state.initial.split(",") if v.strip()],
        "placeholder": state.placeholder,
        "disabled": state.disabled,
        "color": state.color,
        "size": state.size,
        "variant": state.variant,
    }
    if state.suggestions:
        kwargs["options"] = CONTACTS
        kwargs["render"] = contact_row
    if state.pattern:
        kwargs["pattern"] = EMAIL
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def recipient_line(label: str) -> ui.hstack:
    """One line of a mail's header: the label, then the field."""
    line = ui.hstack(gap="sm", align="center")
    with line:
        ui.text(label, color="muted", size="sm", classes="w-8 shrink-0")
    return line


# ── Refreshable panels ────────────────────────────────────────────────


@refreshable
def recipients_panel() -> None:
    """À and Cc of a mail. The suggestions come from a SERVER search."""
    query = AddressSearch().query
    found = matching_contacts(query) if query else CONTACTS
    recipients = Recipients()
    with ui.vstack(gap="sm"):
        with recipient_line("À"):
            ui.tags_input(found, value=recipients.to, render=contact_row,
                          pattern=EMAIL, placeholder="Ajouter quelqu'un",
                          on_search=search_addresses)
        with recipient_line("Cc"):
            ui.tags_input(found, value=recipients.cc, render=contact_row,
                          pattern=EMAIL, on_search=search_addresses)


@refreshable
def server_panel() -> None:
    state = TagsInputPlayground()
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("pattern (an e-mail address)"):
            ui.switch(checked=state.pattern, on_change=server_changed)
        with control("options + render (the address book)"):
            ui.switch(checked=state.suggestions, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color, options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size, options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("variant (surface / ghost)"):
            ui.select(value=state.variant,
                      options=[("surface", "surface"), ("ghost", "ghost")],
                      on_change=server_changed)
        with control("initial (comma-separated)"):
            ui.input(value=state.initial, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="max-w-md",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="recipients",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Destinataires",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=to", on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"), ("off", "False (skip render)")],
                      on_change=server_changed)
    ui.divider()
    kwargs = build_preview(state)
    ui.tags_input(**kwargs)
    ui.divider()
    emitted_html_block(
        "Emitted HTML — the controls grid drives this snapshot live",
        serialize_html(ui.tags_input(**kwargs)),
    )


@refreshable
def events_panel() -> None:
    state = TagsInputEvents()
    ui.text(
        "Four events, one instance each: ``on_change`` (a tag added or "
        "removed), ``on_focus`` / ``on_blur`` (the text field), "
        "``on_search`` (what is typed, after a 200 ms pause — the query "
        "rides a hidden input named ``query``).",
        color="muted", size="sm",
    )
    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
        ui.tags_input(TAGS, placeholder="change", on_change=log_change)
        ui.tags_input(TAGS, placeholder="focus", on_focus=log_focus)
        ui.tags_input(TAGS, placeholder="blur", on_blur=log_blur)
        ui.tags_input(TAGS, placeholder="search", on_search=log_search)
    ui.divider()
    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 12)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs", on_click=clear_log,
                  disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-12:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — type in the fields above)", color="muted", size="sm")
    ui.divider()
    emitted_html_block(
        "Emitted HTML — on_change relocated onto the hidden input",
        serialize_html(ui.tags_input(TAGS[:3], on_change=log_change)),
    )


# ── Page ──────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Tags input", level=1)
        ui.text(
            "Free values typed as tags inside the field — the recipients of "
            "a mail, the labels of a task. Enter, Tab, « ; » and « , » turn "
            "what is typed into a tag; a paste of several values makes "
            "several. Suggestions show while typing, never on a click. "
            "Backspace in the empty field selects the last tag, a second "
            "removes it; a double click puts a tag back into text.",
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)

            ui.heading("The recipients of a mail", level=3)
            ui.text(
                "Type « so », « mar » or « support » : the suggestions come "
                "from a server search (``on_search=``), each drawn by "
                "``render=``. Type an address that is not one — it becomes a "
                "red tag, the reason in its tooltip.",
                color="muted", size="sm",
            )
            recipients_panel()

            ui.heading("Free labels, a few suggestions", level=3)
            ui.tags_input(TAGS, value=["urgent"], placeholder="Ajouter une étiquette")

            ui.heading("pattern= — an invalid value stays, in red", level=3)
            ui.tags_input(value=["sophie.marchand@almadia.example", "pas-une-adresse"],
                          pattern=EMAIL)

            ui.heading("Variants — surface / ghost", level=3)
            ui.text("ghost: no background, no frame — as the lines of a mail. "
                    "The Tab key brings the ring.", color="muted", size="sm")
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                for v in ("surface", "ghost"):
                    ui.tags_input(TAGS, value=["urgent", "client"], variant=v)

            ui.heading("Sizes (xs → xl)", level=3)
            with ui.vstack(gap="sm"):
                for size in SIZES:
                    ui.tags_input(TAGS, value=["urgent", "client"], size=size,
                                  placeholder=f"size={size}")

            ui.heading("Colors (the focus ring)", level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="sm"):
                for color in COLORS:
                    ui.tags_input(TAGS, value=["urgent"], color=color,
                                  placeholder=f"color={color}")

            ui.heading("Disabled", level=3)
            ui.tags_input(TAGS, value=["urgent", "client"], disabled=True)

        # ── Card 2 — Edge cases ─────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.heading("No options — every value is typed", level=3)
            ui.tags_input(placeholder="Type, then Enter")
            ui.heading("A value no option knows — shown as itself", level=3)
            ui.tags_input(CONTACTS, value=["inconnu@ailleurs.example"])
            ui.heading("A long value, many tags — they wrap", level=3)
            ui.tags_input(value=[c[0] for c in CONTACTS], options=CONTACTS,
                          classes="max-w-md")

        # ── Card 3 — Composability ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.heading("Beside a button, on one row", level=3)
            with ui.hstack(gap="sm", align="center"):
                ui.tags_input(TAGS, placeholder="Étiquettes")
                ui.button("Enregistrer")
            ui.heading("In a form field (label)", level=3)
            with ui.form_field("Invités"):
                ui.tags_input(CONTACTS, render=contact_row, pattern=EMAIL, name="guests")

        # ── Card 4 — A11y ───────────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "The text field is a ``combobox`` over the ``listbox`` of "
                "suggestions (``aria-expanded`` follows them). The tags are a "
                "``list``; each cross is named « Remove <label> ». An "
                "``aria-live`` region says what was added or removed. The "
                "keyboard does everything: arrows in the suggestions, Enter "
                "to take one, Backspace twice to remove the last tag.",
                color="muted", size="sm",
            )
            ui.tags_input(CONTACTS, render=contact_row, pattern=EMAIL,
                          attrs={"aria-label": "Destinataires"})

        # ── Card 5 — Server playground ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            server_panel()

        # ── Card 6 — Server events ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        # ── Card 7 — Client playground ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text(
                "``BINDABLE_PROPS = ('value', 'disabled')``: the list and the "
                "lock follow the client store, no round trip.",
                color="muted", size="sm",
            )
            client = TagsInputClient(key="playground")
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (the same list, twice)"):
                    ui.tags_input(TAGS, value=client.picked)
                with control("disabled"):
                    ui.switch(checked=client.disabled)
            ui.divider()
            ui.tags_input(TAGS, value=client.picked, disabled=client.disabled)
            ui.divider()
            emitted_html_block(
                "Emitted HTML — value read and written in the store; "
                "disabled forwarded to the text field.",
                serialize_html(ui.tags_input(TAGS, value=client.picked,
                                             disabled=client.disabled)),
            )

        # ── Card 8 — External controls — the 3 modes ────────────────
        with ui.card(), ui.vstack():
            ui.heading("External controls — the 3 modes", level=2)
            ui.heading("Mode 1 — Imperative only", level=3)
            m1 = ui.tags_input(TAGS, placeholder="Imperative")
            with ui.hstack(wrap=True, gap="sm"):
                ui.button("Set [urgent, client]", on_click=m1.set(["urgent", "client"]))
                ui.button("Add « facture »", on_click=m1.add("facture"))
                ui.button("Add « a; b »", variant="outline", on_click=m1.add("a; b"))
                ui.button("Clear", variant="outline", on_click=m1.clear())
                ui.button("Focus", variant="ghost", on_click=m1.focus())
                ui.button("Blur", variant="ghost", on_click=m1.blur())
            ui.divider()
            ui.heading("Mode 2 — ClientBinding only", level=3)
            bound = TagsInputClient(key="binding_only")
            with ui.hstack(align="center", gap="sm"):
                ui.text("Value:", color="muted", size="sm")
                ui.text(ClientExpression(
                    "JSON.stringify($bz.state.TagsInputClient.binding_only.picked)"),
                    classes="font-mono", size="sm")
            ui.tags_input(TAGS, value=bound.picked)
            with ui.hstack(wrap=True, gap="sm"):
                ui.button("Force [interne]", on_click=bound.picked.set(["interne"]))
                ui.button("Empty", variant="ghost", on_click=bound.picked.set([]))
            ui.divider()
            ui.heading("Mode 3 — Both (write-through)", level=3)
            both = TagsInputClient(key="both")
            m3 = ui.tags_input(TAGS, value=both.picked)
            with ui.hstack(wrap=True, gap="sm"):
                ui.button("Add via tags.add()", on_click=m3.add("client"))
                ui.button("Set via tags.set()", on_click=m3.set(["facture"]))
                ui.button("Set via binding.set()", on_click=both.picked.set(["à relire"]))
            ui.divider()
            emitted_html_block(
                "Emitted HTML — Mode 2 (binding only)",
                serialize_html(ui.tags_input(TAGS[:3], value=bound.picked)),
            )

        # ── Card 9 — Client events ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            cevents = TagsInputClientEvents()
            typed = ClientExpression("$event.target.value")
            ui.tags_input(
                TAGS, placeholder="Type, add, remove",
                on_change=cevents.log.push(typed),
                on_focus=cevents.log.push("focus"),
                on_blur=cevents.log.push("blur"),
                on_search=cevents.log.push(typed),
            )
            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive — no refresh)", color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs", on_click=cevents.log.clear())
            ui.text(ClientExpression(
                '($bz.state.TagsInputClientEvents.default.log || []).join("\\n")'
                ' || "(no events yet)"'), color="muted", size="sm",
                classes="font-mono whitespace-pre")
            ui.divider()
            emitted_html_block(
                "Emitted HTML — the change handler on the hidden input",
                serialize_html(ui.tags_input(TAGS[:3],
                                             on_change=cevents.log.push(typed))),
            )

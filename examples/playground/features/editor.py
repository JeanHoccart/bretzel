"""``Editor`` test bench — and ``EditorTool``, its bar's child.

Ten cards : the full 7-section gabarit (S2 split into 4 visual cards).
``BINDABLE_PROPS = ("value",)`` — the Client playground mirrors the
Markdown live; ``IMPERATIVE = ("set", "clear", "insert", "focus",
"blur")`` — External controls. ``EVENTS = ("change",)`` — Server events
and Client events.

Props : ``value`` (Markdown, autoname-from) / ``placeholder`` /
``disabled`` / ``name`` / ``variant``. Children : ``ui.editor_tool`` in
its bar (``label`` / ``icon`` / ``disabled`` / ``on_click``), or an
overlay whose trigger is one.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block

PATH = "/editor"

VARIANTS = ["surface", "ghost"]

SAMPLE = (
    "Bonjour Jean,\\\n"
    "Voici le point de la semaine, en **trois choses** :\n"
    "\n"
    "- la *rentrée* est calée au 3 septembre ;\n"
    "- les devis sont partis :\n"
    "  - Dupont, **validé** ;\n"
    "  - Martin, en attente ;\n"
    "- le compte rendu est [sur le site](https://example.org/cr).\n"
    "\n"
    "1. relire la convention ;\n"
    "2. signer.\n"
    "\n"
    "Bonne journée,\\\n"
    "Claude"
)


class EditorPlayground(PageState):
    value:       str  = field(default=SAMPLE)
    placeholder: str  = field(default="Votre réponse")
    variant:     str  = field(default="surface")
    disabled:    bool = field(default=False)
    name:        str  = field(default="")
    tool:        bool = field(default=True)
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="server")


class EditorEvents(PageState):
    log: list = field(default_factory=list)


class EditorClient(ClientState, persist="memory"):
    """Mirror of Editor's BINDABLE_PROPS."""

    value: str = field(default="Écrit ici, **ou** dans le champ d'à côté.")


class EditorClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class EditorForm(PageState):
    reply: str = field(default="")
    sent: str = field(default="")


def log(line: str) -> None:
    state = EditorEvents()
    state.log = [*state.log, line]


def log_change(markdown: str = "") -> None:
    log(f"change({markdown[:60]!r})")


def log_tool() -> None:
    log("tool click")


def clear_log() -> None:
    EditorEvents().log = []


def server_changed(state: EditorPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value.
    pass


def playground_change(markdown: str = "") -> None:
    log(f"playground-server-change({markdown[:40]!r})")


def send_reply(form: EditorForm) -> None:
    form.sent = form.reply


CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: EditorPlayground):
    kwargs: dict = {
        "value": state.value,
        "placeholder": state.placeholder,
        "variant": state.variant,
        "disabled": state.disabled,
    }
    if state.name:
        kwargs["name"] = state.name
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
    if state.on_change_mode == "server":
        kwargs["on_change"] = playground_change
        kwargs["debounce"] = 800
    elif state.on_change_mode == "client":
        kwargs["on_change"] = CLIENT_CHANGE_EXPR
    elif state.on_change_mode == "both":
        kwargs["on_change"] = [playground_change, CLIENT_CHANGE_EXPR]
        kwargs["debounce"] = 800
    editor = ui.editor(**kwargs)
    with editor:
        if state.tool:
            ui.editor_tool("Demander à Claude", icon="sparkles", on_click=log_tool)
    return editor


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable
def server_panel() -> None:
    state = EditorPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (Markdown)"):
            ui.textarea(value=state.value, rows=4, on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("variant"):
            ui.select(value=state.variant, options=VARIANTS, on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="reply", on_change=server_changed)
        with control("tool (a ui.editor_tool in the bar)"):
            ui.switch(checked=state.tool, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="max-w-md", on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-editor", on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="The reply",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 30rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=2, placeholder="data-test=editor",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Your reply",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"), ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable (debounce=800)"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()
    with ui.vstack(classes="w-full max-w-2xl mx-auto"):
        build_preview(state)
    ui.divider()
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


@refreshable
def events_panel() -> None:
    state = EditorEvents()

    with ui.vstack(classes="w-full max-w-2xl"):
        ui.text("change — every edit publishes the Markdown ; debounce=600 waits for "
                "a pause before the POST.", color="muted", size="sm")
        ui.editor(on_change=log_change, debounce=600, placeholder="Type, then pause")
        ui.text("click — a tool of one's own.", color="muted", size="sm")
        with ui.editor(placeholder="The sparkles log a click"):
            ui.editor_tool("Log a click", icon="mouse-pointer-click", on_click=log_tool)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs", on_click=clear_log,
                  disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — type, or click the tool)", color="muted", size="sm")

    ui.divider()
    emitted_html_block(
        "Emitted HTML (representative — change relayed by the hidden carrier)",
        serialize_html(ui.editor(on_change=log_change, debounce=600)),
    )


@refreshable
def form_panel() -> None:
    form = EditorForm()
    with ui.form(on_submit=send_reply):
        with ui.vstack():
            ui.editor(value=form.reply, placeholder="La réponse part avec le formulaire")
            with ui.hstack():
                ui.button("Envoyer", type="submit", icon_left="send")
    if form.sent:
        ui.text("Received by the server :", color="muted", size="sm")
        ui.code(form.sent, lang="markdown")


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Editor", level=1)
            ui.text(
                "A text field that formats : bold, italic, lists, links. One sees "
                "formatted text, never its syntax ; the value is Markdown, bound "
                "both ways. Enter goes to the line, Enter on an empty line starts "
                "a paragraph ; Ctrl+B, Ctrl+I, Ctrl+K ; « - » or « 1. » starts a "
                "list ; a paste from Word or Outlook keeps the format and drops "
                "the rest.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop. No size nor colour : one "
                            "format, the theme's.", color="muted", size="sm")

                    ui.heading("Empty, with a placeholder", level=3)
                    ui.editor(placeholder="Votre réponse")

                    ui.heading("value= — Markdown, shown formatted", level=3)
                    ui.editor(value=SAMPLE)

                    ui.heading("variant=\"ghost\" — no background, no frame", level=3)
                    ui.text("The card around it is the frame ; the mouse puts the "
                            "caret in it, the keyboard brings the ring.",
                            color="muted", size="xs")
                    with ui.card():
                        ui.editor(variant="ghost", placeholder="Écrivez ici")

                    ui.heading("disabled=True", level=3)
                    ui.editor(value="Ce texte ne peut pas **changer**.", disabled=True)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text("No named slot : ui.editor_tool children go to the bar, "
                            "after the formatting commands.", color="muted", size="sm")

                    ui.heading("Tools — label, icon, disabled", level=3)
                    with ui.editor(placeholder="Two tools of one's own"):
                        ui.editor_tool("Demander à Claude", icon="sparkles", on_click=log_tool)
                        ui.editor_tool("Pas encore disponible", icon="calendar",
                                       disabled=True)

                    ui.heading("A menu of tools — a dropdown whose trigger is a tool",
                               level=3)
                    with ui.editor(placeholder="Many tools behind one button"):
                        with ui.dropdown(trigger=ui.editor_tool("Insérer", icon="plus")):
                            ui.dropdown_item("Un modèle", icon_left="file-text",
                                             on_click=log_tool)
                            ui.dropdown_item("Une signature", icon_left="pen-line",
                                             on_click=log_tool)

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Inputs that historically break.", color="muted", size="sm")

                    ui.heading("Syntax the editor does not show stays text", level=3)
                    ui.editor(value="## Un titre\n\n> une citation\n\n`du code` et ![une "
                                    "image](https://example.org/a.png)")

                    ui.heading("HTML and script links (XSS escape)", level=3)
                    ui.editor(value="<script>alert(1)</script> et "
                                    "[un lien piégé](javascript:alert(1))")

                    ui.heading("« - » or « 1. » after a line break starts a list", level=3)
                    ui.text("Put the caret at the end, press Enter, then type « - » and a "
                            "space: the line becomes the list's first item.",
                            color="muted", size="xs")
                    ui.editor(value="Deux points avant de commander :")

                    ui.heading("Lists nested three deep", level=3)
                    ui.editor(value="- un\n  - deux\n    - trois\n- quatre\n\n"
                                    "3. trois\n4. quatre")

                    ui.heading("A long text — the field grows with it", level=3)
                    ui.editor(value="\n\n".join(f"Paragraphe {n} d'un long message."
                                                for n in range(1, 9)))

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("In a form (the Markdown travels with the submit), in "
                            "a narrow cell, and ghost under the lines of a mail.",
                            color="muted", size="sm")

                    ui.heading("In a ui.form — submitted with it", level=3)
                    form_panel()

                    ui.heading("In a narrow grid cell — the bar wraps", level=3)
                    with ui.grid(cols=3, gap="md"):
                        with ui.editor(placeholder="Narrow"):
                            ui.editor_tool("Demander à Claude", icon="sparkles")
                        ui.text("A neighbour", color="muted", size="sm")
                        ui.text("Another", color="muted", size="sm")

                    ui.heading("Ghost, in a mail : the lines frame it", level=3)
                    with ui.card(padding="none"):
                        with ui.vstack(gap="none"):
                            with ui.hstack(classes="px-4 py-2"):
                                ui.text("Objet", color="muted", size="sm")
                                ui.text("Le point de la semaine", size="sm")
                            ui.divider()
                            ui.editor(variant="ghost", placeholder="Votre message")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "The bar is a role=toolbar ; every command is an icon "
                        "button with an accessible name and aria-pressed (the B "
                        "is pressed in bold). The text is a role=textbox, "
                        "aria-multiline, named by its placeholder. Tab goes from "
                        "the bar to the text ; in a list, Tab nests the item, "
                        "elsewhere it leaves the field.",
                        color="muted", size="sm",
                    )
                    ui.editor(placeholder="Tab here from the bar")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text("Every prop AND every escape hatch is wired to a "
                            "control ; the preview AND the emitted HTML refresh "
                            "on every change.", color="muted", size="sm")
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text("change (the Markdown) and a tool's click.",
                            color="muted", size="sm")
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of BINDABLE_PROPS = ('value',). The textarea and the "
                        "editor share one ClientState field : type in either, the "
                        "other follows — the textarea shows the Markdown itself.",
                        color="muted", size="sm",
                    )
                    client = EditorClient(key="playground")
                    with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                        with control("value — the Markdown"):
                            ui.textarea(value=client.value, rows=8,
                                        classes="font-mono")
                        with control("value — the editor"):
                            ui.editor(value=client.value)
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — the scope reads the bound path ; the hidden "
                        "carrier reports it.",
                        serialize_html(ui.editor(value=client.value)),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes", level=2)
                    ui.text("The same scenario — set, insert at the cursor, clear, "
                            "focus — three ways.", color="muted", size="sm")

                    ui.heading("Mode 1 — Imperative only (default)", level=3)
                    m1 = ui.editor(placeholder="Imperative — no ClientState")
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set", on_click=m1.set("Posé par **Mode 1**."))
                        ui.button("Insert", variant="outline",
                                  on_click=m1.insert("*inséré au curseur*"))
                        ui.button("Clear", variant="outline", on_click=m1.clear())
                        ui.button("Focus", variant="ghost", on_click=m1.focus())
                        ui.button("Blur", variant="ghost", on_click=m1.blur())

                    ui.divider()
                    ui.heading("Mode 2 — ClientBinding only", level=3)
                    bound = EditorClient(key="binding_only")
                    ui.editor(value=bound.value)
                    with ui.hstack(gap="sm"):
                        ui.button("Set via binding.set(...)",
                                  on_click=bound.value.set("Posé par **le lien**."))
                        ui.button("Clear via binding.set('')", variant="outline",
                                  on_click=bound.value.set(""))

                    ui.divider()
                    ui.heading("Mode 3 — Both (write-through)", level=3)
                    both = EditorClient(key="both")
                    with control("mirror (also bound — the Markdown)"):
                        ui.input(value=both.value)
                    m3 = ui.editor(value=both.value)
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set via editor.set(...)", on_click=m3.set("- un\n- deux"))
                        ui.button("Insert", variant="outline",
                                  on_click=m3.insert("**gras**"))
                        ui.button("Clear via editor.clear()", variant="outline",
                                  on_click=m3.clear())
                        ui.button("Focus", variant="ghost", on_click=m3.focus())

                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML — Mode 1 : bz-set and bz-insert caught at the root.",
                        serialize_html(ui.editor(placeholder="Imperative")),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text("change as a client expression, pushed onto a "
                            "ClientState list — zero network.", color="muted",
                            size="sm")
                    cevents = EditorClientEvents()
                    said = ClientExpression("'change: ' + $el.value.slice(0, 40)")
                    ui.editor(on_change=cevents.log.push(said),
                              placeholder="Each edit pushes a line")
                    ui.divider()
                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())
                    log_text = ClientExpression(
                        '($bz.state.EditorClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text, color="muted", size="sm",
                            classes="font-mono whitespace-pre")
                    ui.divider()
                    emitted_html_block(
                        "Emitted HTML (representative — change on the carrier)",
                        serialize_html(ui.editor(on_change=cevents.log.push(said))),
                    )

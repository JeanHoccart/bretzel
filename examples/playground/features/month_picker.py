"""``MonthPicker`` test bench.

Sept cartes. ``MonthPicker.BINDABLE_PROPS = ("value", "disabled")``.
``EVENTS = ("change", "focus", "blur")``. Enveloppe mince sur
``_picker_field`` + ``ui.calendar(mode="month")``.
"""

import datetime as dt

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/month_picker"

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]

TODAY = dt.date.today()
SEED = "2026-08"


class MonthPickerPlayground(PageState):
    value:       str  = field(default=SEED)
    placeholder: str  = field(default="YYYY-MM")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
    clearable:   bool = field(default=True)
    close_on_pick: bool = field(default=True)
    name:        str  = field(default="")
    minimum:     str  = field(default="")
    maximum:     str  = field(default="")
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")
    on_change_mode: str = field(default="none")


class MonthPickerEvents(PageState):
    log: list = field(default_factory=list)


class MonthPickerClient(ClientState, persist="memory"):
    picked: str = field(default=SEED)
    locked: bool = field(default=False)


class MonthPickerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class MonthPickerServerEvents(ClientState, persist="memory"):
    picked: str = field(default=SEED)


def log(name: str) -> None:
    state = MonthPickerEvents()
    state.log = [*state.log, name]


def log_change(picked: str = "") -> None:
    log(f"change(picked={picked!r})")


def log_focus(picked: str = "") -> None:
    log("focus()")


def log_blur(picked: str = "") -> None:
    log("blur()")


def clear_log() -> None:
    state = MonthPickerEvents()
    state.log = []


def server_changed(state: MonthPickerPlayground) -> None:
    # Typed param -> le dispatcher hydrate la valeur du controle change.
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(value={value!r})")


_CLIENT_CHANGE_EXPR = "$el.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: MonthPickerPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "placeholder": state.placeholder,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
        "clearable": state.clearable,
        "close_on_pick": state.close_on_pick,
    }
    if state.minimum:
        kwargs["min"] = state.minimum
    if state.maximum:
        kwargs["max"] = state.maximum
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
        kwargs["on_change"] = playground_change_handler
    elif state.on_change_mode == "client":
        kwargs["on_change"] = _CLIENT_CHANGE_EXPR
    elif state.on_change_mode == "both":
        kwargs["on_change"] = [playground_change_handler,
                               _CLIENT_CHANGE_EXPR]
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[MonthPickerPlayground])
def server_panel() -> None:
    state = MonthPickerPlayground()
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.input(value=state.value, placeholder=SEED,
                     on_change=server_changed)
        with control("min"):
            ui.input(value=state.minimum, placeholder="2026-03",
                     on_change=server_changed)
        with control("max"):
            ui.input(value=state.maximum, placeholder="2026-12",
                     on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color, options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size, options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("clearable"):
            ui.switch(checked=state.clearable, on_change=server_changed)
        with control("close_on_pick"):
            ui.switch(checked=state.close_on_pick, on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="periode",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-picker",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 220px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=picker",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None"), ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()
    kwargs = build_preview(state)
    with ui.flex(classes="max-w-xs"):
        ui.month_picker(**kwargs)
    ui.divider()
    emitted_html_block("Emitted HTML (MonthPicker)",
                       serialize_html(ui.month_picker(**kwargs)))


@refreshable(deps=[MonthPickerEvents])
def events_panel() -> None:
    state = MonthPickerEvents()
    ui.text(
        "Les trois events, sur TROIS instances : un element ne porte "
        "qu'UN hx-post, donc deux handlers serveur sur le meme picker "
        "levent au construct. change part de l'input cache ; focus et "
        "blur sont relocalises sur le champ editable, la racine etant un "
        "<div> non focusable dont ces deux events ne bullent pas.",
        color="muted", size="sm",
    )
    picked = MonthPickerServerEvents()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with control("on_change"):
            ui.month_picker(value=picked.picked, on_change=log_change)
        with control("on_focus"):
            ui.month_picker(SEED, on_focus=log_focus)
        with control("on_blur"):
            ui.month_picker(SEED, on_blur=log_blur)

    ui.divider()
    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)
    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}", color="muted", size="sm",
                        classes="font-mono")
    else:
        ui.text("(no events yet)", color="muted", size="sm")

    ui.divider()
    emitted_html_block(
        "Emitted HTML (MonthPicker with on_change)",
        serialize_html(ui.month_picker(value=picked.picked, on_change=log_change)),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Month picker", level=1)
        ui.text("Champ de MOIS : la valeur est une chaine 2026-08, zero-paddee donc triable comme lisible. Le panneau est un ui.calendar(mode=month) - une grille d annee, pas des jours.", color="muted")

        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.month_picker(SEED)
                ui.month_picker()
                ui.month_picker(SEED, clearable=False)

            ui.heading("min / max", level=3)
            ui.text("min / max sont tronques au mois : un min au 15 mars n interdit PAS mars, une partie du mois restant permise.", color="muted", size="xs")
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                ui.month_picker(SEED, min="2026-03", max="2026-12")
                ui.month_picker(SEED, max="2026-12")

            ui.heading("Sizes", level=3)
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                for s in SIZES:
                    with ui.vstack(gap="xs"):
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.month_picker(SEED, size=s)

            ui.heading("Colors", level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                for c in COLORS:
                    with ui.vstack(gap="xs"):
                        ui.text(c, color="muted", size="xs")
                        ui.month_picker(SEED, color=c)


            ui.heading("i18n + options", level=3)
            ui.text(
                "``month_names`` traduit la grille ; "
                "``close_on_pick=False`` garde le panneau ouvert "
                "pour comparer plusieurs mois ; ``name=`` est "
                "l'echappatoire quand la valeur est litterale et "
                "doit quand meme etre postee.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("month_names=FR", color="muted",
                            size="xs")
                    ui.month_picker(SEED, month_names=["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin",
          "Juillet", "Aout", "Septembre", "Octobre",
          "Novembre", "Decembre"])
                    with ui.vstack(gap="xs"):
                        ui.text("close_on_pick=False", color="muted",
                                size="xs")
                        ui.month_picker(SEED, close_on_pick=False)
                    with ui.vstack(gap="xs"):
                        ui.text('name="periode"', color="muted",
                                size="xs")
                        ui.month_picker(SEED, name="periode")

                ui.heading("disabled / required", level=3)
                with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                    ui.month_picker(SEED, disabled=True)
                    ui.month_picker(SEED, required=True)

        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Tapez 2026-08, 08/2026 ou 2026/08 puis sortez du champ : tout devient 2026-08. Ce qui n en est pas se vide.", color="muted", size="sm")
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("saisie libre", color="muted", size="xs")
                    ui.month_picker(placeholder="tapez 08/2026 puis Tab")
                with ui.vstack(gap="xs"):
                    ui.text("cellule etroite", color="muted",
                            size="xs")
                    ui.month_picker(SEED, size="sm")
                ui.text("Voisine.", color="muted")

        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label="Debut", hint="Periode de facturation"):
                    ui.month_picker(SEED)
                with ui.form_field(label="Fin"):
                    ui.month_picker(SEED)
            ui.heading("Dans un ui.dialog", level=3)
            with ui.dialog(title="Planifier", width="md") as dlg, \
                        ui.vstack():
                with ui.form_field(label="Quand ?"):
                    ui.month_picker(SEED)
                ui.text("Le panneau est ancre en position fixe, "
                        "donc il echappe a l'overflow du dialog.",
                        color="muted", size="xs")
            ui.button("Ouvrir le dialog", on_click=dlg.open())

        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text("Le champ reste un vrai input texte : tout se fait au clavier sans ouvrir le panneau. Les 12 cellules sont de vrais boutons, donc atteignables au Tab et reellement disabled hors bornes. Escape et le clic dehors referment.", color="muted", size="sm")
            with ui.flex(classes="max-w-xs"):
                ui.month_picker(SEED, aria_label="Mois de facturation")

        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            server_panel()

        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text("Mirror de BINDABLE_PROPS = ('value', "
                    "'disabled'). Tout adresse la meme cellule de "
                    "store, sans aller-retour.",
                    color="muted", size="sm")
            client = MonthPickerClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.month_picker(value=client.picked)
                with control("disabled (bound)"):
                    ui.switch(checked=client.locked,
                              label="Verrouiller")
            ui.divider()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("le meme, pilote par le switch"):
                    ui.month_picker(value=client.picked,
                               disabled=client.locked)
                with control("miroir"):
                    ui.text(
                        ClientExpression(
                            "'valeur : ' + "
                            "($bz.state.MonthPickerClient.default.picked "
                            "|| '(vide)')"
                        ),
                        color="muted", size="sm",
                        classes="font-mono",
                    )
            ui.divider()
            emitted_html_block(
                "Emitted HTML - la valeur liee est lue par le "
                "champ, l'input cache et le calendrier interne.",
                serialize_html(ui.month_picker(value=client.picked,
                                          disabled=client.locked)),
            )

        with ui.card(), ui.vstack():
            # ── External controls — the 3 modes ────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes", level=2)
                    ui.text(
                        "Les sept méthodes arrivées le 2026-09-03. Un picker "
                        "est DEUX natures à la fois : un panneau ancré (comme "
                        "`dialog`) et un champ qui porte une valeur (comme "
                        "`input`). Sa surface est donc l'union des deux "
                        "vocabulaires déjà fixés par ses voisins — rien "
                        "d'inventé.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Impératif seul ─────────────────────
                    ui.heading("Mode 1 — Imperative only (default for "
                               "one-off writes)", level=3)
                    ui.text(
                        "Aucun ClientState. `.open()` / `.close()` / "
                        "`.toggle()` dispatchent `bz-open` / `bz-close` / "
                        "`bz-toggle`, que la racine rattrape ; `.set()` "
                        "dispatche `bz-set`. `.focus()` vise le champ "
                        "VISIBLE — pas le porteur caché, qui est le premier "
                        "`<input>` du composant et ne prend pas le focus.",
                        color="muted", size="sm",
                    )
                    m1 = ui.month_picker()
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set 2026-09", on_click=m1.set("2026-09"))
                        ui.button("Clear", variant="ghost",
                                  on_click=m1.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m1.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m1.blur())

                    ui.divider()

                    # ── Mode 2 — ClientBinding seule ────────────────
                    ui.heading("Mode 2 — ClientBinding only (when another "
                               "component must read or react)", level=3)
                    ui.text(
                        "`value=binding` : la valeur vit dans le store, "
                        "donc un voisin la lit sans aller-retour.",
                        color="muted", size="sm",
                    )
                    lie = MonthPickerClient(key="ext_binding")
                    with ui.hstack(gap="md", align="center"):
                        ui.month_picker(value=lie.picked)
                        ui.text(
                            ClientExpression(
                                "'Valeur : ' + ($bz.state.MonthPickerClient"
                                ".ext_binding.picked || '(aucune)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

                    ui.divider()

                    # ── Mode 3 — Les deux ───────────────────────────
                    ui.heading("Mode 3 — Both (write-through)", level=3)
                    ui.text(
                        "Binding fournie ET méthodes appelées. `.set()` "
                        "détecte la binding et écrit DEDANS — le dispatch "
                        "DOM n'est pas utilisé, la source de vérité reste "
                        "unique. `.open()` reste un dispatch : le panneau "
                        "n'est pas une valeur.",
                        color="muted", size="sm",
                    )
                    deux = MonthPickerClient(key="ext_both")
                    m3 = ui.month_picker(value=deux.picked)
                    with ui.hstack(gap="sm", wrap=True, align="center"):
                        ui.button("Ouvrir", size="xs", on_click=m3.open())
                        ui.button("Set 2026-09", size="xs",
                                  on_click=m3.set("2026-09"))
                        ui.button("Clear", size="xs", variant="ghost",
                                  on_click=m3.clear())
                        ui.text(
                            ClientExpression(
                                "'Store : ' + ($bz.state.MonthPickerClient"
                                ".ext_both.picked || '(vide)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

            ui.heading("Client events", level=2)
            ui.text("change cable a une expression client. Zero "
                    "reseau.", color="muted", size="sm")
            cevents = MonthPickerClientEvents()
            _new = ClientExpression("$event.target.value")
            with ui.flex(classes="max-w-xs"):
                ui.month_picker(SEED, on_change=cevents.log.push(_new))
            ui.divider()
            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())
            ui.divider()
            ui.text(
                ClientExpression(
                    "($bz.state.MonthPickerClientEvents.default.log"
                    " || []).join(String.fromCharCode(10)) || '(no events yet)'"
                ),
                color="muted", size="sm",
                classes="font-mono whitespace-pre",
            )
            ui.divider()
            emitted_html_block(
                "Emitted HTML - le handler bz-on:change vit sur "
                "l'input cache, seul porteur avec name et value.",
                serialize_html(
                    ui.month_picker(SEED, on_change=cevents.log.push(_new))
                ),
            )

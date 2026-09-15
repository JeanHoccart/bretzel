"""``TimePicker`` test bench.

Nine cards. ``TimePicker.BINDABLE_PROPS = ("value", "disabled")`` — la
valeur et le verrou ; ``step`` / ``min`` / ``max`` / ``color`` / ``size``
restent design-time. ``EVENTS = ("change", "focus", "blur")``.
"""

import datetime as dt

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/time_picker"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]
STEPS  = [1, 5, 10, 15, 30, 60]


class TimePickerPlayground(PageState):
    value:       str  = field(default="09:30")
    step:        int  = field(default=15)
    min:         str  = field(default="")
    max:         str  = field(default="")
    placeholder: str  = field(default="HH:MM")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
    clearable:   bool = field(default=True)
    close_on_pick: bool = field(default=True)
    hour_label:  str  = field(default="H")
    minute_label: str = field(default="M")
    name:        str  = field(default="")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class TimePickerEvents(PageState):
    log: list = field(default_factory=list)


class TimePickerClient(ClientState, persist="memory"):
    picked: str = field(default="14:00")
    locked: bool = field(default=False)


class TimePickerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class TimePickerServerEvents(ClientState, persist="memory"):
    picked: str = field(default="08:00")


def log(name: str) -> None:
    state = TimePickerEvents()
    state.log = [*state.log, name]


def log_change(picked: str = "") -> None:
    log(f"change(picked={picked!r})")


def log_focus(picked: str = "") -> None:
    log("focus()")


def log_blur(picked: str = "") -> None:
    log("blur()")


def clear_log() -> None:
    state = TimePickerEvents()
    state.log = []


def server_changed(state: TimePickerPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted).
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


def build_preview(state: TimePickerPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "step": state.step,
        "placeholder": state.placeholder,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
        "clearable": state.clearable,
        "close_on_pick": state.close_on_pick,
        "hour_label": state.hour_label,
        "minute_label": state.minute_label,
    }
    # Chaîne vide = ne pas passer le kwarg.
    if state.min:
        kwargs["min"] = state.min
    if state.max:
        kwargs["max"] = state.max
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


@refreshable(deps=[TimePickerPlayground])
def server_panel() -> None:
    state = TimePickerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.input(value=state.value, placeholder="09:30",
                     on_change=server_changed)
        with control("step (minutes)"):
            ui.select(value=state.step,
                      options=[(s, str(s)) for s in STEPS],
                      on_change=server_changed)
        with control("min (vide = pas de plancher)"):
            ui.input(value=state.min, placeholder="09:00",
                     on_change=server_changed)
        with control("max (vide = pas de plafond)"):
            ui.input(value=state.max, placeholder="18:00",
                     on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("hour_label / minute_label"), ui.hstack(gap="xs"):
            ui.input(value=state.hour_label, on_change=server_changed)
            ui.input(value=state.minute_label, on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("clearable"):
            ui.switch(checked=state.clearable, on_change=server_changed)
        with control("close_on_pick"):
            ui.switch(checked=state.close_on_pick, on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="start_at",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-time",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Heure de début",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 200px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=time",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Quand ?",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_change mode"):
            ui.select(value=state.on_change_mode,
                      options=[("none", "None (no handler)"),
                               ("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(classes="max-w-xs"):
        ui.time_picker(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (TimePicker)",
        serialize_html(ui.time_picker(**kwargs)),
    )


@refreshable(deps=[TimePickerEvents])
def events_panel() -> None:
    state = TimePickerEvents()

    ui.text(
        "Les trois events sont câblés — mais sur TROIS instances, et "
        "c'est structurel : un élément ne porte qu'UN ``hx-post``, donc "
        "deux handlers serveur sur le même picker lèvent au construct "
        "(``HandlerError``). Pour en combiner plusieurs sur un seul "
        "champ, le second passe en expression client.",
        color="muted", size="sm",
    )
    ui.text(
        "Où ils partent : ``change`` depuis l'input caché (le porteur "
        "de form data) ; ``focus`` et ``blur`` sont relocalisés sur le "
        "champ éditable — la racine est un ``<div>`` non focusable, et "
        "ces deux events NE BULLENT PAS, donc un handler laissé là ne "
        "pourrait structurellement jamais partir.",
        color="muted", size="sm",
    )

    picked = TimePickerServerEvents()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with control("on_change"):
            ui.time_picker(value=picked.picked, on_change=log_change)
        with control("on_focus"):
            ui.time_picker(dt.time(10, 0), on_focus=log_focus)
        with control("on_blur"):
            ui.time_picker(dt.time(11, 0), on_blur=log_blur)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)", color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — cliquez le champ, puis une heure)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (TimePicker with on_change) — le bundle hx-* est "
        "relocalisé sur l'input caché par relocate_server_action, qui "
        "lit hx-trigger pour choisir le porteur : un on_focus= partirait "
        "sur le champ éditable, seul élément à recevoir focus.",
        serialize_html(
            ui.time_picker(value=picked.picked, on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Time picker", level=1)
        ui.text(
            "Champ d'heure : un champ éditable et un popover à deux "
            "colonnes aimantées. La valeur est une chaîne \"HH:MM\" "
            "— zéro-paddée, donc elle se trie comme elle se lit. "
            "Aucun calendrier n'est impliqué, et aucun widget natif "
            "non plus : un <input type=\"time\"> n'est pas "
            "thématisable et change d'allure selon le navigateur.",
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.time_picker(dt.time(9, 30))
                ui.time_picker()               # vide
                ui.time_picker(dt.time(23, 45))

            ui.heading("step", level=3)
            ui.text(
                "Combien de minutes existent. 15 par défaut — "
                "step=1 donne les soixante, et c'est là que la "
                "colonne défile vraiment.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                for s in (1, 5, 15):
                    with ui.vstack(gap="xs"):
                        ui.text(f"step={s}", color="muted", size="xs")
                        ui.time_picker(dt.time(10, 0), step=s)

            ui.heading("min / max", level=3)
            ui.text(
                "Les heures hors bornes sont grisées. Nuance : "
                "une HEURE n'est exclue que si aucune de ses "
                "minutes ne tient — sinon min=\"09:30\" griserait "
                "09 entière et 09:45 serait inatteignable.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("min=09:00 max=18:00",
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0),
                                   min="09:00", max="18:00")
                with ui.vstack(gap="xs"):
                    ui.text("min=09:30 (09:45 doit rester actif)",
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 45), min="09:30")
                with ui.vstack(gap="xs"):
                    ui.text("max=12:00", color="muted", size="xs")
                    ui.time_picker(dt.time(8, 0), max="12:00")

            ui.heading("Sizes", level=3)
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                for s in SIZES:
                    with ui.vstack(gap="xs"):
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.time_picker(dt.time(14, 15), size=s)

            ui.heading("Colors", level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                for c in COLORS:
                    with ui.vstack(gap="xs"):
                        ui.text(c, color="muted", size="xs")
                        ui.time_picker(dt.time(14, 15), color=c)

            ui.heading("disabled / required / clearable", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("disabled", color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0), disabled=True)
                with ui.vstack(gap="xs"):
                    ui.text("required", color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0), required=True)
                with ui.vstack(gap="xs"):
                    ui.text("clearable=False (pas de ×)",
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 0), clearable=False)

            ui.heading("close_on_pick", level=3)
            ui.text(
                "À True (défaut) le panneau se referme quand on "
                "clique une MINUTE, pas une heure — l'ordre de "
                "lecture est heure puis minute, refermer à "
                "l'heure couperait le geste en deux.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("close_on_pick=True", color="muted",
                            size="xs")
                    ui.time_picker(dt.time(9, 0))
                with ui.vstack(gap="xs"):
                    ui.text("close_on_pick=False", color="muted",
                            size="xs")
                    ui.time_picker(dt.time(9, 0),
                                   close_on_pick=False)

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                "Le composant n'a pas de slot au sens ``with`` : "
                "sa seule surface de contenu est textuelle — le "
                "placeholder du champ et les deux entêtes de "
                "colonne, pour l'i18n.",
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("défaut (H / M)", color="muted",
                            size="xs")
                    ui.time_picker(dt.time(9, 30))
                with ui.vstack(gap="xs"):
                    ui.text("i18n : placeholder + entêtes",
                            color="muted", size="xs")
                    ui.time_picker(dt.time(9, 30),
                                   placeholder="Heure…",
                                   hour_label="Heures",
                                   minute_label="Min")

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Saisie libre reparsée au blur", level=3)
            ui.text(
                "Tapez 9h30, 9:30, 9.30, 930 ou juste 9, puis "
                "sortez du champ — tout devient 09:30. Ce qui "
                "n'est pas une heure se vide.",
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(placeholder="tapez 930 puis Tab")

            ui.heading("Minuit et 23:59", level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                ui.time_picker(dt.time(0, 0))
                ui.time_picker(dt.time(23, 59), step=1)

            ui.heading("step=60 (une seule minute possible)",
                       level=3)
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(14, 0), step=60)

            ui.heading("min == max (un seul créneau)", level=3)
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(12, 0),
                               min="12:00", max="12:00")

            ui.heading("Valeur hors bornes", level=3)
            ui.text("La valeur reste affichée — on ne réécrit "
                    "jamais ce que le serveur a envoyé.",
                    color="muted", size="xs")
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(3, 0),
                               min="09:00", max="18:00")

            ui.heading("Dans une cellule étroite", level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                ui.time_picker(dt.time(9, 30))
                ui.text("Voisine.", color="muted")
                ui.text("Voisine.", color="muted")
                ui.text("Voisine.", color="muted")

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text("Le picker dans ses contextes habituels.",
                    color="muted", size="sm")

            ui.heading("Dans un form_field", level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.form_field(label="Heure de début",
                                   hint="Ouverture du créneau"):
                    ui.time_picker(dt.time(9, 0), min="08:00")
                with ui.form_field(label="Heure de fin"):
                    ui.time_picker(dt.time(18, 0), max="20:00")

            ui.heading("Un créneau, deux champs", level=3)
            ui.text(
                "Le cas d'usage le plus courant. Note : la "
                "contrainte croisée (fin.min = début) n'est PAS "
                "automatique — min/max ne sont pas bindables "
                "ici, contrairement à la famille date.",
                color="muted", size="xs",
            )
            with ui.hstack(gap="sm", align="center"):
                ui.time_picker(dt.time(9, 0), size="sm")
                ui.text("→", color="muted")
                ui.time_picker(dt.time(17, 30), size="sm")

            ui.heading("name= explicite (échappatoire)", level=3)
            ui.text(
                "L'autoname couvre le cas lié (``value=state.x`` "
                "dérive ``name=\"x\"``). Pour un picker à valeur "
                "littérale qui doit quand même poster, ``name=`` "
                "est le seul moyen d'avoir un porteur de "
                "formulaire sans binding.",
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(9, 0), name="start_at")

            ui.heading("Dans un ui.dialog", level=3)
            with ui.dialog(title="Planifier", width="md") as dlg, \
                            ui.vstack():
                with ui.form_field(label="À quelle heure ?"):
                    ui.time_picker(dt.time(14, 0))
                ui.text(
                    "Le panneau est ancré en position fixe, donc "
                    "il échappe à l'overflow du dialog.",
                    color="muted", size="xs",
                )
            ui.button("Ouvrir le dialog", on_click=dlg.open())

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "Le champ reste un vrai ``<input type=text>`` : "
                "on peut TOUT faire au clavier sans jamais "
                "ouvrir le panneau, ce qui est la voie la plus "
                "rapide pour qui connaît son heure. Les deux "
                "colonnes sont des ``role=listbox`` étiquetés, "
                "et chaque cellule un vrai ``<button>`` — donc "
                "atteignable au Tab et réellement ``disabled`` "
                "hors bornes, pas seulement grisée. Escape et le "
                "clic dehors referment.",
                color="muted", size="sm",
            )
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(dt.time(9, 30),
                               min="09:00", max="18:00",
                               aria_label="Heure du rendez-vous")

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every TimePicker prop AND every escape hatch is "
                "wired to a control ; the preview AND the "
                "emitted HTML both refresh on every change.",
                color="muted", size="sm",
            )
            server_panel()

        # ── Card 7 — Server events ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            events_panel()

        # ── Card 8 — Client playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client playground", level=2)
            ui.text(
                "Mirror of BINDABLE_PROPS = ('value', "
                "'disabled'). La valeur est liée à un "
                "ClientState : le champ, le panneau et le "
                "miroir ci-dessous lisent la MÊME cellule de "
                "store, sans aller-retour.",
                color="muted", size="sm",
            )
            client = TimePickerClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.time_picker(value=client.picked)
                with control("disabled (bound)"):
                    ui.switch(checked=client.locked,
                              label="Verrouiller")

            ui.divider()

            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("le même, piloté par le switch"):
                    ui.time_picker(value=client.picked,
                                   disabled=client.locked)
                with control("miroir"):
                    ui.text(
                        ClientExpression(
                            "'valeur : ' + "
                            "($bz.state.TimePickerClient"
                            ".default.picked || '(vide)')"
                        ),
                        color="muted", size="sm",
                        classes="font-mono",
                    )

            ui.divider()

            emitted_html_block(
                "Emitted HTML — tout adresse la cellule du store "
                "directement : le champ en bz-model, l'input "
                "caché en bz-attr:value, et les 28 cellules via "
                "les _read/_write du scope.",
                serialize_html(
                    ui.time_picker(value=client.picked,
                                   disabled=client.locked)
                ),
            )

        # ── Card 9 — Client events ──────────────────────────────
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
                    m1 = ui.time_picker()
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set 14:30", on_click=m1.set("14:30"))
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
                    lie = TimePickerClient(key="ext_binding")
                    with ui.hstack(gap="md", align="center"):
                        ui.time_picker(value=lie.picked)
                        ui.text(
                            ClientExpression(
                                "'Valeur : ' + ($bz.state.TimePickerClient"
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
                    deux = TimePickerClient(key="ext_both")
                    m3 = ui.time_picker(value=deux.picked)
                    with ui.hstack(gap="sm", wrap=True, align="center"):
                        ui.button("Ouvrir", size="xs", on_click=m3.open())
                        ui.button("Set 14:30", size="xs",
                                  on_click=m3.set("14:30"))
                        ui.button("Clear", size="xs", variant="ghost",
                                  on_click=m3.clear())
                        ui.text(
                            ClientExpression(
                                "'Store : ' + ($bz.state.TimePickerClient"
                                ".ext_both.picked || '(vide)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

            ui.heading("Client events", level=2)
            ui.text("change câblé à une expression client qui "
                    "empile la nouvelle heure dans un "
                    "ClientState. Zéro réseau.",
                    color="muted", size="sm")
            cevents = TimePickerClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.flex(classes="max-w-xs"):
                ui.time_picker(
                    dt.time(9, 0),
                    on_change=cevents.log.push(_new_value),
                )

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            ui.text(
                ClientExpression(
                    '($bz.state.TimePickerClientEvents.default.log'
                    ' || []).join("\\n") || "(no events yet)"'
                ),
                color="muted", size="sm",
                classes="font-mono whitespace-pre",
            )

            ui.divider()

            emitted_html_block(
                "Emitted HTML — le handler bz-on:change vit sur "
                "l'input caché, le seul porteur qui expose name "
                "et value.",
                serialize_html(
                    ui.time_picker(
                        dt.time(9, 0),
                        on_change=cevents.log.push(_new_value),
                    )
                ),
            )

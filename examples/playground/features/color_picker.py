"""``ColorPicker`` test bench.

Neuf cartes, le gabarit de `.claude/bretzel/playground-pattern.md`.
``ColorPicker.BINDABLE_PROPS = ("value", "disabled")`` — la couleur et le
verrou ; ``clearable`` / ``placeholder`` / ``color`` / ``size`` restent
design-time. ``EVENTS = ("change", "focus", "blur")``. Aucune API
impérative, donc pas de carte §7 — comme les trois pickers de date.

⚠️ Ce composant n'a **pas** de ``swatches=`` : sa grille vient de la
palette du thème. Le banc le montre plutôt que de le dire — c'est
``Theme(palette=…)`` qui décide, et donc la même grille partout.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/color_picker"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class ColorPickerPlayground(PageState):
    value:       str  = field(default="#2f5fd0")
    placeholder: str  = field(default="#rrggbb")
    color:       str  = field(default="primary")
    size:        str  = field(default="md")
    disabled:    bool = field(default=False)
    required:    bool = field(default=False)
    clearable:   bool = field(default=True)
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


class ColorPickerEvents(PageState):
    log: list = field(default_factory=list)


class ColorPickerClient(ClientState, persist="memory"):
    picked: str  = field(default="#8e4ec6")
    locked: bool = field(default=False)


class ColorPickerClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class ColorPickerServerEvents(ClientState, persist="memory"):
    picked: str = field(default="#30a46c")


def log(name: str) -> None:
    state = ColorPickerEvents()
    state.log = [*state.log, name]


def log_change(picked: str = "") -> None:
    log(f"change(picked={picked!r})")


def log_focus(picked: str = "") -> None:
    log("focus()")


def log_blur(picked: str = "") -> None:
    log("blur()")


def clear_log() -> None:
    state = ColorPickerEvents()
    state.log = []


def server_changed(state: ColorPickerPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted). ``server_panel`` declares
    # deps=[ColorPickerPlayground], so it re-renders on its own.
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


def build_preview(state: ColorPickerPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "placeholder": state.placeholder,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "required": state.required,
        "clearable": state.clearable,
    }
    # Chaîne vide = ne pas passer le kwarg, sinon le défaut du composant
    # n'est jamais celui qu'on teste.
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


@refreshable(deps=[ColorPickerPlayground])
def server_panel() -> None:
    state = ColorPickerPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value"):
            ui.input(value=state.value, placeholder="#2f5fd0",
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
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("clearable"):
            ui.switch(checked=state.clearable, on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="brand",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-xs",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-color",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Couleur de marque",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 200px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=color",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Quelle teinte ?",
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
        ui.color_picker(**kwargs)

    ui.divider()

    emitted_html_block(
        "Emitted HTML (ColorPicker)",
        serialize_html(ui.color_picker(**kwargs)),
    )


@refreshable(deps=[ColorPickerEvents])
def events_panel() -> None:
    state = ColorPickerEvents()

    ui.text(
        "Les trois events sont câblés — mais sur TROIS instances, et "
        "c'est structurel : un élément ne porte qu'UN ``hx-post``, donc "
        "deux handlers serveur sur le même picker lèvent au construct "
        "(``HandlerError``). Pour en combiner plusieurs sur un seul "
        "champ, le second passe en expression client.",
        color="muted", size="sm",
    )
    ui.text(
        "Où ils partent : ``change`` depuis l'input caché (le porteur de "
        "form data), donc il part aussi bien au clic sur une pastille "
        "qu'à la frappe ; ``focus`` et ``blur`` sont relocalisés sur le "
        "champ éditable — la racine est un ``<div>`` non focusable, et "
        "ces deux events NE BULLENT PAS, donc un handler laissé là ne "
        "pourrait structurellement jamais partir.",
        color="muted", size="sm",
    )

    picked = ColorPickerServerEvents()
    with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
        with control("on_change"):
            ui.color_picker(value=picked.picked, on_change=log_change)
        with control("on_focus"):
            ui.color_picker("#e5484d", on_focus=log_focus)
        with control("on_blur"):
            ui.color_picker("#f76b15", on_blur=log_blur)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — cliquez le champ, puis une pastille)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (ColorPicker with on_change) — le bundle hx-* est "
        "relocalisé sur l'input caché par relocate_server_action, qui "
        "lit hx-trigger pour choisir le porteur : un on_focus= partirait "
        "sur le champ éditable, seul élément à recevoir focus.",
        serialize_html(
            ui.color_picker(value=picked.picked, on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Color picker", level=1)
        ui.text(
            "Champ de couleur : une pastille qui rend la valeur, un "
            "hexadécimal éditable, et un panneau qui propose la palette "
            "du thème. La valeur est une chaîne \"#rrggbb\" — c'est ce "
            "qu'attend un Theme(semantic=…) et ce qu'une form data "
            "transporte tel quel. Aucun widget natif : un "
            "<input type=\"color\"> n'est pas thématisable, change "
            "d'allure selon le navigateur, et ne connaît pas la "
            "palette — qui est justement ce qu'on veut choisir neuf "
            "fois sur dix.",
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.color_picker("#2f5fd0")
                ui.color_picker()              # vide → le damier
                ui.color_picker("#ffe629")

            ui.heading("placeholder", level=3)
            ui.text(
                "Le seul texte du composant, et il sert deux fois : "
                "l'invite du champ vide ET son ``aria-label`` de repli. "
                "\"#rrggbb\" par défaut, parce qu'il dit la FORME "
                "attendue.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("défaut", color="muted", size="xs")
                    ui.color_picker()
                with ui.vstack(gap="xs"):
                    ui.text("placeholder=\"Choisir une teinte…\"",
                            color="muted", size="xs")
                    ui.color_picker(placeholder="Choisir une teinte…")

            ui.heading("Sizes", level=3)
            with ui.grid(cols={"base": 1, "md": 5}, gap="md"):
                for s in SIZES:
                    with ui.vstack(gap="xs"):
                        ui.text(f"size={s}", color="muted", size="xs")
                        ui.color_picker("#8e4ec6", size=s)

            ui.heading("Colors", level=3)
            ui.text(
                "``color=`` ne change PAS la couleur choisie — c'est "
                "l'accent du composant : l'anneau de focus, la bordure "
                "au survol, le liseré de la pastille sélectionnée. La "
                "valeur, elle, se voit dans la pastille.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                for c in COLORS:
                    with ui.vstack(gap="xs"):
                        ui.text(c, color="muted", size="xs")
                        ui.color_picker("#12a594", color=c)

            ui.heading("disabled / required / clearable", level=3)
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("disabled", color="muted", size="xs")
                    ui.color_picker("#0090ff", disabled=True)
                with ui.vstack(gap="xs"):
                    ui.text("required", color="muted", size="xs")
                    ui.color_picker("#0090ff", required=True)
                with ui.vstack(gap="xs"):
                    ui.text("clearable=True (le × si rempli)",
                            color="muted", size="xs")
                    ui.color_picker("#0090ff", clearable=True)

            ui.heading("name", level=3)
            ui.text(
                "Le nom du champ caché qui porte la couleur dans une "
                "form data. Lié à un state il se dérive tout seul ; "
                "``name=`` est l'échappatoire pour une valeur "
                "littérale.",
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#d6409f", name="brand")

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                "Le composant n'a pas de slot au sens ``with`` : il ne "
                "reçoit aucun enfant, et sa seule surface textuelle est "
                "le placeholder. Ce qui reste réglable, ce sont ses "
                "onze slots de THÈME — ``slots={…}`` les surcharge à "
                "l'instance, ``Theme(components={\"color_picker\": …})`` "
                "pour toute l'app.",
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("défaut", color="muted", size="xs")
                    ui.color_picker("#e93d82")
                with ui.vstack(gap="xs"):
                    ui.text("slots={'swatch': 'rounded-none w-10'}",
                            color="muted", size="xs")
                    ui.color_picker(
                        "#e93d82",
                        slots={"swatch": "rounded-none w-10"},
                    )

            ui.divider()

            ui.text(
                "Il n'y a PAS de ``swatches=``, et c'est délibéré : la "
                "grille est la palette du thème, donc tous les pickers "
                "d'une app proposent la même. Une charte se déclare une "
                "fois — ``Theme(palette={\"brand\": \"#…\"})`` — et le "
                "champ reste libre pour tout le reste : n'importe quel "
                "hexadécimal se tape à la main.",
                color="muted", size="sm",
            )

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Valeur vide", level=3)
            ui.text(
                "Le damier du thème transparaît. Une pastille BLANCHE "
                "et une pastille SANS couleur se confondraient — d'où "
                "le damier plutôt qu'un fond neutre.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                ui.color_picker()
                ui.color_picker("")

            ui.heading("Ce qui n'est pas un hexadécimal", level=3)
            ui.text(
                "Le champ ne le refuse pas, et c'est un choix : il est "
                "éditable, donc l'utilisateur tape forcément des états "
                "intermédiaires (\"#2f\"). La pastille reste vide tant "
                "que le navigateur ne sait pas lire la valeur.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                for raw in ("#2f", "rebeccapurple", "pas une couleur"):
                    with ui.vstack(gap="xs"):
                        ui.text(repr(raw), color="muted", size="xs")
                        ui.color_picker(raw)

            ui.heading("Casse et forme courte", level=3)
            ui.text(
                "La pastille sélectionnée se compare en minuscules des "
                "DEUX côtés, donc \"#8E4EC6\" coche bien la même "
                "cellule que \"#8e4ec6\". La forme à trois chiffres "
                "s'affiche, mais aucune cellule ne s'y reconnaît — le "
                "panneau ne normalise pas.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("\"#8E4EC6\" (majuscules)",
                            color="muted", size="xs")
                    ui.color_picker("#8E4EC6")
                with ui.vstack(gap="xs"):
                    ui.text("\"#abc\" (forme courte)",
                            color="muted", size="xs")
                    ui.color_picker("#abc")

            ui.heading("Blanc pur sur fond blanc", level=3)
            ui.text("La pastille garde sa bordure, sinon elle "
                    "disparaîtrait dans la surface.",
                    color="muted", size="xs")
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#ffffff")

            ui.heading("Dans une cellule étroite", level=3)
            with ui.grid(cols={"base": 1, "md": 4}, gap="md"):
                ui.color_picker("#2f5fd0")
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
                with ui.form_field(label="Couleur de marque",
                                   hint="Sert d'accent partout"):
                    ui.color_picker("#2f5fd0")
                with ui.form_field(label="Couleur d'alerte"):
                    ui.color_picker("#e5484d", clearable=True)

            ui.heading("Une paire clair / sombre", level=3)
            ui.text(
                "Le cas d'usage réel — c'est exactement ce que fait "
                "``/theme-studio`` pour ses vingt-deux jetons. Rien ne "
                "lie les deux champs : ce sont deux valeurs "
                "indépendantes, côte à côte.",
                color="muted", size="xs",
            )
            with ui.hstack(gap="sm", align="center"):
                ui.color_picker("#2f5fd0", size="sm")
                ui.text("→", color="muted")
                ui.color_picker("#7da3f0", size="sm")

            ui.heading("name= explicite (échappatoire)", level=3)
            ui.text(
                "L'autoname couvre le cas lié (``value=state.brand`` "
                "dérive ``name=\"brand\"``). Pour un picker à valeur "
                "littérale qui doit quand même poster, ``name=`` est le "
                "seul moyen d'avoir un porteur de formulaire sans "
                "binding.",
                color="muted", size="xs",
            )
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#30a46c", name="accent")

            ui.heading("Dans un ui.dialog", level=3)
            with ui.dialog(title="Personnaliser", width="md") as dlg, \
                            ui.vstack():
                with ui.form_field(label="Quelle teinte ?"):
                    ui.color_picker("#6e56cf")
                ui.text(
                    "Le panneau est ancré en position fixe, donc il "
                    "échappe à l'overflow du dialog.",
                    color="muted", size="xs",
                )
            ui.button("Ouvrir le dialog", on_click=dlg.open())

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "Le champ reste un vrai ``<input type=text>`` : on peut "
                "saisir un hexadécimal au clavier sans jamais ouvrir le "
                "panneau, ce qui est la voie la plus rapide pour qui "
                "connaît son code. Chaque pastille du panneau est un "
                "vrai ``<button>`` étiqueté par sa valeur — donc "
                "atteignable au Tab et annoncée « #8e4ec6 », pas "
                "« bouton ». Le déclencheur porte ``aria-expanded`` ; "
                "Escape et le clic dehors referment.",
                color="muted", size="sm",
            )
            ui.text(
                "Le nuancier ne peut pas être la SEULE façon de "
                "distinguer deux choix — c'est le sens du champ texte à "
                "côté : la valeur est toujours lisible en clair.",
                color="muted", size="sm",
            )
            with ui.flex(classes="max-w-xs"):
                ui.color_picker("#2f5fd0",
                                aria_label="Couleur de la marque")

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every ColorPicker prop AND every escape hatch is wired "
                "to a control ; the preview AND the emitted HTML both "
                "refresh on every change.",
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
                "Mirror of BINDABLE_PROPS = ('value', 'disabled'). La "
                "couleur est liée à un ClientState : le champ, la "
                "pastille, le panneau et le miroir ci-dessous lisent la "
                "MÊME cellule de store, sans aller-retour.",
                color="muted", size="sm",
            )
            client = ColorPickerClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.color_picker(value=client.picked)
                with control("disabled (bound)"):
                    ui.switch(checked=client.locked, label="Verrouiller")

            ui.divider()

            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("le même, piloté par le switch"):
                    ui.color_picker(value=client.picked,
                                    disabled=client.locked)
                with control("miroir"):
                    ui.text(
                        ClientExpression(
                            "'valeur : ' + "
                            "($bz.state.ColorPickerClient"
                            ".default.picked || '(vide)')"
                        ),
                        color="muted", size="sm",
                        classes="font-mono",
                    )

            ui.divider()

            emitted_html_block(
                "Emitted HTML — tout adresse la cellule du store "
                "directement : le champ en bz-model, l'input caché en "
                "bz-attr:value, la pastille de tête en bz-attr:style, "
                "et chaque cellule du panneau en bz-on:click qui ÉCRIT "
                "dans la même cellule.",
                serialize_html(
                    ui.color_picker(value=client.picked,
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
                    m1 = ui.color_picker()
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Ouvrir", on_click=m1.open())
                        ui.button("Fermer", variant="outline",
                                  on_click=m1.close())
                        ui.button("Basculer", variant="outline",
                                  on_click=m1.toggle())
                        ui.button("Set #27754a", on_click=m1.set("#27754a"))
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
                    lie = ColorPickerClient(key="ext_binding")
                    with ui.hstack(gap="md", align="center"):
                        ui.color_picker(value=lie.picked)
                        ui.text(
                            ClientExpression(
                                "'Valeur : ' + ($bz.state.ColorPickerClient"
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
                    deux = ColorPickerClient(key="ext_both")
                    m3 = ui.color_picker(value=deux.picked)
                    with ui.hstack(gap="sm", wrap=True, align="center"):
                        ui.button("Ouvrir", size="xs", on_click=m3.open())
                        ui.button("Set #27754a", size="xs",
                                  on_click=m3.set("#27754a"))
                        ui.button("Clear", size="xs", variant="ghost",
                                  on_click=m3.clear())
                        ui.text(
                            ClientExpression(
                                "'Store : ' + ($bz.state.ColorPickerClient"
                                ".ext_both.picked || '(vide)')"
                            ),
                            color="muted", size="sm", classes="font-mono",
                        )

            ui.heading("Client events", level=2)
            ui.text("change câblé à une expression client qui empile la "
                    "nouvelle couleur dans un ClientState. Zéro réseau.",
                    color="muted", size="sm")
            cevents = ColorPickerClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.flex(classes="max-w-xs"):
                ui.color_picker(
                    "#00a2c7",
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
                    '($bz.state.ColorPickerClientEvents.default.log'
                    ' || []).join("\\n") || "(no events yet)"'
                ),
                color="muted", size="sm",
                classes="font-mono whitespace-pre",
            )

            ui.divider()

            emitted_html_block(
                "Emitted HTML — le handler bz-on:change vit sur l'input "
                "caché, le seul porteur qui expose name et value.",
                serialize_html(
                    ui.color_picker(
                        "#00a2c7",
                        on_change=cevents.log.push(_new_value),
                    )
                ),
            )

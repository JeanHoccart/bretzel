"""``BottomBar`` / ``BottomBarItem`` test bench.

Nine cards : Reference / Slots / Edge cases / Composability / A11y /
Server playground / Server events / Client playground / Client events.
No §7 card — the family exposes no imperative API (nothing to open, set
or toggle : the active tab is derived from the URL).

⚠️ **Chaque barre de démo est enveloppée dans un ``ui.vstack()``**, et ce
n'est pas décoratif. Une bottom bar est TOUJOURS collée (il n'y a pas de
prop ``sticky=`` — cf. le composant), or un élément ``sticky`` ne peut pas
sortir de son bloc conteneur : lui donner un conteneur à sa propre hauteur
l'immobilise. Sans ça, chaque barre de cette page viendrait se coller au
bas de la fenêtre à tour de rôle pendant le scroll, en passant devant le
contenu (mesuré : une seule à la fois, mais ça suffit à brouiller un
banc). Le vrai comportement collant se regarde sur **la barre
tout en bas de cette page**, elle seule montée sans enveloppe — descends, et
elle reste au bord.

⚠️ Les items portent de vrais ``href`` de playground : un clic NAVIGUE
(partial-nav HTMX vers l'outlet du shell). C'est voulu — c'est le câblage
qu'on veut voir marcher. Les cartes d'événements, elles, utilisent des items
sans ``href`` pour que le handler parle sans quitter la page.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/bottom-bar"


COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]

# De vrais chemins du playground : l'item qui pointe sur CETTE page ressort
# actif tout seul (mode auto — comparaison à ``current_path``), ce qui est
# précisément ce qu'on veut regarder.
TABS = [
    ("Home",    "home",   "/"),
    ("Tabs",    "layers", "/tabs"),
    ("Bottom",  "panel-bottom", PATH),
    ("Badge",   "tag",    "/badge"),
]


class BottomBarPlayground(PageState):
    # Props de l'ITEM, appliquées à la tuile « Bottom » (celle qui pointe
    # vers cette page, donc active) pour qu'elle voisine des tuiles au
    # repos qui servent de témoins.
    item_color:   str = field(default="primary")
    item_badge:   str = field(default="")
    item_icon:    str = field(default="bell")
    item_disabled: bool = field(default=False)
    active_mode:  str = field(default="auto")
    # Escape hatches.
    classes:      str = field(default="")
    custom_id:    str = field(default="")
    aria_label:   str = field(default="")
    style:        str = field(default="")
    extra_attrs:  str = field(default="")
    # Universal modifiers.
    visible:      str = field(default="on")
    tooltip:      str = field(default="")


class BottomBarEvents(PageState):
    log: list = field(default_factory=list)


class BottomBarClient(ClientState, persist="memory"):
    active:   bool = field(default=False)
    badge:    int = field(default=0)
    disabled: bool = field(default=False)


class BottomBarClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


def log(name: str) -> None:
    state = BottomBarEvents()
    state.log = [*state.log, name]


def log_home() -> None:
    log("click(tab='Home')")


def log_search() -> None:
    log("click(tab='Search')")


def log_profile() -> None:
    log("click(tab='Profile')")


def clear_log() -> None:
    BottomBarEvents().log = []


def server_changed(state: BottomBarPlayground) -> None:
    # Param typé → le dispatcher hydrate la valeur du contrôle changé dans
    # ``state`` (coercée + persistée). Le panneau déclare
    # ``deps=[BottomBarPlayground]``, il se re-rend seul.
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: BottomBarPlayground):
    kwargs: dict = {}
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

    # Les props d'item pilotées par les contrôles atterrissent sur la tuile
    # qui pointe vers CETTE page — donc active par dérivation d'URL, ses
    # voisines au repos servant de témoins.
    #
    # ⚠️ Ce choix n'est pas cosmétique : `color` ne peint QUE la tuile active
    # (au repos, une tuile est `text-muted` — c'est l'idiome tab bar). En
    # posant les contrôles sur une tuile inactive, le sélecteur de couleur
    # avait l'air MORT alors que l'aller-retour serveur marchait.
    treated: dict = {
        "color": state.item_color,
        "disabled": state.item_disabled,
        "icon": state.item_icon or None,
    }
    if state.item_badge:
        treated["badge"] = state.item_badge
    if state.active_mode != "auto":
        treated["active"] = state.active_mode == "true"

    bar = ui.bottom_bar(**kwargs)
    with bar:
        for label, icon, href in TABS:
            if href == PATH:
                ui.bottom_bar_item(label, href=href, **treated)
            else:
                ui.bottom_bar_item(label, icon=icon, href=href)
    return bar


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[BottomBarPlayground])
def server_panel() -> None:
    state = BottomBarPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("item : color (tuile active)"):
            ui.select(value=state.item_color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("item : icon (tuile active)"):
            ui.input(value=state.item_icon,
                     placeholder="bell / heart / (vide = pas d'icône)",
                     on_change=server_changed)
        with control("item : badge (tuile active)"):
            ui.input(value=state.item_badge,
                     placeholder="3 / 99+ / (vide = pas de pastille)",
                     on_change=server_changed)
        with control("item : disabled (tuile active)"):
            ui.switch(checked=state.item_disabled, on_change=server_changed)
        with control("item : active — le mode de résolution"):
            ui.select(value=state.active_mode,
                      options=[("auto", "None — dérivé de l'URL"),
                               ("true", "True — forcé actif"),
                               ("false", "False — forcé inactif")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!bg-primary/5",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id,
                     placeholder="my-tab-bar",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Main navigation",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="border-top-width: 3px",
                     on_change=server_changed)
        with control("extra_attrs (une par ligne, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=tabbar",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Navigation",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[BottomBarEvents])
def events_panel() -> None:
    state = BottomBarEvents()

    ui.text(
        "``BottomBarItem`` déclare ``EVENTS = ('click',)``. Ici les tuiles "
        "n'ont PAS de ``href`` : le handler serveur parle sans que la page "
        "navigue. Les trois sont câblées.",
        color="muted", size="sm",
    )

    with ui.vstack():   # isole la barre — cf. l'en-tête
        with ui.bottom_bar():
            ui.bottom_bar_item("Home", icon="home", on_click=log_home)
            ui.bottom_bar_item("Search", icon="search", on_click=log_search)
            ui.bottom_bar_item("Profile", icon="user", on_click=log_profile)

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
        ui.text("(aucun événement — clique une tuile ci-dessus)",
                color="muted", size="sm")

    ui.divider()

    with ui.vstack():
        representative = ui.bottom_bar()
    with representative:
        ui.bottom_bar_item("Home", icon="home", on_click=log_home)
    emitted_html_block(
        "Emitted HTML (BottomBarItem avec un handler serveur)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("BottomBar", level=1)
            ui.text(
                "Tab bar bas d'écran — le pendant mobile de ``ui.navbar``. "
                "Deux pièces : ``ui.bottom_bar`` (le ``<nav>`` collé au "
                "bord) et ``ui.bottom_bar_item`` (un onglet : icône "
                "au-dessus, label dessous, largeur égale). Le composant se "
                "monte dans un ``if Screen().is_mobile:`` — le framework "
                "n'impose aucune nav mobile, c'est le dev qui choisit.",
                color="muted",
            )
            ui.text(
                "Deux choses à savoir pour lire cette page : une bottom bar "
                "est toujours collée au bord (aucune prop pour ça), donc "
                "chaque démo est enveloppée dans un conteneur à sa taille "
                "qui l'immobilise — la seule barre libre de le montrer est "
                "tout en bas de la page. Et leurs items portent de vrais "
                "href de playground, donc un clic navigue pour de bon.",
                color="muted", size="sm",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic — 4 onglets", level=3)
                    ui.text(
                        "L'onglet actif est dérivé de l'URL : « Bottom » "
                        "pointe sur cette page, il ressort tout seul.",
                        color="muted", size="xs",
                    )
                    with ui.vstack():
                        with ui.bottom_bar():
                            for label, icon, href in TABS:
                                ui.bottom_bar_item(label, icon=icon, href=href)

                    ui.heading("Pas de variant — et c'est délibéré",
                               level=3)
                    ui.text(
                        "Une pilule arrondie détachée des bords a existé ici "
                        "en `variant=\"floating\"`, puis a été coupée : une "
                        "app n'a qu'UNE tab bar et ne choisit son look "
                        "qu'une fois, donc c'est une décision de thème, pas "
                        "un prop. `ui.bottom_bar(variant=…)` lève désormais, "
                        "au lieu d'être absorbé en silence comme attribut "
                        "HTML. Le look flottant s'obtient par override du "
                        "slot `root` — voir le contrôle `classes` du Server "
                        "playground pour l'essayer tout de suite.",
                        color="muted", size="xs",
                    )

                    ui.heading("item : color", level=3)
                    ui.text(
                        "L'actif se signale par la COULEUR de l'icône et du "
                        "label — pas par un fond plein comme la pilule d'une "
                        "navbar.",
                        color="muted", size="xs",
                    )
                    for c in COLORS:
                        with ui.vstack():
                            with ui.bottom_bar():
                                ui.bottom_bar_item("Active", icon="check",
                                                   color=c, active=True)
                                ui.bottom_bar_item("Idle", icon="circle",
                                                   color=c)
                                ui.bottom_bar_item("Idle", icon="circle",
                                                   color=c)

                    ui.heading("item : badge", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Inbox", icon="inbox", badge=3)
                            ui.bottom_bar_item("Alerts", icon="bell", badge="99+")
                            ui.bottom_bar_item("Chat", icon="message-circle")

                    ui.heading("item : disabled", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home", href="/")
                            ui.bottom_bar_item("Soon", icon="lock",
                                               disabled=True)
                            ui.bottom_bar_item("Profile", icon="user")

                    ui.heading("item : active — explicite vs dérivé",
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("active=True", icon="check",
                                               active=True)
                            ui.bottom_bar_item("active=False", icon="x",
                                               active=False, href="/")
                            ui.bottom_bar_item("auto (URL)", icon="compass",
                                               href=PATH)

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``icon`` accepte un raccourci string ou un "
                        "Component. Le raccourci est ré-emballé en "
                        "``ui.icon(size=\"lg\")`` — 24px, la taille d'une "
                        "cible tactile ; un Icon construit par l'appelant "
                        "garde SA taille et SA couleur.",
                        color="muted", size="sm",
                    )

                    ui.heading("icon=str (raccourci)", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home")
                            ui.bottom_bar_item("Search", icon="search")

                    ui.heading("icon=Component", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item(
                                "Small", icon=ui.icon("home", size="xs"))
                            ui.bottom_bar_item(
                                "Huge", icon=ui.icon("search", size="xl"))
                            ui.bottom_bar_item(
                                "Tinted",
                                icon=ui.icon("heart", color="error"))

                    ui.heading("badge=Component", level=3)
                    ui.text(
                        "Un scalaire est emballé dans un ``ui.badge`` "
                        "``error`` / ``xs`` ; un Component le remplace en "
                        "gardant l'ancrage. ⚠️ Cette phrase annonçait déjà "
                        "la pastille rouge avant le 2026-08-16, alors que "
                        "les trois familles de nav rendaient un scalaire en "
                        "TEXTE NU : elle était vraie de la doc, fausse du "
                        "code. C'est le code qui l'a rejointe.",
                        color="muted", size="xs",
                    )
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Scalar", icon="bell", badge=7)
                            ui.bottom_bar_item(
                                "Component", icon="bell",
                                badge=ui.badge("new", color="success",
                                               size="xs"))

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Entrées limites.", color="muted", size="sm")

                    ui.heading("2 onglets", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Left", icon="arrow-left")
                            ui.bottom_bar_item("Right", icon="arrow-right")

                    ui.heading("6 onglets (au-delà de la reco iOS)",
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            for n in range(1, 7):
                                ui.bottom_bar_item(f"Tab {n}", icon="circle")

                    ui.heading("Labels très longs (truncate)", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Notifications et alertes",
                                               icon="bell")
                            ui.bottom_bar_item("Paramètres du compte",
                                               icon="settings")
                            ui.bottom_bar_item("Aide", icon="help-circle")

                    ui.heading("Icône seule (pas de label)", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item(icon="home")
                            ui.bottom_bar_item(icon="search")
                            ui.bottom_bar_item(icon="user")

                    ui.heading("Label seul (pas d'icône)", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home")
                            ui.bottom_bar_item("Search")
                            ui.bottom_bar_item("Profile")

                    ui.heading("Emoji + multi-écritures", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("🏠 Home", icon="home")
                            ui.bottom_bar_item("שלום", icon="globe")
                            ui.bottom_bar_item("中文", icon="languages")

                    ui.heading("Label HTML-spécial (échappement)", level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("<script>alert(1)</script>",
                                               icon="bug")
                            ui.bottom_bar_item("Safe", icon="shield")

                    ui.heading("Barre vide", level=3)
                    with ui.vstack():
                        ui.bottom_bar()

                    ui.heading("href externe (nouvel onglet, pas de htmx)",
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("GitHub", icon="github",
                                               href="https://github.com")
                            ui.bottom_bar_item("Home", icon="home", href="/")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("La barre dans ses contextes réels.",
                            color="muted", size="sm")

                    ui.heading("La forme d'un shell mobile", level=3)
                    ui.text(
                        "Le contenu, puis la barre — c'est exactement ce "
                        "qu'un ``if Screen().is_mobile:`` produit dans un "
                        "layout.",
                        color="muted", size="xs",
                    )
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Ma page", level=3)
                            ui.text("Le corps de l'app vit ici.",
                                    color="muted")
                            with ui.vstack():
                                with ui.bottom_bar():
                                    for label, icon, href in TABS:
                                        ui.bottom_bar_item(label, icon=icon,
                                                           href=href)

                    ui.heading("Navbar + BottomBar sur la même page",
                               level=3)
                    ui.text(
                        "Les deux possèdent leur propre scope "
                        "``current_path`` — la duplication est voulue, "
                        "chacune doit marcher sans l'autre. Elles restent "
                        "d'accord sur l'item actif.",
                        color="muted", size="xs",
                    )
                    with ui.navbar():
                        with ui.navbar_section(side="left"):
                            ui.heading("Acme", level=3)
                        with ui.navbar_section(side="right"):
                            ui.navbar_item("Tabs", href="/tabs")
                            ui.navbar_item("Bottom", href=PATH)
                    with ui.vstack():
                        with ui.bottom_bar():
                            for label, icon, href in TABS:
                                ui.bottom_bar_item(label, icon=icon, href=href)

                    ui.heading("Onglet avec un badge vivant + une action",
                               level=3)
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home", href="/")
                            ui.bottom_bar_item("Alerts", icon="bell",
                                               badge=12, color="error")
                            ui.bottom_bar_item("Profile", icon="user",
                                               href="/badge")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "La racine est un ``<nav>`` — un vrai repère de "
                        "navigation. Aucun ``aria-label`` n'est imposé "
                        "(mettre un libellé anglais en dur serait une "
                        "erreur d'i18n) : passe-le via le contrôle "
                        "``aria-label`` du Server playground, surtout si "
                        "la page porte déjà une navbar (deux repères "
                        "``nav`` sans nom, c'est illisible au lecteur "
                        "d'écran).",
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        with ui.bottom_bar(
                                aria_label="Navigation principale"):
                            for label, icon, href in TABS:
                                ui.bottom_bar_item(label, icon=icon, href=href)

                    ui.heading("aria-current sur l'onglet courant", level=3)
                    ui.text(
                        "L'onglet dérivé de l'URL émet "
                        "``aria-current=\"page\"`` de façon réactive — le "
                        "lecteur d'écran annonce où on est.",
                        color="muted", size="sm",
                    )

                    ui.heading("Ordre de tabulation", level=3)
                    ui.text(
                        "Les onglets à ``href`` sont des ``<a>`` natifs : "
                        "Tab les traverse dans l'ordre, Entrée active. Un "
                        "onglet ``disabled`` porte ``tabindex=-1`` ET perd "
                        "tous ses canaux de clic — il est sauté.",
                        color="muted", size="sm",
                    )
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("First", icon="home", href="/")
                            ui.bottom_bar_item("Skipped", icon="lock",
                                               href="/tabs", disabled=True)
                            ui.bottom_bar_item("Third", icon="user",
                                               href="/badge")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Chaque prop ET chaque escape hatch est câblé à un "
                        "contrôle ; l'aperçu ET le HTML émis se rafraîchis"
                        "sent à chaque changement. Les props d'ITEM "
                        "atterrissent sur la tuile « Bottom » — celle qui "
                        "pointe vers cette page, donc active — ses voisines "
                        "au repos servant de témoins.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "À savoir pour lire le contrôle `color` : sur une tab "
                        "bar, la couleur ne peint QUE l'onglet ACTIF — au "
                        "repos un onglet est volontairement `muted`, c'est "
                        "l'idiome iOS/Android. Passe `active` à `False` et la "
                        "couleur disparaît : c'est le comportement, pas une "
                        "panne. Au repos, `color` ne pilote plus que le halo "
                        "de focus.",
                        color="muted", size="xs",
                    )
                    server_panel()

            # ── Card 7 — Server events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Miroir du contrat ``BottomBarItem."
                        "BINDABLE_PROPS = ('active', 'badge', 'disabled')``."
                        " Les trois sont liées à un ClientState et pilotées "
                        "par des contrôles externes — zéro aller-retour. "
                        "``BottomBar`` lui-même n'a AUCUNE prop bindable : "
                        "la barre elle-même n'a AUCUNE prop.",
                        color="muted", size="sm",
                    )
                    client = BottomBarClient()
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                        with control("active (bound)"):
                            ui.switch(checked=client.active)
                        with control("badge (bound)"):
                            ui.number_input(value=client.badge,
                                            min=0, max=99)
                        with control("disabled (bound)"):
                            ui.switch(checked=client.disabled)

                    ui.divider()

                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item("Home", icon="home")
                            ui.bottom_bar_item("Alerts", icon="bell",
                                               active=client.active,
                                               badge=client.badge,
                                               disabled=client.disabled)
                            ui.bottom_bar_item("Profile", icon="user")

                    ui.divider()

                    with ui.vstack():
                        preview = ui.bottom_bar()
                    with preview:
                        ui.bottom_bar_item("Alerts", icon="bell",
                                           active=client.active,
                                           badge=client.badge,
                                           disabled=client.disabled)
                    emitted_html_block(
                        "Emitted HTML — ``bz-attr:data-active`` + "
                        "``bz-class`` pour l'actif, ``bz-text`` + "
                        "``bz-show`` pour le compteur (une pastille à 0 se "
                        "replie), ``bz-attr:aria-disabled`` + "
                        "``bz-attr:tabindex`` pour le verrou.",
                        serialize_html(preview),
                    )

            # ── Card 9 — Client events ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``click`` câblé à une expression client qui pousse "
                        "le nom de l'onglet sur une liste ClientState. Zéro "
                        "réseau.",
                        color="muted", size="sm",
                    )
                    cevents = BottomBarClientEvents()
                    with ui.vstack():
                        with ui.bottom_bar():
                            ui.bottom_bar_item(
                                "Home", icon="home",
                                on_click=cevents.log.push("Home"))
                            ui.bottom_bar_item(
                                "Search", icon="search",
                                on_click=cevents.log.push("Search"))
                            ui.bottom_bar_item(
                                "Profile", icon="user",
                                on_click=cevents.log.push("Profile"))

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.BottomBarClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    with ui.vstack():
                        preview = ui.bottom_bar()
                    with preview:
                        ui.bottom_bar_item(
                            "Home", icon="home",
                            on_click=cevents.log.push("Home"))
                    emitted_html_block(
                        "Emitted HTML — ``bz-on:click`` porte l'expression "
                        "client telle quelle, aucun ``hx-post``.",
                        serialize_html(preview),
                    )

        # ── La vraie barre, collante — hors des cards ────────────────
        # La seule barre SANS enveloppe de la page — donc la seule libre de
        # se coller. Son bloc conteneur est le container de la page, bien
        # plus haut qu'elle : elle reste au bas du viewport pendant tout le
        # scroll, puis se pose à sa place en fin de document.
        with ui.bottom_bar():
            for label, icon, href in TABS:
                ui.bottom_bar_item(label, icon=icon, href=href)

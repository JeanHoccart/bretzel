"""Le rendu du banc ``Sidebar`` — les dix cartes.

Dix cartes : Reference / Slots / Edge cases / Composability / A11y /
Server playground / Server events / Client playground / External
controls / Client events.

⚠️ **Chaque sidebar de démo est montée dans un cadre à hauteur fixe, et
porte ``slots=FIT``.** Ce n'est pas décoratif. Le slot ``root`` du thème
est ``h-screen`` (100vh) : posée telle quelle dans une carte, la sidebar
mesure la hauteur du viewport et son footer ``mt-auto`` part hors du
cadre (mesuré : 720px de sidebar dans une boîte de 380px, footer à
y=649, invisible). ``h-screen`` est aussi la raison pour laquelle le
harnais visuel devait monter la sidebar « bare », sans conteneur — le
contournement a disparu avec la suite visual le 2026-08-16, la
contrainte non.

Et l'override doit être ``h-full!`` avec le ``!`` de Tailwind v4, pas
``h-full`` : les deux utilitaires ont la MÊME spécificité, donc le
vainqueur est le dernier de la feuille compilée, pas le dernier de
l'attribut ``class``. Mesuré : ``h-full`` nu perd (720px), ``h-full!``
gagne (378px dans une boîte de 380px, footer visible).

Le jour où ``h-screen`` quitte le thème — la sidebar ne se monte
aujourd'hui QUE dans un parent ``fixed inset-0`` + ``align="stretch"``,
où la hauteur vient déjà du flex, donc l'utilitaire n'y sert à rien —
``FIT`` disparaît d'ici en une ligne.

⚠️ Les items portent de vrais ``href`` de playground : un clic NAVIGUE
(partial-nav HTMX vers l'outlet du shell). C'est voulu, c'est le câblage
qu'on veut voir marcher. Les cartes d'événements utilisent des items
sans ``href`` pour que le handler parle sans quitter la page.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.inspection import emitted_html_block
from examples.playground.features.sidebar.logic import (
    clear_log,
    log_home,
    log_issues,
    log_logout,
    log_settings,
    parse_extra_attrs,
    server_changed,
)
from examples.playground.features.sidebar.state import (
    COLORS,
    FIT,
    MODES,
    NAV,
    PATH,
    WIDTHS,
    SidebarClient,
    SidebarClientEvents,
    SidebarEvents,
    SidebarPlayground,
)

def frame(height: str = "h-[400px]"):
    """Le cadre à hauteur fixe dans lequel vit une sidebar de démo.

    ``align="stretch"`` reproduit exactement ce que font les six shells
    d'``examples/`` (tous en ``fixed inset-0`` + stretch) : c'est le flex
    qui donne sa hauteur à l'aside, pas l'utilitaire du thème."""
    return ui.hstack(
        gap="none", align="stretch",
        classes=(
            f"{height} w-full overflow-hidden "
            "rounded-lg border border-text/10"
        ),
    )


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block

def build_preview(state: SidebarPlayground):
    kwargs: dict = {
        "width": state.width,
        "collapsible": state.collapsible,
        "open": state.open,
        "slots": FIT,
    }
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

    # Les props d'item pilotées par les contrôles atterrissent sur
    # l'entrée qui pointe vers CETTE page — donc active par dérivation
    # d'URL, ses voisines au repos servant de témoins. Même raison que
    # sur le banc bottom_bar : `color` ne peint QUE la ligne active, un
    # sélecteur posé sur une ligne inactive aurait l'air mort.
    treated: dict = {
        "color": state.item_color,
        "disabled": state.item_disabled,
        "icon": state.item_icon or None,
    }
    if state.item_badge:
        treated["badge"] = state.item_badge
    if state.active_mode != "auto":
        treated["active"] = state.active_mode == "true"

    box = ui.sidebar(**kwargs)
    with box:
        ui.sidebar_title("Playground", icon="zap")
        with ui.sidebar_section(label="OVERVIEW"):
            for label, icon, href in NAV:
                if href == PATH:
                    ui.sidebar_item(label, href=href, **treated)
                else:
                    ui.sidebar_item(label, icon=icon, href=href)
        with ui.sidebar_footer(name="Jean Hoccart",
                               subtitle="jean@acme.com"):
            ui.sidebar_footer_item(label="Settings", icon_left="settings")
            ui.sidebar_footer_item(label="Log out", icon_left="log-out",
                                   color="error")
    return box


@refreshable(deps=[SidebarPlayground])
def server_panel() -> None:
    state = SidebarPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("width (état déplié)"):
            ui.select(value=state.width, options=[(w, w) for w in WIDTHS],
                      on_change=server_changed)
        with control("collapsible — ce que « replié » veut dire"):
            ui.select(
                value=state.collapsible,
                options=[
                    ("rail", "rail — bande d'icônes 64px, dans le flux"),
                    ("offcanvas", "offcanvas — largeur 0, dans le flux"),
                    ("overlay", "overlay — au-dessus, fond assombri"),
                    ("none", "none — ne se replie jamais"),
                ],
                on_change=server_changed,
            )
        with control("open"):
            ui.switch(checked=state.open, on_change=server_changed)
        with control("item : color (ligne active)"):
            ui.select(value=state.item_color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("item : icon (ligne active)"):
            ui.input(value=state.item_icon,
                     placeholder="home / bug / (vide = pas d'icône)",
                     on_change=server_changed)
        with control("item : badge (ligne active)"):
            ui.input(value=state.item_badge,
                     placeholder="3 / 99+ / (vide = pas de pastille)",
                     on_change=server_changed)
        with control("item : disabled (ligne active)"):
            ui.switch(checked=state.item_disabled, on_change=server_changed)
        with control("item : active — le mode de résolution"):
            ui.select(value=state.active_mode,
                      options=[("auto", "None — dérivé de l'URL"),
                               ("true", "True — forcé actif"),
                               ("false", "False — forcé inactif")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="bg-primary/5",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-sidebar",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Main navigation",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="border-right-width: 3px",
                     on_change=server_changed)
        with control("extra_attrs (une par ligne, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=sidebar",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Navigation",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)

    ui.divider()

    with frame():
        build_preview(state)
        with ui.vstack(classes="flex-1 min-w-0 p-4"):
            ui.text("Contenu de page", color="muted", size="sm")

    ui.divider()

    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


@refreshable(deps=[SidebarEvents])
def events_panel() -> None:
    state = SidebarEvents()

    ui.text(
        "``SidebarItem`` déclare ``EVENTS = ('click',)`` — c'est le seul "
        "événement serveur de la famille (``Sidebar`` elle-même n'en "
        "déclare aucun : ouvrir/fermer est du client pur). Ici les "
        "entrées n'ont PAS de ``href`` : le handler serveur parle sans "
        "que la page navigue. ``sidebar_footer_item`` porte le même "
        "``on_click`` que ``dropdown_item``, il est câblé aussi.",
        color="muted", size="sm",
    )

    with frame("h-[340px]"):
        with ui.sidebar(slots=FIT, collapsible="none"):
            with ui.sidebar_section(label="SERVER EVENTS"):
                ui.sidebar_item("Home", icon="home", on_click=log_home)
                ui.sidebar_item("Issues", icon="bug", on_click=log_issues)
                ui.sidebar_item("Settings", icon="settings",
                                on_click=log_settings)
            with ui.sidebar_footer(name="Jean Hoccart", subtitle="compte"):
                ui.sidebar_footer_item(label="Log out", icon_left="log-out",
                                       color="error", on_click=log_logout)
        with ui.vstack(classes="flex-1 min-w-0 p-4"):
            ui.text("Clique une entrée →", color="muted", size="sm")

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
        ui.text("(aucun événement — clique une entrée ci-dessus)",
                color="muted", size="sm")

    ui.divider()

    representative = ui.sidebar(slots=FIT)
    with representative:
        ui.sidebar_item("Home", icon="home", on_click=log_home)
    emitted_html_block(
        "Emitted HTML (SidebarItem avec un handler serveur)",
        serialize_html(representative),
    )


def page() -> None:
    client = SidebarClient()
    client_events = SidebarClientEvents()

    with ui.container():
        with ui.vstack():
            ui.heading("Sidebar", level=1)
            ui.text(
                "Rail de navigation desktop. Six pièces : ``ui.sidebar`` "
                "(l'``<aside>``), ``ui.sidebar_title`` (l'en-tête : logo + "
                "titre + toggle), ``ui.sidebar_section`` (un groupe avec "
                "un intertitre), ``ui.sidebar_item`` (une ligne de nav), "
                "``ui.sidebar_footer`` (la rangée compte épinglée en bas, "
                "qui ouvre un popover) et ``ui.sidebar_footer_item`` (une "
                "ligne de ce popover). La nav mobile n'est PAS dans le "
                "composant : c'est le ``if Screen().is_mobile:`` du dev.",
                color="muted",
            )
            ui.text(
                "Deux choses à savoir pour lire cette page. Chaque démo "
                "vit dans un cadre à hauteur fixe et porte "
                "``slots={'root': 'h-full!'}`` : le thème pose "
                "``h-screen`` sur la racine, donc sans override la "
                "sidebar mesure 100vh et son footer sort du cadre. Et les "
                "entrées portent de vrais ``href`` de playground — un "
                "clic navigue pour de bon.",
                color="muted", size="sm",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Basic — titre, section, items, footer",
                               level=3)
                    ui.text(
                        "L'entrée active est dérivée de l'URL : « Sidebar » "
                        "pointe sur cette page, elle ressort toute seule.",
                        color="muted", size="xs",
                    )
                    with frame():
                        with ui.sidebar(slots=FIT):
                            ui.sidebar_title("Playground", icon="zap")
                            with ui.sidebar_section(label="OVERVIEW"):
                                for label, icon, href in NAV:
                                    ui.sidebar_item(label, icon=icon,
                                                    href=href)
                            with ui.sidebar_footer(
                                name="Jean Hoccart",
                                subtitle="jean@acme.com",
                            ):
                                ui.sidebar_footer_item(
                                    label="Settings", icon_left="settings")
                                ui.sidebar_footer_item(
                                    label="Log out", icon_left="log-out",
                                    color="error")
                        with ui.vstack(classes="flex-1 min-w-0 p-4"):
                            ui.text("Contenu de page", color="muted",
                                    size="sm")

                    ui.heading("open — déplié vs replié", level=3)
                    ui.text(
                        "``open`` pilote ``data-open`` sur la racine ; tout "
                        "le repli est du CSS qui lit cet attribut. Le "
                        "chevron du titre le bascule.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        for is_open in (True, False):
                            with ui.vstack(gap="xs"):
                                ui.text(f"open={is_open}", color="muted",
                                        size="xs", classes="font-mono")
                                with frame("h-[300px]"):
                                    with ui.sidebar(slots=FIT, open=is_open):
                                        ui.sidebar_title("App", icon="zap")
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Home", icon="home")
                                            ui.sidebar_item(
                                                "Issues", icon="bug",
                                                badge=12)
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading("collapsible — ce que « replié » veut dire",
                               level=3)
                    ui.text(
                        "Un seul axe, quatre valeurs. ``rail`` garde une "
                        "bande d'icônes de 64px et ``offcanvas`` s'efface "
                        "— tous deux DANS le flux, donc gatés ``md:``. "
                        "``overlay`` sort du flux et passe au-dessus du "
                        "contenu avec un fond assombri : c'est le mode "
                        "qu'on monte sur un téléphone, et le seul qui ne "
                        "soit pas gaté. ``none`` ne se replie jamais et ne "
                        "rend aucun chevron.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        for v in MODES:
                            with ui.vstack(gap="xs"):
                                ui.text(f'collapsible="{v}" · open=False',
                                        color="muted", size="xs",
                                        classes="font-mono")
                                with frame("h-[300px]"):
                                    sb = ui.sidebar(slots=FIT, collapsible=v,
                                                    open=False)
                                    with sb:
                                        ui.sidebar_title("App", icon="zap")
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Home", icon="home")
                                            ui.sidebar_item(
                                                "Issues", icon="bug")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        # ``offcanvas`` et ``overlay``
                                        # sortent la barre de l'écran :
                                        # sans ce bouton la case montre
                                        # une barre qu'on ne peut plus
                                        # rouvrir. La page en monte
                                        # plusieurs, d'où l'argument.
                                        ui.sidebar_trigger(sb, size="sm")
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading("width — largeur DÉPLIÉE", level=3)
                    with ui.vstack(gap="md"):
                        for w in WIDTHS:
                            with ui.vstack(gap="xs"):
                                ui.text(f'width="{w}"', color="muted",
                                        size="xs", classes="font-mono")
                                with frame("h-[220px]"):
                                    with ui.sidebar(slots=FIT, width=w):
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Dashboard", icon="home")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading("Replier, et revenir", level=3)
                    ui.text(
                        "Tout mode SAUF ``none`` rend une **arête "
                        "cliquable** sur le bord de la barre, dans les deux "
                        "états ; un ``sidebar_title`` ajoute son propre "
                        "bouton. Les deux vivent DANS l'aside, donc ils "
                        "partent avec elle : en ``offcanvas`` ou "
                        "``overlay``, le retour se pose dehors — "
                        "``ui.sidebar_trigger()``, où l'app veut. Le "
                        "framework refuse de rendre une barre escamotable "
                        "que rien ne peut rouvrir.",
                        color="muted", size="xs",
                    )
                    ui.text(
                        "``ui.sidebar_trigger`` — deux axes seulement : "
                        "``icon=`` (le dépôt écrit ``panel-left`` dans "
                        "chat, ``menu`` dans le CRM) et ``size=``, pour "
                        "suivre la densité de la barre où il est posé. "
                        "``variant=`` et ``color=`` LÈVENT : une app a un "
                        "déclencheur, il ressemble au reste de sa barre du "
                        "haut.",
                        color="muted", size="xs",
                    )
                    with frame("h-[220px]"):
                        trg = ui.sidebar(slots=FIT, collapsible="overlay",
                                         open=False)
                        with trg:
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                        with ui.vstack(classes="flex-1 min-w-0 p-3",
                                       gap="sm"):
                            with ui.hstack(align="center", gap="sm"):
                                ui.sidebar_trigger(trg, icon="menu",
                                                   size="sm")
                                ui.text("icon=\"menu\" · size=\"sm\"",
                                        color="muted", size="xs",
                                        classes="font-mono")
                            with ui.hstack(align="center", gap="sm"):
                                ui.sidebar_trigger(trg)
                                ui.text("le défaut", color="muted",
                                        size="xs", classes="font-mono")

                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        for coll in ("rail", "none"):
                            with ui.vstack(gap="xs"):
                                ui.text(f'collapsible="{coll}" · sans titre',
                                        color="muted", size="xs",
                                        classes="font-mono")
                                with frame("h-[220px]"):
                                    with ui.sidebar(slots=FIT,
                                                    collapsible=coll):
                                        with ui.sidebar_section(
                                                label="MAIN"):
                                            ui.sidebar_item(
                                                "Home", icon="home")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

                    ui.heading("item : color", level=3)
                    ui.text(
                        "La couleur ne peint QUE la ligne active — au "
                        "repos une ligne est ``text-muted``.",
                        color="muted", size="xs",
                    )
                    with frame("h-[420px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="COLORS"):
                                for c in COLORS:
                                    ui.sidebar_item(c, icon="circle",
                                                    color=c, active=True)
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("item : badge / disabled / active", level=3)
                    with frame("h-[340px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="STATES"):
                                ui.sidebar_item("Inbox", icon="inbox",
                                                badge=3)
                                ui.sidebar_item("Alerts", icon="bell",
                                                badge="99+")
                                ui.sidebar_item("Soon", icon="lock",
                                                disabled=True)
                                ui.sidebar_item("active=True", icon="check",
                                                active=True)
                                ui.sidebar_item("active=False", icon="x",
                                                active=False, href="/")
                                ui.sidebar_item("auto (URL)", icon="compass",
                                                href=PATH)
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "``SidebarItem`` déclare ``NAMED_SLOTS = ('icon',)`` "
                        "et ``ICON_SLOTS = ('icon',)`` : un raccourci string "
                        "ou un Component. ``sidebar_title`` et "
                        "``sidebar_footer`` acceptent aussi les deux formes "
                        "pour ``icon=`` / ``avatar=``.",
                        color="muted", size="sm",
                    )

                    ui.heading("item : icon=str vs icon=Component", level=3)
                    with frame("h-[280px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="ICON SLOT"):
                                ui.sidebar_item("Raccourci", icon="home")
                                ui.sidebar_item(
                                    "Component teinté",
                                    icon=ui.icon("heart", color="error"))
                                ui.sidebar_item(
                                    "Component xs",
                                    icon=ui.icon("search", size="xs"))
                                ui.sidebar_item("Sans icône")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("title : icon=str (teinte primary) vs "
                               "icon=Component (garde SA couleur)", level=3)
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        with frame("h-[200px]"):
                            with ui.sidebar(slots=FIT, collapsible="none"):
                                ui.sidebar_title("String", icon="zap")
                                with ui.sidebar_section():
                                    ui.sidebar_item("Home", icon="home")
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("page", color="muted", size="xs")
                        with frame("h-[200px]"):
                            with ui.sidebar(slots=FIT, collapsible="none"):
                                ui.sidebar_title(
                                    "Component",
                                    icon=ui.icon("flame", color="warning"))
                                with ui.sidebar_section():
                                    ui.sidebar_item("Home", icon="home")
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("page", color="muted", size="xs")

                    ui.heading("footer : avatar=initiales / str / Component",
                               level=3)
                    ui.text(
                        "Sans ``avatar``, les initiales sont dérivées du "
                        "``name`` (« Jean Hoccart » → « JH »).",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 3}, gap="md"):
                        for label, kw in (
                            ("dérivé du name", {}),
                            ("avatar='ZZ'", {"avatar": "ZZ"}),
                            ("avatar=ui.avatar(...)",
                             {"avatar": ui.avatar(initials="BZ",
                                                  color="success")}),
                        ):
                            with ui.vstack(gap="xs"):
                                ui.text(label, color="muted", size="xs",
                                        classes="font-mono")
                                with frame("h-[200px]"):
                                    with ui.sidebar(slots=FIT,
                                                    collapsible="none"):
                                        with ui.sidebar_section():
                                            ui.sidebar_item("Home",
                                                            icon="home")
                                        with ui.sidebar_footer(
                                            name="Jean Hoccart",
                                            subtitle="jean@acme.com",
                                            **kw,
                                        ):
                                            ui.sidebar_footer_item(
                                                label="Log out",
                                                icon_left="log-out",
                                                color="error")
                                    with ui.vstack(
                                            classes="flex-1 min-w-0 p-3"):
                                        ui.text("page", color="muted",
                                                size="xs")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("Libellé très long — truncate", level=3)
                    with frame("h-[220px]"):
                        with ui.sidebar(slots=FIT, width="sm",
                                        collapsible="none"):
                            with ui.sidebar_section(
                                    label="UN INTERTITRE LUI AUSSI TRÈS LONG"):
                                ui.sidebar_item(
                                    "Un libellé d'entrée beaucoup trop long "
                                    "pour la largeur du rail", icon="home")
                                ui.sidebar_item(
                                    "Long + badge", icon="bug", badge="99+")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("Débordement — le footer reste épinglé",
                               level=3)
                    ui.text(
                        "Seule la zone du milieu défile (slot ``scroll``, "
                        "``flex-1 min-h-0 overflow-y-auto``). Le titre et "
                        "le footer sont ``shrink-0`` : une liste de 30 "
                        "entrées ne les emporte pas.",
                        color="muted", size="xs",
                    )
                    with frame("h-[360px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            ui.sidebar_title("Épinglé", icon="zap")
                            with ui.sidebar_section(label="30 ENTRÉES"):
                                for i in range(1, 31):
                                    ui.sidebar_item(f"Entrée {i}",
                                                    icon="circle")
                            with ui.sidebar_footer(name="Jean Hoccart",
                                                   subtitle="épinglé"):
                                ui.sidebar_footer_item(label="Log out",
                                                       icon_left="log-out",
                                                       color="error")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("Sections sans label / sidebar vide", level=3)
                    ui.text(
                        "Une section sans ``label`` n'émet ni intertitre ni "
                        "séparateur de rail — il n'y a pas de légende à "
                        "replier.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 1, "lg": 2}, gap="md"):
                        with frame("h-[200px]"):
                            with ui.sidebar(slots=FIT, collapsible="none"):
                                with ui.sidebar_section():
                                    ui.sidebar_item("Sans label",
                                                    icon="home")
                                    ui.sidebar_item("Ni séparateur",
                                                    icon="circle")
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("page", color="muted", size="xs")
                        with frame("h-[200px]"):
                            ui.sidebar(slots=FIT)
                            with ui.vstack(classes="flex-1 min-w-0 p-3"):
                                ui.text("sidebar vide", color="muted",
                                        size="xs")

                    ui.heading("href externe — pas de partial-nav", level=3)
                    ui.text(
                        "Un ``href`` à schéma (``https:`` / ``mailto:`` / "
                        "``tel:``) sort du garde : ``target=_blank``, aucun "
                        "``hx-get`` injecté.",
                        color="muted", size="xs",
                    )
                    with frame("h-[200px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="LIENS"):
                                ui.sidebar_item("Interne", icon="home",
                                                href="/")
                                ui.sidebar_item(
                                    "Externe", icon="external-link",
                                    href="https://example.com")
                                ui.sidebar_item("Mail", icon="mail",
                                                href="mailto:a@b.c")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Plusieurs sections, un footer à popover, et des "
                        "composants quelconques entre les sections : tout "
                        "ce qui n'est ni ``sidebar_title`` ni "
                        "``sidebar_footer`` atterrit dans la zone "
                        "défilante.",
                        color="muted", size="sm",
                    )
                    with frame("h-[460px]"):
                        with ui.sidebar(slots=FIT):
                            ui.sidebar_title("Acme", icon="box", href="/")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Dashboard", icon="home",
                                                href="/")
                                ui.sidebar_item("Issues", icon="bug",
                                                badge=42)
                                ui.sidebar_item("Releases", icon="rocket")
                            with ui.sidebar_section(label="INSIGHTS"):
                                ui.sidebar_item("Analytics",
                                                icon="bar-chart-3")
                                ui.sidebar_item("Reports", icon="file-text")
                            with ui.sidebar_section(label="ACCOUNT"):
                                ui.sidebar_item("Settings", icon="settings")
                                ui.sidebar_item("Billing", icon="credit-card")
                            with ui.sidebar_footer(name="Jean Hoccart",
                                                   subtitle="jean@acme.com",
                                                   color="secondary"):
                                ui.sidebar_footer_item(
                                    label="Profile", icon_left="user",
                                    href="/")
                                ui.sidebar_footer_item(
                                    label="Settings", icon_left="settings",
                                    shortcut="⌘,")
                                ui.sidebar_footer_item(
                                    label="Docs", icon_left="book",
                                    icon_right="external-link",
                                    href="https://example.com")
                                ui.sidebar_footer_item(
                                    label="Bientôt", icon_left="lock",
                                    disabled=True)
                                ui.sidebar_footer_item(
                                    label="Log out", icon_left="log-out",
                                    color="error")
                        with ui.vstack(classes="flex-1 min-w-0 p-4"):
                            ui.text("Contenu de page", color="muted",
                                    size="sm")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "La racine est ``role=navigation`` + "
                        "``aria-label=Sidebar`` (surchargeables). Chaque "
                        "entrée porte un ``aria-label`` avec son libellé — "
                        "dans le rail replié le libellé visible est "
                        "``hidden``, et un tooltip au survol n'est une "
                        "affordance ni au clavier ni au lecteur d'écran. Le "
                        "panneau de tooltip partagé est donc "
                        "``aria-hidden``. Une entrée ``disabled`` porte "
                        "``aria-disabled`` ET perd son ``href`` + ses "
                        "``hx-*`` + son ``tabindex``.",
                        color="muted", size="sm",
                    )

                    ui.heading("Parcours au clavier", level=3)
                    ui.text(
                        "Tab dans la liste : l'anneau de focus doit être "
                        "entièrement visible et son écart doit se confondre "
                        "avec le fond de la sidebar. Il ne le fait pas "
                        "encore — l'écart est peint en ``ring-offset-"
                        "background`` (#020617) alors que la sidebar est "
                        "``bg-surface`` (#0f172a), et la ligne est à 0px de "
                        "sa boîte défilante en ``overflow-x-hidden``, donc "
                        "l'anneau est rogné à gauche et à droite.",
                        color="muted", size="xs",
                    )
                    with frame("h-[300px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="TAB ORDER"):
                                ui.sidebar_item("Premier", icon="home",
                                                href="/")
                                ui.sidebar_item("Deuxième", icon="bug",
                                                href="/badge")
                                ui.sidebar_item("Verrouillé", icon="lock",
                                                disabled=True, href="/")
                                ui.sidebar_item("Troisième", icon="settings",
                                                href="/icon")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 6 — Server playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Chaque prop du conteneur et de l'entrée, plus les "
                        "échappatoires universelles. Le panneau se re-rend "
                        "côté serveur à chaque changement.",
                        color="muted", size="sm",
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
                        "``Sidebar.BINDABLE_PROPS = ('open',)`` et "
                        "``SidebarItem.BINDABLE_PROPS = ('active', 'badge', "
                        "'disabled')``. Les quatre sont câblées ci-dessous "
                        "sur un ``ClientState`` : aucun aller-retour "
                        "serveur, le runtime écrit dans le DOM.",
                        color="muted", size="sm",
                    )

                    with ui.grid(cols={"base": 1, "sm": 2, "md": 4},
                                 gap="md"):
                        with control("sidebar : open"):
                            ui.switch(checked=client.expanded)
                        with control("item : active"):
                            ui.switch(checked=client.active)
                        with control("item : disabled"):
                            ui.switch(checked=client.disabled)
                        with control("item : badge"):
                            ui.number_input(value=client.badge, min=0, max=99)

                    with frame("h-[300px]"):
                        with ui.sidebar(slots=FIT, open=client.expanded):
                            ui.sidebar_title("Client", icon="zap")
                            with ui.sidebar_section(label="BOUND"):
                                ui.sidebar_item("Piloté", icon="home",
                                                active=client.active,
                                                badge=client.badge,
                                                disabled=client.disabled)
                                ui.sidebar_item("Témoin", icon="circle")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.divider()

                    bound = ui.sidebar(slots=FIT, open=client.expanded)
                    with bound:
                        ui.sidebar_item("Piloté", icon="home",
                                        active=client.active,
                                        badge=client.badge,
                                        disabled=client.disabled)
                    emitted_html_block(
                        "Emitted HTML (SSR snapshot — le runtime prend le "
                        "relais)",
                        serialize_html(bound),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes", level=2)
                    ui.text(
                        "``Sidebar.IMPERATIVE = ('open', 'close', "
                        "'toggle')``. Les trois modes du contrat impératif "
                        "de Bretzel, côte à côte.",
                        color="muted", size="sm",
                    )

                    ui.heading("Mode 1 — impératif seul (aucun binding)",
                               level=3)
                    ui.text(
                        "Sans binding, la méthode dispatche un événement "
                        "DOM (``bz-open`` / ``bz-close`` / ``bz-toggle``) "
                        "que la racine écoute.",
                        color="muted", size="xs",
                    )
                    imperative = ui.sidebar(slots=FIT, collapsible="none")
                    with ui.hstack(gap="sm"):
                        ui.button("open()", size="xs", variant="outline",
                                  on_click=imperative.open())
                        ui.button("close()", size="xs", variant="outline",
                                  on_click=imperative.close())
                        ui.button("toggle()", size="xs",
                                  on_click=imperative.toggle())
                    with frame("h-[240px]"):
                        with imperative:
                            ui.sidebar_title("Impératif", icon="zap")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                                ui.sidebar_item("Issues", icon="bug")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("Mode 2 — ClientBinding seul", level=3)
                    ui.text(
                        "``open=`` reçoit un binding : le switch et la "
                        "sidebar lisent le même signal client.",
                        color="muted", size="xs",
                    )
                    with ui.hstack(gap="sm", align="center"):
                        ui.switch(checked=client.expanded)
                        ui.text("client.expanded", color="muted", size="xs",
                                classes="font-mono")
                    with frame("h-[240px]"):
                        with ui.sidebar(slots=FIT, collapsible="none",
                                        open=client.expanded):
                            ui.sidebar_title("Binding", icon="zap")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

                    ui.heading("Mode 3 — les deux (write-through)", level=3)
                    ui.text(
                        "Avec un binding, ``.toggle()`` écrit DANS le "
                        "binding : le switch ci-dessus suit le bouton, et "
                        "réciproquement.",
                        color="muted", size="xs",
                    )
                    both = ui.sidebar(slots=FIT, collapsible="none",
                                      open=client.expanded)
                    with ui.hstack(gap="sm", align="center"):
                        ui.button("toggle()", size="xs", on_click=both.toggle())
                        ui.switch(checked=client.expanded)
                        ui.text("même signal", color="muted", size="xs")
                    with frame("h-[240px]"):
                        with both:
                            ui.sidebar_title("Les deux", icon="zap")
                            with ui.sidebar_section(label="MAIN"):
                                ui.sidebar_item("Home", icon="home")
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("page", color="muted", size="xs")

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``SidebarItem.EVENTS = ('click',)`` en expression "
                        "client pure — zéro aller-retour, le log vit dans "
                        "un ``ClientState``.",
                        color="muted", size="sm",
                    )

                    with frame("h-[260px]"):
                        with ui.sidebar(slots=FIT, collapsible="none"):
                            with ui.sidebar_section(label="CLIENT EVENTS"):
                                for name in ("Home", "Issues", "Settings"):
                                    ui.sidebar_item(
                                        name, icon="circle",
                                        on_click=client_events.log.push(name),
                                    )
                        with ui.vstack(classes="flex-1 min-w-0 p-3"):
                            ui.text("Clique une entrée →", color="muted",
                                    size="xs")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=client_events.log.clear())

                    ui.text(
                        ClientExpression(
                            "($bz.state.SidebarClientEvents.default.log"
                            ' || []).join("\\n") || "(no events yet)"'
                        ),
                        color="muted", size="sm",
                        classes="font-mono whitespace-pre",
                    )

                    ui.divider()

                    representative = ui.sidebar(slots=FIT)
                    with representative:
                        ui.sidebar_item(
                            "Home", icon="home",
                            on_click=client_events.log.push("Home"),
                        )
                    emitted_html_block(
                        "Emitted HTML (SidebarItem avec une expression "
                        "client)",
                        serialize_html(representative),
                    )

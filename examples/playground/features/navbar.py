"""``Navbar`` test bench.

Quatre cartes obligatoires — Reference / Edge cases / A11y / Server
playground — plus Slots et Composability. ``BINDABLE_PROPS = ()``,
``EVENTS = ()`` et aucune API impérative : pas de carte client, pas de
carte événement.

Ce banc est né le 2026-08-30, en supprimant la famille ``/matrix`` : elle
était le SEUL endroit du playground où ``ui.navbar`` était construit.
Supprimée, le composant se retrouvait livré et démontré nulle part — ce
que ``test_playground_demos_the_api`` a dit tout de suite.

⚠️ Aucune barre de cette page n'est ``sticky=True`` hors du bac de
démonstration : la coque du playground fait défiler le document, donc une
barre épinglée se collerait au haut de la fenêtre et couvrirait la vraie
navigation. Le paramètre se règle dans le *Server playground*, où
l'aperçu vit dans un conteneur qui défile pour lui.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/navbar"


VARIANTS = ["standard", "floating"]
SIDES = ["left", "center", "right"]
LINKS = [("Docs", "/navbar"), ("Pricing", "/navbar"), ("Blog", "/navbar")]


class NavbarPlayground(PageState):
    variant: str = field(default="standard")
    sticky:  str = field(default="off")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")


def server_changed(state: NavbarPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state``. server_panel declares deps=[NavbarPlayground], so it
    # re-renders on its own.
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


def build_preview(state: NavbarPlayground) -> dict:
    kwargs: dict = {
        "variant": state.variant,
        "sticky": state.sticky == "on",
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
    return kwargs


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def demo_bar(**kwargs) -> None:
    """Une barre complète : les trois sections, dans l'ordre de lecture.

    Écrite ici plutôt que recopiée dans chaque carte — les six aperçus de
    la page ne diffèrent QUE par les kwargs de la barre, et c'est
    exactement ce qu'on veut pouvoir comparer.
    """
    with ui.navbar(**kwargs):
        with ui.navbar_section(side="left"):
            ui.heading("Bretzel", level=3)
        with ui.navbar_section(side="center"):
            for label, href in LINKS:
                ui.navbar_item(label, href=href)
        with ui.navbar_section(side="right"):
            ui.button("Get started", color="primary", size="sm")


@refreshable(deps=[NavbarPlayground])
def server_panel() -> None:
    state = NavbarPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("variant"):
            ui.select(value=state.variant,
                      options=[(v, v) for v in VARIANTS],
                      on_change=server_changed)
        with control("sticky"):
            ui.select(value=state.sticky,
                      options=[("off", "False (défaut)"),
                               ("on", "True (épinglée au défilement)")],
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="shadow-lg",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-navbar",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Navigation principale",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 40rem",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=nav",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="La barre du haut",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (défaut)"),
                               ("off", "False (pas de rendu)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    ui.text(
        "Le bac ci-dessous DÉFILE : c'est le seul moyen de juger "
        "``sticky`` sans épingler la barre au haut de la fenêtre, "
        "par-dessus la navigation du playground.",
        color="muted", size="xs",
    )
    with ui.container(
        classes="h-56 overflow-y-auto rounded-xl border border-text/10 p-2"
    ):
        demo_bar(**kwargs)
        with ui.vstack(gap="sm", classes="pt-3"):
            for index in range(8):
                ui.text(f"Ligne de contenu {index + 1} — faites défiler.",
                        color="muted", size="sm")

    ui.divider()

    preview = ui.navbar(**kwargs)
    with preview:
        with ui.navbar_section(side="left"):
            ui.heading("Bretzel", level=3)
    emitted_html_block("Emitted HTML (Navbar)", serialize_html(preview))


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Navbar", level=1)
        ui.text(
            "La barre du haut — un <header> qui possède son "
            "``current_path``, comme la sidebar possède le sien. C'est "
            "la moitié horizontale du même trio : navbar / "
            "navbar_section / navbar_item, miroir de sidebar / "
            "sidebar_section / sidebar_item. Deux usages, et ils ne se "
            "ressemblent pas : la barre d'un site public, et la "
            "navigation MOBILE d'une app dont le bureau montre une "
            "sidebar.",
            color="muted",
        )

        # ── Carte 1 — Reference ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            demo_bar()

            ui.heading("variant", level=3)
            ui.text(
                "``standard`` colle la barre au bord de la page. "
                "``floating`` la détache en carte arrondie — l'allure "
                "des sites Stripe ou Linear, qui ne va qu'avec un fond "
                "de page visible autour.",
                color="muted", size="xs",
            )
            with ui.vstack(gap="md"):
                for name in VARIANTS:
                    with ui.vstack(gap="xs"):
                        ui.text(f"variant={name}", color="muted",
                                size="xs")
                        demo_bar(variant=name)

            ui.heading("sticky", level=3)
            ui.text(
                "``sticky=True`` épingle la barre au haut pendant le "
                "défilement. Elle n'est PAS démontrée épinglée ici : la "
                "coque du playground fait défiler le document, donc "
                "elle se collerait par-dessus la vraie navigation. Le "
                "bac qui défile du *Server playground* est fait pour "
                "ça.",
                color="muted", size="xs",
            )
            ui.code(
                serialize_html(ui.navbar(sticky=True)),
                lang="html",
            )

        # ── Carte 2 — Slots ─────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                "La barre n'a pas de slot au sens ``with`` : elle a des "
                "SECTIONS. ``ui.navbar_section(side=…)`` est le seul "
                "enfant qu'on lui donne, et son ``side`` décide de la "
                "place — pas l'ordre d'écriture.",
                color="muted", size="sm",
            )

            ui.heading("Les trois côtés", level=3)
            with ui.vstack(gap="md"):
                for side in SIDES:
                    with ui.vstack(gap="xs"):
                        ui.text(f'side="{side}" seul', color="muted",
                                size="xs")
                        with ui.navbar():
                            with ui.navbar_section(side=side):
                                ui.text(f"contenu {side}")

            ui.heading("navbar_item — l'état actif se calcule", level=3)
            ui.text(
                "Un item ne dit jamais qu'il est actif : la barre porte "
                "``current_path`` dans son scope client, et chaque item "
                "compare son ``href``. C'est pourquoi « Docs » "
                "ci-dessous est allumé — la page EST /navbar.",
                color="muted", size="xs",
            )
            with ui.navbar():
                with ui.navbar_section(side="left"):
                    ui.navbar_item("Docs", href="/navbar")
                    ui.navbar_item("Ailleurs", href="/sidebar")

        # ── Carte 3 — Edge cases ────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)

            ui.heading("Barre vide", level=3)
            ui.text("Aucune section : la barre garde sa hauteur, donc "
                    "la page ne saute pas quand le contenu arrive.",
                    color="muted", size="xs")
            ui.navbar()

            ui.heading("Une seule section, à droite", level=3)
            ui.text(
                "La marge automatique tient sans voisine — c'est le cas "
                "qui casse dans une barre bâtie à la main en flex.",
                color="muted", size="xs",
            )
            with ui.navbar():
                with ui.navbar_section(side="right"):
                    ui.button("Se connecter", size="sm")

            ui.heading("Trop d'items pour la largeur", level=3)
            ui.text(
                "La barre ne replie rien toute seule : les items "
                "débordent ou se serrent selon la place. Une vraie app "
                "bascule vers un menu à ce moment-là — c'est une "
                "décision de mise en page, pas du composant.",
                color="muted", size="xs",
            )
            with ui.navbar():
                with ui.navbar_section(side="center"):
                    for index in range(12):
                        ui.navbar_item(f"Rubrique {index + 1}",
                                       href="/navbar")

            ui.heading("Libellé très long", level=3)
            with ui.navbar():
                with ui.navbar_section(side="left"):
                    ui.navbar_item(
                        "Une rubrique dont le nom n'a pas été relu",
                        href="/navbar",
                    )

        # ── Carte 4 — Composability ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)

            ui.heading("Barre de site public", level=3)
            ui.text("Marque à gauche, liens au centre, appel à "
                    "l'action à droite — la forme la plus courante.",
                    color="muted", size="xs")
            demo_bar(variant="floating")

            ui.heading("Barre d'application", level=3)
            ui.text(
                "Pas de liens : le titre de l'écran et le compte. Sur "
                "mobile, c'est CETTE barre qui remplace la sidebar — la "
                "coque branche sur ``Screen().is_mobile``.",
                color="muted", size="xs",
            )
            with ui.navbar():
                with ui.navbar_section(side="left"):
                    ui.heading("Tableau de bord", level=3)
                with ui.navbar_section(side="right"):
                    ui.icon_button("bell", variant="ghost")
                    ui.avatar(initials="JH", size="sm")

            ui.heading("Dans une cellule de grille contrainte", level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                for name in VARIANTS:
                    with ui.navbar(variant=name):
                        with ui.navbar_section(side="left"):
                            ui.text("Étroite")
                        with ui.navbar_section(side="right"):
                            ui.button("OK", size="sm")

        # ── Carte 5 — A11y ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "La racine est un vrai ``<header>``, donc un lecteur "
                "d'écran l'annonce comme un repère et permet d'y sauter "
                "directement — ce qu'un ``<div>`` stylé ne donne pas. "
                "Les items sont des liens réels : ils s'atteignent au "
                "Tab, s'ouvrent dans un nouvel onglet au clic du "
                "milieu, et se lisent dans la liste des liens de la "
                "page.",
                color="muted", size="sm",
            )
            ui.text(
                "L'état actif ne tient pas qu'à la couleur : l'item "
                "courant porte aussi son marqueur dans le DOM, ce qui "
                "compte pour qui ne distingue pas la teinte du fond.",
                color="muted", size="sm",
            )

            ui.heading("aria-label quand plusieurs barres coexistent",
                       level=3)
            ui.text(
                "Deux repères de navigation sans nom s'annoncent "
                "pareil. Dès qu'il y en a deux sur une page, chacun a "
                "besoin du sien.",
                color="muted", size="xs",
            )
            with ui.navbar(attrs={"aria-label": "Navigation principale"}):
                with ui.navbar_section(side="left"):
                    ui.navbar_item("Docs", href="/navbar")
            with ui.navbar(attrs={"aria-label": "Navigation secondaire"}):
                with ui.navbar_section(side="left"):
                    ui.navbar_item("Statut", href="/navbar")

        # ── Carte 6 — Server playground ─────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Chaque prop ET chaque échappatoire câblée à un "
                "contrôle ; l'aperçu et le HTML émis se rafraîchissent "
                "à chaque changement.",
                color="muted", size="sm",
            )
            server_panel()

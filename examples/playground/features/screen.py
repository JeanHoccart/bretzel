"""``Viewport`` + ``Pane`` — le banc de l'écran gelé.

Les deux composants du modèle « document gelé, régions qui défilent ».
Ils vont ensemble et se testent ensemble : un ``pane`` sans hauteur
au-dessus de lui ne défile pas, et un ``viewport`` sans ``pane`` clippe
son contenu.

⚠️ **Le viewport ne peut pas être monté DANS cette page**, et c'est une
propriété du composant, pas une limite du banc : il est ``fixed
inset-0``, donc il recouvrirait la barre latérale et la page entière. Il
est démontré de deux façons honnêtes — son HTML émis, lisible ici, et
une **route à part** (``/screen-demo``, sans coque) où il EST l'écran.
C'est le seul endroit du playground où « mettre le composant dans une
carte » n'a aucun sens.

``BINDABLE_PROPS = ()`` pour les deux : de la disposition pure, rien
qu'un driver client aurait à piloter.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/screen"
DEMO_PATH = "/screen-demo"

PADDINGS = ["none", "xs", "sm", "md", "lg", "xl"]
GAPS = ["none", "xs", "sm", "md", "lg", "xl"]
ALIGNS = ["start", "center", "end", "stretch", "baseline"]
JUSTIFIES = ["start", "center", "end", "between", "around", "evenly"]
DIRECTIONS = ["row", "col"]


class ScreenPlayground(PageState):
    # Pane
    gap: str = field(default="sm")
    padding: str = field(default="none")
    align: str = field(default="stretch")
    justify: str = field(default="start")
    # Viewport
    direction: str = field(default="row")
    frame_align: str = field(default="stretch")
    frame_gap: str = field(default="none")


def server_changed(state: ScreenPlayground) -> None:
    # Le dispatcher hydrate la valeur du contrôle modifié dans ``state`` ;
    # ``deps=[ScreenPlayground]`` re-rend le panneau.
    pass


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def filler(count: int, prefix: str = "Ligne") -> None:
    """Assez de contenu pour que le pane déborde — sinon rien ne défile
    et le banc ne montre rien."""
    for i in range(count):
        with ui.card(padding="sm"):
            ui.text(f"{prefix} {i + 1}", size="sm", color="muted")


@refreshable(deps=[ScreenPlayground])
def pane_panel() -> None:
    state = ScreenPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 4}, gap="md"):
        with control("gap"):
            ui.select(value=state.gap, options=[(g, g) for g in GAPS],
                      on_change=server_changed)
        with control("padding"):
            ui.select(value=state.padding,
                      options=[(p, p) for p in PADDINGS],
                      on_change=server_changed)
        with control("align"):
            ui.select(value=state.align, options=[(a, a) for a in ALIGNS],
                      on_change=server_changed)
        with control("justify"):
            ui.select(value=state.justify,
                      options=[(j, j) for j in JUSTIFIES],
                      on_change=server_changed)

    ui.divider()

    # La hauteur bornée est POSÉE PAR LE BANC, jamais par le pane : c'est
    # tout le contrat du composant — il prend ce que son parent lui laisse.
    with ui.card(padding="none", classes="h-72 flex flex-col"):
        with ui.pane(gap=state.gap, padding=state.padding,
                     align=state.align, justify=state.justify):
            filler(14)

    ui.divider()

    preview = ui.pane(gap=state.gap, padding=state.padding,
                      align=state.align, justify=state.justify)
    with preview:
        ui.text("Contenu")
    emitted_html_block("HTML émis (pane avec un seul texte)",
                       serialize_html(preview))


@refreshable(deps=[ScreenPlayground])
def viewport_panel() -> None:
    state = ScreenPlayground()

    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        with control("direction"):
            ui.select(value=state.direction,
                      options=[(d, d) for d in DIRECTIONS],
                      on_change=server_changed)
        with control("align"):
            ui.select(value=state.frame_align,
                      options=[(a, a) for a in ALIGNS],
                      on_change=server_changed)
        with control("gap"):
            ui.select(value=state.frame_gap,
                      options=[(g, g) for g in GAPS],
                      on_change=server_changed)

    ui.divider()

    frame = ui.viewport(direction=state.direction, align=state.frame_align,
                        gap=state.frame_gap)
    with frame, ui.pane(padding="md"):
        ui.text("Région qui défile")
    emitted_html_block("HTML émis (viewport + un pane)",
                       serialize_html(frame))

    with ui.hstack(gap="sm", align="center", wrap=True):
        ui.text("Le voir monté pour de vrai :", color="muted", size="sm")
        ui.button("Ouvrir /screen-demo", href=DEMO_PATH, variant="outline",
                  size="sm")


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Viewport + Pane", level=1)
        ui.text(
            "Les deux composants du modèle « document gelé » : un cadre "
            "qui prend l'écran et ne défile jamais, et les régions qui "
            "défilent à l'intérieur. Bretzel garde par DÉFAUT l'autre "
            "modèle — une page sans coque défile normalement ; celui-ci "
            "s'écrit explicitement.",
            color="muted",
        )

        # ── Carte 1 — Référence : le pane ────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Référence — pane", level=2)
            ui.text(
                "Chaque boîte ci-dessous est une carte de hauteur fixe. "
                "Le pane prend la place restante et défile ; c'est le "
                "PARENT qui donne la hauteur, jamais le pane.",
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                for padding in ("none", "md"):
                    with ui.vstack(gap="xs"):
                        ui.text(f"padding={padding}", size="xs",
                                color="muted")
                        with ui.card(padding="none",
                                     classes="h-64 flex flex-col"):
                            with ui.pane(gap="sm", padding=padding):
                                filler(10)

        # ── Carte 2 — Les deux régimes de hauteur ────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Les deux régimes de hauteur", level=2)
            ui.text(
                "Un pane porte `flex-1` ET `h-full`, parce que son parent "
                "peut avoir deux formes. À gauche une colonne flex — "
                "`flex-basis` gagne, le pane prend la place restante sous "
                "l'en-tête. À droite un bloc à hauteur définie — `flex-1` "
                "est inerte, `h-full` rend. Les deux défilent.",
                color="muted", size="sm",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.vstack(gap="xs"):
                    ui.text("parent = colonne flex (+ un en-tête)",
                            size="xs", color="muted")
                    with ui.card(padding="none",
                                 classes="h-64 flex flex-col"):
                        with ui.hstack(classes="shrink-0 px-3 py-2 "
                                               "border-b border-text/10"):
                            ui.text("En-tête épinglé", size="sm",
                                    weight="semibold")
                        with ui.pane(gap="sm", padding="sm"):
                            filler(10)
                with ui.vstack(gap="xs"):
                    ui.text("parent = bloc à hauteur définie", size="xs",
                            color="muted")
                    with ui.card(padding="none", classes="h-64"):
                        with ui.pane(gap="sm", padding="sm"):
                            filler(10)

        # ── Carte 3 — Deux panes indépendants ────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Deux régions qui défilent seules", level=2)
            ui.text(
                "C'est LA raison d'être du modèle gelé, et ce que le "
                "modèle « document qui défile » ne sait pas faire : deux "
                "colonnes côte à côte, chacune avec sa propre position "
                "de défilement. Un maître-détail, un kanban, un fil de "
                "messages à côté d'une liste.",
                color="muted", size="sm",
            )
            with ui.card(padding="none", classes="h-72"):
                with ui.hstack(gap="none", align="stretch",
                               classes="h-full divide-x divide-text/10"):
                    with ui.pane(gap="xs", padding="sm"):
                        filler(12, "Liste")
                    with ui.pane(gap="xs", padding="sm"):
                        filler(12, "Fiche")

        # ── Carte 4 — Le viewport ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Viewport", level=2)
            ui.text(
                "Il n'est pas monté ici, et c'est voulu : `fixed "
                "inset-0` recouvrirait la barre latérale et cette page. "
                "Son HTML est lisible ci-dessous, et la route "
                "`/screen-demo` le monte pour de vrai, sans coque.",
                color="muted", size="sm",
            )
            viewport_panel()

        # ── Carte 5 — Banc serveur du pane ───────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Banc serveur — pane", level=2)
            ui.text(
                "Chaque prop est câblée à un contrôle ; l'aperçu et le "
                "HTML émis se rafraîchissent à chaque changement.",
                color="muted", size="sm",
            )
            pane_panel()


def full_demo() -> None:
    """Le viewport MONTÉ — page sans coque, il est l'écran.

    Deux régions : une colonne fixe qui ne défile pas, et un pane qui
    défile. Rien d'autre ne bouge, et le document n'a aucune barre à
    lui : c'est exactement ce que le modèle promet.
    """
    with ui.viewport(direction="row", align="stretch", gap="none"):
        with ui.vstack(gap="sm", classes="w-56 shrink-0 p-4 "
                                         "border-r border-text/10"):
            ui.heading("Colonne fixe", level=3, size="sm")
            ui.text("Elle ne défile pas, quelle que soit la longueur de "
                    "la région de droite.", color="muted", size="xs")
            ui.button("← Retour au banc", href=PATH, variant="outline",
                      size="sm")
        with ui.pane(gap="sm", padding="lg"):
            ui.heading("Région qui défile", level=2)
            ui.text("Le document, lui, n'a aucune barre de défilement.",
                    color="muted", size="sm")
            filler(40, "Contenu")

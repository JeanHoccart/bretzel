"""``Resizable`` test bench.

Dix cards. ``Resizable.BINDABLE_PROPS = ("sizes",)`` — le partage des
panneaux est bindable ; orientation / disabled / size / color restent du
design-time, et ``min_size`` (sur le panneau) est une contrainte. Event :
``change``. Impératif : ``.set([30, 70])`` / ``.reset()``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/resizable"


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]
ORIENTATIONS = ["horizontal", "vertical"]

# Les partages proposés par le contrôle ``sizes``. Des CHAÎNES parce
# qu'un select poste du texte ; ``build_preview`` les reparse.
SPLITS = ["", "50,50", "25,75", "70,30", "20,60,20"]

TINTS = ["primary", "success", "warning", "error", "info",
         "secondary", "muted"]


def panel_block(index: int, height: str = "h-40") -> None:
    """Un panneau de démo — un bloc teinté qui porte son numéro.

    Au scope module parce qu'il sert dans les dix cards ; c'est le seuil
    du gabarit (un bloc répété dix fois devient une fonction).

    Il porte un contenu LARGE à dessein : c'est ce qui prouve que
    ``min-w-0`` fait son travail. Sans lui, flexbox refuse de descendre
    sous la largeur du contenu et la poignée se bloque bien avant le
    minimum déclaré — sans que rien n'échoue.
    """
    tint = TINTS[index % len(TINTS)]
    # ⚠️ ``bz-c-<teinte>`` + le PALIER, et surtout PAS un
    # ``f"bg-{tint}/15"``. Une classe assemblée n'existe que sous le
    # compilateur de dev, qui scanne le DOM vivant ; en prod le
    # compilateur ne lit que les sources, il ne verra jamais
    # ``bg-info/15``. Le pont, lui, est une classe complète.
    with ui.resizable_panel():
        with ui.flex(justify="center", align="center",
                     classes=f"{height} w-full bg-(--bz-bg) bz-c-{tint}"):
            ui.heading(str(index + 1), level=3, color=tint)


class ResizablePlayground(PageState):
    split: str = field(default="")
    orientation: str = field(default="horizontal")
    disabled: bool = field(default=False)
    size: str = field(default="md")
    color: str = field(default="primary")
    name: str = field(default="")
    panels: int = field(default=2)
    min_size: int = field(default=0)
    # Escape hatches.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class ResizableEvents(PageState):
    log: list = field(default_factory=list)


class ResizableClient(ClientState, persist="memory"):
    split: list = field(default_factory=lambda: [30, 70])


class ResizableClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ⚠️ Le state qui rend le ``change`` du banc LISIBLE, et il n'est pas
# décoratif. Sans binding ni ``name=``, le composant ne pose AUCUN
# ``name`` sur son input caché — c'est le choix délibéré du socle
# (``hidden_carrier_attrs`` : coller un name par défaut injecterait un
# champ parasite dans chaque formulaire englobant). Le handler part donc
# avec une FormData vide et reçoit sa valeur par défaut, soit
# ``change(sizes='')``. Le nom du champ DOIT s'appeler ``split`` :
# l'autoname le dérive de la binding, et c'est lui que le paramètre de
# ``log_change`` porte.
class ResizableServerEvents(ClientState, persist="memory"):
    split: list = field(default_factory=lambda: [50, 50])


# ``persist="local"`` et pas "memory" : c'est LE cas d'usage qui a mis
# ``resizable`` sur la roadmap — retrouver la largeur de sa colonne au
# rechargement. Rien de plus à déclarer côté composant.
class ResizableRemembered(ClientState, persist="local"):
    split: list = field(default_factory=lambda: [50, 50])


def log(name: str) -> None:
    state = ResizableEvents()
    state.log = [*state.log, name]


def log_change(split: str = "") -> None:
    log(f"change(sizes={split!r})")


def clear_log() -> None:
    state = ResizableEvents()
    state.log = []


def server_changed(state: ResizablePlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted).
    pass


def playground_change_handler(split: str = "") -> None:
    log(f"playground-server-change(sizes={split!r})")


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


def build_preview(state: ResizablePlayground) -> dict:
    kwargs: dict = {
        "orientation": state.orientation,
        "disabled": state.disabled,
        "size": state.size,
        "color": state.color,
    }
    # Chaîne vide = ne pas passer le kwarg (sizes=None = parts égales).
    if state.split:
        kwargs["sizes"] = [float(p) for p in state.split.split(",")]
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


@refreshable(deps=[ResizablePlayground])
def server_panel() -> None:
    state = ResizablePlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("sizes (les poids, vide = parts égales)"):
            ui.select(value=state.split,
                      options=[(s, s or "None (parts égales)")
                               for s in SPLITS],
                      on_change=server_changed)
        with control("panels (combien en rendre)"):
            ui.select(value=state.panels,
                      options=[(i, str(i)) for i in (1, 2, 3, 4)],
                      on_change=server_changed)
        with control("min_size (sur CHAQUE panneau, en %)"):
            ui.select(value=state.min_size,
                      options=[(i, f"{i} %") for i in (0, 10, 20, 30)],
                      on_change=server_changed)
        with control("orientation"):
            ui.select(value=state.orientation,
                      options=[(o, o) for o in ORIENTATIONS],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("size (épaisseur de la poignée)"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="split",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-md",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-split",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Editor split",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="height: 240px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=split",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Tirez la poignée",
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
    with ui.resizable(**kwargs):
        for i in range(state.panels):
            tint = TINTS[i % len(TINTS)]
            with ui.resizable_panel(min_size=state.min_size):
                with ui.flex(justify="center", align="center",
                             classes=f"h-40 w-full bg-(--bz-bg) bz-c-{tint}"):
                    ui.heading(str(i + 1), level=3, color=tint)

    ui.divider()

    preview = ui.resizable(**kwargs)
    with preview:
        with ui.resizable_panel(min_size=state.min_size):
            ui.text("A")
        with ui.resizable_panel():
            ui.text("B")
    emitted_html_block(
        "Emitted HTML (Resizable + ses panneaux + la poignée dérivée)",
        serialize_html(preview),
    )


@refreshable(deps=[ResizableEvents])
def events_panel() -> None:
    state = ResizableEvents()

    ui.text(
        "Resizable émet UN ``change`` au relâchement de la poignée, "
        "jamais pendant le geste — sinon c'est un POST par pixel. "
        "Tirez la poignée ci-dessous et lâchez : une seule ligne "
        "apparaît dans le log, avec la liste complète des poids.",
        color="muted", size="sm",
    )

    split_state = ResizableServerEvents()
    with ui.vstack():
        with ui.resizable(sizes=split_state.split,
                          on_change=log_change) as group:
            panel_block(0, height="h-28")
            panel_block(1, height="h-28")

        with ui.hstack(gap="sm"):
            ui.button("20 / 80", variant="outline",
                      on_click=group.set([20, 80]))
            ui.button("Parts égales", on_click=group.reset())

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
        ui.text("(no events yet — tirez la poignée ci-dessus)",
                color="muted", size="sm")

    ui.divider()

    ui.text(
        "L'autoname couvre le cas lié (``sizes=state.split`` dérive "
        "``name=\"split\"``) — c'est le groupe ci-dessus. Pour un groupe "
        "à valeur LITTÉRALE qui doit quand même poster son partage, "
        "``name=`` est l'échappatoire, et le SEUL moyen : sans l'un ni "
        "l'autre le composant ne pose aucun ``name``, donc le handler "
        "part avec une FormData vide et reçoit ``sizes=''``. C'est "
        "délibéré au socle — un ``name`` par défaut injecterait un champ "
        "parasite dans chaque formulaire englobant.",
        color="muted", size="sm",
    )
    with ui.resizable(name="chosen_split", on_change=log_change):
        panel_block(0, height="h-20")
        panel_block(1, height="h-20")

    ui.divider()

    representative = ui.resizable(on_change=log_change)
    with representative:
        with ui.resizable_panel():
            ui.text("A")
        with ui.resizable_panel():
            ui.text("B")
    emitted_html_block(
        "Emitted HTML (Resizable with on_change handler)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Resizable", level=1)
        ui.text(
            "Des panneaux qui se repartagent leur place, séparés par "
            "des poignées dérivées. Le partage vit en POIDS, pas en "
            "pixels : le groupe garde ses proportions quand il "
            "rétrécit, sans écouter le moindre resize. Ce n'est PAS "
            "la boîte à poignée de coin — celle-là, le CSS la fait "
            "nativement avec resize: both.",
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic (parts égales)", level=3)
            with ui.resizable():
                panel_block(0)
                panel_block(1)

            ui.heading("sizes", level=3)
            ui.text(
                "Une liste de poids. [1, 3] et [25, 75] donnent la "
                "même chose — c'est le RAPPORT qui compte, pas "
                "l'unité.",
                color="muted", size="xs",
            )
            for split in ([50, 50], [25, 75], [70, 30], [20, 60, 20]):
                ui.text(f"sizes={split}", color="muted", size="xs")
                with ui.resizable(sizes=split):
                    for i in range(len(split)):
                        panel_block(i, height="h-24")

            ui.heading("orientation", level=3)
            ui.text(
                "horizontal = panneaux CÔTE À CÔTE, donc une barre "
                "verticale. Le nom décrit la disposition du groupe, "
                "pas celle de la barre.",
                color="muted", size="xs",
            )
            for o in ORIENTATIONS:
                ui.text(f"orientation={o}", color="muted", size="xs")
                with ui.resizable(orientation=o, style="height: 200px"):
                    panel_block(0, height="h-full")
                    panel_block(1, height="h-full")

            ui.heading("Sizes (épaisseur de la poignée)", level=3)
            for s in SIZES:
                ui.text(f"size={s}", color="muted", size="xs")
                with ui.resizable(size=s):
                    panel_block(0, height="h-20")
                    panel_block(1, height="h-20")

            ui.heading("Colors (survol + appui + anneau de focus)",
                       level=3)
            for c in COLORS:
                with ui.resizable(color=c):
                    panel_block(0, height="h-16")
                    panel_block(1, height="h-16")

            ui.heading("disabled", level=3)
            ui.text(
                "La poignée reste DESSINÉE — elle sépare toujours "
                "quelque chose — mais sort du tab order, porte "
                "aria-disabled et le curseur interdit.",
                color="muted", size="xs",
            )
            with ui.resizable(disabled=True):
                panel_block(0, height="h-24")
                panel_block(1, height="h-24")

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                "Un seul sous-composant : ui.resizable_panel. Les "
                "poignées, elles, ne se déclarent pas — il y en a "
                "exactement une de moins que de panneaux, donc les "
                "écrire n'ajouterait qu'une occasion de se tromper.",
                color="muted", size="sm",
            )

            ui.heading("min_size — le butoir", level=3)
            ui.text(
                "Le premier panneau ne descend pas sous 30 %, le "
                "second pas sous 20 %. Tirez : la poignée bute.",
                color="muted", size="xs",
            )
            with ui.resizable():
                with ui.resizable_panel(min_size=30):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-primary/15"):
                        ui.text("min_size=30")
                with ui.resizable_panel(min_size=20):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-success/15"):
                        ui.text("min_size=20")

            ui.heading("max_size — le plafond", level=3)
            ui.text(
                "Le jumeau symétrique de min_size, dans la même unité : "
                "des points de pourcentage. Le premier panneau ne "
                "dépasse pas 45 %, quoi qu'on tire.",
                color="muted", size="xs",
            )
            with ui.resizable():
                with ui.resizable_panel(min_size=20, max_size=45):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-primary/15"):
                        ui.text("20 % ≤ moi ≤ 45 %")
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-success/15"):
                        ui.text("le reste")

            ui.heading("collapsible — ranger un panneau", level=3)
            ui.text(
                "Double-cliquez la poignée (ou Entrée quand elle a le "
                "focus) : le panneau se range et rend sa place au "
                "voisin. Recommencez pour le récupérer à sa taille "
                "d'avant. Le repli passe outre min_size — c'est un "
                "geste explicite, pas un glissement qui dérape.",
                color="muted", size="xs",
            )
            with ui.resizable(gap="sm"):
                with ui.resizable_panel(min_size=25, collapsible=True):
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-primary/15"):
                        ui.text("range-moi")
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-32 w-full bg-success/15"):
                        ui.text("je prends la place")

            ui.heading("gap — la gouttière autour de la poignée", level=3)
            ui.text(
                "La même échelle à six crans que ui.flex / ui.hstack / "
                "ui.grid, parce que c'est le même espace. Elle appartient "
                "au GROUPE : le padding d'un parent ne peut pas créer "
                "d'espace à l'intérieur, entre un panneau et la poignée.",
                color="muted", size="xs",
            )
            with ui.resizable(gap="lg"):
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-24 w-full rounded-xl "
                                         "bg-primary/15"):
                        ui.text("gap=lg")
                with ui.resizable_panel():
                    with ui.flex(justify="center", align="center",
                                 classes="h-24 w-full rounded-xl "
                                         "bg-success/15"):
                        ui.text("24 px de chaque côté")

            ui.heading("Panneaux riches", level=3)
            with ui.resizable(sizes=[35, 65], style="height: 260px"):
                with ui.resizable_panel(min_size=20):
                    with ui.vstack(gap="sm", classes="p-4"):
                        ui.heading("Projets", level=3)
                        for name, icon in (("Aurora", "rocket"),
                                           ("Borealis", "telescope"),
                                           ("Cascade", "archive")):
                            with ui.hstack(gap="sm", align="center"):
                                ui.icon(icon, size="sm", color="primary")
                                ui.text(name)
                with ui.resizable_panel():
                    with ui.vstack(gap="sm", classes="p-4"):
                        ui.heading("Aurora", level=3)
                        ui.text("Le projet principal.", color="muted")
                        ui.button("Ouvrir", variant="outline", size="sm")

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Un seul panneau", level=3)
            ui.text("Aucune poignée : il n'y a rien à repartager.",
                    color="muted", size="xs")
            with ui.resizable():
                panel_block(0, height="h-20")

            ui.heading("Aucun panneau", level=3)
            ui.text("Un groupe vide — pas une erreur.",
                    color="muted", size="xs")
            ui.resizable()

            ui.heading("sizes plus court que le nombre de panneaux",
                       level=3)
            ui.text(
                "Complété à parts égales, jamais levé : les panneaux "
                "viennent souvent des données, donc leur nombre "
                "change sans que la valeur persistée l'ait su.",
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[50]):
                for i in range(3):
                    panel_block(i, height="h-20")

            ui.heading("sizes absurde (négatif, texte)", level=3)
            ui.text("Chaque entrée cassée retombe à part égale, "
                    "panneau par panneau — aucun ne disparaît.",
                    color="muted", size="xs")
            with ui.resizable(sizes=[-10, "nope", 40]):
                for i in range(3):
                    panel_block(i, height="h-20")

            ui.heading("Deux minimums qui ne tiennent pas", level=3)
            ui.text(
                "60 + 60 > 100 : la poignée se fige au lieu de "
                "violer l'un des deux.",
                color="muted", size="xs",
            )
            with ui.resizable():
                with ui.resizable_panel(min_size=60):
                    with ui.flex(justify="center", align="center",
                                 classes="h-20 w-full bg-error/15"):
                        ui.text("min 60")
                with ui.resizable_panel(min_size=60):
                    with ui.flex(justify="center", align="center",
                                 classes="h-20 w-full bg-warning/15"):
                        ui.text("min 60")

            ui.heading("Contenu très large dans un panneau étroit",
                       level=3)
            ui.text(
                "Le test de min-w-0 : le panneau doit RÉTRÉCIR sous "
                "la largeur de son contenu, pas s'y arc-bouter.",
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[20, 80]):
                with ui.resizable_panel():
                    ui.text("UnMotTrèsLongQuiNeVeutPasSeCouperDuTout",
                            classes="whitespace-nowrap")
                with ui.resizable_panel():
                    ui.text("voisin", color="muted")

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text("Resizable dans ses contextes habituels.",
                    color="muted", size="sm")

            ui.heading("Imbriqué (colonne + split vertical)", level=3)
            ui.text(
                "Le cas « éditeur / aperçu » : un groupe vertical "
                "DANS un panneau d'un groupe horizontal. Chacun a "
                "son scope, et le ``:scope >`` du runtime garantit "
                "que le parent ne voit pas les panneaux de l'enfant.",
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[30, 70], style="height: 300px"):
                panel_block(0, height="h-full")
                with ui.resizable_panel():
                    with ui.resizable(orientation="vertical",
                                      classes="h-full"):
                        panel_block(1, height="h-full")
                        panel_block(2, height="h-full")

            ui.heading("Un enfant NU devient un panneau", level=3)
            ui.text(
                "Chaque enfant direct est un panneau — ui.resizable_panel "
                "n'est pas un péage, c'est l'opt-in pour donner un "
                "min_size. C'est ce qui fait qu'un @refreshable ou un "
                "ui.fragment composent sans cérémonie : leurs nœuds "
                "s'attachent au parent courant comme n'importe quel "
                "composant, et une version qui les refusait rendait le "
                "groupe inutilisable avec eux.",
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[40, 60]):
                ui.text("enfant nu, sans resizable_panel",
                        classes="p-4 bg-info/10")
                with ui.resizable_panel(min_size=25):
                    with ui.flex(justify="center", align="center",
                                 classes="h-24 w-full bg-success/15"):
                        ui.text("panneau déclaré (min_size=25)")

            ui.heading("Dans une cellule de grille (contexte contraint)",
                       level=3)
            ui.text(
                "Le test qui compte : un groupe dans une colonne "
                "étroite ne doit ni déborder ni pousser la page.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.card(), ui.resizable(size="sm"):
                    panel_block(0, height="h-24")
                    panel_block(1, height="h-24")
                ui.text("Cellule voisine.", color="muted")
                ui.text("Autre voisine.", color="muted")

            ui.heading("Deux groupes indépendants", level=3)
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.resizable(color="success"):
                    panel_block(0, height="h-24")
                    panel_block(1, height="h-24")
                with ui.resizable(color="error"):
                    panel_block(2, height="h-24")
                    panel_block(3, height="h-24")

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "Chaque poignée est un role=\"separator\" focusable "
                "portant aria-valuenow / valuemin / valuemax et un "
                "aria-controls vers le panneau qu'elle "
                "redimensionne. Les flèches ← → (ou ↑ ↓ en vertical) "
                "la déplacent par pas de 2 points : une poignée qui "
                "n'obéit qu'au pointeur est inutilisable sans "
                "souris. ⚠️ L'aria-orientation déclarée est celle de "
                "la BARRE, donc l'INVERSE de celle du groupe — c'est "
                "la confusion classique du motif.",
                color="muted", size="sm",
            )
            with ui.resizable(aria_label="Demo split"):
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every Resizable prop AND every escape hatch is "
                "wired to a control ; the preview AND the emitted "
                "HTML both refresh on every change.",
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
                "Mirror of Resizable's BINDABLE_PROPS = ('sizes',). "
                "Le partage est lié à un ClientState : tirer la "
                "poignée le remonte, et les boutons l'écrivent — "
                "sans aller-retour.",
                color="muted", size="sm",
            )
            client = ResizableClient()
            with ui.hstack(gap="sm"):
                ui.button("30 / 70", variant="outline", size="sm",
                          on_click=client.split.set([30, 70]))
                ui.button("50 / 50", variant="outline", size="sm",
                          on_click=client.split.set([50, 50]))
                ui.button("80 / 20", variant="outline", size="sm",
                          on_click=client.split.set([80, 20]))

            ui.divider()

            with ui.resizable(sizes=client.split):
                panel_block(0)
                panel_block(1)

            ui.text(
                ClientExpression(
                    "'poids courants : ' + JSON.stringify("
                    "$bz.state.ResizableClient.default.split ?? [])"
                ),
                color="muted", size="sm", classes="font-mono",
            )

            ui.divider()

            ui.heading("Persistance — persist=\"local\"", level=3)
            ui.text(
                "Le cas d'usage qui a mis ce composant sur la "
                "roadmap. Tirez la poignée, rechargez la page (F5) : "
                "le partage est là. Aucun prop de persistance sur le "
                "composant — c'est le ClientState qui le décide, et "
                "il n'y a pas de flash au chargement (la racine "
                "porte un bz-data, donc elle attend html.bz-ready, "
                "que le boot ne pose qu'APRÈS avoir relu "
                "localStorage).",
                color="muted", size="sm",
            )
            remembered = ResizableRemembered()
            with ui.resizable(sizes=remembered.split):
                panel_block(2, height="h-28")
                panel_block(3, height="h-28")

            ui.divider()

            preview = ui.resizable(sizes=client.split)
            with preview:
                with ui.resizable_panel():
                    ui.text("A")
                with ui.resizable_panel():
                    ui.text("B")
            emitted_html_block(
                "Emitted HTML — les directives lisent la cellule du "
                "store directement ; les panneaux se reposent quand "
                "elle bouge, et le geste la remonte au relâchement.",
                serialize_html(preview),
            )

        # ── Card 9 — External controls — the 3 modes ────────────
        with ui.card(), ui.vstack():
            ui.heading("External controls — the 3 modes", level=2)
            ui.text(
                ".reset() dispatche TOUJOURS un event DOM, binding "
                "ou pas : la part égale dépend du NOMBRE de "
                "panneaux vivants, que le serveur ne connaît plus "
                "après un morph qui en a ajouté. .set([…]) écrit "
                "dans la binding quand il y en a une.",
                color="muted", size="sm",
            )

            ui.heading("Mode 1 — Imperative only (default)", level=3)
            with ui.resizable() as m1:
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")
            with ui.hstack(gap="sm"):
                ui.button("20 / 80", variant="outline",
                          on_click=m1.set([20, 80]))
                ui.button("80 / 20", variant="outline",
                          on_click=m1.set([80, 20]))
                ui.button("Parts égales", variant="ghost",
                          on_click=m1.reset())

            ui.divider()

            ui.heading("Mode 2 — ClientBinding only", level=3)
            ui.text(
                "À utiliser quand un AUTRE composant doit lire le "
                "partage — un compteur, un panneau qui se replie "
                "quand sa part descend trop bas.",
                color="muted", size="sm",
            )
            bound = ResizableClient(key="binding_only")
            with ui.resizable(sizes=bound.split):
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")
            ui.text(
                ClientExpression(
                    "'gauche : ' + Math.round(("
                    "$bz.state.ResizableClient.binding_only.split "
                    "?? [50])[0]) + ' %'"
                ),
                color="muted", size="sm",
            )

            ui.divider()

            ui.heading("Mode 3 — Both (write-through)", level=3)
            both = ResizableClient(key="both")
            with ui.resizable(sizes=both.split) as m3:
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")
            with ui.hstack(gap="sm", align="center"):
                ui.button("25 / 75", variant="outline",
                          on_click=m3.set([25, 75]))
                ui.button("Parts égales", on_click=m3.reset())
                ui.text(
                    ClientExpression(
                        "'bound = ' + JSON.stringify("
                        "$bz.state.ResizableClient.both.split ?? [])"
                    ),
                    color="muted", size="sm", classes="font-mono",
                )

            ui.divider()

            imperative_preview = ui.resizable(sizes=both.split)
            with imperative_preview:
                with ui.resizable_panel():
                    ui.text("A")
                with ui.resizable_panel():
                    ui.text("B")
            emitted_html_block(
                "Emitted HTML — la root porte bz-on:bz-set et "
                "bz-on:bz-reset, les deux récepteurs vers lesquels "
                "les méthodes impératives dispatchent.",
                serialize_html(imperative_preview),
            )

        # ── Card 10 — Client events ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text("change wired to a client expression that pushes "
                    "the new split onto a ClientState list. Zero "
                    "network.",
                    color="muted", size="sm")
            cevents = ResizableClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.resizable(on_change=cevents.log.push(_new_value)):
                panel_block(0, height="h-28")
                panel_block(1, height="h-28")

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            log_text = ClientExpression(
                '($bz.state.ResizableClientEvents.default.log'
                ' || []).join("\\n") || "(no events yet)"'
            )
            ui.text(log_text,
                    color="muted", size="sm",
                    classes="font-mono whitespace-pre")

            ui.divider()

            preview = ui.resizable(
                on_change=cevents.log.push(_new_value),
            )
            with preview:
                with ui.resizable_panel():
                    ui.text("A")
                with ui.resizable_panel():
                    ui.text("B")
            emitted_html_block(
                "Emitted HTML — le handler bz-on:change est "
                "relocalisé sur l'input caché, dont le bz-effect "
                "re-tire un change à chaque relâchement de poignée.",
                serialize_html(preview),
            )

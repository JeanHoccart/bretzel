"""``Carousel`` test bench.

Ten visual cards. ``Carousel.BINDABLE_PROPS = ("value",)`` — the current
slide index is bindable ; per_view / autoplay / gap / size / color stay
design-time. Event : ``change``. Imperative API : ``.set(i)`` /
``.next()`` / ``.prev()``.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/carousel"


SIZES  = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]
GAPS   = ["none", "xs", "sm", "md", "lg", "xl"]

# Contenu de slide réutilisé partout : un bloc coloré numéroté, assez
# grand pour qu'on voie où on est.
TINTS = ["primary", "success", "warning", "error", "info",
         "secondary", "muted"]


def slide_block(index: int, height: str = "h-40") -> None:
    """Une slide de démo — un bloc teinté qui porte son numéro.

    Au scope module parce qu'elle sert dans neuf cards ; c'est le seuil
    du gabarit (une expression inline de 3 lignes reste inline, un bloc
    répété neuf fois devient une fonction).
    """
    tint = TINTS[index % len(TINTS)]
    # ⚠️ ``bz-c-<teinte>`` + le PALIER, et surtout PAS un
    # ``f"bg-{tint}/15"``. Une classe assemblée n'existe que sous le
    # compilateur de dev, qui scanne le DOM vivant ; en prod le
    # compilateur ne lit que les sources, il ne verra jamais
    # ``bg-info/15``. C'était rattrapé jusqu'ici par la clôture couleur
    # de la safelist — qui n'existe plus depuis la phase 3 du chantier
    # des jetons. Le pont, lui, est une classe complète.
    with ui.flex(justify="center", align="center",
                 classes=f"{height} w-full rounded-xl bg-(--bz-bg) "
                         f"bz-c-{tint}"):
        ui.heading(str(index + 1), level=3, color=tint)


class CarouselPlayground(PageState):
    value:    int = field(default=0)
    per_view: int = field(default=1)
    autoplay: str = field(default="")
    gap:      str = field(default="md")
    size:     str = field(default="md")
    color:    str = field(default="primary")
    name:     str = field(default="")
    slides:   int = field(default=5)
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class CarouselEvents(PageState):
    log: list = field(default_factory=list)


class CarouselClient(ClientState, persist="memory"):
    slide: int = field(default=0)


class CarouselClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


class CarouselServerEvents(ClientState, persist="memory"):
    slide: int = field(default=0)


def log(name: str) -> None:
    state = CarouselEvents()
    state.log = [*state.log, name]


def log_change(slide: str = "") -> None:
    log(f"change(slide={slide!r})")


def clear_log() -> None:
    state = CarouselEvents()
    state.log = []


def server_changed(state: CarouselPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted).
    pass


def playground_change_handler(slide: str = "") -> None:
    log(f"playground-server-change(slide={slide!r})")


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


def build_preview(state: CarouselPlayground) -> dict:
    kwargs: dict = {
        "value": state.value,
        "per_view": state.per_view,
        "gap": state.gap,
        "size": state.size,
        "color": state.color,
    }
    # Chaîne vide = ne pas passer le kwarg (autoplay=None = éteint).
    if state.autoplay:
        kwargs["autoplay"] = float(state.autoplay)
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


@refreshable(deps=[CarouselPlayground])
def server_panel() -> None:
    state = CarouselPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("value (index de la slide)"):
            ui.select(value=state.value,
                      options=[(i, str(i)) for i in range(8)],
                      on_change=server_changed)
        with control("slides (combien en rendre)"):
            ui.select(value=state.slides,
                      options=[(i, str(i)) for i in (1, 2, 3, 5, 8)],
                      on_change=server_changed)
        with control("per_view"):
            ui.select(value=state.per_view,
                      options=[(i, str(i)) for i in (1, 2, 3, 4)],
                      on_change=server_changed)
        with control("autoplay (secondes, vide = éteint)"):
            ui.select(value=state.autoplay,
                      options=[("", "None (éteint)"), ("1", "1 s"),
                               ("2", "2 s"), ("5", "5 s")],
                      on_change=server_changed)
        with control("gap"):
            ui.select(value=state.gap,
                      options=[(g, g) for g in GAPS],
                      on_change=server_changed)
        with control("size (flèches + puces)"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="slide",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-md",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-carousel",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Photos",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 480px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=carousel",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Faites défiler",
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
    with ui.carousel(**kwargs):
        for i in range(state.slides):
            slide_block(i)

    ui.divider()

    preview = ui.carousel(**kwargs)
    with preview:
        for i in range(2):
            ui.text(f"slide {i}")
    emitted_html_block(
        "Emitted HTML (Carousel + ses slides)",
        serialize_html(preview),
    )


@refreshable(deps=[CarouselEvents])
def events_panel() -> None:
    state = CarouselEvents()

    ui.text(
        "Carousel fires a single ``change`` when the current index "
        "settles — l'écriture est débouncée à 120 ms, donc un "
        "défilement de 0 à 3 émet UN change (3) et non trois. Faites "
        "défiler à la main, cliquez une puce, ou utilisez les boutons.",
        color="muted", size="sm",
    )

    slide_state = CarouselServerEvents()
    with ui.vstack():
        with ui.carousel(value=slide_state.slide,
                         on_change=log_change) as car:
            for i in range(4):
                slide_block(i, height="h-28")

        with ui.hstack(gap="sm"):
            ui.button("Précédent", variant="outline", on_click=car.prev())
            ui.button("Suivant", on_click=car.next())

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
        ui.text("(no events yet — faites défiler le carousel ci-dessus)",
                color="muted", size="sm")

    ui.divider()

    ui.text(
        "L'autoname couvre le cas lié (``value=state.slide`` dérive "
        "``name=\"slide\"``). Pour un carousel à valeur littérale qui "
        "doit quand même poster son index, ``name=`` reste l'échappatoire "
        "— c'est le seul moyen d'avoir un porteur de formulaire sans "
        "binding.",
        color="muted", size="sm",
    )
    with ui.carousel(name="chosen_slide", on_change=log_change):
        for i in range(3):
            slide_block(i, height="h-20")

    ui.divider()

    representative = ui.carousel(value=slide_state.slide,
                                 on_change=log_change)
    with representative:
        ui.text("A")
        ui.text("B")
    emitted_html_block(
        "Emitted HTML (Carousel with on_change handler)",
        serialize_html(representative),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Carousel", level=1)
        ui.text(
            "Défilement aimanté d'une série de contenus. Chaque "
            "enfant direct EST une slide — rien à déclarer, et ça "
            "compose avec ui.each sans cérémonie. Le moteur est du "
            "CSS scroll-snap : le swipe tactile avec inertie, la "
            "molette et le clavier sont ceux du navigateur.",
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            with ui.carousel():
                for i in range(5):
                    slide_block(i)

            ui.heading("per_view", level=3)
            ui.text(
                "Les puces disparaissent dès que per_view > 1 : "
                "une puce dit « il y a N slides, tu es à la "
                "k-ième », ce qui n'a plus de référent quand on "
                "en voit trois à la fois.",
                color="muted", size="xs",
            )
            for n in (1, 2, 3, 4):
                ui.text(f"per_view={n}", color="muted", size="xs")
                with ui.carousel(per_view=n):
                    for i in range(8):
                        slide_block(i, height="h-28")

            ui.heading("gap", level=3)
            for g in GAPS:
                ui.text(f"gap={g}", color="muted", size="xs")
                with ui.carousel(per_view=3, gap=g):
                    for i in range(6):
                        slide_block(i, height="h-20")

            ui.heading("Sizes (flèches + puces)", level=3)
            for s in SIZES:
                ui.text(f"size={s}", color="muted", size="xs")
                with ui.carousel(size=s):
                    for i in range(3):
                        slide_block(i, height="h-24")

            ui.heading("Colors (puce active + anneau de focus)",
                       level=3)
            for c in COLORS:
                with ui.carousel(color=c):
                    for i in range(3):
                        slide_block(i, height="h-20")

            ui.heading("autoplay", level=3)
            ui.text(
                "Avance toutes les 2 s, et s'arrête "
                "DÉFINITIVEMENT au premier geste — un doigt sur "
                "la piste, la molette, une flèche ou une puce.",
                color="muted", size="xs",
            )
            with ui.carousel(autoplay=2):
                for i in range(4):
                    slide_block(i)

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                "Il n'y a pas de ui.slide() : chaque enfant "
                "direct est une slide, le carousel l'enveloppe "
                "lui-même. Une slide à plusieurs éléments se "
                "fait avec un vstack, comme partout ailleurs.",
                color="muted", size="sm",
            )

            ui.heading("Slides riches", level=3)
            with ui.carousel(per_view={"base": 1, "md": 2}):
                for title, body, icon in (
                    ("Aurora", "Le projet principal", "rocket"),
                    ("Borealis", "En revue", "telescope"),
                    ("Cascade", "Archivé", "archive"),
                    ("Delta", "Brouillon", "pencil"),
                ):
                    with ui.card(), ui.vstack(gap="sm"):
                        ui.icon(icon, size="lg", color="primary")
                        ui.heading(title, level=3)
                        ui.text(body, color="muted", size="sm")
                        ui.button("Ouvrir", variant="outline",
                                  size="sm")

            ui.heading("Composé avec ui.each", level=3)
            ui.text(
                "Le cas d'usage numéro un, et la raison des "
                "slides implicites : zéro ligne de cérémonie "
                "dans la boucle.",
                color="muted", size="xs",
            )
            with ui.carousel(per_view=3, gap="sm"):
                for label in ui.each(
                    ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
                ):
                    with ui.flex(justify="center", align="center",
                                 classes="h-20 w-full rounded-lg "
                                         "bg-primary/10"):
                        ui.text(label, weight="medium")

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Une seule slide", level=3)
            ui.text(
                "Aucun contrôle rendu : il n'y a nulle part où "
                "aller. Le cas arrive pour de vrai, le contenu "
                "venant des données.",
                color="muted", size="xs",
            )
            with ui.carousel():
                slide_block(0)

            ui.heading("Autant de slides que per_view", level=3)
            ui.text("Idem — tout tient à l'écran, rien à piloter.",
                    color="muted", size="xs")
            with ui.carousel(per_view=3):
                for i in range(3):
                    slide_block(i, height="h-24")

            ui.heading("Beaucoup de slides (20 puces)", level=3)
            ui.text(
                "La limite connue du choix « une puce par "
                "slide » : au-delà d'une dizaine la rangée "
                "devient une barre. À regarder ici pour "
                "décider s'il faut la plafonner.",
                color="muted", size="xs",
            )
            with ui.carousel():
                for i in range(20):
                    slide_block(i, height="h-24")

            ui.heading("Slides de hauteurs inégales", level=3)
            with ui.carousel():
                slide_block(0, height="h-24")
                slide_block(1, height="h-48")
                slide_block(2, height="h-32")

            ui.heading("value au-delà de la dernière slide",
                       level=3)
            ui.text("Clampé à la borne réelle par le runtime.",
                    color="muted", size="xs")
            with ui.carousel(value=99):
                for i in range(4):
                    slide_block(i, height="h-24")

            ui.heading("Aucune slide", level=3)
            ui.text("Une piste vide, sans contrôle — pas une erreur.",
                    color="muted", size="xs")
            ui.carousel()

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text("Carousel dans ses contextes habituels.",
                    color="muted", size="sm")

            ui.heading("Dans une Card étroite (contexte contraint)",
                       level=3)
            ui.text(
                "Le test qui compte : une piste scrollable dans "
                "une cellule de grille ne doit pas déborder de "
                "sa colonne ni pousser la page.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.card(), ui.carousel(size="sm"):
                    for i in range(4):
                        slide_block(i, height="h-24")
                ui.text("Cellule voisine.", color="muted")
                ui.text("Autre voisine.", color="muted")

            ui.heading("Dans un ui.dialog", level=3)
            with ui.dialog(title="Galerie", width="lg") as dlg, \
                            ui.vstack():
                with ui.carousel() as gal:
                    for i in range(4):
                        slide_block(i)
                ui.button("Suivante", on_click=gal.next())
            ui.button("Ouvrir la galerie", on_click=dlg.open())

            ui.heading("Deux carousels indépendants", level=3)
            ui.text(
                "Chacun a son propre scope : faire défiler l'un "
                "ne doit pas bouger l'autre.",
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 2}, gap="md"):
                with ui.carousel(color="success"):
                    for i in range(4):
                        slide_block(i, height="h-24")
                with ui.carousel(color="error"):
                    for i in range(4):
                        slide_block(i + 2, height="h-24")

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "La root porte role=\"group\" + "
                "aria-roledescription=\"carousel\" (c'est elle "
                "qui contient AUSSI les contrôles). Les flèches "
                "et les puces sont de vrais <button> étiquetés, "
                "donc dans le tab order et activables au "
                "clavier ; aux bords la flèche est réellement "
                "disabled, pas seulement grisée. Les puces ne "
                "prétendent PAS être un tablist : déclarer la "
                "moitié du motif ARIA « carousel à onglets » "
                "annoncerait une structure qui n'existe pas.",
                color="muted", size="sm",
            )
            with ui.carousel(aria_label="Demo carousel"):
                for i in range(4):
                    slide_block(i, height="h-28")

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every Carousel prop AND every escape hatch is "
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
                "Mirror of Carousel's BINDABLE_PROPS = "
                "('value',). L'index est lié à un ClientState : "
                "le select le pilote, et faire défiler la piste "
                "le remonte — sans aller-retour.",
                color="muted", size="sm",
            )
            client = CarouselClient()
            with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                with control("value (bound)"):
                    ui.select(value=client.slide,
                              options=[(i, str(i))
                                       for i in range(4)])

            ui.divider()

            with ui.carousel(value=client.slide):
                for i in range(4):
                    slide_block(i)

            ui.text(
                ClientExpression(
                    "'index courant : ' + "
                    "($bz.state.CarouselClient.default.slide ?? 0)"
                ),
                color="muted", size="sm", classes="font-mono",
            )

            ui.divider()

            preview = ui.carousel(value=client.slide)
            with preview:
                ui.text("A")
                ui.text("B")
            emitted_html_block(
                "Emitted HTML — les directives lisent la cellule "
                "du store directement ; la piste défile quand "
                "elle bouge, et la remonte quand l'utilisateur "
                "fait défiler.",
                serialize_html(preview),
            )

        # ── Card 9 — External controls — the 3 modes ────────────
        with ui.card(), ui.vstack():
            ui.heading("External controls — the 3 modes", level=2)
            ui.text(
                ".next() et .prev() dispatchent TOUJOURS un "
                "event DOM, binding ou pas : leur destination "
                "dépend de la géométrie vivante — combien de "
                "slides tiennent à l'écran au breakpoint "
                "courant — que le serveur ne connaît pas au "
                "rendu. .set(i) écrit dans la binding quand il "
                "y en a une.",
                color="muted", size="sm",
            )

            ui.heading("Mode 1 — Imperative only (default)",
                       level=3)
            with ui.carousel() as m1:
                for i in range(5):
                    slide_block(i, height="h-28")
            with ui.hstack(gap="sm"):
                ui.button("Précédent", variant="outline",
                          on_click=m1.prev())
                ui.button("Suivant", on_click=m1.next())
                ui.button("Début", variant="ghost",
                          on_click=m1.set(0))

            ui.divider()

            ui.heading("Mode 2 — ClientBinding only", level=3)
            ui.text(
                "À utiliser quand un AUTRE composant doit lire "
                "la position — un compteur, un titre qui suit "
                "la slide.",
                color="muted", size="sm",
            )
            bound = CarouselClient(key="binding_only")
            with ui.carousel(value=bound.slide):
                for i in range(5):
                    slide_block(i, height="h-28")
            ui.text(
                ClientExpression(
                    "'slide ' + "
                    "(($bz.state.CarouselClient.binding_only.slide "
                    "?? 0) + 1) + ' sur 5'"
                ),
                color="muted", size="sm",
            )

            ui.divider()

            ui.heading("Mode 3 — Both (write-through)", level=3)
            both = CarouselClient(key="both")
            with ui.carousel(value=both.slide) as m3:
                for i in range(5):
                    slide_block(i, height="h-28")
            with ui.hstack(gap="sm", align="center"):
                ui.button("Précédent", variant="outline",
                          on_click=m3.prev())
                ui.button("Suivant", on_click=m3.next())
                ui.button("Aller à 3", variant="ghost",
                          on_click=m3.set(2))
                ui.text(
                    ClientExpression(
                        "'bound = ' + "
                        "($bz.state.CarouselClient.both.slide ?? 0)"
                    ),
                    color="muted", size="sm",
                    classes="font-mono",
                )

            ui.divider()

            imperative_preview = ui.carousel(value=both.slide)
            with imperative_preview:
                ui.text("A")
                ui.text("B")
            emitted_html_block(
                "Emitted HTML — la root porte bz-on:bz-set / "
                "bz-next / bz-prev, les trois récepteurs vers "
                "lesquels les méthodes impératives dispatchent.",
                serialize_html(imperative_preview),
            )

        # ── Card 10 — Client events ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text("change wired to a client expression that "
                    "pushes the new index onto a ClientState "
                    "list. Zero network.",
                    color="muted", size="sm")
            cevents = CarouselClientEvents()
            _new_value = ClientExpression("$event.target.value")
            with ui.carousel(on_change=cevents.log.push(_new_value)):
                for i in range(4):
                    slide_block(i, height="h-28")

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            log_text = ClientExpression(
                '($bz.state.CarouselClientEvents.default.log'
                ' || []).join("\\n") || "(no events yet)"'
            )
            ui.text(log_text,
                    color="muted", size="sm",
                    classes="font-mono whitespace-pre")

            ui.divider()

            preview = ui.carousel(
                on_change=cevents.log.push(_new_value),
            )
            with preview:
                ui.text("A")
                ui.text("B")
            emitted_html_block(
                "Emitted HTML — le handler bz-on:change est "
                "relocalisé sur l'input caché, dont le "
                "bz-effect re-tire un change à chaque fois que "
                "la position s'arrête.",
                serialize_html(preview),
            )

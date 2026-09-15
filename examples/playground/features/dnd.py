"""``Dropzone`` / ``Draggable`` / ``drag_each`` test bench.

Suit le gabarit de ``.claude/bretzel/playground-pattern.md``. Sections
applicables : §1 Reference, §2 Edge cases / Composability / A11y (pas de
`Slots` — la famille n'a aucun slot nommé), §3 Server playground,
§4 Server events, §6 Client events. **Pas de §5** (`BINDABLE_PROPS` est
vide des deux côtés : une zone ne porte aucune valeur) ni de §7 (aucune
API impérative).

Ce que cette page exerce et qu'aucune autre du playground n'exerce : la
boucle optimiste complète — le navigateur bouge la carte AVANT toute
requête, le drop poste un ``Move``, le handler mute ou refuse, et le
morph réapparie le nœud déplacé au lieu de le recréer. Le refus n'a
aucun chemin de code à lui : la carte qui revient, c'est le rendu serveur
qui contredit le DOM optimiste.
"""

from bretzel import refreshable, ui
from bretzel.components import Move
from bretzel.render import serialize_html
from bretzel.state import ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/dnd"

COLORS = ["primary", "secondary", "success", "warning", "error", "info", "muted"]
MOVE_MODES = ["none", "server", "client"]


# ───────────────────────────────────────────────────────────────────────
# State
# ───────────────────────────────────────────────────────────────────────


class DndPlayground(PageState):
    """§3 — un champ par prop, plus les échappatoires et modificateurs
    universels, comme le gabarit l'exige."""

    # Props Dropzone.
    name:    str = field(default="bench")
    accepts: str = field(default="")
    locked:  bool = field(default=False)
    color:   str = field(default="primary")
    # Props Draggable (portés par drag_each).
    group:    str = field(default="")
    handle:   bool = field(default=False)
    disabled: bool = field(default=False)
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
    on_move_mode: str = field(default="none")
    # Les données que le banc réordonne.
    items: list = field(default_factory=lambda: ["Alpha", "Bravo", "Charlie"])


class DndEvents(PageState):
    """§4 — le journal des events serveur."""

    log:   list = field(default_factory=list)
    items: list = field(default_factory=lambda: ["Un", "Deux", "Trois"])


class Board(PageState):
    """§2 Composability — deux zones qui s'échangent des cartes, et un
    refus serveur pour rendre le snap-back démontrable."""

    todo:    list = field(default_factory=lambda: ["Écrire la spec",
                                                   "Relire le cadrage"])
    done:    list = field(default_factory=lambda: ["Choisir les events"])
    refused: int = field(default=0)


#: La règle métier de la démo. Une CAPACITÉ, choisie parce qu'elle est
#: **réversible** : la première version refusait de sortir de « Terminé »,
#: ce qui piégeait chaque carte pour de bon — et un banc où l'on ne peut
#: pas revenir en arrière se lit comme une panne, pas comme une règle.
#: Un plafond se comprend au premier refus et se défait en sortant une
#: carte.
DONE_CAPACITY = 2


class Locked(PageState):
    """§2 Edge cases — la corbeille : accepte, ne rend rien."""

    kept: list = field(default_factory=lambda: ["Ne sort jamais"])
    free: list = field(default_factory=lambda: ["Peut partir"])


class Apercu(PageState):
    """§2 Edge cases — deux chaises, et un dépôt qui PERMUTE."""

    chaise_g: list = field(default_factory=lambda: ["Jeanne"])
    chaise_d: list = field(default_factory=lambda: ["Timéo"])


class DndClientEvents(ClientState, persist="memory"):
    """§6 — le journal client, écrit sans aucun aller-retour."""

    log: list = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────
# Handlers (module scope — adressables en ``module::qualname``)
# ───────────────────────────────────────────────────────────────────────


def apply_move(columns: dict[str, list], m: Move) -> bool:
    """Retirer d'une zone, insérer dans l'autre. Mute ``columns`` en place
    et rend ``True`` si quelque chose a bougé.

    ``to_index`` est lu du DOM APRÈS le déplacement optimiste, donc il
    désigne déjà la position finale : on retire d'abord, on insère
    ensuite, sans corriger l'index. Un réordonnancement dans une seule
    zone est le cas où ``from_zone == to_zone`` — pas un autre code.

    ⚠️ Cette fonction a porté le commentaire « écrite UNE fois » pendant
    que DEUX handlers réécrivaient le même bloc juste en dessous. C'est
    maintenant vrai : les QUATRE appelants passent par ici
    (reorder_bench, log_move, move_card, move_locked).
    """
    source, target = columns.get(m.from_zone), columns.get(m.to_zone)
    if source is None or target is None:
        return False
    if not (0 <= m.from_index < len(source)):
        return False
    target.insert(min(m.to_index, len(target)), source.pop(m.from_index))
    return True


def reorder_bench(m: Move) -> None:
    state = DndPlayground()
    columns = {m.from_zone: list(state.items)}
    if apply_move(columns, m):
        state.items = columns[m.from_zone]


def log_move(m: Move) -> None:
    state = DndEvents()
    columns = {m.from_zone: list(state.items)}
    if apply_move(columns, m):
        state.items = columns[m.from_zone]
    state.log = [
        f"move · {m.item_key} : {m.from_index} → {m.to_index}"
        f" (même zone : {m.same_zone})",
        *state.log,
    ][:8]


def move_card(m: Move) -> None:
    """Déplacement entre zones, avec un vrai refus.

    Le refus ne lève pas et n'appelle rien : il ne mute pas. Le rendu qui
    suit renvoie l'ordre d'avant, et le morph remet la carte en place.
    """
    state = Board()
    # Refuser, ici, c'est ne rien muter — pas lever, pas appeler un
    # `reject()`. Le rendu qui suit renvoie l'ordre d'avant et le morph
    # ramène la carte.
    if (m.to_zone == "done" and not m.same_zone
            and len(state.done) >= DONE_CAPACITY):
        state.refused = state.refused + 1
        return

    columns = {"todo": list(state.todo), "done": list(state.done)}
    if apply_move(columns, m):
        state.todo, state.done = columns["todo"], columns["done"]


def swap_chaise(m: Move) -> None:
    """Une zone qui contient UN élément : le dépôt PERMUTE.

    C'est le seul handler de ce fichier qui n'insère pas. Il est là pour
    ça : montrer le cas où un espace d'insertion serait un mensonge —
    rien ne se glisse entre deux voisins, quelqu'un est délogé.
    """
    state = Apercu()
    zones = {"chaise_g": list(state.chaise_g), "chaise_d": list(state.chaise_d)}
    source, cible = zones.get(m.from_zone), zones.get(m.to_zone)
    if source is None or cible is None or source is cible or not source:
        return
    occupant = cible.pop(0) if cible else None
    cible.append(source.pop(0))
    if occupant is not None:
        source.append(occupant)
    state.chaise_g, state.chaise_d = zones["chaise_g"], zones["chaise_d"]


def reset_board() -> None:
    """Remettre le banc à zéro. Un banc où un état ne se défait pas est un
    banc qu'on ne peut essayer qu'une fois."""
    state = Board()
    state.todo = ["Écrire la spec", "Relire le cadrage"]
    state.done = ["Choisir les events"]
    state.refused = 0


def move_locked(m: Move) -> None:
    state = Locked()
    columns = {"kept": list(state.kept), "free": list(state.free)}
    if apply_move(columns, m):
        state.kept, state.free = columns["kept"], columns["free"]


def server_changed(state: DndPlayground) -> None:
    """Paramètre typé — le dispatcher hydrate la valeur du contrôle
    modifié dans ``state`` (coercée + persistée). Aucun ``**kwargs``,
    aucun ``setattr``, aucun ``name=`` à poser à la main : c'est
    l'idiome de toutes les pages de banc, et un exemple reste en tier 1.""" 


def clear_log() -> None:
    DndEvents().log = []


# ───────────────────────────────────────────────────────────────────────
# Helpers de gabarit (autorisés au scope module)
# ───────────────────────────────────────────────────────────────────────


def parse_extra_attrs(blob: str) -> dict:
    """``k=v`` par ligne → dict. Les lignes sans ``=`` sont ignorées."""
    out: dict = {}
    for line in (blob or "").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key:
                out[key] = value.strip()
    return out


def control(label: str) -> object:
    """Une cellule de contrôle étiquetée : le nom du prop en gris
    au-dessus de ce que l'appelant met dans le ``with``."""
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def build_preview(state: DndPlayground) -> object:
    """State → kwargs. Une chaîne vide vaut « kwarg absent »."""
    attrs = parse_extra_attrs(state.extra_attrs)
    if state.aria_label:
        attrs["aria-label"] = state.aria_label

    kwargs: dict = {
        "name": state.name or None,
        "locked": state.locked,
        "color": state.color,
    }
    if state.accepts:
        kwargs["accepts"] = [g.strip() for g in state.accepts.split(",") if g.strip()]
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.style:
        kwargs["style"] = state.style
    if attrs:
        kwargs["attrs"] = attrs
    if state.tooltip:
        kwargs["tooltip"] = state.tooltip
    kwargs["visible"] = state.visible != "off"

    if state.on_move_mode == "server":
        kwargs["on_move"] = reorder_bench
    elif state.on_move_mode == "client":
        kwargs["on_move"] = "console.log('move')"

    zone = ui.dropzone(**kwargs)
    with zone, ui.vstack(gap="sm"):
        for label in ui.drag_each(
            state.items,
            group=state.group or None,
            handle=state.handle,
            disabled=(lambda _row: True) if state.disabled else None,
        ):
            with ui.card(padding="sm"):
                ui.text(label)
    return zone


def card(label: str) -> None:
    with ui.card(padding="sm"):
        ui.text(label)


# ───────────────────────────────────────────────────────────────────────
# §3 — Server playground
# ───────────────────────────────────────────────────────────────────────


@refreshable(deps=[DndPlayground])
def server_playground() -> None:
    state = DndPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("name"):
            ui.input(value=state.name, on_change=server_changed)
        with control("accepts"):
            ui.input(value=state.accepts, on_change=server_changed)
        with control("group"):
            ui.input(value=state.group, on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c.title()) for c in COLORS],
                      on_change=server_changed)
        with control("on_move"):
            ui.select(value=state.on_move_mode,
                      options=[(m, m.title()) for m in MOVE_MODES],
                      on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "On"), ("off", "Off")],
                      on_change=server_changed)
        with control("locked"):
            ui.switch(checked=state.locked, label="locked",
                      on_change=server_changed)
        with control("handle"):
            ui.switch(checked=state.handle, label="handle",
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, label="disabled",
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, on_change=server_changed)
        with control("custom_id"):
            ui.input(value=state.custom_id, on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, on_change=server_changed)
        with control("aria_label"):
            ui.input(value=state.aria_label, on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, on_change=server_changed)
        with control("attrs (k=v par ligne)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        on_change=server_changed)

    ui.divider()
    # Une instance VIVANTE, une pour le bloc HTML — cf. le commentaire de
    # ``client_events`` : ``serialize_html`` détache son argument.
    build_preview(state)
    emitted_html_block("Emitted HTML", serialize_html(build_preview(state)))


# ───────────────────────────────────────────────────────────────────────
# §4 — Server events
# ───────────────────────────────────────────────────────────────────────


@refreshable(deps=[DndEvents])
def server_events() -> None:
    state = DndEvents()
    with ui.dropzone(name="events", on_move=log_move), ui.vstack(gap="sm"):
        for label in ui.drag_each(state.items):
            card(label)

    ui.button("Vider le journal", on_click=clear_log, variant="ghost", size="sm")
    with ui.vstack(gap="xs"):
        for line in state.log or ["(aucun event)"]:
            ui.text(line, size="sm", color="muted")

    representative = ui.dropzone(name="sample", on_move=log_move)
    with representative:
        with ui.draggable(key="a"):
            ui.text("A")
    emitted_html_block(
        "Emitted HTML (Dropzone avec on_move serveur)",
        serialize_html(representative),
    )


# ───────────────────────────────────────────────────────────────────────
# §6 — Client events
# ───────────────────────────────────────────────────────────────────────


def client_events() -> None:
    log = DndClientEvents()

    # ⚠️ DEUX instances, et ce n'est pas de la duplication : ``serialize_html``
    # DÉTACHE ce qu'on lui donne (sa docstring le dit — sans quoi le
    # composant rendrait deux fois). Sérialiser la zone de démo la faisait
    # donc disparaître de la page : la carte n'affichait qu'un bloc de code,
    # sans rien à attraper. Le représentant est là pour le HTML, la zone
    # vivante pour le geste — c'est ce que fait déjà la carte §4.
    with ui.dropzone(name="client", on_move=log.log.push("move")):
        with ui.vstack(gap="sm"):
            for label in ui.drag_each(["Un", "Deux", "Trois"]):
                card(label)
    ui.text("Journal client (aucun aller-retour) :", size="sm", color="muted")
    ui.text(log.log, size="sm", color="muted")

    representative = ui.dropzone(name="client_sample", on_move=log.log.push("move"))
    with representative:
        with ui.draggable(key="a"):
            ui.text("A")
    emitted_html_block(
        "Emitted HTML (Dropzone avec on_move client)",
        serialize_html(representative),
    )


# ───────────────────────────────────────────────────────────────────────
# §2 — Composability / Edge cases
# ───────────────────────────────────────────────────────────────────────


@refreshable(deps=[Board])
def composability() -> None:
    state = Board()
    with ui.grid(cols=2, gap="md"):
        for key, title, rows in [("todo", "À faire", state.todo),
                                 ("done", "Terminé", state.done)]:
            with ui.vstack(gap="sm"):
                ui.heading(title, level=4)
                with ui.dropzone(name=key, accepts=["card"], on_move=move_card):
                    with ui.vstack(gap="sm"):
                        for label in ui.drag_each(rows, group="card", handle=True):
                            card(label)
    with ui.hstack(gap="sm", align="center"):
        ui.text(
            f"« Terminé » accepte {DONE_CAPACITY} cartes au plus — "
            f"refus serveur : {state.refused}",
            size="sm", color="muted",
        )
        ui.button("Réinitialiser", on_click=reset_board,
                  variant="ghost", size="sm")


@refreshable(deps=[Locked])
def edge_cases() -> None:
    state = Locked()
    with ui.grid(cols=2, gap="md"):
        with ui.vstack(gap="sm"):
            ui.heading("locked=True — rien ne sort", level=4)
            with ui.dropzone(name="kept", accepts=["any"], locked=True,
                             color="error", on_move=move_locked):
                with ui.vstack(gap="sm"):
                    for label in ui.drag_each(state.kept, group="any"):
                        card(label)
        with ui.vstack(gap="sm"):
            ui.heading("zone libre", level=4)
            with ui.dropzone(name="free", accepts=["any"], color="success",
                             on_move=move_locked):
                with ui.vstack(gap="sm"):
                    for label in ui.drag_each(state.free, group="any"):
                        card(label)


@refreshable(deps=[Apercu])
def apercu_en_vol() -> None:
    """Ce que le geste MONTRE : l'item en vol devient un EMPLACEMENT.

    ⚠️ Ce banc comparait deux colonnes — le défaut d'un côté, la
    proposition de l'autre — jusqu'au 2026-09-13. La proposition EST le
    défaut depuis : garder la comparaison montrerait deux fois la même
    chose. Ce qui reste ici est le cas que le défaut ne couvre PAS.

    Une zone qui contient UN élément : le dépôt permute. Rien ne
    s'insère entre deux voisins, quelqu'un est délogé — et l'emplacement
    mince, qui raconte une insertion, n'a alors rien de juste à dire.
    """
    state = Apercu()
    with ui.hstack(gap="lg"):
        for zone_nom, occupants in (("chaise_g", list(state.chaise_g)),
                                    ("chaise_d", list(state.chaise_d))):
            with (
                ui.dropzone(name=zone_nom, accepts=["chaise"],
                            holds="one", on_move=swap_chaise,
                            color="primary"),
                ui.vstack(gap="none", align="center", justify="center",
                          classes="min-h-24 w-28 rounded-lg border "
                                  "border-dashed border-text/25 p-2"),
            ):
                for qui in ui.drag_each(occupants, group="chaise"):
                    with ui.vstack(gap="xs", align="center"):
                        ui.avatar(name=qui, size="lg", shape="circle")
                        ui.text(qui, size="sm")
    ui.text(
        "holds=\"one\" : la zone dit qu'elle ne tient qu'UN occupant. "
        "Le geste cesse alors d'y glisser la carte — elle en "
        "contiendrait deux le temps du survol, et c'est ça qui \"prend "
        "énormément de place\" — et la marque comme ÉCRASABLE : trait "
        "plein et anneau, là où une zone qui accepte une insertion "
        "reste en pointillés. Le dépôt part quand même au handler, qui "
        "décide d'échanger ou de refuser.",
        color="muted", size="sm",
    )


# ───────────────────────────────────────────────────────────────────────
# Page
# ───────────────────────────────────────────────────────────────────────


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Drag & drop", level=1)
        ui.text(
            "Trois briques : ui.dropzone (la zone), ui.draggable (un item "
            "attrapable) et ui.drag_each (le sucre qui emballe une liste). "
            "Le geste est du Pointer Event — souris : glisser après ~5 px ; "
            "tactile : appui long ~250 ms. Le serveur reste la vérité : un "
            "handler qui ne mute rien fait revenir la carte.",
            color="muted",
        )

        # ── §1 Reference ────────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Balayage visuel de chaque prop.", color="muted", size="sm")

            ui.heading("Basic — une liste qui se réordonne", level=3)
            with ui.dropzone(name="ref_basic"), ui.vstack(gap="sm"):
                for label in ui.drag_each(["Alpha", "Bravo", "Charlie"]):
                    card(label)

            ui.heading("handle=True", level=3)
            ui.text(
                "La carte entière devient inerte : seule la poignée "
                "attrape. Une restriction, pas le geste par défaut.",
                color="muted", size="sm",
            )
            with ui.dropzone(name="ref_handle"), ui.vstack(gap="sm"):
                for label in ui.drag_each(["Avec poignée", "Idem", "Idem"],
                                          handle=True):
                    card(label)

            ui.heading("disabled — un prédicat par item", level=3)
            ui.text(
                "⚠️ disabled veut dire « ne s'attrape pas », PAS « ne bouge "
                "pas ». Tirez une carte libre au-delà de celle du milieu : "
                "elle ne peut pas être saisie, mais son index change — "
                "dépasser un voisin, c'est ça, réordonner une liste. Même "
                "sémantique que Sortable.js et dnd-kit.",
                color="muted", size="sm",
            )
            with ui.dropzone(name="ref_disabled"), ui.vstack(gap="sm"):
                for label in ui.drag_each(
                    ["Libre", "Pas saisissable", "Libre"],
                    disabled=lambda row: row == "Pas saisissable",
                ):
                    card(label)

            ui.heading("ui.draggable posé à la main", level=3)
            ui.text(
                "Sans drag_each : le composant dans une boucle ordinaire. "
                "key= redevient obligatoire — aucun each ne le fournit — et "
                "chaque prop se passe explicitement.",
                color="muted", size="sm",
            )
            with ui.dropzone(name="ref_manual"), ui.vstack(gap="sm"):
                for label, is_locked in [("Un", False), ("Deux", False),
                                         ("Pas saisissable", True)]:
                    with ui.draggable(key=label, group="manual", handle=True,
                                      disabled=is_locked, color="info"):
                        card(label)

            ui.heading("color — visible seulement PENDANT un geste", level=3)
            ui.text(
                "La zone est transparente au repos ; la teinte arrive avec "
                "data-bz-drop-ok, que seul le drag pose. Attrapez une carte "
                "pour la voir.",
                color="muted", size="sm",
            )
            with ui.grid(cols=4, gap="sm"):
                for tint in COLORS[:4]:
                    with ui.vstack(gap="xs"):
                        ui.text(tint, size="sm", color="muted")
                        with ui.dropzone(name=f"ref_{tint}", color=tint):
                            with ui.vstack(gap="sm"):
                                for label in ui.drag_each([tint], key=str):
                                    card(label)

        # ── §2 Edge cases ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text(
                "accepts= décide de ce qui ENTRE, locked= de ce qui SORT — "
                "deux portes, deux props. La zone rouge accepte tout ce que "
                "son groupe autorise et ne rend rien.",
                color="muted", size="sm",
            )
            edge_cases()

            ui.heading("Zone vide", level=3)
            ui.text(
                "Une zone sans item garde une hauteur minimale, sinon elle "
                "s'effondrerait à zéro et deviendrait impossible à viser.",
                color="muted", size="sm",
            )
            ui.dropzone(name="empty", accepts=["any"], on_move=move_locked)

            ui.heading("Une zone qui contient UN élément", level=3)
            ui.text(
                "Le thème réduit l'item en vol à un emplacement — c'est le "
                "défaut, visible dans toutes les listes de cette page. Mais "
                "un emplacement raconte une INSERTION : sur une zone qui "
                "ne tient qu'un occupant, le dépôt permute, et il n'y a "
                "rien à insérer.",
                color="muted", size="sm",
            )
            apercu_en_vol()

            ui.heading("Deux listes indépendantes", level=3)
            ui.text(
                "Aucune ne déclare accepts= : chacune ne reçoit que SES "
                "items. Sans ce défaut, elles s'échangeraient des cartes "
                "parce que personne n'a rien déclaré.",
                color="muted", size="sm",
            )
            with ui.grid(cols=2, gap="md"):
                for zone_name, rows in [("iso_a", ["A1", "A2"]),
                                        ("iso_b", ["B1", "B2"])]:
                    with ui.dropzone(name=zone_name), ui.vstack(gap="sm"):
                        for label in ui.drag_each(rows):
                            card(label)

        # ── §2 Composability ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text(
                "Deux zones qui s'échangent des cartes — le kanban est une "
                "recipe, pas un composant. « Terminé » n'accepte que deux "
                "cartes : la troisième est REFUSÉE par le serveur, qui ne "
                "mute rien, et c'est le morph qui la ramène — aucun code "
                "d'annulation nulle part. Sortir une carte libère la place.",
                color="muted", size="sm",
            )
            composability()

        # ── §2 A11y ─────────────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                "La poignée est un role=button focusable (Tab l'atteint) et "
                "porte un aria-label. Elle fait au moins 24×24 px — le "
                "plancher WCAG 2.2 § 2.5.8 — parce qu'une prise de 16 px est "
                "inutilisable au doigt. Aucune affordance n'est gatée sur "
                ":hover : le survol n'existe pas sur un pointeur grossier.",
                color="muted", size="sm",
            )
            with ui.dropzone(name="a11y"), ui.vstack(gap="sm"):
                for label in ui.drag_each(["Tab pour m'atteindre", "Puis moi"],
                                          handle=True):
                    card(label)
            ui.text(
                "Échap pendant un drag annule et remet la carte d'où elle "
                "vient.",
                color="muted", size="sm",
            )

        # ── §3 Server playground ────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text("Chaque prop, chaque échappatoire, en direct.",
                    color="muted", size="sm")
            server_playground()

        # ── §4 Server events ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server events", level=2)
            ui.text(
                "move est le seul event de la famille. Le handler reçoit un "
                "Move typé — item_key, from_zone, to_zone, from_index, "
                "to_index — via la règle d'injection EventPayload.",
                color="muted", size="sm",
            )
            server_events()

        # ── §6 Client events ────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text(
                "Le même event, en expression client : zéro aller-retour, "
                "et le serveur n'apprend rien du déplacement.",
                color="muted", size="sm",
            )
            client_events()

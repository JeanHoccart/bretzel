"""État page-scopé du playground Diagram, plus les axes constants.

Un champ par prop du composant, un par échappatoire universelle, un
par modificateur — c'est ce que le gabarit demande, et c'est ce qui
fait du Server playground un vrai banc plutôt qu'une démo.

``Picked`` est à part : il pilote le RESSERREMENT de la carte
Reference. Serveur, parce que changer le centre change les nœuds
dessinés, donc le placement.
"""

from bretzel import ui
from bretzel.state import ClientState, PageState, field

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]
DIRECTIONS = ["right", "down"]

# La forme d'une vraie carte d'app : des pages qui consomment un moteur,
# qui consomme lui-même deux sources. Un losange plus une arête longue,
# donc des nœuds fantômes — la configuration où une arête peut passer
# SUR un nœud si le placement est faux.
EDGES = [
    ("dashboard", "planning_engine"),
    ("planning", "planning_engine"),
    ("tournees", "planning_engine"),
    ("planning_engine", "geo"),
    ("planning_engine", "db"),
    ("geo", "db"),
    ("settings", "db"),
]

NODES = [
    ui.node("dashboard", label="dashboard", icon="layout-dashboard",
            badge="1 route", group="pages"),
    ui.node("planning", label="planning", icon="calendar-days",
            badge="2 routes", group="pages"),
    ui.node("tournees", label="tournées", icon="truck", group="pages"),
    ui.node("settings", label="settings", icon="settings", group="pages"),
    ui.node("planning_engine", label="planning_engine", icon="cog",
            group="socle", width=200),
    ui.node("geo", label="geo", icon="map-pin", group="socle"),
    ui.node("db", label="db", icon="database", group="socle"),
]


class Picked(PageState):
    """Le nœud centré dans la carte Reference — SERVEUR.

    Resserrer change les nœuds dessinés, donc le placement : ça ne peut
    pas être client. Éclairer, si — et le composant le fait tout seul.
    """

    key: str = field(default="")


class DiagramPlayground(PageState):
    focus:        str  = field(default="")
    depth:        int  = field(default=1)
    direction:    str  = field(default="right")
    size:         str  = field(default="md")
    color:        str  = field(default="primary")
    empty_text:   str  = field(default="No graph.")
    empty_icon:   str  = field(default="workflow")
    empty_desc:   str  = field(default="")
    empty:        bool = field(default=False)
    render_mode:  str  = field(default="default")
    click_mode:   str  = field(default="none")
    # Échappatoires universelles.
    classes:      str  = field(default="")
    custom_id:    str  = field(default="")
    aria_label:   str  = field(default="")
    style:        str  = field(default="")
    extra_attrs:  str  = field(default="")
    # Modificateurs universels.
    visible:      str  = field(default="on")
    tooltip:      str  = field(default="")




class DiagramServerEvents(PageState):
    """Le journal de la carte Server events.

    ``item_click`` est le SEUL event de ``Diagram`` — le gabarit exige
    qu'ils soient tous câblés, donc un seul contrôle vivant suffit ici.
    """

    log: list = field(default_factory=list)


class DiagramClientEvents(ClientState, persist="memory"):
    """Le même journal, mais en mémoire du NAVIGATEUR.

    Le même event câblé sur une expression cliente : la liste grossit
    sans qu'aucune requête parte. C'est ce que le bloc HTML de la carte
    montre — un ``bz-on:click`` là où le serveur mettait un ``hx-post``.
    """

    log: list = field(default_factory=list)


class DiagramClient(ClientState, persist="memory"):
    """Le nœud sélectionné, côté NAVIGATEUR.

    Le miroir du contrat ``BINDABLE_PROPS = ("value",)`` : lier
    ``value=`` à ce champ, c'est brancher la sélection sur le magasin
    client. Un clic écrit dedans sans qu'aucune requête parte, et tout
    ce qui lit le champ suit.
    """

    node: str = field(default="")

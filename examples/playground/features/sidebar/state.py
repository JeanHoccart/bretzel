"""État et constantes du banc ``Sidebar``.

Les axes (couleurs, largeurs, modes de repli), les quatre ``State``
et les deux constantes que le reste du paquet lit — ``FIT``, le
contournement du ``h-screen`` du thème, et ``NAV``, les entrées de
démonstration.

``PATH`` vit ICI et non dans ``__init__`` — contrairement aux autres
pages découpées — parce que ``NAV`` le CITE : l'entrée qui pointe sur
cette page ressort active toute seule, et c'est précisément ce qu'on
vient regarder. Le poser deux fois en ferait deux sources.
"""

from bretzel.state import ClientState, PageState, field


PATH = "/sidebar"

COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]
WIDTHS = ["sm", "md", "lg"]
# Les quatre modes de repli — l'axe UNIQUE depuis la fusion de
# ``variant=`` et ``collapsible=``. ``overlay`` n'est pas gaté ``md:`` :
# c'est le mode qu'on monte sur un téléphone.
MODES = ["rail", "offcanvas", "overlay", "none"]

# Le contournement de ``h-screen`` — cf. l'en-tête du module. Constante
# plutôt qu'un littéral recopié 15 fois : quand le thème sera corrigé,
# c'est une seule ligne à supprimer et un grep pour retrouver les usages.
FIT = {"root": "h-full!"}

# De vrais chemins du playground : l'entrée qui pointe sur CETTE page
# ressort active toute seule (mode auto — comparaison à ``current_path``),
# ce qui est précisément ce qu'on veut regarder.
NAV = [
    ("Home",     "home",       "/"),
    ("App map",  "network",    "/app-map"),
    ("Sidebar",  "panel-left", PATH),
    ("Badge",    "tag",        "/badge"),
]

class SidebarPlayground(PageState):
    # Props du conteneur.
    width:       str = field(default="md")
    collapsible: str = field(default="rail")
    open:        bool = field(default=True)
    # Props de l'ITEM, appliquées à l'entrée « Sidebar » (celle qui pointe
    # vers cette page, donc active), ses voisines au repos servant de
    # témoins.
    item_color:    str = field(default="primary")
    item_icon:     str = field(default="panel-left")
    item_badge:    str = field(default="")
    item_disabled: bool = field(default=False)
    active_mode:   str = field(default="auto")
    # Escape hatches.
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")


class SidebarEvents(PageState):
    log: list = field(default_factory=list)


class SidebarClient(ClientState, persist="memory"):
    expanded: bool = field(default=True)
    active:   bool = field(default=False)
    badge:    int = field(default=0)
    disabled: bool = field(default=False)


class SidebarClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)

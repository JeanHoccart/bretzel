"""The ``Sidebar`` bench's state and constants.

The axes (colours, widths, collapse modes), the four ``State`` and the
two constants the rest of the package reads — ``FIT``, the workaround for
the theme's ``h-screen``, and ``NAV``, the demonstration entries.

``PATH`` lives HERE and not in ``__init__`` — unlike the other split
pages — because ``NAV`` QUOTES it: the entry pointing at this page comes
out active on its own, and it is precisely what one comes to look at.
Setting it twice would make two sources.
"""

from bretzel.state import ClientState, PageState, field


PATH = "/sidebar"

COLORS = ["primary", "secondary", "success", "warning", "error", "info",
          "muted"]
WIDTHS = ["sm", "md", "lg"]
# The four collapse modes — the SINGLE axis since ``variant=`` and
# ``collapsible=`` merged. ``overlay`` is not gated on ``md:``: it is the
# mode one mounts on a phone.
MODES = ["rail", "offcanvas", "overlay", "none"]

# The ``h-screen`` workaround — cf. the module's header. A constant
# rather than a literal copied 15 times: when the theme is fixed, it is
# one line to delete and a grep to find the uses.
FIT = {"root": "h-full!"}

# Real playground paths: the entry pointing at THIS page comes out
# active on its own (auto mode — comparison with ``current_path``), which
# is precisely what we want to look at.
NAV = [
    ("Home",     "home",       "/"),
    ("App map",  "network",    "/app-map"),
    ("Sidebar",  "panel-left", PATH),
    ("Badge",    "tag",        "/badge"),
]

class SidebarPlayground(PageState):
    # Container props.
    width:       str = field(default="md")
    collapsible: str = field(default="rail")
    open:        bool = field(default=True)
    # ITEM props, applied to the "Sidebar" entry (the one pointing at
    # this page, hence active), its neighbours at rest serving as
    # controls.
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

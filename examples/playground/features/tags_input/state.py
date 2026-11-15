"""TagsInput playground — contacts and the page's states."""

from bretzel.state import ClientState, PageState, field

#: An address book: what the recipients' suggestions come from.
CONTACTS = [
    ("sophie.marchand@almadia.example", "Sophie Marchand"),
    ("thomas.leroy@almadia.example", "Thomas Leroy"),
    ("laura.petit@almadia.example", "Laura Petit"),
    ("karim.benali@almadia.example", "Karim Benali"),
    ("marc.dubois@almadia.example", "Marc Dubois"),
    ("claire.martin@almadia.example", "Claire Martin"),
    ("helpdesk@almadia.example", "Support informatique"),
    ("rh@almadia.example", "Service RH"),
]

#: What a valid typed value is, for a mail address.
EMAIL = r"[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+"

TAGS = ["urgent", "client", "interne", "facture", "à relire"]

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning", "error", "info", "muted"]


class TagsInputPlayground(PageState):
    placeholder: str = field(default="Ajouter quelqu'un")
    pattern:     bool = field(default=True)
    suggestions: bool = field(default=True)
    disabled:    bool = field(default=False)
    color:       str = field(default="primary")
    size:        str = field(default="md")
    variant:     str = field(default="surface")
    initial:     str = field(default="sophie.marchand@almadia.example, pas-une-adresse")
    classes:     str = field(default="")
    custom_id:   str = field(default="")
    aria_label:  str = field(default="")
    style:       str = field(default="")
    extra_attrs: str = field(default="")
    visible:     str = field(default="on")
    tooltip:     str = field(default="")


class Recipients(ClientState, persist="memory"):
    """The mail demo: À and Cc, two lists of addresses."""

    to: list = field(default_factory=lambda: ["sophie.marchand@almadia.example"])
    cc: list = field(default_factory=list)


class AddressSearch(PageState):
    """What the server search found, for the mail demo."""

    query: str = field(default="")


class TagsInputEvents(PageState):
    log: list = field(default_factory=list)


class TagsInputClient(ClientState, persist="memory"):
    """Mirror of ``BINDABLE_PROPS = ('value', 'disabled')``."""

    picked:   list = field(default_factory=lambda: ["urgent"])
    disabled: bool = field(default=False)


class TagsInputClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)

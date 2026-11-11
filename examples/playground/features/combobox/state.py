"""Combobox playground — options and the page's states."""

from bretzel.state import ClientState, PageState, field

# Reasonably sized option list — exercises the search filter without
# blowing up the HTML. Mix of diacritics + multi-word labels so the
# tokenise-then-substring algorithm has something interesting to chew.
COUNTRIES = [
    ("fr", "France"),
    ("es", "España"),
    ("de", "Germany"),
    ("it", "Italia"),
    ("pt", "Portugal"),
    ("nl", "Nederland"),
    ("be", "Belgique"),
    ("ch", "Suisse"),
    ("at", "Österreich"),
    ("se", "Sverige"),
    ("no", "Norge"),
    ("dk", "Danmark"),
    ("fi", "Suomi"),
    ("pl", "Polska"),
    ("cz", "Česko"),
    ("gr", "Ελλάδα"),
    ("uk", "United Kingdom"),
    ("ie", "Ireland"),
    ("us", "United States"),
    ("ca", "Canada"),
    ("mx", "México"),
    ("br", "Brasil"),
    ("ar", "Argentina"),
    ("cl", "Chile"),
    ("jp", "日本"),
    ("cn", "中国"),
    ("kr", "대한민국"),
    ("au", "Australia"),
    ("nz", "New Zealand"),
]


SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


# ── Playground state ──────────────────────────────────────────────────


class ComboboxPlayground(PageState):
    multiple:     bool = field(default=False)
    bulk_actions: bool = field(default=False)
    creatable:    bool = field(default=False)
    placeholder:  str  = field(default="Search countries…")
    empty_text:   str  = field(default="No results")
    disabled:     bool = field(default=False)
    required:     bool = field(default=False)
    color:        str  = field(default="primary")
    size:         str  = field(default="md")
    initial:      str  = field(default="fr")
    # Escape hatches.
    classes:     str  = field(default="")
    custom_id:   str  = field(default="")
    aria_label:  str  = field(default="")
    style:       str  = field(default="")
    extra_attrs: str  = field(default="")
    visible:     str  = field(default="on")
    tooltip:     str  = field(default="")


class ComboboxEvents(PageState):
    log: list = field(default_factory=list)


class ComboboxServerEvents(ClientState, persist="memory"):
    """Drives the server-events demo. ``value=ses.value`` →
    autoname → ``name="value"`` on the hidden input → handler
    receives ``value=`` via FormData."""

    value: str = field(default="")


class ComboboxClient(ClientState, persist="memory"):
    """Mirror of Combobox's BINDABLE_PROPS = ('value', 'disabled').

    ``picked`` binds the ``value`` prop (kept as ``picked`` — reused
    across the External-controls card's three modes, which predate
    the Client playground card and only exercise ``value``)."""

    picked:   str  = field(default="fr")
    disabled: bool = field(default=False)


class ComboboxMultiClient(ClientState, persist="memory"):
    picked: list = field(default_factory=lambda: ["fr", "de"])


class ComboboxClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)

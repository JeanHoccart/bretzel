"""Page-scoped + client-side state for the Button playground.

Four state buckets :

- :class:`ButtonPlayground` (PageState) — drives the Server playground
  card. One field per prop + per universal escape hatch + per
  universal modifier. Flipping any control re-renders the preview AND
  the live HTML inspection block.
- :class:`ButtonEvents` (PageState) — log of server-side event firings
  for the Server events card.
- :class:`ButtonClient` (ClientState) — same idea as ``ButtonPlayground``
  but client-side : the runtime mutates the store in-browser and the button
  re-renders without a network round-trip. Limited to the props that
  actually support ``ClientBinding`` today.
- :class:`ButtonClientEvents` (ClientState) — log of client-only event
  firings (no server round-trip).

Constants ``VARIANTS`` / ``SIZES`` / ``COLORS`` / ``TYPES`` describe
the legal axis values — referenced from ``ui.py`` to build the select
options.
"""

from bretzel.state import ClientState, PageState, field

VARIANTS = ["solid", "soft", "surface", "outline", "ghost"]
SIZES    = ["xs", "sm", "md", "lg", "xl"]
COLORS   = ["primary", "secondary", "success",
            "warning", "error", "info", "muted"]
TYPES    = ["button", "submit", "reset"]


class ButtonPlayground(PageState):
    """Live state of the Server playground card. Page-scoped, so each
    visit of /button gets its own fresh instance (and two tabs don't
    collide).

    Covers every Button prop, the universal escape hatches
    (``classes`` / ``id`` / ``aria_label`` / ``style``), the universal
    modifiers (``visible`` / ``tooltip``), and the event-handler
    shape (``on_click_mode`` switches between none / server callable
    / Client string / both — the framework emits very different
    HTML in each case).

    Empty-string fields turn into a missing kwarg so the component
    picks its own default. ``visible`` is a tri-state via a string
    field because ``True`` (default) must be omitted to let the
    universal modifier short-circuit ; ``"on"`` keeps the default,
    ``"off"`` explicitly sets ``visible=False``.
    """

    # Core props
    label:      str  = field(default="Click me")
    variant:    str  = field(default="solid")
    size:       str  = field(default="md")
    color:      str  = field(default="primary")
    disabled:   bool = field(default=False)
    loading:    bool = field(default=False)
    icon_left:  str  = field(default="")
    icon_right: str  = field(default="")
    type:       str  = field(default="button")
    # Escape hatches — empty string means "don't pass the kwarg".
    classes:    str  = field(default="")
    custom_id:  str  = field(default="")
    aria_label: str  = field(default="")
    style:      str  = field(default="")
    extra_attrs: str = field(default="")  # multi-line "key=value" pairs
    # Universal modifiers (apply post-render via the metaclass wrap).
    visible:    str  = field(default="on")    # "on" | "off"
    tooltip:    str  = field(default="")
    # Event-handler shape — drives which attrs land on the <button>.
    on_click_mode: str = field(default="none")  # "none" | "server" | "client" | "both"


class ButtonEvents(PageState):
    """Live log of server events fired by the events demo button.
    Page-scoped so each tab carries its own history."""

    log: list = field(default_factory=list)


class ButtonClient(ClientState, persist="memory"):
    """Client-side state for the Client playground card. Mirror of
    Button's ``BINDABLE_PROPS = ("label", "disabled", "loading")`` —
    the curated reactive surface. Visual configuration (variant /
    size / color) is design-time on Button ; if you need it to react
    to state, conditional render server-side covers it."""

    label:    str  = field(default="Click me")
    disabled: bool = field(default=False)
    loading:  bool = field(default=False)


class ButtonClientEvents(ClientState, persist="memory"):
    """Live log of client-only events (no server round-trip)."""

    log: list = field(default_factory=list)

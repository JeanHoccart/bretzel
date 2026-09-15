"""Page-scoped + client-side state for the Input playground.

Four state buckets :

- :class:`InputPlayground` (PageState) — drives the Server playground
  card. One field per Input prop + per universal escape hatch + per
  universal modifier + per HTML5 validation attr + per decorative slot.
- :class:`InputEvents` (PageState) — log of server-side event firings
  (change / input / focus / blur / keydown / keyup).
- :class:`InputClient` (ClientState) — drives the Client playground
  card. Limited to the props that actually support ``ClientBinding``
  today : value (two-way via bz-model), type, placeholder, disabled,
  readonly, required. ``size`` / ``color`` / icon-slot bindings would
  be silently SSR-frozen on Input — skipped here.
- :class:`InputClientEvents` (ClientState) — log of client-only event
  firings (no server round-trip).

Constants describe the legal axis values referenced from ``ui.py``.
"""

from bretzel.state import ClientState, PageState, field

# Native-picker types (date / time / color / file / etc.) AND
# ``number`` are NOT allowed on Input — they have dedicated Bretzel
# components (``number`` → ``ui.number_input``). Listing ``number``
# here 500s the preview on selection. Cf.
# ``bretzel/components/inputs/input/input.py::_NATIVE_PICKER_TYPES``.
TYPES = ["text", "email", "password", "tel", "url", "search"]
SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success",
          "warning", "error", "info", "muted"]
AUTOCOMPLETES = ["", "off", "on", "email", "username", "current-password",
                 "new-password", "name", "tel", "url"]


class InputPlayground(PageState):
    """Live state of the Server playground card. Empty-string fields
    turn into a missing kwarg so the component picks its own default.

    Covers every Input prop (text / value / placeholder / type +
    cosmetic color/size), every HTML5 validation attr (required /
    disabled / readonly / min/max/step / pattern / minlength/maxlength
    / autocomplete), every decorative slot (prefix / suffix / icon_left
    / icon_right), every universal escape hatch (classes / id /
    aria_label / style / extra_attrs), every universal modifier
    (visible / tooltip), and the event-handler shape toggle
    (on_change_mode).
    """

    # Core props
    type:         str  = field(default="text")
    placeholder:  str  = field(default="Type here…")
    value:        str  = field(default="")
    color:        str  = field(default="primary")
    size:         str  = field(default="md")
    # HTML5 validation attrs
    disabled:     bool = field(default=False)
    readonly:     bool = field(default=False)
    required:     bool = field(default=False)
    # min / max / step removed : they only apply to type=number, which
    # Input rejects (use ui.number_input).
    pattern:      str  = field(default="")
    minlength:    str  = field(default="")
    maxlength:    str  = field(default="")
    autocomplete: str  = field(default="")
    # Decorative slots — strings ; the playground does not exercise
    # the Component-as-slot shape on Input (kept for the Composability
    # card on the visual side).
    prefix:       str  = field(default="")
    suffix:       str  = field(default="")
    icon_left:    str  = field(default="")
    icon_right:   str  = field(default="")
    # Escape hatches
    classes:      str  = field(default="")
    custom_id:    str  = field(default="")
    aria_label:   str  = field(default="")
    style:        str  = field(default="")
    extra_attrs:  str  = field(default="")
    # Universal modifiers
    visible:      str  = field(default="on")
    tooltip:      str  = field(default="")
    # Event-handler shape — drives which attrs land on the <input>.
    on_change_mode: str = field(default="none")


class InputEvents(PageState):
    """Live log of server events fired by the events demo input.
    Page-scoped so each tab carries its own history."""

    log: list = field(default_factory=list)


class InputClient(ClientState, persist="memory"):
    """Client-side state for the Client playground card. Mirror of
    Input's ``BINDABLE_PROPS = ("value", "disabled", "readonly")`` —
    the curated reactive surface.

    Three flavors covered :

    - ``value`` : two-way ``bz-model`` (the runtime syncs user typing back
      into the store — the Input-specific signature feature).
    - ``disabled`` / ``readonly`` : DOM attrs via ``bz-attr:<attr>``.

    All other Input props (type / placeholder / pattern / minlength /
    maxlength / required / autocomplete /
    color / size / prefix / suffix / icon_left / icon_right) are
    design-time configuration — not bindable. Server playground
    exercises them via PageState (which always works — server
    re-render rebuilds the input with the new attribute values).
    """

    value:    str  = field(default="hello")
    disabled: bool = field(default=False)
    readonly: bool = field(default=False)


class InputClientEvents(ClientState, persist="memory"):
    """Live log of client-only events (no server round-trip)."""

    log: list = field(default_factory=list)

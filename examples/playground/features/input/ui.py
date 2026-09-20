"""Render — refreshable panels + page assembly for the Input feature.

Same gabarit as Button : 10 cards (5 visual + 5 stateful), the 5
stateful cards each emit ONE ``ui.code(serialize_html(...))`` block to
expose their distinctive binding shape (server callable / the runtime
expression / bz-model for two-way bind / etc.).

Input-specific points :

- Two render layouts (bare ``<input>`` vs ``<div><span><input/><span></div>``
  with prefix/suffix). The Server playground exercises both via the
  prefix/suffix controls.
- ``AUTONAME_FROM = "value"`` : passing ``value=client.field`` on the
  Input derives the HTML ``name=`` attribute from the binding's field
  name. The Client playground exposes this in the emitted HTML.
- Two-way binding : ``value=ClientBinding`` lands as ``bz-model="..."``
  (the runtime syncs user typing back into the store), NOT ``bz-attr:value``.
  The Client playground HTML shows ``bz-model`` instead of the usual
  ``bz-attr:`` prefix.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression

from examples.playground.features.inspection import emitted_html_block

from examples.playground.features.input.logic import (
    clear_log,
    log_blur,
    log_change,
    log_focus,
    log_input,
    log_keydown,
    log_keyup,
    playground_change_handler,
    server_changed,
)
from examples.playground.features.input.state import (
    AUTOCOMPLETES,
    COLORS,
    SIZES,
    TYPES,
    InputClient,
    InputClientEvents,
    InputEvents,
    InputPlayground,
)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


# client expression used when ``on_change_mode`` requests the client
# branch — pushes a visible signal on the input itself.
_CLIENT_CHANGE_EXPR = "this.classList.toggle('ring-4')"


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def build_preview(state: InputPlayground):
    """Map the playground state to ``ui.input(...)`` kwargs."""
    kwargs: dict = {
        "type": state.type,
        "color": state.color,
        "size": state.size,
        "disabled": state.disabled,
        "readonly": state.readonly,
        "required": state.required,
    }
    if state.placeholder:
        kwargs["placeholder"] = state.placeholder
    if state.value:
        kwargs["value"] = state.value
    if state.pattern:
        kwargs["pattern"] = state.pattern
    if state.minlength:
        try:
            kwargs["minlength"] = int(state.minlength)
        except ValueError:
            pass
    if state.maxlength:
        try:
            kwargs["maxlength"] = int(state.maxlength)
        except ValueError:
            pass
    if state.autocomplete:
        kwargs["autocomplete"] = state.autocomplete
    if state.prefix:
        kwargs["prefix"] = state.prefix
    if state.suffix:
        kwargs["suffix"] = state.suffix
    if state.icon_left:
        kwargs["icon_left"] = state.icon_left
    if state.icon_right:
        kwargs["icon_right"] = state.icon_right
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
        kwargs["on_change"] = [playground_change_handler, _CLIENT_CHANGE_EXPR]

    return ui.input(**kwargs)


@refreshable(deps=[InputPlayground])
def server_panel() -> None:
    state = InputPlayground()

    # ── Controls grid — every prop, every escape hatch, every modifier.
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("type"):
            ui.select(value=state.type,
                      options=[(t, t) for t in TYPES],
                      on_change=server_changed)
        with control("placeholder"):
            ui.input(value=state.placeholder, placeholder="Type here…",
                     on_change=server_changed)
        with control("value (literal)"):
            ui.input(value=state.value, placeholder="",
                     on_change=server_changed)
        with control("color (focus ring)"):
            ui.select(value=state.color,
                      options=[(c, c.title()) for c in COLORS],
                      on_change=server_changed)
        with control("size"):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control("readonly"):
            ui.switch(checked=state.readonly, on_change=server_changed)
        with control("required"):
            ui.switch(checked=state.required, on_change=server_changed)
        with control("pattern (regex)"):
            ui.input(value=state.pattern, placeholder="[0-9]{4}",
                     on_change=server_changed)
        with control("minlength"):
            ui.input(value=state.minlength, placeholder="3",
                     on_change=server_changed)
        with control("maxlength"):
            ui.input(value=state.maxlength, placeholder="20",
                     on_change=server_changed)
        with control("autocomplete"):
            ui.select(value=state.autocomplete,
                      options=[(a, a or "(none)") for a in AUTOCOMPLETES],
                      on_change=server_changed)
        with control("prefix"):
            ui.input(value=state.prefix, placeholder="$",
                     on_change=server_changed)
        with control("suffix"):
            ui.input(value=state.suffix, placeholder=".com",
                     on_change=server_changed)
        with control("icon_left"):
            ui.input(value=state.icon_left, placeholder="ex: search",
                     on_change=server_changed)
        with control("icon_right"):
            ui.input(value=state.icon_right, placeholder="ex: arrow-right",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes,
                     placeholder="!rounded-none",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-input",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label,
                     placeholder="Email address",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="border-color: rebeccapurple",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=email\nrole=textbox",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip,
                     placeholder="Enter your email address",
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

    with ui.flex(justify="center", align="center"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


@refreshable(deps=[InputEvents])
def events_panel() -> None:
    state = InputEvents()

    # One hx-post per element — each event gets its own instance
    # (mirrors the button.py convention). The full multi-event firing
    # is ALSO shown client-side, zero-round-trip, in the Client
    # events card below.
    ui.text("One input per event below fires its server handler ; "
            "interact with each to populate the log :",
            color="muted", size="sm")
    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
        ui.input(placeholder="change", on_change=log_change)
        ui.input(placeholder="input", on_input=log_input)
        ui.input(placeholder="focus", on_focus=log_focus)
        ui.input(placeholder="blur", on_blur=log_blur)
        ui.input(placeholder="keydown", on_keydown=log_keydown)
        ui.input(placeholder="keyup", on_keyup=log_keyup)

    ui.divider()

    with ui.hstack(justify="between", align="center"):
        ui.text("Live log (newest first, last 10)",
                color="muted", size="sm")
        ui.button("Clear", variant="ghost", size="xs",
                  on_click=clear_log, disabled=not state.log)

    if state.log:
        with ui.vstack(gap="xs"):
            for i, evt in enumerate(reversed(state.log[-10:]), 1):
                ui.text(f"{i}. {evt}",
                        color="muted", size="sm", classes="font-mono")
    else:
        ui.text("(no events yet — interact with the input above to fire one)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (the input wired to the server ``on_change``)",
        serialize_html(
            ui.input(placeholder="Try typing…",
                     on_change=log_change,
                     )
        ),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Input", level=1)
            ui.text(
                "Text input — single-line, optionally decorated with prefix"
                " / suffix / icons. Real stress-testing lives in the Server"
                " playground card below ; the AUTONAME + bz-model two-way"
                " binding are visible in the External controls card's"
                " emitted HTML."
                " Three ways to drive the value : imperative API"
                " (``.set()`` / ``.clear()`` / ``.focus()`` / ``.blur()``),"
                " ClientBinding (``value=client.field``), or both together"
                " — compared side-by-side in Card 9.",
                color="muted",
            )

            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of every prop.",
                            color="muted", size="sm")

                    ui.heading("Types (text-ish only)", level=3)
                    ui.text(
                        "Input is restricted to text-ish HTML5 types. "
                        "Native picker types (date / time / color / "
                        "file / month / datetime-local) are blocked at "
                        "construction time — each has its own dedicated "
                        "Bretzel component (ui.date_picker, etc.) for "
                        "consistent UX.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(gap="sm"):
                        ui.input(type="text",     placeholder="text")
                        ui.input(type="email",    placeholder="you@example.com")
                        ui.input(type="password", placeholder="•••••••")
                        ui.input(type="tel",      placeholder="+33 6 12 34 56 78")
                        ui.input(type="url",      placeholder="https://…")
                        ui.input(type="search",   placeholder="search…")
                    ui.text(
                        "type=\"number\" blocked since mai 2026 — use "
                        "ui.number_input for numeric inputs (proper "
                        "steppers + clamp + precision).",
                        color="muted", size="xs",
                    )

                    ui.heading("Sizes", level=3)
                    with ui.vstack(gap="sm"):
                        for s in SIZES:
                            ui.input(size=s, placeholder=s)

                    ui.heading("Colors (focus ring)", level=3)
                    with ui.vstack(gap="sm"):
                        for c in COLORS:
                            ui.input(color=c, placeholder=f"focus → {c}")

                    ui.heading("State flags", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(placeholder="enabled")
                        ui.input(placeholder="disabled", disabled=True)
                        ui.input(value="readonly value", readonly=True)
                        ui.input(placeholder="required", required=True)

                    ui.heading("Icon overlays", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(placeholder="search…",
                                 icon_left="search")
                        ui.input(placeholder="external",
                                 icon_right="external-link")
                        ui.input(placeholder="search → go",
                                 icon_left="search",
                                 icon_right="arrow-right")

                    ui.heading('clearable (type, then the cross)', level=3)
                    ui.text(
                        'The cross only appears when there is something '
                            'to clear — it is pure CSS (`peer-placeholder-'
                            'shown`), no signal is involved. The click '
                            "empties the field AND replays a keystroke's "
                            'events (`input` then `change`), so a binding, a '
                            'local scope or a server handler all three '
                            'follow. Defaults to False: a free field already '
                            'clears from the keyboard.',
                        size="sm", color="muted",
                    )
                    with ui.vstack(gap="sm"):
                        ui.input(placeholder="tape quelque chose…",
                                 clearable=True)
                        ui.input(value='already filled', clearable=True,
                                 icon_left="search")
                        ui.input(prefix="@", clearable=True,
                                 placeholder='with a prefix')

                    ui.heading("Prefix / suffix", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(placeholder="0.00", prefix="$")
                        ui.input(placeholder="amount", suffix="EUR")
                        ui.input(placeholder="username",
                                 prefix="@", suffix=".bretzel")

                    ui.heading("HTML5 validation", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(minlength=3, maxlength=20,
                                 placeholder="3–20 chars")
                        ui.input(pattern="[0-9]{4}",
                                 placeholder="4-digit PIN", maxlength=4)

                    ui.heading(
                        "Basic — external controls via .set() / "
                        ".clear() / .focus() / .blur()",
                        level=3,
                    )
                    ui.text(
                        "Capture the instance via ``i = ui.input(...)`` "
                        "and call ``i.set('Ada')`` / ``i.clear()`` / "
                        "``i.focus()`` / ``i.blur()`` from sibling "
                        "buttons. The imperative API is the default "
                        "style when you want to write into a field "
                        "from the outside without declaring a "
                        "``ClientState`` — useful for prefill buttons, "
                        "reset actions, or programmatic focus.",
                        color="muted", size="sm",
                    )
                    i = ui.input(placeholder="External controls drive me…")
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set 'Ada'", on_click=i.set("Ada"))
                        ui.button("Clear", variant="outline",
                                  on_click=i.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=i.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=i.blur())

            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Decorative slots — prefix / suffix / icon_left / "
                        "icon_right accept str | Component. Switch the "
                        "Server playground to see the emitted HTML for "
                        "each shape.",
                        color="muted", size="sm",
                    )

                    ui.heading("prefix slot", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(prefix="$",
                                 placeholder="as str")
                        ui.input(prefix=ui.icon("dollar-sign",
                                                color="success"),
                                 placeholder="as ui.icon Component")

                    ui.heading("suffix slot", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(suffix=".com",
                                 placeholder="as str")
                        ui.input(suffix=ui.icon("check", color="success"),
                                 placeholder="as ui.icon Component")

                    ui.heading("icon_left slot", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(icon_left="search",
                                 placeholder="as str shortcut")
                        ui.input(icon_left=ui.icon("search", color="warning"),
                                 placeholder="as ui.icon Component")

                    ui.heading("icon_right slot", level=3)
                    with ui.vstack(gap="sm"):
                        ui.input(icon_right="arrow-right",
                                 placeholder="as str shortcut")
                        ui.input(
                            icon_right=ui.icon("arrow-right", size="lg"),
                            placeholder="as ui.icon Component",
                        )

            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text(
                        "Inputs that historically break form fields. The "
                        "Server playground below lets you reproduce any of "
                        "these live AND inspect the HTML.",
                        color="muted", size="sm",
                    )

                    ui.heading("Empty value + placeholder", level=3)
                    with ui.hstack():
                        ui.input(value="", placeholder="placeholder shows")

                    ui.heading("Very long value (overflow scroll)", level=3)
                    with ui.hstack():
                        ui.input(value="A" * 200, placeholder="")

                    ui.heading("Emoji + multi-script value", level=3)
                    with ui.hstack():
                        ui.input(value="Ship 🚀 — שלום — 中文")

                    ui.heading("HTML-special chars (XSS escape)", level=3)
                    ui.text(
                        "Framework escapes value/placeholder. The script "
                        "tag renders as literal text in the value, never "
                        "executes.",
                        color="muted", size="xs",
                    )
                    with ui.hstack():
                        ui.input(value="<script>alert(1)</script>")

                    ui.heading("All HTML5 validation attrs combined",
                               level=3)
                    with ui.hstack():
                        ui.input(type="email", required=True,
                                 minlength=5, maxlength=50,
                                 pattern=".*@.*",
                                 placeholder="email, 5-50 chars, must contain @")

                    ui.heading("Disabled + required (HTML5 quirk)",
                               level=3)
                    ui.text(
                        "A disabled input is skipped from form "
                        "submission AND from constraint validation — "
                        "the required attr does nothing here.",
                        color="muted", size="xs",
                    )
                    with ui.hstack():
                        ui.input(placeholder="set but ignored",
                                 disabled=True, required=True)

                    ui.heading("Readonly + value (no edit but submits)",
                               level=3)
                    with ui.hstack():
                        ui.input(value="locked content", readonly=True)

            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text(
                        "Input nested inside other Bretzel components. "
                        "The form case is the canonical one — name + value "
                        "land in the form submission via autoname.",
                        color="muted", size="sm",
                    )

                    # NOTE — full-width components (Input / Form / Textarea)
                    # must NOT be wrapped in ``hstack`` for these demos :
                    # the row-flex collapses them to content width. Use a
                    # plain block context (or vstack) instead.

                    ui.heading("Inside ui.form (autoname-driven)",
                               level=3)
                    with ui.form():
                        with ui.vstack(gap="sm"):
                            ui.input(placeholder="email",
                                     type="email", required=True)
                            ui.button("Submit", type="submit",
                                      color="primary")

                    ui.heading("Inside ui.tooltip", level=3)
                    with ui.tooltip(
                        "Your work email — we'll never spam"
                    ):
                        ui.input(placeholder="email",
                                 icon_left="mail")

                    ui.heading("Inside ui.card", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.text("Wrapper card",
                                    color="muted", size="xs")
                            ui.input(placeholder="search…",
                                     icon_left="search")

            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Form inputs need an accessible label — either via "
                        "``aria-label`` (Server playground control), or "
                        "via a sibling ``<label for=…>`` element (out of "
                        "scope here, Input does NOT render its own label "
                        "by design — that's a Field component's job).",
                        color="muted", size="sm",
                    )
                    with ui.hstack():
                        ui.input(icon_left="user",
                                 attrs={"aria-label": "User name"},
                                 placeholder="user name")

            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "The real test bench. Every prop AND every "
                        "escape hatch is wired to a control ; the preview "
                        "and the emitted HTML both refresh on every "
                        "change. The toggle between the bare layout "
                        "and the prefix/suffix layout happens "
                        "automatically when you fill one of the affix "
                        "controls.",
                        color="muted", size="sm",
                    )
                    server_panel()

            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    ui.text(
                        "In V3 an element carries ONE ``hx-post``, so a "
                        "single server handler is wired here : ``on_change`` "
                        "(a module-level callable). The HTML below shows it "
                        "landing on the DOM as ``hx-post`` + ``hx-trigger="
                        "\"change\"`` + the framework identity triplet. The "
                        "other Input events (input / focus / blur / keys) "
                        "are wired client-side — see the Client events card.",
                        color="muted", size="sm",
                    )
                    events_panel()

            # ── Card 8 — Client playground ──────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client playground", level=2)
                    ui.text(
                        "Mirror of Input's ``BINDABLE_PROPS = "
                        "('value', 'disabled', 'readonly')`` contract. "
                        "``value`` flips live via two-way ``bz-model`` "
                        "(typing syncs back into the store) ; "
                        "``disabled`` / ``readonly`` flip via "
                        "``bz-attr:<attr>`` — no network round-trip. "
                        "Everything else (type / size / color / "
                        "prefix / suffix / icons) stays design-time.",
                        color="muted", size="sm",
                    )
                    client = InputClient(key="playground")
                    with ui.grid(cols={"base": 1, "sm": 3}, gap="md"):
                        with control("value"):
                            ui.input(value=client.value)
                        with control("disabled"):
                            ui.switch(checked=client.disabled)
                        with control("readonly"):
                            ui.switch(checked=client.readonly)

                    ui.divider()

                    with ui.flex(justify="center", align="center"):
                        ui.input(value=client.value,
                                  disabled=client.disabled,
                                  readonly=client.readonly)

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — bz-model on value (two-way "
                        "bind), bz-attr:disabled / bz-attr:readonly "
                        "on the two flags.",
                        serialize_html(
                            ui.input(value=client.value,
                                      disabled=client.disabled,
                                      readonly=client.readonly)
                        ),
                    )

            # ── Card 9 — External controls — the 3 modes ────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("External controls — the 3 modes",
                               level=2)
                    ui.text(
                        "Same scenario (external buttons write into "
                        "an input) played three ways. Pick the mode "
                        "that fits your need : imperative for one-off "
                        "writes, binding when another component must "
                        "read the value, both together when you want "
                        "write-through with a reactive observer.",
                        color="muted", size="sm",
                    )

                    # ── Mode 1 — Imperative only ────────────────────
                    ui.heading(
                        "Mode 1 — Imperative only (default for "
                        "one-off writes)",
                        level=3,
                    )
                    ui.text(
                        "No ClientState. The input owns its own DOM "
                        "value ; ``.set('Ada')`` / ``.clear()`` "
                        "dispatch ``bz-set`` / ``bz-clear`` events "
                        "caught by the input. ``.focus()`` / "
                        "``.blur()`` are pure DOM commands. **Use "
                        "this by default when you just need to "
                        "prefill / reset / focus a field from a "
                        "sibling button — no observer needed.**",
                        color="muted", size="sm",
                    )
                    m1 = ui.input(placeholder="Imperative — no binding")
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set 'Ada'", on_click=m1.set("Ada"))
                        ui.button("Clear", variant="outline",
                                  on_click=m1.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m1.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m1.blur())

                    ui.divider()

                    # ── Mode 2 — ClientBinding only ─────────────────
                    ui.heading(
                        "Mode 2 — ClientBinding only (when another "
                        "component must read or react)",
                        level=3,
                    )
                    ui.text(
                        "Use this when **another component needs to "
                        "read the value live** — an echo next to the "
                        "field, a character counter, a button visible "
                        "only when the input has content. "
                        "``value=binding`` lands as ``bz-model`` so "
                        "the user's typing flows back into the "
                        "reactive store live ; siblings reading the "
                        "same store update via client reactivity, no "
                        "round-trip.",
                        color="muted", size="sm",
                    )
                    bound = InputClient(key="binding_only")
                    with ui.hstack(gap="md", align="center"):
                        ui.input(value=bound.value,
                                 placeholder="Type here…")
                        ui.text(
                            ClientExpression(
                                "'Length: ' + ($bz.state.InputClient."
                                "binding_only.value || '').length + "
                                "' chars'"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )

                    ui.divider()

                    # ── Mode 3 — Both : write-through ───────────────
                    ui.heading(
                        "Mode 3 — Both (write-through)",
                        level=3,
                    )
                    ui.text(
                        'A binding supplied AND ``.set(...)`` / '
                            '``.clear()`` called on the instance. The '
                            'framework detects the binding and delegates to '
                            '``binding.set(value)`` — **the DOM dispatch is '
                            'not used**, single source of truth preserved. '
                            'The observer (length, on the right) sees the '
                            'imperative writes AND the manual typing through '
                            'the same store.',
                        color="muted", size="sm",
                    )
                    both = InputClient(key="both")
                    m3 = ui.input(value=both.value,
                                  placeholder="Bound + imperative…")
                    with ui.hstack(gap="md", align="center"):
                        ui.text(
                            ClientExpression(
                                "'Length: ' + ($bz.state.InputClient."
                                "both.value || '').length + ' chars'"
                            ),
                            color="muted", size="sm",
                            classes="font-mono",
                        )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button("Set 'Ada'", on_click=m3.set("Ada"))
                        ui.button("Clear", variant="outline",
                                  on_click=m3.clear())
                        ui.button("Focus", variant="ghost",
                                  on_click=m3.focus())
                        ui.button("Blur", variant="ghost",
                                  on_click=m3.blur())

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — Mode 2 (binding only) : "
                        "bz-model on value reads + writes the bound "
                        "path ; AUTONAME also visible : "
                        "name=\"value\" auto-derived from the "
                        "binding's field name.",
                        serialize_html(
                            ui.input(value=bound.value,
                                     placeholder="Type here…")
                        ),
                    )

            # ── Card 10 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "Input wired to all 6 events with the runtime push "
                        "expressions — zero round-trip. Type / focus / "
                        "blur and watch the log fill via ``bz-text``.",
                        color="muted", size="sm",
                    )
                    cevents = InputClientEvents()
                    ui.input(
                        placeholder="Try typing…",
                        on_change=cevents.log.push("change"),
                        on_input=cevents.log.push("input"),
                        on_focus=cevents.log.push("focus"),
                        on_blur=cevents.log.push("blur"),
                        on_keydown=cevents.log.push("keydown"),
                        on_keyup=cevents.log.push("keyup"),
                    )

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text(
                            "Live log (client-reactive — no refresh)",
                            color="muted", size="sm",
                        )
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.InputClientEvents.default.log || [])'
                        '.join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML (representative — the same input "
                        "carries all 6 ``bz-on:<event>`` directives)",
                        serialize_html(
                            ui.input(
                                placeholder="Try typing…",
                                on_change=cevents.log.push("change"),
                                on_input=cevents.log.push("input"),
                                on_focus=cevents.log.push("focus"),
                                on_blur=cevents.log.push("blur"),
                                on_keydown=cevents.log.push("keydown"),
                                on_keyup=cevents.log.push("keyup"),
                            )
                        ),
                    )

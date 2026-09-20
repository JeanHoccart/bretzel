"""``SignaturePad`` test bench.

Ten cards. ``SignaturePad.BINDABLE_PROPS = ("value",)`` — the stroke's
data URL is bindable (the client writes it by drawing); placeholder /
clear_label / disabled / size / color stay design-time. Event:
``change``. Imperative: ``.clear()``.
"""

from urllib.parse import quote

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression, ClientState, PageState, field
from examples.playground.features.inspection import emitted_html_block

PATH = "/signature_pad"


#: A signature "already there" for the reopened-file demo.
#:
#: An SVG data URI rather than a base64 PNG, for two reasons: it stays
#: READABLE in the source (a base64 blob says nothing about what it
#: draws), and it exercises the other data-URI branch — the
#: percent-encoded one, with no ``=`` padding. The canvas loads both the
#: same.
#:
#: ⚠️ This card's first version used a TRANSPARENT 1×1 PNG: even once
#: the loading was fixed, it would have shown nothing. A demo that cannot
#: visibly fail demonstrates nothing.
#: ⚠️ The colour is written ``#334155`` in the CLEAR: it is ``quote``
#: that encodes it as ``%23``. Writing it already encoded doubles it
#: (``%2523``), the SVG then reads an invalid colour, and the stroke
#: renders NOTHING — measured, and invisible other than by counting
#: pixels.
EXISTING_SIGNATURE = "data:image/svg+xml," + quote(
    "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='110'>"
    "<path d='M20 78 C 55 18, 78 96, 108 52 S 156 12, 186 66 "
    "S 236 88, 262 34' fill='none' stroke='#334155' stroke-width='4' "
    "stroke-linecap='round' stroke-linejoin='round'/>"
    "</svg>"
)

SIZES = ["xs", "sm", "md", "lg", "xl"]
COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


class SignaturePadPlayground(PageState):
    value: str = field(default="")
    placeholder: str = field(default="Sign here")
    clear_label: str = field(default="Clear")
    disabled: bool = field(default=False)
    size: str = field(default="md")
    color: str = field(default="primary")
    name: str = field(default="")
    # Escape hatches.
    classes: str = field(default="")
    custom_id: str = field(default="")
    aria_label: str = field(default="")
    style: str = field(default="")
    extra_attrs: str = field(default="")
    # Universal modifiers.
    visible: str = field(default="on")
    tooltip: str = field(default="")
    # Event-handler shape.
    on_change_mode: str = field(default="none")


class SignaturePadEvents(PageState):
    log: list = field(default_factory=list)


# The component's CANONICAL case: the signature lives in a SERVER state,
# and autoname derives the hidden input's ``name`` from the field.
# Nothing to wire — ``_hydrate_state`` rewrites it on submission.
class Contract(PageState):
    signature: str = field(default="")
    signed_by: str = field(default="")


class SignaturePadClient(ClientState, persist="memory"):
    sig: str = field(default="")


class SignaturePadClientEvents(ClientState, persist="memory"):
    log: list = field(default_factory=list)


# ⚠️ The state that makes the bench's ``change`` READABLE. With neither
# a binding nor a ``name=``, the component sets NO ``name`` on its hidden
# input (the base layer's deliberate choice: a default name would inject
# a stray field into every enclosing form), so the handler leaves with an
# empty FormData. A lesson paid for on the /resizable bench the same
# day.
class SignaturePadServerEvents(ClientState, persist="memory"):
    value: str = field(default="")


def log(name: str) -> None:
    state = SignaturePadEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None:
    # We log the SIZE and the prefix, not the data URL: thirty
    # kilobytes of base64 in a log would make the page unreadable.
    head = value[:30] + "…" if len(value) > 30 else value
    log(f"change(len={len(value)}, head={head!r})")


def clear_log() -> None:
    state = SignaturePadEvents()
    state.log = []


def server_changed(state: SignaturePadPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed control's value
    # into ``state`` (coerced + persisted).
    pass


def playground_change_handler(value: str = "") -> None:
    log(f"playground-server-change(len={len(value)})")


def sign_contract(doc: Contract) -> None:
    """The form demo's handler — hydrated from the submission.

    It is THE point of the component: ``doc.signature`` carries the data
    URL without any endpoint or encoding having been written.
    """
    log(
        f"submit(signed_by={doc.signed_by!r}, "
        f"signature_len={len(doc.signature)})"
    )


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


def build_preview(state: SignaturePadPlayground) -> dict:
    kwargs: dict = {
        "disabled": state.disabled,
        "size": state.size,
        "color": state.color,
    }
    # An empty string = do not pass the kwarg.
    if state.placeholder:
        kwargs["placeholder"] = state.placeholder
    if state.clear_label:
        kwargs["clear_label"] = state.clear_label
    if state.value:
        kwargs["value"] = state.value
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


@refreshable(deps=[SignaturePadPlayground])
def server_panel() -> None:
    state = SignaturePadPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control('placeholder (empty = no prompt)'):
            ui.input(value=state.placeholder, placeholder="Sign here",
                     on_change=server_changed)
        with control('clear_label (empty = no button)'):
            ui.input(value=state.clear_label, placeholder="Clear",
                     on_change=server_changed)
        with control("disabled"):
            ui.switch(checked=state.disabled, on_change=server_changed)
        with control('size (frame height)'):
            ui.select(value=state.size,
                      options=[(s, s) for s in SIZES],
                      on_change=server_changed)
        with control("color"):
            ui.select(value=state.color,
                      options=[(c, c) for c in COLORS],
                      on_change=server_changed)
        with control("name (overrides autoname)"):
            ui.input(value=state.name, placeholder="signature",
                     on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="!h-64",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-pad",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Signature",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style, placeholder="max-width: 420px",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=pad",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder='Sign here',
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
    ui.signature_pad(**kwargs)

    ui.divider()

    emitted_html_block(
        'Emitted HTML (SignaturePad + its canvas + the hidden carrier)',
        serialize_html(ui.signature_pad(**kwargs)),
    )


@refreshable(deps=[SignaturePadEvents])
def events_panel() -> None:
    state = SignaturePadEvents()

    ui.text(
        'The pad emits ONE ``change`` on pen LIFT, never while drawing — '
            'a PNG weighs tens of kilobytes, and emitting it per frame would '
            'send as many POSTs. Sign below and lift your finger: a single '
            'line appears.',
        color="muted", size="sm",
    )

    sig_state = SignaturePadServerEvents()
    with ui.vstack():
        ui.signature_pad(value=sig_state.value, on_change=log_change)

    ui.divider()

    ui.heading('The canonical case — a form', level=3)
    ui.text(
        'The signature lives in a ServerState. Autoname derives '
            '``name="signature"`` from the field, and the handler receives it'
            ' hydrated: no endpoint and no encoding to write.',
        color="muted", size="sm",
    )
    doc = Contract()
    with ui.form(on_submit=sign_contract), ui.vstack(gap="sm"):
        ui.input(value=doc.signed_by, placeholder="Votre nom")
        ui.signature_pad(value=doc.signature)
        with ui.hstack():
            ui.button("Signer", type="submit")

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
        ui.text('(no events yet — sign the pad above)',
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (SignaturePad with on_change handler)",
        serialize_html(
            ui.signature_pad(value=sig_state.value, on_change=log_change)
        ),
    )


def page() -> None:
    with ui.container(), ui.vstack():
        ui.heading("Signature pad", level=1)
        ui.text(
            'Signing with a finger or a mouse, inside a form. The value '
                'is a PNG as a data URL, carried by a named hidden input — so'
                ' it leaves with the form like an ordinary field, and your '
                'ServerState receives it hydrated. The first and only '
                '<canvas> in the repository.',
            color="muted",
        )

        # ── Card 1 — Reference ──────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Reference", level=2)
            ui.text("Visual scan of every prop.",
                    color="muted", size="sm")

            ui.heading("Basic", level=3)
            ui.signature_pad()

            ui.heading('Sizes (frame height)', level=3)
            ui.text(
                'The only size axis a pad has: a <canvas> has NO '
                    'intrinsic dimension, so with no declared height it is '
                    'zero pixels tall.',
                color="muted", size="xs",
            )
            for s in SIZES:
                ui.text(f"size={s}", color="muted", size="xs")
                ui.signature_pad(size=s)

            ui.heading('Colors (focused frame + button)', level=3)
            ui.text(
                'The colour does NOT tint the ink: the stroke takes the '
                    'text colour, so it stays readable in both themes. A '
                    'pen_color= would have frozen an ink invisible on the '
                    'other background.',
                color="muted", size="xs",
            )
            for c in COLORS:
                ui.signature_pad(color=c, size="sm", placeholder=c)

            ui.heading("disabled", level=3)
            ui.text(
                'The frame goes solid and greys out: a signed pad must no'
                    ' longer INVITE a signature.',
                color="muted", size="xs",
            )
            ui.signature_pad(disabled=True)

        # ── Card 2 — Slots ──────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Slots", level=2)
            ui.text(
                'Two texts, and no sub-component: the prompt and the '
                    "button's label. Emptying one makes it DISAPPEAR — that "
                    'is the escape hatch for a pad with no prompt, or with no'
                    ' button because the page already has one elsewhere.',
                color="muted", size="sm",
            )

            ui.heading('a custom placeholder', level=3)
            ui.signature_pad(placeholder='Sign in the frame')

            ui.heading('With no prompt', level=3)
            ui.signature_pad(placeholder="")

            ui.heading('With no Clear button', level=3)
            ui.signature_pad(clear_label="")

            ui.heading('Translated button label', level=3)
            ui.signature_pad(clear_label="Effacer",
                             placeholder='Sign here')

        # ── Card 3 — Edge cases ─────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Edge cases", level=2)
            ui.text("Edge inputs and exotic combinations.",
                    color="muted", size="sm")

            ui.heading("Ni invite ni bouton", level=3)
            ui.text('A bare frame — not an error.',
                    color="muted", size="xs")
            ui.signature_pad(placeholder="", clear_label="")

            ui.heading('A very long prompt', level=3)
            ui.signature_pad(
                placeholder="Signez ici en utilisant votre doigt, votre "
                            "stylet ou votre souris, puis validez"
            )

            ui.heading('A signature already there', level=3)
            ui.text(
                'A reopened file: the data URL is rendered at SSR, loaded'
                    ' on hydration and painted UNDER the new strokes. Sign '
                    'over it: the two leave together. Clearing takes both too'
                    ' — “clear” means an empty frame, not “go back to the '
                    'previous signature”.',
                color="muted", size="xs",
            )
            ui.signature_pad(value=EXISTING_SIGNATURE)

            ui.heading('In a narrow frame', level=3)
            ui.text(
                'The pad fills the space it is given — it has no '
                    'intrinsic width to shrink to.',
                color="muted", size="xs",
            )
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                ui.signature_pad(size="sm")
                ui.text("Cellule voisine.", color="muted")
                ui.text("Autre voisine.", color="muted")

        # ── Card 4 — Composability ──────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Composability", level=2)
            ui.text('SignaturePad in its usual contexts.',
                    color="muted", size="sm")

            ui.heading('In a ui.form_field', level=3)
            with ui.form_field(label="Signature",
                               hint='Sign in the frame above'):
                ui.signature_pad(size="sm")

            ui.heading('Inside a ui.dialog', level=3)
            with ui.dialog(title='Sign the contract', width="lg") as dlg, \
                    ui.vstack():
                ui.signature_pad()
            ui.button('Open the dialog', on_click=dlg.open())

            ui.heading('In a resizable panel', level=3)
            ui.text(
                'The test that counts, and the only one a screenshot does'
                    ' not show: resizing a <canvas> ERASES it. Sign, drag the'
                    ' handle — the signature must survive.',
                color="muted", size="xs",
            )
            ui.text(
                '⚠️ Note the composition: a panel is a SLOT, it does not '
                    'pad. It is the vstack you put inside that sets the p-4 —'
                    ' otherwise the pad sticks to the edge and to the '
                    'separator. Surfaces pad (card, dialog), slots do not '
                    '(panel, slide, tab panel).',
                color="muted", size="xs",
            )
            with ui.resizable(sizes=[60, 40], style="height: 260px"):
                with ui.resizable_panel(min_size=30):
                    with ui.vstack(gap="sm", classes="p-4 h-full"):
                        ui.text('Sign, then drag the handle.',
                                color="muted", size="xs")
                        ui.signature_pad(size="sm")
                with ui.resizable_panel():
                    with ui.vstack(classes="p-4"):
                        ui.text('The neighbouring panel.', color="muted")

        # ── Card 5 — A11y ───────────────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("A11y", level=2)
            ui.text(
                'The <canvas> is aria-hidden ON PURPOSE: what is '
                    'announced and reachable from the keyboard is the hidden '
                    'input (a real form control, with its name) and the Clear'
                    ' button. Putting a role on a drawing surface would '
                    'announce a control no key drives — half an ARIA pattern '
                    'is worth less than no pattern at all.',
                color="muted", size="sm",
            )
            ui.signature_pad(aria_label="Demo signature")

        # ── Card 6 — Server playground ──────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Server playground", level=2)
            ui.text(
                "Every SignaturePad prop AND every escape hatch is "
                "wired to a control ; the preview AND the emitted HTML "
                "both refresh on every change.",
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
                "Mirror of SignaturePad's BINDABLE_PROPS = ('value',). ⚠️"
                    ' Only to be used if ANOTHER component has to read the '
                    'signature client side: the ClientState snapshot leaves '
                    'WHOLE on every action POST, so a bound pad sends its '
                    'tens of kilobytes back on every click of the page. The '
                    'normal case is a ServerState (the “Server events” card).',
                color="muted", size="sm",
            )
            client = SignaturePadClient()
            ui.signature_pad(value=client.sig)

            ui.text(
                ClientExpression(
                    "'bytes in the store: ' + "
                        '(($bz.state.SignaturePadClient.default.sig || '
                        "'').length)"
                ),
                color="muted", size="sm", classes="font-mono",
            )

            ui.divider()

            emitted_html_block(
                'Emitted HTML — the carrier reads the store cell '
                    'directly; the runtime writes into it on pen lift.',
                serialize_html(ui.signature_pad(value=client.sig)),
            )

        # ── Card 9 — External controls — the 3 modes ────────────
        with ui.card(), ui.vstack():
            ui.heading("External controls — the 3 modes", level=2)
            ui.text(
                '.clear() ALWAYS dispatches a DOM event, binding or not: '
                    'clearing is not “writing the empty string”, the points '
                    'kept in memory have to be thrown away and the surface '
                    'repainted — and only the runtime knows how.',
                color="muted", size="sm",
            )

            ui.heading("Mode 1 — Imperative only (default)", level=3)
            m1 = ui.signature_pad()
            with ui.hstack(gap="sm"):
                ui.button("Effacer", variant="outline",
                          on_click=m1.clear())

            ui.divider()

            ui.heading("Mode 2 — ClientBinding only", level=3)
            bound = SignaturePadClient(key="binding_only")
            ui.signature_pad(value=bound.sig)
            ui.text(
                ClientExpression(
                    '(($bz.state.SignaturePadClient.binding_only.sig || '
                        "'').length ? 'signed' : 'empty')"
                ),
                color="muted", size="sm",
            )

            ui.divider()

            ui.heading("Mode 3 — Both", level=3)
            both = SignaturePadClient(key="both")
            m3 = ui.signature_pad(value=both.sig)
            with ui.hstack(gap="sm", align="center"):
                ui.button("Effacer", variant="outline",
                          on_click=m3.clear())
                ui.text(
                    ClientExpression(
                        "'octets = ' + "
                        "(($bz.state.SignaturePadClient.both.sig "
                        "|| '').length)"
                    ),
                    color="muted", size="sm", classes="font-mono",
                )

            ui.divider()

            emitted_html_block(
                'Emitted HTML — the root carries bz-on:bz-clear, the '
                    'receiver .clear() dispatches to.',
                serialize_html(ui.signature_pad(value=both.sig)),
            )

        # ── Card 10 — Client events ─────────────────────────────
        with ui.card(), ui.vstack():
            ui.heading("Client events", level=2)
            ui.text('change wired to a client expression that pushes the payload '
                'SIZE onto a ClientState list. Zero network — and it is the '
                'size that gets pushed, not the data URL: a log of base64 '
                'PNGs is unreadable.',
                    color="muted", size="sm")
            cevents = SignaturePadClientEvents()
            _size = ClientExpression("($event.target.value || '').length")
            ui.signature_pad(on_change=cevents.log.push(_size))

            ui.divider()

            with ui.hstack(justify="between", align="center"):
                ui.text("Live log (client-reactive)",
                        color="muted", size="sm")
                ui.button("Clear", variant="ghost", size="xs",
                          on_click=cevents.log.clear())

            ui.divider()

            log_text = ClientExpression(
                '($bz.state.SignaturePadClientEvents.default.log'
                ' || []).join("\\n") || "(no events yet)"'
            )
            ui.text(log_text,
                    color="muted", size="sm",
                    classes="font-mono whitespace-pre")

            ui.divider()

            emitted_html_block(
                'Emitted HTML — the bz-on:change handler is relocated '
                    'onto the hidden input, whose bz-effect re-fires a change'
                    ' on every pen lift.',
                serialize_html(
                    ui.signature_pad(on_change=cevents.log.push(_size))
                ),
            )

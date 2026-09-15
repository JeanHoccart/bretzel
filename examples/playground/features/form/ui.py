"""Render — cards 1-5 (visual reference) + page assembly for the
Form feature.

Cards 1-5 (Reference / Slots / Edge cases / Composability / A11y)
are visual scans of typical Form shapes ; they use the no-op
``submitted`` handler since the goal there is layout, not behaviour.
Cards 6-8 (Login / Signup / Profile) are realistic scenarios with
their own dedicated state + handler + Alert/Notification surface ;
added in Tasks 2-4 of the redesign plan.
"""

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import ClientExpression


from examples.playground.features.form.logic import (
    account_submit,
    clear_log,
    demo_error_fire,
    log_submit,
    login_submit,
    profile_submit,
    signup_submit,
    submitted,
)
from examples.playground.features.form.state import (
    AccountForm,
    DemoErrors,
    FormClientEvents,
    FormEvents,
    FormPlayground,
    LoginForm,
    ProfileForm,
    SignupForm,
)
from examples.playground.features.inspection import emitted_html_block


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


_CLIENT_SUBMIT_EXPR = "$event.preventDefault(); this.classList.toggle('ring-4')"


def build_preview(state: FormPlayground) -> dict:
    kwargs: dict = {}
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
    if state.on_submit_mode == "server":
        kwargs["on_submit"] = submitted
    elif state.on_submit_mode == "client":
        kwargs["on_submit"] = _CLIENT_SUBMIT_EXPR
    elif state.on_submit_mode == "both":
        kwargs["on_submit"] = [submitted, _CLIENT_SUBMIT_EXPR]
    return kwargs


@refreshable(deps=[FormPlayground])
def server_panel() -> None:
    state = FormPlayground()

    # Form's only real constructor prop is on_submit (a handler
    # shape, not a toggle) — the grid below is universal escape
    # hatches + modifiers + the on_submit shape switch. Thin is fine
    # here ; absent is not.
    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("classes"):
            ui.input(value=state.classes, placeholder="!max-w-sm",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-form",
                     on_change=server_changed)
        with control("aria-label"):
            ui.input(value=state.aria_label, placeholder="Contact form",
                     on_change=server_changed)
        with control("style"):
            ui.input(value=state.style,
                     placeholder="background: rebeccapurple",
                     on_change=server_changed)
        with control("extra_attrs (one per line, key=value)"):
            ui.textarea(value=state.extra_attrs, rows=3,
                        placeholder="data-test=contact",
                        on_change=server_changed)
        with control("tooltip"):
            ui.input(value=state.tooltip, placeholder="Submit to save",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (default)"),
                               ("off", "False (skip render)")],
                      on_change=server_changed)
        with control("on_submit mode"):
            ui.select(value=state.on_submit_mode,
                      options=[("server", "Server callable"),
                               ("client", "Client string"),
                               ("both", "Both (list)")],
                      on_change=server_changed)

    ui.divider()

    kwargs = build_preview(state)
    with ui.flex(justify="center"):
        with ui.form(**kwargs):
            with ui.hstack(align="end", gap="sm"):
                with ui.form_field(label="Anything"):
                    ui.input(placeholder="Type something…")
                ui.button("Submit", type="submit", color="primary")

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(ui.form(**kwargs)),
    )


def server_changed(state: FormPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass


@refreshable(deps=[FormEvents])
def events_panel() -> None:
    state = FormEvents()

    ui.text(
        "Form's one event : ``on_submit``. The scenario cards above "
        "each do real domain work (validation, Alert, Notification) ; "
        "this minimal form just appends to a live log — the canonical "
        "shape shared by every other component's Server events card.",
        color="muted", size="sm",
    )

    with ui.form(on_submit=log_submit):
        with ui.hstack(align="end", gap="sm"):
            with ui.form_field(label="Anything"):
                ui.input(placeholder="Type something…")
            ui.button("Submit", type="submit", color="primary")

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
        ui.text("(no events yet — submit the form above)",
                color="muted", size="sm")

    ui.divider()

    emitted_html_block(
        "Emitted HTML (representative — the on_submit form)",
        serialize_html(ui.form(on_submit=log_submit)),
    )


@refreshable(deps=[AccountForm])
def account_card() -> None:
    """Typed-form-model showcase — the V3 idiomatic pattern.

    No ``*Errors`` ClientState, no ``error=`` prop : the handler takes
    ``form: AccountForm`` and the form_fields infer + display + auto-
    clear from ``form.errors``. Re-rendered by ``account_submit`` on
    both error (show messages, keep raw text) and success (reset)."""
    ui.text(
        "The whole form is ONE typed model. The handler is "
        "``def account_submit(form: AccountForm)`` — hydrated, coerced "
        "and validated by the dispatcher. Try : username ``ada`` "
        "(taken) and/or email ``bad`` (no @) → submit → each field "
        "shows its message inline, inferred from the bound input "
        "(no ``error=``). Your typed text stays (raw layer). Type in a "
        "field → its error clears instantly (local ``bz-data`` flag). "
        "Fix both → toast.",
        color="muted", size="sm",
    )

    form = AccountForm()
    with ui.form(on_submit=account_submit):
        with ui.vstack():
            with ui.form_field(label="Username", required=True):
                ui.input(value=form.username, placeholder="ada")
            with ui.form_field(label="Email", required=True):
                ui.input(value=form.email, type="email",
                         placeholder="ada@example.com")
            ui.button("Create account", type="submit", color="primary")

    ui.divider()

    preview = ui.form(on_submit=account_submit)
    with preview:
        with ui.vstack():
            with ui.form_field(label="Username", required=True):
                ui.input(value=form.username, placeholder="ada")
            with ui.form_field(label="Email", required=True):
                ui.input(value=form.email, type="email")
            ui.button("Create account", type="submit", color="primary")
    emitted_html_block(
        "Emitted HTML — no ``error=`` on the form_fields. Each infers "
        "its field from the bound input's autoname and reads "
        "``form.errors[field]``. After a rejected submit the error span "
        "carries ``role=alert`` + ``bz-show`` and the root a local "
        "``bz-data`` flag whose ``bz-on:input`` clears it on edit.",
        serialize_html(preview),
    )


@refreshable(deps=[LoginForm])
def login_card() -> None:
    """Login — typed pattern. ``login_submit(form: LoginForm)`` ; no
    separate error-store ClientState, no ``error=`` : each form_field
    infers its field from the bound input, reads ``form.errors`` and
    auto-clears on edit. The ``✓ Logged in`` branch is state-conditional."""
    state = LoginForm()

    ui.text(
        "Per-field validators run during hydration. Try, in order : "
        "(1) submit empty → browser-native required tooltip ; "
        "(2) email='bad-email' (no @) → inline error on Email ; "
        "(3) email='ada@example.com' + password='wrong' → inline error "
        "on Password (hint : 123) ; type one char → it clears instantly. "
        "Re-submit password='123' → ✓ Logged in.",
        color="muted", size="sm",
    )

    with ui.form(on_submit=login_submit):
        with ui.vstack():
            with ui.form_field(label="Email", required=True):
                ui.input(value=state.email, type="email",
                         placeholder="you@example.com")
            with ui.form_field(label="Password", required=True):
                ui.input(value=state.password, type="password")
            ui.button("Log in", type="submit", color="primary")

    if state.logged_in:
        ui.divider()
        ui.text(f"✓ Logged in as {state.email}",
                color="success", size="sm")

    ui.divider()

    preview = ui.form(on_submit=login_submit)
    with preview:
        with ui.vstack():
            with ui.form_field(label="Email", required=True):
                ui.input(value=state.email, type="email")
            with ui.form_field(label="Password", required=True):
                ui.input(value=state.password, type="password")
            ui.button("Log in", type="submit", color="primary")
    emitted_html_block(
        "Emitted HTML — no error= : each form_field infers its field from "
        "the bound input and reads form.errors[field], auto-clearing on "
        "input via the local bz-data flag.",
        serialize_html(preview),
    )


@refreshable(deps=[SignupForm])
def signup_card() -> None:
    """Signup — per-field + cross-field. The cross-field ``FormError``
    (passwords don't match) lands in ``form.errors["_"]`` and shows in a
    top Alert ; per-field errors are inferred by each form_field. Typed
    pattern : no separate error-store ClientState."""
    state = SignupForm()

    ui.text(
        "A per-field validator (email) AND a cross-field validator "
        "(passwords match) on the same SignupForm. Submit two different "
        "passwords → form-level Alert (``form.errors['_']``) ; bad email "
        "→ inline error on Email ; all correct → toast. The dispatcher "
        "collects both kinds in one pass. Cross-field errors don't "
        "auto-clear (no single keystroke fixes them) — the Alert is "
        "server-rendered and disappears on the next valid submit.",
        color="muted", size="sm",
    )

    # Form-level (cross-field) error — server-rendered from
    # ``form.errors["_"]``, gone on the next valid submit.
    if state.errors.get("_"):
        ui.alert(state.errors["_"], color="error")

    with ui.form(on_submit=signup_submit):
        with ui.vstack():
            with ui.form_field(label="Email", required=True):
                ui.input(value=state.email, type="email")
            with ui.form_field(label="Password", required=True):
                ui.input(value=state.password, type="password")
            with ui.form_field(label="Confirm password", required=True):
                ui.input(value=state.confirm, type="password")
            ui.button("Create account", type="submit", color="primary")

    ui.divider()

    preview = ui.form(on_submit=signup_submit)
    with preview:
        with ui.vstack():
            with ui.form_field(label="Email", required=True):
                ui.input(value=state.email, type="email")
            with ui.form_field(label="Password", required=True):
                ui.input(value=state.password, type="password")
            with ui.form_field(label="Confirm password", required=True):
                ui.input(value=state.confirm, type="password")
            ui.button("Create account", type="submit", color="primary")
    emitted_html_block(
        "Emitted HTML — per-field form_fields infer their errors ; the "
        "cross-field message rides form.errors['_'] in a top Alert.",
        serialize_html(preview),
    )


@refreshable(deps=[ProfileForm])
def profile_card() -> None:
    """Profile edit — transformation validators normalise on hydration ;
    success stamps ``saved_at``. Typed pattern : no separate error-store."""
    state = ProfileForm()

    ui.text(
        "Transformation validators normalise the input during hydration "
        "(strip + lowercase email). Type '  JEAN@Example.COM  ' → it "
        "lands as 'jean@example.com' after submit. A bad email raises → "
        "inline error (inferred, auto-clearing) ; success refreshes the "
        "card so the normalised values + save timestamp show up.",
        color="muted", size="sm",
    )

    if state.saved_at:
        ui.alert(
            f"Profile saved at {state.saved_at}. Values normalised.",
            color="success", dismissible=True,
        )

    with ui.form(on_submit=profile_submit):
        with ui.vstack():
            with ui.form_field(label="Name", required=True):
                ui.input(value=state.name)
            with ui.form_field(label="Email", required=True):
                ui.input(value=state.email, type="email")
            ui.button("Save", type="submit", color="primary")

    ui.divider()

    preview = ui.form(on_submit=profile_submit)
    with preview:
        with ui.vstack():
            with ui.form_field(label="Name", required=True):
                ui.input(value=state.name)
            with ui.form_field(label="Email", required=True):
                ui.input(value=state.email, type="email")
            ui.button("Save", type="submit", color="primary")
    emitted_html_block(
        "Emitted HTML — form_fields infer errors from form.errors ; the "
        "success Alert is a server-rendered conditional (state.saved_at).",
        serialize_html(preview),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Form", level=1)
            ui.text(
                "Wraps children in a ``<form>`` tag with submit "
                "handling. The dispatcher walks up to the nearest "
                "``<form>`` ancestor on submit and ships the "
                "FormData verbatim — every named child input shows "
                "up as a kwarg on the handler. The companion "
                "``ui.form_field`` decorates an input with label / "
                "hint / error display.",
                color="muted",
            )
            ui.text(
                "For typed end-to-end forms, annotate the handler with "
                "a ``State`` model (``def save(form: MyForm)``) : the "
                "dispatcher hydrates + coerces + validates it, collects "
                "rejections into ``form.errors``, and each ``form_field`` "
                "shows its message automatically (inferred from the bound "
                "input, auto-cleared on edit). See the **Typed form "
                "model** card — it collapses the manual ClientState "
                "boilerplate of the Login / Signup / Profile cards.",
                color="muted",
            )

            # ── Card 1 — Reference ──────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)
                    ui.text("Visual scan of typical Form shapes.",
                            color="muted", size="sm")

                    ui.heading("Minimal", level=3)
                    with ui.form(on_submit=submitted):
                        with ui.vstack():
                            ui.input(name="email", type="email",
                                     placeholder="ada@example.com")
                            ui.button("Sign up", type="submit",
                                      color="primary")

                    ui.heading("With FormField labels + hints", level=3)
                    with ui.form(on_submit=submitted):
                        with ui.vstack():
                            with ui.form_field(label="Email",
                                               hint="We'll never share it.",
                                               required=True):
                                ui.input(name="email_a",
                                         type="email",
                                         placeholder="ada@example.com")
                            with ui.form_field(label="Password",
                                               hint="At least 12 chars",
                                               required=True):
                                ui.input(name="pass_a",
                                         type="password",
                                         minlength=12)
                            ui.button("Sign up", type="submit",
                                      color="primary")

                    ui.heading("With FormField error (static literal)",
                               level=3)
                    with ui.form(on_submit=submitted):
                        with ui.vstack():
                            with ui.form_field(
                                label="Email",
                                error="That address is already in use.",
                            ):
                                ui.input(name="email_b",
                                         type="email",
                                         value="taken@example.com",
                                         color="error")
                            ui.button("Retry", type="submit",
                                      color="primary")

                    ui.heading(
                        "With FormField error (reactive — Layer 2 + 4)",
                        level=3,
                    )
                    ui.text(
                        "No ``required=`` on this field, so HTML5 "
                        "native validation stays out of the way. "
                        "Click 'Test error' → server writes into "
                        "the DemoErrors ClientState → FormField "
                        "inline error appears via bz-show + bz-text. "
                        "Then type ONE character in the field → "
                        "the error vanishes instantly via the "
                        "``@input.capture`` auto-clear directive "
                        "(zero round-trip).",
                        color="muted", size="xs",
                    )
                    _demo_errors = DemoErrors()
                    with ui.form(on_submit=demo_error_fire):
                        with ui.vstack():
                            with ui.form_field(label="Email",
                                               error=_demo_errors.email):
                                ui.input(name="email",
                                         type="email",
                                         placeholder="you@example.com")
                            ui.button("Test error",
                                      type="submit",
                                      color="error")

                    ui.heading("Inline (hstack) form", level=3)
                    with ui.form(on_submit=submitted):
                        with ui.hstack(align="end", gap="sm"):
                            with ui.form_field(label="Search"):
                                ui.input(name="search", placeholder="Search…")
                            ui.button("Go", type="submit",
                                      color="primary")

            # ── Card 2 — Slots ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Slots", level=2)
                    ui.text(
                        "Form is a container — children flow through "
                        "the ``with`` block. Any input with a "
                        "``name=`` reaches the handler as a kwarg.",
                        color="muted", size="sm",
                    )

                    ui.heading("Mixed input types", level=3)
                    with ui.form(on_submit=submitted):
                        with ui.vstack():
                            with ui.form_field(label="Name"):
                                ui.input(name="name", placeholder="Ada")
                            ui.select(
                                [("free", "Free"),
                                 ("pro", "Pro")],
                                name="plan",
                                placeholder="Plan…",
                            )
                            ui.checkbox(name="terms",
                                        label="I accept the terms",
                                        required=True)
                            with ui.radio_group(name="channel",
                                                value="email"):
                                ui.radio(value="email", label="Email")
                                ui.radio(value="sms",   label="SMS")
                            ui.button("Submit", type="submit",
                                      color="primary")

            # ── Card 3 — Edge cases ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)
                    ui.text("Unusual usage patterns.",
                            color="muted", size="sm")

                    ui.heading("name= — le champ nommé à la main",
                               level=3)
                    ui.text(
                        "form_field dérive normalement son name du "
                        "binding de son contrôle. name= est "
                        "l'échappatoire quand il n'y a pas de "
                        "binding : c'est alors la seule façon "
                        "d'apparaître dans la form data.",
                        color="muted", size="xs",
                    )
                    with ui.form_field(label="Référence interne",
                                       name="internal_ref"):
                        ui.input(placeholder="REF-2026-…")

                    ui.heading("Empty form (no inputs)", level=3)
                    with ui.form(on_submit=submitted):
                        ui.button("Submit empty", type="submit")

                    ui.heading("Form with no submit handler", level=3)
                    ui.text(
                        "Without ``on_submit=``, the form falls "
                        "back to a regular HTTP POST to ``action=`` "
                        "— pass it as an ``attrs={\"action\": "
                        "\"/path\"}`` kwarg.",
                        color="muted", size="xs",
                    )
                    with ui.form(attrs={"action": "/_demo/noop",
                                        "method": "post"}):
                        with ui.vstack():
                            ui.input(name="legacy",
                                     placeholder="Plain HTTP POST")
                            ui.button("Submit (no JS)",
                                      type="submit")

                    ui.heading("Disabled submit (loading state)",
                               level=3)
                    ui.text(
                        "Disable the submit button while in flight "
                        "to prevent double-submits. ``loading=True`` "
                        "on Button auto-disables internally.",
                        color="muted", size="xs",
                    )
                    with ui.form(on_submit=submitted):
                        with ui.vstack():
                            ui.input(name="email_c",
                                     placeholder="ada@example.com")
                            ui.button("Submitting…",
                                      type="submit",
                                      loading=True,
                                      color="primary")

                    ui.heading("Reset button (native HTML reset)",
                               level=3)
                    with ui.form(on_submit=submitted):
                        with ui.vstack():
                            ui.input(name="topic_d",
                                     placeholder="Topic",
                                     value="Default value")
                            with ui.hstack(gap="sm"):
                                ui.button("Reset", type="reset",
                                          variant="ghost")
                                ui.button("Submit", type="submit",
                                          color="primary")

            # ── Card 4 — Composability ──────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)
                    ui.text("Form patterns you'll reach for.",
                            color="muted", size="sm")

                    ui.heading("Settings panel (Form inside Card)",
                               level=3)
                    with ui.card():
                        with ui.vstack():
                            ui.heading("Profile", level=3)
                            with ui.form(on_submit=submitted):
                                with ui.vstack():
                                    with ui.form_field(
                                        label="Display name"
                                    ):
                                        ui.input(name="display_name",
                                                 placeholder="Ada")
                                    with ui.form_field(
                                        label="Bio",
                                        hint="Markdown supported, "
                                             "max 160 chars",
                                    ):
                                        ui.textarea(name="bio",
                                                    rows=3,
                                                    maxlength=160)
                                    with ui.hstack(justify="end"):
                                        ui.button("Save",
                                                  type="submit",
                                                  color="primary")

                    ui.heading("Form inside ui.grid (two-column)",
                               level=3)
                    with ui.form(on_submit=submitted):
                        with ui.grid(cols={"base": 1, "sm": 2},
                                     gap="md"):
                            with ui.form_field(label="First name"):
                                ui.input(name="first_name", placeholder="Ada")
                            with ui.form_field(label="Last name"):
                                ui.input(name="last_name", placeholder="Lovelace")
                            with ui.form_field(label="Email"):
                                ui.input(name="email_grid", type="email", placeholder="ada@example.com")
                            with ui.form_field(label="Phone"):
                                ui.input(name="phone", type="tel", placeholder="+44 …")
                        with ui.hstack(justify="end"):
                            ui.button("Save", type="submit",
                                      color="primary")

            # ── Card 5 — A11y ───────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "Native ``<form>`` semantics carry through "
                        "— browsers + assistive tech know to "
                        "submit on Enter, focus the first "
                        "required-but-empty field, etc. "
                        "``FormField`` pairs labels to inputs via "
                        "``<label for=…>`` so screen readers "
                        "announce the field name when the input "
                        "gets focus.",
                        color="muted", size="sm",
                    )
                    with ui.form(on_submit=submitted):
                        with ui.vstack():
                            with ui.form_field(label="Email",
                                               required=True):
                                ui.input(name="email_a11y",
                                         type="email",
                                         required=True)
                            ui.button("Submit", type="submit",
                                      color="primary")

            # ── Typed form model — the V3 idiomatic pattern ─────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Typed form model", level=2)
                    ui.text(
                        "The idiomatic V3 pattern : one typed ``State`` "
                        "holds the data AND the validators ; the handler "
                        "takes ``form: AccountForm`` and reads "
                        "``form.errors``. Each ``form_field`` infers its "
                        "field from the bound input and displays + "
                        "auto-clears the message — no ``*Errors`` "
                        "ClientState, no ``setattr`` loop, no ``error=`` "
                        "wiring. The Login / Signup / Profile cards below "
                        "do the same by hand (the explicit ClientState "
                        "path), kept for when you want a separate error "
                        "store or a form-level cross-field Alert.",
                        color="muted", size="sm",
                    )
                    account_card()

            # ── Card 6 — Login (per-field validator + inline error) ─
            with ui.card():
                with ui.vstack():
                    ui.heading("Login", level=2)
                    ui.text(
                        "Demonstrates ``@validator(\"email\")`` — a "
                        "single-field validator that runs during "
                        "hydration. Raising rolls the field back ; the "
                        "dispatcher collects the message into "
                        "``form.errors[\"email\"]`` and the form_field "
                        "shows it inline (inferred, no ``error=``).",
                        color="muted", size="sm",
                    )
                    login_card()

            # ── Card 7 — Signup (cross-field + Alert + Notification) ─
            with ui.card():
                with ui.vstack():
                    ui.heading("Signup", level=2)
                    ui.text(
                        "Demonstrates ``@validator`` without arg — a "
                        "whole-instance validator enforcing a multi-field "
                        "invariant. Raising ``FormError`` routes the "
                        "message to ``form.errors[\"_\"]`` (form-level) → "
                        "a top Alert, while per-field ``ValueError``s land "
                        "on their fields. Success fires a toast.",
                        color="muted", size="sm",
                    )
                    signup_card()

            # ── Card 8 — Profile edit (transforms + Alert success) ──
            with ui.card():
                with ui.vstack():
                    ui.heading("Profile edit", level=2)
                    ui.text(
                        "Demonstrates transformation validators — "
                        "``@validator(\"field\")`` that returns a "
                        "normalised value instead of raising. The "
                        "dispatcher writes the returned value during "
                        "hydration, so the handler reads typed, "
                        "normalised fields. After save, a dismissible "
                        "success Alert shows the timestamp.",
                        color="muted", size="sm",
                    )
                    profile_card()

            # ── Card 9 — Server playground ───────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Every escape hatch is wired to a control (Form's "
                        "only real constructor prop, ``on_submit``, is a "
                        "handler-shape switch, not a value toggle) ; the "
                        "preview AND the emitted HTML both refresh on "
                        "every change.",
                        color="muted", size="sm",
                    )
                    server_panel()

            # ── Card 10 — Server events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server events", level=2)
                    events_panel()

            # ── Card 11 — Client events ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Client events", level=2)
                    ui.text(
                        "``on_submit`` wired to a client expression "
                        "that pushes onto a ClientState list — zero "
                        "network, the browser's native form submission "
                        "is prevented client-side. The log below "
                        "re-renders via bz-text on every push.",
                        color="muted", size="sm",
                    )
                    cevents = FormClientEvents()
                    # Prefix with preventDefault() — a client-string
                    # on_submit= doesn't stop the native submission on
                    # its own (unlike a server handler, which routes
                    # through hx-post and never touches the native
                    # action), so without it this would navigate away.
                    _submit_expr = ("$event.preventDefault(); "
                                    + cevents.log.push("submit"))
                    with ui.form(on_submit=_submit_expr):
                        with ui.hstack(align="end", gap="sm"):
                            with ui.form_field(label="Anything"):
                                ui.input(placeholder="Type something…")
                            ui.button("Submit", type="submit",
                                      color="primary")

                    ui.divider()

                    with ui.hstack(justify="between", align="center"):
                        ui.text("Live log (client-reactive — no refresh)",
                                color="muted", size="sm")
                        ui.button("Clear", variant="ghost", size="xs",
                                  on_click=cevents.log.clear())

                    log_text = ClientExpression(
                        '($bz.state.FormClientEvents.default.log'
                        ' || []).join("\\n") || "(no events yet)"'
                    )
                    ui.text(log_text,
                            color="muted", size="sm",
                            classes="font-mono whitespace-pre")

                    ui.divider()

                    emitted_html_block(
                        "Emitted HTML — client expression pushes the "
                        "event name onto the bound list, zero "
                        "round-trip. preventDefault() is part of the "
                        "expression, not implicit.",
                        serialize_html(ui.form(on_submit=_submit_expr)),
                    )

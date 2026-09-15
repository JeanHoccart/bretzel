"""Server-side handlers for the Form feature playground.

Module-level callables so Bretzel can address them via
``module::qualname``. The framework rejects lambdas / closures
upstream.

The 3 scenario handlers follow the same V2-native pattern :
1. Capture per-field validator failures via try/except over setattr.
2. ``FormError`` (whole-instance validator) routes to the ``form``
   key for the form-level Alert ; ``ValueError`` routes to the
   matching field's key for inline FormField error display.
3. Write the resulting errors into a ClientState — the delta carries
   them back to the client and FormField updates reactively via
   bz-show + bz-text. No manual refresh needed for the error path.
4. The card declares ``deps=[FormModel]``, so mutating the form on
   success (reset / saved_at) re-renders it automatically and the
   success branch shows (Alert / Notification / ✓ Logged in text).
"""

import datetime as _datetime

from bretzel import ui

from examples.playground.features.form.state import (
    AccountForm,
    DemoErrors,
    FormEvents,
    LoginForm,
    ProfileForm,
    SignupForm,
)


def submitted(**_kwargs) -> None:
    """No-op submit handler shared by the visual reference cards.

    Visual demos exist to show **shape**, not behaviour ; clicking
    Submit in those cards should be visually harmless (no toast, no
    Alert flash, no error display)."""


def demo_error_fire(**_kwargs) -> None:
    """Always-fail demo handler — writes a fake error into the
    DemoErrors ClientState every time. Lets the user click "Test
    error", see the FormField inline error appear, then type in
    the field to watch it auto-clear instantly. Pure Layer 2 + 4
    showcase with no HTML5 native validation involved."""

    errors = DemoErrors()
    errors.email = "Server says : this address looks suspicious."


def account_submit(form: AccountForm) -> None:
    """The V3 idiomatic handler. Contrast with ``login_submit`` below :
    no per-field ``setattr`` loop, no ``*Errors`` ClientState. ``form``
    arrives typed + validated ; the dispatcher collected any validator
    rejections into ``form.errors``. We just re-render so each
    ``form_field`` shows its inferred message (and keeps the user's raw
    text). On success, reset the model + toast."""

    if form.errors:
        return

    name = form.username
    form.username = ""
    form.email = ""
    ui.notification(
        f"Account '{name}' created!", title="Welcome", variant="success",
    )


def login_submit(form: LoginForm) -> None:
    """Per-field validators (email format, toy password check) run during
    hydration ; rejections land in ``form.errors`` and the form_fields show
    them inline (auto-clearing on edit). On success, flip ``logged_in``."""
    if form.errors:
        return
    form.logged_in = True


def signup_submit(form: SignupForm) -> None:
    """Per-field (email) + cross-field (passwords match → ``FormError`` →
    ``form.errors["_"]``) validation, all collected by the dispatcher in
    one pass. On success, fire a Notification toast."""
    if form.errors:
        return
    ui.notification(
        "Account created!", title="Welcome", variant="success",
    )


def profile_submit(form: ProfileForm) -> None:
    """Transformation validators normalise name/email during hydration ;
    a bad email raises (inline error). On success, stamp ``saved_at`` so
    the card shows the normalised values + timestamp."""
    if form.errors:
        return
    form.saved_at = _datetime.datetime.now().strftime("%H:%M:%S")


def log_submit(**_kwargs) -> None:
    """Canonical S4 event-log handler — appends to a live log, unlike
    the scenario handlers above which each do real domain work.
    Dedicated minimal form for the Server events card."""
    state = FormEvents()
    state.log = [*state.log, "submit"]


def clear_log() -> None:
    FormEvents().log = []

"""features/login — the public page: password, and the doors.

It touches no ``UserState``: that would raise ``AuthRequiredError`` as
long as nobody is signed in, which is exactly what the framework
guarantees — and a login page leaning on it would return 401 before
having signed anybody in.
"""

from __future__ import annotations

from bretzel import Feature, page, redirect, refreshable, ui
from bretzel.server import auth
from bretzel.state import PageState, field
from examples.auth.core.domain import (
    ALLOWED_DOMAIN,
    API_TOKENS,
    APP_PORT,
    LOGIN_PATH,
    PROXY_HEADER,
    authenticate,
    trusted_proxy,
)
from examples.auth.features.access import DOORS


class Credentials(PageState):
    email: str = field(default='')
    password: str = field(default='')
    error: str = field(default='')


def sign_in(form: Credentials) -> None:
    """The proof, then the session — two gestures, and only the second
    belongs to the framework.

    ``form.password`` is cleared before any return: a refused password
    must not come back in the field's HTML on re-render.
    """
    user = authenticate(str(form.email), str(form.password))
    form.password = ""
    if user is None:
        # We do not say which of the two causes failed — otherwise we
        # hand out the list of accounts that exist.
        form.error = "Wrong address or password."
        return
    form.error = ""
    auth.login(user["id"])
    redirect("/")


@refreshable(deps=[Credentials])
def sign_in_form() -> None:
    form = Credentials()
    with ui.form(on_submit=sign_in), ui.vstack(gap="md"):
        with ui.form_field(label="Address", required=True):
            ui.input(value=form.email, icon_left="mail",
                     placeholder="jean@macorp.fr", autocomplete="username")
        with ui.form_field(label="Password", required=True):
            ui.input(value=form.password, type="password", icon_left="lock",
                     autocomplete="current-password")
        if form.error:
            ui.alert(form.error, color="error", icon="triangle-alert",
                     # ``ui.alert`` does NOT set ``role="alert"`` by
                     # itself ("interrupt" semantics are unjustified for
                     # an info panel). Here we want it: a screen reader
                     # must announce the refusal.
                     role="alert")
        ui.button("Sign in", type="submit", color="primary",
                  icon_left="log-in")


def doors_block() -> None:
    """One button per mounted door — a plain link to its route.

    Nothing to wire: ``@auth.door`` mounted ``/auth/<name>``, and that
    route is public by construction (``app.public_paths``), so the guard
    lets it through without the app having to name it.
    """
    if not DOORS:
        return
    with ui.vstack(gap="sm"):
        ui.divider(label="or")
        for door in DOORS:
            ui.link(f"Continue with {door.name}", href=door.path,  # type: ignore[attr-defined]
                    classes="w-full")
        # Without this line, the refusal reads as a failure: you click,
        # you come back to this screen, and NOTHING says why. It happened
        # on the first real attempt — the person thought the door was
        # broken when it was doing exactly its job.
        ui.text(
            f"The test provider offers two accounts. "
            f"“jean@macorp.fr” gets in. "
            f"“someone@elsewhere.com” is REFUSED and brings you "
            f"back here: that is on purpose, the app only accepts the "
            f"{ALLOWED_DOMAIN} domain (the on_user function, in "
            f"features/access.py). A door proves an address; the app is "
            f"what decides.",
            size="xs", color="muted",
        )


def ways_panel() -> None:
    """The state of the four ways in, read at run time.

    This screen exists so nobody has to re-read the code to know what is
    wired: every line says what it is worth HERE, now, with the variable
    that turns it on.
    """
    token = next(iter(API_TOKENS))
    base = f"http://127.0.0.1:{APP_PORT}/"
    ways = [
        ("Password", True, "the form above"),
        (
            "OAuth / OIDC door",
            bool(DOORS),
            "the button above" if DOORS
            else "off — BZ_OIDC_ISSUER + CLIENT_ID + CLIENT_SECRET "
                 "are missing",
        ),
        (
            "Machine token",
            True,
            f'curl.exe -s -H "Authorization: Bearer {token}" {base}me',
        ),
        (
            "Header from an SSO proxy",
            trusted_proxy(),
            f'curl.exe -s -H "{PROXY_HEADER}: jean@macorp.fr" {base}me'
            if trusted_proxy()
            else "off — BZ_TRUST_PROXY_HEADER=1 is missing",
        ),
    ]
    with ui.vstack(gap="xs"):
        ui.divider(label="The four ways — all already live")
        ui.text(
            "Nothing to start one by one: what is ticked works right "
            "now. The last two have no screen — paste their command "
            "in a terminal while the app runs, and it answers three lines "
            "that say who you are.",
            size="xs", color="muted",
        )
        for label, active, detail in ways:
            with ui.vstack(gap="none"):
                with ui.hstack(gap="xs", align="center"):
                    ui.icon("circle-check" if active else "circle-dashed",
                            color="success" if active else "muted", size="sm")
                    ui.text(label, size="sm", weight="medium")
                ui.text(detail, size="xs", color="muted", classes="pl-6 break-all")
        ui.text(
            "⚠️ The “machine token” of this demo is a "
            "string in a dict, not a JWT. A real app would check a "
            "signature here — which changes nothing else: the "
            "function returns an identifier or None, and the framework "
            "does not know where it came from.",
            size="xs", color="muted",
        )


@page(LOGIN_PATH, title="Sign in")
def login_page() -> None:
    with ui.viewport(), ui.pane(align="center", justify="center", padding="md"):
        with ui.vstack(gap="lg", classes="w-full max-w-sm"):
            with ui.hstack(gap="sm", align="center", justify="center"):
                ui.icon("key-round", color="primary", size="lg")
                ui.heading("Four ways in", level=1, size="xl")
            with ui.card(padding="lg"), ui.vstack(gap="lg"):
                sign_in_form()
                doors_block()
                ways_panel()
            ui.text(
                "Demo accounts: jean@macorp.fr or ada@macorp.fr, "
                "password “demo”. The commands of the four ways "
                "are in examples/auth/README.md.",
                color="muted", size="xs",
            )


feature = Feature(
    name="login",
    kind="page",
    provides=[login_page, Credentials, sign_in, ways_panel],
    uses=["access"],
)

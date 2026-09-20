"""features/login — page: the sign-in, and the only public route.

What this screen puts under constraint: ``bretzel.auth``, which **none of
the 18 examples exercised** — neither `login`, nor `logout`, nor the
middleware guard, nor an anonymous ``UserState``'s 401. The docs and the
unit tests talked about it; nothing used it.

Three things this page does NOT do, and each is a decision:

- **it touches no ``UserState``.** ``ViewerPrefs`` would raise
  ``AuthRequiredError`` — which is precisely what the framework
  guarantees, and a sign-in page leaning on it would return 401 before
  having signed anybody in;
- **it does not say which of the two causes failed.** Distinguishing
  "unknown login" from "wrong password" hands whoever is trying the list
  of accounts that exist (cf. ``auth_data.authenticate``);
- **it does not set the cookie itself.** ``auth.login(id)`` does that,
  and performs the anti-fixation session rotation along the way — two
  things an example copying them would inevitably half do.
"""

from __future__ import annotations

from bretzel import Feature, page, redirect, refreshable, ui
from bretzel.server import auth
from bretzel.state import PageState, field
from examples.crm.core.domain import DEMO_PASSWORD, LOGIN_PATH, ROLES
from examples.crm.features.auth_data import all_users, authenticate


class Credentials(PageState):
    login: str = field(default='')
    password: str = field(default='')
    error: str = field(default='')


def sign_in(form: Credentials) -> None:
    """Verify, sign in, and send back to the pipeline.

    ``form.password`` is never rewritten into the state: a refused
    password must not come back in the field's HTML on re-render.
    """
    user = authenticate(str(form.login), str(form.password))
    form.password = ""
    if user is None:
        form.error = "Wrong login or password."
        return
    form.error = ""
    # The identifier travels as a STRING — it is ``login``'s contract,
    # and it is why ``auth_data.find_by_id`` converts it back.
    auth.login(str(user["id"]))
    redirect("/")


@refreshable(deps=[Credentials])
def sign_in_form() -> None:
    form = Credentials()
    with ui.form(on_submit=sign_in):
        with ui.vstack(gap="md"):
            with ui.form_field(label="Login", required=True):
                ui.input(value=form.login, icon_left="user",
                         placeholder="a.benali", autocomplete="username")
            with ui.form_field(label="Password", required=True):
                ui.input(value=form.password, type="password",
                         icon_left="lock",
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


def demo_accounts() -> None:
    """The demonstration accounts, written in clear.

    A real app would never do that. This one is a measuring instrument:
    hiding the trial data set would protect nothing and make the twelve
    screens unreachable.
    """
    with ui.vstack(gap="sm"):
        ui.divider(label="Demonstration accounts")
        ui.text(f"Mot de passe unique : « {DEMO_PASSWORD} »", color="muted",
                size="xs")
        # Read from the DATABASE. It used to be rebuilt from ``OWNERS``
        # — so adding an account to the seed made this list lie without
        # any test flinching.
        for user in all_users():
            director = user["role"] == "directeur"
            with ui.hstack(justify="between", align="center"):
                ui.text(user["login"], size="sm", weight="medium")
                ui.badge(ROLES[user["role"]], variant="soft",
                         color="primary" if director else "muted", size="xs")


@page(LOGIN_PATH, title="Sign in")
def login_page() -> None:
    """Without ``layout=``: the shell carries the app's navigation, and
    nobody is signed in yet to be entitled to it."""
    # The frame does not scroll, the pane does — on a short phone the
    # card does not fit, and the button must be reachable. It is the
    # composition, not a prop: a ``ui.viewport(scrolls=True)`` would have
    # been a boolean inverting the component's central property.
    with ui.viewport(), ui.pane(align="center", justify="center",
                                padding="md"):
        with ui.vstack(gap="lg", classes="w-full max-w-sm"):
            with ui.hstack(gap="sm", align="center", justify="center"):
                ui.icon("handshake", color="primary", size="lg")
                ui.heading("Bretzel CRM", level=1, size="xl")
            with ui.card(padding="lg"):
                with ui.vstack(gap="lg"):
                    sign_in_form()
                    demo_accounts()


feature = Feature(
    name="login",
    kind="page",
    provides=[login_page, Credentials],
    uses=["auth_data"],
)

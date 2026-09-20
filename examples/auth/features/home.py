"""features/home — the page behind the guard, and the proof of it all.

It reads a ``UserState``. That is what counts: this scope only exists if
there is an identity, and it works **identically** whether that identity
comes from the form, an OAuth door or a machine token. Before 2026-08-23
that was false — only the framework's cookie granted it, and an app that
resolved its own user got a 401.
"""

from __future__ import annotations

from bretzel import Feature, page, refresh, refreshable, ui
from bretzel.server import auth
from bretzel.state import UserState, field
from examples.auth.features.access import current_user, sign_out


class Preferences(UserState):
    """One state per person — the demonstration that an app identity
    opens the same doors as a framework identity."""

    visits: int = field(default=0)


def count_a_visit() -> None:
    prefs = Preferences()
    prefs.visits += 1
    refresh(identity_card)


@refreshable(deps=[Preferences])
def identity_card() -> None:
    user = current_user()
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(gap="sm", align="center"):
            ui.icon("user-round", color="primary")
            ui.heading(user["name"] if user else "Unknown", level=2, size="lg")
        with ui.vstack(gap="xs"):
            ui.text(f"user_id: {auth.user_id()}", size="sm", color="muted")
            ui.text(f"address: {user['email'] if user else '—'}",
                    size="sm", color="muted")
            ui.text(f"visits counted in a UserState: {Preferences().visits}",
                    size="sm", color="muted")
        with ui.hstack(gap="sm"):
            ui.button("Count a visit", on_click=count_a_visit,
                      variant="soft")
            ui.button("Sign out", on_click=sign_out, color="error",
                      variant="ghost", icon_left="log-out")


@page("/", title="Signed in")
def home_page() -> None:
    with ui.viewport(), ui.pane(align="center", justify="center", padding="md"):
        with ui.vstack(gap="lg", classes="w-full max-w-md"):
            ui.heading("You are in", level=1, size="xl")
            ui.text(
                "The app no longer knows through which door — and "
                "does not have to. That is the split: Bretzel owns the "
                "identity and its transport, the app owns the proof.",
                color="muted",
            )
            identity_card()


feature = Feature(
    name="home",
    kind="page",
    provides=[home_page, Preferences, identity_card, count_a_visit],
    uses=["access"],
)

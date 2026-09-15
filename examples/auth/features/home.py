"""features/home — la page derrière la garde, et la preuve du dispositif.

Elle lit un ``UserState``. C'est ce qui compte : ce scope n'existe que
s'il y a une identité, et il fonctionne **à l'identique** que celle-ci
vienne du formulaire, d'une porte OAuth ou d'un jeton de machine. Avant
le 2026-08-23 c'était faux — seul le cookie du framework y donnait
droit, et une app qui résolvait son propre utilisateur recevait 401.
"""

from __future__ import annotations

from bretzel import Feature, page, refresh, refreshable, ui
from bretzel.server import auth
from bretzel.state import UserState, field
from examples.auth.features.access import current_user, sign_out


class Preferences(UserState):
    """Un état par personne — la démonstration qu'une identité d'app
    ouvre les mêmes portes qu'une identité du framework."""

    visites: int = field(default=0)


def compter() -> None:
    prefs = Preferences()
    prefs.visites += 1
    refresh(identity_card)


@refreshable(deps=[Preferences])
def identity_card() -> None:
    user = current_user()
    with ui.card(padding="lg"), ui.vstack(gap="md"):
        with ui.hstack(gap="sm", align="center"):
            ui.icon("user-round", color="primary")
            ui.heading(user["name"] if user else "Inconnu", level=2, size="lg")
        with ui.vstack(gap="xs"):
            ui.text(f"user_id : {auth.user_id()}", size="sm", color="muted")
            ui.text(f"adresse : {user['email'] if user else '—'}", size="sm",
                    color="muted")
            ui.text(f"visites comptées dans un UserState : {Preferences().visites}",
                    size="sm", color="muted")
        with ui.hstack(gap="sm"):
            ui.button("Compter une visite", on_click=compter, variant="soft")
            ui.button("Se déconnecter", on_click=sign_out, color="error",
                      variant="ghost", icon_left="log-out")


@page("/", title="Connecté")
def home_page() -> None:
    with ui.viewport(), ui.pane(align="center", justify="center", padding="md"):
        with ui.vstack(gap="lg", classes="w-full max-w-md"):
            ui.heading("Vous êtes entré", level=1, size="xl")
            ui.text(
                "L'app ne sait plus par où — et n'a pas à le savoir. "
                "C'est le partage : Bretzel possède l'identité et son "
                "transport, l'app possède la preuve.",
                color="muted",
            )
            identity_card()


feature = Feature(
    name="home",
    kind="page",
    provides=[home_page, Preferences, identity_card, compter],
    uses=["access"],
)

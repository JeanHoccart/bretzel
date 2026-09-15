"""features/login — page : la connexion, et la seule route publique.

Ce que cet écran met sous contrainte : ``bretzel.auth``, qu'**aucun des 18
exemples n'exerçait** — ni `login`, ni `logout`, ni la garde
middleware, ni le 401 d'un ``UserState`` anonyme. La doc et les tests
unitaires en parlaient ; rien ne s'en servait.

Trois choses que cette page ne fait PAS, et chacune est une décision :

- **elle ne touche aucun ``UserState``.** ``ViewerPrefs`` lèverait
  ``AuthRequiredError`` — c'est précisément ce que le framework garantit,
  et une page de connexion qui s'appuierait dessus rendrait 401 avant
  d'avoir pu connecter qui que ce soit ;
- **elle ne dit pas laquelle des deux causes a échoué.** Distinguer
  « login inconnu » de « mot de passe faux » offre à qui essaie la liste
  des comptes qui existent (cf. ``auth_data.authenticate``) ;
- **elle ne pose pas le cookie elle-même.** ``auth.login(id)`` s'en
  charge, et fait au passage la rotation de session anti-fixation — deux
  choses qu'un exemple qui les recopierait ferait forcément à moitié.
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
    erreur: str = field(default='')


def sign_in(form: Credentials) -> None:
    """Vérifie, connecte, et renvoie vers le pipeline.

    ``form.password`` n'est jamais réécrit dans l'état : un mot de passe
    refusé ne doit pas revenir dans le HTML du champ au re-rendu.
    """
    user = authenticate(str(form.login), str(form.password))
    form.password = ""
    if user is None:
        form.erreur = "Identifiant ou mot de passe incorrect."
        return
    form.erreur = ""
    # L'identifiant voyage en CHAÎNE — c'est le contrat de ``login``, et
    # c'est pour ça que ``auth_data.find_by_id`` le reconvertit.
    auth.login(str(user["id"]))
    redirect("/")


@refreshable(deps=[Credentials])
def sign_in_form() -> None:
    form = Credentials()
    with ui.form(on_submit=sign_in):
        with ui.vstack(gap="md"):
            with ui.form_field(label="Identifiant", required=True):
                ui.input(value=form.login, icon_left="user",
                         placeholder="a.benali", autocomplete="username")
            with ui.form_field(label="Mot de passe", required=True):
                ui.input(value=form.password, type="password",
                         icon_left="lock",
                         autocomplete="current-password")
            if form.erreur:
                ui.alert(form.erreur, color="error", icon="triangle-alert",
                     # ``ui.alert`` ne pose PAS ``role="alert"`` tout seul
                     # (sémantique « interromps » injustifiée pour un
                     # panneau d'info). Ici on la veut : un lecteur
                     # d'écran doit annoncer le refus.
                     role="alert")
            ui.button("Se connecter", type="submit", color="primary",
                      icon_left="log-in")


def demo_accounts() -> None:
    """Les comptes de démonstration, écrits en clair.

    Une app réelle ne ferait jamais ça. Celle-ci est un instrument de
    mesure : cacher le jeu d'essai ne protégerait rien et rendrait les
    douze écrans inatteignables.
    """
    with ui.vstack(gap="sm"):
        ui.divider(label="Comptes de démonstration")
        ui.text(f"Mot de passe unique : « {DEMO_PASSWORD} »", color="muted",
                size="xs")
        # Lue en BASE. Elle était refabriquée depuis ``OWNERS`` — donc
        # ajouter un compte au semis faisait mentir cette liste sans
        # qu'aucun test ne bronche.
        for user in all_users():
            director = user["role"] == "directeur"
            with ui.hstack(justify="between", align="center"):
                ui.text(user["login"], size="sm", weight="medium")
                ui.badge(ROLES[user["role"]], variant="soft",
                         color="primary" if director else "muted", size="xs")


@page(LOGIN_PATH, title="Connexion")
def login_page() -> None:
    """Sans ``layout=`` : la coque porte la navigation de l'app, et personne
    n'est encore connecté pour y avoir droit."""
    # Le cadre ne défile pas, le pane si — sur un téléphone bas la carte
    # ne tient pas, et il faut pouvoir atteindre le bouton. C'est la
    # composition, pas une prop : un ``ui.viewport(scrolls=True)`` aurait
    # été un booléen qui inverse la propriété centrale du composant.
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

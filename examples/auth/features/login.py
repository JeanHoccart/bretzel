"""features/login — la page publique : mot de passe, et les portes.

Elle ne touche aucun ``UserState`` : celui-ci lèverait ``AuthRequiredError``
tant que personne n'est connecté, ce qui est exactement ce que le
framework garantit — et une page de connexion qui s'appuierait dessus
rendrait 401 avant d'avoir pu connecter qui que ce soit.
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
    erreur: str = field(default='')


def sign_in(form: Credentials) -> None:
    """La preuve, puis la session — deux gestes, et seul le second est
    du framework.

    ``form.password`` est vidé avant tout retour : un mot de passe refusé
    ne doit pas revenir dans le HTML du champ au re-rendu.
    """
    user = authenticate(str(form.email), str(form.password))
    form.password = ""
    if user is None:
        # On ne dit pas laquelle des deux causes a échoué — sinon on offre
        # la liste des comptes qui existent.
        form.erreur = "Adresse ou mot de passe incorrect."
        return
    form.erreur = ""
    auth.login(user["id"])
    redirect("/")


@refreshable(deps=[Credentials])
def sign_in_form() -> None:
    form = Credentials()
    with ui.form(on_submit=sign_in), ui.vstack(gap="md"):
        with ui.form_field(label="Adresse", required=True):
            ui.input(value=form.email, icon_left="mail",
                     placeholder="jean@macorp.fr", autocomplete="username")
        with ui.form_field(label="Mot de passe", required=True):
            ui.input(value=form.password, type="password", icon_left="lock",
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


def doors_block() -> None:
    """Un bouton par porte montée — un simple lien vers sa route.

    Rien à câbler : ``@auth.door`` a monté ``/auth/<nom>``, et cette
    route est publique par construction (``app.public_paths``), donc la
    garde la laisse passer sans que l'app ait à la nommer.
    """
    if not DOORS:
        return
    with ui.vstack(gap="sm"):
        ui.divider(label="ou")
        for door in DOORS:
            ui.link(f"Continuer avec {door.name}", href=door.path,  # type: ignore[attr-defined]
                    classes="w-full")
        # Sans cette ligne, le refus se lit comme une panne : on clique,
        # on revient sur cet écran, et RIEN ne dit pourquoi. C'est arrivé
        # au premier essai réel — la personne a cru que la porte était
        # cassée alors qu'elle faisait exactement son travail.
        ui.text(
            f"Le fournisseur de test propose deux comptes. « jean@macorp.fr » "
            f"entre. « someone@ailleurs.com » est REFUSÉ et te ramène ici : "
            f"c'est voulu, l'app n'accepte que le domaine {ALLOWED_DOMAIN} "
            f"(la fonction on_user, dans features/access.py). Une porte "
            f"prouve une adresse ; c'est l'app qui décide.",
            size="xs", color="muted",
        )


def ways_panel() -> None:
    """L'état des quatre façons d'entrer, lu à l'exécution.

    Cet écran existe pour qu'on n'ait pas à relire le code pour savoir ce
    qui est branché : chaque ligne dit ce qu'elle vaut ICI, maintenant,
    avec la variable qui l'allume.
    """
    token = next(iter(API_TOKENS))
    base = f"http://127.0.0.1:{APP_PORT}/"
    ways = [
        ("Mot de passe", True, "le formulaire ci-dessus"),
        (
            "Porte OAuth / OIDC",
            bool(DOORS),
            "le bouton ci-dessus" if DOORS
            else "éteinte — il manque BZ_OIDC_ISSUER + CLIENT_ID + CLIENT_SECRET",
        ),
        (
            "Jeton de machine",
            True,
            f'curl.exe -s -H "Authorization: Bearer {token}" {base}moi',
        ),
        (
            "En-tête d'un proxy SSO",
            trusted_proxy(),
            f'curl.exe -s -H "{PROXY_HEADER}: jean@macorp.fr" {base}moi'
            if trusted_proxy()
            else "éteinte — il manque BZ_TRUST_PROXY_HEADER=1",
        ),
    ]
    with ui.vstack(gap="xs"):
        ui.divider(label="Les quatre façons — toutes déjà actives")
        ui.text(
            "Rien à démarrer une par une : ce qui est coché marche "
            "maintenant. Les deux dernières n'ont pas d'écran — colle leur "
            "commande dans un terminal pendant que l'app tourne, elle "
            "répond trois lignes qui disent qui tu es.",
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
            "⚠️ Le « jeton de machine » de cette démo est une chaîne dans un "
            "dict, pas un JWT. Une vraie app vérifierait ici une signature "
            "— ça ne change rien au reste : la fonction rend un identifiant "
            "ou None, et le framework ne sait pas d'où il vient.",
            size="xs", color="muted",
        )


@page(LOGIN_PATH, title="Connexion")
def login_page() -> None:
    with ui.viewport(), ui.pane(align="center", justify="center", padding="md"):
        with ui.vstack(gap="lg", classes="w-full max-w-sm"):
            with ui.hstack(gap="sm", align="center", justify="center"):
                ui.icon("key-round", color="primary", size="lg")
                ui.heading("Quatre façons d'entrer", level=1, size="xl")
            with ui.card(padding="lg"), ui.vstack(gap="lg"):
                sign_in_form()
                doors_block()
                ways_panel()
            ui.text(
                "Comptes de démonstration : jean@macorp.fr ou ada@macorp.fr, "
                "mot de passe « demo ». Les commandes des quatre façons "
                "sont dans examples/auth/README.md.",
                color="muted", size="xs",
            )


feature = Feature(
    name="login",
    kind="page",
    provides=[login_page, Credentials, sign_in, ways_panel],
    uses=["access"],
)

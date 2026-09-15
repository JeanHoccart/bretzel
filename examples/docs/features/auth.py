"""SUJET — L'authentification.

Le partage a été écrit le 2026-08-24, et il n'est pas celui qu'on croit :

**Bretzel possède l'identité et son transport** — le cookie signé, son
expiration, sa rotation anti-fixation, la chaîne de lecture
``@auth.source``, les portes OAuth/OIDC ``@auth.door``, et le scope
``UserState`` qui n'existe QUE par cette auth.

**L'app possède la preuve** — le mot de passe, la table des comptes, les
rôles, et la décision d'accepter cette personne.

⚠️ L'ancienne ligne du charter — « juste les hooks middleware, l'app
fait son auth » — était fausse dans les deux sens : le framework livrait
déjà bien plus, et une app qui résolvait son utilisateur toute seule
recevait un 401.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/auth"


@page(PATH, layout=shell, title="Authentification")
def auth_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("L'authentification", level=1, size="3xl")
            ui.text(
                "Bretzel tient l'identité et son transport. Votre app "
                "tient la preuve — et c'est la seule décision qui vous "
                "appartienne vraiment : accepter cette personne, ou non.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Qui fait quoi", level=2)
                    ui.table(
                        columns=[
                            ui.column("quoi", label="Ce dont il s'agit"),
                            ui.column("qui", label="Qui le porte"),
                        ],
                        rows=[
                            {"quoi": "le cookie signé, son expiration, sa "
                                     "rotation anti-fixation",
                             "qui": "Bretzel"},
                            {"quoi": "d'où une identité peut venir "
                                     "(`@auth.source`)",
                             "qui": "Bretzel — vous branchez la source"},
                            {"quoi": "les portes OAuth2 / OIDC "
                                     "(`@auth.door`)",
                             "qui": "Bretzel — route, échange de jeton, "
                                    "cookie"},
                            {"quoi": "le scope `UserState`",
                             "qui": "Bretzel — il n'existe QUE par cette "
                                    "auth"},
                            {"quoi": "les mots de passe, la table des "
                                     "comptes, les rôles",
                             "qui": "votre app"},
                            {"quoi": "la page de connexion",
                             "qui": "votre app"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Entrer par un compte Google", level=2)
                    ui.text(
                        "Une porte OIDC se déclare, et le décorateur "
                        "monte sa route, échange le jeton et pose le "
                        "cookie. Ce qui reste à écrire est la décision : "
                        "rendre `None` REFUSE.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "from bretzel import auth, oauth\n"
                        "\n"
                        "@auth.door(oauth.OIDC(\n"
                        "    name=\"google\",\n"
                        "    issuer=\"https://accounts.google.com\",\n"
                        "    client_id=CLIENT_ID,\n"
                        "    client_secret=CLIENT_SECRET,\n"
                        "))\n"
                        "def entree(profil) -> str | None:\n"
                        "    \"\"\"Le SEUL filtre entre « cette personne a un\n"
                        "    compte chez Google » et « cette personne entre\n"
                        "    chez moi ». Sans lui, la porte est ouverte à\n"
                        "    la planète entière.\"\"\"\n"
                        "    if not profil.email.endswith(\"@monentreprise.fr\"):\n"
                        "        return None\n"
                        "    return profil.email      # l'identifiant retenu\n",
                        lang="python",
                    )
                    ui.text(
                        "`@auth.door` S'EMPILE : deux portes peuvent "
                        "aboutir à la même fonction, ce qui est le cas "
                        "courant quand on accepte Google ET Microsoft. "
                        "`oauth.OAuth2` couvre les fournisseurs sans "
                        "OIDC, où l'on donne les trois URL à la main.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Sans OAuth : la source d'identité",
                               level=2)
                    ui.text(
                        "`@auth.source` dit D'OÙ une identité peut "
                        "venir — un jeton d'API, un en-tête posé par un "
                        "proxy de confiance, une session maison. La "
                        "fonction rend un identifiant, ou `None`.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "@auth.source\n"
                        "def depuis_le_jeton(requete) -> str | None:\n"
                        "    jeton = requete.headers.get(\"x-api-key\")\n"
                        "    return comptes.par_jeton(jeton)      # ou None\n"
                        "\n"
                        "# Après une vérification de mot de passe, à vous :\n"
                        "auth.login(utilisateur.id)\n"
                        "auth.logout()\n"
                        "auth.user_id()          # str | None\n"
                        "auth.is_authenticated() # bool\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Le scope qui en dépend", level=2)
                    ui.text(
                        "`UserState` est le seul des quatre scopes "
                        "serveur qui exige une identité. C'est ce qui "
                        "rendait le partage confus : une app qui "
                        "résolvait son utilisateur elle-même, sans passer "
                        "par `auth`, recevait un 401 en touchant ce "
                        "scope.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Preferences(UserState):\n"
                        "    theme: str = field(default=\"clair\")\n"
                        "\n"
                        "# Lisible dès qu'`auth.user_id()` rend quelque chose.\n"
                        "Preferences().theme = \"sombre\"\n",
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Ce qui n'est PAS livré", level=2)
                    ui.text(
                        "Pas de page de connexion fournie, pas de "
                        "gestion de mots de passe, pas de rôles ni de "
                        "permissions, pas de SAML. Et pas Apple : son "
                        "`client_secret` est un JWT ES256, donc une "
                        "dépendance cryptographique que le framework "
                        "refuse d'ajouter pour un fournisseur.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "`examples/auth` montre les quatre façons "
                        "d'entrer côte à côte, et tourne.",
                        color="muted", size="sm",
                    )

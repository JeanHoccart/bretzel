"""TOPIC — Authentication.

The split was written on 2026-08-24, and it is not the one people think:

**Bretzel owns the identity and its transport** — the signed cookie, its
expiry, its anti-fixation rotation, the ``@auth.source`` read chain, the
``@auth.door`` OAuth/OIDC doors, and the ``UserState`` scope that exists
ONLY through that auth.

**The app owns the proof** — the password, the accounts table, the
roles, and the decision to accept this person.

⚠️ The charter's old line — "just the middleware hooks, the app does its
own auth" — was wrong in both directions: the framework already shipped
far more, and an app resolving its own user got a 401.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/auth"


@page(PATH, layout=shell, title="Authentification")
def auth_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("L'authentification", level=1, size="3xl")
            ui.text(
                tr('Bretzel holds the identity and its transport. Your app '
                   'holds the proof — and that is the only decision that is '
                   'really yours: accepting this person, or not.',
                   "Bretzel tient l'identité et son transport. Votre app "
                   "tient la preuve — et c'est la seule décision qui vous "
                   'appartienne vraiment : accepter cette personne, ou non.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Who does what',
                                  'Qui fait quoi'), level=2)
                    ui.table(
                        columns=[
                            ui.column("quoi", label="Ce dont il s'agit"),
                            ui.column(tr('who',
                                         'qui'), label=tr('Who carries it',
                                                      'Qui le porte')),
                        ],
                        rows=[
                            {"quoi": tr('the signed cookie, its expiry, its '
                                        'anti-fixation rotation',
                                        'le cookie signé, son expiration, sa '
                                        'rotation anti-fixation'),
                             tr('who',
                                'qui'): "Bretzel"},
                            {"quoi": tr('where an identity can come from '
                                        '(`@auth.source`)',
                                        "d'où une identité peut venir "
                                        '(`@auth.source`)'),
                             tr('who',
                                'qui'): tr('Bretzel — you wire the source',
                                       'Bretzel — vous branchez la source')},
                            {"quoi": tr('the OAuth2 / OIDC doors '
                                        '(`@auth.door`)',
                                        'les portes OAuth2 / OIDC '
                                        '(`@auth.door`)'),
                             tr('who',
                                'qui'): tr('Bretzel — route, token exchange, '
                                       'cookie',
                                       'Bretzel — route, échange de jeton, '
                                       'cookie')},
                            {"quoi": tr('the `UserState` scope',
                                        'le scope `UserState`'),
                             tr('who',
                                'qui'): tr('Bretzel — it exists ONLY through that'
                                       ' auth',
                                       "Bretzel — il n'existe QUE par cette "
                                       'auth')},
                            {"quoi": tr('the passwords, the account table, '
                                        'the roles',
                                        'les mots de passe, la table des '
                                        'comptes, les rôles'),
                             tr('who',
                                'qui'): "votre app"},
                            {"quoi": tr('the sign-in page',
                                        'la page de connexion'),
                             tr('who',
                                'qui'): "votre app"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Signing in with a Google account',
                                  'Entrer par un compte Google'), level=2)
                    ui.text(
                        tr('An OIDC door is declared, and the decorator '
                           'mounts its route, exchanges the token and sets '
                           'the cookie. What is left to write is the '
                           'decision: returning `None` REFUSES.',
                           'Une porte OIDC se déclare, et le décorateur monte'
                           ' sa route, échange le jeton et pose le cookie. Ce'
                           ' qui reste à écrire est la décision : rendre '
                           '`None` REFUSE.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('from bretzel import auth, oauth\n\n@auth.door(oauth.OIDC(\n    name="google",\n    issuer="https://accounts.google.com",\n    client_id=CLIENT_ID,\n    client_secret=CLIENT_SECRET,\n))\ndef way_in(profile) -> str | None:\n    """The ONLY filter between “this person has a\n    Google account” and “this person comes into my\n    app”. Without it, the door is open to the whole\n    planet."""\n    if not profile.email.endswith("@mycompany.com"):\n        return None\n    return profile.email     # the identifier kept\n',
                           'from bretzel import auth, oauth\n\n@auth.door(oauth.OIDC(\n    name="google",\n    issuer="https://accounts.google.com",\n    client_id=CLIENT_ID,\n    client_secret=CLIENT_SECRET,\n))\ndef entree(profil) -> str | None:\n    """Le SEUL filtre entre « cette personne a un\n    compte chez Google » et « cette personne entre\n    chez moi ». Sans lui, la porte est ouverte à\n    la planète entière."""\n    if not profil.email.endswith("@monentreprise.fr"):\n        return None\n    return profil.email      # l\'identifiant retenu\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('`@auth.door` STACKS: two doors can end at the '
                           'same function, which is the common case when one '
                           'accepts Google AND Microsoft. `oauth.OAuth2` '
                           'covers the providers with no OIDC, where the '
                           'three URLs are given by hand.',
                           "`@auth.door` S'EMPILE : deux portes peuvent "
                           'aboutir à la même fonction, ce qui est le cas '
                           'courant quand on accepte Google ET Microsoft. '
                           '`oauth.OAuth2` couvre les fournisseurs sans OIDC,'
                           " où l'on donne les trois URL à la main."),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Without OAuth: the identity source',
                                  "Sans OAuth : la source d'identité"),
                               level=2)
                    ui.text(
                        tr('`@auth.source` says WHERE an identity can come '
                           'from — an API token, a header set by a trusted '
                           'proxy, a home-made session. The function returns '
                           'an identifier, or `None`.',
                           "`@auth.source` dit D'OÙ une identité peut venir —"
                           " un jeton d'API, un en-tête posé par un proxy de "
                           'confiance, une session maison. La fonction rend '
                           'un identifiant, ou `None`.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('@auth.source\ndef from_the_token(request) -> str | None:\n    token = request.headers.get("x-api-key")\n    return accounts.by_token(token)      # or None\n\n# After a password check, over to you:\nauth.login(user.id)\nauth.logout()\nauth.user_id()          # str | None\nauth.is_authenticated() # bool\n',
                           '@auth.source\ndef depuis_le_jeton(requete) -> str | None:\n    jeton = requete.headers.get("x-api-key")\n    return comptes.par_jeton(jeton)      # ou None\n\n# Après une vérification de mot de passe, à vous :\nauth.login(utilisateur.id)\nauth.logout()\nauth.user_id()          # str | None\nauth.is_authenticated() # bool\n'),
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The scope that depends on it',
                                  'Le scope qui en dépend'), level=2)
                    ui.text(
                        tr('`UserState` is the only one of the four server '
                           'scopes that demands an identity. That is what '
                           'made the split confusing: an app resolving its '
                           'own user, without going through `auth`, received '
                           'a 401 on touching that scope.',
                           '`UserState` est le seul des quatre scopes serveur'
                           " qui exige une identité. C'est ce qui rendait le "
                           'partage confus : une app qui résolvait son '
                           'utilisateur elle-même, sans passer par `auth`, '
                           'recevait un 401 en touchant ce scope.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('class Preferences(UserState):\n    theme: str = field(default="light")\n\n# Readable as soon as `auth.user_id()` returns something.\nPreferences().theme = "dark"\n',
                           'class Preferences(UserState):\n    theme: str = field(default="clair")\n\n# Lisible dès qu\'`auth.user_id()` rend quelque chose.\nPreferences().theme = "sombre"\n'),
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What is NOT shipped',
                                  "Ce qui n'est PAS livré"), level=2)
                    ui.text(
                        tr('No sign-in page supplied, no password handling, '
                           'no roles and no permissions, no SAML. And not '
                           'Apple: its `client_secret` is an ES256 JWT, hence'
                           ' a cryptographic dependency the framework refuses'
                           ' to add for one provider.',
                           'Pas de page de connexion fournie, pas de gestion '
                           'de mots de passe, pas de rôles ni de permissions,'
                           ' pas de SAML. Et pas Apple : son `client_secret` '
                           'est un JWT ES256, donc une dépendance '
                           "cryptographique que le framework refuse d'ajouter"
                           ' pour un fournisseur.'),
                        color="muted", size="sm",
                    )
                    ui.text(
                        tr('`examples/auth` shows the four ways in side by '
                           'side, and it runs.',
                           "`examples/auth` montre les quatre façons d'entrer"
                           ' côte à côte, et tourne.'),
                        color="muted", size="sm",
                    )

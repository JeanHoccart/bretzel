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

PATH = "/auth"


@page(PATH, layout=shell, title="Authentication · Bretzel docs",
      description="Authentication in Bretzel: signed-cookie identity, OAuth and OIDC doors such as Google sign-in, and the one decision your app owns.")
def auth_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Authentication", level=1, size="3xl")
            ui.text(
                'Bretzel holds the identity and its transport. Your app '
                'holds the proof — and that is the only decision that is '
                'really yours: accepting this person, or not.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Who does what', level=2)
                    ui.table(
                        columns=[
                            ui.column("quoi", label="What it is"),
                            ui.column('who', label='Who carries it'),
                        ],
                        rows=[
                            {"quoi": 'the signed cookie, its expiry, its '
                                     'anti-fixation rotation',
                             'who': "Bretzel"},
                            {"quoi": 'where an identity can come from '
                                     '(`@auth.source`)',
                             'who': 'Bretzel — you wire the source'},
                            {"quoi": 'the OAuth2 / OIDC doors '
                                     '(`@auth.door`)',
                             'who': 'Bretzel — route, token exchange, '
                                    'cookie'},
                            {"quoi": 'the `UserState` scope',
                             'who': 'Bretzel — it exists ONLY through that'
                                    ' auth'},
                            {"quoi": 'the passwords, the account table, '
                                     'the roles',
                             'who': "your app"},
                            {"quoi": 'the sign-in page',
                             'who': "your app"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Signing in with a Google account', level=2)
                    ui.text(
                        'An OIDC door is declared, and the decorator '
                        'mounts its route, exchanges the token and sets '
                        'the cookie. What is left to write is the '
                        'decision: returning `None` REFUSES.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'from bretzel import auth, oauth\n\n@auth.door(oauth.OIDC(\n    name="google",\n    issuer="https://accounts.google.com",\n    client_id=CLIENT_ID,\n    client_secret=CLIENT_SECRET,\n))\ndef way_in(profile) -> str | None:\n    """The ONLY filter between “this person has a\n    Google account” and “this person comes into my\n    app”. Without it, the door is open to the whole\n    planet."""\n    if not profile.email.endswith("@mycompany.com"):\n        return None\n    return profile.email     # the identifier kept\n',
                        lang="python",
                    )
                    ui.text(
                        '`@auth.door` STACKS: two doors can end at the '
                        'same function, which is the common case when one '
                        'accepts Google AND Microsoft. `oauth.OAuth2` '
                        'covers the providers with no OIDC, where the '
                        'three URLs are given by hand.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Without OAuth: the identity source',
                               level=2)
                    ui.text(
                        '`@auth.source` says WHERE an identity can come '
                        'from — an API token, a header set by a trusted '
                        'proxy, a home-made session. The function returns '
                        'an identifier, or `None`.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '@auth.source\ndef from_the_token(request) -> str | None:\n    token = request.headers.get("x-api-key")\n    return accounts.by_token(token)      # or None\n\n# After a password check, over to you:\nauth.login(user.id)\nauth.logout()\nauth.user_id()          # str | None\nauth.is_authenticated() # bool\n',
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The scope that depends on it', level=2)
                    ui.text(
                        '`UserState` is the only one of the four server '
                        'scopes that demands an identity. That is what '
                        'made the split confusing: an app resolving its '
                        'own user, without going through `auth`, received '
                        'a 401 on touching that scope.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'class Preferences(UserState):\n    theme: str = field(default="light")\n\n# Readable as soon as `auth.user_id()` returns something.\nPreferences().theme = "dark"\n',
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading('What is NOT shipped', level=2)
                    ui.text(
                        'No sign-in page supplied, no password handling, '
                        'no roles and no permissions, no SAML. And not '
                        'Apple: its `client_secret` is an ES256 JWT, hence'
                        ' a cryptographic dependency the framework refuses'
                        ' to add for one provider.',
                        color="muted", size="sm",
                    )

# Sign in with a password

> I need a sign-in page with an email and a password, and an /account page that only signed-in users can see.

Save it as `app.py`, run `bretzel dev app:app`, open http://127.0.0.1:8000 and sign in as `ada@example.com` with the password `analytical-engine`.

```python
"""Sign in with a password; /account is for signed-in people only."""

import hashlib
import hmac
import secrets
import sys

from bretzel import Bretzel, auth, page, redirect, refreshable, ui
from bretzel.state import PageState, field


def hash_password(password: str, salt: str = "") -> str:
    """``salt:digest`` in hex: what the accounts table stores, never the password."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return f"{salt}:{digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    salt = stored.split(":")[0]
    return hmac.compare_digest(hash_password(password, salt), stored)


# The accounts table. In a real app: a table of your database, filled by a
# sign-up page. The demo account's password is "analytical-engine".
ACCOUNTS = {
    "ada@example.com": {"name": "Ada Lovelace", "password_hash": hash_password("analytical-engine")},
}


class SignIn(PageState):
    email: str = field(default="")
    password: str = field(default="")
    error: str = field(default="")


def sign_in(form: SignIn) -> None:
    email = str(form.email).strip().lower()
    account = ACCOUNTS.get(email)
    accepted = account is not None and password_matches(str(form.password), account["password_hash"])
    form.password = ""
    if not accepted:
        form.error = "Wrong email or password."
        return
    auth.login(email)
    redirect("/account")


def sign_out() -> None:
    auth.logout()
    redirect("/login")


@refreshable
def sign_in_form() -> None:
    form = SignIn()
    with ui.form(on_submit=sign_in), ui.vstack(gap="md"):
        with ui.form_field(label="Email", required=True):
            ui.input(value=form.email, type="email", autocomplete="username")
        with ui.form_field(label="Password", required=True):
            ui.input(value=form.password, type="password", autocomplete="current-password")
        if form.error:
            ui.alert(form.error, color="error", role="alert")
        ui.button("Sign in", type="submit", color="primary", icon_left="log-in")


@page("/login", title="Sign in")
def login_page() -> None:
    with ui.container(width="sm", classes="py-16"), ui.vstack(gap="lg"):
        ui.heading("Sign in", level=1)
        sign_in_form()


@page("/account", title="Your account")
def account_page() -> None:
    email = auth.user_id()
    if email not in ACCOUNTS:
        redirect("/login")  # while a page renders, this answers a redirect
        return
    with ui.container(width="sm", classes="py-16"), ui.vstack(gap="lg"):
        ui.heading("Your account", level=1)
        ui.text(f"Signed in as {ACCOUNTS[email]['name']} ({email}).")
        ui.button("Sign out", variant="outline", icon_left="log-out", on_click=sign_out)


@page("/")
def home() -> None:
    redirect("/account")


app = Bretzel(title="Sign in")
app.include(sys.modules[__name__])
```

## Why it works

- Bretzel carries the identity: `auth.login(email)` sets a signed cookie, `auth.user_id()` reads it back, `auth.logout()` clears it. The app owns the proof: the accounts table and the password check, against a salted PBKDF2 hash compared with `hmac.compare_digest`.
- `redirect()` called while a page renders answers a redirect: `/account` sends a stranger to `/login`. Called from a handler, it sends the browser to the new page.
- The form sits in a `@refreshable`, so the error shows; the password is cleared before returning, so it never comes back in the page.
- **The trap: this guards one page.** To guard many, write one `@app.middleware` that sends every non-public path to `/login` with `redirect_response(request, "/login")`, and keep the sign-in action public with `action_path(sign_in)` (both from `bretzel.server`), or the button looks dead.

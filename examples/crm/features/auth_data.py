"""features/auth_data — data: the user accounts table.

The framework does not model a user beyond their identifier:
``bretzel.auth`` remembers "this request belongs to X" in a signed
cookie, and exposes four functions to write and read it back. **The
profile, the role and the password belong to the app** — it is written in
the module.

This feature is therefore the half the CRM brings, on the data side. The
hashing lives in ``core/security.py`` (standard library, PBKDF2), and the
"who sees what" decision lives in ``access.py`` — three distinct things,
three places.
"""

from __future__ import annotations

from bretzel import Feature

from examples.crm.core.db import query
from examples.crm.core.security import verify_password


def find_by_login(login: str) -> dict | None:
    """An account by its login, or ``None``.

    ``COLLATE NOCASE``: a login gets typed, and refusing "A.Benali"
    because a capital was entered is a frustration with no upside — the
    uniqueness is already guaranteed by the column constraint.
    """
    rows = query(
        "SELECT * FROM users WHERE login = ? COLLATE NOCASE", (login.strip(),)
    )
    return rows[0] if rows else None


def all_users() -> list[dict]:
    """The accounts, for the sign-in's demonstration list.

    Read from the DATABASE rather than rebuilt from ``OWNERS``: the
    sign-in page reconstructed it by hand, so adding an account to the
    seed made it lie in silence. ``role`` first: "commercial" sorts
    before "directeur".
    """
    return query(
        "SELECT login, display_name, role FROM users ORDER BY role, login"
    )


def find_by_id(user_id: str) -> dict | None:
    """An account by the identifier the authentication cookie carries.

    ``bretzel.auth`` only carries a **string** — it is what its docstring
    says, and it is why we convert it back here rather than assume an
    integer elsewhere. A signed cookie whose user has been deleted
    returns ``None``, and the caller treats that as anonymous.
    """
    if not user_id.isdigit():
        return None
    rows = query("SELECT * FROM users WHERE id = ?", (int(user_id),))
    return rows[0] if rows else None


def authenticate(login: str, password: str) -> dict | None:
    """The account if the credentials are right, ``None`` otherwise.

    ⚠️ **A single failure message for both causes**, and it is
    deliberate: distinguishing "unknown login" from "wrong password"
    gives whoever is trying the list of accounts that exist. So the
    caller only receives a ``None``, and has nothing to be more talkative
    with.

    ⚠️ We verify the password **even when the login does not exist** —
    against a dummy digest. Otherwise the response time betrays the
    account's existence: a few milliseconds for an unknown login,
    240 000 PBKDF2 iterations for a known one.
    """
    user = find_by_login(login)
    stored = user["password_hash"] if user else _DUMMY_HASH
    ok = verify_password(password, stored)
    return user if ok else None


#: A valid digest of a password nobody has. It exists only to give
#: :func:`authenticate` something to verify when the login is unknown —
#: cf. its docstring.
_DUMMY_HASH = (
    "pbkdf2_sha256$240000$"
    "00000000000000000000000000000000$"
    "0000000000000000000000000000000000000000000000000000000000000000"
)


feature = Feature(
    name="auth_data",
    kind="data",
    provides=[find_by_login, find_by_id, all_users, authenticate],
    uses=["db"],
)

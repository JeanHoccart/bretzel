"""core/security — password hashing. The standard library, nothing else.

**The app owns this, and it is written in the framework**:
``bretzel.auth`` says in so many words "Bretzel doesn't model users
beyond their string ID. Apps own their profile / role / password
machinery". The four functions it exposes only remember *which*
identifier is signed in, in a signed cookie — they do not know what a
password is, and must not know.

This module is therefore the half the CRM brings. It fits in two
functions because ``hashlib`` does all the work:

- **PBKDF2-HMAC-SHA256**, 240 000 iterations, a 16-byte salt per user. No
  argon2 and no bcrypt: those are dependencies, and the charter insists
  an example adds none. PBKDF2 has been in the standard library forever
  and remains an acceptable answer;
- **constant-time comparison** (``hmac.compare_digest``). A ``==`` on
  digests leaks their common prefix through the response time.

⚠️ The stored format carries ITS parameters
(``pbkdf2_sha256$<iters>$<salt>$<key>``) rather than reading them from a
module constant. That is what allows raising the iteration count later
without invalidating the existing accounts: every digest knows how it was
computed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: Today's cost. It lives in the digest, not only here — cf. the
#: module's docstring.
ITERATIONS = 240_000
ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """``pbkdf2_sha256$<iterations>$<salt hex>$<key hex>``.

    ``salt=`` is only there for the seed, which must be
    **deterministic**: two machines seeding the same database must get
    the same rows. An account created by the app always takes a random
    salt.
    """
    if salt is None:
        salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    )
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Does the password match the stored digest?

    Returns ``False`` on a malformed digest rather than raising: a
    damaged row in the database must not become a 500 on the sign-in
    page, where it would be a signal to whoever provoked it.
    """
    try:
        algorithm, iterations, salt_hex, expected_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), expected_hex)

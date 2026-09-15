"""Key derivation + signing primitives for the security layer.

One ``secret_key`` is configured on :class:`BretzelConfig` ; every
HMAC-protected surface in the framework (action signing, auth cookie,
CSRF token) uses a **purpose-specific** key derived from that master
secret. A leak of one derived key does not compromise the others.

Derivation is HMAC-SHA256 of the purpose label under the master key
— a single-block HMAC-based KDF that produces an independent 32-byte
key per purpose. We don't need the full HKDF Extract+Expand pipeline
of RFC 5869 because the master is already high-entropy at config
construction (validated ≥16 chars, recommended 64). The purpose
labels carry a version suffix (``.v1``) so we can rotate them in a
future major release without breaking existing tokens.

"""

from __future__ import annotations

import hashlib
import hmac

# Purpose labels — keep in sync with the call sites listed below. The
# ``.v1`` suffix is reserved for a future rotation : bumping to ``.v2``
# would invalidate every token / cookie signed with the old key, which
# is the cheapest "emergency rotation" we can ship.
PURPOSE_ACTION = "bretzel.action.v1"   # handlers.sign_action / verify_action
PURPOSE_AUTH = "bretzel.auth.v1"       # auth.login / verify_auth_cookie
PURPOSE_CSRF = "bretzel.csrf.v1"       # middleware.csrf — token for user POSTs


def derive_key(master: str | bytes, purpose: str) -> bytes:
    """Return a 32-byte key derived from ``master`` for ``purpose``.

    Single-block HKDF-Expand semantics : ``HMAC-SHA256(master, purpose)``.
    Different purposes yield independent keys ; compromise of one does
    not weaken the others.

    The master is the value passed to ``Bretzel(secret_key=...)``. The
    purpose is one of the ``PURPOSE_*`` constants — never a free-form
    string from user input.
    """
    if not master:
        raise ValueError(
            "derive_key called with empty master. The Bretzel config "
            "validation should have rejected this at construction."
        )
    key = master.encode("utf-8") if isinstance(master, str) else master
    return hmac.new(key, purpose.encode("utf-8"), hashlib.sha256).digest()


def sign(key: bytes, payload: str | bytes, *, hex_len: int | None = None) -> str:
    """Compute the HMAC-SHA256 hex digest of ``payload`` under ``key``.

    Truncated to ``hex_len`` characters when set ; the action-id signer
    uses 16 (~64 bits, plenty against online forging while keeping URLs
    debuggable), the CSRF signer uses 32 (~128 bits), and the auth-cookie
    signer uses the full 64.
    """
    message = payload.encode("utf-8") if isinstance(payload, str) else payload
    digest = hmac.new(key, message, hashlib.sha256).hexdigest()
    return digest[:hex_len] if hex_len else digest


def verify(key: bytes, payload: str | bytes, signature: str, *, hex_len: int | None = None) -> bool:
    """Constant-time check that ``signature`` matches ``sign(key, payload)``."""
    expected = sign(key, payload, hex_len=hex_len)
    return hmac.compare_digest(expected, signature)

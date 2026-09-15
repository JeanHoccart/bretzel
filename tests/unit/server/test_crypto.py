"""Unit tests for :mod:`bretzel.server.crypto`."""

from __future__ import annotations

import pytest

from bretzel.server.crypto import (
    PURPOSE_ACTION,
    PURPOSE_AUTH,
    PURPOSE_CSRF,
    derive_key,
    sign,
    verify,
)


_MASTER = "x" * 32


class TestDeriveKey:
    def test_returns_32_bytes(self) -> None:
        key = derive_key(_MASTER, PURPOSE_ACTION)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_deterministic(self) -> None:
        # Same inputs → same output. Critical : verify on a different
        # process / worker must reproduce the same signature.
        a = derive_key(_MASTER, PURPOSE_ACTION)
        b = derive_key(_MASTER, PURPOSE_ACTION)
        assert a == b

    def test_different_purposes_differ(self) -> None:
        # The whole point of derivation : a leak of one key must NOT
        # compromise the others.
        action = derive_key(_MASTER, PURPOSE_ACTION)
        auth = derive_key(_MASTER, PURPOSE_AUTH)
        csrf = derive_key(_MASTER, PURPOSE_CSRF)
        assert action != auth
        assert action != csrf
        assert auth != csrf

    def test_different_masters_differ(self) -> None:
        a = derive_key("a" * 32, PURPOSE_ACTION)
        b = derive_key("b" * 32, PURPOSE_ACTION)
        assert a != b

    def test_bytes_master_accepted(self) -> None:
        # Both str (the config-time form) and bytes (the call-site form)
        # work — derivation result is identical.
        assert (
            derive_key(_MASTER, PURPOSE_ACTION)
            == derive_key(_MASTER.encode("utf-8"), PURPOSE_ACTION)
        )

    def test_empty_master_rejected(self) -> None:
        # Empty key in HMAC produces a valid-looking output, which is
        # the textbook footgun. We reject upfront so a misconfigured
        # test rig fails loudly instead of producing forgeable tokens.
        with pytest.raises(ValueError, match="empty master"):
            derive_key("", PURPOSE_ACTION)


class TestSignVerify:
    def test_round_trip(self) -> None:
        key = derive_key(_MASTER, PURPOSE_ACTION)
        sig = sign(key, "payload")
        assert verify(key, "payload", sig)

    def test_full_length_is_64_hex(self) -> None:
        # SHA-256 in hex = 64 chars when not truncated.
        sig = sign(derive_key(_MASTER, PURPOSE_AUTH), "x")
        assert len(sig) == 64
        assert all(c in "0123456789abcdef" for c in sig)

    def test_truncation_respected(self) -> None:
        sig = sign(derive_key(_MASTER, PURPOSE_ACTION), "x", hex_len=16)
        assert len(sig) == 16

    def test_tampered_payload_rejected(self) -> None:
        key = derive_key(_MASTER, PURPOSE_ACTION)
        sig = sign(key, "real")
        assert not verify(key, "fake", sig)

    def test_wrong_key_rejected(self) -> None:
        sig = sign(derive_key(_MASTER, PURPOSE_ACTION), "x")
        assert not verify(derive_key(_MASTER, PURPOSE_AUTH), "x", sig)

    def test_bytes_payload_accepted(self) -> None:
        key = derive_key(_MASTER, PURPOSE_ACTION)
        assert sign(key, "abc") == sign(key, b"abc")

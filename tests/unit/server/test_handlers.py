"""Unit tests for ``bretzel.server.handlers``."""

from __future__ import annotations

import functools

import pytest

from bretzel.server.crypto import PURPOSE_ACTION, derive_key
from bretzel.server.handlers import (
    HandlerResolutionError,
    decode_args,
    encode_action_id,
    encode_args,
    resolve_handler,
    sign_action,
    verify_action,
)


# Module-level handlers — addressable via ``module::qualname``.
def my_handler(value: int = 0) -> int:
    return value * 2


class _Holder:
    @staticmethod
    def static_method(x: int = 0) -> int:
        return x

    @classmethod
    def class_method(cls, x: int = 0) -> int:
        return x


_SECRET = "x" * 32
# What the dispatch path actually uses : the *derived* action key.
_KEY = derive_key(_SECRET, PURPOSE_ACTION)


# ───────────────────────────────────────────────────────────────────────────
# encode_action_id
# ───────────────────────────────────────────────────────────────────────────


class TestEncodeActionId:
    def test_module_function(self) -> None:
        out = encode_action_id(my_handler)
        assert out.endswith("::my_handler")

    def test_static_method(self) -> None:
        out = encode_action_id(_Holder.static_method)
        assert "_Holder.static_method" in out

    def test_class_method(self) -> None:
        out = encode_action_id(_Holder.class_method)
        assert "_Holder.class_method" in out

    def test_partial_unwraps_to_underlying(self) -> None:
        bound = functools.partial(my_handler, 7)
        # The id describes ``my_handler`` — the bound args go via ``encode_args``.
        assert encode_action_id(bound) == encode_action_id(my_handler)

    def test_lambda_rejected(self) -> None:
        with pytest.raises(HandlerResolutionError, match="Lambda"):
            encode_action_id(lambda: None)

    def test_closure_rejected(self) -> None:
        def outer() -> None:
            def inner() -> None: ...

            encode_action_id(inner)

        with pytest.raises(HandlerResolutionError, match="closure|Closure"):
            outer()

    def test_non_callable_rejected(self) -> None:
        with pytest.raises(TypeError):
            encode_action_id(42)  # type: ignore[arg-type]


# ───────────────────────────────────────────────────────────────────────────
# resolve_handler — round-trip through sys.modules
# ───────────────────────────────────────────────────────────────────────────


class TestResolveHandler:
    def test_round_trip(self) -> None:
        action_id = encode_action_id(my_handler)
        resolved = resolve_handler(action_id)
        assert resolved is my_handler
        # And it actually runs.
        assert resolved(7) == 14

    def test_resolves_static_method(self) -> None:
        action_id = encode_action_id(_Holder.static_method)
        resolved = resolve_handler(action_id)
        assert resolved is _Holder.static_method

    def test_malformed_id_raises(self) -> None:
        with pytest.raises(HandlerResolutionError, match="Malformed"):
            resolve_handler("missing-separator")

    def test_unknown_module_raises(self) -> None:
        with pytest.raises(HandlerResolutionError, match="not in sys.modules"):
            resolve_handler("does.not.exist::handler")

    def test_unknown_attribute_raises(self) -> None:
        # The module exists but has no such attribute.
        with pytest.raises(HandlerResolutionError, match="Could not resolve"):
            resolve_handler(f"{__name__}::nonexistent")

    def test_non_callable_target_rejected(self) -> None:
        # ``__file__`` is a string attribute on the module — exists,
        # but isn't callable.
        with pytest.raises(HandlerResolutionError, match="not a callable"):
            resolve_handler(f"{__name__}::__file__")


# ───────────────────────────────────────────────────────────────────────────
# encode_args / decode_args
# ───────────────────────────────────────────────────────────────────────────


class TestArgsCodec:
    def test_no_partial_returns_empty(self) -> None:
        assert encode_args(my_handler) == ""

    def test_partial_round_trip(self) -> None:
        bound = functools.partial(my_handler, 7, value=8)
        blob = encode_args(bound)
        assert blob != ""
        args, kwargs = decode_args(blob)
        assert args == [7]
        assert kwargs == {"value": 8}

    def test_empty_blob_decodes_to_empty(self) -> None:
        assert decode_args("") == ([], {})

    def test_non_json_value_rejected_at_encode(self) -> None:
        class Custom:
            pass

        bound = functools.partial(my_handler, Custom())
        with pytest.raises(HandlerResolutionError, match="JSON"):
            encode_args(bound)

    def test_corrupt_blob_rejected_at_decode(self) -> None:
        with pytest.raises(HandlerResolutionError):
            decode_args("not-base64!")


# ───────────────────────────────────────────────────────────────────────────
# HMAC sign / verify
# ───────────────────────────────────────────────────────────────────────────


class TestSignVerify:
    def test_round_trip(self) -> None:
        action_id = encode_action_id(my_handler)
        signature = sign_action(_KEY, action_id, "")
        assert verify_action(_KEY, action_id, "", signature) is True

    def test_round_trip_with_args(self) -> None:
        action_id = encode_action_id(my_handler)
        bound = functools.partial(my_handler, 7)
        args_blob = encode_args(bound)
        signature = sign_action(_KEY, action_id, args_blob)
        assert verify_action(_KEY, action_id, args_blob, signature)

    def test_signature_short(self) -> None:
        # 16 hex chars → 64 bits — explicitly designed for URL brevity.
        signature = sign_action(_KEY, "x::y")
        assert len(signature) == 16
        assert all(c in "0123456789abcdef" for c in signature)

    def test_tampered_id_rejected(self) -> None:
        signature = sign_action(_KEY, "real::handler")
        assert verify_action(_KEY, "fake::handler", "", signature) is False

    def test_tampered_args_rejected(self) -> None:
        signature = sign_action(_KEY, "x::y", "args1")
        assert verify_action(_KEY, "x::y", "args2", signature) is False

    def test_wrong_key_rejected(self) -> None:
        signature = sign_action(_KEY, "x::y", "")
        other_key = derive_key("y" * 32, PURPOSE_ACTION)
        assert verify_action(other_key, "x::y", "", signature) is False

    def test_derived_keys_differ_per_purpose(self) -> None:
        # Cross-purpose tampering : a signature made with the auth key
        # must NOT verify with the action key, even though both derive
        # from the same master secret.
        from bretzel.server.crypto import PURPOSE_AUTH

        auth_key = derive_key(_SECRET, PURPOSE_AUTH)
        signature = sign_action(auth_key, "x::y", "")
        assert verify_action(_KEY, "x::y", "", signature) is False

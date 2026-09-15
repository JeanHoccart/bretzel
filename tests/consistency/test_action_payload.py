"""Gate : the signed action payload format lives in ONE function.

``sign_action`` and ``verify_action`` must feed byte-identical input to
the HMAC or every action POST 403s, and ``idempotency_key`` reuses the
same ``action_id|args_blob|ts`` identity. The format string used to be
copy-pasted across all three ; it now lives once in
``handlers.action_hmac_payload``.

These checks keep it honest : the wire format is pinned (a change must be
deliberate), and sign→verify round-trips over the exact ``ts`` so a
re-divergence of the two payload builders fails here.
"""

from __future__ import annotations

from bretzel.server.handlers import (
    action_hmac_payload,
    sign_action,
    verify_action,
)
from bretzel.server.idempotency import idempotency_key

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "le format est ÉPINGLÉ par comparaison directe et le roundtrip sign→verify est EXÉCUTÉ : il n'y a aucun motif à reconnaître, donc rien qui puisse devenir aveugle"
)

_KEY = b"k" * 32  # arbitrary derived-key stand-in for the HMAC


def test_payload_format_is_pinned() -> None:
    # A change here is a wire-format change — make it deliberate.
    assert action_hmac_payload("act", "blob", "12345") == "act|blob|12345"


def test_sign_verify_roundtrip_over_ts() -> None:
    sig = sign_action(_KEY, "aid", "args", "111")
    assert verify_action(_KEY, "aid", "args", sig, "111")
    # ts is part of the signed payload → a different ts must NOT verify.
    assert not verify_action(_KEY, "aid", "args", sig, "222")


def test_idempotency_key_tracks_the_signed_payload() -> None:
    base = idempotency_key("u", "aid", "args", "111")
    assert base != idempotency_key("u", "aid", "args", "222")  # ts differs
    assert base != idempotency_key("u", "aid", "other", "111")  # args differ
    assert base != idempotency_key("v", "aid", "args", "111")   # user differs
    assert base == idempotency_key("u", "aid", "args", "111")   # deterministic

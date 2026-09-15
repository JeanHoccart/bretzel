"""Field materialisation helpers for :class:`ClientState` wire payloads.

The V3 wire format itself (``<bz-envelope>`` / ``<bz-patch>`` tags,
namespaced form-data) lives in :mod:`bretzel.runtime.envelope` — the
transport boundary. This module only owns what genuinely belongs to
the state layer : how to turn a :class:`ClientState` instance into a
JSON-friendly field map, and the canonical wire key for an instance.
"""

from __future__ import annotations

from typing import Any

from bretzel.state.scopes.client import ClientState


def instance_key(state: ClientState) -> str:
    """Return the wire key for ``state`` : ``"<ClassName>.<key>"``.

    Matches the dot-separated form used by :class:`ClientBinding` paths
    and by the namespaced form-data fields (``Class.key.field``).
    """
    return f"{type(state).__name__}.{state._key}"


def full_field_dict(state: ClientState) -> dict[str, Any]:
    """Read every declared field, materialising defaults.

    Goes through ``getattr`` so descriptor logic runs (validators,
    factory defaults). ``State.to_dict`` only emits fields explicitly
    assigned (used for compact disk persistence where ``from_dict``
    rebuilds from defaults), but the runtime evaluator can't read
    defaults — it only has the JSON in front of it. If
    ``ClientCounter.count`` defaults to 0 and the user never touched
    it, the wire payload still has to carry ``"count": 0`` or the
    binding ``$bz.state.ClientCounter.default.count`` resolves to
    ``undefined`` and renders empty.

    Skips :class:`ClientBinding` / :class:`ClientExpression` returns —
    should never happen here since envelopes are built outside
    ``rendering_scope``, but we guard defensively for any caller that
    builds one inside.
    """
    from bretzel.state.scopes.client import (
        ClientBinding,
        ClientExpression,
    )

    out: dict[str, Any] = {}
    for name in type(state)._all_fields():
        value = getattr(state, name)
        if isinstance(value, (ClientBinding, ClientExpression)):
            continue
        out[name] = value
    return out

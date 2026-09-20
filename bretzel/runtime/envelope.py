"""Envelope / patch serialisation — the V3 wire format server ↔ runtime.

Two outgoing payloads cross the boundary (.claude/bretzel/runtime.md):

- **``<bz-envelope>``** — bootstrap blob, emitted ONCE per full-page
  render. Carries every :class:`ClientState` instance (fields +
  persist / send_to_server config, cf. :func:`build_envelope`), the
  framework endpoints and the CSRF token. ``00_index.js`` parses it on
  ``DOMContentLoaded`` to seed the signal store and register the
  persistence adapters.

- **``<bz-patch>``** — delta patches, emitted on action responses and
  on the partial-nav seed path. ``05_bridge.js`` parses them on
  ``htmx:afterSwap`` and applies them to the signal store.

Both are normal HTML tags (not ``<script type=...>`` workarounds):
idiomorph swaps them like any element, the bridge consumes + removes
them.

Incoming, client state rides as **namespaced form-data** in the POST
body (``Class.key.field=value``).
:func:`parse_client_payload` splits it from regular handler args.

The client payload carries no TTL. Server states have their own
retention durations, managed by the registry and the backend.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, NotRequired, TypedDict

from bretzel.core.escape import escape_inline_json
from bretzel.runtime import protocol
from bretzel.state.persistence.client_bridge import full_field_dict, instance_key
from bretzel.state.scopes.client import ClientState

__all__ = [
    "Envelope",
    "Patch",
    "build_envelope",
    "build_patch",
    "default_endpoints",
    "error_envelope",
    "parse_client_payload",
    "serialize_envelope",
    "serialize_patch",
]


class Envelope(TypedDict):
    """Top-level shape of the ``<bz-envelope>`` payload."""

    version: str
    client_state: dict[str, Any]
    endpoints: dict[str, str]
    csrf: str
    #: The CORRECTED address, when the browser's is incomplete.
    #:
    #: A ``session``-scoped state remembers a sort or a filter across
    #: navigations. Landing on a bare ``/accounts`` therefore returns a
    #: sorted view under an address that says nothing of it — and the
    #: copied link shows something else to whoever receives it. The
    #: server knows both: it composes the right address and sets it here.
    #:
    #: The runtime passes it to ``history.replaceState`` — **replace**,
    #: not push: correcting an address is not navigating, and stacking an
    #: entry on every load would make the back button unusable.
    #:
    #: Empty string = nothing to correct, which is the case for every app
    #: that declared nothing addressable.
    address: str
    #: The identity of the rendered page. The server needs it on EVERY
    #: action to find the ``page``-scoped state again; without it, it
    #: forges a fresh one, hence a blank state.
    #:
    #: The runtime carries it in the header of every action, including
    #: from an element teleported outside the page container.
    page_id: str


class Patch(TypedDict):
    """Top-level shape of one ``<bz-patch>`` payload."""

    patches: dict[str, dict[str, Any]]
    #: Transport config, present **only on the seed patch**
    #: (``include_unchanged=True``, the partial-nav path). An ordinary
    #: action response does not carry it: the client already has the
    #: config of those instances, sending it back would be bytes per
    #: click.
    #:
    #: It lets a ``ClientState`` discovered during a partial navigation
    #: receive its fields and its configuration together.
    config: NotRequired[dict[str, dict[str, Any]]]


def _transport_config(state: ClientState) -> dict[str, Any]:
    """An instance's transport config — ONE definition, two carriers.

    The ``<bz-envelope>`` carries it on a hard load, the seed
    ``<bz-patch>`` carries it on a partial nav. A single function keeps
    the two representations from diverging.
    """
    return {
        "persist": state.__persist__,
        "send_to_server": state.__send_to_server__,
    }


def default_endpoints() -> dict[str, str]:
    """The runtime endpoints baked into a fresh envelope."""
    return {
        "action": protocol.ROUTE_ACTION,
        "sse": protocol.ROUTE_SSE,
        "refetch": protocol.ROUTE_REFETCH,
    }


# ───────────────────────────────────────────────────────────────────────────
# Server → client : bootstrap envelope
# ───────────────────────────────────────────────────────────────────────────


def build_envelope(
    client_states: Iterable[ClientState],
    csrf_token: str,
    *,
    endpoints: dict[str, str] | None = None,
    page_id: str = "",
    address: str = "",
) -> Envelope:
    """Build a deterministic, JSON-friendly runtime envelope."""
    client_state: dict[str, Any] = {}
    for state in client_states:
        client_state[instance_key(state)] = {
            "fields": full_field_dict(state),
            **_transport_config(state),
        }
    return Envelope(
        version=protocol.PROTOCOL_VERSION,
        client_state=client_state,
        endpoints=endpoints if endpoints is not None else default_endpoints(),
        csrf=csrf_token,
        page_id=page_id,
        address=address,
    )


def serialize_envelope(
    client_states: Iterable[ClientState],
    csrf_token: str,
    *,
    endpoints: dict[str, str] | None = None,
    page_id: str = "",
    address: str = "",
) -> str:
    """Render the complete ``<bz-envelope>…</bz-envelope>`` tag."""
    payload = escape_inline_json(
        json.dumps(
            build_envelope(
                client_states, csrf_token,
                endpoints=endpoints, page_id=page_id, address=address,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    tag = protocol.ENVELOPE_TAG_NAME
    return f"<{tag}>{payload}</{tag}>"


# ───────────────────────────────────────────────────────────────────────────
# Server → client : delta patches
# ───────────────────────────────────────────────────────────────────────────


def build_patch(
    client_states: Iterable[ClientState],
    *,
    include_unchanged: bool = False,
) -> Patch:
    """Bundle the client states to send into a patch payload.

    Default mode emits dirty instances only — the action-response flow
    where the runtime already has fresh values and only the changed
    ones need patching. ``include_unchanged=True`` emits every instance
    with full fields : the partial-nav seed path, where a freshly
    mounted page needs the complete state, not just the diff.
    """
    patches: dict[str, dict[str, Any]] = {}
    config: dict[str, dict[str, Any]] = {}
    for state in client_states:
        if include_unchanged:
            patches[instance_key(state)] = full_field_dict(state)
            # The seed is the ONLY case where the client can discover
            # an instance it has never seen — so the only one that must
            # carry its config. An ordinary action response speaks of
            # instances already configured at boot.
            config[instance_key(state)] = _transport_config(state)
        elif state._dirty:
            patches[instance_key(state)] = state.to_dict()
    payload = Patch(patches=patches)
    if config:
        payload["config"] = config
    return payload


def serialize_patch(
    client_states: Iterable[ClientState],
    *,
    include_unchanged: bool = False,
) -> str:
    """Render the ``<bz-patch>…</bz-patch>`` tag, or ``""`` if empty.

    Returns a stable empty string when nothing matches the filter so
    the render layer can decide whether to emit the tag at all.
    """
    payload = build_patch(client_states, include_unchanged=include_unchanged)
    if not payload["patches"] and not payload.get("config"):
        return ""
    body = escape_inline_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
    tag = protocol.PATCH_TAG_NAME
    return f"<{tag}>{body}</{tag}>"


def error_envelope(kind: str, message: str = "") -> str:
    """Render a ``<bz-patch>`` carrying a reserved ``_error`` directive.

    Bare-text 4xx responses reach the client as a dead-end generic
    "Request failed (403)" toast — the bridge can't tell a stale HMAC
    signature (which a reload heals) from a real error. This wraps the
    body so ``05_bridge.js``'s ``htmx:responseError`` handler can dispatch
    on ``kind``:

    - ``"reload"`` → ``window.location.reload()``. A stale / rotated
      action signature or CSRF token: re-rendering the page mints fresh
      ones, so the user's next click just works instead of dead-ending.
      (Loop-guarded client-side: a second reload-error within 3 s falls
      back to a toast.)
    - anything else → error toast (same as the un-enveloped fallback).

    A redirection goes through the ``HX-Redirect`` header that
    :func:`bretzel.redirect` sets and htmx handles natively. The emitted
    kinds are guarded by
    ``tests/consistency/test_bridge_error_kinds_are_emitted.py``.

    Emitted from the action route (bad / expired signature) and the CSRF
    middleware. The ``<bz-patch>`` rides in the 4xx body; HTMX doesn't
    swap error responses, so the bridge extracts the tag by regex.
    """
    payload = escape_inline_json(
        json.dumps(
            {"patches": {"_error": {"kind": kind, "message": message}}},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    tag = protocol.PATCH_TAG_NAME
    return f"<{tag}>{payload}</{tag}>"


# ───────────────────────────────────────────────────────────────────────────
# Client → server : namespaced form-data parser
# ───────────────────────────────────────────────────────────────────────────


def parse_client_payload(
    form_data: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    """Split form-data into (client state per instance) + (handler args).

    Wire format on an inbound POST::

        SidebarPrefs.default.collapsed=true
        SearchUI.default.query=hello
        comment=Hello%20world           # regular handler arg

    Returns a tuple :

    - ``{("SidebarPrefs", "default"): {"collapsed": "true"}, ...}`` —
      feeds the StateRegistry for hydration ;
    - ``{"comment": "Hello world"}`` — feeds the action handler's
      signature injection.

    A field is treated as client state iff it has exactly two dots AND
    its first segment starts uppercase (class-name convention) — plain
    handler args like ``user.email`` or dotted ids stay untouched.
    """
    client_state: dict[tuple[str, str], dict[str, Any]] = {}
    handler_args: dict[str, Any] = {}
    for raw_key, value in form_data.items():
        parts = raw_key.split(".")
        if len(parts) == 3 and parts[0][:1].isupper():
            cls_name, instance_key, field = parts
            client_state.setdefault((cls_name, instance_key), {})[field] = value
        else:
            handler_args[raw_key] = value
    return client_state, handler_args

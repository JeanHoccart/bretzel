"""Envelope / patch serialisation — the V3 wire format server ↔ runtime.

Two outgoing payloads cross the boundary (.claude/bretzel/runtime.md) :

- **``<bz-envelope>``** — bootstrap blob, emitted ONCE per full-page
  render. Carries every :class:`ClientState` instance (fields +
  persist / send_to_server config, cf. :func:`build_envelope`), the
  framework endpoints and the CSRF token. ``00_index.js`` parses it on
  ``DOMContentLoaded`` to seed the signal store and register the
  persistence adapters.

- **``<bz-patch>``** — delta patches, emitted on action responses and
  on the partial-nav seed path. ``05_bridge.js`` parses them on
  ``htmx:afterSwap`` and applies them to the signal store.

Both are normal HTML tags (not ``<script type=...>`` workarounds) :
idiomorph swaps them like any element, the bridge consumes + removes
them.

Incoming, client state rides as **namespaced form-data** in the POST
body (``Class.key.field=value``).
:func:`parse_client_payload` splits it from regular handler args.

Le payload client ne porte pas de TTL. Les états serveur ont leurs
propres durées de conservation, gérées par le registre et le backend.
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
    #: L'adresse CORRIGÉE, quand celle du navigateur est incomplète.
    #:
    #: Un état de portée ``session`` se souvient d'un tri ou d'un filtre
    #: par-delà les navigations. Arriver sur ``/comptes`` nu rend donc une
    #: vue triée sous une adresse qui n'en dit rien — et le lien copié
    #: montre autre chose chez qui le reçoit. Le serveur, lui, sait les
    #: deux : il compose l'adresse juste et la pose ici.
    #:
    #: Le runtime la passe à ``history.replaceState`` — **replace**, pas
    #: push : corriger une adresse n'est pas naviguer, et empiler une
    #: entrée à chaque chargement rendrait le bouton retour inutilisable.
    #:
    #: Chaîne vide = rien à corriger, ce qui est le cas de toute app qui
    #: n'a rien déclaré adressable.
    address: str
    #: L'identite de la page rendue. Le serveur en a besoin sur CHAQUE
    #: action pour retrouver l'etat de scope ``page`` ; sans elle il en
    #: forge une neuve, donc un etat vierge.
    #:
    #: Le runtime la reprend dans l'en-tête de chaque action, y compris
    #: depuis un élément téléporté hors du conteneur de page.
    page_id: str


class Patch(TypedDict):
    """Top-level shape of one ``<bz-patch>`` payload."""

    patches: dict[str, dict[str, Any]]
    #: Config de transport, présente **uniquement sur le patch de seed**
    #: (``include_unchanged=True``, le chemin de nav partielle). Une
    #: réponse d'action ordinaire ne la porte pas : le client a déjà la
    #: config de ces instances, la renvoyer serait des octets par clic.
    #:
    #: Elle permet à un ``ClientState`` découvert pendant une navigation
    #: partielle de recevoir ses champs et sa configuration ensemble.
    config: NotRequired[dict[str, dict[str, Any]]]


def _transport_config(state: ClientState) -> dict[str, Any]:
    """La config de transport d'une instance — UNE définition, deux porteurs.

    L'``<bz-envelope>`` la porte au chargement dur, le ``<bz-patch>`` de
    seed la porte en nav partielle. Une seule fonction empêche les deux
    représentations de diverger.
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
            # Le seed est le SEUL cas où le client peut découvrir une
            # instance qu'il n'a jamais vue — donc le seul qui doive
            # porter sa config. Une réponse d'action ordinaire parle
            # d'instances déjà configurées au boot.
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
    on ``kind`` :

    - ``"reload"`` → ``window.location.reload()``. A stale / rotated
      action signature or CSRF token : re-rendering the page mints fresh
      ones, so the user's next click just works instead of dead-ending.
      (Loop-guarded client-side : a second reload-error within 3 s falls
      back to a toast.)
    - anything else → error toast (same as the un-enveloped fallback).

    Une redirection passe par l'en-tête ``HX-Redirect`` que
    :func:`bretzel.redirect` pose et qu'htmx traite nativement. Les kinds
    émis sont gardés par ``tests/consistency/test_bridge_error_kinds_are_emitted.py``.

    Emitted from the action route (bad / expired signature) and the CSRF
    middleware. The ``<bz-patch>`` rides in the 4xx body ; HTMX doesn't
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

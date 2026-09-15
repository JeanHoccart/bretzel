"""Unit tests for ``bretzel.runtime.envelope`` (V3 wire format)."""

from __future__ import annotations

import json

from bretzel.runtime import protocol
from bretzel.runtime.envelope import (
    build_envelope,
    build_patch,
    default_endpoints,
    error_envelope,
    parse_client_payload,
    serialize_envelope,
    serialize_patch,
)
from bretzel.state.fields.descriptor import field
from bretzel.state.scopes.client import ClientState

# ───────────────────────────────────────────────────────────────────────────
# Sample ClientState classes
# ───────────────────────────────────────────────────────────────────────────


class FilterState(ClientState, persist="local"):
    sort_by: str = field(default='date')
    is_active: bool = field(default=False)


class CartState(ClientState):
    items: list[int] = field(default_factory=list)


_PALETTE = {
    "primary": {"bg": "primary", "fg": "primary-foreground"},
    "brand": {"bg": "amber-500", "fg": "white"},
}


def _strip_tag(raw: str, tag: str) -> str:
    """Return the JSON payload inside ``<tag>…</tag>``."""
    prefix, suffix = f"<{tag}>", f"</{tag}>"
    assert raw.startswith(prefix) and raw.endswith(suffix), raw
    return raw[len(prefix) : -len(suffix)]


# ───────────────────────────────────────────────────────────────────────────
# default_endpoints
# ───────────────────────────────────────────────────────────────────────────


class TestDefaultEndpoints:
    def test_keys(self) -> None:
        eps = default_endpoints()
        assert set(eps.keys()) == {"action", "sse", "refetch"}

    def test_values_match_protocol(self) -> None:
        eps = default_endpoints()
        assert eps["action"] == protocol.ROUTE_ACTION
        assert eps["sse"] == protocol.ROUTE_SSE
        assert eps["refetch"] == protocol.ROUTE_REFETCH


# ───────────────────────────────────────────────────────────────────────────
# build_envelope / serialize_envelope
# ───────────────────────────────────────────────────────────────────────────


class TestEnvelope:
    def test_minimal_shape(self) -> None:
        env = build_envelope([], "csrf-token-x")
        assert env["version"] == protocol.PROTOCOL_VERSION
        assert env["client_state"] == {}
        # ``palette`` a quitté l'envelope le 2026-08-01 (2 197 o/page
        # que rien ne lisait) — plus de champ à asserter.
        assert env["endpoints"] == default_endpoints()
        assert env["csrf"] == "csrf-token-x"

    def test_with_client_states(self) -> None:
        f = FilterState()
        f.sort_by = "name"
        env = build_envelope([f], "x")
        assert "FilterState.default" in env["client_state"]
        entry = env["client_state"]["FilterState.default"]
        # Defaults are materialised so the runtime evaluator can resolve
        # every field on initial render.
        assert entry["fields"] == {"sort_by": "name", "is_active": False}
        assert entry["persist"] == "local"
        # Transport config rides with each entry. ``send_to_server`` est
        # désormais un vrai réglage (``class X(ClientState,
        # send_to_server=False)``) — jusqu'au 2026-08-14 il était lu en
        # ``getattr`` sans que rien ne puisse l'écrire, et cette assertion
        # de PRÉSENCE le figeait sans rien vérifier de son effet.
        assert entry["send_to_server"] is True
        # ``sync`` a quitté l'envelope le 2026-08-14 : moitié cliente
        # écrite, moitié serveur impossible (un ClientState n'est pas
        # persisté côté serveur, donc un champ omis retombe sur son défaut
        # de classe). Gate : test_client_state_transport_config.py.
        assert "sync" not in entry
        # TTL plumbing is gone in V3 (component mechanics, not framework state).
        assert "ttl" not in entry

    def test_endpoints_overridable(self) -> None:
        eps = {"action": "/x/action", "partial": "/x/partial", "sse": "/x/sse"}
        env = build_envelope([], "x", endpoints=eps)
        assert env["endpoints"] == eps

    def test_serialize_emits_complete_tag(self) -> None:
        raw = serialize_envelope([FilterState()], "x")
        tag = protocol.ENVELOPE_TAG_NAME
        decoded = json.loads(_strip_tag(raw, tag))
        assert decoded["version"] == protocol.PROTOCOL_VERSION
        assert "FilterState.default" in decoded["client_state"]
        assert decoded["csrf"] == "x"

    def test_serialize_compact_json(self) -> None:
        # No spaces between keys / commas — payload size matters when
        # this lives inline on every page.
        raw = serialize_envelope([], "x")
        assert ", " not in raw
        assert ": " not in raw

    def test_serialize_defuses_closing_tag_in_values(self) -> None:
        # A value containing ``</bz-envelope>`` must not terminate the
        # tag early — the serializer escapes ``</`` as ``<\/``.
        f = FilterState()
        f.sort_by = "</bz-envelope><script>alert(1)</script>"
        raw = serialize_envelope([f], "x")
        body = _strip_tag(raw, protocol.ENVELOPE_TAG_NAME)
        assert "</bz-envelope>" not in body
        # JSON round-trips back to the original value.
        decoded = json.loads(body)
        entry = decoded["client_state"]["FilterState.default"]
        assert entry["fields"]["sort_by"] == (
            "</bz-envelope><script>alert(1)</script>"
        )


# ───────────────────────────────────────────────────────────────────────────
# build_patch / serialize_patch
# ───────────────────────────────────────────────────────────────────────────


class TestPatch:
    def test_empty_when_no_dirty(self) -> None:
        f = FilterState()  # not dirty
        patch = build_patch([f])
        assert patch == {"patches": {}}

    def test_serialize_empty_returns_empty_string(self) -> None:
        # Lets the render layer decide not to emit the tag at all.
        assert serialize_patch([FilterState()]) == ""

    def test_includes_dirty_states_only(self) -> None:
        clean = FilterState()  # not dirty
        dirty = CartState()
        dirty.items.append(7)  # mutates list — but that's append, not assign
        # The metaclass-installed Field.__set__ marks _dirty on assignment ;
        # an in-place list mutation doesn't. Force it explicitly.
        dirty._dirty = True

        patch = build_patch([clean, dirty])
        assert "CartState.default" in patch["patches"]
        assert "FilterState.default" not in patch["patches"]

    def test_dirty_state_payload_is_to_dict(self) -> None:
        f = FilterState()
        f.sort_by = "name"  # this assignment marks dirty
        f.is_active = True
        patch = build_patch([f])
        assert patch["patches"]["FilterState.default"] == {
            "sort_by": "name",
            "is_active": True,
        }

    def test_serialize_round_trips(self) -> None:
        f = FilterState()
        f.is_active = True
        raw = serialize_patch([f])
        decoded = json.loads(_strip_tag(raw, protocol.PATCH_TAG_NAME))
        assert decoded == {
            "patches": {"FilterState.default": {"is_active": True}}
        }

    def test_custom_key_in_patch(self) -> None:
        f = FilterState(key="alpha")
        f.sort_by = "name"
        patch = build_patch([f])
        assert "FilterState.alpha" in patch["patches"]

    def test_seed_flow_ships_full_fields_for_clean_states(self) -> None:
        # Partial-nav seed (include_unchanged=True) : a freshly mounted
        # page needs the COMPLETE state of every instance, dirty or not
        # — the runtime may never have seen these ClientStates before.
        f = FilterState()  # clean
        patch = build_patch([f], include_unchanged=True)
        assert patch["patches"]["FilterState.default"] == {
            "sort_by": "date",
            "is_active": False,
        }

    def test_action_flow_omits_clean_states(self) -> None:
        # The default (dirty-only) action flow leaves clean instances
        # out — the runtime already has fresh values for them.
        clean = FilterState()
        patch = build_patch([clean])
        assert patch["patches"] == {}


# ───────────────────────────────────────────────────────────────────────────
# parse_client_payload — namespaced form-data → (client state, handler args)
# ───────────────────────────────────────────────────────────────────────────


class TestParseClientPayload:
    def test_splits_state_from_handler_args(self) -> None:
        states, args = parse_client_payload(
            {
                "SidebarPrefs.default.collapsed": "true",
                "SearchUI.default.query": "hello",
                "comment": "Hello world",
            }
        )
        assert states == {
            ("SidebarPrefs", "default"): {"collapsed": "true"},
            ("SearchUI", "default"): {"query": "hello"},
        }
        assert args == {"comment": "Hello world"}

    def test_multiple_fields_same_instance_grouped(self) -> None:
        states, _ = parse_client_payload(
            {
                "FilterState.default.sort_by": "name",
                "FilterState.default.is_active": "true",
            }
        )
        assert states == {
            ("FilterState", "default"): {
                "sort_by": "name",
                "is_active": "true",
            }
        }

    def test_custom_instance_key(self) -> None:
        states, _ = parse_client_payload({"FilterState.alpha.sort_by": "x"})
        assert ("FilterState", "alpha") in states

    def test_lowercase_dotted_keys_stay_handler_args(self) -> None:
        # Even with exactly two dots, a lowercase first segment is a
        # plain handler arg : the class-name convention (first segment
        # uppercase) is what gates the client-state branch.
        states, args = parse_client_payload({"user.profile.email": "a@b.c"})
        assert states == {}
        assert args == {"user.profile.email": "a@b.c"}

    def test_wrong_dot_count_stays_handler_arg(self) -> None:
        states, args = parse_client_payload(
            {
                "Simple": "1",
                "Two.dots": "2",
                "Four.dots.in.key": "4",
            }
        )
        assert states == {}
        assert set(args) == {"Simple", "Two.dots", "Four.dots.in.key"}

    def test_empty_mapping(self) -> None:
        assert parse_client_payload({}) == ({}, {})


# ───────────────────────────────────────────────────────────────────────────
# Round-trip — envelope fields → form-data wire → parse_client_payload
# ───────────────────────────────────────────────────────────────────────────


class TestRoundTrip:
    def test_envelope_fields_can_ride_back_as_form_data(self) -> None:
        f = FilterState()
        f.sort_by = "name"
        env = build_envelope([f], "x")
        # The runtime echoes each field back as namespaced form-data
        # (``Class.key.field=value``) on the next action POST.
        form_data = {
            f"{wire_key}.{field_name}": value
            for wire_key, entry in env["client_state"].items()
            for field_name, value in entry["fields"].items()
        }
        states, args = parse_client_payload(form_data)
        assert args == {}
        # Defaults flow through the wire too (so the registry always
        # has every declared field at hand).
        assert states == {
            ("FilterState", "default"): {"sort_by": "name", "is_active": False}
        }


# ───────────────────────────────────────────────────────────────────────────
# error_envelope — the reserved _error directive (reload / redirect / toast)
# ───────────────────────────────────────────────────────────────────────────


class TestErrorEnvelope:
    def test_reload_shape_parses_back(self) -> None:
        out = error_envelope("reload", "Invalid action signature.")
        tag = protocol.PATCH_TAG_NAME
        assert out.startswith(f"<{tag}>") and out.endswith(f"</{tag}>")
        # The bridge extracts the inner JSON and JSON.parses it — so it must
        # round-trip. ``escape_inline_json`` only defuses ``</`` (none here).
        inner = out[len(f"<{tag}>"):-len(f"</{tag}>")]
        assert json.loads(inner) == {
            "patches": {"_error": {"kind": "reload",
                                   "message": "Invalid action signature."}}
        }

    def test_message_defaults_empty(self) -> None:
        inner = error_envelope("reload")
        assert '"message":""' in inner

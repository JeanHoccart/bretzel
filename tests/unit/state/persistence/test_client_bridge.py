"""Unit tests for ``bretzel.state.persistence.client_bridge`` (V3).

The V2 wire helpers (header-JSON ``parse_client_payload``,
``serialize_client_envelope`` + TTL plumbing) were deleted with the V3
migration — the wire format now lives in ``bretzel.runtime.envelope``
and is covered by ``tests/unit/runtime/test_envelope.py``. What stays
in the state layer (and is tested here) : field materialisation and
the canonical instance wire key.
"""

from __future__ import annotations

from bretzel.state import field
from bretzel.state.fields.descriptor import field as _field
from bretzel.state.persistence.client_bridge import (
    full_field_dict,
    instance_key,
)
from bretzel.state.scopes.client import ClientState


class TestInstanceKey:
    def test_default_key(self) -> None:
        class Filters(ClientState):
            sort_by: str = field(default='date')

        assert instance_key(Filters()) == "Filters.default"

    def test_custom_key(self) -> None:
        class Basket(ClientState):
            items: list[int] = _field(default_factory=list)

        assert instance_key(Basket(key="alpha")) == "Basket.alpha"


class TestFullFieldDict:
    def test_materialises_defaults(self) -> None:
        class Filters(ClientState):
            sort_by: str = field(default='date')
            is_active: bool = field(default=False)

        f = Filters()
        f.sort_by = "name"

        # EVERY declared field is present, defaults included — the
        # runtime evaluator only sees the JSON in front of it ;
        # missing keys would resolve to ``undefined`` client-side.
        assert full_field_dict(f) == {"sort_by": "name", "is_active": False}

    def test_untouched_instance_emits_pure_defaults(self) -> None:
        class Prefs(ClientState):
            collapsed: bool = field(default=False)
            lang: str = field(default='fr')

        assert full_field_dict(Prefs()) == {"collapsed": False, "lang": "fr"}

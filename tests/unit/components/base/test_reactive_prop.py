"""Unit tests for ``bretzel.components.base.reactive_prop``."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentDefinitionError
from bretzel.components.base.reactive_prop import (
    ReactivePropDescriptor,
    reactive_prop,
)

# ───────────────────────────────────────────────────────────────────────────
# ReactivePropDescriptor — class + instance access
# ───────────────────────────────────────────────────────────────────────────


class TestDescriptor:
    def test_set_name(self) -> None:
        class C:
            x = reactive_prop(default=0)

        descriptor = C.__dict__["x"]
        assert isinstance(descriptor, ReactivePropDescriptor)
        assert descriptor.name == "x"

    def test_class_access_returns_descriptor(self) -> None:
        class C:
            x = reactive_prop(default=0)

        assert isinstance(C.x, ReactivePropDescriptor)

    def test_instance_default_when_no_storage(self) -> None:
        class C:
            x = reactive_prop(default=42)

        c = C()
        # No ``_reactive_values`` attached → falls back to descriptor default.
        assert c.x == 42

    def test_instance_value_overrides_default(self) -> None:
        class C:
            x = reactive_prop(default=0)

        c = C()
        c._reactive_values = {"x": 99}
        assert c.x == 99

    def test_default_factory(self) -> None:
        class C:
            items = reactive_prop(default_factory=list)

        c = C()
        assert c.items == []

    def test_both_default_and_factory_rejected(self) -> None:
        with pytest.raises(ComponentDefinitionError, match="both"):
            reactive_prop(default=0, default_factory=list)

    def test_no_default_returns_none_via_resolve(self) -> None:
        descriptor = reactive_prop()
        assert descriptor.resolve_default() is None
        assert descriptor.has_default() is False

    def test_repr_mentions_name(self) -> None:
        class C:
            disabled = reactive_prop(default=False)

        assert "disabled" in repr(C.__dict__["disabled"])

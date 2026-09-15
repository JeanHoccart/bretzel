"""Unit tests for ``bretzel.state.fields.descriptor``."""

from __future__ import annotations

import pytest

from bretzel.core.tracking import DependencyTracker
from bretzel.state.fields.descriptor import MISSING, Field, field

# ───────────────────────────────────────────────────────────────────────────
# Fixtures — manual State-like classes (no metaclass yet)
# ───────────────────────────────────────────────────────────────────────────


class _Dirtyable:
    """Minimal stand-in for a State instance — has the ``_dirty`` flag."""

    def __init__(self) -> None:
        self._dirty = False


# ───────────────────────────────────────────────────────────────────────────
# Construction / configuration
# ───────────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_default_value(self) -> None:
        f = Field(default=42)
        assert f.default == 42
        assert f.default_factory is None

    def test_default_factory(self) -> None:
        f = Field(default_factory=list)
        assert f.default is MISSING
        assert f.default_factory is list

    def test_both_raises(self) -> None:
        with pytest.raises(ValueError, match="default"):
            Field(default=0, default_factory=lambda: 1)

    def test_type_annotation_captured(self) -> None:
        f = Field(default="", type_=str)
        assert f.type_ is str

    def test_name_starts_empty(self) -> None:
        f = Field(default=0)
        assert f.name == ""


class TestSetName:
    def test_class_attribute_assignment(self) -> None:
        class C:
            x = Field(default=0)

        assert C.x.name == "x"
        assert C.x._storage_key == "_field_x"


# ───────────────────────────────────────────────────────────────────────────
# Get / set behaviour
# ───────────────────────────────────────────────────────────────────────────


class TestGetSet:
    def test_default_returned(self) -> None:
        class C(_Dirtyable):
            x = Field(default=42)

        c = C()
        assert c.x == 42

    def test_set_then_get(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0)

        c = C()
        c.x = 100
        assert c.x == 100

    def test_two_instances_independent(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0)

        a, b = C(), C()
        a.x = 1
        b.x = 2
        assert a.x == 1
        assert b.x == 2

    def test_default_factory_per_instance(self) -> None:
        class C(_Dirtyable):
            items = Field(default_factory=list)

        a, b = C(), C()
        a.items.append(1)
        # Each instance has its OWN list — no shared state.
        assert a.items == [1]
        assert b.items == []

    def test_default_factory_caches(self) -> None:
        # Subsequent reads on same instance return the same object.
        class C(_Dirtyable):
            items = Field(default_factory=list)

        c = C()
        first = c.items
        second = c.items
        assert first is second

    def test_no_default_no_value_raises(self) -> None:
        class C(_Dirtyable):
            x = Field()  # no default, no factory

        with pytest.raises(AttributeError, match="no default"):
            _ = C().x

    def test_class_level_returns_descriptor(self) -> None:
        class C(_Dirtyable):
            x = Field(default=42)

        # Accessing on the class (no instance) yields the Field itself.
        assert isinstance(C.x, Field)


# ───────────────────────────────────────────────────────────────────────────
# Dirty marking
# ───────────────────────────────────────────────────────────────────────────


class TestDirty:
    def test_set_marks_dirty(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0)

        c = C()
        assert c._dirty is False
        c.x = 1
        assert c._dirty is True

    def test_no_dirty_attr_does_not_crash(self) -> None:
        # A bare class without _dirty is a valid degenerate case (used by
        # the descriptor's tests themselves before the State machinery).
        class Bare:
            x = Field(default=0)

        b = Bare()
        b.x = 1  # must not raise
        assert b.x == 1


# ───────────────────────────────────────────────────────────────────────────
# Tracker hookup
# ───────────────────────────────────────────────────────────────────────────


class TestTrackerHookup:
    def test_get_calls_track_access(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from bretzel.state.fields import descriptor as mod

        class FakeObs:
            def invalidate(self) -> None: ...

        local_tracker = DependencyTracker()
        monkeypatch.setattr(mod, "TRACKER", local_tracker)

        class C(_Dirtyable):
            x = Field(default=0)

        c = C()
        obs = FakeObs()
        with local_tracker.observing(obs):
            _ = c.x  # should record dependency

        assert local_tracker.has_dependents(c, "x") is True

    def test_set_calls_notify_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from bretzel.state.fields import descriptor as mod

        invalidated: list[int] = []

        class FakeObs:
            def invalidate(self) -> None:
                invalidated.append(1)

        local_tracker = DependencyTracker()
        monkeypatch.setattr(mod, "TRACKER", local_tracker)

        class C(_Dirtyable):
            x = Field(default=0)

        c = C()
        obs = FakeObs()
        with local_tracker.observing(obs):
            _ = c.x  # register
        c.x = 5  # should fire notify_change
        assert invalidated == [1]


# ───────────────────────────────────────────────────────────────────────────
# field() factory
# ───────────────────────────────────────────────────────────────────────────


class TestFieldFactory:
    def test_returns_field(self) -> None:
        f = field(default=10)
        assert isinstance(f, Field)
        assert f.default == 10

    def test_default_factory(self) -> None:
        f = field(default_factory=dict)
        assert isinstance(f, Field)
        assert f.default_factory is dict


# ───────────────────────────────────────────────────────────────────────────
# Introspection helpers
# ───────────────────────────────────────────────────────────────────────────


class TestScalarCoercion:
    """Form-data strings should land as the field's declared scalar type.

    The framework's POST handlers receive everything as ``str`` (HTML form
    semantics). Users must be able to write ``setattr(state, key, value)``
    without per-field if-ladders for bool/int/float — the descriptor pays
    the cost once.
    """

    def test_str_to_bool_true(self) -> None:
        class C(_Dirtyable):
            x = Field(default=False, type_=bool)

        c = C()
        c.x = "true"
        assert c.x is True
        c.x = "1"
        assert c.x is True
        c.x = "on"
        assert c.x is True

    def test_str_to_bool_false(self) -> None:
        class C(_Dirtyable):
            x = Field(default=True, type_=bool)

        c = C()
        c.x = "false"
        assert c.x is False
        c.x = "0"
        assert c.x is False
        c.x = ""
        assert c.x is False

    def test_str_to_bool_garbage_raises(self) -> None:
        class C(_Dirtyable):
            x = Field(default=False, type_=bool)

        c = C()
        with pytest.raises(ValueError, match="bool"):
            c.x = "maybe"

    def test_str_to_int(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0, type_=int)

        c = C()
        c.x = "42"
        assert c.x == 42
        assert isinstance(c.x, int)

    def test_str_to_int_garbage_raises(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0, type_=int)

        c = C()
        with pytest.raises(ValueError):
            c.x = "not a number"

    def test_str_to_float(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0.0, type_=float)

        c = C()
        c.x = "3.14"
        assert c.x == 3.14
        assert isinstance(c.x, float)

    def test_empty_string_to_float_skips_assignment(self) -> None:
        # HTML ``type="number"`` input erased by the user → empty
        # string lands on the handler. Previous behaviour : 500 on
        # ``float("")``. New behaviour : silently skip the write so
        # the current value is preserved.
        class C(_Dirtyable):
            x = Field(default=42.0, type_=float)

        c = C()
        c.x = 100.0       # explicit write lands
        assert c.x == 100.0
        c.x = ""          # empty form value → no-op
        assert c.x == 100.0

    def test_empty_string_to_int_skips_assignment(self) -> None:
        class C(_Dirtyable):
            x = Field(default=7, type_=int)

        c = C()
        c.x = 12
        assert c.x == 12
        c.x = ""
        assert c.x == 12

    def test_empty_string_to_bool_stays_false(self) -> None:
        # Empty string for bool is legacy-coerced to False via
        # ``_FALSE_STRINGS`` — keep that to avoid surprising apps
        # that relied on it for unchecked-checkbox semantics.
        class C(_Dirtyable):
            x = Field(default=True, type_=bool)

        c = C()
        c.x = ""
        assert c.x is False

    def test_empty_string_to_str_stays_empty(self) -> None:
        # Empty is a valid str value.
        class C(_Dirtyable):
            x = Field(default="foo", type_=str)

        c = C()
        c.x = ""
        assert c.x == ""

    def test_native_bool_passes_through(self) -> None:
        # Coercion must not interfere with already-typed values.
        class C(_Dirtyable):
            x = Field(default=False, type_=bool)

        c = C()
        c.x = True
        assert c.x is True

    def test_str_to_str_unchanged(self) -> None:
        # No bogus coercion when the field is already str-typed.
        class C(_Dirtyable):
            x = Field(default="", type_=str)

        c = C()
        c.x = "true"
        assert c.x == "true"

    def test_no_type_no_coercion(self) -> None:
        # Untyped field : strings pass through untouched.
        class C(_Dirtyable):
            x = Field(default=None)

        c = C()
        c.x = "true"
        assert c.x == "true"

    def test_list_field_untouched(self) -> None:
        # Containers and other non-scalar types are never coerced.
        class C(_Dirtyable):
            items = Field(default_factory=list, type_=list)

        c = C()
        c.items = ["a", "b"]
        assert c.items == ["a", "b"]

    def test_optional_bool_still_coerces(self) -> None:
        # ``flag: bool | None`` resolves to a UnionType at the descriptor
        # level. Coercion must unwrap ``X | None`` so handlers don't have
        # to special-case nullable scalar fields.
        class C(_Dirtyable):
            x = Field(default=None, type_=bool | None)

        c = C()
        c.x = "true"
        assert c.x is True
        c.x = "false"
        assert c.x is False

    def test_optional_int_still_coerces(self) -> None:
        class C(_Dirtyable):
            x = Field(default=None, type_=int | None)

        c = C()
        c.x = "42"
        assert c.x == 42

    def test_ambiguous_union_skips_coercion(self) -> None:
        # ``int | str`` has two scalar candidates → no clear target,
        # leave the value alone rather than guess.
        class C(_Dirtyable):
            x = Field(default="", type_=int | str)

        c = C()
        c.x = "42"
        assert c.x == "42"  # stays str, not coerced to 42

    def test_coercion_runs_before_validator(self) -> None:
        # Validators see the coerced value, not the raw string. Lets
        # ``@validator("count") def _(self, v: int)`` actually receive
        # an int when the form sends "42".
        from bretzel.state.fields.validator import Validator

        seen: list[Any] = []

        def _capture(self: object, v: int) -> int:
            seen.append(v)
            return v

        class C(_Dirtyable):
            x = Field(default=0, type_=int)
            __validators__ = {"x": [Validator(target="x", fn=_capture)]}

        c = C()
        c.x = "42"
        assert seen == [42]
        assert isinstance(seen[0], int)


class TestHasValue:
    def test_false_before_set(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0)

        c = C()
        assert C.x.has_value(c) is False

    def test_true_after_set(self) -> None:
        class C(_Dirtyable):
            x = Field(default=0)

        c = C()
        c.x = 1
        assert C.x.has_value(c) is True

    def test_true_after_factory_materialised(self) -> None:
        # Reading triggers the factory which caches → has_value flips True.
        class C(_Dirtyable):
            items = Field(default_factory=list)

        c = C()
        _ = c.items  # materialise
        assert C.items.has_value(c) is True

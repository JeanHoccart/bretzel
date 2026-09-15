"""Unit tests for ``bretzel.state.fields.validator``."""

from __future__ import annotations

import pytest

from bretzel.core.tracking import DependencyTracker
from bretzel.state.fields.descriptor import Field
from bretzel.state.fields.validator import Validator, validator

# ───────────────────────────────────────────────────────────────────────────
# Decorator declarations
# ───────────────────────────────────────────────────────────────────────────


class TestValidatorDecorator:
    def test_field_form_returns_validator(self) -> None:
        @validator("coupon")
        def normalize(self: object, value: str) -> str:
            return value.upper()

        assert isinstance(normalize, Validator)
        assert normalize.target == "coupon"

    def test_no_arg_form_returns_validator(self) -> None:
        @validator
        def check(self: object) -> None:
            pass

        assert isinstance(check, Validator)
        assert check.target is None

    def test_metadata_carried(self) -> None:
        @validator("x")
        def my_check(self: object, v: int) -> int:
            """Docstring."""
            return v

        assert my_check.__name__ == "my_check"
        assert my_check.__doc__ == "Docstring."

    def test_invocation_calls_underlying(self) -> None:
        @validator("x")
        def upper(self: object, v: str) -> str:
            return v.upper()

        # Calling the wrapper falls through to the function.
        assert upper(None, "hello") == "HELLO"

    def test_invalid_arg_raises(self) -> None:
        with pytest.raises(TypeError):
            validator(123)  # type: ignore[arg-type]


# ───────────────────────────────────────────────────────────────────────────
# Field integration — single-field validators run on __set__
# ───────────────────────────────────────────────────────────────────────────


class TestSingleFieldValidator:
    def test_transforms_value(self) -> None:
        @validator("x")
        def normalize(self: object, v: str) -> str:
            return v.strip().upper()

        class C:
            x = Field(default="")
            __validators__ = {"x": [normalize]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        c.x = "  hello  "
        assert c.x == "HELLO"

    def test_chained_in_declaration_order(self) -> None:
        order: list[str] = []

        @validator("x")
        def first(self: object, v: int) -> int:
            order.append("first")
            return v + 1

        @validator("x")
        def second(self: object, v: int) -> int:
            order.append("second")
            return v * 10

        class C:
            x = Field(default=0)
            __validators__ = {"x": [first, second]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        c.x = 5  # first → 6, then second → 60
        assert c.x == 60
        assert order == ["first", "second"]

    def test_rejects_via_raise(self) -> None:
        @validator("x")
        def positive_only(self: object, v: int) -> int:
            if v < 0:
                raise ValueError("must be positive")
            return v

        class C:
            x = Field(default=0)
            __validators__ = {"x": [positive_only]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        c.x = 5
        with pytest.raises(ValueError, match="positive"):
            c.x = -1
        # Previous value preserved.
        assert c.x == 5

    def test_validator_for_other_field_ignored(self) -> None:
        called: list[bool] = []

        @validator("y")
        def y_only(self: object, v: object) -> object:
            called.append(True)
            return v

        class C:
            x = Field(default=0)
            __validators__ = {"y": [y_only]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        c.x = 1
        assert called == []


# ───────────────────────────────────────────────────────────────────────────
# Whole-instance validators — run AFTER the write, rollback on raise
# ───────────────────────────────────────────────────────────────────────────


class TestWholeInstanceValidator:
    def test_runs_after_write(self) -> None:
        seen_value: list[int] = []

        @validator
        def see(self: object) -> None:
            seen_value.append(self.x)  # type: ignore[attr-defined]

        class C:
            x = Field(default=0)
            __validators__ = {None: [see]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        c.x = 42
        # Validator saw the new value, not the old one.
        assert seen_value == [42]

    def test_rollback_on_raise(self) -> None:
        @validator
        def must_be_positive(self: object) -> None:
            if self.x < 0:  # type: ignore[attr-defined]
                raise ValueError("invariant broken")

        class C:
            x = Field(default=0)
            __validators__ = {None: [must_be_positive]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        c.x = 5  # ok
        with pytest.raises(ValueError, match="invariant"):
            c.x = -3
        # Rollback preserved the previous value.
        assert c.x == 5

    def test_rollback_when_no_previous_value(self) -> None:
        # When the very first set is rejected, storage must be cleared
        # (not left holding the rejected value).
        @validator
        def reject_all(self: object) -> None:
            raise ValueError("nope")

        class C:
            x = Field(default=10)
            __validators__ = {None: [reject_all]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        with pytest.raises(ValueError):
            c.x = 99
        # Storage was popped → reads return the default again.
        assert c.x == 10
        assert C.x.has_value(c) is False


# ───────────────────────────────────────────────────────────────────────────
# Notify — only fired on a fully-validated mutation
# ───────────────────────────────────────────────────────────────────────────


class TestNotifyTiming:
    def test_no_notify_on_rollback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from bretzel.state.fields import descriptor as mod

        local_tracker = DependencyTracker()
        monkeypatch.setattr(mod, "TRACKER", local_tracker)

        invalidated: list[int] = []

        class FakeObs:
            def invalidate(self) -> None:
                invalidated.append(1)

        @validator
        def reject(self: object) -> None:
            raise ValueError

        class C:
            x = Field(default=0)
            __validators__ = {None: [reject]}

            def __init__(self) -> None:
                self._dirty = False

        c = C()
        obs = FakeObs()
        with local_tracker.observing(obs):
            _ = c.x  # register dependency
        with pytest.raises(ValueError):
            c.x = 5
        # Mutation rolled back → no observer should have been invalidated.
        assert invalidated == []

"""Unit tests for ``bretzel.state.scopes.server``."""

from __future__ import annotations

import datetime as dt

import pytest

from bretzel.state.fields.descriptor import field
from bretzel.state.scopes.client import rendering_scope
from bretzel.state.scopes.server import SCOPES, ServerState


class TestDefaults:
    def test_default_scope_session(self) -> None:
        class S(ServerState):
            x: int = field(default=0)

        assert S.__scope__ == "session"

    def test_subclass_inherits_session_default(self) -> None:
        class S(ServerState):
            x: int = field(default=0)

        class T(S):
            y: int = field(default=0)

        assert T.__scope__ == "session"


class TestExplicitScope:
    @pytest.mark.parametrize("scope", SCOPES)
    def test_each_scope_accepted(self, scope: str) -> None:
        # Build a fresh subclass for each scope to avoid leaking class attrs.
        cls = type(
            f"S_{scope}",
            (ServerState,),
            {"__annotations__": {"x": int}, "x": field(default=0)},
            scope=scope,
        )
        assert cls.__scope__ == scope

    def test_scope_overrides_inherited(self) -> None:
        class A(ServerState, scope="user"):
            x: int = field(default=0)

        class B(A, scope="app"):
            y: int = field(default=0)

        assert A.__scope__ == "user"
        assert B.__scope__ == "app"

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid scope"):

            class S(ServerState, scope="cosmic"):  # type: ignore[call-arg]
                x: int = field(default=0)


class TestStateMachineryInherited:
    def test_field_wrapping_still_works(self) -> None:
        class Cart(ServerState, scope="session"):
            items: list[int] = field(default_factory=list)
            coupon: str = field(default='')

        c = Cart()
        assert c.items == []
        c.items.append(1)
        assert c.items == [1]
        assert c.coupon == ""

    def test_to_dict_works(self) -> None:
        class Cart(ServerState):
            coupon: str = field(default='')

        c = Cart()
        c.coupon = "X"
        assert c.to_dict() == {"coupon": "X"}


class TestFieldReadStamping:
    """A render-scope field read returns the value stamped with its
    ``field_name`` so ``AUTONAME_FROM`` inputs can derive the HTML
    ``name=``. Regression guard for the date types, which fell through
    ``_stamp`` (caught by the visual IA+photo sweep : a server-bound
    ``date_picker`` autonamed to ``name="value"`` instead of the field).
    """

    def test_str_field_read_carries_field_name(self) -> None:
        class S(ServerState):
            coupon: str = field(default='SAVE10')

        s = S()
        with rendering_scope():
            v = s.coupon
        assert v == "SAVE10"
        assert v.field_name == "coupon"

    def test_date_field_read_carries_field_name(self) -> None:
        class S(ServerState):
            appointment: dt.date = field(default=dt.date(2026, 6, 15))

        s = S()
        with rendering_scope():
            v = s.appointment
        # Transparent : still a real date for every operation …
        assert isinstance(v, dt.date)
        assert v == dt.date(2026, 6, 15)
        assert v.isoformat() == "2026-06-15"
        # … but now carries the stamp the autoname logic reads.
        assert v.field_name == "appointment"

    def test_stamped_date_replace_drops_stamp_no_crash(self) -> None:
        # Regression : ``date.replace`` reconstructs via ``type(self)(y,m,d)``,
        # but ``_BoundDate.__new__`` takes ``(date, field_name)`` — so the
        # stock path passed ints where a date was expected and 500'd
        # (Calendar's ``month.replace(day=1)`` on a server-bound month).
        # ``replace`` must return a plain date, stamp dropped.
        class S(ServerState):
            month: dt.date = field(default=dt.date(2026, 6, 15))

        with rendering_scope():
            first = S().month.replace(day=1)
        assert first == dt.date(2026, 6, 1)
        assert type(first) is dt.date

    def test_stamped_datetime_replace_drops_stamp_no_crash(self) -> None:
        class S(ServerState):
            at: dt.datetime = field(default=dt.datetime(2026, 6, 15, 9, 30))

        with rendering_scope():
            first = S().at.replace(day=1)
        assert first == dt.datetime(2026, 6, 1, 9, 30)
        assert type(first) is dt.datetime

    def test_datetime_field_keeps_time_and_field_name(self) -> None:
        class S(ServerState):
            at: dt.datetime = field(default=dt.datetime(2026, 6, 15, 14, 30, 5))

        s = S()
        with rendering_scope():
            v = s.at
        assert isinstance(v, dt.datetime)
        assert v == dt.datetime(2026, 6, 15, 14, 30, 5)
        # Time component survives the stamp (datetime has its own wrapper,
        # not flattened onto the date branch).
        assert (v.hour, v.minute, v.second) == (14, 30, 5)
        assert v.field_name == "at"

    def test_outside_render_returns_raw_unstamped_date(self) -> None:
        class S(ServerState):
            d: dt.date = field(default=dt.date(2026, 6, 15))

        s = S()
        v = s.d  # no render scope → raw value, no stamp
        assert type(v) is dt.date
        assert not hasattr(v, "field_name")

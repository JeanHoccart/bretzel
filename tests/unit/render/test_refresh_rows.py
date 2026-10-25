"""``refresh(zone, rows=[…])`` queues a zone for some rows only."""

from __future__ import annotations

import pytest

from bretzel import refreshable
from bretzel.components.base.testing import render_isolated
from bretzel.render.decorators.refreshable import enqueue_deps, refresh
from bretzel.state import AppState, field


class Signal(AppState):
    n: int = field(default=0)


@refreshable(deps=[Signal])
def listing() -> None:
    """A zone refreshed by rows, or whole when ``Signal`` changes."""


def test_rows_queue_the_zone_for_those_keys() -> None:
    with render_isolated() as ctx:
        refresh(listing, rows=[3, "7"])
        refresh(listing, rows=[9])
        assert ctx.refresh_queue == [listing]
        assert ctx.zone_rows[listing.id] == {"3", "7", "9"}


def test_a_whole_refresh_wins_over_rows_either_way() -> None:
    with render_isolated() as ctx:
        refresh(listing, rows=[3])
        enqueue_deps(ctx, {Signal})
        assert listing.id not in ctx.zone_rows and ctx.refresh_queue == [listing]
    with render_isolated() as ctx:
        refresh(listing)
        refresh(listing, rows=[3])
        assert listing.id not in ctx.zone_rows


def test_no_rows_refreshes_nothing() -> None:
    with render_isolated() as ctx:
        refresh(listing, rows=[])
        assert ctx.refresh_queue == []


def test_a_string_is_not_a_list_of_keys() -> None:
    with render_isolated(), pytest.raises(TypeError, match="list of row keys"):
        refresh(listing, rows="42")


def test_rows_of_a_zone_this_page_does_not_show_are_not_rendered() -> None:
    """Rendered here, the zone would ship whole for nothing: the client
    presents no fingerprint for a zone it does not have."""
    with render_isolated() as ctx:
        ctx.live_zones = frozenset({"some_other_zone"})
        refresh(listing, rows=[3])
        assert ctx.refresh_queue == []

"""An application owns its refreshable zones.

Two apps in one process keep apart; a zone is known before this process
has drawn it, wherever it is declared; two functions under one name stop
the start instead of one of them never refreshing.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, refreshable, ui
from bretzel.render import RefreshableHandle
from bretzel.render.decorators.refreshable import ZoneRegistry

SECRET = "x" * 32


@refreshable(name="first_zone")
def first_zone() -> None:
    ui.text("first")


@refreshable(name="second_zone")
def second_zone() -> None:
    ui.text("second")


@page("/")
def home() -> None:
    first_zone()


def test_a_zone_is_known_at_startup_before_any_render() -> None:
    app = Bretzel(secret_key=SECRET, mode="dev")
    app.include(home)
    with TestClient(app):
        assert app.zones.by_name["first_zone"] is first_zone
        assert app.zones.by_id[first_zone.id] is first_zone


def test_two_apps_do_not_share_their_zones() -> None:
    one, other = ZoneRegistry(), ZoneRegistry()
    one.add(first_zone)
    other.add(second_zone)
    assert set(one.by_name) == {"first_zone"}
    assert set(other.by_name) == {"second_zone"}


def test_the_decorator_alone_registers_nothing() -> None:
    @refreshable(name="never_included")
    def lonely() -> None:
        pass

    app = Bretzel(secret_key=SECRET, mode="dev")
    with TestClient(app):
        assert "never_included" not in app.zones.by_name


def test_a_first_render_enters_a_zone_the_walk_could_not_see() -> None:
    @refreshable(name="born_in_a_function")
    def local_zone() -> None:
        ui.text("local")

    @page("/local")
    def local_page() -> None:
        local_zone()

    app = Bretzel(secret_key=SECRET, mode="dev")
    app.include(local_page)
    with TestClient(app) as client:
        assert "born_in_a_function" not in app.zones.by_name
        assert client.get("/local").status_code == 200
        assert app.zones.by_name["born_in_a_function"] is local_zone


def _two_zones_under_one_name() -> tuple[RefreshableHandle, RefreshableHandle]:
    @refreshable(name="taken")
    def a() -> None:
        pass

    @refreshable(name="taken")
    def b() -> None:
        pass

    return a, b


def test_two_functions_under_one_name_are_refused() -> None:
    a, b = _two_zones_under_one_name()
    zones = ZoneRegistry()
    zones.add(a)
    with pytest.raises(ValueError, match="taken"):
        zones.add(b)


def test_adding_the_same_zone_twice_is_harmless() -> None:
    zones = ZoneRegistry()
    zones.add(first_zone)
    zones.add(first_zone)
    assert list(zones.by_id.values()) == [first_zone]

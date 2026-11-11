"""``bretzel features`` / ``bretzel impact`` — the contracts, asked.

A small app is written on disk (the audit reads the real modules), with
one case of each finding:

- ``shop`` imports ``stock`` without declaring it, and declares ``extra``
  without importing it — the drift that used to be a WARN nobody read;
- ``stock.unused`` is public and nothing uses it — a dead surface;
- ``stock.LIMIT`` is taken by ``shop`` without being public;
- ``stock.ITEMS``, a constant, IS public: ``provides`` got its value, the
  audit recognises it by identity under the name it is imported by;
- ``stock.seeded`` is used by ``core/`` only, ``stock.secret`` by a test
  only: neither is reported.
"""

from __future__ import annotations

import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from bretzel.cli.main import main
from bretzel.server import feature_audit as fa


@pytest.fixture(scope="module")
def shop_app(tmp_path_factory):
    root = tmp_path_factory.mktemp("audit")
    pkg = f"auditapp_{uuid.uuid4().hex[:8]}"
    files = {
        f"{pkg}/__init__.py": "",
        f"{pkg}/features/__init__.py": "",
        f"{pkg}/features/extra.py": """
            '''features/extra — nothing much.'''
            from bretzel import Feature
            feature = Feature(name="extra", kind="logic")
        """,
        f"{pkg}/features/stock.py": """
            '''features/stock — what is on the shelves.'''
            from bretzel import Feature
            ITEMS = {"apple": 3}
            LIMIT = 10
            def get_items(): return ITEMS
            def unused(): return 0
            def seeded(): return 1
            def secret(): return 2
            feature = Feature(name="stock", kind="data",
                              provides=[ITEMS, get_items, unused, seeded])
        """,
        f"{pkg}/features/shop.py": f"""
            '''features/shop — the shop's page.'''
            from bretzel import Feature, page, ui
            from {pkg}.features import stock
            from {pkg}.features.stock import ITEMS, LIMIT
            @page("/shop")
            def shop_page():
                ui.text(str(len(stock.get_items()) + len(ITEMS) + LIMIT))
            feature = Feature(name="shop", kind="page", provides=[shop_page],
                              uses=["extra"])
        """,
        f"{pkg}/core/__init__.py": "",
        f"{pkg}/core/seed.py": f"""
            from {pkg}.features.stock import seeded
            VALUE = seeded()
        """,
        f"{pkg}/main.py": f"""
            from bretzel import Bretzel
            from {pkg}.core import seed  # noqa: F401
            from {pkg}.features import extra, shop, stock
            app = Bretzel(secret_key="x" * 32, mode="dev")
            app.include(extra, stock, shop)
        """,
        f"{pkg}/tests/test_stock.py": f"""
            from {pkg}.features import stock
            def test_secret(): assert stock.secret() == 2
        """,
        f"{pkg}/tests/probes/probe_shop.py": """
            window.goto("/shop")
        """,
        f"{pkg}/tests/probes/probe_other.py": """
            window.goto("/elsewhere")
        """,
    }
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    sys.path.insert(0, str(root))
    __import__(f"{pkg}.main")
    module = sys.modules[f"{pkg}.main"]
    yield pkg, root / pkg, list(module.app.features)
    sys.path.remove(str(root))


def test_the_contracts_that_lie_are_said(shop_app) -> None:
    _pkg, root, features = shop_app
    found = fa.findings(features, root)
    assert "shop imports stock without declaring it in `uses`" in found
    assert "shop declares extra in `uses` and never imports it" in found
    assert any(line.startswith("stock.unused is in `provides` and nothing outside") for line in found)
    assert "stock.LIMIT is taken by shop and is not in its `provides`" in found


def test_what_is_used_somewhere_is_not_reported(shop_app) -> None:
    """A constant recognised by identity, a use from ``core/``, a test
    looking inside: none is a finding."""
    _pkg, root, features = shop_app
    said = "\n".join(fa.findings(features, root))
    for name in ("stock.ITEMS", "stock.get_items", "stock.seeded", "stock.secret"):
        assert name not in said, said


def test_the_map_says_routes_exposure_and_users(shop_app) -> None:
    _pkg, _root, features = shop_app
    rows = {r["name"]: r for r in fa.describe_features(features)}
    assert rows["shop"]["routes"] == ["/shop"]
    assert rows["stock"]["provides"] == ["ITEMS", "get_items", "unused", "seeded"]
    assert rows["stock"]["used_by"] == ["shop"]
    assert rows["stock"]["summary"] == "features/stock — what is on the shelves."


def test_a_change_names_the_features_pages_and_probes_it_touches(shop_app) -> None:
    _pkg, root, features = shop_app
    found = fa.impact(features, [root / "features" / "stock.py"], root / "tests" / "probes")
    assert found.touched == ("stock",)
    assert found.affected == ("shop", "stock")
    assert found.routes == (("/shop", "shop"),)
    assert found.probes == (("probe_shop.py", ("shop",)),)
    lone = fa.impact(features, [root / "features" / "extra.py"], root / "tests" / "probes")
    assert lone.affected == ("extra",) and lone.probes == ()


def test_the_commands(shop_app, capsys, monkeypatch) -> None:
    pkg, root, _features = shop_app
    monkeypatch.chdir(root.parent)
    assert main(["features", f"{pkg}.main:app"]) == 0
    out = capsys.readouterr().out
    assert "shop · page — features/shop.py" in out and "To fix (4)" in out
    assert main(["impact", f"{pkg}.main:app", str(root / "features" / "stock.py")]) == 0
    out = capsys.readouterr().out
    assert "probe_shop.py  — shop" in out and "probe_other" not in out


def test_a_lying_contract_stops_the_app_in_dev(shop_app) -> None:
    """The drift was a WARN at startup that nobody read. In dev it now refuses to start, and says every line."""
    from starlette.testclient import TestClient

    from bretzel.server.feature import FeatureError

    pkg, _root, _features = shop_app
    app = sys.modules[f"{pkg}.main"].app
    with pytest.raises(FeatureError) as caught, TestClient(app):
        pass
    said = str(caught.value)
    assert "shop imports stock without declaring it in `uses`" in said
    assert "stock.LIMIT is taken by shop and is not in its `provides`" in said
    assert "stock.unused" not in said          # advice, not an error


def test_production_never_refuses_to_start_over_a_contract(shop_app) -> None:
    from starlette.testclient import TestClient

    from bretzel import Bretzel

    pkg, _root, _features = shop_app
    mods = [sys.modules[f"{pkg}.features.{n}"] for n in ("extra", "stock", "shop")]
    app = Bretzel(secret_key="p" * 64, mode="prod")
    app.include(*mods)
    with TestClient(app) as client:
        assert client.get("/shop").status_code == 200


@pytest.fixture(scope="module")
def layered_app(tmp_path_factory):
    """Every way a ``kind`` lies: a ``data`` importing a page, a ``logic``
    mounting a page, a ``page`` mounting none."""
    root = tmp_path_factory.mktemp("kinds")
    pkg = f"kindapp_{uuid.uuid4().hex[:8]}"
    files = {
        f"{pkg}/__init__.py": "",
        f"{pkg}/home.py": """
            from bretzel import Feature, page, ui
            @page("/")
            def home_page(): ui.text("home")
            def home_href(): return "/"
            feature = Feature(name="home", kind="page", provides=[home_page, home_href])
        """,
        f"{pkg}/notes_data.py": f"""
            from bretzel import Feature
            from {pkg}.home import home_href
            def back(): return home_href()
            feature = Feature(name="notes_data", kind="data", provides=[back], uses=["home"])
        """,
        f"{pkg}/helper.py": """
            from bretzel import Feature, page, ui
            @page("/aide")
            def help_page(): ui.text("aide")
            feature = Feature(name="helper", kind="logic", provides=[help_page])
        """,
        f"{pkg}/empty_page.py": """
            from bretzel import Feature
            def nothing(): return None
            feature = Feature(name="empty_page", kind="page", provides=[nothing])
        """,
        f"{pkg}/main.py": f"""
            from bretzel import Bretzel
            from {pkg} import empty_page, helper, home, notes_data
            app = Bretzel(secret_key="x" * 32, mode="dev")
            app.include(home, notes_data, helper, empty_page)
        """,
    }
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    sys.path.insert(0, str(root))
    __import__(f"{pkg}.main")
    yield list(sys.modules[f"{pkg}.main"].app.features)
    sys.path.remove(str(root))


def test_a_kind_that_lies_is_said(layered_app) -> None:
    said = fa.kind_errors(layered_app)
    assert said == [
        "notes_data (data) imports home (page): below the interface, a feature never "
        "imports what draws it",
        "helper is a `logic` and provides a page: its kind is `page`",
        "empty_page is a `page` and provides no page",
    ], said
    assert set(said) <= set(fa.contract_errors(layered_app))


def test_the_shop_kinds_are_true(shop_app) -> None:
    _pkg, _root, features = shop_app
    assert fa.kind_errors(features) == []

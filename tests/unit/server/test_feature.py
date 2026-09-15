"""The ``Feature`` contract + ``validate_features`` graph checks.

Phase 1 of the living skeleton : a feature declares kind / provides /
uses / reads, and a set of them must form a valid graph (unique names,
resolvable deps, acyclic ``uses``) — the load-bearing check ``include``
will run so a broken contract stops the app loudly.
"""

from __future__ import annotations

import json

import pytest

from bretzel import Feature, FeatureError, layout, page, ui
from bretzel.server import AppGraph, describe_app, validate_features
from bretzel.state import SessionState, field


class _DemoState(SessionState):
    n: int = field(default=0)


@page("/demo")
def _demo_page() -> None:
    ui.text("demo")


def _plain_helper() -> None:
    ...


# ── The Feature object ──────────────────────────────────────────────────

def test_construction_normalises_iterables_to_tuples() -> None:
    f = Feature(name="cart", kind="page", provides=[1, 2], uses=["a"], reads=["b"])
    assert f.provides == (1, 2)
    assert f.uses == ("a",)
    assert f.reads == ("b",)


def test_defaults_are_empty_tuples() -> None:
    f = Feature(name="money", kind="logic")
    assert f.provides == () and f.uses == () and f.reads == ()


def test_unknown_kind_raises() -> None:
    with pytest.raises(FeatureError, match="unknown kind"):
        Feature(name="x", kind="widget")


def test_empty_name_raises() -> None:
    with pytest.raises(FeatureError, match="non-empty string"):
        Feature(name="  ", kind="page")


def test_non_string_dependency_raises() -> None:
    with pytest.raises(FeatureError, match="holds feature NAMES"):
        Feature(name="x", kind="page", uses=[object()])


def test_feature_is_frozen() -> None:
    f = Feature(name="x", kind="logic")
    with pytest.raises(Exception):
        f.name = "y"  # type: ignore[misc]


# ── validate_features — the graph ───────────────────────────────────────

def _shop() -> list[Feature]:
    return [
        Feature(name="db", kind="infra"),
        Feature(name="money", kind="logic"),
        Feature(name="catalog_data", kind="data", uses=["db"]),
        Feature(name="catalog", kind="page", uses=["catalog_data", "money"]),
        Feature(name="cart", kind="page", uses=["catalog_data", "money"]),
    ]


def test_valid_graph_passes_and_returns_tuple() -> None:
    result = validate_features(_shop())
    assert isinstance(result, tuple)
    assert {f.name for f in result} == {"db", "money", "catalog_data", "catalog", "cart"}


def test_duplicate_name_raises() -> None:
    feats = [Feature(name="dup", kind="logic"), Feature(name="dup", kind="page")]
    with pytest.raises(FeatureError, match="Duplicate feature name 'dup'"):
        validate_features(feats)


def test_unknown_uses_target_raises() -> None:
    feats = [Feature(name="page", kind="page", uses=["ghost"])]
    with pytest.raises(FeatureError, match="uses='ghost'.*isn't a known feature"):
        validate_features(feats)


def test_unknown_reads_target_raises() -> None:
    feats = [Feature(name="report", kind="data", reads=["ghost"])]
    with pytest.raises(FeatureError, match="reads='ghost'"):
        validate_features(feats)


def test_direct_cycle_raises_with_path() -> None:
    feats = [
        Feature(name="a", kind="logic", uses=["b"]),
        Feature(name="b", kind="logic", uses=["a"]),
    ]
    with pytest.raises(FeatureError, match="Cycle in uses"):
        validate_features(feats)


def test_self_cycle_raises() -> None:
    with pytest.raises(FeatureError, match="Cycle in uses"):
        validate_features([Feature(name="a", kind="logic", uses=["a"])])


def test_reads_is_excluded_from_the_cycle_check() -> None:
    # a uses b (hard dep) ; b reads a (read-only, cross-domain) — this is
    # NOT a construction cycle, so it must be allowed. reads exists as the
    # sanctioned escape from the strict tree for reporting.
    feats = [
        Feature(name="a", kind="data", uses=["b"]),
        Feature(name="b", kind="data", reads=["a"]),
    ]
    result = validate_features(feats)
    assert len(result) == 2


# ── describe_app — the living skeleton ──────────────────────────────────

def test_describe_app_classifies_provides_and_builds_graph() -> None:
    feats = [
        Feature(name="db", kind="infra"),
        Feature(
            name="demo",
            kind="page",
            provides=[_DemoState, _demo_page, _plain_helper],
            uses=["db"],
        ),
    ]
    g = describe_app(feats)
    assert isinstance(g, AppGraph)
    assert {n.name for n in g.nodes} == {"db", "demo"}

    demo = next(n for n in g.nodes if n.name == "demo")
    by_label = {p.label: p for p in demo.provides}
    assert by_label["_DemoState"].kind == "state"
    assert by_label["_demo_page"].kind == "page"
    assert by_label["_demo_page"].detail == "/demo"
    assert by_label["_plain_helper"].kind == "function"

    assert ("/demo", "demo") in g.routes
    assert ("demo", "db", "uses") in g.edges


def test_describe_app_reads_edge_is_labelled() -> None:
    g = describe_app([
        Feature(name="a", kind="data"),
        Feature(name="report", kind="data", reads=["a"]),
    ])
    assert ("report", "a", "reads") in g.edges


def test_describe_app_derives_folder_paths_from_modules() -> None:
    feats = [
        Feature(name="db", kind="infra", module="app.features.core.db.feature"),
        Feature(name="board", kind="page",
                module="app.features.projects.board.feature"),
        Feature(name="home", kind="page", module="app.features.home"),
    ]
    by_path = {n.name: n.path for n in describe_app(feats).nodes}
    assert by_path["db"] == ("core",)
    assert by_path["board"] == ("projects",)
    assert by_path["home"] == ()


def test_module_is_auto_captured_and_excluded_from_equality() -> None:
    a = Feature(name="x", kind="logic")
    assert a.module  # captured (this test module)
    # module is compare=False, so two same-contract features are still equal
    assert Feature(name="y", kind="logic", module="m1") == Feature(
        name="y", kind="logic", module="m2"
    )


def test_describe_app_render_hierarchy() -> None:
    @layout
    def root_shell() -> None: ...

    @layout(parent=root_shell)
    def sub() -> None: ...

    @page("/deep", layout=sub)
    def deep_page() -> None: ...

    feats = [
        Feature(name="shell", kind="shell", provides=[root_shell]),
        Feature(name="sub", kind="layout", provides=[sub]),
        Feature(name="deep", kind="page", provides=[deep_page]),
        Feature(name="store", kind="data"),  # not renderable → shared
    ]
    by = {n.name: n for n in describe_app(feats).nodes}
    assert by["shell"].renderable and by["shell"].render_parent == ""   # root layout
    assert by["sub"].render_parent == "shell"                          # sub-layout
    assert by["deep"].render_parent == "sub"                           # page under sub
    assert not by["store"].renderable                                  # shared


def test_optimal_parent_global_foundation() -> None:
    # A data feature used by two pages under the root commons at the root — a
    # global foundation, wherever its repo folder happens to be.
    @layout
    def shell_l() -> None: ...

    @page("/", layout=shell_l)
    def home_pg() -> None: ...

    @page("/notes", layout=shell_l)
    def notes_pg() -> None: ...

    feats = [
        Feature(name="shell", kind="shell", provides=[shell_l]),
        Feature(name="home", kind="page", provides=[home_pg], uses=["store"]),
        Feature(name="notes", kind="page", provides=[notes_pg], uses=["store"]),
        Feature(name="store", kind="data"),
    ]
    by = {n.name: n for n in describe_app(feats).nodes}
    assert by["store"].optimal_parent == "shell"   # LCA(home, notes) = shell


def test_optimal_parent_branch_local() -> None:
    # A data feature used ONLY by pages under a sub-layout sinks into that
    # branch — even though `home` exists, it doesn't use `acct`.
    @layout
    def shell_l() -> None: ...

    @layout(parent=shell_l)
    def account_nav() -> None: ...

    @page("/", layout=shell_l)
    def home_pg() -> None: ...

    @page("/account", layout=account_nav)
    def profile_pg() -> None: ...

    @page("/account/security", layout=account_nav)
    def security_pg() -> None: ...

    feats = [
        Feature(name="shell", kind="shell", provides=[shell_l]),
        Feature(name="account_nav", kind="layout", provides=[account_nav]),
        Feature(name="home", kind="page", provides=[home_pg]),
        Feature(name="profile", kind="page", provides=[profile_pg], uses=["acct"]),
        Feature(name="security", kind="page", provides=[security_pg], uses=["acct"]),
        Feature(name="acct", kind="data"),
    ]
    by = {n.name: n for n in describe_app(feats).nodes}
    assert by["acct"].optimal_parent == "account_nav"  # LCA(profile, security)


def test_optimal_parent_single_consumer_nests_under_it() -> None:
    @layout
    def shell_l() -> None: ...

    @page("/", layout=shell_l)
    def home_pg() -> None: ...

    feats = [
        Feature(name="shell", kind="shell", provides=[shell_l]),
        Feature(name="home", kind="page", provides=[home_pg], uses=["store"]),
        Feature(name="store", kind="data"),
    ]
    by = {n.name: n for n in describe_app(feats).nodes}
    assert by["store"].optimal_parent == "home"   # sole consumer → private to it


def test_optimal_parent_unused_is_global() -> None:
    by = {n.name: n for n in describe_app([Feature(name="orphan", kind="data")]).nodes}
    assert by["orphan"].optimal_parent == ""   # used by nobody → floats to global


def test_optimal_parent_resolves_transitively() -> None:
    # logic → data → pages : the logic feature lands where the pages that
    # TRANSITIVELY need it common, not at its direct (non-render) consumer.
    @layout
    def shell_l() -> None: ...

    @layout(parent=shell_l)
    def account_nav() -> None: ...

    @page("/account", layout=account_nav)
    def profile_pg() -> None: ...

    @page("/account/security", layout=account_nav)
    def security_pg() -> None: ...

    feats = [
        Feature(name="shell", kind="shell", provides=[shell_l]),
        Feature(name="account_nav", kind="layout", provides=[account_nav]),
        Feature(name="profile", kind="page", provides=[profile_pg], uses=["acct_store"]),
        Feature(name="security", kind="page", provides=[security_pg], uses=["acct_store"]),
        Feature(name="acct_store", kind="data", uses=["acct_logic"]),
        Feature(name="acct_logic", kind="logic"),
    ]
    by = {n.name: n for n in describe_app(feats).nodes}
    assert by["acct_store"].optimal_parent == "account_nav"
    assert by["acct_logic"].optimal_parent == "account_nav"   # transitive through data


def test_provide_carries_its_defining_module() -> None:
    # Each provided symbol points at ITS file (obj.__module__), distinct from
    # the feature's contract module — the map's symbol→code link.
    feats = [Feature(name="demo", kind="page",
                     provides=[_DemoState, _demo_page, _plain_helper])]
    by = {p.label: p for p in describe_app(feats).nodes[0].provides}
    assert by["_DemoState"].module == __name__
    assert by["_demo_page"].module == __name__


def test_refreshable_provide_classified_as_view_with_fn_name() -> None:
    # A @refreshable zone is a RefreshableHandle wrapping fn — classify as
    # "view" under the FN's name/module, not "RefreshableHandle · function".
    from bretzel import refreshable

    @refreshable
    def my_zone() -> None: ...

    info = describe_app(
        [Feature(name="d", kind="data", provides=[my_zone])]
    ).nodes[0].provides[0]
    assert info.label == "my_zone"
    assert info.kind == "view"
    assert info.module == __name__


def test_undeclared_provides_flags_orphan_and_skips_covered() -> None:
    # L1 : un routable enregistré hors de toute Feature est signalé ; le même,
    # couvert par un provides, ne l'est pas.
    from bretzel.server import undeclared_provides

    feats = [Feature(name="demo", kind="page", provides=[_demo_page])]

    def orphan() -> None: ...
    orphan._bz_page = type("P", (), {"path": "/orphan"})()  # type: ignore[attr-defined]

    assert undeclared_provides(feats, [_demo_page]) == []
    assert undeclared_provides(feats, [orphan]) == [("orphan", "/orphan")]


def test_app_graph_to_dict_is_json_serialisable() -> None:
    g = describe_app([
        Feature(name="a", kind="logic"),
        Feature(name="b", kind="page", uses=["a"]),
    ])
    payload = g.to_dict()
    json.dumps(payload)  # must not raise
    assert set(payload) == {"nodes", "routes", "edges"}

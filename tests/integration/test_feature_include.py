"""Phase 2 — ``app.include()`` reads ``Feature`` objects and validates the
graph at startup.

A feature-based app mounts its ``provides`` and starts ; a lying contract
(unknown dependency, cycle) stops the app assembling in the lifespan
startup, loudly, instead of half-mounting.
"""

from __future__ import annotations

import types

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, Feature, page, ui

_SECRET = "test-secret-key-1234567890"


# ``mode="dev"`` partout ici : le défaut de ``Bretzel()`` est **prod**, et
# entrer dans le lifespan d'une app prod déclenche une vraie compilation
# Tailwind (voire le téléchargement du binaire, 112 Mo, sur un environnement
# neuf). Ces tests portent sur ``include()``, pas sur le pipeline CSS.


def _make_page(path: str, text: str):
    @page(path)
    def _p() -> None:
        ui.text(text)

    slug = "p_" + (path.strip("/").replace("/", "_") or "root")
    _p.__name__ = slug
    _p.__qualname__ = slug
    return _p


def test_include_feature_mounts_provides_and_populates_features() -> None:
    home = _make_page("/", "home")
    feat = Feature(name="home", kind="page", provides=[home])

    app = Bretzel(secret_key=_SECRET, mode="dev")
    app.include(feat)

    assert {f.name for f in app.features} == {"home"}
    with TestClient(app) as client:
        assert client.get("/").status_code == 200


def test_feature_discovered_by_module_scan() -> None:
    mod = types.ModuleType("fake_feature_mod")
    mod.feature = Feature(name="m", kind="page", provides=[_make_page("/m", "m")])

    app = Bretzel(secret_key=_SECRET, mode="dev")
    app.include(mod)

    assert {f.name for f in app.features} == {"m"}
    with TestClient(app) as client:
        assert client.get("/m").status_code == 200


def test_reincluding_same_feature_is_idempotent() -> None:
    feat = Feature(name="solo", kind="logic")
    app = Bretzel(secret_key=_SECRET, mode="dev")
    app.include(feat, feat)
    app.include(feat)
    assert len(app.features) == 1


def test_unknown_dependency_stops_startup() -> None:
    bad = Feature(name="x", kind="page", provides=[_make_page("/x", "x")],
                  uses=["ghost"])
    app = Bretzel(secret_key=_SECRET, mode="dev")
    app.include(bad)
    with pytest.raises(Exception):
        with TestClient(app):
            pass


def test_cycle_stops_startup() -> None:
    a = Feature(name="a", kind="logic", uses=["b"])
    b = Feature(name="b", kind="logic", uses=["a"])
    app = Bretzel(secret_key=_SECRET, mode="dev")
    app.include(a, b)
    with pytest.raises(Exception):
        with TestClient(app):
            pass


def test_no_features_is_backward_compatible() -> None:
    # A legacy app that includes only plain @page callables (no Feature)
    # must still start — validate_features([]) is a no-op.
    app = Bretzel(secret_key=_SECRET, mode="dev")
    app.include(_make_page("/legacy", "legacy"))
    assert app.features == ()
    with TestClient(app) as client:
        assert client.get("/legacy").status_code == 200
    # …and the L1 lint stays silent : an app that didn't opt into Features
    # has nothing "undeclared".
    assert app.undeclared_pages == ()


# ── Lints L1/L2 — le manifeste arbitré contre la réalité ─────────────────


def test_lifespan_populates_undeclared_pages() -> None:
    # Une app qui MIXE : une Feature + une page nue → la page nue est
    # signalée au startup (L1) et exposée pour la carte.
    covered = _make_page("/ok", "ok")
    bare = _make_page("/bare", "bare")
    app = Bretzel(secret_key=_SECRET, mode="dev")
    app.include(Feature(name="ok", kind="page", provides=[covered]), bare)
    with TestClient(app) as client:
        assert client.get("/bare").status_code == 200
    assert app.undeclared_pages == (("p_bare", "/bare"),)


def test_dependency_drift_clean_on_real_examples() -> None:
    # Garde permanente : les contrats des apps d'exemple collent à leurs
    # imports réels. Si quelqu'un ajoute un import cross-feature sans le
    # déclarer (ou déclare sans importer), CE test devient rouge.
    from bretzel.server import dependency_drift
    from examples.crm.main import app as crm

    assert dependency_drift(crm.features) == []


def test_dependency_drift_detects_missing_and_stale() -> None:
    from bretzel.server import dependency_drift
    from examples.crm.main import app as crm

    feats = list(crm.features)
    data = next(f for f in feats if f.name == "accounts_data")

    # MISSING : accounts_data importe core.db mais son contrat ne le dit plus.
    bad = Feature(name="accounts_data", kind="data",
                  provides=list(data.provides), uses=[], module=data.module)
    doctored = [bad if f.name == "accounts_data" else f for f in feats]
    report = next(d for d in dependency_drift(doctored)
                  if d.feature == "accounts_data")
    assert "db" in report.missing

    # STALE : un contrat déclare un uses que son module n'importe jamais.
    ghost = Feature(name="ghost", kind="data", uses=["db"],
                    module="examples.crm.features.shell")
    report = next(d for d in dependency_drift([*feats, ghost])
                  if d.feature == "ghost")
    assert report.stale == ("db",)

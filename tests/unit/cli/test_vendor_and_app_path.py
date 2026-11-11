"""Two CLI rough edges reported by the comparison's builder (2026-10-25).

- ``python -m bretzel.render.vendor --help`` STARTED the download: its
  arguments were not read. ``bretzel vendor`` now exists, and both read
  ``--help`` / ``--force``.
- ``bretzel check --deep helpdesk.main:app`` (and ``bretzel dev``) could
  not import an app that is not installed — a uv "virtual" project —
  without ``PYTHONPATH=.``; the ASGI runners put the app's directory first.

Since 2026-11-06 every entry point reads ``module:attribute`` through ONE
function (``bretzel.introspect._target.load_target``). The probe had its
own copy, and it was the one that still missed the app's directory.
"""

from __future__ import annotations

import sys

import pytest

from bretzel.cli.main import main
from bretzel.introspect._target import load_target
from bretzel.probe._server import resolve


def _no_download(*args, **kwargs):
    raise AssertionError("--help must not download anything")


@pytest.mark.parametrize("argv", [["vendor", "--help"]])
def test_bretzel_vendor_help_prints_and_downloads_nothing(argv, monkeypatch, capsys) -> None:
    monkeypatch.setattr("bretzel.render.vendor.download_all", _no_download)
    with pytest.raises(SystemExit) as stop:
        main(argv)
    assert stop.value.code == 0
    assert "--force" in capsys.readouterr().out


def test_the_module_entry_point_reads_its_arguments(monkeypatch, capsys) -> None:
    from bretzel.render import vendor

    monkeypatch.setattr(vendor, "download_all", _no_download)
    with pytest.raises(SystemExit) as stop:
        vendor.main(["--help"])
    assert stop.value.code == 0


def test_bretzel_vendor_downloads_with_force(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr("bretzel.render.vendor.download_all",
                        lambda force=False: seen.setdefault("force", force) and [])
    assert main(["vendor", "--force"]) == 0
    assert seen["force"] is True


@pytest.mark.parametrize("entry", ["load_target", "probe"])
def test_every_entry_point_finds_an_app_that_is_not_installed(
    entry, tmp_path, monkeypatch
) -> None:
    (tmp_path / "virtualapp_mod.py").write_text("app = 'the app'\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", str(tmp_path))])
    try:
        if entry == "probe":
            app = resolve("virtualapp_mod:app")
        else:
            app, origin = load_target("virtualapp_mod:app")
            assert origin.name == "virtualapp_mod.py"
    finally:
        sys.modules.pop("virtualapp_mod", None)
    assert app == "the app"


@pytest.mark.parametrize("target", ["no_colon", ":app", "mod:"])
def test_a_target_that_is_not_module_attribute_is_refused(target) -> None:
    with pytest.raises(ValueError, match="expected module:attribute"):
        load_target(target)


def test_a_missing_attribute_names_what_the_module_has() -> None:
    with pytest.raises(ValueError, match="does not expose `nope`. Available:"):
        load_target("bretzel.introspect._target:nope")


def test_one_reader_of_module_attribute() -> None:
    """``partition(":")`` then ``import_module``: only in ``_target``.

    The three copies that existed had drifted (the probe missed the app's
    directory, each said a missing attribute its own way). A fourth would
    drift the same way."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "bretzel"
    readers = sorted(
        p.relative_to(root.parent).as_posix()
        for p in root.rglob("*.py")
        if 'partition(":")' in (src := p.read_text(encoding="utf-8"))
        and "import_module" in src
    )
    assert readers == ["bretzel/introspect/_target.py"], readers

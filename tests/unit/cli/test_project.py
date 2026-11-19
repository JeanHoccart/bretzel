from __future__ import annotations

import importlib
import re
import shlex
import sys
from pathlib import Path

import pytest

from bretzel.cli.commands.project import create_project, run_project
from bretzel.cli.main import build_parser, main


def test_new_creates_an_importable_application(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "hello"

    assert main(["new", "Hello", "--directory", str(destination)]) == 0

    assert (destination / "pyproject.toml").is_file()
    assert (destination / "app/features/home.py").is_file()
    monkeypatch.syspath_prepend(str(destination))
    monkeypatch.setenv("BRETZEL_MODE", "dev")
    imported = importlib.import_module("app.main")
    assert imported.app.config.title == "Hello"


def test_a_new_project_installs_the_css_compiler(tmp_path: Path) -> None:
    """A generated app depends on ``bretzel[css]``: in production it then
    serves a stylesheet compiled once, instead of compiling in the
    browser from a script fetched on unpkg. Bretzel itself keeps the
    compiler optional (~40 MB), decided on 2026-10-22."""
    import tomllib

    destination = tmp_path / "hello"
    assert main(["new", "Hello", "--directory", str(destination)]) == 0
    project = tomllib.loads((destination / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == ["bretzel[css]"]


def test_generated_application_starts_in_production_without_a_public_secret(
    tmp_path: Path, monkeypatch
) -> None:
    """No key in the code and none in the environment: the app still
    starts, on a key of its own kept out of the sources."""
    destination = tmp_path / "production"
    files = create_project(destination, display_name="Production")
    monkeypatch.syspath_prepend(str(destination))
    monkeypatch.chdir(destination)
    monkeypatch.delenv("BRETZEL_SECRET_KEY", raising=False)
    monkeypatch.setenv("BRETZEL_MODE", "prod")

    imported = importlib.import_module("app.main")

    kept = (destination / ".bretzel" / "secret_key").read_text().strip()
    assert imported.app.config.secret_key == kept
    assert not any(kept in f.read_text(encoding="utf-8") for f in files)


def test_new_refuses_to_touch_an_existing_directory(tmp_path: Path) -> None:
    destination = tmp_path / "already-here"
    destination.mkdir()

    with pytest.raises(ValueError, match="already exists"):
        create_project(destination, display_name="Existing")


def test_dev_uses_the_framework_watcher(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "project"
    create_project(destination, display_name="Project")
    monkeypatch.syspath_prepend(str(destination))
    measured = {}

    def fake_run_dev_server(**kwargs) -> None:
        measured.update(kwargs)

    monkeypatch.setattr("bretzel.server._dev.run_dev_server", fake_run_dev_server)
    run_project(
        "app.main:app",
        host="127.0.0.1",
        port=8123,
        reload=True,
        watch_dir=destination,
    )

    assert measured["target"] == "app.main:app"
    assert measured["port"] == 8123
    assert measured["watch_dirs"] == [destination.resolve()]


def test_every_command_of_the_ai_guide_runs_on_the_new_project(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Le guide que ``bretzel new`` écrit pour l'IA ne cite que des
    commandes qui marchent, sur le projet qu'il accompagne : un guide qui
    ment coûte plus cher qu'aucun guide. ``probe`` demande un navigateur :
    il est seulement analysé."""
    destination = tmp_path / "guided"
    create_project(destination, display_name="Guided")
    guide = (destination / "AGENTS.md").read_text(encoding="utf-8")
    assert (destination / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"

    commands = [shlex.split(c)[1:] for c in re.findall(r"`(bretzel [^`]+)`", guide)]
    assert len(commands) >= 4, f"le guide ne cite plus ses commandes : {commands}"
    monkeypatch.chdir(destination)
    monkeypatch.syspath_prepend(str(destination))
    monkeypatch.setenv("BRETZEL_MODE", "dev")
    for argv in commands:
        if argv[0] == "probe":
            build_parser().parse_args(argv)  # SystemExit si la commande est fausse
            continue
        assert main(argv) == 0, (argv, capsys.readouterr())


@pytest.fixture(autouse=True)
def forget_scaffold_modules() -> None:
    yield
    for name in tuple(sys.modules):
        if name == "app" or name.startswith("app."):
            sys.modules.pop(name, None)

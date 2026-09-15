"""Create and run the smallest complete Bretzel application."""

from __future__ import annotations

import importlib
import os
import re
import secrets
from pathlib import Path
from textwrap import dedent
from typing import Any


def create_project(destination: Path, *, display_name: str) -> list[Path]:
    """Create a self-contained starter project and return the written files.

    Refuse any existing destination. A scaffold must never merge with or
    overwrite a directory whose contents Bretzel does not own.
    """
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"le dossier existe déjà : {destination}")

    package_name = _package_name(destination.name)
    secret_key = secrets.token_urlsafe(32)
    files = {
        ".gitignore": ".venv/\n__pycache__/\n*.py[cod]\n.env\n.bretzel/\n",
        "README.md": dedent(
            f"""\
            # {display_name}

            A Bretzel application.

            ```bash
            python -m venv .venv
            python -m pip install -e .
            bretzel dev
            ```

            Then open <http://127.0.0.1:8000>.
            """
        ),
        "pyproject.toml": dedent(
            f"""\
            [build-system]
            requires = ["hatchling>=1.26"]
            build-backend = "hatchling.build"

            [project]
            name = "{package_name}"
            version = "0.1.0"
            requires-python = ">=3.12"
            dependencies = ["bretzel"]

            [tool.hatch.build.targets.wheel]
            packages = ["app"]
            """
        ),
        "app/__init__.py": "",
        "app/features/__init__.py": "",
        "app/features/home.py": dedent(
            """\
            from bretzel import page, ui


            @page("/", title="Accueil")
            def home() -> None:
                with ui.container(width="md", classes="py-16"):
                    with ui.vstack(gap="md"):
                        ui.heading("Bienvenue dans Bretzel", level=1, size="4xl")
                        ui.text(
                            "Modifie app/features/home.py : le navigateur suivra.",
                            color="muted",
                            size="lg",
                        )
                        ui.button("Ça marche", on_click=lambda: ui.notification("Oui !"))
            """
        ),
        "app/main.py": dedent(
            f"""\
            import os

            from bretzel import Bretzel

            from app.features import home


            mode = os.environ.get("BRETZEL_MODE", "prod")
            secret_key = os.environ.get("BRETZEL_SECRET_KEY")
            if secret_key is None:
                if mode == "prod":
                    raise RuntimeError(
                        "BRETZEL_SECRET_KEY is required when BRETZEL_MODE=prod"
                    )
                secret_key = {secret_key!r}

            app = Bretzel(
                title={display_name!r},
                secret_key=secret_key,
                mode=mode,
            )
            app.include(home)
            """
        ),
    }

    written: list[Path] = []
    for relative, content in files.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def run_project(
    target: str,
    *,
    host: str,
    port: int,
    reload: bool,
    watch_dir: Path,
) -> None:
    """Import a Bretzel app and run it with development defaults."""
    os.environ.setdefault("BRETZEL_MODE", "dev")
    module_name, separator, attribute = target.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("cible invalide — attendu `module:attribut`")

    module = importlib.import_module(module_name)
    app: Any = getattr(module, attribute, None)
    from bretzel import Bretzel

    if not isinstance(app, Bretzel):
        raise ValueError(f"{target} ne désigne pas une instance Bretzel")

    if not reload:
        app.run(host=host, port=port)
        return

    from bretzel.server._dev import run_dev_server

    run_dev_server(
        target=target,
        host=host,
        port=port,
        log_level="info",
        watch_dirs=[watch_dir.resolve()],
    )


def _package_name(raw: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return normalized or "bretzel-app"

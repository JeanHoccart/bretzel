"""``Bretzel(static_dir=…)`` monte vraiment le dossier.

Le kwarg était accepté, stocké dans la config, et documenté « mounted at
``/static`` on the underlying FastAPI » — sans qu'aucun ``.mount()``
n'existe dans le dépôt (mesuré 2026-08-01). Un utilisateur qui le passait
recevait **rien**, en silence : pire qu'un kwarg absent, qui aurait levé.

Ces tests fixent le contrat câblé le 2026-08-01, dans les deux sens : le
dossier est servi, et un chemin faux **refuse le démarrage** au lieu de
monter un mount vide.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, ui

_SECRET = "x" * 24


def _app(static_dir: str | None) -> Bretzel:
    app = Bretzel(title="t", secret_key=_SECRET, static_dir=static_dir)

    @page("/")
    def home() -> None:
        ui.text("hi")

    app.include(home)
    return app


class TestStaticDir:
    def test_serves_a_declared_file(self, tmp_path: Path) -> None:
        (tmp_path / "logo.txt").write_text("BRETZEL", encoding="utf-8")
        with TestClient(_app(str(tmp_path))) as client:
            resp = client.get("/static/logo.txt")
        assert resp.status_code == 200
        assert resp.text == "BRETZEL"

    def test_unknown_file_is_404_not_500(self, tmp_path: Path) -> None:
        with TestClient(_app(str(tmp_path))) as client:
            assert client.get("/static/nope.txt").status_code == 404

    def test_missing_directory_refuses_to_boot(self, tmp_path: Path) -> None:
        """Un chemin faux est une faute de frappe : elle doit se voir.

        Le pendant du test précédent — sans lui, on aurait pu « câbler » le
        mount avec un ``check_dir=False`` silencieux et croire le contrat
        tenu alors qu'il ne sert rien.
        """
        ghost = tmp_path / "pas-la"
        with pytest.raises(RuntimeError, match="does not point at an existing folder"):
            with TestClient(_app(str(ghost))) as client:
                client.get("/")

    def test_no_static_dir_mounts_nothing(self) -> None:
        """Le défaut reste : aucune route ``/static``."""
        with TestClient(_app(None)) as client:
            assert client.get("/static/anything").status_code == 404

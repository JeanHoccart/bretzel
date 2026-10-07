"""``bretzel --version`` prints the package version and exits 0."""

from __future__ import annotations

import pytest

from bretzel import __version__
from bretzel.cli.main import build_parser


def test_version_flag_prints_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert f"bretzel {__version__}" in out

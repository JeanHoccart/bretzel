"""Unit tests for ``bretzel.theme.compiler``.

We don't ship the Tailwind binary in the test environment, so we
mock subprocess + filesystem boundaries. End-to-end compilation
goes in ``tests/integration/theme/`` (skipped automatically when
the binary isn't present).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bretzel.theme.compiler import (
    CompilerError,
    CompileResult,
    compile_with_lightning,
    find_lightning_binary,
    start_lightning_watch,
)

# ───────────────────────────────────────────────────────────────────────────
# find_lightning_binary
# ───────────────────────────────────────────────────────────────────────────


class TestFindBinary:
    def test_env_var_wins_when_executable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = tmp_path / "tw"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        monkeypatch.setenv("BRETZEL_TAILWIND_BIN", str(fake))
        assert find_lightning_binary() == fake

    def test_env_var_invalid_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "BRETZEL_TAILWIND_BIN", str(tmp_path / "does_not_exist")
        )
        with pytest.raises(CompilerError, match="not executable"):
            find_lightning_binary()

    def test_falls_through_to_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # No env override.
        monkeypatch.delenv("BRETZEL_TAILWIND_BIN", raising=False)
        # Stub the wheel lookup to return None.
        from bretzel.theme import compiler as mod

        monkeypatch.setattr(mod, "_find_wheel_binary", lambda: None)
        # Pretend ``tailwindcss`` IS on PATH.
        fake = tmp_path / "tailwindcss"
        fake.write_text("#!/bin/sh\n")
        monkeypatch.setattr(
            "shutil.which",
            lambda name: str(fake) if name == "tailwindcss" else None,
        )
        assert find_lightning_binary() == fake

    def test_nothing_found_raises_with_install_hints(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BRETZEL_TAILWIND_BIN", raising=False)
        from bretzel.theme import compiler as mod

        monkeypatch.setattr(mod, "_find_wheel_binary", lambda: None)
        monkeypatch.setattr("shutil.which", lambda name: None)
        with pytest.raises(CompilerError) as exc:
            find_lightning_binary()
        # The error names at least one install path.
        msg = str(exc.value)
        assert "tailwindcss" in msg
        assert "pip install" in msg


# ───────────────────────────────────────────────────────────────────────────
# compile_with_lightning
# ───────────────────────────────────────────────────────────────────────────


def _ok_run(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=stdout,
        stderr=stderr,
    )


def _err_run(stderr: str = "boom") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr=stderr,
    )


class TestCompileWithLightning:
    def test_writes_output_and_returns_result(self, tmp_path: Path) -> None:
        out = tmp_path / "build" / "style.css"
        bin_path = tmp_path / "tw"
        bin_path.write_text("")  # exists, content irrelevant under mock

        def fake_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            # The mock writes the output file so the size lookup works.
            output_index = args.index("-o") + 1
            Path(args[output_index]).write_text("/* compiled */", encoding="utf-8")
            return _ok_run(stdout="ok", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            result = compile_with_lightning(
                "@theme {}\n",
                output_path=out,
                binary=bin_path,
            )

        assert isinstance(result, CompileResult)
        assert result.output_path == out
        assert result.bytes_written > 0
        assert out.read_text(encoding="utf-8") == "/* compiled */"

    def test_passes_minify_flag(self, tmp_path: Path) -> None:
        out = tmp_path / "style.css"
        captured: dict[str, list[str]] = {}

        def fake_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            captured["args"] = list(args)
            Path(args[args.index("-o") + 1]).write_text("x", encoding="utf-8")
            return _ok_run()

        with patch("subprocess.run", side_effect=fake_run):
            compile_with_lightning(
                "x", output_path=out, binary=tmp_path / "tw", minify=True
            )
        assert "--minify" in captured["args"]

        captured.clear()
        with patch("subprocess.run", side_effect=fake_run):
            compile_with_lightning(
                "x", output_path=out, binary=tmp_path / "tw", minify=False
            )
        assert "--minify" not in captured["args"]

    def test_passes_content_paths(self, tmp_path: Path) -> None:
        out = tmp_path / "style.css"
        captured: dict[str, list[str]] = {}

        def fake_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            captured["args"] = list(args)
            Path(args[args.index("-o") + 1]).write_text("x", encoding="utf-8")
            return _ok_run()

        with patch("subprocess.run", side_effect=fake_run):
            compile_with_lightning(
                "x",
                output_path=out,
                binary=tmp_path / "tw",
                content_paths=[Path("/src"), Path("/lib")],
            )
        # Each --content path appears as its own pair.
        args = captured["args"]
        flags = [args[i] for i in range(len(args) - 1) if args[i] == "--content"]
        assert len(flags) == 2
        assert "/src" in args or "\\src" in args  # Win path separator

    def test_nonzero_exit_raises_with_stderr(self, tmp_path: Path) -> None:
        out = tmp_path / "style.css"
        with (
            patch("subprocess.run", return_value=_err_run("Tailwind: bad config")),
            pytest.raises(CompilerError, match="bad config"),
        ):
            compile_with_lightning("x", output_path=out, binary=tmp_path / "tw")

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "deep" / "nest" / "style.css"
        assert not out.parent.exists()

        def fake_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            Path(args[args.index("-o") + 1]).write_text("x", encoding="utf-8")
            return _ok_run()

        with patch("subprocess.run", side_effect=fake_run):
            compile_with_lightning("x", output_path=out, binary=tmp_path / "tw")
        assert out.exists()


# ───────────────────────────────────────────────────────────────────────────
# start_lightning_watch
# ───────────────────────────────────────────────────────────────────────────


class TestStartLightningWatch:
    def test_invokes_popen_with_watch_flag(self, tmp_path: Path) -> None:
        fake_popen = MagicMock()
        with patch("subprocess.Popen", fake_popen):
            start_lightning_watch(
                tmp_path / "in.css",
                tmp_path / "out.css",
                binary=tmp_path / "tw",
            )
        args = fake_popen.call_args.args[0]
        assert "--watch" in args
        assert str(tmp_path / "in.css") in args
        assert str(tmp_path / "out.css") in args

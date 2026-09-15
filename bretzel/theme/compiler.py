"""Subprocess wrapper around the Tailwind v4 / Lightning CSS binary.

Production deployments compile a tree-shaken ``style.css`` once at
``bretzel build`` time ; ``bretzel dev`` keeps the binary running in
``--watch`` mode for hot-reload.

This module owns the *spawn* — finding the binary, invoking it with
the right flags, surfacing errors with actionable messages. The
actual compilation is the binary's job.

Lightning CSS itself ships inside the Tailwind v4 binary distributed
as a Python wheel (``tailwindcss-python`` or ``pytailwindcss``,
TBD in phase 1). We don't pin which one yet — the binary resolver
walks every plausible install location in order.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


class CompilerError(RuntimeError):
    """Raised when the binary cannot be located or returns a non-zero
    exit code. The message includes whatever the binary printed to
    stderr so the user has something actionable on hand."""


# ───────────────────────────────────────────────────────────────────────────
# Locate the binary
# ───────────────────────────────────────────────────────────────────────────


def find_lightning_binary() -> Path:
    """Resolve the Tailwind v4 / Lightning CSS binary.

    Resolution order :

    1. ``$BRETZEL_TAILWIND_BIN`` env var (explicit override).
    2. The ``tailwindcss-python`` Python wheel, if installed
       (exposes a ``tailwindcss`` console script in the venv).
    3. ``shutil.which("tailwindcss")`` — system PATH lookup.

    Raises :class:`CompilerError` with install hints when nothing
    works — the user lands on a clear next-step.
    """
    env_path = os.environ.get("BRETZEL_TAILWIND_BIN")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise CompilerError(
            f"BRETZEL_TAILWIND_BIN points to {env_path!r} but the file "
            "is not executable or doesn't exist."
        )

    # Try the Python-wheel-installed console script first ; users on
    # macOS / Windows often install via ``pip install tailwindcss-python``
    # to avoid manual binary management.
    wheel = _find_wheel_binary()
    if wheel is not None:
        return wheel

    on_path = shutil.which("tailwindcss")
    if on_path:
        return Path(on_path)

    raise CompilerError(
        "Could not locate the Tailwind v4 / Lightning CSS binary.\n\n"
        "Install one of :\n"
        "  • pip install tailwindcss-python\n"
        "  • pip install pytailwindcss\n"
        "  • a system-level binary on $PATH (named ``tailwindcss``)\n\n"
        "Or set BRETZEL_TAILWIND_BIN to an explicit path."
    )


def _find_wheel_binary() -> Path | None:
    """Look for a ``tailwindcss`` / ``tailwindcss.exe`` in the active venv's
    Scripts/bin dir."""
    import sys

    venv_root = Path(sys.executable).parent
    for name in ("tailwindcss", "tailwindcss.exe"):
        candidate = venv_root / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


# ───────────────────────────────────────────────────────────────────────────
# Compile invocation
# ───────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class CompileResult:
    """Return value of a successful one-shot compile."""

    output_path: Path
    bytes_written: int
    stdout: str
    stderr: str


def compile_with_lightning(
    theme_css: str,
    *,
    output_path: Path,
    content_paths: Sequence[Path] = (),
    minify: bool = True,
    binary: Path | None = None,
    extra_args: Sequence[str] = (),
) -> CompileResult:
    """One-shot compile : feed ``theme_css`` to the binary, write to
    ``output_path``.

    Parameters :

    - ``theme_css`` : the entry stylesheet (the result of
      :func:`bretzel.theme.css.generate_theme_css_full`).
    - ``output_path`` : where the compiled CSS lands. Parent dir is
      created if missing.
    - ``content_paths`` : files to scan for utility usage. Tailwind v4
      auto-detects from the workspace, but explicit paths help when
      sources live outside the cwd.
    - ``minify`` : pass ``--minify`` (production) ; default ``True``.
    - ``binary`` : pre-resolved binary path (defaults to
      :func:`find_lightning_binary`).
    - ``extra_args`` : additional CLI flags appended verbatim.

    Raises :class:`CompilerError` on non-zero exit.
    """
    bin_path = binary or find_lightning_binary()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Tailwind v4 reads the entry CSS from stdin when ``-i -`` is used
    # — saves us a temp-file dance.
    args: list[str] = [
        str(bin_path),
        "-i", "-",
        "-o", str(output_path),
    ]
    if minify:
        args.append("--minify")
    for path in content_paths:
        args.extend(["--content", str(path)])
    args.extend(extra_args)

    proc = subprocess.run(
        args,
        input=theme_css,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise CompilerError(
            f"Tailwind/Lightning CSS exited with status {proc.returncode} :\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )

    bytes_written = output_path.stat().st_size if output_path.exists() else 0
    return CompileResult(
        output_path=output_path,
        bytes_written=bytes_written,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def start_lightning_watch(
    theme_css_path: Path,
    output_path: Path,
    *,
    content_paths: Sequence[Path] = (),
    binary: Path | None = None,
    extra_args: Sequence[str] = (),
) -> subprocess.Popen[bytes]:
    """Spawn the binary in ``--watch`` mode and return the live process.

    ⚠️ **Aucun appelant de production** (vérifié 2026-08-01 : le seul appel du
    dépôt est dans ``tests/unit/theme/test_compiler.py``). C'est normal —
    ``bretzel dev`` n'existe pas encore, et le pipeline CSS de dev compile
    Tailwind dans le navigateur. Cette fonction est la brique du jour où on
    câblera Lightning CSS (décision actée, cf. ``EVOLUTION.md``) ; gardée
    plutôt que supprimée pour cette raison, pas par oubli.

    Quand ce sera branché : the caller owns the lifecycle —
    ``proc.terminate()`` on shutdown.
    """
    bin_path = binary or find_lightning_binary()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    args: list[str] = [
        str(bin_path),
        "-i", str(theme_css_path),
        "-o", str(output_path),
        "--watch",
    ]
    for path in content_paths:
        args.extend(["--content", str(path)])
    args.extend(extra_args)

    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

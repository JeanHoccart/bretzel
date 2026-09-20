"""Standalone Tailwind v4 binary downloader + compile orchestration.

Mirrors the strategy from v1's ``archive/V1/bretzel/build/tailwind.py`` but
targets the v4 binaries (which read ``@import "tailwindcss"`` +
``@theme {}`` directly from the input CSS — no separate
``tailwind.config.js`` needed).

Download → cache in ``.bretzel/bin/`` → invoke via
:func:`bretzel.theme.compiler.compile_with_lightning`. The download
runs once ; subsequent calls reuse the cached binary.

Used by :mod:`bretzel.server.lifecycle` when ``css="build"`` to produce
the compiled stylesheet. This setting is independent of ``debug`` and
``mode``. Downloading requires an explicit ``allow_download=True``;
normal application startup only looks for an installed binary or cache.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import platform
import re
import stat
import tempfile
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from bretzel.theme.compiler import (
    CompilerError,
    compile_with_lightning,
    find_lightning_binary,
)

# ───────────────────────────────────────────────────────────────────────────
# Tailwind v4 standalone binary — pinned, overridable via env
# ───────────────────────────────────────────────────────────────────────────

_DEFAULT_VERSION = "v4.3.2"   # >= 4.1 : `@source inline(...)` support (4.0.0 rejects it)
_VERSION = os.environ.get("BRETZEL_TAILWIND_VERSION", _DEFAULT_VERSION)
_BASE_URL = (
    f"https://github.com/tailwindlabs/tailwindcss/releases/download/{_VERSION}"
)

_BINARIES = {
    ("linux",   "x86_64"):  "tailwindcss-linux-x64",
    ("linux",   "aarch64"): "tailwindcss-linux-arm64",
    ("darwin",  "x86_64"):  "tailwindcss-macos-x64",
    ("darwin",  "arm64"):   "tailwindcss-macos-arm64",
    ("windows", "amd64"):   "tailwindcss-windows-x64.exe",
    ("windows", "arm64"):   "tailwindcss-windows-arm64.exe",
}


# ───────────────────────────────────────────────────────────────────────────
# Cache layout
# ───────────────────────────────────────────────────────────────────────────


def _cache_dir() -> Path:
    """Per-project cache root — ``./.bretzel/`` next to the cwd.

    Mirrors v1's layout so users moving over recognise the directory.
    """
    d = Path.cwd() / ".bretzel"
    d.mkdir(exist_ok=True)
    return d


def _binary_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    elif system == "darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    else:
        system = "linux"
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    name = _BINARIES.get((system, arch))
    if not name:
        raise CompilerError(
            f"No Tailwind v4 binary available for {system}/{machine}. "
            "Set BRETZEL_TAILWIND_BIN to a manually-installed path."
        )
    return name


def _binary_path() -> Path:
    return _cache_dir() / "bin" / _binary_name()


# ───────────────────────────────────────────────────────────────────────────
# Download
# ───────────────────────────────────────────────────────────────────────────


def download_binary() -> Path:
    """Download the Tailwind v4 standalone binary if absent.

    Returns the cached path. Subsequent calls are cheap : we just
    ``stat`` the file on disk.
    """
    path = _binary_path()
    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{_BASE_URL}/{_binary_name()}"
    print(f"[bretzel] Downloading Tailwind CLI {_VERSION} ...")

    def _progress(count: int, block_size: int, total_size: int) -> None:
        if total_size > 0:
            pct = int(count * block_size * 100 / total_size)
            print(f"\r[bretzel] {min(pct, 100)} %", end="", flush=True)

    urllib.request.urlretrieve(url, path, reporthook=_progress)
    print()

    if platform.system() != "Windows":
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[bretzel] Binary ready -> {path}")
    return path


# ───────────────────────────────────────────────────────────────────────────
# Compile
# ───────────────────────────────────────────────────────────────────────────


#: What Tailwind reads besides the input CSS: it scans the workspace
#: looking for classes. These folders carry none, or none that are live,
#: and including them would make the fingerprint a needless cost.
_SCAN_SKIP: frozenset[str] = frozenset({
    ".bretzel", ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    "archive",          # V1 is READ-ONLY by charter, it does not move
})

#: The extensions a class can live in. A `.py` carries some (component
#: themes are Python), an `.html` does too.
_SCAN_SUFFIXES: frozenset[str] = frozenset({".py", ".html", ".js", ".md"})


def _content_fingerprint(roots: Sequence[Path]) -> str:
    """Fingerprint of the files the compiler SCANS.

    Tailwind v4 does not only compile the input CSS: it reads the
    workspace to know which classes exist. The compiled output therefore
    depends on TWO things, and the cache must reflect both.

    **Without this, a class change never reaches production.** On
    2026-08-27, replacing ``transition-all`` with an explicit list in
    ``sidebar/theme.py`` changed nothing: the class touches no colour, so
    it does not enter the safelist, so the input CSS's fingerprint does
    not move, so the cache returned the old file. The render stayed what
    it was, with not a single error.

    The trap was masked until then: the cache held a single slot and two
    apps kept taking it from each other, so it recompiled on almost every
    startup — fresh by accident. Fixing that uncovered this.

    We read ``(path, size, mtime_ns)``, never the content: it is a
    ``stat`` walk, not a read.

    ⚠️ **Pruning happens ON THE WAY DOWN, not by filtering afterwards.**
    A first version did ``root.rglob("*")`` then discarded the unwanted
    paths: so it descended into ``.git`` and ``archive/`` before throwing
    them away. Measured on this repository: **1 462 ms** against 60 ms
    with pruning — for a function that runs at the startup of every app
    in production mode.
    """
    parts: list[str] = []
    for root in roots:
        prefix = root.as_posix()
        for folder, subfolders, filenames in os.walk(root):
            subfolders[:] = [d for d in subfolders if d not in _SCAN_SKIP]
            base = Path(folder)
            for name in filenames:
                if os.path.splitext(name)[1] not in _SCAN_SUFFIXES:
                    continue
                path = base / name
                try:
                    st = path.stat()
                except OSError:
                    continue
                # The root's path PREFIXES the entry: two roots can
                # carry the same relative path (``theme/css.py`` exists
                # in the package AND in an app folder that mirrored it),
                # and two identical entries would cancel out in the hash.
                parts.append(
                    f"{prefix}/{path.relative_to(root).as_posix()}"
                    f":{st.st_size}:{st.st_mtime_ns}"
                )
    parts.sort()
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


#: A root declared in the theme CSS, as
#: :func:`bretzel.theme.tailwind.generate_source_directives` writes it.
_SOURCE_PATH_RE = re.compile(r'@source "([^"]+)";')


def scan_roots(theme_css: str) -> list[Path]:
    """The folders the compiler will read, for THIS input CSS.

    **The CSS is the source of truth, not a parameter.** The roots are
    already written in it — that is what the binary will read. Reading
    them back here rather than passing them down the stack guarantees
    the fingerprint covers exactly what is scanned: a caller cannot
    declare a root to the compiler while forgetting to declare it to the
    cache, which would return a stale ``style.css`` **with no error**.

    The ``cwd`` opens the list because Tailwind scans it by itself, with
    no directive saying so.

    A root nested inside another is dropped: walking it twice would
    double the walk's cost without changing a single entry (both passes
    would produce the same prefix for the same files).
    """
    roots: list[Path] = [Path.cwd().resolve()]
    for raw in _SOURCE_PATH_RE.findall(theme_css):
        path = Path(raw).resolve()
        if not path.is_dir():
            # An absent root is not silently made up for: the binary
            # will fail on it, and ``get_or_build_css`` turns that
            # failure into an explicit fallback. Here we ignore it only
            # so as not to bring the cache computation down.
            continue
        roots.append(path)
    # Pruning the nested ones, in both directions: the normal case of
    # the repository in development is ``cwd`` = the repository root, so
    # the package is INSIDE it and must not be walked a second time.
    return [
        r for r in roots
        if not any(other != r and other in r.parents for other in roots)
    ]


def _theme_digest(theme_css: str) -> str:
    """Fingerprint of the input — it NAMES the compiled file.

    It used to live in a ``style.css.sha256`` set beside a single
    ``style.css``, which left room for only ONE theme per folder. Cf.
    :func:`get_or_build_css`.
    """
    return hashlib.sha256(theme_css.encode("utf-8")).hexdigest()


#: How many compiled sheets the cache keeps. Each weighs 230 to 740 KB,
#: and the key includes the fingerprint of the scanned sources: **any**
#: edit to a framework ``theme.py`` creates a fresh entry. Without
#: eviction, measured on 2026-08-30 on the dev machine: **470 files,
#: 298 MB** accumulated over two days of work on the themes.
#:
#: Twelve because that is what a normal round trip consumes — two or
#: three example apps, each with its theme variations — without paying
#: 3 s of recompilation on every switch.
CACHE_KEEP: Final[int] = 12


def _touch(path: Path) -> None:
    """Set the date to now. Never raises — losing an LRU rank has no
    consequence, losing an app startup does."""
    with contextlib.suppress(OSError):
        path.touch()


def _sheet_for(pointer: Path) -> Path | None:
    """The sheet this pointer designates, or ``None``.

    An ORPHANED pointer — whose sheet has been evicted — returns
    ``None``, so it behaves like a cache miss: we recompile. That is the
    right default, and it is why eviction does not have to touch the
    pointers to stay correct.
    """
    try:
        sheet = pointer.parent / pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return sheet if sheet.is_file() else None


def _store_sheet(scratch: Path, css_dir: Path, pointer: Path) -> Path:
    """Store the freshly compiled sheet UNDER THE FINGERPRINT OF ITS
    CONTENT, and point the key at it.

    Why two levels. The cache key includes the fingerprint of the
    scanned sources — it MUST, otherwise changing a class that touches
    no colour would never reach production (cf.
    :func:`_content_fingerprint`). But the converse is false: touching a
    ``theme.py`` without changing a single class produces a fresh key for
    an IDENTICAL output.

    Measured on 2026-08-31: **6 of the 7 cached sheets were byte for
    byte identical** — two distinct contents for seven entries. The cache
    advertised twelve slots and held two useful ones during a session of
    theme work, and the CRM's sheet could be evicted by six copies of the
    playground's.

    Addressing by content fixes that without touching the key: twelve
    slots now hold twelve DIFFERENT themes.
    """
    payload = scratch.read_bytes()
    sheet = css_dir / f"{hashlib.sha256(payload).hexdigest()[:16]}.css"
    if sheet.is_file():
        # Already there, byte for byte: we throw away the duplicate and
        # bump its date, since we have just used it.
        with contextlib.suppress(OSError):
            scratch.unlink()
        _touch(sheet)
    else:
        try:
            scratch.replace(sheet)
        except OSError:
            # Another process may have stored it in the meantime. Its
            # copy is as good as ours — they have the same fingerprint.
            if not sheet.is_file():
                raise
    with contextlib.suppress(OSError):
        pointer.write_text(sheet.name, encoding="utf-8")
    return sheet


def _prune_css_cache(css_dir: Path, *, keep: int = CACHE_KEEP) -> int:
    """Keep only the ``keep`` MOST RECENTLY USED sheets.

    By modification date, and the cache-hit path refreshes it: without
    that ``touch``, the order would be that of compilations, so the sheet
    served ten times a day would be evicted by a variation compiled once
    and never read again.

    Never raises. A file another process holds open refuses to be deleted
    on Windows, and losing an eviction has no consequence — losing the
    app's startup does.
    """
    try:
        entries = sorted(
            css_dir.glob("*.css"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return 0
    removed = 0
    for stale in entries[keep:]:
        try:
            stale.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def get_or_build_css(
    theme_css: str, *, rebuild: bool = False, allow_download: bool = False
) -> str:
    """Return a compiled ``style.css`` string for ``theme_css``.

    Tries (in order):

    1. The already-cached compilation for THIS input —
       ``./.bretzel/css/<fingerprint>.css``, unless ``rebuild=True``.
    2. A binary already locatable via :func:`find_lightning_binary`
       (env var / wheel / ``$PATH``) — runs the compile, caches the
       result.
    3. A binary already present in ``./.bretzel/bin/``. Downloading it
       is only allowed when ``allow_download=True``.

    Errors :class:`CompilerError` if every path fails.

    The key combines the input CSS and the fingerprint of the scanned
    sources. A ``.key`` file points at the sheet named by its content:
    several entries can share the same compiled CSS. The cache is bounded
    by :data:`CACHE_KEEP` and can be rebuilt after deletion.
    """
    cache = _cache_dir()
    # TWO inputs, hence two halves of a key: the theme CSS, and the
    # files the compiler scans to find classes in. The scanned roots come
    # out of the CSS itself (``scan_roots``): the ``cwd``, plus the
    # installed package and what the app declared.
    digest = _theme_digest(
        theme_css + _content_fingerprint(scan_roots(theme_css))
    )
    css_dir = cache / "css"
    css_dir.mkdir(parents=True, exist_ok=True)
    pointer = css_dir / f"{digest[:16]}.key"

    if not rebuild:
        sheet = _sheet_for(pointer)
        if sheet is not None:
            # ``touch``: that is what makes eviction an LRU rather than
            # a FIFO. Without it, the sheet served every day would carry
            # its compilation date and fall before a variation compiled
            # once by mistake.
            _touch(sheet)
            _touch(pointer)
            return sheet.read_text(encoding="utf-8")

    # No implicit download at startup: the caller must explicitly allow
    # this network access with ``allow_download``.
    try:
        binary = find_lightning_binary()
    except CompilerError:
        # ``find_lightning_binary`` only knows the env, the wheel and
        # the PATH — not our own cache. A binary already downloaded into
        # ``.bretzel/bin/`` must obviously serve.
        cached = _binary_path()
        if cached.is_file():
            binary = cached
        elif allow_download:
            binary = download_binary()
        else:
            raise

    print("[bretzel] Compiling Tailwind CSS ...")
    import time

    t0 = time.time()
    # We compile to a TEMPORARY name: the final name is the fingerprint
    # of what comes out, and we only know it afterwards.
    #
    # ⚠️ **The name must be unique per CALLER, not per key.** It was
    # derived from the key, so two processes compiling the SAME theme at
    # the same time shared the file: the first renamed it, the second
    # read a vanished path and died on ``FileNotFoundError`` at the app's
    # startup. And "two apps starting together from the same root" is
    # precisely the situation this cache holds several slots for.
    #
    # Found on 2026-08-31 in `-m browser -n 4`, and the lesson is worth
    # more than the fix: it showed up as a pytest COLLECTION error
    # ("Different tests were collected between gw3 and gw0"), on three
    # runs out of six, because the gate mounting the benches does it at
    # import time. I first attributed it to my own edits — wrongly.
    fd, tmp_name = tempfile.mkstemp(
        dir=css_dir, prefix=f".{digest[:16]}.", suffix=".tmp",
    )
    os.close(fd)
    scratch = Path(tmp_name)
    result = compile_with_lightning(
        theme_css,
        output_path=scratch,
        binary=binary,
        minify=True,
    )
    elapsed = round(time.time() - t0, 1)
    css_path = _store_sheet(scratch, css_dir, pointer)
    size_kb = result.bytes_written // 1024
    print(
        f"[bretzel] CSS ready - {size_kb} KB raw "
        f"(~{max(size_kb // 5, 1)} KB gzip) ({elapsed}s) -> {css_path}"
    )
    _prune_css_cache(css_dir)
    return css_path.read_text(encoding="utf-8")


__all__ = [
    "CACHE_KEEP",
    "download_binary",
    "get_or_build_css",
    "scan_roots",
]

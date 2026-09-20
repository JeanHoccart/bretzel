"""The roots the production compiler SCANS — and who declares them.

Tailwind does not only compile the input CSS: it reads files to know
which classes to keep. Without a directive, it only reads the ``cwd``.
This module therefore answers a single question, and that is its whole
reason to exist: **which folders, besides the current one.**

Three answers, and their order says what they are:

1. **The framework package**, always, without anyone asking. The bug
   closed on 2026-08-29 was exactly its absence: installed by pip,
   ``bretzel`` is no longer under the ``cwd``, so the classes of its
   ``theme.py`` files disappeared from the production ``style.css`` —
   609 KB against 684, with no error, with the right colours and no
   formatting at all.
2. **What installed packages declare**, through the ``bretzel.scan_roots``
   entry point (cf. :func:`discovered_source_roots`).
3. Nothing else. There is **no** third door — no ``Theme`` kwarg, no
   config option. One single way to do each thing (charter principle 4),
   and this is the one because it is the only one where ``pip install``
   is enough: the app writes nothing for a third-party package to be
   scanned.

Declaring a root
----------------
A package carrying Tailwind classes — a third-party component library,
**or the app itself when it ships as a package** — says so in its
``pyproject.toml`` ::

    [project.entry-points."bretzel.scan_roots"]
    my-components = "my_components"

The key is free (it only serves diagnostics); the value is the **name of
an importable module**, whose folder becomes the root.

⚠️ **A declared root is a folder READ at startup**, not code that runs:
resolution goes through :func:`importlib.util.find_spec`, which does not
load the module.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from functools import cache
from importlib import metadata, util
from pathlib import Path

#: The installed package — the root carrying the component themes.
#:
#: ``parents[1]`` from ``bretzel/theme/sources.py`` gives ``bretzel/``,
#: **wherever the package is laid down**: the development repository, or
#: the ``site-packages`` of whoever installs it.
#:
#: It is computed, NOT discovered, and that is deliberate: going through
#: the entry point would make the framework's render depend on the
#: presence of its own metadata, and therefore break an uninstalled
#: ``git clone``. The one root whose path we know without reading
#: anything is also the one we cannot afford to miss.
FRAMEWORK_SOURCE_ROOT: Path = Path(__file__).resolve().parents[1]

#: The entry-point group. It is a **public API**: a third-party package
#: writes it in its ``pyproject.toml``, so renaming it breaks their
#: metadata without any test in this repository seeing it.
ENTRY_POINT_GROUP = "bretzel.scan_roots"


@cache
def discovered_source_roots() -> tuple[Path, ...]:
    """The roots installed packages declare, sorted.

    **Sorted, and that is structural**: entry-point order depends on
    ``sys.path`` order and on the file system. And these roots go into
    the CSS, whose fingerprint NAMES the cached compiled file
    (``build.get_or_build_css``). An unstable order would produce two
    fingerprints for one environment, hence a two-second recompilation
    on every startup — the exact illness fixed on 2026-08-27,
    reintroduced through the next door.

    An unusable entry does not bring startup down — the app is not
    responsible for a third party's metadata — but it does not pass in
    silence either: that package's classes would be missing in
    production, and nothing else would say so. Same arbitration as the
    compiler fallback, which also announces itself.

    Memoised: installation metadata does not change during a process's
    life. ``discovered_source_roots.cache_clear()`` exists for the
    tests, which fabricate entry points.
    """
    roots: set[Path] = set()
    for point in metadata.entry_points(group=ENTRY_POINT_GROUP):
        path = _root_of_module(point.module)
        if path is None:
            print(
                f"[bretzel] WARN: the {ENTRY_POINT_GROUP} entry point "
                f"\"{point.name}\" names {point.module!r}, not found.\n"
                "[bretzel]        Its Tailwind classes will be missing "
                "from the compiled style.css."
            )
            continue
        roots.add(path)
    return tuple(sorted(roots))


def _root_of_module(name: str) -> Path | None:
    """An importable module's folder, **without importing it**.

    A package (``my_components``) returns its folder; a plain module
    (``my_components.theme``) returns the folder containing it — both
    forms work, because an author will write one or the other without
    thinking about the difference.

    Returns ``None`` when the name does not resolve: uninstalled
    package, orphaned metadata, typo.
    """
    already_loaded = sys.modules.get(name)
    if already_loaded is not None:
        spec = getattr(already_loaded, "__spec__", None)
    else:
        try:
            spec = util.find_spec(name)
        except (ImportError, AttributeError, ValueError):
            return None
    if spec is None:
        return None
    if spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations))).resolve()
    if spec.origin and spec.origin != "built-in":
        return Path(spec.origin).resolve().parent
    return None


def all_source_roots() -> tuple[Path, ...]:
    """The framework package, then what the others declare.

    The framework first because it is the only certain one; the rest
    sorted by :func:`discovered_source_roots`. A root declared twice
    appears once.
    """
    roots: list[Path] = [FRAMEWORK_SOURCE_ROOT]
    roots.extend(
        r for r in discovered_source_roots() if r != FRAMEWORK_SOURCE_ROOT
    )
    return tuple(roots)


def generate_source_directives(roots: Iterable[Path | str]) -> str:
    """Return the Tailwind v4 ``@source "<dir>";`` block for ``roots``.

    Measured on 2026-08-29, ``cwd`` = some app folder, real production
    path (``get_or_build_css``) ::

        without directive   609 KB   tabular-nums ABSENT · 16rem ABSENT
        with                684 KB   both PRESENT

    The ``@source inline(...)`` safelist could not make up for it, and
    that is what makes the two mechanisms complementary rather than
    redundant: the safelist only closes what the scanner CANNOT see (a
    ``{bg_color}`` unresolved at render time). A static class like
    ``rounded-md`` is perfectly visible — provided one looks in the right
    folder.

    A path is written as-is into CSS: a quote inside it would cut the
    directive in the middle, so it raises rather than producing a broken
    sheet.

    ⚠️ **For the production compiler only.** The dev mode's browser
    compiler reads the live DOM, not the disk; these directives are
    stripped from the inlined CSS by
    :func:`bretzel.theme.css.strip_scan_roots`.
    """
    lines: list[str] = []
    for root in roots:
        path = Path(root).resolve().as_posix()
        if '"' in path:
            raise ValueError(
                f"Unusable scan root: {path!r} contains a quote, which "
                'would end the @source "…" directive in the middle of the '
                "path."
            )
        lines.append(f'@source "{path}";')
    return "\n".join(lines)


__all__ = [
    "ENTRY_POINT_GROUP",
    "FRAMEWORK_SOURCE_ROOT",
    "all_source_roots",
    "discovered_source_roots",
    "generate_source_directives",
]

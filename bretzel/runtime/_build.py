"""Assemble the ``_src/[0-9]*_*.js`` sources in the order of their names.

``python -m bretzel.runtime._build`` produces ``runtime.js`` and
``runtime.min.js``. The ``--check`` option verifies that the two committed
files match the sources, without rewriting them.

Each source keeps its IIFE. The substitutions declared in ``_TOKENS`` take
the constants from :mod:`bretzel.runtime.protocol`; the size reduction is
provided by :mod:`bretzel.runtime._minify`.

The server serves the readable bundle in dev mode and its reduced form in
production. Bundle freshness is tested; no size budget is enforced.
See ``.claude/bretzel/runtime.md`` for the runtime contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # bretzel/runtime
SRC = HERE / "_src"
PROJECT = HERE.parent.parent                    # repo root
sys.path.insert(0, str(PROJECT))

from bretzel.runtime._minify import minify  # noqa: E402
from bretzel.runtime.protocol import (  # noqa: E402
    ENVELOPE_TAG_NAME,
    NAV_PENDING_KEY,
    PATCH_TAG_NAME,
    PROTOCOL_VERSION,
    ROUTE_ACTION,
    SCREEN_SYNC_FN,
)

_TOKENS = {
    "__PROTOCOL_VERSION__": PROTOCOL_VERSION,
    "__ENVELOPE_TAG__": ENVELOPE_TAG_NAME,
    "__PATCH_TAG__": PATCH_TAG_NAME,
    "__SCREEN_SYNC_FN__": SCREEN_SYNC_FN,
    "__ROUTE_ACTION__": ROUTE_ACTION,
    "__NAV_PENDING_KEY__": NAV_PENDING_KEY,
}


def _bundle() -> str:
    parts = [
        source.read_text(encoding="utf-8")
        for source in sorted(SRC.glob("[0-9]*_*.js"))
    ]
    bundle = "\n\n".join(parts)
    for token, value in _TOKENS.items():
        bundle = bundle.replace(token, value)
    return bundle


#: The readable bundle (served in dev) and its reduced form (served in
#: prod). Both are committed: an installed package does not replay the
#: build.
READABLE = HERE / "runtime.js"
MINIFIED = HERE / "runtime.min.js"


def build() -> Path:
    bundle = _bundle()
    READABLE.write_text(bundle, encoding="utf-8", newline="\n")
    small = minify(bundle)
    MINIFIED.write_text(small, encoding="utf-8", newline="\n")
    count = len(list(SRC.glob("[0-9]*_*.js")))
    print(
        f"Built {READABLE} - {len(bundle):,} chars from {count} modules "
        f"(+ {MINIFIED.name}, {len(small):,} chars)."
    )
    return READABLE


def check() -> int:
    """CI helper: non-zero when either bundle is stale vs ``_src/``.

    BOTH are checked. A stale ``runtime.min.js`` does not show in dev —
    which serves the other file — and would only break in production,
    that is to say in the place where it is discovered worst.
    """
    bundle = _bundle()
    for target, expected in ((READABLE, bundle), (MINIFIED, minify(bundle))):
        if not target.exists():
            print(
                f"[bretzel] {target.name} missing - run "
                "python -m bretzel.runtime._build"
            )
            return 1
        if target.read_text(encoding="utf-8") != expected:
            print(
                f"[bretzel] {target.name} is stale - run "
                "python -m bretzel.runtime._build and commit the result."
            )
            return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        sys.exit(check())
    build()

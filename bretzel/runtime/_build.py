"""Assemble the runtime sources in the order declared by :data:`~bretzel.runtime.sources.MODULES`.

``python -m bretzel.runtime._build`` produces ``runtime.js`` and
``runtime.min.js``. The ``--check`` option verifies that the two committed
files match the sources, without rewriting them.

Each source keeps its IIFE. The substitutions declared in ``_TOKENS`` take
the constants from :mod:`bretzel.runtime.protocol`; the size reduction is
provided by :mod:`bretzel.runtime._minify`.

The server serves the readable bundle in dev mode and its reduced form in
production. Bundle freshness is tested; no size budget is enforced.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # bretzel/runtime
PROJECT = HERE.parent.parent                    # repo root
sys.path.insert(0, str(PROJECT))

from bretzel.runtime._minify import minify  # noqa: E402
from bretzel.runtime.protocol import (  # noqa: E402
    ADDRESSABLE_ID,
    AT_TAG_NAME,
    BUSY_CLASS,
    DATA_BZ_BASE,
    DATA_BZ_BUSY,
    DATA_BZ_REPLACE,
    DATA_NAV_HREF,
    ENVELOPE_TAG_NAME,
    NAV_PENDING_KEY,
    PATCH_TAG_NAME,
    PROTOCOL_VERSION,
    ROUTE_ACTION,
    SCREEN_SYNC_FN,
    SINK_ELEMENT_ID,
    TITLE_EVENT,
)
from bretzel.runtime.sources import COMPONENTS, MODULES, SOURCES, SRC  # noqa: E402,F401

_TOKENS = {
    "__PROTOCOL_VERSION__": PROTOCOL_VERSION,
    "__ENVELOPE_TAG__": ENVELOPE_TAG_NAME,
    "__PATCH_TAG__": PATCH_TAG_NAME,
    "__AT_TAG__": AT_TAG_NAME,
    "__ADDRESSABLE_ID__": ADDRESSABLE_ID,
    "__BUSY_ATTR__": DATA_BZ_BUSY,
    "__BUSY_CLASS__": BUSY_CLASS,
    "__REPLACE_ATTR__": DATA_BZ_REPLACE,
    "__NAV_ATTR__": DATA_NAV_HREF,
    "__SINK_ID__": SINK_ELEMENT_ID,
    "__SCREEN_SYNC_FN__": SCREEN_SYNC_FN,
    "__ROUTE_ACTION__": ROUTE_ACTION,
    "__BASE_ATTR__": DATA_BZ_BASE,
    "__NAV_PENDING_KEY__": NAV_PENDING_KEY,
    "__TITLE_EVENT__": TITLE_EVENT,
}


def _bundle() -> str:
    parts = [source.read_text(encoding="utf-8") for source in SOURCES]
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
    print(
        f"Built {READABLE} - {len(bundle):,} chars from {len(SOURCES)} modules "
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

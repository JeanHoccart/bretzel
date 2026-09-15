"""Gate : the runtime JS mirrors ``protocol.py`` verbatim.

``protocol.py`` is the single source of truth for every wire token —
``bz-*`` attribute names, HTTP headers, envelope tags, SSE events. The JS
runtime cannot import Python, so it re-hardcodes those strings ; a classic
drift point (the V2→V3 rename left code emitting ``bz-prop:`` after the
constant moved to ``bz-attr:``). This gate discovers the token set by
*introspection* — no hardcoded list — and asserts each value appears
verbatim in the built ``runtime.js``. A new ``BZ_*_PREFIX`` / ``HEADER_*``
/ tag is covered automatically ; a rename on one side only fails here at
commit time instead of surfacing in a manual audit weeks later.

Excluded by design (documented, not oversights) :
- ``ROUTE_*`` / ``SINK_ELEMENT_ID`` — the JS learns endpoints from the
  ``<bz-envelope>`` at runtime, it never hardcodes them (anti-règle 3).
- ``BZ_STATE_ATTR`` — reserved protocol surface, emitted/read by nothing
  yet (guarded as an export by ``test_protocol.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bretzel.runtime import protocol

#: Preuve de morsure : contrôle POSITIF — l'introspection des constantes rend encore un
#: miroir peuplé.
MUTATION_PROOF = "test_mirror_set_is_non_trivial"

_RUNTIME_JS = Path(protocol.__file__).resolve().parent / "runtime.js"


def _mirrored_tokens() -> list[tuple[str, str]]:
    """``(name, value)`` for every constant the JS must mirror.

    Membership is derived from naming convention so new constants are
    covered without touching this test : directive prefixes
    (``BZ_*_PREFIX``), ``data-bz-*`` stamps (``DATA_BZ_*`` /
    ``DATA_SUBSCRIBE_*``), HTTP headers (``HEADER_*``), SSE event names
    (``SSE_*``) and custom-element tags (``*_TAG_NAME``).
    """
    out: list[tuple[str, str]] = []
    for name, value in vars(protocol).items():
        if not (isinstance(value, str) and name.isupper()):
            continue
        mirrored = (
            (name.startswith("BZ_") and name.endswith("_PREFIX"))
            or name.startswith("DATA_BZ")
            or name.startswith("DATA_SUBSCRIBE")
            or name.startswith("HEADER_")
            or name.startswith("SSE_")
            or name.endswith("_TAG_NAME")
            or name == "SERVERSYNC_KEY"  # bz-data scope marker read by 03_scope.js
            or name == "SCREEN_SYNC_FN"  # global called by name in 05_bridge.js
        )
        if mirrored:
            out.append((name, value))
    return out


@pytest.fixture(scope="module")
def runtime_js() -> str:
    assert _RUNTIME_JS.exists(), f"built runtime.js missing at {_RUNTIME_JS}"
    return _RUNTIME_JS.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "value"), _mirrored_tokens(), ids=lambda p: p if isinstance(p, str) else ""
)
def test_wire_token_present_in_runtime_js(name: str, value: str, runtime_js: str) -> None:
    assert value in runtime_js, (
        f"protocol.{name} = {value!r} is not present verbatim in runtime.js. "
        f"Either the JS drifted from protocol.py, or runtime.js needs a "
        f"rebuild : `py -m bretzel.runtime._build`."
    )


def test_mirror_set_is_non_trivial() -> None:
    # Guard against the discovery predicate silently matching nothing
    # (e.g. a refactor renames the constants) — which would make the
    # parametrized test vacuously pass.
    assert len(_mirrored_tokens()) >= 20

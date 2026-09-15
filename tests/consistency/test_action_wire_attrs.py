"""Gate : the server-action wire attrs live in ONE tuple.

The bundle a value-holding control relocates from its root onto the
hidden ``<input>`` (``hx-post`` / ``hx-trigger`` / ``hx-target`` /
``hx-swap`` / ``hx-vals`` / ``data-bz-sig`` / ``data-bz-ts``) used to be
copy-pasted into 8+ component modules. At the HMAC-v2 rollout four of
those copies missed ``data-bz-ts`` : the signed render timestamp stayed
on the handler-less root, the bridge forwarded an empty ``X-Bz-Ts`` and
**every** action POST for those controls 403'd (cf. traps.md
§ "data-bz-ts oublié au relocate" — the bug that kicked off this audit).

The tuple now lives once, in ``base/_wiring.SERVER_ACTION_ATTRS``, and
every value-holding control imports it. This gate keeps it that way so
the fix can't rot back into N drifting copies :

1. no component re-lists ``"hx-post"`` as a tuple element (i.e. rebuilds
   the bundle locally) ;
2. no component hardcodes the ``data-bz-sig`` / ``data-bz-ts`` wire
   literals (they must flow from the shared constant) ;
3. the sig+ts couple is asserted structurally — nobody can drop the ts.
"""

from __future__ import annotations

import re
from pathlib import Path

from bretzel.components.base._wiring import (
    CHANGE_HANDLER_KEYS,
    SERVER_ACTION_ATTRS,
)
from bretzel.runtime import BZ_ON_PREFIX, DATA_BZ_SIG, DATA_BZ_TS
from tests.consistency._discovery import (
    assert_sweep_is_not_vacuous,
    component_sources,
)

_COMPONENTS = Path(__file__).resolve().parents[2] / "bretzel" / "components"
_CANONICAL = ("base", "_wiring.py")  # the ONE place the tuple may live

# ``"hx-post",`` as a tuple element (trailing comma) — NOT the membership
# checks ``if "hx-post" in attrs`` (no comma) nor the emitter dict key
# ``"hx-post": ...`` (colon) that legitimately name the attribute.
_TUPLE_ELEMENT = re.compile(r"""["']hx-post["']\s*,""")
_SIG_TS_LITERALS = ('"data-bz-sig"', "'data-bz-sig'", '"data-bz-ts"', "'data-bz-ts'")


def _rel(py: Path) -> str:
    return str(py.relative_to(_COMPONENTS.parent.parent))


def test_no_component_redefines_the_action_tuple() -> None:
    offenders = [
        _rel(py)
        for py in component_sources()
        if py.parts[-2:] != _CANONICAL
        and _TUPLE_ELEMENT.search(py.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "These component modules rebuild the server-action tuple locally "
        "instead of importing SERVER_ACTION_ATTRS from base/_wiring — the "
        f"exact shape that let 4 copies drift into the HMAC-v2 403: {offenders}"
    )


def test_the_sig_ts_sweep_visits_the_components() -> None:
    """Non-vacuity floor — the test below is a prohibition."""
    assert_sweep_is_not_vacuous()


def test_no_component_hardcodes_sig_ts_literals() -> None:
    offenders = [
        _rel(py)
        for py in component_sources()
        if any(lit in py.read_text(encoding="utf-8") for lit in _SIG_TS_LITERALS)
    ]
    assert not offenders, (
        "These component modules hardcode the data-bz-sig/data-bz-ts wire "
        "literals — use DATA_BZ_SIG / DATA_BZ_TS (via SERVER_ACTION_ATTRS) "
        f"so a rename can't leave a silent 403 behind: {offenders}"
    )


def test_sig_and_ts_travel_together() -> None:
    assert DATA_BZ_SIG in SERVER_ACTION_ATTRS
    assert DATA_BZ_TS in SERVER_ACTION_ATTRS, (
        "data-bz-ts must stay in SERVER_ACTION_ATTRS — dropping it "
        "reintroduces the HMAC-v2 403 (sig relocates without ts → the "
        "bridge forwards an empty X-Bz-Ts → verify fails)."
    )


def test_change_handler_keys_is_the_superset() -> None:
    # The BOTH-shapes tuple (used by Accordion/Pagination/Tree/Tabs) is
    # exactly the server bundle plus the string-handler event.
    assert (*SERVER_ACTION_ATTRS, f"{BZ_ON_PREFIX}change") == CHANGE_HANDLER_KEYS


def test_the_detector_still_bites() -> None:
    """Mutation : un tuple d'attributs d'action re-listé est reconnu.

    Le 403 sournois du 2026-07-04 venait de là : le tuple était recopié
    dans huit composants et l'un d'eux a manqué le ``data-bz-ts``. Si la
    regex cessait de matcher, la neuvième copie passerait.
    """
    for offending in ('("hx-post", "data-bz-sig")', "('hx-post' , 'x')"):
        assert _TUPLE_ELEMENT.search(offending), f"{offending!r} devrait mordre"
    assert not _TUPLE_ELEMENT.search('attrs["hx-post"] = url'), "faux positif"

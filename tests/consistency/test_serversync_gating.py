"""Gate : server-backed overlays / date inputs opt into ``_serverSync``.

The ``_serverSync`` marker is what lets a ``@refreshable`` morph re-adopt a
server-authoritative scope value (``absorb`` preserves the live client signal
otherwise, so a server-driven ``open=state.field`` / ``value=state.field``
change would never reach the DOM). It must be emitted ONLY when the prop is
server-backed — a literal keeps its client state across an unrelated refresh,
and a ClientBinding lives in ``$bz._store`` (never a scope signal).

Commit ``0972a6d`` fixed exactly this for the overlays + date family
(dialog/drawer/dropdown/popover, date_picker/date_range_picker, calendar) —
they were rendering the stale value on refresh — but shipped WITH NO GUARD.
The value-holding inputs (select/combobox/slider/number_input/toggle_group)
and nav (tabs/pagination/accordion/tree) already carry an inline
``TestServerSyncGating`` in their unit files ; this gate closes the blind spot
for the seven that didn't, so a regression (marker dropped, or leaked onto a
literal / binding) fails at commit.

Contract per component : server-backed → emits ``_serverSync`` ·
literal → omits · binding → omits.
"""

from __future__ import annotations

import datetime as dt

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.runtime import SERVERSYNC_KEY
from bretzel.state.scopes.client import ClientBinding
from bretzel.state.scopes.server import _BoundBool, _BoundDate, _BoundTuple

#: Preuve de morsure : les deux sens dans un seul test : valeur backée serveur → marker,
#: littéral → pas de marker.
MUTATION_PROOF = "test_serversync_gated_on_server_backed"

_D1 = dt.date(2024, 6, 15)
_D2 = dt.date(2024, 7, 20)


def _binding(field: str, value: object) -> ClientBinding:
    return ClientBinding(
        class_name="UI", instance_key="default", field_name=field, value=value
    )


# (label, server_backed, literal, binding) — each a zero-arg factory that
# builds the component (must run inside a render context). New server-sync
# components join this table.
_CASES = [
    ("dialog",
     lambda: ui.dialog(open=_BoundBool(True, "o")),
     lambda: ui.dialog(open=True),
     lambda: ui.dialog(open=_binding("o", False))),
    ("drawer",
     lambda: ui.drawer(open=_BoundBool(True, "o")),
     lambda: ui.drawer(open=True),
     lambda: ui.drawer(open=_binding("o", False))),
    ("dropdown",
     lambda: ui.dropdown(open=_BoundBool(True, "o")),
     lambda: ui.dropdown(open=True),
     lambda: ui.dropdown(open=_binding("o", False))),
    ("popover",
     lambda: ui.popover(open=_BoundBool(True, "o")),
     lambda: ui.popover(open=True),
     lambda: ui.popover(open=_binding("o", False))),
    ("date_picker",
     lambda: ui.date_picker(value=_BoundDate(_D1, "v")),
     lambda: ui.date_picker(value=_D1),
     lambda: ui.date_picker(value=_binding("v", _D1.isoformat()))),
    ("date_range_picker",
     lambda: ui.date_range_picker(value=_BoundTuple((_D1, _D2), "v")),
     lambda: ui.date_range_picker(value=(_D1, _D2)),
     lambda: ui.date_range_picker(value=_binding("v", [_D1.isoformat(), _D2.isoformat()]))),
    ("calendar",
     lambda: ui.calendar(month=_BoundDate(_D1, "m")),
     lambda: ui.calendar(month=_D1),
     lambda: ui.calendar(month=_binding("m", _D1.isoformat()))),
]


def _emits_marker(factory) -> bool:
    with render_isolated():
        return SERVERSYNC_KEY in serialize(factory().render())


@pytest.mark.parametrize("label,server_backed,literal,binding", _CASES,
                         ids=[c[0] for c in _CASES])
def test_serversync_gated_on_server_backed(label, server_backed, literal, binding) -> None:
    assert _emits_marker(server_backed), (
        f"{label}: a server-backed prop must emit '{SERVERSYNC_KEY}' so a "
        f"@refreshable morph re-adopts the server value (else the control "
        f"renders the stale client signal — the 0972a6d bug)."
    )
    assert not _emits_marker(literal), (
        f"{label}: a literal prop must NOT emit '{SERVERSYNC_KEY}' — an "
        f"unrelated refresh would wipe the user's client state."
    )
    assert not _emits_marker(binding), (
        f"{label}: a ClientBinding prop must NOT emit '{SERVERSYNC_KEY}' — its "
        f"value lives in $bz._store, patched by the envelope, never a scope signal."
    )


def test_range_value_as_a_list_of_stamped_dates_is_server_backed() -> None:
    """La forme ``value=[state.debut, state.fin]`` compte comme serveur.

    Le tableau ci-dessus n'exerçait que le shape « stampé à l'extérieur »
    (``_BoundTuple``), et DateRangePicker gardait un test inline sur le
    ``field_name`` de la liste — qui n'en a pas. Résultat : pour le
    pattern documenté à deux champs serveur distincts, aucun
    ``_serverSync`` n'était émis et un changement serveur de la plage
    était perdu au morph. Divergence VIVANTE (contrairement aux 6 autres
    call-sites du même dialecte, dont la valeur est scalaire) — corrigée
    en routant par ``_value_server_backed``, dont c'est le « case 3 ».
    Cf. audit F25 + gate ``test_server_backed_single_dialect``.
    """
    assert _emits_marker(
        lambda: ui.date_range_picker(
            value=[_BoundDate(_D1, "start"), _BoundDate(_D2, "end")]
        )
    ), (
        f"date_range_picker : value=[state.debut, state.fin] est "
        f"server-backed (deux dates stampées dans une liste littérale) et "
        f"doit émettre '{SERVERSYNC_KEY}'. Un test inline sur le "
        f"``field_name`` de la LISTE répond False — d'où le helper."
    )

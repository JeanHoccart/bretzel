"""Browser-based tools for probing a running Bretzel application."""

from __future__ import annotations

from bretzel.probe._probe import Net, Probe, ProbeFailedError, ScopeNotReadableError, probe
from bretzel.probe._window import Box, DropMissedError, ElementNotFoundError, Window

#: The harness's four refusals are PUBLIC, and for a reason: a probe
#: measuring an edge case sometimes wants to catch them — "this selector
#: must designate nothing", "this drop must fail". Leaving them in a
#: private module forced writing ``from bretzel.probe._window import …``,
#: that is to say depending on a path nothing promises. Added on
#: 2026-09-11, by the user's decision, after the drag gate had to do it.
__all__ = [
    "Box",
    "DropMissedError",
    "ElementNotFoundError",
    "Net",
    "Probe",
    "ProbeFailedError",
    "ScopeNotReadableError",
    "Window",
    "probe",
]

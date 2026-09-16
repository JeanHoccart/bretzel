"""Browser-based tools for probing a running Bretzel application."""

from __future__ import annotations

from bretzel.probe._probe import Net, Probe, ProbeFailedError, ScopeNotReadableError, probe
from bretzel.probe._window import Box, DropMissedError, ElementNotFoundError, Window

#: Les quatre refus du harnais sont PUBLICS, et pour une raison : un
#: probe qui mesure un cas limite veut parfois les attraper — « ce
#: sélecteur ne doit rien désigner », « ce dépôt doit rater ». Les
#: laisser dans un module privé obligeait à écrire
#: ``from bretzel.probe._window import …``, c'est-à-dire à dépendre d'un
#: chemin que rien ne promet. Ajoutées le 2026-09-11, sur décision de
#: l'utilisateur, après que la gate du glisser a dû le faire.
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

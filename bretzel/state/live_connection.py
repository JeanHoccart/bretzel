"""``LiveConnection`` — l'état de la liaison SSE, tenu par le runtime.

Même forme que ``ColorScheme`` : une app ne l'instancie jamais pour le
PILOTER — le runtime bascule ``connected`` sur les événements ``open`` /
``error`` de l'EventSource. Elle ne fait que le LIRE, pour afficher un
témoin en ligne / hors ligne ::

    from bretzel import LiveConnection

    ui.badge("LIVE",    color="success", visible=LiveConnection().connected)
    ui.badge("offline", color="muted",   visible=~LiveConnection().connected)

``connected`` part à ``False`` et passe à ``True`` dès que l'EventSource
paresseux du runtime — ouvert seulement quand une zone ``broadcast=[State]``
est sur la page — s'établit ; il retombe à ``False`` sur une coupure
passagère et remonte à la reconnexion. Rien à câbler côté serveur, le
runtime possède tout le cycle (``bretzel/runtime/_src/00_index.js``,
``ensureSse``).

"""

from __future__ import annotations

from bretzel.state import field
from bretzel.state.scopes.client import ClientState


class LiveConnection(ClientState, persist="memory"):
    """Expose the state of the framework's real-time connection."""

    connected: bool = field(default=False)

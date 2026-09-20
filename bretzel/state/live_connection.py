"""``LiveConnection`` — the state of the SSE link, held by the runtime.

Same shape as ``ColorScheme``: an app never instantiates it to DRIVE it —
the runtime flips ``connected`` on the EventSource's ``open`` / ``error``
events. The app only READS it, to show an online / offline indicator ::

    from bretzel import LiveConnection

    ui.badge("LIVE",    color="success", visible=LiveConnection().connected)
    ui.badge("offline", color="muted",   visible=~LiveConnection().connected)

``connected`` starts at ``False`` and turns ``True`` as soon as the
runtime's lazy EventSource — opened only when a ``broadcast=[State]`` zone
is on the page — is established; it drops back to ``False`` on a transient
cut and comes back up on reconnection. Nothing to wire server-side, the
runtime owns the whole cycle (``bretzel/runtime/_src/00_index.js``,
``ensureSse``).

"""

from __future__ import annotations

from bretzel.state import field
from bretzel.state.scopes.client import ClientState


class LiveConnection(ClientState, persist="memory"):
    """Expose the state of the framework's real-time connection."""

    connected: bool = field(default=False)

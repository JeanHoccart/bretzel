"""Runtime protocol version + compatibility check.

Bumped only when the wire format between server and client changes
incompatibly. Patch-level bumps (``v1.0`` → ``v1.1``) signal additive,
backwards-compatible additions ; major bumps (``v1.x`` → ``v2.x``)
signal a break.

The server checks the client's reported version on every action POST via
:func:`check_compat` — dans ``server/routing/actions.py``, juste avant la
vérification HMAC. Un major différent est refusé en **409** avec une
envelope ``_error: reload``, donc le bridge recharge et re-tire un
``runtime.js`` à jour.

⚠️ Ce contrôle sert la LISIBILITÉ, pas la sûreté : un header absent tombe
dans le chemin HMAC, qui vérifie l'authenticité de l'action.
"""

from __future__ import annotations

from bretzel.runtime.protocol import PROTOCOL_VERSION

__all__ = [
    "PROTOCOL_VERSION",
    "check_compat",
    "check_protocol_compat",
    "parse_major",
]


def parse_major(version: str) -> str:
    """Extract the major-version segment of a ``vN.M[.K]`` string.

    Tolerant of an optional leading ``v`` and minor ``.`` suffixes.
    Returns the segment up to (but not including) the first ``.`` —
    that's the granularity we gate compatibility on.
    """
    if not isinstance(version, str) or not version:
        raise ValueError(f"Expected a non-empty version string, got {version!r}.")
    return version.split(".", 1)[0]


def check_compat(client_version: str) -> bool:
    """Return ``True`` if the client's reported version is compatible.

    "Compatible" today means same major (``v1.x`` ↔ ``v1.y``). The
    function is tolerant of a missing client header (returns ``False`` —
    the caller decides whether to refuse or warn).
    """
    if not client_version:
        return False
    try:
        return parse_major(client_version) == parse_major(PROTOCOL_VERSION)
    except ValueError:
        return False


# Funnel canonical name (.claude/bretzel/runtime.md §version.py). Same check.
check_protocol_compat = check_compat

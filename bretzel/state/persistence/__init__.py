"""Storage backends and the ClientState field-materialisation helpers.

Internal aggregator — the user-facing API lives in
:mod:`bretzel.state` (:class:`MemoryBackend`, :class:`RedisBackend`,
:class:`Backend`). The V3 wire format itself lives in
:mod:`bretzel.runtime.envelope`.
"""

from bretzel.state.persistence.base import Backend
from bretzel.state.persistence.client_bridge import (
    full_field_dict,
    instance_key,
)
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.persistence.redis import BretzelError, RedisBackend

__all__ = [
    "Backend",
    "BretzelError",
    "MemoryBackend",
    "RedisBackend",
    "full_field_dict",
    "instance_key",
]

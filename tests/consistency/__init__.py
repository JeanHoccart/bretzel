"""Self-evolving consistency gates.

These tests discover their subjects by introspection — component classes
from the ``ui`` namespace, wire constants from ``protocol.py`` — rather
than from hardcoded lists. A new component or protocol constant is covered
automatically, so the gates keep catching *tomorrow's* drift without ever
being edited. Each replaces a class of discrepancy that used to be found
only by a manual code↔doc audit.
"""

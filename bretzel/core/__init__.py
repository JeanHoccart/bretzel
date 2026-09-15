"""Layer 0 — pure primitives, zero I/O.

Public API stable across the whole framework. Anything not re-exported
here is internal and may change without notice.

**Couche INTERNE — aucune surface utilisateur.**

Rien ici ne se tape dans le code d'une app : ce sont les noeuds
d'arbre, l'echappement et le tracker de dependances. ``__all__`` y est
donc le contrat INTER-COUCHE, pas une API publique, et la gate
``test_public_surface_is_classified`` ne balaie pas ce module.
Les deux exceptions se tapent ailleurs : ``BretzelError`` et
``AuthRequiredError`` sont canoniques ici mais publiques sur
``bretzel``.
"""

from bretzel.core.errors import BretzelError
from bretzel.core.escape import (
    escape_attr,
    escape_html,
    escape_js,
    serialize_attrs,
)
from bretzel.core.identity import IdGenerator, hash_segment
from bretzel.core.invoke import call_without_blocking
from bretzel.core.payload import EventPayload
from bretzel.core.serialize import VOID_ELEMENTS, serialize
from bretzel.core.tracking import (
    TRACKER,
    CircularDependencyError,
    DependencyTracker,
    Observer,
)
from bretzel.core.tree import Element, FragmentNode, HtmlNode, Node, TextNode

__all__ = [
    # tree
    "Node",
    "Element",
    "TextNode",
    "HtmlNode",
    "FragmentNode",
    # serialize
    "serialize",
    "VOID_ELEMENTS",
    # escape
    "escape_html",
    "escape_attr",
    "escape_js",
    "serialize_attrs",
    # identity
    "IdGenerator",
    "hash_segment",
    # payload
    "EventPayload",
    # errors
    "BretzelError",
    # tracking
    "DependencyTracker",
    "Observer",
    "TRACKER",
    "CircularDependencyError",
    # invoke
    "call_without_blocking",
]

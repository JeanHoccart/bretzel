"""INTERNAL layer — pure framework primitives with no user-facing API."""

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

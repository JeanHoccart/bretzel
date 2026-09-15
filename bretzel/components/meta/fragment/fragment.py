"""``Fragment`` — children grouping with no DOM wrapper.

The React ``<>...</>`` / Vue ``<template>`` / SwiftUI ``EmptyView``
equivalent — a container that holds children but emits NO surrounding
tag. The children inline directly into the parent's render output,
preserving the parent's layout invariants.

Usage ::

    def user_actions(user):
        with ui.fragment():
            ui.button("Edit", on_click=...)
            ui.button("Delete", on_click=...)

    with ui.hstack(gap="lg"):
        user_actions(user)       # buttons land flat in the hstack
        ui.button("Save")        # arrives as a sibling, not nested

Without Fragment, the same helper would force a wrapping container
(``with ui.flex():`` etc.) that changes the layout context for every
caller — Fragment lets composition stay layout-neutral.

The underlying machinery is :class:`bretzel.core.tree.Fragment` — a
``Node`` subclass the serializer already inlines (concatenates its
children without a surrounding tag). The Component layer here just
turns the existing tree primitive into a first-class authoring shape
accessible via the ``ui`` namespace.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.core.tree import FragmentNode


class Fragment(Component):
    """Wrap-less container — children render flat into the parent."""

    # No ``DEFAULT_TAG`` — render() returns a :class:`FragmentNode`,
    # not an :class:`Element`. The serializer sees the Fragment node
    # and concatenates its children without a wrapping tag.
    # nothing to bind. The whole point is to be invisible.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    #: « Je ne suis pas là », au sens du tri d'un parent. Un ``ui.tabs``
    #: qui cherche ses ``Tab`` doit me traverser. Contrairement à la
    #: section d'une zone ``@refreshable``, je n'ai aucune identité à
    #: rendre au nœud composé : ``_rewrap`` est donc l'identité.
    #: Cf. ``base/_wiring.unwrap_transparent``.
    IS_TRANSPARENT_WRAPPER: ClassVar[bool] = True

    @staticmethod
    def _rewrap(node: Any) -> Any:
        return node

    def __init__(self, **kwargs: Any) -> None:
        # Fragment accepts no kwargs ; any extras are a misuse (no
        # ``classes=``, no ``id=`` — there's no DOM element to attach
        # them to). Surface the misuse rather than swallowing.
        if kwargs:
            raise TypeError(
                f"Fragment takes no keyword arguments — "
                f"got : {sorted(kwargs)}. There's no wrapping element "
                f"to attach attributes to ; use ``ui.flex()`` / "
                f"``ui.hstack()`` if you need one."
            )
        super().__init__()

    def render(self) -> FragmentNode:  # type: ignore[override]
        """Return a :class:`FragmentNode` carrying the rendered children.

        The serializer inlines this node — its children appear in the
        parent's HTML output with NO surrounding tag.
        """
        return FragmentNode(children=self._render_children())


__all__ = ["Fragment"]

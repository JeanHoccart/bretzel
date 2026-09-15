"""Re-export :class:`VStack`, :class:`HStack`.

Both are tiny shortcuts on top of :class:`Flex` that bake a direction
in and offer a smaller kwargs surface for the common "list of items"
layouts. There is no bare ``Stack`` — pick ``VStack`` / ``HStack``
explicitly, or drop to ``Flex`` for a runtime-chosen direction.
"""

from bretzel.components.layout.stack.stack import HStack, VStack

__all__ = ["HStack", "VStack"]

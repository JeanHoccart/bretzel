"""Re-export the :class:`Code` component."""

from bretzel.components.primitives.code.code import Code, highlight_code
from bretzel.components.primitives.code.theme import CODE_THEME

__all__ = ["CODE_THEME", "Code", "highlight_code"]

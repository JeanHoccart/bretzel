"""The only real global: the theme.

The scale comes from the framework — controls at 30 px, median text at
14 px, the DEFAULT shipped since 2026-09-13. Three panels in a frozen
document — the density IS what makes the three-column view readable.

All that stays here is what the framework cannot decide: the hue.
"""

from bretzel.theme import Theme

THEME = Theme(semantic={"primary": "#4f46e5"})  # indigo

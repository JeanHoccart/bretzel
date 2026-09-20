"""The only real global: the theme.

The scale comes from the framework — controls at 30 px, median text at
14 px, the DEFAULT shipped since 2026-09-13. An instant messenger is a
dense list that scrolls.

All that stays here is what the framework cannot decide: the hue.
"""

from bretzel.theme import Theme

THEME = Theme(semantic={"primary": "#0ea5e9"})  # cyan

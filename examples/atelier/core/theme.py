"""The only visual global: the theme.

A tool's scale is the framework's since 2026-09-13, so this app has
nothing to ask for — and it is the one in the repository that needs it
most: one read per task means a table of phases, counters and replayed
commands.

All that stays here is the hue. A measuring instrument is neither a
success nor an error, hence neither green nor red — it is the VERDICTS
that get to add colour (a task in back-and-forth, a tool that failed).
"""

from bretzel.theme import Theme

THEME = Theme(semantic={"primary": "#b45309"})  # amber

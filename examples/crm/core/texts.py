"""The words the FRAMEWORK writes itself, where this app disagrees.

⚠️ **This table used to be fifty lines long, and its length was the
point.** The CRM was written in French, and the table answered "how much
English does Bretzel put on a French screen?" — a MEASUREMENT of a
framework gap, not configuration. The app now declares ``lang="en"``, so
every one of those lines said in English exactly what
``bretzel.render.texts.DEFAULT_TEXTS`` already says: an override that
overrides nothing demonstrates nothing, and it hides the one that does.

The gap has not gone away with the French: most of those lines were
generic ("Fermer", "Effacer", "Page précédente"), which the next French
app would retype identically. It stays filed in ``.claude/work/todo.md``.

What is left is what is really from HERE: the accounts are European, so
the charts count in euros where the framework's default hard-codes the
dollar.

The valid keys are in ``bretzel.render.texts.DEFAULT_TEXTS``; an unknown
key RAISES at startup.
"""

TEXTS: dict[str, str] = {
    "chart.currency": "{value} €",
}

"""core/i18n — the app's own words, in both languages.

The split is the one ``examples/docs`` states and the framework
enforces: **Bretzel translates ITS sentences** — the drag-and-drop
announcements, the file-upload limits, the pagination labels — and the
app translates ITS OWN. Bretzel does not know them and never will; what
it provides is the seam, :class:`~bretzel.Language`.

One function, and it is deliberately the whole surface:

    ui.button(tr("Create", "Créer"))

No catalogue, no key, no `.po`. The English is the source text and the
French sits beside it, so a sentence and its translation are never two
files apart — which is the only way they cannot drift. The cost is
real and accepted: a third language would make this shape untenable,
and that is the moment to reach for a real i18n library.

⚠️ :func:`tr` reads the request's language, so it needs a render
context. A module-level constant cannot call it — which is why the
board's column labels and the team's names are FUNCTIONS
(:func:`~examples.kanban.features.donnees.colonnes`) rather than tuples.
The key stays a stable identifier (``"a_faire"``); only the label
travels.
"""

from bretzel import Language


def tr(en: str, fr: str) -> str:
    """Return the copy for the language resolved for this request."""
    return fr if Language().code.startswith("fr") else en

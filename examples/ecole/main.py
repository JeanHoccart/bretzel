"""École — a physics-chemistry teacher's three notebooks, in one.

``py -m examples.ecole.main`` (port 8019).

**One single application**, and it is the specification's first decision
(``.claude/work/ecole-cahier-des-charges.md``, § 1.1). In the real world
these are two programs, two servers, two ports, and the second reads the
first's database read-only to know the classes and the timetable. That
seam exists only because there are two processes; here there is only one,
and the two "cross dependencies" become ordinary reads.

What the app stages — its mechanic, in one sentence: **a whole trade fits
in a single typed data model, and every screen is only a reading of that
model from an angle.** Three notebooks — the pupils, the calendar, the
lesson log — that the teacher today keeps by hand or in two separate
programs.

State of construction
----------------------
The specification cuts the work into ten batches, each delivered alone,
each consuming the previous one. **All ten batches are delivered**: the
complete data model (§ 5), the set seeded at real volumes (§ 13), the
shell, the home page, the year selector and the RT-1 barrier; the
settings screen — the year, its terms per cycle, its days without class
and what each makes you lose in lessons; and the week's grid, with its
deduced alternation, its blocks, its practicals, its exceptional hours
and its way back; and the classes — the photo grid, a pupil's sheet,
their particularities, their path, the four movements and the search by
first name or surname; and the marks — the assessments, the breakdown by
skill, bulk entry, the business refusals, the histogram and the export to
École Directe; and the comments — the observation tiles, writing under
400 characters, the rule of hand-written text, the class review and the
summary; and the seating plan — the room's outline, the aisles as
corridors, the drag arbitrated by the server, the class constraints,
automatic distribution, the versions and the freeze; and the follow-up —
the work to check, the two reminders computed on demand, and the
start-of-lesson frames; and the lesson log — the evening entry
pre-filled, the two copy buttons, picking up a sister class, the
progression table and the session sheets; and the imports and exports —
the two-step import, the photo replacement matched by name, and the
printable archives.

``main`` is the only file that knows the instance: it ``include``s the
features, seeds the database at startup, and lets the contract validate.
"""

from bretzel import Bretzel
from examples.ecole.core import db
from examples.ecole.core.db import init_db
from examples.ecole.core.texts import FR_TEXTS
from examples.ecole.core.theme import THEME
from examples.ecole.features import (
    accueil,
    annees,
    appreciations,
    appreciations_data,
    cahier,
    cahier_data,
    calendrier_data,
    classe,
    classes_data,
    eleve,
    eleves_data,
    emploi_du_temps,
    errors,
    evaluation,
    evaluations,
    grille_data,
    import_data,
    import_screen,
    notes_data,
    plan,
    plan_data,
    recherche,
    reglages,
    shell,
    suivi,
    suivi_data,
    vue_classe,
)

app = Bretzel(
    title="École · physique-chimie",
    secret_key="dev-ecole-secret-change-me",
    theme=THEME,
    # ``dev``: the teacher launches the app themselves and reopens it
    # often. The CSS is compiled IN the browser, so no Tailwind binary is
    # required for a first startup. The CRM is in ``prod`` to measure the
    # real speed; that is not what this app measures.
    mode="prod",
    # The language, declared once: it sets ``<html lang="fr">``, makes
    # the browser name the months and the days, and travels to the date
    # components — of which the app will be full from batch 2.
    lang="fr",
    texts=FR_TEXTS,
)


@app.startup
async def semer() -> None:
    # Idempotent: only re-seeds if the seed's version or the school year
    # has moved. ~1 s the first time, zero afterwards.
    init_db()


app.include(
    db,                 # infra  — le fichier SQLite et ses portes
    annees,             # logic  — the year looked at, the RT-1 barrier
    classes_data,       # data   — the class reads
    calendrier_data,    # data   — the year, its terms, its days
    grille_data,        # data   — the typical grid and its exceptions
    eleves_data,        # data   — the pupils and their enrolments
    notes_data,         # data   — assessments, marks, refusals
    appreciations_data,  # data  — the observation sheets
    plan_data,          # data   — rooms, seats, constraints
    suivi_data,         # data   — work to check, the reminders
    cahier_data,        # data   — the lesson log, the progression
    import_data,        # data   — the two-step import, the archive
    vue_classe,         # state  — what is looked at of a class
    suivi,              # logic  — frames, reminders, checks
    evaluations,        # logic  — a class's Évaluations tab
    shell,              # shell  — the frame
    emploi_du_temps,    # page   — the week's grid (the opening)
    accueil,            # page   — one tile per class
    classe,             # page   — a class and its pupils
    eleve,              # page   — a pupil's sheet
    evaluation,         # page   — entering a test's marks
    appreciations,      # page   — tiles, text, review, summary
    plan,               # page   — the seating plan, arbitrated drag
    cahier,             # page   — the evening entry, the sheets
    import_screen,      # page   — import a list, archive
    recherche,          # page   — search by surname or first name
    reglages,           # page   — year, terms, days without class
    errors,             # error
)


if __name__ == "__main__":
    app.run(port=8019, reload=True)

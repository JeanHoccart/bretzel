"""features/sessions — page : une fenêtre de travail, vue de haut.

L'écran des tâches répond « comment s'est passée celle-là ». Celui-ci
répond « est-ce que ça progresse », qui est l'autre moitié de la question
posée — et la seule qui demande d'avoir tout l'historique sous la main.
"""

from __future__ import annotations

from bretzel import Feature, page, ui
from examples.atelier.features.phases_page import (
    COLONNES_SESSION,
    lignes_session,
)
from examples.atelier.features.shell import shell


@page("/sessions", title="Sessions", layout=shell)
def sessions_page() -> None:
    """Toutes les sessions, la plus récente en tête."""
    lignes = lignes_session()

    with ui.vstack(gap="lg", classes="h-full min-h-0"):
        ui.heading("Les sessions", level=1)
        ui.text(
            "Une ligne par fenêtre de travail. La colonne qui compte est "
            "« cycles moyens » : c'est elle qui dit si la méthode tient "
            "dans le temps ou si elle se dégrade quand la tâche grossit.",
            color="muted",
        )

        if not lignes:
            ui.alert(
                "La base est vide. Lance "
                "`py -m examples.atelier.core.ingest` pour aspirer les "
                "transcripts.",
                color="info",
            )
            return

        ui.table(columns=COLONNES_SESSION, rows=lignes, row_key="id")


feature = Feature(
    name="sessions",
    kind="page",
    uses=["phases_page", "shell"],
    provides=[sessions_page],
)

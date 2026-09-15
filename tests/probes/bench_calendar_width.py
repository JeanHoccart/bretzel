"""Bench app pour le probe de largeur du calendrier (port 8979).

Un calendrier par (palier de taille x mois), dans la langue passee en
``BENCH_LANG``. Ce qu'on vient mesurer : la position de la fleche
« mois suivant » ne doit PAS dependre du mois affiche.

Pourquoi les mois choisis
--------------------------
Les extremes de longueur du libelle, dans les deux langues :
mai / May (le plus court) et septembre / September (le plus long).
Decembre est la pour un troisieme point, parce qu'un ecart mesure sur
deux valeurs peut etre une coincidence.

Tier-1 user code only. Run :  py tests/probes/bench_calendar_width.py
"""

from __future__ import annotations

import datetime as dt
import os

from bretzel import Bretzel, page, ui

LANG = os.environ.get("BENCH_LANG", "fr")

#: Les paliers, et les mois qui encadrent la longueur du libelle.
SIZES = ("xs", "sm", "md", "lg", "xl")
MONTHS = (5, 8, 9, 12)

app = Bretzel(
    secret_key="dev-calendar-width-bench-secret-key",
    title="Bretzel - calendar width bench",
    mode="dev",
    lang=LANG,
)


@page("/", title="Calendar width bench")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-6"):
        for size in SIZES:
            ui.text(f"size={size}", weight="semibold")
            with ui.hstack(gap="md", wrap=True):
                for month in MONTHS:
                    with ui.vstack(id=f"c-{size}-{month}"):
                        ui.calendar(value=dt.date(2026, month, 14), size=size)

        # Le mode ``month`` rend une grille d'ANNEE (3 x 4) et non des
        # jours : sa largeur naturelle n'a rien a voir avec 7 cellules,
        # donc une largeur figee par palier doit AUSSI lui aller.
        ui.text("mode=month", weight="semibold")
        with ui.hstack(gap="md", wrap=True):
            for size in SIZES:
                with ui.vstack(id=f"y-{size}"):
                    ui.calendar(value="2026-08", mode="month", size=size)


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8979))

"""Bench app pour le probe des marques de calendrier (port 8980).

Un calendrier marque par palier, plus un ``ui.date_picker`` — pour que le
probe verifie que la prop TRAVERSE bien l'enveloppe du picker et n'est pas
seulement branchee sur ``ui.calendar``.

Les marques couvrent trois cas qui comptent :
  - un jour ORDINAIRE marque ;
  - le jour SELECTIONNE marque (la pastille doit rester visible sur le
    fond d'accent, sinon elle disparait dedans) ;
  - un jour du mois PRECEDENT marque, visible dans le debord de la
    grille — il ne doit PAS etre pastille.

Et le mois suivant en porte aussi, pour que le probe verifie le chemin de
RE-RENDU : la grille est rebatie en JavaScript a chaque changement de
mois, donc une marque qui ne survivrait pas au clic serait invisible ici
sans ce troisieme point.

Tier-1 user code only. Run :  py tests/probes/bench_calendar_marks.py
"""

from __future__ import annotations

import datetime as dt

from bretzel import Bretzel, page, ui

SIZES = ("xs", "sm", "md", "lg", "xl")

#: Aout 2026 s'ouvre un samedi, donc la grille deborde sur juillet.
SELECTED = dt.date(2026, 8, 14)
PLAIN = dt.date(2026, 8, 3)
OUTSIDE = dt.date(2026, 7, 30)
NEXT_MONTH = dt.date(2026, 9, 9)

MARKS = {PLAIN: 1, SELECTED: 2, OUTSIDE: 3, NEXT_MONTH: 5}

app = Bretzel(
    secret_key="dev-calendar-marks-bench-secret-key",
    title="Bretzel - calendar marks bench",
    mode="dev",
    lang="fr",
    # La surcharge sert de preuve : si le nom accessible d'une case
    # marquee sort en anglais, c'est que le gabarit n'a pas voyage.
    texts={"calendar.marked": "{day}, {n} activites"},
)


@page("/", title="Calendar marks bench")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-6"):
        for size in SIZES:
            with ui.vstack(id=f"m-{size}"):
                ui.calendar(value=SELECTED, marks=MARKS, size=size)

        # Le meme calendrier SANS marques : c'est le temoin. Sans lui, on
        # ne peut pas dire si la pastille decale le numero du jour ou si
        # les cases ont toujours ete comme ca.
        with ui.vstack(id="temoin"):
            ui.calendar(value=SELECTED, size="md")

        with ui.vstack(id="picker"):
            ui.date_picker(value=SELECTED, marks=MARKS, size="md")


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8980))

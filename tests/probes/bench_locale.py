"""Bench app pour le probe de langue (port 8978).

DEUX apps dans un seul processus, montees sous des chemins differents ne
suffirait pas : ``lang`` est une config d'APP, donc il en faut deux. On
lance donc ce fichier avec ``BENCH_LANG=fr`` ou ``en`` et le probe le
demarre deux fois.

Ce qu'il expose, c'est la seule chose que le HTML ne peut pas prouver :
un ``ui.calendar`` SANS ``month_names=`` ni ``weekday_names=``, dont les
noms sont donc calcules par le navigateur depuis ``<html lang>``. Le
serveur n'emet AUCUN nom — c'est verifiable au HTML — mais que le
navigateur en mette les bons a la place ne se voit qu'au navigateur.

Le second calendrier, lui, passe des noms EXPLICITES : c'est
l'echappatoire tier 2, et elle doit gagner sur la langue.

Tier-1 user code only. Run :  py tests/probes/bench_locale.py
"""

from __future__ import annotations

import datetime as dt
import os

from bretzel import Bretzel, page, ui

LANG = os.environ.get("BENCH_LANG", "fr")

#: Des noms qui ne ressemblent a AUCUNE langue : si le probe les lit, il
#: sait que la liste explicite a gagne, et pas par coincidence.
MADE_UP_MONTHS = [f"M{i:02d}" for i in range(1, 13)]
MADE_UP_WEEKDAYS = [f"J{i}" for i in range(7)]

app = Bretzel(
    secret_key="dev-locale-bench-secret-key",
    title="Bretzel - locale bench",
    mode="dev",
    lang=LANG,
    texts=(
        {
            "alert.dismiss": "Fermer l'alerte",
            "calendar.month": "Mois",
            "chart.currency": "{value} EUR",
        }
        if LANG == "fr"
        else {}
    ),
)


#: Les titres du banc suivent ``BENCH_LANG`` eux aussi. Ils etaient
#: ecrits en francais en dur, quelle que soit la langue demandee : le
#: mode anglais rendait donc une page MIXTE, Chrome la detectait comme
#: anglaise, proposait de la traduire, et Google Translate massacrait
#: les abreviations de jours (WED -> « epouser », SAT -> « assis »,
#: SUN -> « soleil »). Un banc qui melange deux langues ne mesure pas ce
#: qu'il pretend mesurer — il fabrique le doute qu'il devait lever.
LABELS = {
    "fr": ("Sans liste : la langue decide", "Avec liste explicite : elle gagne"),
    "en": ("No list: the language decides", "Explicit list: it wins"),
}
AUTO_LABEL, EXPLICIT_LABEL = LABELS.get(LANG, LABELS["en"])


@page("/", title="Locale bench")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-6"):
        ui.text(AUTO_LABEL, weight="semibold")
        with ui.vstack(id="auto"):
            ui.calendar(value=dt.date(2025, 8, 14))

        ui.text(EXPLICIT_LABEL, weight="semibold")
        with ui.vstack(id="explicit"):
            ui.calendar(
                value=dt.date(2025, 8, 14),
                month_names=MADE_UP_MONTHS,
                weekday_names=MADE_UP_WEEKDAYS,
            )

        with ui.vstack(id="alert"):
            ui.alert("Message", dismissible=True)


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8978))

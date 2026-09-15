"""Bench : la langue resolue par requete (:8988).

Une app bilingue minimale — un mot du framework, un calendrier, deux
boutons de selection. Elle sert a mesurer les trois maillons de la
chaine dans un VRAI navigateur :

- l'en-tete ``Accept-Language`` decide a la premiere visite ;
- le calendrier suit, alors que RIEN n'est traduit cote serveur : ses
  noms de mois viennent d'``Intl`` dans le navigateur, a partir du
  ``<html lang>`` que le shell pose ;
- ``Language.set`` pose le cookie et fait recharger, et le cookie gagne
  ensuite sur l'en-tete.

Run :  py tests/probes/bench_lang.py
"""

from __future__ import annotations

from functools import partial

from bretzel import Bretzel, Language, page, ui

app = Bretzel(
    secret_key="dev-lang-bench-secret-key",
    title="Bretzel - lang bench",
    lang="en",
    languages=["en", "fr"],
    texts={"fr": {"alert.dismiss": "Fermer"}},
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-8"):
        ui.heading("Langue resolue par requete", level=2)
        with ui.hstack(gap="sm"):
            ui.button("English", on_click=partial(Language.set, "en"),
                      attrs={"data-probe": "to-en"})
            ui.button("Francais", on_click=partial(Language.set, "fr"),
                      attrs={"data-probe": "to-fr"})
        # Le mot du framework : il vient de ``texts=``, cote serveur.
        ui.alert("Message", dismissible=True, attrs={"data-probe": "alert"})
        # Le calendrier : ses mois viennent d'Intl, cote navigateur.
        ui.calendar(value=None, attrs={"data-probe": "cal"})


app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8988))

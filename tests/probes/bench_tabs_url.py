"""Bench pour la sonde « un onglet a une adresse » (port 8971).

La forme EXACTE du CRM (``features/contact_detail.py``) : une page routée
par un paramètre de chemin, trois onglets, des panneaux montés que
``bz-show`` bascule. C'est l'écran d'où la demande est partie —
``localhost:8016/contacts/5`` n'indiquait pas quel onglet était ouvert.

Deux blocs d'onglets sur la page, et ce n'est pas décoratif : le second
n'a **pas** d'``url=``. Il vérifie qu'un onglet sans adresse ne touche à
rien quand son voisin en pousse une — c'est l'opt-in qui se mesure.

Run :  py tests/probes/bench_tabs_url.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-tabs-url-bench-secret-key",
    title="Bretzel · Tabs URL bench",
    mode="dev",
)


@page("/contacts/{contact_id}")
def contact_detail(contact_id: int) -> None:
    with ui.vstack(gap="lg", classes="p-8"):
        ui.text(f"Contact #{contact_id}", size="2xl", weight="bold")

        # Le lien qui compte : on arrive sur cet écran par une navigation
        # PARTIELLE, jamais par un chargement dur. « Aucune suite ne
        # NAVIGUE » est le point aveugle documenté du dépôt.
        ui.link("aller au contact 6", href="/contacts/6", id="vers-6")

        with ui.tabs(value="identity", url="onglet", id="adresse"):
            ui.tab("identity", label="Identite", icon="id-card")
            ui.tab("activity", label="Activites", icon="history")
            ui.tab("documents", label="Documents", icon="paperclip")
            with ui.tab_panel(tab="identity"):
                ui.text("PANNEAU IDENTITE", id="p-identity")
            with ui.tab_panel(tab="activity"):
                ui.text("PANNEAU ACTIVITES", id="p-activity")
            with ui.tab_panel(tab="documents"):
                ui.text("PANNEAU DOCUMENTS", id="p-documents")

        ui.text("Sans url= — ne doit RIEN pousser", color="muted")
        with ui.tabs(value="un", id="muet"):
            ui.tab("un", label="Un")
            ui.tab("deux", label="Deux")
            with ui.tab_panel(tab="un"):
                ui.text("PANNEAU UN", id="p-un")
            with ui.tab_panel(tab="deux"):
                ui.text("PANNEAU DEUX", id="p-deux")


app.include(contact_detail)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8971))

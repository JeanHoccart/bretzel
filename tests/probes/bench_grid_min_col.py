"""Bench app pour le probe de ``ui.grid(min_col=…)`` (port 8985).

La rangee « Affichage » du CRM, telle quelle, sous les deux regimes.

⚠️ Les deux grilles vivent dans un conteneur de **1024 px**, et c'est le
coeur du banc : c'est la largeur de contenu reelle du CRM une fois la
barre laterale de 256 px et le padding de la coque deduits, sur une
fenetre de 1440. Un prefixe ``xl:`` lit le VIEWPORT — donc 1440 — pendant
que la grille n'a que 1024. Sans ce decalage, les deux regimes rendent la
meme chose et le banc ne prouve rien.

Tier-1 user code only. Run :  py tests/probes/bench_grid_min_col.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

app = Bretzel(
    secret_key="dev-grid-min-col-bench-secret-key",
    title="Bretzel - grid min_col bench",
    mode="dev",
)

DENSITES = [("sm", "Compacte"), ("md", "Normale"), ("lg", "Aérée")]
THEMES = [("light", "Clair"), ("dark", "Sombre"), ("system", "Système")]
LANDINGS = [("/", "Pipeline"), ("/comptes", "Comptes")]
PER_PAGE = [("25", "25 lignes"), ("50", "50 lignes")]


def quatre_champs() -> None:
    """Les quatre controles de la rangee « Affichage », dans l'ordre."""
    with ui.form_field(label="Thème", hint="Suivi du système par défaut."):
        ui.toggle_group(value="system", options=THEMES)
    with ui.form_field(label="Densité", hint="S'applique aux tableaux."):
        ui.toggle_group(value="md", options=DENSITES)
    with ui.form_field(label="Page d'accueil"):
        ui.select(value="/", options=LANDINGS)
    with ui.form_field(label="Lignes par page"):
        ui.select(value="25", options=PER_PAGE)


@page("/", title="Grid min_col bench")
def home() -> None:
    with ui.vstack(gap="lg", classes="p-6"):
        # ⚠️ **768 et non 1024 depuis le 2026-09-13.** Ce bloc est le
        # TÉMOIN : il doit déborder, sinon le reste du probe ne prouve
        # rien. Sa largeur était calibrée sur l'échelle d'alors — quatre
        # cellules de 256 px pour un groupe de champs plus large. Quand
        # l'échelle du framework est passée à 3 px le cran, le groupe a
        # maigri d'un quart et s'est mis à TENIR : le témoin annonçait
        # -26,2 px, c'est-à-dire qu'il ne témoignait plus.
        #
        # La leçon vaut au-delà d'ici : un témoin écrit en pixels absolus
        # est couplé à la densité du thème, et il cesse de témoigner en
        # SILENCE — le probe reste vert sur ses autres mesures.
        with ui.vstack(id="paliers", classes="w-[768px]"):
            with ui.grid(cols={"base": 1, "md": 2, "xl": 4}, gap="md"):
                quatre_champs()

        with ui.vstack(id="intrinseque", classes="w-[1024px]"):
            with ui.grid(min_col="16rem", gap="md"):
                quatre_champs()

        # Un conteneur ETROIT : les deux doivent finir par se replier,
        # et c'est le versant licite — ``min_col`` ne doit pas empecher
        # une colonne unique quand il n'y a la place que pour une.
        with ui.vstack(id="etroit", classes="w-[300px]"):
            with ui.grid(min_col="16rem", gap="md"):
                quatre_champs()


app.include(home)


if __name__ == "__main__":
    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    app.run(port=bench_port(8985))

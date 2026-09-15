"""Banc : un panneau ancré dans un conteneur ÉTROIT garde une largeur lisible.

Le bug, constaté sur `examples/crm` le 2026-08-29 : le sélecteur de
portefeuille vit dans la barre latérale, et quand elle se replie en
``rail`` (``w-16``) la gâchette ``w-full`` tombe à ~48 px. Le panneau,
lui, est épinglé à la largeur de la gâchette par ``match_width`` — en
``minWidth`` ET ``maxWidth`` — donc il rendait 48 px : les libellés
s'enroulaient lettre par lettre, avec une barre horizontale.

Trois cas, et c'est le TRIO qui prouve quelque chose :

- ``#rail-select`` — le cas réel, un ``ui.select`` dans une vraie
  sidebar repliée. C'est celui qui était cassé ;
- ``#box-select`` — le même dans une simple boîte ``w-16``. La classe
  du bug n'appartient pas à la sidebar : n'importe quel conteneur
  étroit la déclenche, et ce cas le dit sans dépendre d'un composant ;
- ``#wide-select`` — le TÉMOIN, dans ``w-96``. Au-dessus du plancher
  le comportement doit rester **identique au byte près** : c'est ce
  cas qui rougit si le correctif a débordé sur ce qu'il ne devait pas
  toucher.

Un quatrième, ``#hidden-select``, tient l'autre moitié de la décision :
le panneau est lisible mais la GÂCHETTE, elle, n'a pas de forme rail
(un carré de 31 px à chevron nu). `examples/crm` la fait donc
disparaître au repli, section comprise — ce banc monte la même
construction pour que ça se mesure ailleurs que dans l'app.

Son probe est :mod:`tests.probes.probe_anchored_floor`.

Lancer le banc (port 8989 — jamais le 8000, qui est à l'utilisateur) ::

    py -m tests.probes.bench_anchored_floor
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

PORT = 8989

#: Le ``h-screen`` du thème sidebar refuse tout montage contraint, et
#: ``h-full`` nu PERD (même spécificité) — il faut le ``!``.
FIT = {"root": "h-full!"}

#: Les libellés du CRM, à l'identique : c'est leur longueur qui rend le
#: panneau étroit illisible, une liste de « A »/« B » ne prouverait rien.
OPTIONS = [
    ("", "Tous les portefeuilles"),
    ("aicha", "Aïcha Benali"),
    ("marc", "Marc Dubois"),
    ("sofia", "Sofia Rossi"),
    ("lea", "Léa Martin"),
    ("tom", "Tom Nguyen"),
    ("chloe", "Chloé Weiss"),
]

app = Bretzel(
    secret_key="dev-anchored-floor-bench-secret-key",
    title="Bretzel · anchored panel floor bench",
    mode="dev",
)


@page("/")
def home() -> None:
    with ui.hstack(
        gap="none", align="stretch",
        classes="h-[560px] w-[980px] border border-text/20",
    ):
        with ui.sidebar(
            slots=FIT, collapsible="rail", open=False, id="probe-side",
        ):
            ui.sidebar_title("App", icon="zap")
            with ui.sidebar_section(label="PORTEFEUILLE"):
                with ui.vstack(gap="none", classes="px-2 pb-2"):
                    ui.select(OPTIONS, size="sm", id="rail-select")
            # La forme retenue par `examples/crm` : la GÂCHETTE n'a pas
            # de forme rail, donc la section entière disparaît au repli.
            # Sur la section et pas sur le champ — sinon le
            # `section_divider` (le trait qui remplace le titre dans le
            # rail) resterait, séparateur sans rien dessous.
            with ui.sidebar_section(
                label="CACHÉ AU REPLI",
                classes="group-data-[open=false]/sidebar:hidden",
            ):
                with ui.vstack(gap="none", classes="px-2 pb-2"):
                    ui.select(OPTIONS, size="sm", id="hidden-select")
        with ui.vstack(gap="xl", classes="flex-1 min-w-0 p-6"):
            # Hors de la sidebar : le probe scope ses mesures par id, et
            # ``check_sidebars_are_reachable`` refuse une sidebar repliée
            # sans moyen de revenir.
            ui.sidebar_trigger()

            ui.text("boîte w-16 (= la largeur du rail)", size="xs",
                    color="muted")
            with ui.vstack(gap="none", classes="w-16"):
                ui.select(OPTIONS, size="sm", id="box-select")

            ui.text("témoin w-96 — doit rester identique", size="xs",
                    color="muted")
            with ui.vstack(gap="none", classes="w-96"):
                ui.select(OPTIONS, size="sm", id="wide-select")


app.include(__name__)


if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(PORT))

"""Bench : la sidebar — montage contraint + la page de banc. (:8981)

Deux routes :

- ``/mount`` — peut-on monter une sidebar dans un conteneur contraint ?
  Le root de la sidebar est ``h-screen`` (100vh), ce qui l'empêche d'être
  benchée dans une carte : le footer ``mt-auto`` part à ~1000px, hors du
  cadre. L'ancien harnais visuel avait dû contourner ça en rendant la
  sidebar « bare » ; il a été supprimé le 2026-08-16, pas la contrainte.
  Trois formes comparées, parce que ``h-full`` et ``h-screen`` ont la MÊME
  spécificité : le vainqueur est le dernier de la feuille Tailwind, pas le
  dernier de l'attribut ``class``.

  Mesuré le 2026-08-15 : A (défaut) = 720px dans une boîte de 380, footer
  à y=649 (invisible) · B (``h-full`` nu) = 720px, PERD · C (``h-full!``)
  = 378px, footer visible à y=307.

- ``/`` — la page de banc réelle (``examples/playground/features/
  sidebar.py``) montée dans le shell du playground, pour la vérification
  visuelle sans occuper le port 8000 que l'utilisateur pilote.

Run :  py tests/probes/bench_sidebar_mount.py
"""

from __future__ import annotations

from bretzel import Bretzel, page, ui

import examples.playground.main  # noqa: F401, E402
from examples.playground.app.layout import shell
from examples.playground.features import sidebar as sidebar_feat

app = Bretzel(
    secret_key="dev-sidebar-mount-bench-secret-key",
    title="Bretzel · sidebar bench",
    mode="dev",
)


def demo(label: str, **kw) -> None:
    """Une sidebar complète (titre + section + items + footer) dans une
    boîte de 380px. Le footer est le témoin : s'il est visible, la
    sidebar tient dans la boîte."""
    ui.text(label, color="muted", classes="font-mono text-xs")
    with ui.hstack(
        gap="none", align="stretch",
        classes="h-[380px] w-full overflow-hidden border border-text/20 rounded-lg",
    ):
        with ui.sidebar(**kw):
            ui.sidebar_title("Bench", icon="zap")
            with ui.sidebar_section(label="OVERVIEW"):
                ui.sidebar_item("Home", icon="home", href="/none-1")
                ui.sidebar_item("App map", icon="network", href="/none-2")
            with ui.sidebar_footer(name="Jean Hoccart", subtitle="jean@acme.com"):
                ui.sidebar_footer_item(label="Settings", icon_left="settings")
        with ui.vstack(classes="flex-1 p-4"):
            ui.text("contenu", color="muted")


@page("/mount")
def mount() -> None:
    with ui.vstack(gap="xl", classes="p-8 bg-background"):
        ui.heading("Sidebar — montage en conteneur contraint", level=2)
        demo("A — défaut (h-screen dans le thème)")
        demo("B — slots={'root': 'h-full'}", slots={"root": "h-full"})
        demo("C — slots={'root': 'h-full!'}", slots={"root": "h-full!"})


# ``app.include(__name__)`` rake le namespace du MODULE : le résultat doit
# être lié à un nom top-level, sinon la page est marquée mais jamais vue.
#
# ⚠️ **Une lambda, et surtout PAS ``sidebar_feat.page`` directement.** La
# marque ``@page`` vit sur l'objet fonction : la remarquer ici écrasait
# celle que ``examples/playground/app/routes.py`` y a posée pour
# ``/sidebar``, donc importer ce banc rendait ``/sidebar`` introuvable
# dans le playground — et c'est ce qui faisait rougir la suite rapide
# sous ``-n 4``, selon le worker qui héritait de ce fichier. Le socle
# refuse désormais la double marque (``PageAlreadyMarkedError``) ; cette
# forme est celle qu'il indique.
bench_page = page("/", layout=shell)(lambda: sidebar_feat.page())

app.include(__name__)

if __name__ == "__main__":
    import uvicorn

    from tests.probes._serve import bench_port, use_local_tailwind

    # Le compilateur CSS depuis 127.0.0.1 et non depuis unpkg :

    # une suite ne doit pas dependre d'un tiers (cf. `_serve`).

    use_local_tailwind()


    uvicorn.run(app, host="127.0.0.1", port=bench_port(8981))

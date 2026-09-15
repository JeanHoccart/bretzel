"""SUJET — Les deux modèles de défilement.

Bretzel fait les DEUX, et c'est délibéré :

- **le document défile** — le modèle du web, celui d'un site. C'est le
  défaut : on n'écrit rien de particulier ;
- **le document est GELÉ**, et ce sont des régions qui défilent — le
  modèle d'un outil. Une barre latérale qui ne bouge pas, un en-tête
  toujours là, une liste qui défile seule.

Le dépôt faisait déjà les deux sans le dire — 8 apps contre 10 — et
``ui.viewport`` / ``ui.pane`` sont arrivés pour nommer le second.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/scrolling"


@page(PATH, layout=shell, title="Le défilement")
def scrolling_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Le défilement", level=1, size="3xl")
            ui.text(
                "Une page de site défile en entier. Un outil, non : sa "
                "barre latérale reste, son en-tête reste, et c'est la "
                "zone centrale qui bouge. Bretzel fait les deux, et le "
                "choix se pose une fois, à la coque.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Le défaut : le document défile", level=2)
                    ui.text(
                        "Rien à écrire. Une page grandit, le navigateur "
                        "fait défiler. C'est le modèle de la plupart des "
                        "sites, et celui de la majorité des exemples du "
                        "dépôt.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "@layout\n"
                        "def coque() -> None:\n"
                        "    with ui.vstack(gap=\"md\", classes=\"p-8\"):\n"
                        "        ui.heading(\"Mon app\")\n"
                        "        ui.outlet()\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("L'autre : le document est gelé", level=2)
                    ui.text(
                        "`ui.viewport` est un cadre plein écran, hors "
                        "flux : LUI ne défile pas. `ui.pane` est une "
                        "région qui prend la place restante et défile "
                        "toute seule. C'est exactement ce que fait la "
                        "coque de cette documentation.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "@layout\n"
                        "def coque() -> None:\n"
                        "    with ui.viewport():          # ne défile PAS\n"
                        "        with ui.sidebar(collapsible=\"rail\"):\n"
                        "            ...                  # reste en place\n"
                        "        with ui.pane(padding=\"lg\"):\n"
                        "            ui.outlet()          # défile, seule\n",
                        lang="python",
                    )
                    ui.text(
                        "`ui.viewport` est un `Flex` : il accepte "
                        "`direction`, `gap`, `align`, `justify`. Par "
                        "défaut ses enfants sont en ligne — barre "
                        "latérale à gauche, panneau à droite.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Lequel choisir", level=2)
                    ui.table(
                        columns=[
                            ui.column("si", label="Si"),
                            ui.column("alors", label="Alors"),
                        ],
                        rows=[
                            {"si": "une page de contenu qu'on lit de haut "
                                   "en bas",
                             "alors": "le défaut — le document défile"},
                            {"si": "une barre latérale ou un en-tête qui "
                                   "doivent rester visibles",
                             "alors": "`ui.viewport` + `ui.pane`"},
                            {"si": "deux listes côte à côte qui défilent "
                                   "indépendamment",
                             "alors": "`ui.viewport` + deux `ui.pane`"},
                            {"si": "on hésite",
                             "alors": "le défaut. Geler le document est "
                                      "un engagement : tout ce qui "
                                      "dépasse doit vivre dans une "
                                      "région"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que geler le document implique",
                               level=2)
                    ui.alert(
                        "Tout ce qui dépasse doit être DANS une région "
                        "qui défile. Un contenu posé directement dans le "
                        "`ui.viewport` est coupé, sans barre de "
                        "défilement pour le rattraper — le cadre ne "
                        "défile pas, c'est sa définition.",
                        color="warning", title="Le piège principal",
                    )
                    ui.alert(
                        "`document.body.scrollHeight` vaut 0 dans ce "
                        "modèle, et `window.scrollTo` ne fait rien : ce "
                        "n'est pas le document qui porte le défilement. "
                        "Un script — ou un test — qui veut faire défiler "
                        "doit viser la région. Mesuré en écrivant les "
                        "probes de cette doc, où l'instrument a d'abord "
                        "rendu 0 px de hauteur totale.",
                        color="info",
                        title="Ce qui surprend quand on scripte",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Cette page en est un exemple", level=2)
                    ui.text(
                        "La barre de gauche ne bouge pas quand ce texte "
                        "défile — c'est un `ui.viewport` avec une "
                        "`ui.sidebar` et un `ui.pane`. Le playground "
                        "aussi. Les apps de démonstration plus simples, "
                        "elles, laissent le document défiler.",
                        color="muted", size="sm",
                    )

"""SUJET — Le glisser-déposer.

Deux composants et un objet : on déclare la zone qui ACCEPTE, l'élément
qui SE SAISIT, et le handler reçoit d'où vient quoi et où ça va.

Ce que le chapitre insiste à dire, parce que c'est ce qui coûte quand on
l'ignore : ``accepts=`` et ``group=`` ne sont pas décoratifs. Sans eux,
toutes les zones acceptent tout, et une carte tombe dans une zone qui ne
sait pas quoi en faire.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/drag"


@page(PATH, layout=shell, title="Glisser-déposer")
def drag_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Glisser-déposer", level=1, size="3xl")
            ui.text(
                "Réordonner une liste, faire glisser une carte d'une "
                "colonne à l'autre. Le navigateur fait le geste, le "
                "serveur reçoit le résultat — et c'est lui qui décide "
                "s'il l'applique.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Les deux moitiés", level=2)
                    ui.text(
                        "`ui.dropzone` est la région qui accepte ; "
                        "`ui.draggable` enveloppe un élément qu'on peut "
                        "saisir. Les deux sont des CONTENEURS : on écrit "
                        "leur contenu dans un `with`.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "with ui.dropzone(name=\"a_faire\", accepts=[\"tache\"],\n"
                        "                 on_move=deplacer):\n"
                        "    for t in ui.each(taches, key=\"id\"):\n"
                        "        with ui.draggable(key=str(t.id), group=\"tache\"):\n"
                        "            ui.card(t.titre)\n",
                        lang="python",
                    )
                    ui.alert(
                        "`accepts=` et `group=` sont ce qui empêche une "
                        "carte de tomber dans une zone qui ne la "
                        "comprend pas. Sans eux, TOUTES les zones "
                        "acceptent TOUT — et le handler reçoit un "
                        "mouvement qu'il doit rejeter lui-même.",
                        color="warning", title="Les deux à ne pas oublier",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Ce que le handler reçoit", level=2)
                    ui.text(
                        "Un seul objet, `Move`, avec cinq champs. Il dit "
                        "tout ce qu'il faut pour appliquer OU refuser le "
                        "geste — et refuser est un cas normal.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("champ", label="Champ"),
                            ui.column("dit", label="Ce qu'il dit"),
                        ],
                        rows=[
                            {"champ": "item_key",
                             "dit": "la clé de l'élément déplacé — celle "
                                    "du `ui.draggable(key=…)`"},
                            {"champ": "from_zone",
                             "dit": "le `name=` de la zone de départ"},
                            {"champ": "to_zone",
                             "dit": "le `name=` de la zone d'arrivée"},
                            {"champ": "from_index",
                             "dit": "sa position d'origine dans la zone"},
                            {"champ": "to_index",
                             "dit": "la position visée à l'arrivée"},
                        ],
                        size="sm",
                    )
                    ui.code(
                        "from bretzel.components import Move\n"
                        "\n"
                        "def deplacer(mouvement: Move) -> None:\n"
                        "    \"\"\"Ce qu'un dépôt applique — ou refuse.\"\"\"\n"
                        "    if not mouvement.to_zone.startswith(\"colonne-\"):\n"
                        "        return                 # refusé, sans un mot\n"
                        "    tache_id = int(mouvement.item_key)\n"
                        "    deplacer_en_base(tache_id, mouvement.to_zone,\n"
                        "                     mouvement.to_index)\n",
                        lang="python",
                    )
                    ui.text(
                        "`item_key` est une CHAÎNE — c'est ce que le DOM "
                        "transporte. Une clé numérique se reconvertit à "
                        "l'arrivée, et un `int()` qui lève sur une valeur "
                        "inattendue vaut mieux qu'un déplacement au "
                        "hasard.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Verrouiller une zone", level=2)
                    ui.text(
                        "`locked=True` la rend inerte sans la retirer de "
                        "la page : elle reste visible, elle n'accepte "
                        "plus. C'est la forme à prendre pour un droit — "
                        "une grille qu'on ne peut plus modifier après "
                        "validation — plutôt que de ne pas rendre la "
                        "zone du tout.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "with ui.dropzone(name=\"places\", accepts=[\"eleve\"],\n"
                        "                 on_move=placer,\n"
                        "                 locked=not peut_modifier):\n"
                        "    ...\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("La poignée", level=2)
                    ui.text(
                        "`handle=True` sur le `ui.draggable` : l'élément "
                        "ne se saisit plus n'importe où, mais par une "
                        "zone dédiée. À prendre dès que la carte contient "
                        "elle-même des contrôles — sans ça, tirer sur un "
                        "bouton déplace la carte au lieu de cliquer.",
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Un cas réel, dans le dépôt", level=2)
                    ui.text(
                        "`examples/kanban` fait glisser des cartes entre "
                        "plan de classe : une zone par place, une zone de "
                        "réserve, et un handler qui refuse tout ce qui "
                        "n'est pas une place. C'est le portage d'une app "
                        "qui tourne pour de vrai, pas une démonstration.",
                        color="muted", size="sm",
                    )

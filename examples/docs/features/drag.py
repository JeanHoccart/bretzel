"""TOPIC — Drag and drop.

Two components and one object: one declares the zone that ACCEPTS, the
element that IS PICKED UP, and the handler receives what comes from
where and where it goes.

What the chapter insists on saying, because it is what costs when
ignored: ``accepts=`` and ``group=`` are not decorative. Without them,
every zone accepts everything, and a card falls into a zone that does not
know what to do with it.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/drag"


@page(PATH, layout=shell, title=tr('Drag and drop',
                                   'Glisser-déposer'))
def drag_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Drag and drop',
                          'Glisser-déposer'), level=1, size="3xl")
            ui.text(
                tr('Reordering a list, dragging a card from one column to '
                   'another. The browser makes the gesture, the server '
                   'receives the result — and it is the server that decides '
                   'whether to apply it.',
                   "Réordonner une liste, faire glisser une carte d'une "
                   "colonne à l'autre. Le navigateur fait le geste, le "
                   "serveur reçoit le résultat — et c'est lui qui décide s'il"
                   " l'applique."),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The two halves',
                                  'Les deux moitiés'), level=2)
                    ui.text(
                        tr('`ui.dropzone` is the region that accepts; '
                           '`ui.draggable` wraps an item one can grab. Both '
                           'are CONTAINERS: their content is written inside a'
                           ' `with`.',
                           '`ui.dropzone` est la région qui accepte ; '
                           "`ui.draggable` enveloppe un élément qu'on peut "
                           'saisir. Les deux sont des CONTENEURS : on écrit '
                           'leur contenu dans un `with`.'),
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
                        tr('`accepts=` and `group=` are what stop a card '
                           'falling into a zone that does not understand it. '
                           'Without them, EVERY zone accepts EVERYTHING — and'
                           ' the handler receives a move it has to reject '
                           'itself.',
                           '`accepts=` et `group=` sont ce qui empêche une '
                           'carte de tomber dans une zone qui ne la comprend '
                           'pas. Sans eux, TOUTES les zones acceptent TOUT — '
                           "et le handler reçoit un mouvement qu'il doit "
                           'rejeter lui-même.'),
                        color="warning", title=tr('The two not to forget',
                                                  'Les deux à ne pas oublier'),
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What the handler receives',
                                  'Ce que le handler reçoit'), level=2)
                    ui.text(
                        tr('A single object, `Move`, with five fields. It '
                           'says everything needed to apply OR refuse the '
                           'gesture — and refusing is a normal case.',
                           'Un seul objet, `Move`, avec cinq champs. Il dit '
                           "tout ce qu'il faut pour appliquer OU refuser le "
                           'geste — et refuser est un cas normal.'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("champ", label="Champ"),
                            ui.column("dit", label="Ce qu'il dit"),
                        ],
                        rows=[
                            {"champ": "item_key",
                             "dit": tr("the moved item's key — the "
                                       "`ui.draggable(key=…)`'s",
                                       "la clé de l'élément déplacé — celle "
                                       'du `ui.draggable(key=…)`')},
                            {"champ": "from_zone",
                             "dit": tr("the departure zone's `name=`",
                                       'le `name=` de la zone de départ')},
                            {"champ": "to_zone",
                             "dit": tr("the arrival zone's `name=`",
                                       "le `name=` de la zone d'arrivée")},
                            {"champ": "from_index",
                             "dit": tr('its original position in the zone',
                                       "sa position d'origine dans la zone")},
                            {"champ": "to_index",
                             "dit": tr('the position aimed at on arrival',
                                       "la position visée à l'arrivée")},
                        ],
                        size="sm",
                    )
                    ui.code(
                        tr('from bretzel.components import Move\n\ndef on_drop(move: Move) -> None:\n    """What a drop applies — or refuses."""\n    if not move.to_zone.startswith("column-"):\n        return                 # refused, without a word\n    task_id = int(move.item_key)\n    move_in_database(task_id, move.to_zone,\n                     move.to_index)\n',
                           'from bretzel.components import Move\n\ndef deplacer(mouvement: Move) -> None:\n    """Ce qu\'un dépôt applique — ou refuse."""\n    if not mouvement.to_zone.startswith("colonne-"):\n        return                 # refusé, sans un mot\n    tache_id = int(mouvement.item_key)\n    deplacer_en_base(tache_id, mouvement.to_zone,\n                     mouvement.to_index)\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('`item_key` is a STRING — that is what the DOM '
                           'carries. A numeric key converts back on arrival, '
                           'and an `int()` that raises on an unexpected value'
                           ' is better than a move made at random.',
                           "`item_key` est une CHAÎNE — c'est ce que le DOM "
                           'transporte. Une clé numérique se reconvertit à '
                           "l'arrivée, et un `int()` qui lève sur une valeur "
                           "inattendue vaut mieux qu'un déplacement au "
                           'hasard.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Locking a zone',
                                  'Verrouiller une zone'), level=2)
                    ui.text(
                        tr('`locked=True` makes it inert without removing it '
                           'from the page: it stays visible, it no longer '
                           'accepts. It is the shape to take for a permission'
                           ' — a grid that can no longer be changed after '
                           'approval — rather than not rendering the zone at '
                           'all.',
                           '`locked=True` la rend inerte sans la retirer de '
                           "la page : elle reste visible, elle n'accepte "
                           "plus. C'est la forme à prendre pour un droit — "
                           "une grille qu'on ne peut plus modifier après "
                           'validation — plutôt que de ne pas rendre la zone '
                           'du tout.'),
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
                    ui.heading(tr('The handle',
                                  'La poignée'), level=2)
                    ui.text(
                        tr('`handle=True` on the `ui.draggable`: the item is '
                           'no longer grabbed anywhere, but by a dedicated '
                           'area. To be taken as soon as the card itself '
                           'contains controls — without it, dragging on a '
                           'button moves the card instead of clicking.',
                           "`handle=True` sur le `ui.draggable` : l'élément "
                           "ne se saisit plus n'importe où, mais par une zone"
                           ' dédiée. À prendre dès que la carte contient '
                           'elle-même des contrôles — sans ça, tirer sur un '
                           'bouton déplace la carte au lieu de cliquer.'),
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('A real case, in the repository',
                                  'Un cas réel, dans le dépôt'), level=2)
                    ui.text(
                        tr('`examples/kanban` drags cards between columns: '
                           'one zone per column, a handler that refuses what '
                           'does not fit. It is the port of an app that '
                           'really runs, not a demonstration.',
                           '`examples/kanban` fait glisser des cartes entre '
                           'plan de classe : une zone par place, une zone de '
                           'réserve, et un handler qui refuse tout ce qui '
                           "n'est pas une place. C'est le portage d'une app "
                           'qui tourne pour de vrai, pas une démonstration.'),
                        color="muted", size="sm",
                    )

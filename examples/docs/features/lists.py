"""TOPIC — Lists and tables.

Two neighbouring capabilities, and it is the same need at two scales:
showing a collection that moves without re-rendering the whole page.

- ``ui.each`` / ``filter_each`` / ``paginate_each`` — the author writes
  the body, the framework sets the key and the client-side hiding;
- ``ui.datatable`` — the component owns the loop, because it sorts,
  filters, paginates and exports.

That difference is not a matter of taste: it is the base layer's
``COLLECTION_OWNER`` rule. **Whoever writes the ``for`` decides the API's
shape.** The author writes the loop → a ``with`` and children; the
component writes it → a ``render=``. Gated by
``test_collection_owner_decides_the_api``.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/lists"


@page(PATH, layout=shell, title="Listes et tableaux")
def lists_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Listes et tableaux", level=1, size="3xl")
            ui.text(
                tr('Displaying a moving collection, without re-rendering the '
                   'page. Two tools, and the choice between them hangs on one'
                   ' question: who writes the loop?',
                   'Afficher une collection qui bouge, sans re-rendre la '
                   'page. Deux outils, et le choix entre eux tient à une '
                   'seule question : qui écrit la boucle ?'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The question that settles it',
                                  'La question qui tranche'), level=2)
                    ui.text(
                        tr("It is the base layer's COLLECTION_OWNER rule, and"
                           ' it is gated. Whoever writes the `for` decides '
                           'the shape of the API — because the rendering '
                           'happens there.',
                           "C'est la règle COLLECTION_OWNER du socle, et elle"
                           ' est gatée. Qui écrit le `for` décide de la forme'
                           " de l'API — parce que le rendu se fait chez lui."),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column(tr('who',
                                         'qui'), label=tr('Who writes the loop',
                                                      'Qui écrit la boucle')),
                            ui.column("api", label=tr('The shape of the API',
                                                      "La forme de l'API")),
                            ui.column("ex", label="Exemple"),
                        ],
                        rows=[
                            {tr('who',
                                'qui'): "l'auteur",
                             "api": tr('a `with`, and the children inside',
                                       'un `with`, et les enfants dedans'),
                             "ex": "ui.each, filter_each, paginate_each"},
                            {tr('who',
                                'qui'): tr('the component',
                                       'le composant'),
                             "api": tr('a `render=` it calls per row',
                                       "un `render=` qu'il appelle par ligne"),
                             "ex": "ui.datatable, ui.select"},
                            {tr('who',
                                'qui'): tr('the client (JS)',
                                       'le client (JS)'),
                             "api": tr('neither one nor the other — the body '
                                       'is a template',
                                       "ni l'un ni l'autre — le corps est un "
                                       'gabarit'),
                             "ex": "ui.file_upload"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('ui.each — the key, and why it counts',
                                  'ui.each — la clé, et pourquoi elle compte'),
                               level=2)
                    ui.text(
                        tr('A bare `for` loop works… until an item carries '
                           'client state. On re-render, idiomorph pairs the '
                           'nodes by position: deleting the first shifts all '
                           'the others, and the open accordion changes row. '
                           '`ui.each` pushes a stable key per item, so the '
                           'pairing follows IDENTITY.',
                           "Une boucle `for` nue marche… jusqu'à ce qu'un "
                           'élément porte un état client. Au re-rendu, '
                           'idiomorph apparie les nœuds par position : '
                           'supprimer le premier décale tous les autres, et '
                           "l'accordéon ouvert change de ligne. `ui.each` "
                           'pousse une clé stable par élément, donc '
                           "l'appariement suit l'IDENTITÉ."),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('for task in ui.each(tasks, key="id"):\n    with ui.card():\n        ui.text(task.title)\n        ui.accordion(...)      # keeps its state\n\n# `key=` also accepts a callable:\nfor t in ui.each(tasks, key=lambda t: t.uuid):\n    ui.text(t.title)\n',
                           'for tache in ui.each(taches, key="id"):\n    with ui.card():\n        ui.text(tache.titre)\n        ui.accordion(...)      # garde son état\n\n# `key=` accepte aussi un callable :\nfor t in ui.each(taches, key=lambda t: t.uuid):\n    ui.text(t.titre)\n'),
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('filter_each — narrowing as you type',
                                  'filter_each — resserrer à la frappe'),
                               level=2)
                    ui.text(
                        tr('It sets a `bz-show` on every item, compared with '
                           'what is typed. The filtering is therefore '
                           'ENTIRELY client side: no round trip, and the '
                           'items are HIDDEN, not removed — the DOM count '
                           'does not move.',
                           'Il pose un `bz-show` sur chaque élément, comparé '
                           "à ce qu'on tape. Le filtre est donc ENTIÈREMENT "
                           'côté client : aucun aller-retour, et les éléments'
                           ' sont CACHÉS, pas retirés — le compte du DOM ne '
                           'bouge pas.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Filtre(ClientState):\n"
                        "    cherche: str = field(default=\"\")\n"
                        "\n"
                        "f = Filtre()\n"
                        "ui.input(value=f.cherche, placeholder=\"Filtrer…\")\n"
                        "\n"
                        "for fruit in ui.filter_each(\n"
                        "    FRUITS,\n"
                        "    query=f.cherche,\n"
                        "    text=lambda x: x,          # sur quoi on cherche\n"
                        "    key=lambda x: x,\n"
                        "    empty=lambda: ui.text(\"Rien ne correspond.\"),\n"
                        "):\n"
                        "    ui.text(fruit)\n",
                        lang="python",
                    )
                    ui.text(
                        tr('`empty=` is rendered too, and hidden as long as a'
                           ' row matches — otherwise it would take a round '
                           'trip to know there is nothing.',
                           '`empty=` est rendu lui aussi, et masqué tant '
                           "qu'une ligne correspond — sinon il faudrait un "
                           "aller-retour pour savoir qu'il n'y a rien."),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('paginate_each — a client-side window',
                                  'paginate_each — une fenêtre côté client'),
                               level=2)
                    ui.text(
                        tr('The same mechanics: everything is rendered, only '
                           'the current window is visible. `page` is a '
                           '1-indexed `ClientBinding` — so a `ui.pagination` '
                           'drives it with no network.',
                           'Même mécanique : tout est rendu, seule la fenêtre'
                           ' courante est visible. `page` est une '
                           '`ClientBinding` 1-indexée — donc un '
                           '`ui.pagination` la pilote sans réseau.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Vue(ClientState):\n"
                        "    page: int = field(default=1)\n"
                        "\n"
                        "v = Vue()\n"
                        "for ligne in ui.paginate_each(LIGNES, page=v.page,\n"
                        "                              per_page=20, key=\"id\"):\n"
                        "    ui.text(ligne.nom)\n"
                        "ui.pagination(value=v.page, total=len(LIGNES),\n"
                        "              per_page=20)\n",
                        lang="python",
                    )
                    ui.alert(
                        tr('Everything is rendered: it is instant, and it '
                           'only suits what fits in memory. Beyond a few '
                           'hundred rows, `ui.datatable` is what you need — '
                           'it paginates on the SERVER and renders only the '
                           'page asked for.',
                           "Tout est rendu : c'est instantané, et ça ne "
                           "convient qu'à ce qui tient en mémoire. Au-delà de"
                           " quelques centaines de lignes, c'est "
                           "`ui.datatable` qu'il faut — il pagine côté "
                           'SERVEUR et ne rend que la page demandée.'),
                        color="warning", title=tr('Where the limit is',
                                                  'Où est la limite'),
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('ui.datatable — the loop belongs to the '
                                  'component',
                                  'ui.datatable — la boucle appartient au '
                                  'composant'), level=2)
                    ui.text(
                        tr('It sorts, filters, paginates, searches and '
                           'exports. It is what decides which rows exist, so '
                           'the author cannot write the `for` — they describe'
                           ' their columns, and pass a `render=` for the ones'
                           ' that are not text.',
                           'Il trie, filtre, pagine, cherche et exporte. '
                           "C'est lui qui décide quelles lignes existent, "
                           "donc l'auteur ne peut pas écrire le `for` — il "
                           'décrit ses colonnes, et passe un `render=` pour '
                           'celles qui ne sont pas du texte.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('class AccountsTable(DatatableState, scope="session",\n                    addressable=True):\n    """One subclass PER table: the state is keyed by\n    class, so sharing the base would share the sort\n    and the page."""\n\nui.datatable(\n    state=AccountsTable,\n    columns=[\n        ui.column("name", label="Name", sortable=True),\n        ui.column("city", label="City", filter=True),\n        ui.column("status", label="Status",\n                  render=lambda v, row: ui.badge(v)),\n    ],\n    rows=load,             # a list, or a callable(Query)\n    exportable=True,\n    export_filename="accounts.csv",\n    row_key="id",\n)\n',
                           'class ComptesTable(DatatableState, scope="session",\n                   addressable=True):\n    """Une sous-classe PAR table : l\'état est clé\n    par classe, donc partager la base ferait\n    partager le tri et la page."""\n\nui.datatable(\n    state=ComptesTable,\n    columns=[\n        ui.column("nom", label="Nom", sortable=True),\n        ui.column("ville", label="Ville", filter=True),\n        ui.column("statut", label="Statut",\n                  render=lambda v, ligne: ui.badge(v)),\n    ],\n    rows=charger,          # list, ou callable(Query)\n    exportable=True,\n    export_filename="comptes.csv",\n    row_key="id",\n)\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('`addressable=True` gives the view an ADDRESS: '
                           'sorting, paginating or searching rewrites the '
                           'URL. The link shares, bookmarks, and the '
                           "browser's arrows go back and forth.",
                           '`addressable=True` donne une ADRESSE à la vue : '
                           "trier, paginer ou chercher réécrit l'URL. Le lien"
                           ' se partage, se met en favori, et les flèches du '
                           "navigateur font l'aller-retour."),
                        color="muted", size="sm",
                    )
                    ui.alert(
                        tr('`rows=` accepts a list OR a callable that '
                           'receives the `Query` (sort, page, search) and '
                           'returns `(rows, total)`. It is the shape to take '
                           'as soon as the source is a database: without it, '
                           'one loads everything to display twenty.',
                           '`rows=` accepte une liste OU un callable qui '
                           'reçoit la `Query` (tri, page, recherche) et rend '
                           "`(lignes, total)`. C'est la forme à prendre dès "
                           'que la source est une base : sans elle, on charge'
                           " tout pour n'en afficher que vingt."),
                        color="info", title=tr('The parameter that changes '
                                               'everything',
                                               'Le paramètre qui change tout'),
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text(tr('The exact signatures:',
                               'Les signatures exactes :'), color="muted",
                            size="sm")
                    ui.link("Catalogue ui.* →", href="/components")

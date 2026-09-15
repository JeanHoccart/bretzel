"""SUJET — Listes et tableaux.

Deux capacités voisines, et c'est le même besoin à deux échelles :
afficher une collection qui bouge sans re-rendre toute la page.

- ``ui.each`` / ``filter_each`` / ``paginate_each`` — l'auteur écrit le
  corps, le framework pose la clé et le masquage client ;
- ``ui.datatable`` — le composant possède la boucle, parce qu'il trie,
  filtre, pagine et exporte.

Cette différence n'est pas un détail de goût : c'est la règle
``COLLECTION_OWNER`` du socle. **Qui écrit le ``for`` décide de la forme
de l'API.** L'auteur écrit la boucle → un ``with`` et des enfants ; le
composant l'écrit → un ``render=``. Gaté par
``test_collection_owner_decides_the_api``.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/lists"


@page(PATH, layout=shell, title="Listes et tableaux")
def lists_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Listes et tableaux", level=1, size="3xl")
            ui.text(
                "Afficher une collection qui bouge, sans re-rendre la "
                "page. Deux outils, et le choix entre eux tient à une "
                "seule question : qui écrit la boucle ?",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("La question qui tranche", level=2)
                    ui.text(
                        "C'est la règle COLLECTION_OWNER du socle, et "
                        "elle est gatée. Qui écrit le `for` décide de la "
                        "forme de l'API — parce que le rendu se fait "
                        "chez lui.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("qui", label="Qui écrit la boucle"),
                            ui.column("api", label="La forme de l'API"),
                            ui.column("ex", label="Exemple"),
                        ],
                        rows=[
                            {"qui": "l'auteur",
                             "api": "un `with`, et les enfants dedans",
                             "ex": "ui.each, filter_each, paginate_each"},
                            {"qui": "le composant",
                             "api": "un `render=` qu'il appelle par ligne",
                             "ex": "ui.datatable, ui.select"},
                            {"qui": "le client (JS)",
                             "api": "ni l'un ni l'autre — le corps est un "
                                    "gabarit",
                             "ex": "ui.file_upload"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("ui.each — la clé, et pourquoi elle compte",
                               level=2)
                    ui.text(
                        "Une boucle `for` nue marche… jusqu'à ce qu'un "
                        "élément porte un état client. Au re-rendu, "
                        "idiomorph apparie les nœuds par position : "
                        "supprimer le premier décale tous les autres, et "
                        "l'accordéon ouvert change de ligne. `ui.each` "
                        "pousse une clé stable par élément, donc "
                        "l'appariement suit l'IDENTITÉ.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "for tache in ui.each(taches, key=\"id\"):\n"
                        "    with ui.card():\n"
                        "        ui.text(tache.titre)\n"
                        "        ui.accordion(...)      # garde son état\n"
                        "\n"
                        "# `key=` accepte aussi un callable :\n"
                        "for t in ui.each(taches, key=lambda t: t.uuid):\n"
                        "    ui.text(t.titre)\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("filter_each — resserrer à la frappe",
                               level=2)
                    ui.text(
                        "Il pose un `bz-show` sur chaque élément, comparé "
                        "à ce qu'on tape. Le filtre est donc ENTIÈREMENT "
                        "côté client : aucun aller-retour, et les "
                        "éléments sont CACHÉS, pas retirés — le compte du "
                        "DOM ne bouge pas.",
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
                        "`empty=` est rendu lui aussi, et masqué tant "
                        "qu'une ligne correspond — sinon il faudrait un "
                        "aller-retour pour savoir qu'il n'y a rien.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("paginate_each — une fenêtre côté client",
                               level=2)
                    ui.text(
                        "Même mécanique : tout est rendu, seule la "
                        "fenêtre courante est visible. `page` est une "
                        "`ClientBinding` 1-indexée — donc un "
                        "`ui.pagination` la pilote sans réseau.",
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
                        "Tout est rendu : c'est instantané, et ça ne "
                        "convient qu'à ce qui tient en mémoire. Au-delà "
                        "de quelques centaines de lignes, c'est "
                        "`ui.datatable` qu'il faut — il pagine côté "
                        "SERVEUR et ne rend que la page demandée.",
                        color="warning", title="Où est la limite",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("ui.datatable — la boucle appartient au "
                               "composant", level=2)
                    ui.text(
                        "Il trie, filtre, pagine, cherche et exporte. "
                        "C'est lui qui décide quelles lignes existent, "
                        "donc l'auteur ne peut pas écrire le `for` — il "
                        "décrit ses colonnes, et passe un `render=` pour "
                        "celles qui ne sont pas du texte.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class ComptesTable(DatatableState, scope=\"session\",\n"
                        "                   addressable=True):\n"
                        "    \"\"\"Une sous-classe PAR table : l'état est clé\n"
                        "    par classe, donc partager la base ferait\n"
                        "    partager le tri et la page.\"\"\"\n"
                        "\n"
                        "ui.datatable(\n"
                        "    state=ComptesTable,\n"
                        "    columns=[\n"
                        "        ui.column(\"nom\", label=\"Nom\", sortable=True),\n"
                        "        ui.column(\"ville\", label=\"Ville\", filter=True),\n"
                        "        ui.column(\"statut\", label=\"Statut\",\n"
                        "                  render=lambda v, ligne: ui.badge(v)),\n"
                        "    ],\n"
                        "    rows=charger,          # list, ou callable(Query)\n"
                        "    exportable=True,\n"
                        "    export_filename=\"comptes.csv\",\n"
                        "    row_key=\"id\",\n"
                        ")\n",
                        lang="python",
                    )
                    ui.text(
                        "`addressable=True` donne une ADRESSE à la vue : "
                        "trier, paginer ou chercher réécrit l'URL. Le "
                        "lien se partage, se met en favori, et les "
                        "flèches du navigateur font l'aller-retour.",
                        color="muted", size="sm",
                    )
                    ui.alert(
                        "`rows=` accepte une liste OU un callable qui "
                        "reçoit la `Query` (tri, page, recherche) et rend "
                        "`(lignes, total)`. C'est la forme à prendre dès "
                        "que la source est une base : sans elle, on "
                        "charge tout pour n'en afficher que vingt.",
                        color="info", title="Le paramètre qui change tout",
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text("Les signatures exactes :", color="muted",
                            size="sm")
                    ui.link("Catalogue ui.* →", href="/components")

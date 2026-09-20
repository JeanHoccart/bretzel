"""Foundations — Describing the UI.

Before any interactivity: how an interface is described. Python
components composed with `with`, a page, and rendering FROM a typed
state. The complete component catalogue lives in the Reference.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr


@page("/describe", layout=shell, title=tr('Describe the UI',
                                          "Décrire l'UI"))
def describe_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Describe the UI',
                          "Décrire l'UI"), level=1, size="3xl")
            ui.text(
                tr('Before making anything interactive, one has to know how '
                   'to describe an interface. In Bretzel, a UI is a tree of '
                   'Python components — static as long as no state moves.',
                   'Avant de rendre quoi que ce soit interactif, il faut '
                   'savoir décrire une interface. En Bretzel, une UI est un '
                   "arbre de composants Python — statique tant qu'aucun état "
                   'ne bouge.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Components composed with `with`',
                                  'Des composants composés avec `with`'), level=2)
                    ui.text(
                        tr('The `ui.*` components are functions. The '
                           'containers (stack, card, grid…) open with a '
                           '`with` block; their children are declared inside.',
                           'Les composants `ui.*` sont des fonctions. Les '
                           "conteneurs (stack, card, grid…) s'ouvrent avec un"
                           ' bloc `with` ; leurs enfants se déclarent dedans.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('with ui.card():\n    with ui.vstack(gap="sm"):\n        ui.heading("Profile", level=2)\n        ui.text("Member since 2024", color="muted")\n        ui.button("Edit")\n',
                           'with ui.card():\n    with ui.vstack(gap="sm"):\n        ui.heading("Profil", level=2)\n        ui.text("Membre depuis 2024", color="muted")\n        ui.button("Éditer")\n'),
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(tr('The complete list (inputs, overlays, '
                                   'tables, charts…) is in',
                                   'La liste complète (inputs, overlays, '
                                   'tables, charts…) est dans'), color="muted", size="sm")
                        ui.link(tr('the catalogue',
                                   'le catalogue'), href="/components")
                        ui.text(".", color="muted", size="sm")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('A page',
                                  'Une page'), level=2)
                    ui.text(
                        tr('A page is a function decorated with `@page` and '
                           'its URL. A `@layout` draws the common frame (a '
                           'sidebar, a header) and exposes a region through '
                           '`ui.outlet()` where the pages render.',
                           'Une page est une fonction décorée `@page` avec '
                           'son URL. Un `@layout` dessine le cadre commun '
                           '(une sidebar, un header) et expose une région via'
                           ' `ui.outlet()` où les pages se rendent.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "@page(\"/profil\", layout=shell)\n"
                        "def profil() -> None:\n"
                        "    ui.heading(\"Profil\", level=1)\n",
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Render from the state',
                                  "Rendre depuis l'état"), level=2)
                    ui.text(
                        tr('The key point: the UI is built BY READING the '
                           'state. One never modifies the display by hand — '
                           'one describes what it must be for the current '
                           'state. When the state changes, the UI is '
                           'recomputed (that is reactivity, further on). The '
                           'flow goes one way only: state → UI.',
                           "Le point clé : l'UI se construit EN LISANT "
                           "l'état. On ne modifie jamais l'affichage à la "
                           "main — on décrit ce qu'il doit être pour l'état "
                           "courant. Quand l'état change, l'UI est recalculée"
                           " (c'est la réactivité, plus loin). Le flux va "
                           'dans un seul sens : état → UI.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "def cart_summary() -> None:\n"
                        "    cart = Cart()\n"
                        "    ui.text(f\"{len(cart.items)} articles\")\n"
                        "    for item in cart.items:\n"
                        "        ui.text(item[\"name\"])\n",
                        lang="python",
                    )
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(tr('Where does that state come from? That is '
                                   'next:',
                                   "D'où vient cet état ? C'est la suite :"),
                                color="muted", size="sm")
                        ui.link(tr('Server state →',
                                   "L'état serveur →"), href="/state-server")

"""TOPIC — The two scrolling models.

Bretzel does BOTH, and it is deliberate:

- **the document scrolls** — the web's model, a site's. It is the
  default: one writes nothing in particular;
- **the document is FROZEN**, and regions scroll — a tool's model. A
  sidebar that does not move, a header always there, a list scrolling on
  its own.

The repository already did both without saying so — 8 apps against 10 —
and ``ui.viewport`` / ``ui.pane`` arrived to name the second.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/scrolling"


@page(PATH, layout=shell, title=tr('Scrolling',
                                   'Le défilement'))
def scrolling_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Scrolling',
                          'Le défilement'), level=1, size="3xl")
            ui.text(
                tr('A site page scrolls whole. A tool does not: its sidebar '
                   'stays, its header stays, and it is the central area that '
                   'moves. Bretzel does both, and the choice is made once, at'
                   ' the shell.',
                   'Une page de site défile en entier. Un outil, non : sa '
                   "barre latérale reste, son en-tête reste, et c'est la zone"
                   ' centrale qui bouge. Bretzel fait les deux, et le choix '
                   'se pose une fois, à la coque.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The default: the document scrolls',
                                  'Le défaut : le document défile'), level=2)
                    ui.text(
                        tr('Nothing to write. A page grows, the browser '
                           'scrolls. It is the model of most sites, and of '
                           "the majority of the repository's examples.",
                           'Rien à écrire. Une page grandit, le navigateur '
                           "fait défiler. C'est le modèle de la plupart des "
                           'sites, et celui de la majorité des exemples du '
                           'dépôt.'),
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
                    ui.heading(tr('The other: the document is frozen',
                                  "L'autre : le document est gelé"), level=2)
                    ui.text(
                        tr('`ui.viewport` is a full-screen frame, out of the '
                           'flow: IT does not scroll. `ui.pane` is a region '
                           'that takes the remaining space and scrolls on its'
                           " own. That is exactly what this documentation's "
                           'shell does.',
                           '`ui.viewport` est un cadre plein écran, hors flux'
                           ' : LUI ne défile pas. `ui.pane` est une région '
                           'qui prend la place restante et défile toute '
                           "seule. C'est exactement ce que fait la coque de "
                           'cette documentation.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('@layout\ndef shell() -> None:\n    with ui.viewport():          # does NOT scroll\n        with ui.sidebar(collapsible="rail"):\n            ...                  # stays in place\n        with ui.pane(padding="lg"):\n            ui.outlet()          # scrolls, on its own\n',
                           '@layout\ndef coque() -> None:\n    with ui.viewport():          # ne défile PAS\n        with ui.sidebar(collapsible="rail"):\n            ...                  # reste en place\n        with ui.pane(padding="lg"):\n            ui.outlet()          # défile, seule\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('`ui.viewport` is a `Flex`: it accepts '
                           '`direction`, `gap`, `align`, `justify`. By '
                           'default its children are in a row — sidebar on '
                           'the left, panel on the right.',
                           '`ui.viewport` est un `Flex` : il accepte '
                           '`direction`, `gap`, `align`, `justify`. Par '
                           'défaut ses enfants sont en ligne — barre latérale'
                           ' à gauche, panneau à droite.'),
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
                            {"si": tr('a content page one reads top to bottom',
                                      "une page de contenu qu'on lit de haut "
                                      'en bas'),
                             "alors": tr('the default — the document scrolls',
                                         'le défaut — le document défile')},
                            {"si": tr('a sidebar or a header that must stay '
                                      'visible',
                                      'une barre latérale ou un en-tête qui '
                                      'doivent rester visibles'),
                             "alors": "`ui.viewport` + `ui.pane`"},
                            {"si": tr('two lists side by side that scroll '
                                      'independently',
                                      'deux listes côte à côte qui défilent '
                                      'indépendamment'),
                             "alors": "`ui.viewport` + deux `ui.pane`"},
                            {"si": tr('one hesitates',
                                      'on hésite'),
                             "alors": tr('the default. Freezing the document '
                                         'is a commitment: everything that '
                                         'overflows must live in a region',
                                         'le défaut. Geler le document est un'
                                         ' engagement : tout ce qui dépasse '
                                         'doit vivre dans une région')},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What freezing the document implies',
                                  'Ce que geler le document implique'),
                               level=2)
                    ui.alert(
                        tr('Everything that overflows must be INSIDE a '
                           'scrolling region. Content placed directly in the '
                           '`ui.viewport` is cut off, with no scrollbar to '
                           'catch it — the frame does not scroll, that is its'
                           ' definition.',
                           'Tout ce qui dépasse doit être DANS une région qui'
                           ' défile. Un contenu posé directement dans le '
                           '`ui.viewport` est coupé, sans barre de défilement'
                           ' pour le rattraper — le cadre ne défile pas, '
                           "c'est sa définition."),
                        color="warning", title=tr('The main trap',
                                                  'Le piège principal'),
                    )
                    ui.alert(
                        tr('`document.body.scrollHeight` is 0 in this model, '
                           'and `window.scrollTo` does nothing: it is not the'
                           ' document that carries the scrolling. A script — '
                           'or a test — that wants to scroll must target the '
                           'region. Measured while writing this '
                           "documentation's probes, where the instrument "
                           'first returned 0 px of total height.',
                           '`document.body.scrollHeight` vaut 0 dans ce '
                           'modèle, et `window.scrollTo` ne fait rien : ce '
                           "n'est pas le document qui porte le défilement. Un"
                           ' script — ou un test — qui veut faire défiler '
                           'doit viser la région. Mesuré en écrivant les '
                           "probes de cette doc, où l'instrument a d'abord "
                           'rendu 0 px de hauteur totale.'),
                        color="info",
                        title=tr('What surprises you when scripting',
                                 'Ce qui surprend quand on scripte'),
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('This page is an example of it',
                                  'Cette page en est un exemple'), level=2)
                    ui.text(
                        tr('The left bar does not move when this text scrolls'
                           ' — it is a `ui.viewport` with a `ui.sidebar` and '
                           'a `ui.pane`. The playground too. The simpler '
                           'demonstration apps, for their part, let the '
                           'document scroll.',
                           'La barre de gauche ne bouge pas quand ce texte '
                           "défile — c'est un `ui.viewport` avec une "
                           '`ui.sidebar` et un `ui.pane`. Le playground '
                           'aussi. Les apps de démonstration plus simples, '
                           'elles, laissent le document défiler.'),
                        color="muted", size="sm",
                    )

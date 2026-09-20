"""ACTIONS — Client actions (no round trip).

The client side of actions: what runs in the browser, without touching
the server. `on_<event>=` accepts a client expression (a string); it is
rarely written by hand — methods generate it. Three ways, one single
mechanism. Imperative contract checked: imperative-api.md + dialog.py;
the string path: button.py (str → bz-on:click).
"""

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr


@page("/actions-client", layout=shell, title="Actions client")
def actions_client_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Actions client", level=1, size="3xl")
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    tr('For a purely visual interaction, one stays in the '
                       'browser — no round trip (cf.',
                       'Pour une interaction purement visuelle, on reste dans'
                       " le navigateur — pas d'aller-retour (cf."),
                    color="muted", size="lg",
                )
                ui.link("Comment Bretzel fonctionne", href="/how")
                ui.text(tr('). `on_<event>=` then accepts a client expression.',
                           '). `on_<event>=` accepte alors une expression '
                           'cliente.'),
                        color="muted", size="lg")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Three ways, a single mechanism',
                                  'Trois façons, un seul mécanisme'), level=2)
                    ui.text(
                        tr('All produce the same thing: an expression '
                           'evaluated client side, with no request. The first'
                           ' two write it for you; the third one is you.',
                           'Toutes produisent la même chose : une expression '
                           'évaluée côté client, sans requête. Les deux '
                           "premières te l'écrivent ; la troisième, c'est "
                           'toi.'),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("faux", label=tr('Way',
                                                       'Façon')),
                            ui.column("quand", label="Quand"),
                        ],
                        rows=[
                            {"faux": tr('1. Imperative methods (.open / '
                                        '.close / .toggle)',
                                        '1. Méthodes impératives (.open / '
                                        '.close / .toggle)'),
                             "quand": tr('driving a component, with no state '
                                         'to declare',
                                         'piloter un composant, sans état à '
                                         'déclarer')},
                            {"faux": tr('2. Binding methods (.set / .toggle /'
                                        ' .clear …)',
                                        '2. Méthodes de binding (.set / '
                                        '.toggle / .clear …)'),
                             "quand": tr('a client state that is readable / '
                                         'shareable / persistable',
                                         'un état client lisible / '
                                         'partageable / persistable')},
                            {"faux": tr('3. Raw string (on_click="…")',
                                        '3. Chaîne brute (on_click="…")'),
                             "quand": tr('the escape hatch: an expression by '
                                         'hand',
                                         'la porte de sortie : une expression'
                                         ' à la main')},
                        ],
                        size="sm",
                    )

            # ── 1. Imperative ────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('1. Imperative methods',
                                  '1. Méthodes impératives'), level=2)
                    ui.text(
                        tr('Write-only: they return the client string, to be '
                           'given to `on_click=`. Overlays: `.open()` '
                           '`.close()` `.toggle()`. Value-carrying fields: '
                           '`.set(v)` `.clear()`. Some components add '
                           'semantic aliases — for example '
                           '`.expand()/.collapse()` on the accordion.',
                           'Écriture-seule : elles rendent la chaîne cliente,'
                           ' à donner à `on_click=`. Overlays : `.open()` '
                           '`.close()` `.toggle()`. Champs à valeur : '
                           '`.set(v)` `.clear()`. Certains composants '
                           'ajoutent des alias sémantiques — par ex. '
                           "`.expand()/.collapse()` sur l'accordéon."),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('# container: with … as\nwith ui.dialog() as confirm:\n    ui.text("Delete this item?")\n    ui.button("OK", on_click=delete)\n\nui.button("Delete", on_click=confirm.open())\n\n# simple: direct assignment\naccept = ui.checkbox()\nui.button("Accept all", on_click=accept.set(True))\n',
                           '# conteneur : with … as\nwith ui.dialog() as confirm:\n    ui.text("Supprimer cet élément ?")\n    ui.button("OK", on_click=delete)\n\nui.button("Supprimer", on_click=confirm.open())\n\n# simple : affectation directe\naccept = ui.checkbox()\nui.button("Tout accepter", on_click=accept.set(True))\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('Ideal for repetitive overlays (one confirmation '
                           'dialog per row): the instance drives itself, with'
                           ' no state to declare. No reading (`.value`, '
                           '`.is_open`) — to read, go through a binding.',
                           'Idéal pour les overlays répétitifs (un dialog de '
                           "confirmation par ligne) : l'instance se pilote "
                           'elle-même, aucun état à déclarer. Pas de lecture '
                           '(`.value`, `.is_open`) — pour lire, passe par un '
                           'binding.'),
                        color="muted", size="sm",
                    )

            # ── 2. Binding ───────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('2. Binding methods',
                                  '2. Méthodes de binding'), level=2)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(
                            tr('When client state has to be readable, shared '
                               'or persistent, one declares it (a '
                               'ClientState) and drives it through its '
                               'binding. The methods are the same return '
                               'shapes. Detail in',
                               "Quand l'état client doit être lisible, "
                               'partagé ou persistant, on le déclare (un '
                               'ClientState) et on pilote via son binding. '
                               'Les méthodes sont les mêmes formes de retour.'
                               ' Détail dans'),
                            color="muted", size="sm",
                        )
                        ui.link(tr('Client state',
                                   'État client'), href="/state-client")
                        ui.text(".", color="muted", size="sm")
                    ui.code(
                        tr('class PanelUI(ClientState):\n    open: bool = False\n\npanel = PanelUI()\nui.button("Show", on_click=panel.open.toggle())\nwith ui.card(visible=panel.open):\n    ui.text("Zero round trips.")\n',
                           'class PanelUI(ClientState):\n    open: bool = False\n\npanel = PanelUI()\nui.button("Afficher", on_click=panel.open.toggle())\nwith ui.card(visible=panel.open):\n    ui.text("Zéro aller-retour.")\n'),
                        lang="python",
                    )

            # ── 3. Porte de sortie ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('3. Escape hatch — a raw string',
                                  '3. Porte de sortie — chaîne brute'), level=2)
                    ui.text(
                        tr('Passing a string to `on_<event>=` emits it as a '
                           'client expression evaluated in the browser (`bz-'
                           'on:click`). It is the escape hatch for the rare '
                           'case where no shorthand fits — to be kept, '
                           'precisely, for the rare cases.',
                           "Passer une chaîne à `on_<event>=` l'émet comme "
                           'une expression cliente évaluée dans le navigateur'
                           " (`bz-on:click`). C'est l'échappatoire pour le "
                           'cas rare où aucun raccourci ne convient — à '
                           'réserver, justement, aux cas rares.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        'ui.button("Remonter", on_click="window.scrollTo(0, 0)")\n',
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading(tr('To remember',
                                  'À retenir'), level=3)
                    ui.text(
                        tr('Client side = no round trip. A shorthand when one'
                           ' exists, a binding when the state has to be read,'
                           ' the string as a last resort. As soon as the '
                           'truth changes, one goes back to the server '
                           '(Handlers & actions).',
                           "Côté client = pas d'aller-retour. Un raccourci "
                           "quand il existe, un binding quand l'état doit "
                           'être lu, la chaîne en dernier recours. Dès que la'
                           ' vérité change, on repasse côté serveur (Handlers'
                           ' & actions).'),
                        color="muted", size="sm",
                    )

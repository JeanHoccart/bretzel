"""STATE — Client state.

The client side of state: it lives in the browser, mirrored by the
runtime, with no round trip. Useful for pure UI (filters, display
preferences) that does not need the server. `persist=` decides survival.
Modes checked in ``state/scopes/client.py``.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, field
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import emitted_html_block, state_mirror
from examples.docs.lib.i18n import tr

PATH = "/state-client"


class EchoClient(ClientState, persist="local"):
    """Browser state — mirrored by the runtime, zero round trips."""

    text: str = field(default='')


def echo_demo() -> None:
    echo = EchoClient()
    with ui.vstack(gap="sm"):
        ui.input(value=echo.text, placeholder="Tape ici…")
        with ui.hstack(align="center", gap="sm"):
            ui.text("Reflet live :", color="muted", size="sm")
            ui.text(echo.text, weight="bold", classes="font-mono")


@page(PATH, layout=shell, title=tr('Client state',
                                   'État client'))
def state_client_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Client state',
                          'État client'), level=1, size="3xl")
            ui.text(
                tr('A client state lives in the browser — the runtime '
                   'reflects it, without ever touching the server. It is the '
                   'right choice for pure UI: a panel open or closed, a '
                   'display filter, a local preference.',
                   'Un état client vit dans le navigateur — le runtime le '
                   "reflète, sans jamais toucher le serveur. C'est le bon "
                   "choix pour de l'UI pure : un panneau ouvert/fermé, un "
                   "filtre d'affichage, une préférence locale."),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Declaring, and persistence',
                                  'Déclarer, et la persistance'), level=2)
                    ui.text(
                        tr('One inherits from `ClientState`. `persist=` '
                           'decides one thing only: how long the value '
                           'survives.',
                           'On hérite de `ClientState`. `persist=` décide '
                           "d'une seule chose : combien de temps la valeur "
                           'survit.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class FilterUI(ClientState, persist=\"local\"):\n"
                        "    sort_by: str = \"date\"\n",
                        lang="python",
                    )
                    ui.table(
                        columns=[
                            ui.column("persist", label="persist="),
                            ui.column("survie", label="Survie"),
                            ui.column(tr('for',
                                         'pour'), label=tr('What for',
                                                       'Pour quoi')),
                        ],
                        rows=[
                            {"persist": tr('"memory" (default)',
                                           '"memory" (défaut)'),
                             "survie": tr('throwaway — lost on reload (F5) '
                                          'and on close',
                                          'jetable — perdue au reload (F5) et'
                                          ' à la fermeture'),
                             tr('for',
                                'pour'): tr('a UI flag (menu open)',
                                        "un flag d'UI (menu ouvert)")},
                            {"persist": "\"session\"",
                             "survie": tr('survives a reload, lost on close',
                                          'survit au reload, perdue à la '
                                          'fermeture'),
                             tr('for',
                                'pour'): tr('a filter, a wizard step',
                                        'un filtre, une étape de wizard')},
                            {"persist": "\"local\"",
                             "survie": tr('survives everything',
                                          'survit à tout'),
                             tr('for',
                                'pour'): tr('a real preference (theme, sort)',
                                        'une vraie préférence (thème, tri)')},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Demo — the client mirror, zero round trips',
                                  'Démo — le miroir client, zéro aller-retour'),
                               level=2)
                    ui.text(
                        tr('The input writes into a ClientState; the text '
                           'below reflects it through `bz-text`. No network —'
                           ' the runtime swaps the text on every keystroke.',
                           "L'input écrit dans un ClientState ; le texte en "
                           'dessous le reflète via `bz-text`. Aucun réseau — '
                           'le runtime swappe le texte à chaque frappe.'),
                        color="muted", size="sm",
                    )
                    echo_demo()
                    emitted_html_block(
                        tr('The `<span bz-text>` bound to '
                           '$bz.state.EchoClient.default.text',
                           'Le `<span bz-text>` bound à '
                           '$bz.state.EchoClient.default.text'),
                        serialize_html(
                            ui.text(EchoClient().text, weight="bold",
                                    classes="font-mono")
                        ),
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Summary',
                                  'Récapitulatif'), level=2)
                    with ui.card():
                        state_mirror(EchoClient)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(tr('Driving that state from an event:',
                                   'Piloter cet état depuis un événement :'),
                                color="muted", size="sm")
                        ui.link("Actions client →", href="/actions-client")
                        ui.text(tr('· the live reflection in detail:',
                                   '· le reflet live en détail :'),
                                color="muted", size="sm")
                        ui.link(tr('Client reactivity →',
                                   'Réactivité client →'), href="/reactivity-client")

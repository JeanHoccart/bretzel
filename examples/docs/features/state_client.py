"""L'ÉTAT — État client.

Le côté client de l'état : il vit dans le navigateur, reflété par le
runtime, sans aller-retour. Utile pour de l'UI pure (filtres, préférences
d'affichage) qui n'a pas besoin du serveur. `persist=` décide de la survie.
Modes vérifiés dans ``state/scopes/client.py``.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.render import serialize_html
from bretzel.state import ClientState, field
from examples.docs.features.shell import shell
from examples.docs.lib.blocks import emitted_html_block, state_mirror

PATH = "/state-client"


class EchoClient(ClientState, persist="local"):
    """État navigateur — reflété par le runtime, zéro aller-retour."""

    text: str = field(default='')


def echo_demo() -> None:
    echo = EchoClient()
    with ui.vstack(gap="sm"):
        ui.input(value=echo.text, placeholder="Tape ici…")
        with ui.hstack(align="center", gap="sm"):
            ui.text("Reflet live :", color="muted", size="sm")
            ui.text(echo.text, weight="bold", classes="font-mono")


@page(PATH, layout=shell, title="État client")
def state_client_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("État client", level=1, size="3xl")
            ui.text(
                "Un état client vit dans le navigateur — le runtime le "
                "reflète, sans jamais toucher le serveur. C'est le bon choix "
                "pour de l'UI pure : un panneau ouvert/fermé, un filtre "
                "d'affichage, une préférence locale.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Déclarer, et la persistance", level=2)
                    ui.text(
                        "On hérite de `ClientState`. `persist=` décide d'une "
                        "seule chose : combien de temps la valeur survit.",
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
                            ui.column("pour", label="Pour quoi"),
                        ],
                        rows=[
                            {"persist": "\"memory\" (défaut)",
                             "survie": "jetable — perdue au reload (F5) et à "
                                       "la fermeture",
                             "pour": "un flag d'UI (menu ouvert)"},
                            {"persist": "\"session\"",
                             "survie": "survit au reload, perdue à la fermeture",
                             "pour": "un filtre, une étape de wizard"},
                            {"persist": "\"local\"",
                             "survie": "survit à tout",
                             "pour": "une vraie préférence (thème, tri)"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Démo — le miroir client, zéro aller-retour",
                               level=2)
                    ui.text(
                        "L'input écrit dans un ClientState ; le texte en "
                        "dessous le reflète via `bz-text`. Aucun réseau — le "
                        "runtime swappe le texte à chaque frappe.",
                        color="muted", size="sm",
                    )
                    echo_demo()
                    emitted_html_block(
                        "Le `<span bz-text>` bound à "
                        "$bz.state.EchoClient.default.text",
                        serialize_html(
                            ui.text(EchoClient().text, weight="bold",
                                    classes="font-mono")
                        ),
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Récapitulatif", level=2)
                    with ui.card():
                        state_mirror(EchoClient)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text("Piloter cet état depuis un événement :",
                                color="muted", size="sm")
                        ui.link("Actions client →", href="/actions-client")
                        ui.text("· le reflet live en détail :",
                                color="muted", size="sm")
                        ui.link("Réactivité client →", href="/reactivity-client")

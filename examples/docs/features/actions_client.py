"""LES ACTIONS — Actions client (sans aller-retour).

Le côté client des actions : ce qui s'exécute dans le navigateur, sans
toucher le serveur. `on_<event>=` accepte une expression cliente (une
chaîne) ; on l'écrit rarement à la main — des méthodes la génèrent.
Trois façons, un seul mécanisme. Contrat impératif vérifié :
imperative-api.md + dialog.py ; le chemin chaîne : button.py
(str → bz-on:click).
"""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/actions-client", layout=shell, title="Actions client")
def actions_client_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Actions client", level=1, size="3xl")
            with ui.hstack(align="baseline", gap="sm", wrap=True):
                ui.text(
                    "Pour une interaction purement visuelle, on reste dans le "
                    "navigateur — pas d'aller-retour (cf.",
                    color="muted", size="lg",
                )
                ui.link("Comment Bretzel fonctionne", href="/how")
                ui.text("). `on_<event>=` accepte alors une expression cliente.",
                        color="muted", size="lg")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Trois façons, un seul mécanisme", level=2)
                    ui.text(
                        "Toutes produisent la même chose : une expression "
                        "évaluée côté client, sans requête. Les deux premières "
                        "te l'écrivent ; la troisième, c'est toi.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("faux", label="Façon"),
                            ui.column("quand", label="Quand"),
                        ],
                        rows=[
                            {"faux": "1. Méthodes impératives (.open / .close "
                                     "/ .toggle)",
                             "quand": "piloter un composant, sans état à "
                                      "déclarer"},
                            {"faux": "2. Méthodes de binding (.set / .toggle "
                                     "/ .clear …)",
                             "quand": "un état client lisible / partageable / "
                                      "persistable"},
                            {"faux": "3. Chaîne brute (on_click=\"…\")",
                             "quand": "la porte de sortie : une expression à "
                                      "la main"},
                        ],
                        size="sm",
                    )

            # ── 1. Impératif ─────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("1. Méthodes impératives", level=2)
                    ui.text(
                        "Écriture-seule : elles rendent la chaîne cliente, à "
                        "donner à `on_click=`. Overlays : `.open()` `.close()` "
                        "`.toggle()`. Champs à valeur : `.set(v)` `.clear()`. "
                        "Certains composants ajoutent des alias sémantiques — "
                        "par ex. `.expand()/.collapse()` sur l'accordéon.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# conteneur : with … as\n"
                        "with ui.dialog() as confirm:\n"
                        '    ui.text("Supprimer cet élément ?")\n'
                        '    ui.button("OK", on_click=delete)\n'
                        "\n"
                        'ui.button("Supprimer", on_click=confirm.open())\n'
                        "\n"
                        "# simple : affectation directe\n"
                        "accept = ui.checkbox()\n"
                        'ui.button("Tout accepter", on_click=accept.set(True))\n',
                        lang="python",
                    )
                    ui.text(
                        "Idéal pour les overlays répétitifs (un dialog de "
                        "confirmation par ligne) : l'instance se pilote "
                        "elle-même, aucun état à déclarer. Pas de lecture "
                        "(`.value`, `.is_open`) — pour lire, passe par un "
                        "binding.",
                        color="muted", size="sm",
                    )

            # ── 2. Binding ───────────────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("2. Méthodes de binding", level=2)
                    with ui.hstack(align="baseline", gap="sm", wrap=True):
                        ui.text(
                            "Quand l'état client doit être lisible, partagé ou "
                            "persistant, on le déclare (un ClientState) et on "
                            "pilote via son binding. Les méthodes sont les "
                            "mêmes formes de retour. Détail dans",
                            color="muted", size="sm",
                        )
                        ui.link("État client", href="/state-client")
                        ui.text(".", color="muted", size="sm")
                    ui.code(
                        "class PanelUI(ClientState):\n"
                        "    open: bool = False\n"
                        "\n"
                        "panel = PanelUI()\n"
                        'ui.button("Afficher", on_click=panel.open.toggle())\n'
                        "with ui.card(visible=panel.open):\n"
                        '    ui.text("Zéro aller-retour.")\n',
                        lang="python",
                    )

            # ── 3. Porte de sortie ───────────────────────────────────
            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("3. Porte de sortie — chaîne brute", level=2)
                    ui.text(
                        "Passer une chaîne à `on_<event>=` l'émet comme une "
                        "expression cliente évaluée dans le navigateur "
                        "(`bz-on:click`). C'est l'échappatoire pour le cas rare "
                        "où aucun raccourci ne convient — à réserver, justement, "
                        "aux cas rares.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        'ui.button("Remonter", on_click="window.scrollTo(0, 0)")\n',
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="xs"):
                    ui.heading("À retenir", level=3)
                    ui.text(
                        "Côté client = pas d'aller-retour. Un raccourci quand "
                        "il existe, un binding quand l'état doit être lu, la "
                        "chaîne en dernier recours. Dès que la vérité change, "
                        "on repasse côté serveur (Handlers & actions).",
                        color="muted", size="sm",
                    )

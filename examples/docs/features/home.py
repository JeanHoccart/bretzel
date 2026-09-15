"""Aperçu — Le pitch. La page d'accueil de la doc, à la racine.

Pourquoi Bretzel, la seule idée à retenir (UI = f(state)), et par où
commencer. Zéro signature ici — le détail vient après.
"""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/", layout=shell, title="Le pitch")
def home_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Bretzel", level=1, size="4xl")
            ui.text(
                "Construis des interfaces web en Python. Tu écris des "
                "composants et un état typés côté serveur ; le navigateur "
                "les affiche et les tient à jour — sans JavaScript ni build "
                "front à maintenir.",
                color="muted", size="lg",
            )

            with ui.card(color="primary"):
                with ui.vstack(gap="xs"):
                    ui.heading("La seule idée à retenir", level=2)
                    ui.text(
                        "UI = f(state). Le serveur détient la vérité ; tu "
                        "mutes un état typé, l'interface suit. Pas de "
                        "synchronisation client / serveur à écrire à la main.",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("À quoi ça ressemble", level=2)
                    ui.text(
                        "Un état, un handler, une page. La valeur pilote "
                        "l'affichage ; le clic mute l'état.",
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Counter(SessionState):\n"
                        "    n: int = 0\n"
                        "\n"
                        "def increment() -> None:\n"
                        "    Counter().n += 1\n"
                        "\n"
                        "@refreshable(deps=[Counter])\n"
                        "def display() -> None:\n"
                        "    ui.heading(str(Counter().n))\n"
                        "\n"
                        "@page(\"/\")\n"
                        "def home() -> None:\n"
                        "    display()\n"
                        "    ui.button(\"+1\", on_click=increment)\n",
                        lang="python",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading("Comment lire cette doc", level=2)
                    ui.text(
                        "La barre de gauche suit l'ordre où l'on en a "
                        "besoin. DÉMARRER se lit d'un trait, une fois. LE "
                        "CYCLE est le cœur : l'état, les actions, la "
                        "réactivité — chacun avec son côté serveur et son "
                        "côté client, parce que c'est la forme même du "
                        "framework. CONSTRUIRE et LES SUJETS s'ouvrent "
                        "quand on a le problème sous la main. CHERCHER ne "
                        "s'apprend pas : ce sont des index lus en direct "
                        "dans le code.",
                        color="muted", size="sm",
                    )
                    ui.link("Commencer : comment Bretzel fonctionne →",
                            href="/how")

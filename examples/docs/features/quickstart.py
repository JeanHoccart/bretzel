"""Le premier trajet complet : de zéro à une page Bretzel modifiée."""

from bretzel import page, ui

from examples.docs.features.shell import shell

PATH = "/quickstart"


@page(PATH, layout=shell, title="Démarrer en 5 minutes")
def quickstart_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="xl"):
            with ui.vstack(gap="sm", classes="max-w-4xl"):
                with ui.hstack(align="center", gap="sm", wrap=True):
                    ui.badge("Quickstart", color="primary", variant="soft")
                    ui.badge("5 minutes", color="muted", variant="outline")
                ui.heading("Votre première application Bretzel", level=1, size="4xl")
                ui.text(
                    "Créez le projet, lancez le serveur puis modifiez une page. "
                    "À la fin, vous aurez parcouru la boucle essentielle : "
                    "décrire l’interface en Python et voir le navigateur suivre.",
                    color="muted", size="lg",
                )

            with ui.card(color="warning"):
                with ui.vstack(gap="sm"):
                    ui.heading("Avant la première version PyPI", level=2, size="lg")
                    ui.text(
                        "Bretzel est encore en early alpha. Pour l’essayer aujourd’hui, "
                        "installez le dépôt GitHub. Après la première publication, cette "
                        "commande deviendra simplement `pip install bretzel`.",
                        size="sm",
                    )
                    ui.code(
                        'python -m pip install "bretzel @ '
                        'git+https://github.com/JeanHoccart/bretzel.git"',
                        lang="bash",
                    )

            with ui.grid(cols=2, gap="lg", classes="max-lg:grid-cols-1"):
                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("1", color="primary")
                        ui.heading("Créer le projet", level=2)
                        ui.code(
                            "bretzel new hello-bretzel\n"
                            "cd hello-bretzel\n"
                            "python -m venv .venv",
                            lang="bash",
                        )
                        ui.text(
                            "`bretzel new` crée une application minimale dans un "
                            "nouveau dossier. Il refuse d’écraser un dossier existant.",
                            color="muted", size="sm",
                        )

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("2", color="primary")
                        ui.heading("Activer l’environnement", level=2)
                        ui.text("Windows PowerShell", weight="semibold", size="sm")
                        ui.code(".\\.venv\\Scripts\\Activate.ps1", lang="powershell")
                        ui.text("macOS ou Linux", weight="semibold", size="sm")
                        ui.code("source .venv/bin/activate", lang="bash")

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("3", color="primary")
                        ui.heading("Installer et lancer", level=2)
                        ui.code(
                            "python -m pip install -e .\n"
                            "bretzel dev",
                            lang="bash",
                        )
                        ui.text(
                            "Ouvrez `http://127.0.0.1:8000`. `bretzel dev` "
                            "surveille les fichiers et relance l’application à chaque "
                            "modification.",
                            color="muted", size="sm",
                        )

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("4", color="primary")
                        ui.heading("Modifier la page", level=2)
                        ui.text(
                            "Ouvrez `app/features/home.py`, changez le titre et "
                            "enregistrez. Le navigateur recharge l’application.",
                            color="muted", size="sm",
                        )
                        ui.code(
                            'ui.heading("Mon premier Bretzel", level=1, size="4xl")',
                            lang="python",
                        )

            with ui.card(color="primary"):
                with ui.vstack(gap="md"):
                    ui.heading("Ce que le générateur a créé", level=2)
                    ui.code(
                        "hello-bretzel/\n"
                        "├── app/\n"
                        "│   ├── main.py              # configure l’application\n"
                        "│   └── features/\n"
                        "│       └── home.py          # votre première page\n"
                        "├── pyproject.toml\n"
                        "└── README.md",
                        lang="text",
                    )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button(
                            "Comprendre le modèle", href="/how",
                            icon_right="arrow-right",
                        )
                        ui.button(
                            "Lire la configuration", href="/config",
                            variant="outline",
                        )

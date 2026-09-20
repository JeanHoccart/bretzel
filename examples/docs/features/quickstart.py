"""The first complete journey: from zero to a modified Bretzel page."""

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/quickstart"


@page(PATH, layout=shell, title="Quickstart")
def quickstart_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="xl"):
            with ui.vstack(gap="sm", classes="max-w-4xl"):
                with ui.hstack(align="center", gap="sm", wrap=True):
                    ui.badge("Quickstart", color="primary", variant="soft")
                    ui.badge("5 minutes", color="muted", variant="outline")
                ui.heading(tr("Your first Bretzel app", "Votre première application Bretzel"), level=1, size="4xl")
                ui.text(
                    tr("Create the project, run the server, then edit a page. "
                       "At the end you will have completed the essential loop: "
                       "describe the interface in Python and watch the browser follow.",
                       "Créez le projet, lancez le serveur puis modifiez une page. "
                       "À la fin, vous aurez parcouru la boucle essentielle : "
                       "décrire l’interface en Python et voir le navigateur suivre."),
                    color="muted", size="lg",
                )

            with ui.card(color="warning"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr("Before the first PyPI release", "Avant la première version PyPI"), level=2, size="lg")
                    ui.text(
                        tr("Bretzel is still an early alpha. To try it today, install "
                           "the GitHub repository. After the first release, this command "
                           "will simply become `pip install bretzel`.",
                           "Bretzel est encore en early alpha. Pour l’essayer aujourd’hui, "
                           "installez le dépôt GitHub. Après la première publication, cette "
                           "commande deviendra simplement `pip install bretzel`."),
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
                        ui.heading(tr("Create the project", "Créer le projet"), level=2)
                        ui.code(
                            "bretzel new hello-bretzel\n"
                            "cd hello-bretzel\n"
                            "python -m venv .venv",
                            lang="bash",
                        )
                        ui.text(
                            tr("`bretzel new` creates a minimal application in a new "
                               "folder. It refuses to overwrite an existing directory.",
                               "`bretzel new` crée une application minimale dans un "
                               "nouveau dossier. Il refuse d’écraser un dossier existant."),
                            color="muted", size="sm",
                        )

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("2", color="primary")
                        ui.heading(tr("Activate the environment", "Activer l’environnement"), level=2)
                        ui.text("Windows PowerShell", weight="semibold", size="sm")
                        ui.code(".\\.venv\\Scripts\\Activate.ps1", lang="powershell")
                        ui.text(tr("macOS or Linux", "macOS ou Linux"), weight="semibold", size="sm")
                        ui.code("source .venv/bin/activate", lang="bash")

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("3", color="primary")
                        ui.heading(tr("Install and run", "Installer et lancer"), level=2)
                        ui.code(
                            "python -m pip install -e .\n"
                            "bretzel dev",
                            lang="bash",
                        )
                        ui.text(
                            tr("Open `http://127.0.0.1:8000`. `bretzel dev` watches "
                               "your files and restarts the application after every change.",
                               "Ouvrez `http://127.0.0.1:8000`. `bretzel dev` "
                               "surveille les fichiers et relance l’application à chaque "
                               "modification."),
                            color="muted", size="sm",
                        )

                with ui.card():
                    with ui.vstack(gap="md"):
                        ui.badge("4", color="primary")
                        ui.heading(tr("Edit the page", "Modifier la page"), level=2)
                        ui.text(
                            tr("Open `app/features/home.py`, change the heading, and save. "
                               "The browser reloads the application.",
                               "Ouvrez `app/features/home.py`, changez le titre et "
                               "enregistrez. Le navigateur recharge l’application."),
                            color="muted", size="sm",
                        )
                        ui.code(
                            'ui.heading("Mon premier Bretzel", level=1, size="4xl")',
                            lang="python",
                        )

            with ui.card(color="primary"):
                with ui.vstack(gap="md"):
                    ui.heading(tr("What the generator created", "Ce que le générateur a créé"), level=2)
                    ui.code(
                        "hello-bretzel/\n"
                        "├── app/\n"
                        "│   ├── main.py              # " + tr("configures the application", "configure l’application") + "\n"
                        "│   └── features/\n"
                        "│       └── home.py          # " + tr("your first page", "votre première page") + "\n"
                        "├── pyproject.toml\n"
                        "└── README.md",
                        lang="text",
                    )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button(
                            tr("Understand the model", "Comprendre le modèle"), href="/how",
                            icon_right="arrow-right",
                        )
                        ui.button(
                            tr("Read the configuration", "Lire la configuration"), href="/config",
                            variant="outline",
                        )

"""Accueil public de la documentation Bretzel."""

from bretzel import page, ui

from examples.docs.features.shell import shell


@page("/", layout=shell, title="Introduction")
def home_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="xl"):
            with ui.hstack(align="center", gap="sm", wrap=True):
                ui.badge("Documentation", color="primary", variant="soft")
                ui.badge("v0.1.0a1 · Early alpha", color="warning", variant="outline")

            with ui.hstack(align="center", justify="between", gap="xl", wrap=True):
                with ui.vstack(gap="md", classes="max-w-3xl"):
                    ui.heading(
                        "Construisez des applications web réactives en Python.",
                        level=1, size="4xl",
                    )
                    ui.text(
                        "Bretzel réunit composants, état typé et logique serveur "
                        "dans un seul modèle. Le navigateur reste synchronisé, "
                        "sans projet JavaScript ni chaîne npm à maintenir.",
                        color="muted", size="lg",
                    )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.button(
                            "Démarrer en 5 minutes", href="/config",
                            icon_right="arrow-right", size="lg",
                        )
                        ui.button(
                            "Comprendre le modèle", href="/how",
                            variant="outline", size="lg",
                        )
                ui.image(
                    "/_bretzel/favicon.svg", alt="Logo Bretzel", fit="contain",
                    classes="w-64 max-md:w-44 bg-transparent",
                    attrs={"loading": "eager"},
                )

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    with ui.hstack(align="center", justify="between", gap="md", wrap=True):
                        ui.text("Installation", weight="bold")
                        ui.badge("Python 3.12–3.13", color="muted", variant="outline")
                    ui.code(
                        "pip install bretzel\n"
                        "bretzel new mon-app\n"
                        "cd mon-app && bretzel dev",
                        lang="bash",
                    )

            ui.heading("Le modèle mental", level=2, size="2xl")
            with ui.grid(cols=3, gap="md", classes="max-lg:grid-cols-1"):
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.icon("database", color="primary", size="xl")
                        ui.heading("Un état typé", level=3)
                        ui.text(
                            "Le serveur détient la vérité dans des objets Python "
                            "explicites et testables.",
                            color="muted",
                        )
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.icon("mouse-pointer-click", color="secondary", size="xl")
                        ui.heading("Des actions Python", level=3)
                        ui.text(
                            "Les interactions appellent des handlers sans écrire "
                            "une seconde application côté client.",
                            color="muted",
                        )
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.icon("zap", color="warning", size="xl")
                        ui.heading("Une UI réactive", level=3)
                        ui.text(
                            "Quand l’état change, Bretzel met à jour seulement "
                            "les fragments qui en dépendent.",
                            color="muted",
                        )

            with ui.card(color="primary"):
                with ui.vstack(gap="sm"):
                    ui.heading("La seule idée à retenir", level=2)
                    ui.text(
                        "UI = f(state). Décrivez l’interface, modifiez l’état, "
                        "laissez Bretzel maintenir le navigateur à jour.",
                        size="lg",
                    )
                    ui.link("Lire comment Bretzel fonctionne →", href="/how")

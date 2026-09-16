"""DÉMARRER — Juger le code écrit contre le framework.

Le jumeau de « Décrire l'UI » : ``describe`` DIT ce qui existe,
``check`` juge ce qu'on en a fait. Les douze règles sont lues en direct
dans :data:`bretzel.lint.rules.STATIC` — leur nom et leur phrase
viennent du module qui les porte, donc ce chapitre ne peut pas annoncer
une règle morte ni en taire une neuve.

⚠️ Cette page importe ``bretzel.lint``, ce qu'aucun module du framework
n'a le droit de faire (contrat ``lint-stays-extractable``). C'est
volontaire et sans effet sur la garantie : ``examples/docs`` est une
APP, pas le framework — si ``lint`` sortait un jour du dépôt, ce
chapitre sortirait avec lui, ce qui est exactement le comportement
voulu.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.lint import rule_summaries

from examples.docs.features.shell import shell

PATH = "/check"


def rule_rows() -> list[dict[str, str]]:
    """Les règles vivantes et leur phrase, par la porte publique du linter.

    ``rule_summaries()`` EST ce que le CLI exécute, et la phrase vient
    du module qui porte la règle : une règle ajoutée apparaît ici au
    prochain rendu, une règle retirée disparaît, et aucune ligne de
    cette page ne redit ce qui est écrit ailleurs. Un catalogue recopié
    à la main dérive plus vite qu'il ne sert — ce dépôt a supprimé un
    skill entier pour cette raison.
    """
    return [
        {"regle": slug, "refuse": phrase}
        for slug, phrase in rule_summaries().items()
    ]


@page(PATH, layout=shell, title="Juger le code")
def check_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Juger le code", level=1, size="3xl")
            ui.text(
                "`describe` dit ce qui existe ; `check` juge ce que tu en "
                "as fait. Les deux lisent le code INSTALLÉ, donc aucun des "
                "deux ne peut se tromper d'époque.",
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Le lancer", level=2)
                    ui.code(
                        "py -m bretzel.cli.main check mon_app/\n"
                        "py -m bretzel.cli.main check --deep mon_app.main:app\n",
                        lang="bash",
                    )
                    ui.text(
                        "Le premier passage est STATIQUE : il lit les "
                        "fichiers, ne monte rien, et n'a besoin d'aucune "
                        "app qui démarre. `--deep` en plus monte l'app "
                        "réelle et arbitre sa carte — les features "
                        "déclarées contre ce qu'elles font vraiment.",
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Pourquoi un linter de PLUS", level=2)
                    ui.text(
                        "Ruff et mypy jugent du Python. Aucun des deux ne "
                        "sait qu'un kwarg inconnu passé à `ui.button` part "
                        "en attribut HTML inerte : ça ne lève pas, ça ne "
                        "s'affiche pas, et ça ne se voit pas en revue. "
                        "C'est le mode d'échec dominant ici, et c'est celui "
                        "que ces règles prennent — chacune attrape une "
                        "faute SILENCIEUSE.",
                        color="muted", size="sm",
                    )

            with ui.card(color="surface"):
                with ui.vstack(gap="md"):
                    rows = rule_rows()
                    with ui.hstack(align="center", gap="sm"):
                        ui.heading("Ce qu'il sait voir", level=2)
                        ui.badge(str(len(rows)), color="muted",
                                 variant="outline")
                    ui.text(
                        "Lu en direct par `rule_summaries()` — la table que "
                        "le CLI exécute, et la phrase que chaque règle "
                        "porte en tête de son module. Une règle neuve "
                        "apparaît ici sans qu'on édite cette page.",
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("regle", label="Règle"),
                            ui.column("refuse", label="Elle refuse…"),
                        ],
                        rows=rows,
                        size="sm",
                    )

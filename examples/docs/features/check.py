"""GETTING STARTED — Judging the code written against the framework.

"Describe the UI"'s twin: ``describe`` SAYS what exists, ``check``
judges what was done with it. The twelve rules are read live from
:data:`bretzel.lint.rules.STATIC` — their name and their sentence come
from the module carrying them, so this chapter cannot announce a dead
rule nor keep quiet about a new one.

⚠️ This page imports ``bretzel.lint``, which no module of the framework
is allowed to do (the ``lint-stays-extractable`` contract). It is
deliberate and has no effect on the guarantee: ``examples/docs`` is an
APP, not the framework — if ``lint`` ever left the repository, this
chapter would leave with it, which is exactly the intended behaviour.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.lint import rule_summaries

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/check"


def rule_rows() -> list[dict[str, str]]:
    """The live rules and their sentence, through the linter's public
    door.

    ``rule_summaries()`` IS what the CLI runs, and the sentence comes
    from the module carrying the rule: a rule added appears here at the
    next render, a rule removed disappears, and no line of this page
    repeats what is written elsewhere. A catalogue copied by hand drifts
    faster than it serves — this repository deleted a whole skill for
    that reason.
    """
    return [
        {"regle": slug, "refuse": phrase}
        for slug, phrase in rule_summaries().items()
    ]


@page(PATH, layout=shell, title=tr('Judge the code',
                                   'Juger le code'))
def check_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Judge the code',
                          'Juger le code'), level=1, size="3xl")
            ui.text(
                tr('`describe` says what exists; `check` judges what you made'
                   ' of it. Both read the INSTALLED code, so neither can be '
                   'out of date.',
                   '`describe` dit ce qui existe ; `check` juge ce que tu en '
                   'as fait. Les deux lisent le code INSTALLÉ, donc aucun des'
                   " deux ne peut se tromper d'époque."),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Running it',
                                  'Le lancer'), level=2)
                    ui.code(
                        "py -m bretzel.cli.main check mon_app/\n"
                        "py -m bretzel.cli.main check --deep mon_app.main:app\n",
                        lang="bash",
                    )
                    ui.text(
                        tr('The first pass is STATIC: it reads the files, '
                           'mounts nothing, and needs no app to start. '
                           '`--deep` additionally mounts the real app and '
                           'arbitrates its map — the declared features '
                           'against what they really do.',
                           'Le premier passage est STATIQUE : il lit les '
                           "fichiers, ne monte rien, et n'a besoin d'aucune "
                           "app qui démarre. `--deep` en plus monte l'app "
                           'réelle et arbitre sa carte — les features '
                           "déclarées contre ce qu'elles font vraiment."),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Why ONE MORE linter',
                                  'Pourquoi un linter de PLUS'), level=2)
                    ui.text(
                        tr('Ruff and mypy judge Python. Neither knows that an'
                           ' unknown kwarg passed to `ui.button` leaves as an'
                           ' inert HTML attribute: it does not raise, it does'
                           ' not show, and it is not visible in review. That '
                           'is the dominant failure mode here, and it is the '
                           'one these rules take — each catches a SILENT '
                           'mistake.',
                           'Ruff et mypy jugent du Python. Aucun des deux ne '
                           "sait qu'un kwarg inconnu passé à `ui.button` part"
                           ' en attribut HTML inerte : ça ne lève pas, ça ne '
                           "s'affiche pas, et ça ne se voit pas en revue. "
                           "C'est le mode d'échec dominant ici, et c'est "
                           'celui que ces règles prennent — chacune attrape '
                           'une faute SILENCIEUSE.'),
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
                        tr('Read live by `rule_summaries()` — the table the '
                           'CLI executes, and the sentence every rule carries'
                           ' at the head of its module. A new rule appears '
                           'here without this page being edited.',
                           'Lu en direct par `rule_summaries()` — la table '
                           'que le CLI exécute, et la phrase que chaque règle'
                           ' porte en tête de son module. Une règle neuve '
                           "apparaît ici sans qu'on édite cette page."),
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column("regle", label=tr('Rule',
                                                        'Règle')),
                            ui.column("refuse", label="Elle refuse…"),
                        ],
                        rows=rows,
                        size="sm",
                    )

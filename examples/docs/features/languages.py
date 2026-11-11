"""TOPIC — Speaking the visitor's language.

Two tables, one mechanism:

- **the framework's sentences** — "Go to slide 3", "Maximum size 8 MB",
  the accessibility labels nobody writes by hand — ship in English and
  French and follow ``lang``; an app has nothing to do;
- **the app's sentences** go through ``t("Create")``: the sentence as
  written in the code is the key, ``Bretzel(translations=…)`` gives the
  other languages, and a counted sentence takes the language's plural.

Formats derive from the language in the browser (``Intl``): month and day
names, a date field's ``16/10/2026``, a number field's ``2,5``.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/languages"


@page(PATH, layout=shell, title="The languages · Bretzel docs",
      description="Internationalisation in Bretzel: the framework's sentences, your app's "
                  "sentences through t(), plurals, and the formats the language gives.")
def languages_page() -> None:
    with ui.container(width="xl"), ui.vstack(gap="lg"):
        ui.heading("Speaking the visitor's language", level=1,
                   size="3xl")
        ui.text(
            "Declare the languages once. The framework's own sentences "
            "follow them; yours go through `t()`, with a table per "
            "language.",
            color="muted", size="lg",
        )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('What the framework does on its own', level=2)
            ui.text(
                "The sentences Bretzel produces — a carousel's "
                "accessibility labels, a `file_upload`'s maximum-"
                "size message, a table's result count — ship in "
                "English and French, and follow the language. "
                "Dates and numbers are shown the language's way: "
                "a date field reads `16/10/2026` in French and "
                "`10/16/2026` in American English, a number field "
                "`2,5` and `2.5` — the value posted stays the "
                "same.",
                color="muted", size="sm",
            )
            ui.code(
                'app = Bretzel(\n    secret_key="…",\n    lang="en",                  # the default language\n    languages=("en", "fr"),     # the ones we accept\n)\n',
                lang="python",
            )
            ui.text(
                'The language is resolved PER REQUEST: an explicit'
                " choice wins over the browser's header, and a "
                'language one has not declared falls back to the '
                'default. A single sentence of the framework can '
                'still be replaced, in the same `translations=` '
                'table, by its name (`"sidebar.toggle"`).',
                color="muted", size="sm",
            )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Your app's sentences: t()", level=2)
            ui.text(
                "Write the sentence in the code, in the app's "
                "language, and give the others in a table. The "
                "sentence is the key: the code reads like the "
                "screen, and a sentence nobody translated yet "
                "still shows, as written.",
                color="muted", size="sm",
            )
            ui.code(
                'from bretzel import Bretzel, t, ui\n\napp = Bretzel(\n    lang="en", languages=("en", "fr"),\n    translations={"fr": {\n        "Save": "Enregistrer",\n        "Hello {name}": "Bonjour {name}",\n    }},\n)\n\nui.button(t("Save"), color="primary")\nui.text(t("Hello {name}", name=user.name))\n',
                lang="python",
            )
            ui.text(
                "`t()` reads the request's language, so it is "
                "called while rendering or handling — never in a "
                "module-level constant, evaluated once for nobody. "
                "A translated list is a function, not a tuple.",
                color="muted", size="sm",
            )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Counting", level=2)
            ui.text(
                "A sentence with a number has several forms, and "
                "each language picks its own: English says the "
                "singular for 1 only, French for 0 and 1, Russian "
                "or Polish have a third and a fourth form. Give the "
                "plural in the code, the forms in the table — the "
                "language's rule chooses.",
                color="muted", size="sm",
            )
            ui.code(
                'ui.text(t("{n} task", n=count, plural="{n} tasks"))\n\n# in translations={"fr": {...}}:\n"{n} task": {"one": "{n} tâche", "other": "{n} tâches"},\n',
                lang="python",
            )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("What a table still lacks", level=2)
            ui.text(
                "The command reads the app's code for every "
                "`t(\"…\")` and prints, language by language, the "
                "sentences a table lacks — with where they are "
                "called — and the entries no call uses any more. "
                "At startup, a table for an undeclared language or "
                "a renamed hole raises.",
                color="muted", size="sm",
            )
            ui.code("bretzel translations main:app\n", lang="bash")

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading("Letting the user choose", level=2)
            ui.text(
                '`Language.set` is a SERVER handler: it picks the '
                'language and reloads the page in it. So one '
                'passes it as a `partial`, not as a call — '
                '`Language.set("fr")` would run at RENDER time, '
                'not on the click.',
                color="muted", size="sm",
            )
            ui.code(
                'from functools import partial\n\nui.button("English", on_click=partial(Language.set, "en"))\nui.button("Français", on_click=partial(Language.set, "fr"))\n',
                lang="python",
            )
            ui.text(
                'Why this exists when the language is already '
                'automatic: `Accept-Language` describes the '
                "operating system's configuration, not a reading "
                'choice. With no way of saying otherwise, somebody'
                ' whose machine is in English cannot read in '
                'French.',
                color="muted", size="sm",
            )

        with ui.card(), ui.vstack(gap="sm"):
            ui.heading('What it does not do', level=2)
            ui.alert(
                'The tables are Python dicts, not `.po` files: an '
                'app that hands them to translators loads them from '
                'the files it prefers. Dates and numbers written by '
                'the server — in a sentence, a cell — are formatted '
                'by the app; the framework formats those of its '
                'fields, in the browser. Right-to-left languages are '
                'not handled.',
                color="info", title='The limits',
            )

"""TOPIC — Speaking the visitor's language.

The split is clear-cut, and it is what must be understood before writing
a line:

- **the framework translates ITS sentences** — "Go to slide 3", "Maximum
  size 8 MB", the accessibility labels nobody writes by hand. It is
  ``bretzel.render.text``, and an app has nothing to do to benefit;
- **the app translates ITS OWN.** Bretzel does not know them and never
  will. It provides the seam: ``Language().code``.

⚠️ This is NOT an i18n library. No `.po` files, no plurals, no localised
dates beyond what the browser does. The roadmap announces it in 2.1 —
this chapter describes what EXISTS.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/languages"


@page(PATH, layout=shell, title=tr('The languages',
                                   'Les langues'))
def languages_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr("Speaking the visitor's language",
                          'Parler la langue de qui visite'), level=1,
                       size="3xl")
            ui.text(
                tr('Two halves, and only one is yours: the framework '
                   'translates its own sentences, your app translates its '
                   'own.',
                   'Deux moitiés, et une seule vous appartient : le framework'
                   ' traduit ses propres phrases, votre app traduit les '
                   'siennes.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What the framework does on its own',
                                  'Ce que le framework fait tout seul'),
                               level=2)
                    ui.text(
                        tr("The sentences Bretzel produces — a carousel's "
                           "accessibility labels, a `file_upload`'s maximum-"
                           "size message, an empty table's text — go through "
                           "its own table. Declare the app's languages, and "
                           'they follow.',
                           'Les phrases que Bretzel produit — libellés '
                           "d'accessibilité d'un carrousel, message de taille"
                           " maximale d'un `file_upload`, texte d'un tableau "
                           'vide — passent par sa propre table. Déclarez les '
                           "langues de l'app, et elles suivent."),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('app = Bretzel(\n    secret_key="…",\n    lang="en",                  # the default language\n    languages=("en", "fr"),     # the ones we accept\n)\n',
                           'app = Bretzel(\n    secret_key="…",\n    lang="fr",                  # la langue par défaut\n    languages=("fr", "en"),     # celles qu\'on accepte\n)\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('The language is resolved PER REQUEST: an explicit'
                           " choice wins over the browser's header, and a "
                           'language one has not declared falls back to the '
                           'default rather than rendering a raw key.',
                           'La langue est résolue PAR REQUÊTE : un choix '
                           "explicite l'emporte sur l'en-tête du navigateur, "
                           "et une langue qu'on n'a pas déclarée retombe sur "
                           'le défaut plutôt que de rendre une clé brute.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What your app must do',
                                  'Ce que votre app doit faire'), level=2)
                    ui.text(
                        tr('`Language()` reads like its three ambient sisters'
                           ' — `Screen()`, `ColorScheme()`, '
                           '`LiveConnection()`: one object, one field. The '
                           'table is yours.',
                           '`Language()` se lit comme ses trois sœurs '
                           "d'ambiance — `Screen()`, `ColorScheme()`, "
                           '`LiveConnection()` : un objet, un champ. À vous '
                           'la table.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('from bretzel import Language\n\nPHRASES = {\n    "en": {"save": "Save", "cancel": "Cancel"},\n    "fr": {"save": "Enregistrer",\n            "cancel": "Annuler"},\n}\n\ndef say(key: str) -> str:\n    """A function, not a component: this is TEXT, and\n    it must be able to go into a `placeholder=` as\n    much as into a `ui.text`."""\n    code = Language().code.split("-")[0]\n    return PHRASES.get(code, PHRASES["en"])[key]\n\nui.button(say("save"), color="primary")\n',
                           'from bretzel import Language\n\nPHRASES = {\n    "fr": {"save": "Enregistrer",\n            "cancel": "Annuler"},\n    "en": {"save": "Save", "cancel": "Cancel"},\n}\n\ndef dire(cle: str) -> str:\n    """Une fonction, pas un composant : c\'est du\n    TEXTE, et il doit pouvoir aller dans un\n    `placeholder=` comme dans un `ui.text`."""\n    code = Language().code.split("-")[0]\n    return PHRASES.get(code, PHRASES["en"])[cle]\n\nui.button(dire("save"), color="primary")\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('`Language().code` can carry a region (`fr-CA`, '
                           '`en-GB`). Cutting at the hyphen is the simplest '
                           'form that works; keeping the region only makes '
                           'sense if the table really distinguishes it.',
                           '`Language().code` peut porter une région (`fr-'
                           'CA`, `en-GB`). Couper au tiret est la forme la '
                           "plus simple qui marche ; garder la région n'a de "
                           'sens que si la table la distingue vraiment.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("Laisser choisir", level=2)
                    ui.text(
                        tr('`Language.set` is a SERVER handler: it picks the '
                           'language and reloads the page in it. So one '
                           'passes it as a `partial`, not as a call — '
                           '`Language.set("fr")` would run at RENDER time, '
                           'not on the click.',
                           '`Language.set` est un handler SERVEUR : il '
                           'choisit la langue et recharge la page dedans. On '
                           'le passe donc en `partial`, pas en appel — '
                           '`Language.set("fr")` s\'exécuterait au RENDU, pas '
                           'au clic.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('from functools import partial\n\nui.button("English", on_click=partial(Language.set, "en"))\nui.button("Français", on_click=partial(Language.set, "fr"))\n',
                           'from functools import partial\n\nui.button("Français", on_click=partial(Language.set, "fr"))\nui.button("English", on_click=partial(Language.set, "en"))\n'),
                        lang="python",
                    )
                    ui.text(
                        tr('Why this exists when the language is already '
                           'automatic: `Accept-Language` describes the '
                           "operating system's configuration, not a reading "
                           'choice. With no way of saying otherwise, somebody'
                           ' whose machine is in English cannot read in '
                           'French.',
                           'Pourquoi ça existe alors que la langue est déjà '
                           'automatique : `Accept-Language` décrit la '
                           "configuration du système d'exploitation, pas un "
                           'choix de lecture. Sans un moyen de dire le '
                           "contraire, quelqu'un dont la machine est en "
                           'anglais ne peut pas lire en français.'),
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What it does not do',
                                  'Ce que ça ne fait pas'), level=2)
                    ui.alert(
                        tr('This is not an i18n library. No `.po` files, no '
                           'plural rules, no string extraction, no date or '
                           'currency formatting beyond what the browser can '
                           "do. It is a SEAM: the request's language, and the"
                           " framework's table for its own words. The roadmap"
                           ' announces full i18n in 2.1.',
                           "Ce n'est pas une bibliothèque d'i18n. Pas de "
                           'fichiers `.po`, pas de règles de pluriel, pas '
                           "d'extraction de chaînes, pas de formatage de "
                           'dates ou de devises au-delà de ce que le '
                           "navigateur sait faire. C'est une COUTURE : la "
                           'langue de la requête, et la table du framework '
                           'pour ses propres mots. La feuille de route '
                           "annonce l'i18n complète en 2.1."),
                        color="warning", title=tr('A seam, not a library',
                                                  'Une couture, pas une lib'),
                    )
                    ui.text(
                        tr('That split is a choice, not a lack of time: an '
                           "app's sentences belong to it, and a framework "
                           'imposing its catalogue format would impose its '
                           'tooling too.',
                           'Ce partage est un choix, pas un manque de temps :'
                           " les phrases d'une app lui appartiennent, et un "
                           'framework qui imposerait son format de catalogue '
                           'imposerait aussi son outillage.'),
                        color="muted", size="sm",
                    )

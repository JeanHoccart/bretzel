"""REFERENCE — App structure.

The flat app: features at one level that decorate themselves, a ``main``
that ``include``s them, a ``core`` for the global-only. No ``app/``
folder. These docs ARE a flat app — they take themselves as the example.

⚠️ **What this page announced less of than the framework.** It listed
three decorators — ``@page`` / ``@layout`` / ``@error_page`` — under the
title "the three feature roles". There are eleven, and above all it
mentioned ``Feature`` nowhere, the contract declaring what a feature
provides and what it depends on, checked as a graph at startup.

Hence the structural correction: **the decorator table RESOLVES every
symbol it names** (:data:`MARQUEURS`), and the ``Feature`` kinds are read
from ``FEATURE_KINDS``, imported through its layer's public door —
``bretzel.server``, and not ``bretzel.server.feature``, which the gate
``test_no_example_dives_below_a_public_door`` refuses (it bit here on the
first attempt). A page that names a vanished decorator says so on screen
instead of letting it be believed, and
``test_the_structure_chapter_names_real_decorators`` makes it blush
first.
"""

from __future__ import annotations

import importlib

from bretzel import page, ui
from bretzel.server import FEATURE_KINDS

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/structure"

#: What a feature may declare: the decorator's dotted path, the form one
#: writes, and what it sets.
#:
#: The order is the one in which they are met while building an app — the
#: views first, the machinery next.
MARQUEURS: tuple[tuple[str, str, str], ...] = (
    ("bretzel.page", '@page("/tarifs")',
     tr('a route that renders a view',
        'une route qui rend une vue')),
    ("bretzel.layout", "@layout",
     tr('a reusable shell (nav, chrome) — referenced by `layout=`',
        'une coquille réutilisable (nav, chrome) — référencée par `layout=`')),
    ("bretzel.error_page", "@error_page(404)",
     tr('the rendering of an HTTP status',
        "le rendu d'un statut HTTP")),
    ("bretzel.download", '@download("/export.csv")',
     tr('a route that returns a FILE, not a page',
        'une route qui rend un FICHIER, pas une page')),
    ("bretzel.refreshable", "@refreshable(deps=[Panier])",
     tr('a zone that re-renders when a state mutates',
        'une zone qui se re-rend quand un état mute')),
    ("bretzel.background", "@background",
     tr('work launched after the response, off the critical path',
        'un travail lancé après la réponse, hors du chemin critique')),
    ("bretzel.idempotent", "@idempotent",
     tr('an action a double click must not run twice',
        "une action qu'un double clic ne doit pas exécuter deux fois")),
    ("bretzel.auth.source", "@auth.source",
     tr('where an identity can come from (an API token, a trusted proxy…)',
        "d'où une identité peut venir (jeton d'API, proxy de confiance…)")),
    ("bretzel.auth.door", "@auth.door(OIDC(...))",
     tr('an OAuth/OIDC door, and the decision to accept the profile',
        "une porte OAuth/OIDC, et la décision d'accepter le profil")),
    ("bretzel.server.decorators.middleware", "@middleware",
     tr('one pass on every request',
        'un passage sur chaque requête')),
    ("bretzel.server.decorators.lifecycle.startup", "@startup / @shutdown",
     tr("opening and closing the app's resources",
        "l'ouverture et la fermeture des ressources de l'app")),
)


def resolve(chemin: str) -> bool:
    """Does the symbol really exist?

    ⚠️ We import the longest importable prefix then descend by
    ``getattr``: ``bretzel.auth`` is a module, ``bretzel.page`` an
    attribute of the package, and cutting the path in two would fail on
    one or the other.
    """
    parts = chemin.split(".")
    objet = None
    reste = list(parts)
    for coupe in range(len(parts), 0, -1):
        try:
            objet = importlib.import_module(".".join(parts[:coupe]))
        except ImportError:
            continue
        reste = parts[coupe:]
        break
    if objet is None:
        return False
    for attribut in reste:
        if not hasattr(objet, attribut):
            return False
        objet = getattr(objet, attribut)
    return True


def marqueurs_table() -> None:
    """The eleven markers — each resolved before being shown."""
    ui.table(
        columns=[
            ui.column("forme", label=tr('What one writes',
                                        "Ce qu'on écrit")),
            ui.column("pose", label=tr('What it declares',
                                       'Ce que ça déclare')),
        ],
        rows=[
            {
                "forme": forme if resolve(chemin)
                else f"{forme}  ⚠️ introuvable — cette page est périmée",
                "pose": pose,
            }
            for chemin, forme, pose in MARQUEURS
        ],
        size="sm",
    )


@page(PATH, layout=shell, title="Structure d'app")
def structure_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Structure d'app", level=1, size="3xl")
            ui.text(
                tr('Everything is a feature, flat. Each decorates itself; '
                   '`main` gathers them. No `app/` folder, no central wiring.',
                   'Tout est une fonctionnalité, à plat. Chacune se décore '
                   'elle-même ; `main` les rassemble. Pas de dossier `app/`, '
                   'pas de câblage central.'),
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The skeleton',
                                  'Le squelette'), level=2)
                    ui.code(
                        tr('examples/docs/\n├── main.py            # creates Bretzel(...) + app.include(...)\n├── features/          # everything flat\n│   ├── shell.py       # @layout — the shell (nav, chrome)\n│   ├── home.py        # @page("/")\n│   ├── components.py  # @page("/components")\n│   ├── errors.py      # @error_page(404) / @error_page(500)\n│   └── …\n└── lib/               # shared helpers (introspect, blocks)\n',
                           'examples/docs/\n├── main.py            # crée Bretzel(...) + app.include(...)\n├── features/          # tout à plat\n│   ├── shell.py       # @layout — la coquille (nav, chrome)\n│   ├── home.py        # @page("/")\n│   ├── components.py  # @page("/components")\n│   ├── errors.py      # @error_page(404) / @error_page(500)\n│   └── …\n└── lib/               # helpers partagés (introspect, blocks)\n'),
                        lang="text",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('A feature decorates itself',
                                  'Une fonctionnalité se décore elle-même'),
                               level=2)
                    ui.text(
                        tr('The decorator only MARKS the function. The actual'
                           ' registration happens in `app.include(…)` — the '
                           'import order has no effect at all.',
                           'Le décorateur ne fait que MARQUER la fonction. '
                           "L'enregistrement effectif arrive dans "
                           "`app.include(…)` — l'ordre des imports n'a aucun "
                           'effet.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# features/home.py\n"
                        "from bretzel import page, ui\n"
                        "from examples.docs.features.shell import shell\n"
                        "\n"
                        "@page(\"/\", layout=shell, title=\"Accueil\")\n"
                        "def home_page() -> None:\n"
                        "    ui.heading(\"Bienvenue\")\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("main rassemble", level=2)
                    ui.text(
                        tr('`app.include(module, …)` scans the modules for '
                           'their marks. The `shell` (`@layout`) does not '
                           'need including — it resolves by reference through'
                           ' `layout=shell`.',
                           '`app.include(module, …)` scanne les modules pour '
                           "leurs marques. Le `shell` (`@layout`) n'a pas "
                           "besoin d'être inclus — il se résout par référence"
                           ' via `layout=shell`.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# main.py\n"
                        "from bretzel import Bretzel\n"
                        "\n"
                        "app = Bretzel(secret_key=\"…\", mode=\"dev\")\n"
                        "\n"
                        "from examples.docs.features import home, components, errors\n"
                        "app.include(home, components, errors)\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Flat, yes — but not necessarily',
                                  'À plat, oui — mais pas obligatoirement'),
                               level=2)
                    ui.text(
                        tr('“Flat” is the default, not a constraint. One '
                           'folder per domain works, and the framework has '
                           'nothing to know: `include` scans the top-level '
                           'callables of the module it is given. So it is '
                           "enough for the sub-folder's `__init__.py` to RE-"
                           'EXPORT its pages.',
                           '« À plat » est le défaut, pas une contrainte. Un '
                           "dossier par domaine marche, et le framework n'a "
                           'rien à savoir : `include` scanne les callables de'
                           " premier niveau du module qu'on lui donne. Il "
                           'suffit donc que le `__init__.py` du sous-dossier '
                           'RÉEXPORTE ses pages.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('myapp/\n├── main.py\n└── billing/              # one domain, one folder\n    ├── __init__.py       # re-exports the pages\n    ├── quotes.py         # @page("/quotes")\n    └── invoices.py       # @page("/invoices")\n',
                           'monapp/\n├── main.py\n└── facturation/          # un domaine, un dossier\n    ├── __init__.py       # réexporte les pages\n    ├── devis.py          # @page("/devis")\n    └── factures.py       # @page("/factures")\n'),
                        lang="text",
                    )
                    ui.code(
                        tr('# billing/__init__.py\nfrom myapp.billing.quotes import quotes_page\nfrom myapp.billing.invoices import invoices_page\n\n# main.py\nfrom myapp import billing\napp.include(billing)          # both routes mount\n',
                           '# facturation/__init__.py\nfrom monapp.facturation.devis import devis_page\nfrom monapp.facturation.factures import factures_page\n\n# main.py\nfrom monapp import facturation\napp.include(facturation)      # les deux routes montent\n'),
                        lang="python",
                    )
                    ui.alert(
                        tr('The trap is there, and it is silent: if the '
                           '`__init__.py` re-exports the MODULES (`from . '
                           'import quotes, invoices`) instead of the '
                           'functions, `include` finds no mark and the routes'
                           ' return 404 — with no error at startup. Measured.'
                           ' In that case, include the modules themselves: '
                           '`app.include(billing.quotes, billing.invoices)`.',
                           'Le piège est là, et il est silencieux : si le '
                           '`__init__.py` réexporte les MODULES (`from . '
                           'import devis, factures`) au lieu des fonctions, '
                           '`include` ne trouve aucune marque et les routes '
                           'rendent 404 — sans erreur au démarrage. Mesuré. '
                           'Dans ce cas, incluez les modules eux-mêmes : '
                           '`app.include(facturation.devis, '
                           'facturation.factures)`.'),
                        color="warning",
                        title=tr('Re-export the FUNCTIONS, not the modules',
                                 'Réexporter les FONCTIONS, pas les modules'),
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(f"Les {len(MARQUEURS)} marqueurs", level=2)
                    ui.text(
                        tr('A feature does not declare views only. Everything'
                           ' that follows is placed the same way — one '
                           'decorates a function at module level, and '
                           '`include` picks it up.',
                           'Une fonctionnalité ne déclare pas que des vues. '
                           'Tout ce qui suit se pose de la même façon — on '
                           'décore une fonction au niveau du module, et '
                           '`include` la ramasse.'),
                        color="muted", size="sm",
                    )
                    marqueurs_table()
                    ui.text(
                        tr('Every row is checked at display time: the symbol '
                           'is really resolved. A renamed decorator would '
                           'flag itself here instead of letting you believe '
                           'it exists.',
                           "Chaque ligne est vérifiée à l'affichage : le "
                           'symbole est résolu pour de vrai. Un décorateur '
                           'renommé se signalerait ici au lieu de laisser '
                           "croire qu'il existe."),
                        color="muted", size="xs",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('When the app grows: declaring a contract',
                                  "Quand l'app grandit : déclarer un contrat"),
                               level=2)
                    ui.text(
                        tr('Flat and with no contract, nothing stops a '
                           'feature importing another quietly. `Feature` '
                           'makes the dependency explicit: what I provide, '
                           'what I use, what I read. The graph is checked at '
                           'startup — an unknown dependency, a cycle and a '
                           'name collision are errors, not run-time '
                           'surprises.',
                           "À plat et sans contrat, rien n'empêche une "
                           "fonctionnalité d'en importer une autre en douce. "
                           '`Feature` rend la dépendance explicite : ce que '
                           'je fournis, ce dont je me sers, ce que je lis. Le'
                           ' graphe est vérifié au démarrage — dépendance '
                           'inconnue, cycle et collision de noms sont des '
                           "erreurs, pas des surprises à l'exécution."),
                        color="muted", size="sm",
                    )
                    ui.code(
                        tr('# features/cart/feature.py\nfrom bretzel import Feature\nfrom .state import CartState\nfrom .ui import cart_page\n\nfeature = Feature(\n    name="cart",\n    kind="page",\n    provides=[CartState, cart_page],   # my public surface\n    uses=["catalog_data", "money"], # the only ones I may import\n)\n',
                           '# features/cart/feature.py\nfrom bretzel import Feature\nfrom .state import CartState\nfrom .ui import cart_page\n\nfeature = Feature(\n    name="cart",\n    kind="page",\n    provides=[CartState, cart_page],   # ma surface publique\n    uses=["catalog_data", "money"], # les seules que je peux importer\n)\n'),
                        lang="python",
                    )
                    ui.text(
                        f"`kind=` prend l'une des {len(FEATURE_KINDS)} "
                        f"valeurs suivantes : "
                        f"{', '.join('`' + k + '`' for k in sorted(FEATURE_KINDS))}.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="sm", wrap=True, align="baseline"):
                        ui.text(tr('The graph rendered live on a demo app:',
                                   'Le graphe rendu en direct sur une app de '
                                   'démo :'), color="muted", size="sm")
                        ui.link("Carte de l'app →", href="/app-map")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('Having the structure judged',
                                  'Faire juger la structure'), level=2)
                    ui.text(
                        tr('`check` reads the code written against the '
                           'framework. With `--deep`, it mounts the named app'
                           ' and arbitrates its map too — which reading files'
                           ' alone cannot see.',
                           '`check` lit le code écrit contre le framework. '
                           "Avec `--deep`, il monte l'app désignée et arbitre"
                           " aussi sa carte — ce qu'une lecture de fichiers "
                           'seule ne peut pas voir.'),
                        color="muted", size="sm",
                    )
                    ui.code(
                        "py -m bretzel.cli.main check examples\n"
                        "py -m bretzel.cli.main check --deep examples.docs.main:app\n",
                        lang="bash",
                    )

            with ui.card(color="surface"):
                ui.text(
                    tr('These docs run exactly like that: '
                       '`examples/docs/features/` flat, `shell.py` as the '
                       '`@layout`, `main.py` doing the `include`. What you '
                       'are reading IS the pattern. `core/` (when it exists) '
                       'carries the global-only: shared states, cross-cutting'
                       ' config — no views.',
                       'Cette doc tourne exactement comme ça : '
                       '`examples/docs/features/` à plat, `shell.py` en '
                       '`@layout`, `main.py` qui `include`. Ce que tu lis EST'
                       ' le pattern. `core/` (quand il existe) porte le '
                       'global-only : états partagés, config transverse — pas'
                       ' de vue.'),
                    color="muted", size="sm",
                )

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

PATH = "/structure"

#: What a feature may declare: the decorator's dotted path, the form one
#: writes, and what it sets.
#:
#: The order is the one in which they are met while building an app — the
#: views first, the machinery next.
MARQUEURS: tuple[tuple[str, str, str], ...] = (
    ("bretzel.page", '@page("/pricing")',
     'a route that renders a view'),
    ("bretzel.layout", "@layout",
     'a reusable shell (nav, chrome) — referenced by `layout=`'),
    ("bretzel.error_page", "@error_page(404)",
     'the rendering of an HTTP status'),
    ("bretzel.download", '@download("/export.csv")',
     'a route that returns a FILE, not a page'),
    ("bretzel.refreshable", "@refreshable",
     'a zone that re-renders when a state mutates'),
    ("bretzel.background", "@background",
     'work launched after the response, off the critical path'),
    ("bretzel.idempotent", "@idempotent",
     'an action a double click must not run twice'),
    ("bretzel.auth.source", "@auth.source",
     'where an identity can come from (an API token, a trusted proxy…)'),
    ("bretzel.auth.door", "@auth.door(OIDC(...))",
     'an OAuth/OIDC door, and the decision to accept the profile'),
    ("bretzel.server.decorators.middleware", "@middleware",
     'one pass on every request'),
    ("bretzel.server.decorators.lifecycle.startup", "@startup / @shutdown",
     "opening and closing the app's resources"),
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
            ui.column("forme", label='What one writes'),
            ui.column("pose", label='What it declares'),
        ],
        rows=[
            {
                "forme": forme if resolve(chemin)
                else f"{forme}  ⚠️ not found — this page is out of date",
                "pose": pose,
            }
            for chemin, forme, pose in MARQUEURS
        ],
        size="sm",
    )


@page(PATH, layout=shell, title="App structure · Bretzel docs",
      description="Structure a Bretzel app: flat features that decorate themselves, gathered by main with app.include and no central wiring.")
def structure_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("App structure", level=1, size="3xl")
            ui.text(
                'Everything is a feature, flat. Each decorates itself; '
                '`main` gathers them. No `app/` folder, no central wiring.',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The skeleton', level=2)
                    ui.code(
                        'examples/docs/\n├── main.py            # creates Bretzel(...) + app.include(...)\n├── features/          # everything flat\n│   ├── shell.py       # @layout — the shell (nav, chrome)\n│   ├── home.py        # @page("/")\n│   ├── components.py  # @page("/components")\n│   ├── errors.py      # @error_page(404) / @error_page(500)\n│   └── …\n└── lib/               # shared helpers (introspect, blocks)\n',
                        lang="text",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('A feature decorates itself',
                               level=2)
                    ui.text(
                        'The decorator only MARKS the function. The actual'
                        ' registration happens in `app.include(…)` — the '
                        'import order has no effect at all.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "# features/home.py\n"
                        "from bretzel import page, ui\n"
                        "from examples.docs.features.shell import shell\n"
                        "\n"
                        "@page(\"/\", layout=shell, title=\"Home\")\n"
                        "def home_page() -> None:\n"
                        "    ui.heading(\"Welcome\")\n",
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading("main gathers", level=2)
                    ui.text(
                        '`app.include(module, …)` scans the modules for '
                        'their marks. The `shell` (`@layout`) does not '
                        'need including — it resolves by reference through'
                        ' `layout=shell`.',
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
                    ui.heading('Flat, yes — but not necessarily',
                               level=2)
                    ui.text(
                        '“Flat” is the default, not a constraint. One '
                        'folder per domain works, and the framework has '
                        'nothing to know: `include` scans the top-level '
                        'callables of the module it is given. So it is '
                        "enough for the sub-folder's `__init__.py` to RE-"
                        'EXPORT its pages.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'myapp/\n├── main.py\n└── billing/              # one domain, one folder\n    ├── __init__.py       # re-exports the pages\n    ├── quotes.py         # @page("/quotes")\n    └── invoices.py       # @page("/invoices")\n',
                        lang="text",
                    )
                    ui.code(
                        '# billing/__init__.py\nfrom myapp.billing.quotes import quotes_page\nfrom myapp.billing.invoices import invoices_page\n\n# main.py\nfrom myapp import billing\napp.include(billing)          # both routes mount\n',
                        lang="python",
                    )
                    ui.alert(
                        'The trap is there, and it is silent: if the '
                        '`__init__.py` re-exports the MODULES (`from . '
                        'import quotes, invoices`) instead of the '
                        'functions, `include` finds no mark and the routes'
                        ' return 404 — with no error at startup. Measured.'
                        ' In that case, include the modules themselves: '
                        '`app.include(billing.quotes, billing.invoices)`.',
                        color="warning",
                        title='Re-export the FUNCTIONS, not the modules',
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(f"The {len(MARQUEURS)} markers", level=2)
                    ui.text(
                        'A feature does not declare views only. Everything'
                        ' that follows is placed the same way — one '
                        'decorates a function at module level, and '
                        '`include` picks it up.',
                        color="muted", size="sm",
                    )
                    marqueurs_table()
                    ui.text(
                        'Every row is checked at display time: the symbol '
                        'is really resolved. A renamed decorator would '
                        'flag itself here instead of letting you believe '
                        'it exists.',
                        color="muted", size="xs",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('When the app grows: declaring a contract',
                               level=2)
                    ui.text(
                        'Flat and with no contract, nothing stops a '
                        'feature importing another quietly. `Feature` '
                        'makes the dependency explicit: what I provide, '
                        'what I use, what I read. The graph is checked at '
                        'startup — an unknown dependency, a cycle and a '
                        'name collision are errors, not run-time '
                        'surprises.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        '# features/cart/feature.py\nfrom bretzel import Feature\nfrom .state import CartState\nfrom .ui import cart_page\n\nfeature = Feature(\n    name="cart",\n    kind="page",\n    provides=[CartState, cart_page],   # my public surface\n    uses=["catalog_data", "money"], # the only ones I may import\n)\n',
                        lang="python",
                    )
                    ui.text(
                        f"`kind=` takes one of these {len(FEATURE_KINDS)} "
                        f"values: "
                        f"{', '.join('`' + k + '`' for k in sorted(FEATURE_KINDS))}.",
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="sm", wrap=True, align="baseline"):
                        ui.text('The graph rendered live on a demo app:', color="muted", size="sm")
                        ui.link("App map →", href="/app-map")

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('Having the structure judged', level=2)
                    ui.text(
                        '`check` reads the code written against the '
                        'framework. With `--deep`, it mounts the named app'
                        ' and arbitrates its map too — which reading files'
                        ' alone cannot see.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "py -m bretzel.cli.main check examples\n"
                        "py -m bretzel.cli.main check --deep examples.docs.main:app\n",
                        lang="bash",
                    )

            with ui.card(color="surface"):
                ui.text(
                    'These docs run exactly like that: '
                    '`examples/docs/features/` flat, `shell.py` as the '
                    '`@layout`, `main.py` doing the `include`. What you '
                    'are reading IS the pattern. `core/` (when it exists) '
                    'carries the global-only: shared states, cross-cutting'
                    ' config — no views.',
                    color="muted", size="sm",
                )

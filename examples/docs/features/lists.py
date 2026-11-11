"""TOPIC — Lists and tables.

Two neighbouring capabilities, and it is the same need at two scales:
showing a collection that moves without re-rendering the whole page.

- ``ui.each`` / ``filter_each`` / ``paginate_each`` — the author writes
  the body, the framework sets the key and the client-side hiding;
- ``ui.datatable`` — the component owns the loop, because it sorts,
  filters, paginates and exports.

That difference is not a matter of taste: it is the base layer's
``COLLECTION_OWNER`` rule. **Whoever writes the ``for`` decides the API's
shape.** The author writes the loop → a ``with`` and children; the
component writes it → a ``render=``. Gated by
``test_collection_owner_decides_the_api``.
"""

from __future__ import annotations

from bretzel import page, ui
from examples.docs.features.shell import shell

PATH = "/lists"


@page(PATH, layout=shell, title="Lists and tables · Bretzel docs",
      description="Lists and tables in Bretzel: render a moving collection without re-rendering the page, with ui.each or ui.datatable.")
def lists_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading("Lists and tables", level=1, size="3xl")
            ui.text(
                'Displaying a moving collection, without re-rendering the '
                'page. Two tools, and the choice between them hangs on one'
                ' question: who writes the loop?',
                color="muted", size="lg",
            )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('The question that settles it', level=2)
                    ui.text(
                        "It is the base layer's COLLECTION_OWNER rule, and"
                        ' it is gated. Whoever writes the `for` decides '
                        'the shape of the API — because the rendering '
                        'happens there.',
                        color="muted", size="sm",
                    )
                    ui.table(
                        columns=[
                            ui.column('who', label='Who writes the loop'),
                            ui.column("api", label='The shape of the API'),
                            ui.column("ex", label="Example"),
                        ],
                        rows=[
                            {'who': "the author",
                             "api": 'a `with`, and the children inside',
                             "ex": "ui.each, filter_each, paginate_each"},
                            {'who': 'the component',
                             "api": 'a `render=` it calls per row',
                             "ex": "ui.datatable, ui.select"},
                            {'who': 'the client (JS)',
                             "api": 'neither one nor the other — the body '
                                    'is a template',
                             "ex": "ui.file_upload"},
                        ],
                        size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('ui.each — the key, and why it counts',
                               level=2)
                    ui.text(
                        'A bare `for` names each item by its rank. Fine '
                        'for a list written in the code (`for size in '
                        '("sm", "md")`): it never moves. For a list that '
                        'comes from data, deleting the first item shifts '
                        'the others, and a client state (an open menu, a '
                        'ticked box) stays with the rank: it lands on the '
                        'neighbour. `ui.each` names each item by its key, '
                        'so that state follows IDENTITY. In debug mode, '
                        'Bretzel warns when it happens — only then.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'for task in ui.each(tasks, key="id"):\n    with ui.card():\n        ui.text(task.title)\n        ui.accordion(...)      # keeps its state\n\n# `key=` also accepts a callable:\nfor t in ui.each(tasks, key=lambda t: t.uuid):\n    ui.text(t.title)\n',
                        lang="python",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('filter_each — narrowing as you type',
                               level=2)
                    ui.text(
                        'It sets a `bz-show` on every item, compared with '
                        'what is typed. The filtering is therefore '
                        'ENTIRELY client side: no round trip, and the '
                        'items are HIDDEN, not removed — the DOM count '
                        'does not move.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class Filter(ClientState):\n"
                        "    query: str = field(default=\"\")\n"
                        "\n"
                        "f = Filter()\n"
                        "ui.input(value=f.query, placeholder=\"Filter…\")\n"
                        "\n"
                        "for fruit in ui.filter_each(\n"
                        "    FRUITS,\n"
                        "    query=f.query,\n"
                        "    text=lambda x: x,          # what is searched\n"
                        "    key=lambda x: x,\n"
                        "    empty=lambda: ui.text(\"Nothing matches.\"),\n"
                        "):\n"
                        "    ui.text(fruit)\n",
                        lang="python",
                    )
                    ui.text(
                        '`empty=` is rendered too, and hidden as long as a'
                        ' row matches — otherwise it would take a round '
                        'trip to know there is nothing.',
                        color="muted", size="sm",
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('paginate_each — a client-side window',
                               level=2)
                    ui.text(
                        'The same mechanics: everything is rendered, only '
                        'the current window is visible. `page` is a '
                        '1-indexed `ClientBinding` — so a `ui.pagination` '
                        'drives it with no network.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        "class View(ClientState):\n"
                        "    page: int = field(default=1)\n"
                        "\n"
                        "v = View()\n"
                        "for row in ui.paginate_each(ROWS, page=v.page,\n"
                        "                            per_page=20, key=\"id\"):\n"
                        "    ui.text(row.name)\n"
                        "ui.pagination(value=v.page, total=len(ROWS),\n"
                        "              per_page=20)\n",
                        lang="python",
                    )
                    ui.alert(
                        'Everything is rendered: it is instant, and it '
                        'only suits what fits in memory. Beyond a few '
                        'hundred rows, `ui.datatable` is what you need — '
                        'it paginates on the SERVER and renders only the '
                        'page asked for.',
                        color="warning", title='Where the limit is',
                    )

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading('ui.datatable — the loop belongs to the '
                               'component', level=2)
                    ui.text(
                        'It sorts, filters, paginates, searches and '
                        'exports. It is what decides which rows exist, so '
                        'the author cannot write the `for` — they describe'
                        ' their columns, and pass a `render=` for the ones'
                        ' that are not text.',
                        color="muted", size="sm",
                    )
                    ui.code(
                        'class AccountsTable(DatatableState, scope="session",\n                    addressable=True):\n    """One subclass PER table: the state is keyed by\n    class, so sharing the base would share the sort\n    and the page."""\n\nui.datatable(\n    state=AccountsTable,\n    columns=[\n        ui.column("name", label="Name", sortable=True),\n        ui.column("city", label="City", filter=True),\n        ui.column("status", label="Status",\n                  render=lambda v, row: ui.badge(v)),\n    ],\n    rows=load,             # a list, or a callable(Query)\n    exportable=True,\n    export_filename="accounts.csv",\n    row_key="id",\n)\n',
                        lang="python",
                    )
                    ui.text(
                        '`addressable=True` gives the view an ADDRESS: '
                        'sorting, paginating or searching rewrites the '
                        'URL. The link shares, bookmarks, and the '
                        "browser's arrows go back and forth.",
                        color="muted", size="sm",
                    )
                    ui.alert(
                        '`rows=` accepts a list OR a callable that '
                        'receives the `Query` (sort, page, search) and '
                        'returns `(rows, total)`. It is the shape to take '
                        'as soon as the source is a database: without it, '
                        'one loads everything to display twenty.',
                        color="info", title='The parameter that changes '
                                            'everything',
                    )

            with ui.card(color="surface"):
                with ui.hstack(gap="sm", wrap=True, align="baseline"):
                    ui.text('The exact signatures:', color="muted",
                            size="sm")
                    ui.link("ui.* catalogue →", href="/components")

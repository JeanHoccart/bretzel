"""The RUNTIME chapter's render blocks — ``runtime_surface``'s mirrors.

The same contract as :mod:`examples.docs.lib.blocks`: a mirror knows no
content, it renders what the introspection gives it. Adding a directive,
a magic or a ``$bz.<name>`` to the framework makes it appear here at the
next render, without touching this file.

Separated from ``blocks.py`` for the duration of the "API surface" work
in progress — cf. :mod:`examples.docs.lib.runtime_surface`'s work note.
On folding back, :func:`grouped_tables` and :func:`section` are meant to
serve the other chapters: ``client_algebra_mirror`` (blocks.py) today
re-inlines the first one's exact body, and six pages of ``features/``
rewrite the second by hand.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager

from bretzel import ui
from examples.docs.lib.i18n import tr

from examples.docs.lib.runtime_surface import (
    binding_order,
    bundle_facts,
    describe_directives,
    describe_magics,
    describe_runtime_api,
    describe_runtime_modules,
)


@contextmanager
def section(title: str, intro: str = ""):
    """A chapter card: title, standfirst, then the body.

    The folder's pages write this preamble by hand, at four levels of
    indentation; ``cheatsheet.py`` had already extracted it for its own
    use.
    """
    with ui.card():
        with ui.vstack(gap="sm"):
            ui.heading(title, level=2)
            if intro:
                ui.text(intro, color="muted", size="sm")
            yield


def grouped_tables(
    ops: Sequence,
    columns: Iterable,
    row: Callable[[object], dict[str, str]],
) -> None:
    """One table per category, preceded by its label and its count.

    ``ops`` arrives already sorted by category (the ``describe_*`` see to
    that), so the groups are contiguous and ``groupby`` is enough.
    """
    for category, group in itertools.groupby(ops, key=lambda o: o.category):
        items = list(group)
        with ui.vstack(gap="xs"):
            with ui.hstack(align="center", gap="sm"):
                ui.text(category, weight="bold", size="sm")
                ui.badge(str(len(items)), color="muted", variant="outline")
            ui.table(columns=list(columns), rows=[row(o) for o in items],
                     size="sm")


def runtime_modules_mirror() -> None:
    """The bundle's modules, in load order, with their real weight. The
    base layer and the component engines are separated because it is not
    the same nature of code: the first is the runtime, the second is what
    the components deposit in it."""
    facts = bundle_facts()
    with ui.hstack(gap="sm", wrap=True, align="center"):
        ui.badge(f"{facts['modules']} modules", color="info", variant="soft")
        ui.badge(f"socle : {facts['core_modules']} fichiers, "
                 f"{facts['core_lines']} lignes", color="primary", variant="soft")
        ui.badge(f"bundle : {facts['bundle_bytes'] // 1024} Ko",
                 color="muted", variant="outline")

    grouped_tables(
        describe_runtime_modules(),
        [
            ui.column("file", label="Fichier"),
            ui.column("title", label=tr('Role',
                                        'Rôle')),
            ui.column("lines", label="Lignes", align="right"),
        ],
        lambda m: {"file": m.name, "title": m.title, "lines": str(m.lines)},
    )


def directives_mirror() -> None:
    """The directives, grouped by what they GUARANTEE (not by the module
    that implements them).

    Two text columns, and they do not have the same status: the
    "guarantee" is an editorial gloss, the "contract" is the definition
    the base layer gives of its own directive, read from ``protocol.py``.
    Showing both stops the second being silently covered over by the
    first.
    """
    ops = describe_directives()
    unwired = [o for o in ops if not o.implemented]
    if unwired:
        with ui.card(color="error"):
            ui.text(
                tr('Declared on the Python side, never wired into the '
                   'runtime: ',
                   'Déclarée côté Python, jamais branchée dans le runtime : ')
                + ", ".join(o.name for o in unwired)
                + tr('. Nothing raises at run time — a half-live directive is'
                     ' simply ignored by the browser.',
                     ". Rien ne lève à l'exécution — une directive à moitié "
                     'vivante est simplement ignorée par le navigateur.'),
                size="sm",
            )

    grouped_tables(
        ops,
        [
            ui.column("syntax", label=tr('Written into the HTML',
                                         'Écrit dans le HTML')),
            ui.column("doc", label="Ce qu'elle garantit"),
            ui.column("contract", label=tr('Declared by',
                                           'Déclarée par')),
        ],
        lambda o: {
            "syntax": o.syntax,
            "doc": o.doc,
            "contract": (f"{o.constant} — {o.protocol_note}"
                         if o.implemented
                         else f"{o.constant} — ⚠ non branchée"),
        },
    )

    order = binding_order()
    if order:
        with ui.vstack(gap="xs"):
            ui.text(tr('Wiring order on a single element',
                       'Ordre de câblage sur un même élément'), weight="bold",
                    size="sm")
            ui.text(" → ".join(order), classes="font-mono", size="sm",
                    color="muted")
            ui.text(
                tr('Read from the engine. It is not cosmetic: bz-ref is wired'
                   ' first (a neighbour can read it), bz-init last (the node '
                   'is fully wired when it runs).',
                   "Lu dans le moteur. Il n'est pas cosmétique : bz-ref est "
                   'câblé en premier (un voisin peut le lire), bz-init en '
                   'dernier (le nœud est entièrement câblé quand il tourne).'),
                color="muted", size="xs",
            )


def magics_mirror() -> None:
    """The variables available in a ``bz-*`` expression, read at their
    exact source: the expression compiler's argument list."""
    grouped_tables(
        describe_magics(),
        [
            ui.column("name", label="Variable"),
            ui.column("doc", label="Contenu"),
        ],
        lambda m: {"name": m.name, "doc": m.doc},
    )


def runtime_api_mirror() -> None:
    """The global ``$bz`` object's surface, module by module.

    The "exposes" column is read from the JS literal: it is what stops an
    eleventh helper staying invisible because the prose listed ten.

    What is private (the ``_`` prefix) is not hidden but reduced to a
    count and a list: reading it says what the framework reserves for
    itself, without suggesting it is an API.
    """
    ops = describe_runtime_api()
    public = [o for o in ops if o.public]
    private = [o for o in ops if not o.public]

    grouped_tables(
        public,
        [
            ui.column("name", label="Nom"),
            ui.column("doc", label=tr('What it is',
                                      "Ce que c'est")),
            ui.column("members", label="Expose"),
            ui.column("module", label=tr('Defined in',
                                         'Défini dans')),
        ],
        lambda o: {
            "name": f"$bz.{o.name}",
            "doc": o.doc,
            "members": ", ".join(o.members) or "—",
            "module": o.module,
        },
    )

    if private:
        with ui.accordion(collapsible=True):
            with ui.accordion_item(
                "private",
                label=f"{len(private)} entrées internes (préfixe _)",
                icon="lock",
            ):
                ui.text(
                    tr('The framework reserves them: they change without '
                       'notice and no component should call them. Two are '
                       'exceptions and are invoked from the server-rendered '
                       'HTML ($bz._resolveIcon, $bz._tick) — the prefix says '
                       '“the framework writes this”, not “nobody calls it”.',
                       'Le framework se les réserve : elles changent sans '
                       'préavis et aucun composant ne doit les appeler. Deux '
                       'font exception et sont invoquées depuis le HTML rendu'
                       ' par le serveur ($bz._resolveIcon, $bz._tick) — le '
                       'préfixe dit « le framework écrit ça », pas « personne'
                       " ne l'appelle »."),
                    color="muted", size="sm",
                )
                ui.text(
                    "  ".join(f"$bz.{o.name}" for o in private),
                    classes="font-mono", size="xs", color="muted",
                )

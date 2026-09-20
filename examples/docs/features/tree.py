"""REFERENCE — The framework's tree, built on its own.

This page writes NOTHING. It calls ``describe_package("bretzel")`` and
recursively renders what comes back: 117 folders, 303 modules and 608
public symbols, each with the sentence its author wrote.

⚠️ **It stopped at the folders, and it looked empty** — because 73 of
their 117 docstrings are generated stubs ("icon_button component."). The
content was one level down: 97 % of the public symbols have a real first
line. It is that level that has been shown since 2026-09-02.

Why it exists
--------------
The question "what can Bretzel do, without reading all the code?" had no
answer in one piece. There were three, separate, and one had to know
which to ask for:

======================  ===========  ===============================
the tree                117 lines    what EXISTS
the classified surfaces 258 lines    what each symbol is FOR
the ``ui.*`` detail     2 827 lines  params, slots, events
======================  ===========  ===============================

3 202 lines in all — unreadable in one block, navigable as a tree. So it
is the tree that serves as the ENTRY, and the detail comes on demand.

⚠️ **It builds itself at every render, so it cannot go stale.** A folder
added tomorrow appears in it without anybody touching this file — which
is exactly what this repository's hand-written lists lacked, and what
made the ``bretzel-api`` skill be deleted on 2026-08-01.

The only invariant to keep is that a folder has a docstring, and
``test_every_package_describes_itself`` sees to that.

⚠️ What the page does NOT show: of a symbol, it gives the name and the
first line, **not its parameters, its slots nor its events**. The
``ui.*`` catalogue has its page (``/components``), and ``bretzel describe
<name>`` gives the complete card at the command line. Putting everything
here would make 3 202 lines nobody would read.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.state import ClientState, field
from bretzel.introspect import (
    ModuleInfo,
    PackageNode,
    SymbolLine,
    describe_package,
    module_names,
    package_names,
    walk,
)

from examples.docs.features.shell import shell
from examples.docs.lib.blocks import plain
from examples.docs.lib.i18n import tr

PATH = "/tree"


class Selection(ClientState):
    """The selected package — ON THE CLIENT, and that is the point.

    The 117 panels are rendered at once and `visible=` hides 116: so the
    selection is INSTANT — no round trip, no latency, no zone to refresh.
    The alternative (a `@refreshable` on `on_change`) would cost one POST
    per click to show text the server already had at hand on the first
    render.

    ⚠️ **What it costs, measured, and it is more than what was written
    here.** This docstring's first version said "25 kB of text" — that is
    the docstrings' size, not the page's. The page is **599 kB**
    (2026-09-02), because the markup weighs ten times its text. It is
    accepted for a reference page one opens in dev, and it would not be
    in an app.
    """

    picked: str = field(default="bretzel")

#: The packages that ALSO have a classification by need. We flag them in
#: the tree: they are the only ones where `describe` returns a grouped
#: surface rather than a plain filing.
_CLASSES = frozenset(module_names())


def noeud(n: PackageNode) -> None:
    """A package and its descendants — RECURSIVE, like the tree read.

    ``ui.tree_node`` is a container: a ``with`` of nested nodes makes a
    branch of it. So we give it exactly the ``PackageNode``'s shape,
    without flattening.
    """
    # The label carries the folder's sentence — it is WHAT one comes to
    # read, and putting it in a tooltip would make it invisible on touch
    # (hovering does not exist with a finger).
    with ui.tree_node(value=n.name, label=libelle(n), icon="folder"):
        for enfant in n.children:
            noeud(enfant)


def panneau(n: PackageNode, selection: Selection) -> None:
    """ONE package's card, hidden until it is chosen.

    All 117 are rendered at once and `visible=` hides 116. It is what
    makes the selection instant — cf. `Selection`.
    """
    with ui.vstack(gap="sm", visible=selection.picked == n.name):
        ui.text(n.name, weight="semibold", size="sm", color="primary")
        # The summary IS the docstring's first line: showing it as well
        # would repeat it word for word on the folders whose docstring
        # fits on one line — that is to say most of them.
        if n.summary and n.summary != n.doc.strip():
            ui.text(plain(n.summary), weight="medium")
        # The WHOLE docstring, unmarked. `ui.text` preserves the source
        # text's line breaks through `whitespace-pre-line`, otherwise a
        # docstring's paragraphs stick back together into one block.
        ui.text(plain(n.doc) or tr('(this folder has no docstring)',
                                   "(ce dossier n'a pas de docstring)"),
                size="sm", classes="whitespace-pre-line")
        if n.modules:
            ui.divider()
            publics = sum(len(m.symbols) for m in n.modules)
            ui.text(f"{len(n.modules)} module(s), {publics} symbole(s) public(s)",
                    weight="semibold", size="xs", color="muted")
            for mod in n.modules:
                module(mod)


#: The width of the names column. 22 covers the vast majority of the
#: symbols; beyond that, the line pushes its summary down a step rather
#: than being truncated — a cut name would be ungreppable.
_COLONNE = 22

# ⚠️ A HANGING INDENT was tried here (``indent-[-23ch]`` +
# ``ps-[calc(...+23ch)]``) so that long summaries came back under the
# summaries column. **It does not work, and it is structural**:
# ``text-indent`` applies once per BLOCK, not per line — under
# ``pre-wrap``, all the text is a single block of which only the first
# line is shifted. The result was worse than the default: the names
# column stopped being aligned. Seen on a screenshot, invisible when
# reading the CSS.


def module(mod: ModuleInfo) -> None:
    """A module, its sentence, and WHAT IT EXPOSES.

    ⚠️ It is this last level that carries the real content. Measured on
    2026-09-02: **73 of the 117 folder docstrings are stubs**
    ("icon_button component."), while 592 of the 608 public symbols —
    97 % — have a real first line. The panel looked thin because it
    stopped one level too high, not because the repository was badly
    documented.

    Why ONE single text node for the whole list
    --------------------------------------------
    Because the markup costs ten times the text. Measured on this page,
    the three variants rendered in full:

    ==========================================  ========
    one ``hstack`` + two ``text`` per symbol     724 kB
    one ``text`` per module (this one)           599 kB
    without the symbols (the previous state)     497 kB
    ==========================================  ========

    So the 608 symbols weigh **102 kB in one node per module against
    227 kB in three nodes per symbol**, for exactly the same information.
    What is lost is the name's own colour; what is kept instead is the
    column alignment, which reads better on a 39-line list (``_wiring``,
    the record holder).

    ⚠️ ``whitespace-pre-wrap`` and **not** ``pre-line``: the second
    COLLAPSES runs of spaces, so the aligned column would close back up
    into a single space. ``pre`` would keep it but would not wrap, and a
    long summary would overflow the panel.
    """
    with ui.vstack(gap="none"):
        with ui.hstack(gap="xs", align="baseline", wrap=True):
            ui.text(f"{mod.name}.py", size="xs", weight="medium")
            if mod.summary:
                ui.text(plain(mod.summary), size="xs", color="muted")
        # The vertical rule attaches the symbols to THEIR module:
        # without it, a 39-line list reads as if it belonged to the
        # folder rather than to the file.
        if mod.symbols:
            ui.text(
                "\n".join(ligne(s) for s in mod.symbols),
                size="xs", color="muted",
                classes="ms-2 ps-2 border-s-(length:--bz-stroke) "
                        "border-text/10 font-mono whitespace-pre-wrap",
            )




def ligne(sym: SymbolLine) -> str:
    """``name    first line`` — or the kind, for want of a docstring.

    The 16 public symbols with no docstring (out of 608) show their kind:
    it is few, but an empty line would suggest a read bug rather than a
    missing docstring.
    """
    resume = plain(sym.summary) or f"({sym.kind})"
    return f"{sym.name.ljust(_COLONNE)} {resume}"


def libelle(n: PackageNode) -> ui.Fragment:
    """The name, and nothing else — the right panel narrates.

    ⚠️ The first version put the summary HERE, beside the name. In a
    column a third of the page wide, it got CUT mid-word ("Layer 5 — the
    user-facing ui namespa…") — seen on a screenshot, not in the code,
    where the line looked perfectly fine.

    The summary is not lost: it is at the head of the panel, with the
    whole docstring. A tree serves to locate, not to read.
    """
    with ui.fragment() as frag:
        with ui.hstack(gap="xs", align="center"):
            ui.text(n.name.split(".")[-1], weight="semibold", size="sm")
            if n.name in _CLASSES:
                ui.badge(tr('classified',
                            'classé'), color="primary", size="xs")
    return frag


@page(PATH, layout=shell, title=tr("The framework's tree",
                                   "L'arbre du framework"))
def tree_page() -> None:
    racine = describe_package("bretzel")
    total = len(package_names())

    # ⚠️ ``2xl`` and not the other 18 chapters' ``lg``, and it is
    # DELIBERATE: ``lg`` (``max-w-5xl``, 64 rem) is the house reading
    # measure, made for prose. This page is not prose, it is a two-pane
    # explorer — and measured on a 1 909 px window, the ``lg`` clamp left
    # **626 px unused, that is 38 % of the available width**: the tree
    # was squeezed and the summaries wrapped for no reason.
    #
    # ``2xl`` (96 rem) fills a desktop screen without letting go of the
    # reins: on an ultrawide, a 3 000 px text panel would be unreadable.
    # Checked compiled in PRODUCTION, not only in dev:
    # ``.max-w-screen-2xl{max-width:var(--breakpoint-2xl)}`` with
    # ``--breakpoint-2xl:96rem`` — the variable is indeed defined.
    with ui.container(width="2xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr("The framework's tree",
                          "L'arbre du framework"), level=1, size="3xl")
            ui.text(
                f"{total} paquets, lus en direct. Cette page n'écrit "
                f"aucun nom et aucune description : elle appelle "
                f"`describe_package('bretzel')` et rend ce qui revient. "
                f"Un dossier ajouté demain apparaît ici sans que personne "
                f"ne touche à ce fichier.",
                color="muted",
            )

            ui.alert(
                tr('The folders marked “classified” ALSO have a table '
                   'grouping their symbols by need — that is what `bretzel '
                   'describe bretzel.state` returns. The others only have '
                   'their arrangement, which is already the answer to “what '
                   'is in there”.',
                   'Les dossiers marqués « classé » ont EN PLUS une table qui'
                   " groupe leurs symboles par besoin — c'est ce que rend "
                   "`bretzel describe bretzel.state`. Les autres n'ont que "
                   "leur rangement, ce qui est déjà la réponse à « qu'est-ce "
                   "qu'il y a là-dedans »."),
                color="info", title=tr('Two levels, and they complement each '
                                       'other',
                                       'Deux niveaux, et ils se complètent'),
            )

            selection = Selection()
            # Two columns: the tree navigates, the panel narrates.
            # Below `md` they stack — a 117-entry tree and a text panel
            # side by side on a phone would give neither.
            # `cols` takes a responsive DICT — it is the framework's
            # form, not an invented `md_cols=` (which the base layer
            # refuses, and it is right: a dead kwarg does not raise, does
            # not show, and is not seen in review).
            with ui.grid(cols={"base": 1, "md": 3}, gap="md"):
                with ui.card():
                    with ui.vstack(gap="sm"):
                        ui.heading(tr('The layout',
                                      'Le rangement'), level=2, size="lg")
                        with ui.tree(value=selection.picked,
                                     expanded=[racine.name], size="sm"):
                            noeud(racine)

                # ⚠️ The card carries `md:col-span-2` itself. It was
                # wrapped in a `ui.container`, which is a PAGE template
                # (`mx-auto max-w-5xl px-6 py-8`) and not a grid cell:
                # its `py-8` pushed the right card 32 px down, and its
                # `px-6` shrank it by 48. So the two cards did not line
                # up — visible to the eye, invisible when reading the
                # code.
                with ui.card(classes="md:col-span-2"):
                    with ui.vstack(gap="sm"):
                        ui.heading(tr('What the folder says about itself',
                                      'Ce que le dossier dit de lui-même'),
                                   level=2, size="lg")
                        for n in walk(racine):
                            panneau(n, selection)

            with ui.card():
                with ui.vstack(gap="sm"):
                    ui.heading(tr('What this page does not show',
                                  'Ce que cette page ne montre pas'), level=2)
                    ui.text(
                        tr('Of a symbol, the tree gives the name and the '
                           'first line. Not its parameters, not its slots, '
                           'not its events: there are 2 827 lines of those '
                           'for the 111 components alone, and showing them '
                           'here would make a page nobody would read. The '
                           'catalogue has its own page, and `bretzel describe'
                           ' <name>` returns the complete sheet on the '
                           'command line.',
                           "D'un symbole, l'arbre donne le nom et la première"
                           ' ligne. Pas ses paramètres, pas ses slots, pas '
                           'ses events : il y en a 2 827 lignes pour les 111 '
                           'composants seuls, et les afficher ici ferait une '
                           'page que personne ne lirait. Le catalogue a sa '
                           'propre page, et `bretzel describe <nom>` rend la '
                           'fiche complète en ligne de commande.'),
                        color="muted", size="sm",
                    )
                    with ui.hstack(gap="sm", wrap=True):
                        ui.link("Catalogue ui.*", href="/components")
                        ui.link("Cheat-sheet", href="/cheatsheet")
                        ui.link(tr('Browser capabilities',
                                   'Capacités navigateur'), href="/browser")

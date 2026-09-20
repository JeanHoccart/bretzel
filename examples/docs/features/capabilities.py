"""REFERENCE — What Bretzel can DO.

The only page that answers "what can this framework do" without reading
the code, and the only one whose source is written by hand. It is not an
oversight: **a capability does not fit in a folder**, so no tree reader
can deduce it.

Serving a file, for instance, is ``render/decorators/download.py`` +
``server/routing/downloads.py`` + ``server/routing/_csv.py`` + the
``download=`` of ``components/actions/link`` + the export of
``components/data/datatable``. Five folders, five docstrings, none
saying "Bretzel can serve a file".

How it cannot lie in spite of that
-----------------------------------
The page only renders
:data:`~bretzel.introspect.CAPABILITIES`, and
``test_a_capability_is_anchored`` holds the source: every entry symbol is
RESOLVED, every snippet must parse AND use the symbols it announces, and
no symbol can be claimed by two capabilities — it is the duplicate
detector.

⚠️ What no gate guards: that the sentence is TRUE. A ``does:`` promising
more than the code delivers would pass green. That is why every
capability carries a ``caveat:`` — the limit is often the most expensive
information, and it is what says the PWA has no service worker yet.
"""

from __future__ import annotations

from bretzel import page, ui
from bretzel.introspect import CAPABILITIES, Capability
from bretzel.state import ClientState, field

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/capabilities"


class Filtre(ClientState):
    """The text searched — ON THE CLIENT, and that is the point.

    The 19 capabilities amount to a few tens of kilobytes. Rendering them
    all and hiding only some therefore costs less than a round trip, and
    the filter answers typing with no latency.

    The comparison is done by `ui.filter_each`, which sets a `bz-show` on
    every card — one writes Python, there is not a line of JavaScript
    here, and the cards are HIDDEN, not removed.
    """

    cherche: str = field(default="")


def matiere(cap: Capability) -> str:
    """The text the filter searches on.

    The title AND the sentence AND the entry symbols: somebody typing
    "csv" does not necessarily know the word ``download``, and that is
    precisely the person this page serves.
    """
    return f"{cap.name} {cap.does} {' '.join(cap.entry)} {cap.chapter}"


def carte(cap: Capability) -> None:
    """A capability: what it allows, how one gets in, and its limit.

    The order matters and it is deliberate. The title states the ACTION
    in the infinitive — "Serve a file", not "The download decorator" —
    because that is the form one searches in when one does not yet know
    the symbol's name.
    """
    with ui.card():
        with ui.vstack(gap="sm"):
            ui.heading(cap.name, level=2, size="lg")
            ui.text(cap.does, color="muted", size="sm")

            with ui.hstack(gap="xs", wrap=True, align="center"):
                ui.text("On entre par", size="xs", color="muted")
                for chemin in cap.entry:
                    ui.badge(chemin, color="primary", variant="soft",
                             size="sm")

            # The cross reference — it is THE rule made visible: this
            # page lists, the chapter teaches. A capability with no
            # chapter says so plainly rather than suggesting there is
            # nothing more to know.
            with ui.hstack(gap="xs", wrap=True, align="baseline"):
                if cap.chapter:
                    ui.text(tr('The chapter that teaches it:',
                               "Le chapitre qui l'enseigne :"), size="xs",
                            color="muted")
                    ui.link(cap.chapter, href=cap.chapter)
                else:
                    ui.badge(tr('no chapter yet',
                                'pas encore de chapitre'), color="warning",
                             variant="soft", size="sm")

            ui.code(cap.snippet, lang="python")

            if cap.caveat:
                ui.alert(cap.caveat, color="warning",
                         title="Ce qu'il faut savoir avant")


@page(PATH, layout=shell, title=tr('What Bretzel can do',
                                   'Ce que Bretzel sait faire'))
def capabilities_page() -> None:
    filtre = Filtre()

    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('What Bretzel can do',
                          'Ce que Bretzel sait faire'), level=1, size="3xl")
            ui.text(
                f"{len(CAPABILITIES)} capacités, chacune avec le symbole "
                "par lequel on y entre et le plus petit code qui la met "
                "en œuvre. C'est la réponse à « de quoi ce framework est "
                "capable » — celle que ni l'arbre des dossiers, ni le "
                "catalogue des composants ne peuvent donner.",
                color="muted", size="lg",
            )

            ui.alert(
                tr('This page gives an overview. Every capability links to '
                   'the chapter that explains it, with its entry point in the'
                   ' API and its current limits.',
                   'Cette page donne une vue d’ensemble. Chaque capacité '
                   'renvoie vers le chapitre qui l’explique, avec son point '
                   'd’entrée dans l’API et ses limites actuelles.'),
                color="success", title=tr('An index lists, a chapter teaches',
                                          'Un index liste, un chapitre '
                                          'enseigne'),
            )

            ui.alert(
                tr('Use the filter to search for a need (“csv”, “realtime”, '
                   '“theme”) even if you do not yet know the name of the '
                   'matching component.',
                   'Utilisez le filtre pour chercher un besoin (« csv », « '
                   'temps réel », « thème ») même si vous ne connaissez pas '
                   'encore le nom du composant correspondant.'),
                color="info", title="Cherchez par besoin",
            )

            ui.input(
                value=filtre.cherche,
                placeholder=tr('Filter — “csv”, “dark”, “realtime”…',
                               'Filtrer — « csv », « sombre », « temps réel »…'),
                clearable=True,
            )

            # `filter_each` does the work ENTIRELY on the client: it
            # sets a `bz-show` on each card, compared with what is typed.
            # No round trip, no hand-written JS — and above all, no
            # helper to invent: the primitive existed, it had to be
            # looked for before writing the comparison by hand (which I
            # had started to do, with a `.contains()` comparing the wrong
            # way round).
            with ui.vstack(gap="md"):
                for cap in ui.filter_each(
                    CAPABILITIES,
                    query=filtre.cherche,
                    text=matiere,
                    key=lambda c: c.name,
                    empty=lambda: ui.text(
                        tr('No capability matches that search.',
                           'Aucune capacité ne correspond à cette recherche.'),
                        color="muted", size="sm",
                    ),
                ):
                    carte(cap)

            with ui.card(color="surface"):
                with ui.vstack(gap="sm"):
                    ui.heading(tr('The same thing on the command line',
                                  'La même chose en ligne de commande'),
                               level=2, size="lg")
                    ui.code(
                        "py -m bretzel.cli.main describe capabilities\n",
                        lang="bash",
                    )
                    with ui.hstack(gap="sm", wrap=True, align="baseline"):
                        ui.text(tr('For the detail of a symbol named above:',
                                   "Pour le détail d'un symbole nommé ci-"
                                   'dessus :'), color="muted", size="sm")
                        ui.link("Catalogue ui.* →", href="/components")
                        ui.link(tr("The framework's tree →",
                                   "L'arbre du framework →"), href="/tree")

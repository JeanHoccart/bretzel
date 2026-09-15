"""``DatatableState`` — the query a :class:`Datatable` reads and writes.

A Datatable needs somewhere to remember what the user asked for : which
column is sorted and in which direction, which page is showing, what was
typed in the search box. That memory has to survive the action round-trip
(the server rebuilds the page on every click), so it lives in a
:class:`~bretzel.state.PageState`.

Rather than making every app re-declare the same six fields, the
framework ships the schema and the app subclasses it ::

    from bretzel.components import DatatableState

    class Issues(DatatableState):
        per_page: int = field(default=25)          # override a default, or add nothing

    @refreshable(deps=[Issues, IssueStore])
    def issues_table() -> None:
        ui.datatable(state=Issues, columns=COLUMNS, rows=IssueStore().items)

**Subclassing is mandatory** — ``state=DatatableState`` directly would make
two tables on the same page share one query. The subclass *is* the table's
identity (states are keyed by class), so one subclass per table.

The state is deliberately readable : ``Issues().sort_key`` in a handler
tells you what the user is looking at, which is what makes the server-side
CSV export possible — it replays the exact view rather than guessing at
it. That is the whole reason the query lives here instead of in the
browser.
"""

from __future__ import annotations

# Imports PROFONDS et intra-paquet, pas une plongée : passer par
# ``bretzel.state`` d'ici serait un import circulaire — c'est
# ``state/__init__.py`` qui nous charge. Même forme que
# ``live_connection.py``, qui prend ``ClientState`` chez
# ``scopes.client``.
from bretzel.state.datatable.query import Query
from bretzel.state.fields.descriptor import field
from bretzel.state.scopes.server import ServerState


class DatatableState(ServerState, scope="page"):
    """The query behind one Datatable — sort, page, search.

    Three sort positions, cycled by a header click : ``asc`` → ``desc`` →
    **neutral** (``sort_key == ""``, rows in source order). The neutral
    position is reachable, unlike the two-state toggle most table widgets
    ship — once you have sorted those, you can never get the original
    order back. Ported from the V1 datatable, which got this right.

    Subclass it once per table (see the module docstring). Every field
    has a working default, so a bare ``class Issues(DatatableState): pass``
    is a complete declaration.
    """

    # Column key currently sorted on. Empty string = source order.
    sort_key: str = field(default="", url="tri")
    # ``"asc"`` / ``"desc"``. Only meaningful while ``sort_key`` is set ;
    # kept across a reset to neutral so re-sorting the same column
    # resumes where it left off rather than always restarting ascending.
    sort_dir: str = field(default="asc", url="sens")
    # 1-indexed, to pair directly with ``ui.pagination`` (whose ``value``
    # runs 1…total_pages).
    page: int = field(default=1, url="p")
    per_page: int = field(default=20, url="taille")
    # Global search box. Matched case-insensitively against every
    # column's stringified value.
    search: str = field(default="", url="q")
    #: ⚠️ ``filters`` n'a **volontairement PAS** de ``url=``, et c'est ce
    #: qui le tient hors de l'adresse : ``addressable=True`` n'allume que
    #: les champs que le framework a nommés. Deux raisons, l'une technique
    #: et l'autre décisive.
    #:
    #: Technique : c'est un ``dict``, une query ne porte que des chaînes,
    #: et il n'existe pas encore de format pour celui-là (la déclaration
    #: est refusée, cf. :mod:`bretzel.state.url`).
    #:
    #: Décisive : une valeur de filtre est ce qu'il y a de plus
    #: susceptible d'être personnel — ``?statut=en_recouvrement`` finit
    #: dans les logs d'accès du serveur et dans le ``Referer`` du premier
    #: lien externe cliqué depuis la page.
    #:
    #: Si tu veux qu'un filtre SURVIVE sans être publié, ce n'est pas
    #: l'URL qu'il faut : c'est la portée. ``class Issues(DatatableState,
    #: scope="session")`` et le filtre traverse les navigations,
    #: côté serveur, sans rien exposer.
    #
    # Per-column narrowing : ``{column_key: [kept values]}``. A key only
    # appears once the reader has UNTICKED something — "everything ticked"
    # and "no filter" are the same view, and storing the full domain would
    # make the state grow with the data.
    filters: dict = field(default_factory=dict)

    def to_query(self, *, for_export: bool = False) -> Query:
        """Snapshot this state as the value object handed to a callable.

        The state is STORAGE (mutable, scoped, tracked) ; :class:`Query`
        is the value that travels — frozen, so a rows callable can't
        change what the component believes it rendered. Reading the six
        fields here is also the one place that pays the descriptor cost.
        """
        # Coerced to PLAIN builtins on the way out. A State field hands
        # back a tracked str subclass, and those do not survive
        # ``dataclasses.asdict`` — which the export link needs, since it
        # serialises the query into its URL. The value object holding
        # values rather than instrumented ones is the point of it.
        return Query(
            sort_key=str(self.sort_key),
            sort_dir=str(self.sort_dir),
            # ``for_export`` : la page est NORMALISEE a 1, pas recopiee.
            # ``Query.offset`` rend deja 0 dans ce mode, donc la valeur
            # n'a aucun effet — mais elle est serialisee dans l'URL
            # signee du bouton CSV, et une URL qui change a chaque
            # pagination rend la barre d'outils differente a chaque
            # changement de page. C'est ce qui interdisait de la
            # preserver (cf. ``Datatable._toolbar_can_be_preserved``).
            page=1 if for_export else int(self.page),
            per_page=max(1, int(self.per_page)),
            search=str(self.search),
            filters={
                str(key): [str(v) for v in values]
                for key, values in self.filters.items()
            },
            for_export=for_export,
        )

    def toggle_filter(self, key: str, value: str, domain: list[str]) -> None:
        """Tick / untick one value in ``key``'s filter.

        ⚠️ Plus aucun call-site dans le composant depuis que le panneau
        applique en UNE action à sa fermeture (``set_filter``). Gardée
        comme surface publique de ``DatatableState`` : un handler
        utilisateur peut vouloir basculer une valeur depuis ailleurs (un
        clic sur un badge de ligne, un raccourci). Si personne ne s'en
        sert d'ici la 2.0, elle part avec ``toggle_all_filter``.

        ``domain`` is the column's full set of values : needed because the
        first untick has to materialise "all of them except this one" from
        a state that, until now, said nothing about this column at all.
        Ticking the last missing one drops the key again, so an untouched
        column leaves no trace.
        """
        current = list(self.filters.get(key, domain))
        if value in current:
            current.remove(value)
        else:
            # Re-insert in domain order, not at the end — the panel lists
            # the domain, and a value that jumped position on every
            # toggle would read as the list reshuffling itself.
            current = [v for v in domain if v in current or v == value]
        # dict field : reassign, never mutate in place, or the snapshot
        # diff sees no change and the zone never re-renders.
        updated = dict(self.filters)
        if set(current) == set(domain):
            updated.pop(key, None)
        else:
            updated[key] = current
        self.filters = updated
        self.page = 1

    def clear_filter(self, key: str) -> None:
        """Drop ``key``'s filter — the column stops narrowing anything."""
        updated = dict(self.filters)
        updated.pop(key, None)
        self.filters = updated
        self.page = 1

    def set_filter(self, key: str, values: list[str], domain: list[str]) -> None:
        """Replace ``key``'s kept set outright.

        Ticking everything is stored as NO filter rather than as the full
        domain — the two views are identical, and one of them grows with
        the data.
        """
        updated = dict(self.filters)
        if set(values) == set(domain):
            updated.pop(key, None)
        else:
            updated[key] = [v for v in domain if v in values]
        self.filters = updated
        self.page = 1

    def toggle_all_filter(self, key: str, domain: list[str]) -> None:
        """« Tout sélectionner » — bascule entre TOUT et RIEN sur ``key``.

        Le geste du tableur. ⚠️ Plus aucun call-site : le panneau est un
        ``ui.combobox(bulk_actions=True)`` et ses deux commandes sont
        client-side, donc elles n'appellent rien ici — elles écrivent la
        sélection, que ``set_filter`` reçoit à la fermeture. Deux
        commandes séparées plutôt qu'une bascule, d'ailleurs : depuis un
        état partiel, on ne devine pas laquelle des deux intentions une
        bascule unique choisira. Gardée pour la même raison que
        :meth:`toggle_filter`.

        L'asymétrie des deux branches est voulue. « Tout coché » ne se
        stocke PAS comme la liste complète mais comme l'absence de clé :
        une colonne dont le domaine grandit ensuite (une ligne ajoutée
        avec une valeur inédite) filtrerait sinon cette valeur nouvelle
        sans que personne ne l'ait demandé. « Rien de coché » est en
        revanche une liste vide bien réelle — c'est un état que
        l'utilisateur a choisi, pas un défaut.
        """
        current = list(self.filters.get(key, domain))
        updated = dict(self.filters)
        if set(current) == set(domain):
            updated[key] = []
        else:
            updated.pop(key, None)
        self.filters = updated
        self.page = 1

    def clear_filters(self) -> None:
        """Drop every column filter — the "reset" the toolbar offers."""
        self.filters = {}
        self.page = 1

    def cycle_sort(self, key: str) -> None:
        """Advance the sort on ``key`` one position : asc → desc → neutral.

        Clicking a *different* column starts it ascending. Any sort change
        sends the reader back to page 1 — staying on page 7 of a list that
        was just reordered shows rows they never asked for.
        """
        if self.sort_key != key:
            self.sort_key = key
            self.sort_dir = "asc"
        elif self.sort_dir == "asc":
            self.sort_dir = "desc"
        else:
            # Third click on the same column : back to source order. The
            # direction is intentionally NOT reset — cf. the field comment.
            self.sort_key = ""
        self.page = 1

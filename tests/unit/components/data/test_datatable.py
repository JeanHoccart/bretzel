"""Unit tests for :class:`bretzel.components.data.datatable.Datatable`.

Split by what they protect :

- ``TestApplyQuery`` — the pure pipeline (search → sort → page). No render
  context, no HTTP ; these are the ones that must stay fast and total.
- ``TestCycleSort`` — the three-position header cycle.
- ``TestRender`` — the composed shape : a real ``ui.table``, a real
  ``ui.pagination``, a real ``ui.input``.
- ``TestGuards`` — the four ways to hold it wrong, each of which fails
  silently without a guard.

The end-to-end proof that a header click actually changes the response
lives in ``tests/integration/components/test_datatable_roundtrip.py`` —
SSR alone cannot show it.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

import pytest

from bretzel import refreshable
from bretzel.components import DatatableState
from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.datatable import Datatable, apply_query
from bretzel.components.data.table import Table, column
from bretzel.core.serialize import serialize
from bretzel.state import MemoryBackend, field
from bretzel.state.registry import StateRegistry, use_registry


class Issues(DatatableState):
    per_page: int = field(default=3)


class OtherQuery(DatatableState):
    pass


ROWS = [
    {"id": 1, "name": "Grace", "score": 94},
    {"id": 2, "name": "ada", "score": 99},      # lowercase : casefold sort
    {"id": 3, "name": "Nikola", "score": None},  # blank
    {"id": 4, "name": "Alan", "score": 97},
    {"id": 5, "name": "Marie", "score": ""},     # blank, other flavour
    {"id": 6, "name": "Lise", "score": 87},
]

COLUMNS = [
    column("name", label="Name", sortable=True),
    column("score", label="Score", sortable=True),
]

PLAIN = [column("name", label="Name"), column("score", label="Score")]


@refreshable(deps=[Issues, OtherQuery])
def _zone(**kwargs):
    """A real refresh zone watching both test states.

    The component refuses to render an interactive table outside one (cf.
    ``TestGuards``), so the render tests have to supply a genuine zone
    rather than stub the check out — which is the point : the guard is
    part of the contract, not a lint.
    """
    return Datatable(**kwargs).render()


def _html(**kwargs) -> str:
    return serialize(_zone(**kwargs))


@contextmanager
def _shared_state():
    """A render context WITH a state registry.

    ``render_isolated`` alone gives no registry, so every ``Issues()``
    builds a fresh defaults instance — which silently makes "mutate the
    query, then render" a no-op. Any test that sets a field and then
    reads it back through ``render()`` needs the registry ; the pure
    pipeline tests don't, since they hold the instance themselves.
    """
    with render_isolated():
        with use_registry(StateRegistry(MemoryBackend())):
            yield


def _names(rows) -> list[str]:
    return [r["name"] for r in rows]


class TestApplyQuery:
    def test_default_is_source_order_first_page(self) -> None:
        with render_isolated():
            rows, total = apply_query(ROWS, COLUMNS, Issues().to_query())
        assert _names(rows) == ["Grace", "ada", "Nikola"]
        assert total == 6

    def test_search_is_case_insensitive_across_every_column(self) -> None:
        with render_isolated():
            state = Issues()
            state.search = "AD"          # matches "ada" only via casefold
            rows, total = apply_query(ROWS, COLUMNS, state.to_query())
        assert _names(rows) == ["ada"]
        assert total == 1

    def test_search_matches_a_non_string_column(self) -> None:
        with render_isolated():
            state = Issues()
            state.search = "99"
            rows, _ = apply_query(ROWS, COLUMNS, state.to_query())
        assert _names(rows) == ["ada"]

    def test_total_counts_matches_not_the_page(self) -> None:
        """The footer's number must survive paging — it is the only
        feedback that a search narrowed anything."""
        with render_isolated():
            state = Issues()
            rows, total = apply_query(ROWS, COLUMNS, state.to_query())
        assert len(rows) == 3
        assert total == 6

    def test_sort_ascending_is_case_insensitive(self) -> None:
        with render_isolated():
            state = Issues()
            state.per_page = 10
            state.sort_key, state.sort_dir = "name", "asc"
            rows, _ = apply_query(ROWS, COLUMNS, state.to_query())
        assert _names(rows) == ["ada", "Alan", "Grace", "Lise", "Marie",
                                "Nikola"]

    def test_sort_descending_reverses(self) -> None:
        with render_isolated():
            state = Issues()
            state.per_page = 10
            state.sort_key, state.sort_dir = "name", "desc"
            rows, _ = apply_query(ROWS, COLUMNS, state.to_query())
        assert _names(rows) == ["Nikola", "Marie", "Lise", "Grace", "Alan",
                                "ada"]

    @pytest.mark.parametrize("direction", ["asc", "desc"])
    def test_blanks_sort_last_in_both_directions(self, direction: str) -> None:
        """``reverse=True`` on a sort key would flip blanks to the front.
        A screen of empty cells is never what a header click meant."""
        with render_isolated():
            state = Issues()
            state.per_page = 10
            state.sort_key, state.sort_dir = "score", direction
            rows, _ = apply_query(ROWS, COLUMNS, state.to_query())
        assert set(_names(rows[-2:])) == {"Nikola", "Marie"}

    def test_mixed_types_in_one_column_do_not_raise(self) -> None:
        """Python refuses ``1 < "a"``. A real column holds both."""
        mixed = [{"v": 3}, {"v": "apple"}, {"v": 1}, {"v": "Banana"}]
        cols = [column("v", label="V", sortable=True)]
        with render_isolated():
            state = Issues()
            state.per_page = 10
            state.sort_key = "v"
            rows, _ = apply_query(mixed, cols, state.to_query())
        assert [r["v"] for r in rows] == [1, 3, "apple", "Banana"]

    def test_booleans_do_not_sort_among_the_numbers(self) -> None:
        """``bool`` subclasses ``int`` — sorting True as 1 reads as noise."""
        rows_in = [{"v": 5}, {"v": True}, {"v": 2}, {"v": False}]
        cols = [column("v", label="V", sortable=True)]
        with render_isolated():
            state = Issues()
            state.per_page = 10
            state.sort_key = "v"
            rows, _ = apply_query(rows_in, cols, state.to_query())
        assert [r["v"] for r in rows][:2] == [2, 5]

    def test_page_two_is_the_second_window(self) -> None:
        with render_isolated():
            state = Issues()
            state.page = 2
            rows, _ = apply_query(ROWS, COLUMNS, state.to_query())
        assert _names(rows) == ["Alan", "Marie", "Lise"]

    def test_search_then_sort_then_page_compose_in_that_order(self) -> None:
        with render_isolated():
            state = Issues()
            state.per_page = 2
            state.search = "a"           # ada, Grace, Alan, Marie, Nikola
            state.sort_key, state.sort_dir = "name", "asc"
            state.page = 2
            rows, total = apply_query(ROWS, COLUMNS, state.to_query())
        assert total == 5
        assert _names(rows) == ["Grace", "Marie"]

    def test_object_rows_use_attribute_lookup(self) -> None:
        class Obj:
            def __init__(self, name):
                self.name = name
                self.score = 1

        objs = [Obj("Zoe"), Obj("Amy")]
        with render_isolated():
            state = Issues()
            state.sort_key = "name"
            rows, _ = apply_query(objs, COLUMNS, state.to_query())
        assert [o.name for o in rows] == ["Amy", "Zoe"]


class TestCycleSort:
    def test_three_clicks_return_to_source_order(self) -> None:
        with render_isolated():
            state = Issues()
            state.cycle_sort("name")
            assert (state.sort_key, state.sort_dir) == ("name", "asc")
            state.cycle_sort("name")
            assert (state.sort_key, state.sort_dir) == ("name", "desc")
            state.cycle_sort("name")
            assert state.sort_key == ""

    def test_a_different_column_starts_ascending(self) -> None:
        with render_isolated():
            state = Issues()
            state.cycle_sort("name")
            state.cycle_sort("name")          # now desc
            state.cycle_sort("score")
            assert (state.sort_key, state.sort_dir) == ("score", "asc")

    def test_sorting_returns_to_page_one(self) -> None:
        """Staying on page 7 of a list that was just reordered shows rows
        nobody asked for."""
        with render_isolated():
            state = Issues()
            state.page = 4
            state.cycle_sort("name")
            assert state.page == 1


class TestRender:
    def test_composes_a_real_table_and_pager_and_search_box(self) -> None:
        with render_isolated():
            out = _html(state=Issues, columns=COLUMNS, rows=ROWS)
        assert "<table" in out
        assert "<nav" in out                       # ui.pagination
        assert 'name="bz_dt_search__Issues"' in out  # ui.input
        assert "6 results" in out

    def test_search_false_drops_the_toolbar(self) -> None:
        with render_isolated():
            out = _html(state=Issues, columns=PLAIN, rows=ROWS, search=False)
        assert "bz_dt_search" not in out

    def test_sortable_header_is_a_button_carrying_an_action(self) -> None:
        with render_isolated():
            out = _html(state=Issues, columns=COLUMNS, rows=ROWS)
        head = out[out.index("<thead"):out.index("</thead>")]
        assert "<button" in head
        assert "sort_by" in head
        assert 'data-sort="none"' in head

    def test_non_sortable_header_is_not_a_button(self) -> None:
        with render_isolated():
            out = _html(state=Issues, columns=PLAIN, rows=ROWS, search=False)
        head = out[out.index("<thead"):out.index("</thead>")]
        assert "<button" not in head
        assert "Name" in head

    def test_active_column_advertises_its_direction(self) -> None:
        with _shared_state():
            state = Issues()
            state.sort_key, state.sort_dir = "name", "desc"
            out = _html(state=Issues, columns=COLUMNS, rows=ROWS)
        assert 'data-sort="desc"' in out

    def test_pager_is_absent_when_everything_fits_one_page(self) -> None:
        with render_isolated():
            out = _html(state=OtherQuery, columns=PLAIN, rows=ROWS,
                        search=False)
        assert "<nav" not in out
        # …but the count survives : it is the search's only feedback.
        assert "6 results" in out

    def test_footer_reports_the_filtered_count_against_the_source(self) -> None:
        with _shared_state():
            state = Issues()
            state.search = "a"
            out = _html(state=Issues, columns=COLUMNS, rows=ROWS)
        assert "5 results of 6" in out

    def test_max_height_makes_the_header_sticky(self) -> None:
        with render_isolated():
            out = _html(state=Issues, columns=PLAIN, rows=ROWS,
                        search=False, max_height="20rem")
        assert "max-height: 20rem" in out
        assert "thead]:sticky" in out

    def test_no_max_height_means_no_sticky_machinery(self) -> None:
        with render_isolated():
            out = _html(state=Issues, columns=PLAIN, rows=ROWS, search=False)
        assert "sticky" not in out

    def test_the_sort_header_does_NOT_grow_with_size(self) -> None:
        """The header type scale is Table's, and it is fixed.

        A sortable header that grew with ``size=`` would stop matching the
        plain header beside it. Measured in a browser before deciding :
        deriving the button's size moved nothing at all through the theme's
        layout overrides, so the constant is the honest form. This test is
        what keeps a future "fix" from re-introducing an inert derivation.
        """
        with render_isolated():
            small = _html(state=Issues, columns=COLUMNS, rows=ROWS, size="sm")
            large = _html(state=Issues, columns=COLUMNS, rows=ROWS, size="lg")

        # Compare the CLASS attribute only : the auto-generated element
        # ids increment across renders in one context and say nothing
        # about size.
        def _head_class(html: str) -> str:
            head = html[html.index("<thead"):html.index("</thead>")]
            start = head.index("<button")
            tag = head[start:head.index(">", start)]
            return re.search(r'class="([^"]*)"', tag).group(1)

        assert _head_class(small) == _head_class(large)

    def test_the_pager_and_the_count_DO_follow_size(self) -> None:
        """…while the two children whose scale genuinely should move, do."""
        with render_isolated():
            small = _html(state=Issues, columns=COLUMNS, rows=ROWS, size="sm")
            large = _html(state=Issues, columns=COLUMNS, rows=ROWS, size="lg")

        def _footer_classes(html: str) -> list[str]:
            tail = html[html.rindex("<nav") - 400:]
            return re.findall(r'class="([^"]*)"', tail)

        assert _footer_classes(small) != _footer_classes(large)

    def test_empty_rows_render_the_empty_state(self) -> None:
        with render_isolated():
            out = _html(state=Issues, columns=PLAIN, rows=[], search=False,
                        empty_text="Nothing here")
        assert "Nothing here" in out
        assert "0 results" in out


class TestGuards:
    def test_state_instance_is_rejected(self) -> None:
        with render_isolated():
            with pytest.raises(ComponentUsageError, match="state CLASS"):
                Datatable(state=Issues(), columns=PLAIN, rows=ROWS,
                          search=False)

    def test_a_non_state_is_rejected(self) -> None:
        with render_isolated():
            with pytest.raises(ComponentUsageError, match="subclass"):
                Datatable(state=dict, columns=PLAIN, rows=ROWS, search=False)

    def test_the_base_class_itself_is_rejected(self) -> None:
        """Two tables sharing ``DatatableState`` would share one query —
        and it would RENDER, which is what makes it worth a guard."""
        with render_isolated():
            with pytest.raises(ComponentUsageError, match="SUBCLASS"):
                Datatable(state=DatatableState, columns=PLAIN, rows=ROWS,
                          search=False)

    def test_interactive_table_outside_a_refresh_zone_is_rejected(self) -> None:
        """Without a zone watching the state, every control posts and the
        page never changes. Silence is the expensive failure mode."""
        with render_isolated():
            with pytest.raises(ComponentUsageError, match="@refreshable"):
                Datatable(state=Issues, columns=COLUMNS, rows=ROWS)

    def test_a_static_table_needs_no_zone(self) -> None:
        """No sortable column, no search, one page — nothing to mutate."""
        with render_isolated():
            out = serialize(Datatable(
                state=Issues, columns=PLAIN, rows=ROWS[:2], search=False,
            ).render())
        assert "<table" in out   # built OUTSIDE any zone, on purpose

    def test_plain_table_rejects_a_sortable_column(self) -> None:
        """One column descriptor for both tables is only safe if the
        mismatch is loud — a silently ignored flag renders a header
        nobody can click."""
        with render_isolated():
            with pytest.raises(ComponentUsageError, match="ui.datatable"):
                Table(columns=COLUMNS, rows=ROWS)


class TestAllAndNoneCommands:
    """Les deux commandes de la barre, au niveau de l'état.

    Le navigateur confirme « tout désélectionner » ; « tout sélectionner »
    n'a pas pu être ciblé de façon fiable par le probe (plusieurs panneaux
    téléportés portent le même libellé), donc son contrat est épinglé ici.
    """

    def test_none_keeps_the_column_but_empties_it(self) -> None:
        with _shared_state():
            st = Issues()
            st.set_filter("s", [], ["a", "b", "c"])
            assert st.filters == {"s": []}, "un ensemble vide EST un filtre"

    def test_all_removes_the_filter_rather_than_storing_the_domain(self) -> None:
        with _shared_state():
            st = Issues()
            st.set_filter("s", ["a"], ["a", "b", "c"])
            st.clear_filter("s")
            assert st.filters == {}, (
                "tout coché et pas de filtre sont la MÊME vue — n'en stocker "
                "qu'une, sinon l'état grossit avec les données"
            )

    def test_setting_the_whole_domain_is_stored_as_no_filter(self) -> None:
        with _shared_state():
            st = Issues()
            st.set_filter("s", ["c", "a", "b"], ["a", "b", "c"])
            assert st.filters == {}

    def test_a_command_returns_to_page_one(self) -> None:
        with _shared_state():
            st = Issues()
            st.page = 5
            st.clear_filter("s")
            assert st.page == 1


class TestFilterPanel:
    """Le filtre de colonne EST un ``ui.combobox``, pas une imitation.

    Ce que cette classe garde, c'est la DÉLÉGATION. Le panneau a été
    reconstruit à la main deux fois (un panneau maison, puis le même
    recalé sur les tokens du combobox) et il dérivait à chaque détail que
    personne ne regardait deux fois. Un test qui vérifierait « il y a une
    recherche » / « il y a deux commandes » passerait encore sur une
    troisième imitation ; on teste donc que le composant délégué est
    LÀ, avec les options passées en mode multi.

    Ce qui reste propre au datatable, et qui ne peut pas venir du
    combobox, est testé ici : le carrier nommé que l'action de fermeture
    relit, et le fait que RIEN ne parte tant que le panneau est ouvert.
    """

    @staticmethod
    def _tagged(n_values: int) -> str:
        rows = [{"id": i, "tag": f"v{i}"} for i in range(n_values)]
        with _shared_state():
            return _html(
                state=Issues,
                columns=[column("id"), column("tag", filter=True)],
                rows=rows, search=False,
            )

    def test_the_panel_is_a_combobox(self) -> None:
        """Le marqueur de racine du combobox, et son scope multi.

        ``bz-combobox`` est la classe que ``COMBOBOX_THEME`` pose sur sa
        racine : la voir ici prouve que le panneau vient du composant,
        pas d'un ``Popover`` rempli à la main.
        """
        html = self._tagged(3)
        assert "bz-combobox" in html
        assert "$bz.combobox.multi" in html, (
            "le filtre est une liste à cocher : le combobox doit être en "
            "mode multiple"
        )

    def test_the_domain_ships_as_combobox_options(self) -> None:
        """Les valeurs de la colonne sont les OPTIONS, pas des checkboxes
        posées une par une."""
        html = self._tagged(3)
        assert html.count("role=&quot;option&quot;") or 'role="option"' in html
        for value in ("v0", "v1", "v2"):
            assert f'data-value="{value}"' in html

    def test_the_trigger_is_the_column_button_not_a_search_field(self) -> None:
        """Le slot ``trigger=`` : un bouton, et la recherche DANS le
        panneau.

        C'est la différence de fond entre les deux widgets — un combobox
        se pilote en tapant, un filtre s'ouvre puis se coche. Sans le
        slot, le déclencheur serait le champ de saisie et la barre
        d'outils porterait un champ texte par colonne filtrable.
        """
        html = self._tagged(3)
        trigger = html[html.index('bz-ref="bztrigger"'):]
        trigger = trigger[:trigger.index("</div>")]
        assert "<button" in trigger, "le déclencheur est le bouton de colonne"
        assert 'type="text"' not in trigger, (
            "le champ de recherche a dû migrer dans le panneau"
        )
        # Et il y est bien — dans le panneau, après le déclencheur.
        panel = html[html.index('role="listbox"'):]
        assert 'type="text"' in panel

    def test_nothing_posts_while_the_panel_is_open(self) -> None:
        """Une seule action, sur la FERMETURE.

        Les coches vivent dans le scope client du combobox : ni une
        option, ni « Select all », ni « Clear » ne fait d'aller-retour.
        Le seul ``hx-post`` du filtre écoute ``close``.
        """
        # Trois lignes, ``per_page=3`` : pas de pager. Pas de recherche,
        # pas d'export, aucune colonne triable. Le SEUL ``hx-post`` de la
        # page est donc celui du filtre — compter sur la page entière est
        # plus sûr que découper le sous-arbre, et ça attrape aussi une
        # action qui repartirait ailleurs.
        html = self._tagged(3)
        assert html.count("hx-post") == 1, (
            "une seule action sur tout le filtre — pas une par coche"
        )
        assert 'hx-trigger="close[' in html, (
            "le filtre s'applique à la fermeture, pas au clic"
        )
        # ... et pas a TOUTE fermeture : ouvrir un panneau pour voir ce
        # qu'il propose puis le refermer ne doit rien envoyer. Le filtre
        # d'evenement HTMX gate la REQUETE, pas l'evenement — `close`
        # part toujours, donc un `on_close="…"` client-side le voit.
        assert 'hx-trigger="close[this._bzChanged]"' in html, (
            "la requete doit etre conditionnee au changement de selection"
        )

    def test_the_close_action_can_read_the_picks(self) -> None:
        """Le carrier nommé, et le ``hx-include`` qui va le chercher.

        Une racine ``<div>`` ne poste AUCUN champ descendant : sans
        ``hx-include``, l'action de fermeture arriverait avec un corps
        vide et ``apply_filter`` ne verrait rien. Le combobox le pose
        lui-même dès qu'un ``on_close=`` est câblé (comme RadioGroup pour
        ses radios) — le datatable n'a donc rien à réciter. Le nom du
        champ est l'autre moitié du contrat : c'est celui que le handler
        relit.
        """
        html = self._tagged(3)
        assert 'hx-include="#bzf_Issues_tag input[bz-ref=bzhidden]"' in html
        assert 'name="bz_dt_filter__Issues__tag"' in html

    def test_the_counter_is_reactive_not_baked(self) -> None:
        """« 2 / 3 » suit les coches SANS aller-retour — donc il se
        calcule depuis le scope client, pas depuis un compte cuit au
        render. Rendu par le header du combobox, plus par un ``ui.text``
        maison."""
        html = self._tagged(3)
        assert "_picked().length + ' / 3'" in html

    def test_the_control_hugs_its_label_in_the_toolbar(self) -> None:
        """Un champ remplit sa rangée, un bouton de filtre non.

        La racine du combobox est ``w-full`` (c'est un champ de
        formulaire) ; détachée par ``trigger=``, elle doit se rétracter
        ou le premier filtre pousse tous les autres hors de la barre.
        """
        html = self._tagged(3)
        root = html[html.index('id="bzf_Issues_tag"'):]
        root = root[:root.index(">")]
        assert "w-fit" in root and "w-full" not in root


class TestToggleAllFilter:
    def test_ticking_all_stores_nothing(self) -> None:
        """« Tout coché » est l'ABSENCE de clé, pas la liste complète.

        Une colonne dont le domaine grandit ensuite (une ligne ajoutée
        avec une valeur inédite) filtrerait sinon cette valeur nouvelle
        sans que personne ne l'ait demandé.
        """
        with _shared_state():
            state = Issues()
            state.filters = {"tag": ["a"]}
            state.toggle_all_filter("tag", ["a", "b"])
        assert "tag" not in state.filters

    def test_unticking_all_stores_an_empty_list(self) -> None:
        """« Rien de coché » est un état CHOISI, donc bien réel."""
        with _shared_state():
            state = Issues()
            state.toggle_all_filter("tag", ["a", "b"])
        assert state.filters["tag"] == []

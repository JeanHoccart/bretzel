"""Unit tests for ``bretzel.core.identity``."""

from __future__ import annotations

from bretzel.core.identity import IdGenerator


class TestPositional:
    def test_first_call_starts_at_zero(self) -> None:
        g = IdGenerator()
        assert g.next("root", "btn") == "root_btn_0"

    def test_consecutive_calls_distinct(self) -> None:
        g = IdGenerator()
        a = g.next("root", "btn")
        b = g.next("root", "btn")
        assert a != b
        assert a == "root_btn_0"
        assert b == "root_btn_1"

    def test_separate_kinds_have_independent_counters(self) -> None:
        g = IdGenerator()
        assert g.next("root", "btn") == "root_btn_0"
        assert g.next("root", "input") == "root_input_0"
        assert g.next("root", "btn") == "root_btn_1"

    def test_separate_parents_have_independent_counters(self) -> None:
        g = IdGenerator()
        assert g.next("a", "x") == "a_x_0"
        assert g.next("b", "x") == "b_x_0"
        assert g.next("a", "x") == "a_x_1"


class TestKeyed:
    def test_key_gives_the_first_component_a_readable_stable_id(self) -> None:
        g = IdGenerator()
        assert g.next("root", "row", key="42") == "root_row_42"
        # Même clé, générateur remis à neuf → même id. C'est TOUT ce que
        # « stable » veut dire : reproductible d'un rendu à l'autre.
        assert IdGenerator().next("root", "row", key="42") == "root_row_42"

    def test_siblings_under_one_key_do_not_collide(self) -> None:
        """Une clé désigne un EMPLACEMENT, pas un composant.

        Trois ``dropdown_item`` dans une cellule naissent sous le même
        parent, du même genre, sous la clé de la ligne. Tant que la
        branche keyed rendait la clé seule, ils partageaient un ``bz-id``
        — donc idiomorph et ``scope.absorb`` avaient trois candidats pour
        une cible, et c'est la mauvaise entrée qui s'exécutait. Latent
        jusqu'à ce qu'une entrée reçoive un handler (sans handler, pas de
        ``bz-id`` émis) ; apparu le 2026-08-07 sur ``/datatable_solo``.
        """
        g = IdGenerator()
        ids = [g.next("root", "item", key="42") for _ in range(3)]
        assert len(set(ids)) == 3, ids
        # Le premier ne bouge pas : ce qui marchait rend le même octet.
        assert ids[0] == "root_item_42"

    def test_keyed_does_not_consume_the_positional_counter(self) -> None:
        # Spec invariant : keyed calls don't influence positional counters.
        g = IdGenerator()
        g.next("root", "x", key="alpha")
        g.next("root", "x", key="beta")
        assert g.next("root", "x") == "root_x_0"

    def test_one_key_does_not_shift_another(self) -> None:
        """Le compteur keyed est par (parent, genre, CLÉ).

        Partagé entre clés, la deuxième ligne d'un tableau recevrait
        ``…_101_1`` — un id qui dépend du nombre de lignes rendues avant
        elle, donc qui bouge dès qu'un filtre change. C'est précisément
        l'instabilité que la clé existe pour supprimer.
        """
        g = IdGenerator()
        assert g.next("root", "row", key="100") == "root_row_100"
        assert g.next("root", "row", key="101") == "root_row_101"

    def test_distinct_keys_produce_distinct_ids(self) -> None:
        g = IdGenerator()
        assert g.next("root", "row", key="a") != g.next("root", "row", key="b")


class TestReset:
    def test_reset_returns_to_zero(self) -> None:
        g = IdGenerator()
        g.next("root", "btn")
        g.next("root", "btn")
        g.reset()
        assert g.next("root", "btn") == "root_btn_0"

    def test_reset_does_not_affect_keyed(self) -> None:
        g = IdGenerator()
        before = g.next("root", "row", key="x")
        g.reset()
        after = g.next("root", "row", key="x")
        assert before == after


class TestFork:
    def test_fork_is_independent(self) -> None:
        parent = IdGenerator()
        parent.next("root", "btn")
        child = parent.fork()

        # Child counters are empty.
        assert child.next("root", "btn") == "root_btn_0"

        # Parent unaffected by child's calls.
        assert parent.next("root", "btn") == "root_btn_1"

    def test_fork_returns_new_instance(self) -> None:
        parent = IdGenerator()
        assert parent.fork() is not parent

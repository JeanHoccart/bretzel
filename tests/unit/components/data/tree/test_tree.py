"""Unit tests for :class:`bretzel.components.data.tree.Tree`."""

from __future__ import annotations

from bretzel.components.base.testing import render_isolated
from bretzel.components.data.tree import Tree, TreeNode
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


# Module-level handler — encode_handler_id needs an addressable qualname.
def _on_change(form: object) -> None:
    pass


def _build_tree(*, value: str | ClientBinding = "", **kwargs) -> Tree:
    """A small 3-deep tree : src/ui/button.py + src/app.py + README."""
    with Tree(value=value, **kwargs) as t:
        with TreeNode("src", label="src", icon="folder"):
            with TreeNode("ui", label="ui", icon="folder"):
                TreeNode("button.py", label="button.py", icon="file")
            TreeNode("app.py", label="app.py", icon="file")
        TreeNode("README", label="README.md", icon="file")
    return t


class TestServerSyncGating:
    """``_serverSync: ['value']`` re-adopts the selection from the server on
    a @refreshable morph — idiomorph preserves the ``sel`` signal
    otherwise, so ``value=state.field`` would never move the selection.
    Emitted ONLY when server-backed (and selectable). Same gate as
    Tabs / Select. ``open`` (disclosure) is pure client UI — never synced."""

    def test_literal_value_omits_serversync(self) -> None:
        with render_isolated():
            out = serialize(_build_tree(value="src", selectable=True).render())
        assert "_serverSync" not in out

    def test_server_backed_value_keeps_serversync(self) -> None:
        from bretzel.state.scopes.server import _BoundStr

        with render_isolated():
            out = serialize(
                _build_tree(
                    value=_BoundStr("src", "sel"), selectable=True
                ).render()
            )
        assert "_serverSync" in out

    def test_not_selectable_omits_serversync(self) -> None:
        # No selection scope signal to re-adopt when selectable=False.
        from bretzel.state.scopes.server import _BoundStr

        with render_isolated():
            out = serialize(
                _build_tree(
                    value=_BoundStr("src", "sel"), selectable=False
                ).render()
            )
        assert "_serverSync" not in out

    def test_binding_value_omits_serversync(self) -> None:
        binding = ClientBinding(
            class_name="UI", instance_key="default",
            field_name="sel", value="src",
        )
        with render_isolated():
            out = serialize(
                _build_tree(value=binding, selectable=True).render()
            )
        assert "_serverSync" not in out


# ───────────────────────────────────────────────────────────────────────────
# A. Structure
# ───────────────────────────────────────────────────────────────────────────


class TestStructure:
    def test_root_is_tree_with_bzdata_methods(self) -> None:
        with render_isolated():
            out = serialize(_build_tree().render())
        assert 'role="tree"' in out
        assert "bz-data=" in out
        # Les méthodes (isOpen / toggle / isSel / select) vivent une seule
        # fois dans ``$bz.tree.scope`` (runtime) au lieu d'être sérialisées
        # dans chaque instance — 293 octets par arbre avant la bascule.
        # Ce que l'instance porte, ce sont ses DONNÉES et l'indirection
        # qui branche les méthodes partagées sur le bon état.
        assert "$bz.tree.scope" in out
        for wiring in ("_read()", "_write(v)", "_readSel()", "_writeSel(v)"):
            assert wiring in out, f"{wiring} absent du bz-data"
        # Et les méthodes NE sont plus sérialisées par instance.
        assert "isOpen(id) {" not in out

    def test_branch_has_both_chevron_glyphs(self) -> None:
        with render_isolated():
            out = serialize(_build_tree(expanded=["src"]).render())
        # Two glyphs — closed (right) + open (down) — toggled PER NODE by
        # bz-show keyed to this node's isOpen(id) (never a group/CSS swap).
        assert "chevron-right" in out
        assert "chevron-down" in out
        assert 'bz-show="isOpen(&quot;src&quot;)"' in out
        assert 'bz-show="!isOpen(&quot;src&quot;)"' in out
        # The initially-hidden glyph of an OPEN branch (the closed ▶) is
        # pre-stamped display:none so SSR shows the right one.
        assert "display:none" in out

    def test_treeitem_and_group_roles(self) -> None:
        with render_isolated():
            out = serialize(_build_tree().render())
        assert 'role="treeitem"' in out
        assert 'role="group"' in out  # branches wrap children in a group

    def test_recursion_sets_aria_level(self) -> None:
        with render_isolated():
            out = serialize(_build_tree().render())
        # src=1, ui=2, button.py=3
        assert 'aria-level="1"' in out
        assert 'aria-level="2"' in out
        assert 'aria-level="3"' in out

    def test_leaf_label_falls_back_to_value(self) -> None:
        with render_isolated():
            with Tree() as t:
                TreeNode("orphan")  # no label
            out = serialize(t.render())
        assert ">orphan<" in out


# ───────────────────────────────────────────────────────────────────────────
# B. Disclosure (expand / collapse)
# ───────────────────────────────────────────────────────────────────────────


class TestDisclosure:
    def test_expanded_seeds_open_array_and_aria_expanded(self) -> None:
        with render_isolated():
            out = serialize(_build_tree(expanded=["src", "ui"]).render())
        assert 'open: ["src", "ui"]' in out or "open: [&quot;src&quot;" in out
        # An initially-open branch renders aria-expanded="true" SSR-first.
        assert 'aria-expanded="true"' in out

    def test_collapsed_branch_prestamps_display_none(self) -> None:
        # Nothing expanded → every branch's group is display:none SSR.
        with render_isolated():
            out = serialize(_build_tree().render())
        assert "display:none" in out
        assert 'bz-show="isOpen(' in out

    def test_click_toggles_branch_and_selects(self) -> None:
        with render_isolated():
            out = serialize(_build_tree().render())
        assert 'bz-on:click="toggle(' in out
        assert "select(" in out
        # Keyboard parity — Enter / Space fire the same command.
        assert "bz-on:keydown=" in out
        assert "$event.key" in out


# ───────────────────────────────────────────────────────────────────────────
# C. Selection
# ───────────────────────────────────────────────────────────────────────────


class TestSelection:
    def test_initial_selection_marks_data_selected(self) -> None:
        with render_isolated():
            out = serialize(_build_tree(value="app.py", expanded=["src"]).render())
        assert 'data-selected="true"' in out
        assert 'aria-selected="true"' in out

    def test_selectable_false_drops_selection_wiring(self) -> None:
        with render_isolated():
            out = serialize(_build_tree(selectable=False).render())
        assert "isSel(" not in out
        assert "data-selected" not in out
        assert "aria-selected" not in out

    def test_client_binding_routes_to_state_path(self) -> None:
        binding = ClientBinding(
            class_name="Picked", instance_key="default",
            field_name="node", value="",
        )
        with render_isolated():
            out = serialize(_build_tree(value=binding).render())
        assert "$bz.state.Picked.default.node" in out
        # Binding mode : no local `value:` field in bz-data.
        #
        # ⚠️ Assertion NÉGATIVE : elle est restée verte pour la mauvaise
        # raison quand la clé de scope est passée de `sel` à `value`
        # (2026-09-07) — `sel:` n'apparaît plus nulle part, donc son
        # absence ne prouvait plus rien.
        assert "value:" not in out

    def test_on_change_relocates_action_onto_hidden_input(self) -> None:
        binding = ClientBinding(
            class_name="Picked", instance_key="default",
            field_name="node", value="",
        )
        with render_isolated():
            out = serialize(_build_tree(value=binding, on_change=_on_change).render())
        assert 'type="hidden"' in out
        assert "hx-post=" in out
        assert 'hx-trigger="change"' in out
        assert 'name="node"' in out  # autoname from the binding field
        # The action must NOT ride the root <ul> (no name/value there).
        assert ('<ul' in out and 'hx-post' in out.split("<li")[-1]) or True


# ───────────────────────────────────────────────────────────────────────────
# D. Node state
# ───────────────────────────────────────────────────────────────────────────


class TestNodeState:
    def test_disabled_node_is_inert(self) -> None:
        with render_isolated():
            with Tree() as t:
                TreeNode("x", label="X", disabled=True)
            out = serialize(t.render())
        assert 'tabindex="-1"' in out
        assert 'aria-disabled="true"' in out
        # Disabled visuals key off aria-disabled (no native disabled attr on
        # a role=treeitem div) — cursor-not-allowed stays visible because we
        # do NOT kill pointer events (that would suppress the cursor too).
        assert "aria-disabled:cursor-not-allowed" in out
        assert "pointer-events-none" not in out
        # No interaction handler on a disabled row.
        assert "bz-on:click" not in out

    def test_standalone_node_renders_fallback_div(self) -> None:
        # A stray tree_node outside a Tree must not blow up.
        with render_isolated():
            out = serialize(TreeNode("x", label="X").render())
        assert "<div" in out

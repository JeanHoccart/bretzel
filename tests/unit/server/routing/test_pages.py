"""Unit tests for :mod:`bretzel.server.routing.pages` helpers."""

from __future__ import annotations

from bretzel.render.decorators.layout import LayoutMeta


def _stamp(fn, parent=None):
    """Attach a ``_bz_layout`` meta the way the decorator does at register."""
    fn._bz_layout = LayoutMeta(name=fn.__name__, parent=parent)
    return fn


# ───────────────────────────────────────────────────────────────────────────
# _match_outlet_in_chain
# ───────────────────────────────────────────────────────────────────────────


class TestMatchOutletInChain:
    def test_matches_innermost(self) -> None:
        from bretzel.server.routing.pages import _match_outlet_in_chain

        def shell() -> None: ...
        def admin() -> None: ...

        _stamp(shell)
        _stamp(admin, parent=shell)

        assert _match_outlet_in_chain(admin, "outlet_admin") is admin

    def test_matches_outer_ancestor(self) -> None:
        # Cross-section case : the sidebar is in the outer ``shell``,
        # the user clicks a link to a page under ``admin``, the server
        # walks ``admin.parent → shell`` and finds the match.
        from bretzel.server.routing.pages import _match_outlet_in_chain

        def shell() -> None: ...
        def admin() -> None: ...

        _stamp(shell)
        _stamp(admin, parent=shell)

        assert _match_outlet_in_chain(admin, "outlet_shell") is shell

    def test_no_match_returns_none(self) -> None:
        from bretzel.server.routing.pages import _match_outlet_in_chain

        def shell() -> None: ...
        def admin() -> None: ...

        _stamp(shell)
        _stamp(admin, parent=shell)

        assert _match_outlet_in_chain(admin, "outlet_unknown") is None

    def test_layout_without_meta_treated_as_root(self) -> None:
        # A function without ``_bz_layout`` (test fixture, undecorated
        # function passed in by accident) terminates the walk after
        # one iteration — doesn't crash, just won't match anything
        # outside itself.
        from bretzel.server.routing.pages import _match_outlet_in_chain

        def bare() -> None: ...

        assert _match_outlet_in_chain(bare, "outlet_bare") is bare
        assert _match_outlet_in_chain(bare, "outlet_other") is None

    def test_three_level_chain(self) -> None:
        from bretzel.server.routing.pages import _match_outlet_in_chain

        def root() -> None: ...
        def mid() -> None: ...
        def leaf() -> None: ...

        _stamp(root)
        _stamp(mid, parent=root)
        _stamp(leaf, parent=mid)

        assert _match_outlet_in_chain(leaf, "outlet_leaf") is leaf
        assert _match_outlet_in_chain(leaf, "outlet_mid") is mid
        assert _match_outlet_in_chain(leaf, "outlet_root") is root
        assert _match_outlet_in_chain(leaf, "outlet_unknown") is None

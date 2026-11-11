"""``@refreshable`` — what a zone follows, and how it is addressed.

A zone follows every state it OBTAINS while it renders: ``MyState()``
in its body, in any helper it calls, or in the flattening (a table's
``rows=``). What is not a state — a database, the clock — is followed
through a ``Topic``, by the functions that read it. There is no list to write, so none to get wrong: a state forgotten
froze the zone without a word, a state too many re-rendered the whole
panel for a closed dialog.
"""

from __future__ import annotations

import pytest

from bretzel import ui
from bretzel.components.base import Component
from bretzel.components.base.testing import render_isolated
from bretzel.core.tree import TextNode
from bretzel.render.decorators.refreshable import (
    ZoneRegistry,
    RefreshableHandle,
    broadcast_changes,
    enqueue_readers,
    field_id,
    refresh,
    refreshable,
    state_qualname,
)
from bretzel.runtime.protocol import DATA_SUBSCRIBE_STATE, DATA_SUBSCRIBE_URL
from bretzel.state import AppState, ClientState, PageState, computed, field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry


class _S(AppState):
    items: list = field(default_factory=list)


class TestDualForm:
    def test_bare_form_defaults(self) -> None:
        @refreshable
        def zone_bare() -> None:
            pass

        assert isinstance(zone_bare, RefreshableHandle)
        # Never rendered in this process: it knows nothing it reads yet.
        assert zone_bare.reads is None
        # default name = the module-qualified zone name
        assert zone_bare.name == zone_bare.zone_qualname

    def test_declarative_form_carries_metadata(self) -> None:
        @refreshable(name="zone_named")
        def zone_named() -> None:
            pass

        assert isinstance(zone_named, RefreshableHandle)
        assert zone_named.name == "zone_named"

    def test_deps_is_gone(self) -> None:
        """One way to say what a zone follows: obtaining it, or @reads."""
        with pytest.raises(TypeError):
            refreshable(deps=[_S])  # type: ignore[call-arg]

    def test_broadcast_is_gone(self) -> None:
        """Who else hears of a change follows from what the zone read and
        from that state's scope: there is nothing left to declare."""
        with pytest.raises(TypeError):
            refreshable(broadcast=[_S])  # type: ignore[call-arg]


class TestNameRegistry:
    def test_explicit_name_is_addressable(self) -> None:
        @refreshable(name="my_addressable_zone")
        def zone_x() -> None:
            pass

        zones = ZoneRegistry()
        zones.add(zone_x)
        assert zones.by_name["my_addressable_zone"] is zone_x

    def test_default_name_is_registered(self) -> None:
        @refreshable
        def zone_y() -> None:
            pass

        zones = ZoneRegistry()
        zones.add(zone_y)
        assert zones.by_name[zone_y.zone_qualname] is zone_y


class _SA(AppState):
    x: int = field(default=0)


class _SB(AppState):
    y: int = field(default=0)


def read_a_through_a_helper() -> int:
    return _SA().x


class Signal(ClientState):
    on: bool = field(default=False)


class TestFollowsWhatItReads:
    """A state change (from the diff) enqueues exactly the zones that
    reached it in a render."""

    def test_diff_returns_changed_classes(self) -> None:
        class _SE(AppState):
            items: list = field(default_factory=list)

        reg = StateRegistry(MemoryBackend())
        with use_registry(reg):
            s = _SE()
            s.items.append(1)  # in-place
            changed = reg.diff_and_notify()
        assert _SE in changed

    def test_a_zone_follows_a_state_reached_through_a_helper(self) -> None:
        @refreshable
        def za() -> None:
            read_a_through_a_helper()

        @refreshable
        def zb() -> None:
            _SB()

        with render_isolated() as ctx:
            za()
            zb()
            assert set(za.reads) == {_SA}
            enqueue_readers(ctx, {_SA: set()})
            assert za in ctx.refresh_queue
            assert zb not in ctx.refresh_queue

    def test_a_nested_zone_reads_for_itself(self) -> None:
        """What the child reads is not the parent's: opening a dialog
        must not re-render the panel around it."""

        @refreshable
        def child() -> None:
            _SB()

        @refreshable
        def parent() -> None:
            _SA()
            child()

        with render_isolated() as ctx:
            parent()
            assert set(parent.reads) == {_SA}
            assert set(child.reads) == {_SB}
            enqueue_readers(ctx, {_SB: set()})
            assert child in ctx.refresh_queue
            assert parent not in ctx.refresh_queue

    def test_reads_add_up_across_renders(self) -> None:
        """Two clients may take two branches: the zone follows both."""
        branch = {"a": True}

        @refreshable
        def zbranch() -> None:
            if branch["a"]:
                _SA()
            else:
                _SB()

        with render_isolated():
            zbranch()
            branch["a"] = False
            zbranch()
        assert set(zbranch.reads) == {_SA, _SB}

    def test_a_shown_zone_never_rendered_here_is_refreshed(self) -> None:
        """A restart or another worker: the zone does not know what it
        reads, so it re-renders — the safe side — and learns."""

        @refreshable
        def zfresh() -> None:
            _SB()

        with render_isolated() as ctx:
            ctx.app.zones.add(zfresh)
            ctx.live_zones = frozenset({zfresh.id})
            enqueue_readers(ctx, {_SA: set()})
            assert zfresh in ctx.refresh_queue

    def test_enqueue_dedups_a_zone_reaching_two_changed_states(self) -> None:
        @refreshable
        def zcd() -> None:
            _SA()
            _SB()

        with render_isolated() as ctx:
            zcd()
            enqueue_readers(ctx, {_SA: set(), _SB: set()})
            assert ctx.refresh_queue.count(zcd) == 1

    def test_no_changes_enqueues_nothing(self) -> None:
        @refreshable
        def zn() -> None:
            _SA()

        with render_isolated() as ctx:
            zn()
            enqueue_readers(ctx, {})
            assert zn not in ctx.refresh_queue


class _View(AppState):
    q: str = field(default="")
    ticket: int = field(default=0)

    @computed
    def needle(self) -> str:
        return self.q.strip()


def enqueued_on(zone: RefreshableHandle, changed: dict[type, set[str]]) -> bool:
    """Is ``zone`` enqueued by an action that changed these fields?"""
    with render_isolated() as ctx:
        ctx.app.zones.add(zone)
        enqueue_readers(ctx, changed)
        return zone in ctx.refresh_queue


class TestFollowsByField:
    """A zone is redrawn when a FIELD it read changed — not any field of
    the class (measured on the helpdesk: opening a ticket redrew the
    status filter, which reads the filters and not the ticket)."""

    def test_a_zone_follows_the_fields_it_read(self) -> None:
        @refreshable
        def zsearch() -> None:
            _View().q

        with render_isolated():
            zsearch()
        assert zsearch.reads == {_View: frozenset({"q"})}
        assert not enqueued_on(zsearch, {_View: {"ticket"}})
        assert enqueued_on(zsearch, {_View: {"q"}})

    def test_unknown_changed_fields_count_as_every_field(self) -> None:
        @refreshable
        def zunknown() -> None:
            _View().q

        with render_isolated():
            zunknown()
        assert enqueued_on(zunknown, {_View: set()})

    def test_fields_add_up_across_branches(self) -> None:
        branch = {"q": True}

        @refreshable
        def zfork() -> None:
            view = _View()
            if branch["q"]:
                view.q
            else:
                view.ticket

        with render_isolated():
            zfork()
            branch["q"] = False
            zfork()
        assert zfork.reads == {_View: frozenset({"q", "ticket"})}

    def test_has_value_is_a_read_of_the_field(self) -> None:
        @refreshable
        def zset() -> None:
            _View.q.has_value(_View())

        with render_isolated():
            zset()
        assert zset.reads == {_View: frozenset({"q"})}

    def test_a_computed_follows_the_fields_it_was_computed_from(self) -> None:
        """Replayed from its cache: the second render reads no field."""

        @refreshable
        def zneedle() -> None:
            _View().needle

        with render_isolated():
            zneedle()
            zneedle()
        assert zneedle.reads == {_View: frozenset({"q"})}
        assert not enqueued_on(zneedle, {_View: {"ticket"}})

    @pytest.mark.parametrize("how", ["to_dict", "errors", "obtained only"])
    def test_what_a_descriptor_cannot_see_counts_as_the_whole_class(
        self, how: str
    ) -> None:
        """A bulk read or a state handed on without a field read may show
        anything."""
        reads = {
            "to_dict": lambda: _View().to_dict(),
            "errors": lambda: _View().errors,
            "obtained only": lambda: _View(),
        }

        @refreshable
        def zwhole() -> None:
            reads[how]()

        with render_isolated():
            zwhole()
        assert zwhole.reads == {_View: frozenset({"q", "ticket"})}
        assert enqueued_on(zwhole, {_View: {"ticket"}})


class _ShowsTheNeedleAtRender(Component):
    """A component whose READ happens at render — like a table's
    ``rows=`` callable — not when it is built."""

    THEME = {}
    THEME_KEY = "_shows_the_needle"
    DEFAULT_TAG = "span"
    BINDABLE_PROPS = ()

    def render(self) -> TextNode:
        return TextNode(_View().q)


class TestARecomposedZoneStillFollows:
    """``ui.sidebar`` renders a zone's footer itself, outside the zone's own
    flattening: what the footer's content reads must still be the zone's.

    It was ``ui.tabs`` until 2026-10-27; a zone inside a parent that
    composes its children is refused since then, and the sidebar — which
    only places them — is where a zone is still rendered this way."""

    def test_a_read_at_render_inside_a_recomposed_zone_is_the_zone_s(
        self,
    ) -> None:
        @refreshable
        def zfooter() -> None:
            with ui.sidebar_footer(name="Account"):
                _ShowsTheNeedleAtRender()

        with render_isolated() as ctx:
            ctx.app.sse_broker = None
            bar = ui.sidebar()
            with bar:
                zfooter()
            bar.render()
        assert zfooter.reads is not None
        assert "q" in zfooter.reads.get(_View, frozenset())


class TestFollowsPerClient:
    """What a zone follows is what THE BROWSER'S version of it read."""

    def test_the_zone_carries_what_its_render_read(self) -> None:
        from bretzel.core.serialize import serialize

        @refreshable
        def zcarried() -> None:
            ui.text(_View().q)

        with render_isolated() as ctx:
            ctx.app.sse_broker = None
            zcarried()
            html = serialize(ctx.root_children[0].render())
        assert f'data-bz-r="{field_id(_View, "q")}"' in html

    def test_the_client_s_version_decides(self) -> None:
        @refreshable
        def zshown() -> None:
            _View().ticket

        with render_isolated() as ctx:
            zshown()  # this process learned "ticket"...
            ctx.live_zones = frozenset({zshown.id})
            # ...but the browser shows a version that read "q" only.
            ctx.zone_reads = {zshown.id: frozenset({field_id(_View, "q")})}
            enqueue_readers(ctx, {_View: {"ticket"}})
            assert zshown not in ctx.refresh_queue
            enqueue_readers(ctx, {_View: {"q"}})
            assert zshown in ctx.refresh_queue

    def test_a_version_that_read_nothing_never_redraws(self) -> None:
        @refreshable
        def zstatic() -> None:
            pass

        with render_isolated() as ctx:
            ctx.live_zones = frozenset({zstatic.id})
            ctx.zone_reads = {zstatic.id: frozenset()}
            enqueue_readers(ctx, {_View: set()})
            assert zstatic not in ctx.refresh_queue

    def test_a_zone_the_browser_does_not_describe_falls_back(self) -> None:
        """An older runtime: what this process learned decides."""

        @refreshable
        def zold() -> None:
            _View().q

        with render_isolated() as ctx:
            zold()
            ctx.live_zones = frozenset({zold.id})
            enqueue_readers(ctx, {_View: {"q"}})
            assert zold in ctx.refresh_queue


class TestRefreshImperative:
    """Phase 4 : the single imperative trigger ``refresh(zone_or_name)``."""

    def test_refresh_by_handle_enqueues(self) -> None:
        @refreshable
        def zh() -> None:
            pass

        with render_isolated() as ctx:
            refresh(zh)
            assert zh in ctx.refresh_queue

    def test_refresh_refuses_a_name(self) -> None:
        with pytest.raises(TypeError, match="zone itself"):
            refresh("a_zone")

    def test_refresh_dedups_by_identity(self) -> None:
        @refreshable
        def zd() -> None:
            pass

        with render_isolated() as ctx:
            refresh(zd)
            refresh(zd)
            assert ctx.refresh_queue.count(zd) == 1

    def test_refresh_out_of_context_is_noop(self) -> None:
        @refreshable
        def zo() -> None:
            pass

        # No active context → no raise, no enqueue — but a warning: the
        # silence hid that nothing reached any screen (2026-11-03).
        with pytest.warns(RuntimeWarning, match="outside a request"):
            refresh(zo)

    def test_refresh_is_publicly_exported(self) -> None:
        import bretzel

        assert bretzel.refresh is refresh


# ───────────────────────────────────────────────────────────────────────────
# The other tabs: what a zone read, as far as its scope allows
# ───────────────────────────────────────────────────────────────────────────


class _FakeBroker:
    """Captures publish() calls so a test can assert the fan-out without a
    live SSE stream."""

    def __init__(self) -> None:
        self.published: list[str] = []

    def publish(self, qualname: str, *, except_tab: str = "",
                only_session: str = "") -> None:
        # ``except_tab`` / ``only_session`` : l'onglet émetteur et la
        # session visée, que le vrai courtier applique. Le double les
        # reçoit et les ignore — ce qu'il mesure, c'est QUELS canaux sont
        # publiés, pas à qui.
        del except_tab, only_session
        self.published.append(qualname)

    def subscribe(self, session_id: str, qualname: str) -> None:
        pass


class _FakeApp:
    def __init__(self, broker: _FakeBroker | None, *zones: object) -> None:
        self.sse_broker = broker
        self.zones = ZoneRegistry()
        for zone in zones:
            self.zones.add(zone)


class _FakeCtx:
    def __init__(self, app: _FakeApp, session_id: str = "sess-1") -> None:
        self.app = app
        self.session_id = session_id
        self.refresh_queue: list = []


def _rendered(zone: RefreshableHandle) -> RefreshableHandle:
    """Render ``zone`` once, so the process knows what it reads."""
    with render_isolated() as rctx:
        rctx.app.sse_broker = None
        zone()
    return zone


def _published(changes: dict[type, set[str]], *zones: RefreshableHandle) -> list[str]:
    broker = _FakeBroker()
    broadcast_changes(_FakeCtx(_FakeApp(broker, *zones)), changes)
    return broker.published


class TestBroadcast:
    def test_a_shared_state_a_zone_read_reaches_the_others(self) -> None:
        class _SB(AppState):
            x: int = field(default=0)

        @refreshable
        def zb() -> None:
            _SB().x

        assert _published({_SB: set()}, _rendered(zb)) == [state_qualname(_SB)]

    def test_a_state_no_zone_reads_stays_quiet(self) -> None:
        class _SQ(AppState):
            x: int = field(default=0)

        @refreshable
        def zq() -> None:
            pass

        assert _published({_SQ: set()}, _rendered(zq)) == []

    def test_a_zone_never_rendered_here_counts_as_reading_everything(self) -> None:
        """Another worker, a restart: the safe side is one signal too many."""

        class _SU(AppState):
            x: int = field(default=0)

        @refreshable
        def zu() -> None:
            _SU().x

        assert zu.reads is None
        assert _published({_SU: set()}, zu) == [state_qualname(_SU)]

    def test_a_change_publishes_only_its_own_state(self) -> None:
        class _SM1(AppState):
            x: int = field(default=0)

        class _SM2(AppState):
            y: int = field(default=0)

        @refreshable
        def zm() -> None:
            _SM1().x
            _SM2().y

        assert _published({_SM2: set()}, _rendered(zm)) == [state_qualname(_SM2)]

    def test_a_channel_stays_quiet_when_no_zone_read_the_field(self) -> None:
        """A write to a table no zone shows publishes nothing."""

        class _Tables(AppState):
            deals: int = field(default=0)
            notes: int = field(default=0)

        @refreshable
        def zpulse() -> None:
            _Tables().deals

        _rendered(zpulse)
        assert _published({_Tables: {"notes"}}, zpulse) == []
        assert _published({_Tables: {"deals"}}, zpulse) == [state_qualname(_Tables)]

    def test_no_broker_is_a_noop(self) -> None:
        class _SNB(AppState):
            x: int = field(default=0)

        @refreshable
        def znb() -> None:
            pass

        ctx = _FakeCtx(_FakeApp(None, znb))
        broadcast_changes(ctx, {_SNB: set()})  # must not raise


class TestSubscription:
    """What the browser listens to for a zone: the shared states it read."""

    def test_only_what_another_tab_can_change(self) -> None:
        class _App(AppState):
            x: int = field(default=0)

        class _Page(PageState):
            x: int = field(default=0)

        @refreshable
        def zone() -> None:
            pass

        attrs = zone.subscription({_App, _Page})
        assert attrs[DATA_SUBSCRIBE_STATE] == state_qualname(_App)
        assert attrs[DATA_SUBSCRIBE_URL].endswith(zone.zone_qualname)

    def test_a_zone_reading_nothing_shared_opens_no_stream(self) -> None:
        class _Page(PageState):
            x: int = field(default=0)

        @refreshable
        def zone() -> None:
            pass

        assert zone.subscription({_Page}) == {}
        assert zone.subscription(()) == {}

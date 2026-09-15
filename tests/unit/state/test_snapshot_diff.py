"""Phase 1 of the reactivity refactor — the ServerState snapshot-diff.

``StateRegistry.diff_and_notify()`` detects mutations a state underwent
since it was resolved, INCLUDING in-place list/dict ops that
``Field.__set__`` never sees (it only fires on reassignment). It is
value-based (compares ``_field_values`` snapshots), so it catches every
mutation form and has net-change semantics. This locks that behaviour in.

Cf. ``.claude/bretzel/reactivity-refactor-plan.md`` § Phase 1.
"""

from __future__ import annotations

import asyncio

from bretzel.state import AppState, field
from bretzel.state.persistence.memory import MemoryBackend
from bretzel.state.registry import StateRegistry, use_registry


class _Store(AppState):
    items: list = field(default_factory=list)
    tags: dict = field(default_factory=dict)
    name: str = field(default='')


def _registry() -> StateRegistry:
    return StateRegistry(MemoryBackend())


class TestInPlaceDetection:
    """The whole point : mutations that never hit ``Field.__set__``."""

    def test_list_append_is_detected(self) -> None:
        reg = _registry()
        with use_registry(reg):
            s = _Store()
            s.items.append("x")  # in-place — descriptor blind spot
            assert not s._dirty  # invisible to Field.__set__
            reg.diff_and_notify()
            assert s._dirty  # value-diff caught it

    def test_dict_setitem_is_detected(self) -> None:
        reg = _registry()
        with use_registry(reg):
            s = _Store()
            s.tags["k"] = "v"
            assert not s._dirty
            reg.diff_and_notify()
            assert s._dirty

    def test_list_pop_is_detected(self) -> None:
        reg = _registry()
        with use_registry(reg):
            s = _Store()
            s.items.append("a")
            reg.diff_and_notify()  # baseline now ["a"]
            s.items.pop()
            s._dirty = False
            reg.diff_and_notify()
            assert s._dirty  # removal is a change too


class TestReassignmentUnaffected:
    def test_reassignment_still_dirties_and_survives_diff(self) -> None:
        reg = _registry()
        with use_registry(reg):
            s = _Store()
            s.name = "hi"  # Field.__set__ already sets _dirty
            assert s._dirty
            reg.diff_and_notify()  # must not crash / stay consistent
            assert s._dirty


class TestNoFalsePositives:
    def test_untouched_state_stays_clean(self) -> None:
        reg = _registry()
        with use_registry(reg):
            s = _Store()
            reg.diff_and_notify()
            assert not s._dirty

    def test_reading_a_default_factory_is_not_a_change(self) -> None:
        # Reading materialises the default list/dict into __dict__ ; the
        # diff must NOT mistake that lazy materialisation for a mutation.
        reg = _registry()
        with use_registry(reg):
            s = _Store()
            _ = s.items
            _ = s.tags
            reg.diff_and_notify()
            assert not s._dirty

    def test_revert_within_action_is_net_no_change(self) -> None:
        # append + pop = net zero → value-diff (net-change semantics) fires
        # nothing, unlike an operation-hooking proxy.
        reg = _registry()
        with use_registry(reg):
            s = _Store()
            s.items.append("x")
            s.items.pop()
            reg.diff_and_notify()
            assert not s._dirty


class TestBugFixPersistence:
    """The latent bug this closes : today ``commit`` only saves ``_dirty``
    states, and in-place mutations never set ``_dirty`` — so
    ``store.items.append(...)`` silently VANISHED on the next request.
    diff_and_notify makes it dirty, so commit persists it."""

    def test_in_place_mutation_survives_to_next_request(self) -> None:
        backend = MemoryBackend()  # one backend shared across both requests

        async def scenario() -> list:
            # Request 1 : mutate in place + the end-of-action pipeline.
            reg1 = StateRegistry(backend)
            with use_registry(reg1):
                s = _Store()
                s.items.append("x")
                reg1.diff_and_notify()  # what actions.py now calls
                await reg1.commit()
            # Request 2 : fresh registry, same backend → reload.
            reg2 = StateRegistry(backend)
            with use_registry(reg2):
                return list(_Store().items)

        assert asyncio.run(scenario()) == ["x"]

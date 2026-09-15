"""``bz-class`` must re-apply its classes after a morph clobbers ``class="``.

Central regression for the whole ``bz-class`` family (Pagination, Accordion,
Sidebar, Navbar, Select, Combobox, Notification, LineChart, FileUpload). The
directive tracks the classes it adds so it never touches the server's static
``class="`` ; that tracking set used to live on the element
(``el._bzClassDyn``) — a JS property that SURVIVES idiomorph.

The failure it guards (reproduced live before the fix) :

1. A server-events control fires ``on_change`` → HTMX POST → its
   ``@refreshable`` zone re-renders and idiomorph morphs the subtree.
2. The morph rewrites ``class="`` back to the SSR baseline, STRIPPING the
   class this directive had added (Pagination's active pill, an open
   Accordion body's ``grid-rows-[1fr]``…).
3. The bridge re-scans the swapped subtree — ``bindEl`` disposes + re-binds
   every directive. With the tracking set persisted on the element it still
   claimed the class was applied (``prev === next``) so the re-bound effect
   NEVER re-added the stripped class — the styling silently vanished until
   the next unrelated interaction.

The fix makes the tracking set per-BIND (a closure in ``02_directives.js``),
so the re-bind after a morph starts empty and re-applies from the real
(clobbered) DOM baseline.

Rather than depend on a full HMAC-signed POST round-trip (which the audit
harness doesn't always drive to a real morph), this exercises the exact
runtime mechanism deterministically : take a live ``bz-class`` element, strip
its dynamic class the way idiomorph would, then call ``$bz._scan`` (the same
rescan the bridge runs in ``htmx:afterSwap``) and assert the class returns.

Heavier than ``tests/unit`` (uvicorn + Chromium) — run explicitly :
``py -m pytest tests/runtime_js/test_bzclass_survives_morph.py -q -m browser``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

# An open Accordion body carries ``grid-rows-[1fr]`` purely via bz-class
# (the row-template classes never appear in the static class="). That makes
# it a clean, unambiguous probe for "did bz-class re-apply after a rescan".
_OPEN_BODY = (
    "[role='region'].grid"  # the accordion body wrapper (display:grid)
)


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def test_bzclass_reapplies_after_morph_clobber_and_rescan(base_url: str) -> None:
    with browser_page(base_url, "/accordion") as page:
        # Wait for the runtime to hydrate at least one OPEN accordion body
        # (an item rendered expanded → its bz-class added grid-rows-[1fr]).
        page.wait_for_function(
            """() => [...document.querySelectorAll("[role='region']")]
                .some(b => b.classList.contains('grid-rows-[1fr]'))""",
            timeout=4000,
        )

        result = page.evaluate(
            """() => {
                const body = [...document.querySelectorAll("[role='region']")]
                    .find(b => b.classList.contains('grid-rows-[1fr]'));
                if (!body) return {ok: false, why: 'no open body'};

                // 1. Simulate the idiomorph clobber : strip the dynamic
                //    class, exactly as a morph resetting class=" to the SSR
                //    baseline would (the SSR baseline never has grid-rows-*).
                body.classList.remove('grid-rows-[1fr]');
                const strippedOff = !body.classList.contains('grid-rows-[1fr]');

                // 2. Run the SAME rescan the bridge runs in htmx:afterSwap.
                window.$bz._scan(body);

                // 3. The effect must have re-added the class from the real
                //    (clobbered) DOM baseline. With the old element-persisted
                //    tracking set this stayed stripped (prev === next).
                const reapplied = body.classList.contains('grid-rows-[1fr]');
                return {ok: true, strippedOff, reapplied};
            }"""
        )
        assert result["ok"], result.get("why")
        assert result["strippedOff"], "probe precondition: class was not stripped"
        assert result["reapplied"], (
            "bz-class did NOT re-apply grid-rows-[1fr] after a rescan — the "
            "morph-clobber regression is back (el._bzClassDyn persisted across "
            "the re-bind). Cf. traps.md § 'bz-class perdue après un morph'."
        )

"""Wait for the STATE, never for a duration.

Promoted from ``tests/audit/interaction.py`` on 2026-09-10, with its
measurement: this helper replaced an unconditional ``setTimeout(1500)``
on 2026-08-31, which weighed **88 to 92 % of the whole visual audit's
time** — 46 s out of 52 for ``button``. The suite cost 52 minutes, so it
never ran, and during that silence two anchor selectors died for 24 h
without anyone seeing.

⚠️ **This is not ``networkidle``, and it cannot be.** A page carrying a
``@refreshable(broadcast=[…])`` zone opens an ``EventSource``, hence an
HTTP connection that never closes: network idleness therefore NEVER
happens and the wait expires after 30 s (measured on 2026-08-15 while
mounting ``examples/chat``). So we watch the ACTION requests — the
``.htmx-request`` marker the bridge sets for the duration of a round trip
— and the DOM's silence.

Two phases, and the first is not negotiable: a control may DEBOUNCE
before posting, so handing back as soon as the DOM is quiet would read a
stale state and report "it does nothing" about something that works.
"""

from __future__ import annotations

from typing import Any

#: The floor covers a 300 ms debounce; the 120 ms of silence declares
#: the swap settled. Both stay below the ceiling, which has the last
#: word.
FLOOR_MS = 320
QUIET_MS = 120

_JS = """
async (args) => {
    const t0 = Date.now();
    let last = 0;
    const obs = new MutationObserver(() => { last = Date.now(); });
    obs.observe(document.documentElement, {
        subtree: true, childList: true,
        attributes: true, characterData: true,
    });
    try {
        // Phase 1 — let the blow land: a request in flight, a mutation,
        // or the floor expiring.
        while (Date.now() - t0 < args.floor) {
            await new Promise(r => setTimeout(r, 20));
            if (last || document.querySelector('.htmx-request')) break;
        }
        // Phase 2 — wait for the return to calm, under the ceiling.
        while (Date.now() - t0 < args.ceiling) {
            await new Promise(r => setTimeout(r, 20));
            if (document.querySelector('.htmx-request')) continue;
            if (last && Date.now() - last >= args.quiet) return 'SETTLED';
            if (!last && Date.now() - t0 >= args.floor + args.quiet) {
                return 'NOTHING_MOVED';
            }
        }
        return 'TIMEOUT';
    } finally {
        obs.disconnect();
    }
}
"""


def settle_page(page: Any, *, timeout: float, floor: int = FLOOR_MS) -> str:
    """Return ``SETTLED``, ``NOTHING_MOVED``, ``NAVIGATED`` or ``TIMEOUT``.

    ``floor=0`` for a wait that FOLLOWS NO GESTURE — a resize, a theme
    change, a navigation that has already awaited ``load``. Measured on
    2026-09-10 in A/B alternation on the same page: **463 ms with the
    floor, 136 ms without**. The floor only pays behind a control that
    can debounce before posting; elsewhere it is pure sleep, exactly what
    this module exists for having removed.

    ``NOTHING_MOVED`` is not a fault: many gestures change nothing on
    screen, and that is sometimes exactly what is being measured (a
    refused drop putting the card back).
    """
    args = {"floor": floor, "quiet": QUIET_MS, "ceiling": int(timeout * 1000)}
    try:
        return str(page.evaluate(_JS, args))
    except Exception as exc:
        if "Execution context was destroyed" not in str(exc):
            raise
        # A NAVIGATION took the document away from under the wait. That
        # is a calm, not a failure: the click did what it was asked. Found
        # on 2026-09-10 while mounting the first scenario with a sign-in
        # — a form POST that redirects. No app probe can avoid this case,
        # so the harness must hold it.
        page.wait_for_load_state("load")
        # Floor at zero: the new document has just loaded, there is no
        # debounce in progress to cover.
        page.evaluate(_JS, {**args, "floor": 0})
        return "NAVIGATED"

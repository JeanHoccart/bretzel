"""The browser — one Chromium per process, one context per window.

Promoted from ``tests/audit/harness.py`` on 2026-09-10, with its
measurements.

⚠️ **One single ``sync_playwright()`` per process.** Playwright's sync
API is not thread-safe and two instances in the same thread tread on
each other: measured on 2026-08-27, ``-m browser`` went from 286 greens
to "1 failure + 75 errors" as soon as one file opened its own — and it
still passed when run ALONE, which is the worst of symptoms. That is why
this module carries the singleton, and why ``tests/audit/harness.py``
delegates to it instead of keeping a second one.

⚠️ **It is not yet a process-wide exclusivity**:
``tests/e2e/conftest.py`` still opens its own. No conflict today —
``-m e2e`` has its own slot — but the guarantee only holds for the
suites that come through here.

The browser is SHARED, the context is FRESH. Measured in in-process A/B
alternation (a sequential before/after is worth nothing on this machine,
which drifts by a factor of 2): fresh browser **633 ms** median, fresh
context on a shared browser **408 ms**.

Isolation does not change: cookies, storage, cache and permissions are
per CONTEXT, that is Playwright's guarantee. What is shared is the
Chromium process — nothing a probe can observe. **That is exactly why
``windows=`` opens contexts and not tabs**: two tabs of the same context
share cookies, hence the same session, so a two-user scenario would no
longer measure anything.
"""

from __future__ import annotations

import atexit
import contextlib
from collections.abc import Iterator
from typing import Any

_PW: Any = None
_BROWSER: Any = None


def shared_browser() -> Any:
    """The process's Chromium — started on the first request.

    Restarted if the browser has disconnected: a probe that crashes it
    must not condemn every following one in the same process.
    """
    global _PW, _BROWSER
    from playwright.sync_api import sync_playwright

    if _PW is None:
        _PW = sync_playwright().start()
    if _BROWSER is None or not _BROWSER.is_connected():
        _BROWSER = _PW.chromium.launch(headless=True)
    return _BROWSER


@contextlib.contextmanager
def contexts(
    count: int,
    *,
    size: tuple[int, int],
    headed: bool = False,
    touch: bool = False,
) -> Iterator[list[Any]]:
    """``count`` fresh contexts, closed together on exit.

    ``headed=True`` steps outside the singleton: a visible browser is
    launched for the call and closed afterwards. A visible Chromium
    shared between headless probes would be a surprise, not an
    optimisation.

    ``touch=True`` opens a TOUCH context. It is the only mode where the
    browser really applies ``touch-action``: without it, a test
    dispatching synthetic ``PointerEvent`` measures our code and not the
    browser's decision, so it stays green whatever the component's
    ``touch-action``.
    """
    if headed:
        from playwright.sync_api import sync_playwright

        pw: Any = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)
    else:
        pw = None
        browser = shared_browser()

    opened: list[Any] = []
    try:
        for _ in range(count):
            opened.append(
                browser.new_context(
                    viewport={"width": size[0], "height": size[1]},
                    has_touch=touch,
                    is_mobile=touch,
                )
            )
        yield opened
    finally:
        for ctx in opened:
            with contextlib.suppress(Exception):
                ctx.close()
        if pw is not None:
            with contextlib.suppress(Exception):
                browser.close()
                pw.stop()


@atexit.register
def _close_shared_browser() -> None:
    global _PW, _BROWSER
    with contextlib.suppress(Exception):
        if _BROWSER is not None:
            _BROWSER.close()
    with contextlib.suppress(Exception):
        if _PW is not None:
            _PW.stop()
    _BROWSER = _PW = None

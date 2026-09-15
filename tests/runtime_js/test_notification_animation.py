"""Toast enter / leave animation wiring — runtime_js probe.

Proves the V3 notification animation is wired end-to-end (the V2 Alpine
``x-transition`` path was dropped in the runtime rewrite) :

- a shown toast mounts with ``bz-toast-enter`` (the enter keyframe) ;
- dismissing it flips ``bz-toast-leave`` and the **two-phase** removal in
  ``09_notification.js`` keeps the node alive for the leave keyframe before
  splicing it ;
- ``prefers-reduced-motion: reduce`` short-circuits the leave dance — the
  toast is dropped immediately.

Heavier than ``tests/unit`` (uvicorn + Chromium), so it lives here.
Run only this : ``py -m pytest tests/runtime_js/test_notification_animation.py -q``
"""

from __future__ import annotations

import pytest

from tests.audit.harness import audit_server, browser_page

# The toaster skeleton lives in every page's shell ; a shown toast renders
# as a ``role="status"`` node inside the OOB portal.
TOAST = "#bz-notification-root [role='status']"
DISMISS = f"{TOAST} button[aria-label='Dismiss notification']"


@pytest.fixture(scope="module")
def base_url():
    with audit_server() as url:
        yield url


def _notify(page, **detail):
    """Fire the ``bz:notify`` DOM event the toaster subscribes to.

    ``duration_ms=0`` disables auto-dismiss so the test drives removal.
    """
    detail.setdefault("message", "hello")
    detail.setdefault("variant", "success")
    detail.setdefault("duration_ms", 0)
    page.evaluate(
        "d => document.dispatchEvent(new CustomEvent('bz:notify', {detail: d}))",
        detail,
    )


def test_toast_enter_leave_animation_wired(base_url: str) -> None:
    with browser_page(base_url, "/notification") as page:
        page.emulate_media(reduced_motion="no-preference")

        _notify(page)
        page.wait_for_selector(TOAST, timeout=3000)
        cls = page.get_attribute(TOAST, "class") or ""
        assert "bz-toast-enter" in cls, f"enter class missing : {cls!r}"

        # Dismiss → the two-phase removal flips ``_leaving`` so the leave
        # keyframe class lands BEFORE the node is spliced.
        page.click(DISMISS)
        page.wait_for_function(
            "s => { const t = document.querySelector(s);"
            " return !!t && t.className.includes('bz-toast-leave'); }",
            arg=TOAST,
            timeout=1500,
        )
        # ...then phase 2 drops it once the keyframe has run.
        page.wait_for_selector(TOAST, state="detached", timeout=3000)


def test_toast_survivor_slides_on_neighbour_dismiss(base_url: str) -> None:
    """When one of two stacked toasts leaves, the survivor must GLIDE into
    the freed slot, not teleport.

    Regression : the leave keyframe only fades + scales the departing toast
    (transforms don't reflow), so at splice time the survivor used to jump
    ~60px in a single frame — "elle réapparaît, ça fait sale". The ``:flip``
    modifier on the toast ``bz-for`` now FLIP-animates surviving rows (cf.
    ``02_directives.js`` ``flipPlay``). We sample the survivor's top through
    the reflow and require a continuum of intermediate positions.
    """
    with browser_page(base_url, "/notification") as page:
        page.emulate_media(reduced_motion="no-preference")

        # Two toasts, auto-dismiss off so the test drives the removal.
        _notify(page, message="FIRST")
        _notify(page, message="SECOND")
        page.wait_for_function(
            "s => document.querySelectorAll(s).length === 2", arg=TOAST, timeout=3000
        )

        # Dismiss FIRST, then sample the SECOND toast's top every frame for
        # 500ms. A slide leaves many distinct tops between old and new ; a
        # jump leaves only the two endpoints.
        tops = page.evaluate(
            """async () => {
                const q = s => [...document.querySelectorAll(s)];
                const sel = "#bz-notification-root [role='status']";
                const leaver = q(sel).find(n => n.textContent.includes('FIRST'));
                leaver.querySelector("button[aria-label='Dismiss notification']").click();
                const seen = new Set();
                const t0 = performance.now();
                return await new Promise(res => {
                    (function tick() {
                        const s = q(sel).find(n => n.textContent.includes('SECOND'));
                        if (s) seen.add(Math.round(s.getBoundingClientRect().top));
                        if (performance.now() - t0 > 500) res([...seen]);
                        else requestAnimationFrame(tick);
                    })();
                });
            }"""
        )
        # A genuine slide passes through several intermediate rows ; the old
        # teleport bug produced only ~2 distinct tops (start + end).
        assert len(tops) >= 5, f"survivor jumped instead of sliding : tops={sorted(tops)}"


def test_toast_reduced_motion_removes_immediately(base_url: str) -> None:
    with browser_page(base_url, "/notification") as page:
        page.emulate_media(reduced_motion="reduce")

        _notify(page)
        page.wait_for_selector(TOAST, timeout=3000)

        # Under reduced-motion the runtime skips the leave delay entirely —
        # the node is removed straight away, no ``bz-toast-leave`` hold.
        page.click(DISMISS)
        page.wait_for_selector(TOAST, state="detached", timeout=1500)

"""Playwright probe — Slider POINTER-CLICK path (the reported bug).

User report : "dès que je clique il passe à 0". The existing
``probe_slider.py`` only drives the KEYBOARD path (``_nudge`` →
``_setHandle``), which never reads ``this._track``. The click path
(``_jumpToPointer`` → ``_pointerToValue``) returns ``this._min`` when
``this._track`` is null or zero-width — exactly a snap-to-0.

Drives ``bench_slider.py`` (uvicorn :8965). Clicks the track at ~80 %
and asserts the value lands near 80, not 0. Also dumps the scope's
``_track`` / rect so we see the root cause if it FAILs.

Run :  py tests/probes/probe_slider_click.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("slider bench never came up on :8965")


def valuenow(handle):
    return handle.get_attribute("aria-valuenow")


def scope_diag(page, sid):
    """Read the slider scope's _track presence + track rect width."""
    return page.evaluate(
        """(sid) => {
          const root = document.querySelector('#' + sid);
          const track = root.querySelector('[bz-ref=bztrack]');
          const sc = window.$bz._scopeFor(root);
          const t = sc.proxy._track;
          const rect = track ? track.getBoundingClientRect() : null;
          return {
            hasTrack: !!t,
            trackIsTheEl: t === track,
            rectW: rect ? Math.round(rect.width) : -1,
            value: sc.proxy.value,
          };
        }""",
        sid,
    )


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_slider.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 700, "height": 700})
            errs = []
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")
            page.wait_for_timeout(80)

            h = page.query_selector_all("#sl-single [role=slider]")
            check("starts at 50", valuenow(h[0]) == "50", valuenow(h[0]))

            diag = scope_diag(page, "sl-single")
            print(f"\n  scope diag (single): {diag}")
            check("_track captured (not null)", diag["hasTrack"], str(diag))
            check("_track is the bztrack el", diag["trackIsTheEl"], str(diag))
            check("track has non-zero width", diag["rectW"] > 0, str(diag))

            # Click the track at ~80 % of its width.
            track = page.query_selector("#sl-single [bz-ref=bztrack]")
            box = track.bounding_box()
            x = box["x"] + box["width"] * 0.8
            y = box["y"] + box["height"] / 2
            print(f"\n  clicking track at x={x:.0f} (80%) y={y:.0f}")
            page.mouse.click(x, y)
            page.wait_for_timeout(80)

            v = valuenow(h[0])
            print(f"  value after click @80% : {v}")
            check(
                "click @80% lands near 80 (step 10 → 80), NOT 0",
                v == "80",
                f"got {v} — the reported snap-to-0 bug" if v == "0" else f"got {v}",
            )

            # Second click lower, ~30 %.
            x2 = box["x"] + box["width"] * 0.3
            page.mouse.click(x2, y)
            page.wait_for_timeout(80)
            v2 = valuenow(h[0])
            print(f"  value after click @30% : {v2}")
            check("click @30% lands near 30", v2 == "30", f"got {v2}")

            # ── Carrier + change event (same bz-init capture as _track) ──
            # ``_emitChange`` reads ``this._carrier`` ; if the init failed
            # to capture it, drag/click would update the value but NEVER
            # fire ``change`` (silent — downstream on_change handlers dead).
            print("\n  carrier + change-event on drag")
            carrier_ok = page.evaluate(
                """() => {
                  const root = document.querySelector('#sl-single');
                  const sc = window.$bz._scopeFor(root);
                  const c = sc.proxy._carrier;
                  window.__bzChange = 0;
                  if (c) c.addEventListener('change', () => { window.__bzChange++; });
                  return !!c;
                }"""
            )
            check("_carrier captured (change events can fire)", carrier_ok)
            # Real drag : pointer down on track @50%, move to @70%, up.
            box = track.bounding_box()
            page.mouse.move(box["x"] + box["width"] * 0.5, y)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * 0.7, y, steps=5)
            page.mouse.up()
            page.wait_for_timeout(80)
            v3 = valuenow(h[0])
            changes = page.evaluate("() => window.__bzChange")
            print(f"  value after drag→70% : {v3}, change events : {changes}")
            check("drag lands at 70", v3 == "70", f"got {v3}")
            check("drag fired ≥1 change event", changes >= 1, f"got {changes}")

            # ── Disabled : click + drag + keyboard must ALL be inert ────
            print("\n  disabled slider stays put")
            dh = page.query_selector_all("#sl-disabled [role=slider]")
            check("disabled starts at 40", valuenow(dh[0]) == "40", valuenow(dh[0]))
            ddiag = page.evaluate(
                """() => {
                  const root = document.querySelector('#sl-disabled');
                  const track = root.querySelector('[bz-ref=bztrack]');
                  const handle = root.querySelector('[role=slider]');
                  const sc = window.$bz._scopeFor(root);
                  // Effective hover target over the middle of the track :
                  // pointer-events:none on the track means elementFromPoint
                  // skips it (and its handles), resolving to the root — so
                  // the root's cursor-not-allowed is what the user sees.
                  const r = track.getBoundingClientRect();
                  const hit = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
                  return {
                    disabledState: sc.proxy._disabledState(),
                    trackPE: getComputedStyle(track).pointerEvents,
                    handlePE: getComputedStyle(handle).pointerEvents,
                    handleTab: handle.getAttribute('tabindex'),
                    aria: handle.getAttribute('aria-disabled'),
                    rootCursor: getComputedStyle(root).cursor,
                    rootOpacity: getComputedStyle(root).opacity,
                    hitIsRoot: hit === root,
                    hitTag: hit ? (hit.id || hit.tagName) : null,
                  };
                }"""
            )
            print(f"  disabled diag : {ddiag}")
            check("_disabledState() is true", ddiag["disabledState"] is True, str(ddiag))
            check("track pointer-events:none", ddiag["trackPE"] == "none", str(ddiag))
            check("handle inherits pointer-events:none", ddiag["handlePE"] == "none", str(ddiag))
            check("handle tabindex=-1 (no keyboard focus)", ddiag["handleTab"] == "-1", str(ddiag))
            check("aria-disabled=true", ddiag["aria"] == "true", str(ddiag))
            check("root cursor = not-allowed", ddiag["rootCursor"] == "not-allowed", str(ddiag))
            check("root opacity = 0.5 (muted)", ddiag["rootOpacity"] == "0.5", str(ddiag))
            check("hover over track resolves to root (cursor falls through)",
                  ddiag["hitIsRoot"], str(ddiag))
            # Try to click the track at 80% — value must stay 40.
            dtrack = page.query_selector("#sl-disabled [bz-ref=bztrack]")
            dbox = dtrack.bounding_box()
            page.mouse.click(dbox["x"] + dbox["width"] * 0.8, dbox["y"] + dbox["height"] / 2)
            page.wait_for_timeout(60)
            # Try to drag the handle.
            hbox = dh[0].bounding_box()
            page.mouse.move(hbox["x"] + hbox["width"] / 2, hbox["y"] + hbox["height"] / 2)
            page.mouse.down()
            page.mouse.move(dbox["x"] + dbox["width"] * 0.2, dbox["y"] + dbox["height"] / 2, steps=4)
            page.mouse.up()
            page.wait_for_timeout(60)
            vdis = valuenow(dh[0])
            print(f"  value after click+drag attempts : {vdis}")
            check("disabled slider did NOT move (still 40)", vdis == "40", f"got {vdis}")

            check("no JS console errors", not errs, "; ".join(errs[:5]))
            page.screenshot(path=str(HERE / "slider_click_screenshot.png"))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SLIDER CLICK PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("SLIDER CLICK PROBE PASSED — track-click sets the value correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Probe — attribute the dense-page boot cost ('load' handler Violation).

Runs ``bench_load_perf.py`` (uvicorn :8971) twice — debug ON then OFF —
and reports, per regime :

  - time to ``bz:ready``           (nav-start → runtime booted)
  - longest single long-task       (the >50ms task the browser flags)
  - total long-task time
  - ``bz:boot-scan`` measure        ($bz._scan duration, if instrumented)

debug ON  = in-browser Tailwind compiler runs.
debug OFF = no Tailwind-in-browser ; $bz._scan cost is identical.
The delta isolates Tailwind ; ``bz:boot-scan`` isolates OUR scan.

Run :  py tests/probes/probe_load_perf.py
"""

from __future__ import annotations

import os
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

# Installed BEFORE any page script : capture long-tasks + stamp bz:ready.
INIT = """
window.__longtasks = [];
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__longtasks.push(e.duration);
  }).observe({ type: 'longtask', buffered: true });
} catch (e) {}
window.__bzReadyAt = null;
document.addEventListener('bz:ready', () => { window.__bzReadyAt = performance.now(); });
"""


def wait_server(timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("load-perf bench never came up on :8971")


def measure(pw, label):
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1000, "height": 900})
    page.add_init_script(INIT)
    page.goto(BASE + "/")
    page.wait_for_selector("html.bz-ready")
    page.wait_for_timeout(400)  # let any post-ready long-tasks land
    data = page.evaluate(
        """() => {
            const lt = window.__longtasks || [];
            const scan = performance.getEntriesByName('bz:boot-scan');
            return {
              ready: window.__bzReadyAt,
              ltMax: lt.length ? Math.max(...lt) : 0,
              ltTotal: lt.reduce((a, b) => a + b, 0),
              ltCount: lt.length,
              bootScan: scan.length ? scan[0].duration : null,
            };
        }"""
    )
    browser.close()
    print(f"\n{label}")
    print(f"  time to bz:ready   : {data['ready'] and round(data['ready'])} ms")
    print(f"  longest long-task  : {round(data['ltMax'])} ms   (>50ms ⇒ Violation)")
    print(f"  total long-task    : {round(data['ltTotal'])} ms  ({data['ltCount']} tasks)")
    bs = data["bootScan"]
    print(f"  bz:boot-scan ($bz._scan) : {('%d ms' % round(bs)) if bs is not None else 'n/a (runtime not instrumented)'}")
    return data


def run_regime(debug: bool):
    env = os.environ.copy()
    env["BENCH_DEBUG"] = "1" if debug else "0"
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_load_perf.py"), str(PORT)],
        cwd=HERE.parent.parent, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            return measure(pw, f"=== debug={'ON (Tailwind-in-browser)' if debug else 'OFF (prod-like)'} ===")
    finally:
        server.terminate()
        server.wait(timeout=10)


def main():
    on = run_regime(True)
    off = run_regime(False)
    print("\n── attribution ──────────────────────────────────────────")
    tw = (on["ltMax"] - off["ltMax"])
    print(f"  Tailwind-in-browser (debug-only) ≈ {round(tw)} ms of the longest task")
    print(f"  $bz._scan / runtime boot         ≈ {round(off['ltMax'])} ms (persists prod)")
    if off["bootScan"] is not None:
        print(f"  ($bz._scan measured exactly      : {round(off['bootScan'])} ms)")
    print()
    verdict = "Tailwind-in-browser" if tw > off["ltMax"] else "our $bz._scan"
    print(f"VERDICT — dominant boot cost on a dense page : {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

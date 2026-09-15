"""Playwright probe — switch thumb vertical centering (:8977).

For every switch, compares the thumb span's vertical centre against the
track div's : they must coincide (±1.5px) or the thumb sits off-rail.

Run :  py tests/probes/probe_switch.py
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

MEASURE = """() => {
  const out = [];
  document.querySelectorAll('.bz-switch').forEach((root, i) => {
    const cont = root.querySelector('div.relative') || root;
    const divs = cont.querySelectorAll(':scope > div, :scope > span');
    // track = the block div (not sr-only input) ; thumb = the span.
    const track = cont.querySelector(':scope > div');
    const thumb = cont.querySelector(':scope > span');
    if (!track || !thumb) { out.push({i, err: 'no track/thumb'}); return; }
    const t = track.getBoundingClientRect(), h = thumb.getBoundingClientRect();
    out.push({
      i,
      trackMid: t.top + t.height / 2,
      thumbMid: h.top + h.height / 2,
      delta: Math.abs((t.top + t.height/2) - (h.top + h.height/2)),
      thumbInsideV: h.top >= t.top - 0.5 && h.bottom <= t.bottom + 0.5,
    });
  });
  return out;
}"""


def main():
    srv = subprocess.Popen(
        [sys.executable, str(HERE / "bench_switch.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                urllib.request.urlopen(BASE + "/", timeout=1)
                break
            except OSError:
                time.sleep(0.3)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 700, "height": 700})
            page.goto(BASE + "/")
            page.wait_for_function(
                "document.documentElement.classList.contains('bz-ready')"
            )
            page.wait_for_timeout(200)
            rows = page.evaluate(MEASURE)
            print(f"  {len(rows)} switches measured")
            worst = 0.0
            for r in rows:
                if r.get("err"):
                    FAILURES.append(f"switch {r['i']}: {r['err']}")
                    continue
                worst = max(worst, r["delta"])
                centred = r["delta"] <= 1.5 and r["thumbInsideV"]
                tag = "ok " if centred else "OFF"
                print(f"   [{tag}] switch {r['i']:2d}  delta={r['delta']:.2f}px"
                      f"  inside={r['thumbInsideV']}")
                if not centred:
                    FAILURES.append(
                        f"switch {r['i']}: delta={r['delta']:.2f}px "
                        f"inside={r['thumbInsideV']}")
            print(f"  worst vertical offset: {worst:.2f}px")
            page.screenshot(path=str(HERE / "switch_centering.png"),
                            full_page=True)
            print("  screenshot → switch_centering.png")
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)

    print()
    if FAILURES:
        print(f"SWITCH PROBE FAILED — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("SWITCH PROBE PASSED — thumb centred on every size.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

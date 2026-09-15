"""Playwright probe — `size=` atteint TOUT le picker, BLOCKING gate.

Pilote ``bench_picker_size.py`` (uvicorn :8961).

Le bug (juillet 2026) : `ui.combobox(size="xl")` grossissait le trigger et
les options, mais gardait des pills Badge `sm`, un chevron `sm`, un panel
`max-h-60` (3,5 options visibles, la 4e coupée) et un compteur `text-xs`.
Cause : le composeur de base SKIPPE en silence une table `sizes`
multi-slots, donc `size` n'atteignait que les 3 slots câblés à la main.

Pourquoi un probe et pas un test SSR : le gate `test_size_reaches_slots`
prouve que les CLASSES sont émises. Il ne prouve pas qu'elles COMPILENT ni
que `getComputedStyle` les reflète — `max-h-52`/`max-h-72` ne sont pas dans
la palette Tailwind par défaut, et une classe qui ne compile pas est
invisible en SSR. Seul un vrai Chromium tranche.

Mesures (xs < md < xl, strictement) :
1. Pills : font-size réelle.
2. Chevron : taille du glyphe (font-size — jamais w/h, cf. traps.md).
3. Panel : max-height effective.
4. Compteur "N / total" : font-size.
5. Zéro erreur console. Screenshot.

Run :  py tests/probes/probe_picker_size.py
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
SIZES = ("xs", "md", "xl")

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(f"{label} — {detail}")


# Aucune interaction : le runtime déplie le ``bz-for`` des pills au boot,
# et ``getComputedStyle`` lit un élément même masqué par ``display:none``.
# Le panel et le compteur du header sont donc mesurables panel fermé — pas
# de clic, pas d'attente d'animation, pas de flakiness.
_MEASURE_JS = """
(root) => {
    const q = (sel) => document.querySelector(root + ' ' + sel);
    const size = (el, prop) =>
        el ? (parseFloat(getComputedStyle(el)[prop]) || 0) : 0;

    // La pill = le span qui PORTE le label pické. Repère sémantique :
    // aucun hook data-* n'existe et les classes Badge peuvent bouger.
    const pill = [...document.querySelectorAll(root + ' span')]
        .find(s => s.textContent.trim() === 'Italia');

    return {
        pill:    size(pill, 'fontSize'),
        chevron: size(q("iconify-icon[icon*='chevron']"), 'fontSize'),
        panel:   size(q('[role=listbox]'), 'maxHeight'),
        counter: size(q("[class*='tabular-nums']"), 'fontSize'),
    };
}
"""


def strictly_increasing(values: dict[str, float]) -> bool:
    xs, md, xl = (values[s] for s in SIZES)
    return 0 < xs < md < xl


def measure(page, kind: str) -> None:
    """kind = 'cb' (combobox) ou 'sel' (select)."""
    print(f"\n-- {kind} --")
    got = {
        size: page.evaluate(_MEASURE_JS, f"#{kind}-{size}") for size in SIZES
    }
    for axis, label in (
        ("pill", "pills"),
        ("chevron", "chevron"),
        ("panel", "panel max-height"),
        ("counter", "compteur"),
    ):
        values = {s: got[s][axis] for s in SIZES}
        check(
            f"{kind} — {label} suit size (xs < md < xl)",
            strictly_increasing(values),
            str(values),
        )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_picker_size.py"), str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(BASE, timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            print("le bench n'a pas démarré sur :8961")
            return 1

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1400})
            console_errors: list[str] = []
            page.on("console", lambda m: (
                console_errors.append(m.text) if m.type == "error" else None
            ))
            page.goto(BASE)
            # ``bz-ready`` est posé sur <html> (runtime 00_index.js), pas
            # sur <body> — il libère le `[bz-data]{visibility:hidden}`.
            page.wait_for_selector("html.bz-ready", timeout=15000)

            measure(page, "cb")
            measure(page, "sel")

            print()
            check("zéro erreur console", not console_errors, "; ".join(console_errors[:6]))

            # ``iconify-icon`` va chercher ses glyphes sur api.iconify.design
            # et les injecte dans son shadow root APRÈS le boot. Sans cette
            # attente le screenshot montre des chevrons vides : les mesures
            # (pilotées par font-size) passent, mais l'artefact visuel ne
            # prouve rien. On attend le <svg>, pas un délai arbitraire.
            page.wait_for_function(
                """() => [...document.querySelectorAll('iconify-icon')]
                    .every(el => el.shadowRoot
                        && el.shadowRoot.innerHTML.includes('<svg'))""",
                timeout=10000,
            )
            page.screenshot(path=str(HERE / "picker_size_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"PICKER SIZE PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("PICKER SIZE PROBE PASSED — size= atteint tout le picker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Playwright probe — batch-3 (scoped) V3 ports, BLOCKING gate.

Drives ``bench_batch3.py`` (uvicorn :8950) in a real Chromium :

Tabs :
1. Panel one visible, two/three hidden at rest.
2. Click tab Two → panel two shows, one hides.
3. L'onglet actif est le SEUL souligné, et le soulignement déménage
   au clic (``border-bottom`` opaque vs transparent — CSS pur, plus
   d'indicateur glissant depuis la refonte).

ToggleGroup :
4. "Day" selected at rest ; click "Month" → data-selected flips.

Accordion :
5. Section A open, B closed ; click B header → B opens.

Pagination :
6. Click page 3 → the active page indicator follows.

Slider :
7. Keyboard ArrowRight on the handle increments the value.

NumberInput :
8. "+" button increments the field.

9. Zero JS console errors. Screenshot.

Run :  py tests/probes/probe_batch3.py
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from tests.probes._serve import free_port
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("batch3 bench never came up on :8950")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_batch3.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1100, "height": 1100})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")

            # ── Tabs ───────────────────────────────────────────────────
            print("\nTabs — bascule + soulignement de l'onglet actif")
            p1 = page.locator("#panel-one")
            p2 = page.locator("#panel-two")
            check("panel one visible at rest", p1.is_visible())
            check("panel two hidden at rest", p2.is_hidden())
            # ⚠️ Le soulignement est du CSS PUR depuis la refonte : plus de
            # ``[data-tab-indicator]``, plus de ``ResizeObserver``, plus de
            # ``translateX``. ``test_tabs.py::test_active_underline_is_pure_css``
            # affirme l'absence des quatre. Ce probe cherchait encore
            # l'indicateur glissant — donc il ne mesurait rien, il attendait
            # 30 s un élément qu'un test unitaire garantit absent.
            #
            # Ce qu'on mesure à la place est ce que l'ŒIL voit : le
            # ``border-bottom`` de l'onglet actif est OPAQUE, celui des
            # autres transparent — et il DÉMÉNAGE au clic.
            underlined_js = r"""() => Array.from(
                 document.querySelectorAll('[role=tab]'))
                   .filter(t => {
                     const c = getComputedStyle(t).borderBottomColor;
                     return c && !/,\s*0\s*\)$/.test(c) && c !== 'transparent';
                   })
                   .map(t => (t.textContent || '').trim())"""

            def underlined(expected: str | None = None) -> list[str]:
                """Les onglets dont le ``border-bottom`` est OPAQUE.

                ⚠️ Deux pièges, tous deux mesurés :

                1. ``transition-colors duration-150`` sur l'onglet : à
                   100 ms du clic, l'ancien est à mi-fondu et compte
                   ENCORE comme souligné. On attend donc au lieu de
                   deviner un délai ;
                2. attendre « exactement un souligné » ne suffit pas —
                   c'est vrai AVANT le clic aussi. Sous charge, le
                   prédicat était satisfait par l'ANCIEN état et le probe
                   lisait ``['One']`` après avoir cliqué Two. On attend
                   donc que ce soit le bon onglet, nommé.
                """
                if expected is not None:
                    with contextlib.suppress(PlaywrightTimeout):
                        page.wait_for_function(
                            f"() => {{ const u = ({underlined_js})();"
                            f"  return u.length === 1 && u[0] === {expected!r}; }}",
                            timeout=4000,
                        )
                return page.evaluate(underlined_js)

            check("un seul onglet souligné au repos",
                  underlined("One") == ["One"], str(underlined()))
            page.get_by_role("tab", name="Two").click()
            page.wait_for_selector("#panel-two", state="visible")
            check("clicking tab Two shows panel two", p2.is_visible())
            check("panel one hides", p1.is_hidden())
            check("le soulignement a DÉMÉNAGÉ sur l'onglet cliqué",
                  underlined("Two") == ["Two"], str(underlined()))

            # ── ToggleGroup ────────────────────────────────────────────
            print("\nToggleGroup — segmented")
            tg = page.locator("#bench-toggle")
            day = tg.get_by_role("button", name="Day")
            month = tg.get_by_role("button", name="Month")
            check(
                "Day selected at rest",
                day.get_attribute("data-selected") == "true",
            )
            month.click()
            page.wait_for_function(
                "[...document.querySelectorAll('#bench-toggle button')]"
                ".find(b => b.textContent.trim() === 'Month')"
                ".getAttribute('data-selected') === 'true'"
            )
            check("clicking Month selects it", month.get_attribute("data-selected") == "true")
            check("Day deselected", day.get_attribute("data-selected") == "false")

            # ── Accordion ──────────────────────────────────────────────
            # Collapse is a CSS grid (0fr↔1fr) : is_visible() can't tell
            # a 0-height clipped body from an open one, so measure the
            # grid wrapper's offsetHeight instead.
            print("\nAccordion")

            def acc_height(body_id: str) -> float:
                return page.evaluate(
                    """(id) => {
                        let el = document.getElementById(id);
                        while (el && getComputedStyle(el).display !== 'grid')
                            el = el.parentElement;
                        return el ? el.offsetHeight : -1;
                    }""",
                    body_id,
                )

            check("section A open at rest (grid height > 0)", acc_height("acc-body-a") > 0)
            check("section B closed at rest (grid height ~0)", acc_height("acc-body-b") < 2)
            page.get_by_role("button", name="Section B").click()
            page.wait_for_function(
                """() => {
                    let el = document.getElementById('acc-body-b');
                    while (el && getComputedStyle(el).display !== 'grid')
                        el = el.parentElement;
                    return el && el.offsetHeight > 2;
                }"""
            )
            check("clicking B header opens B", acc_height("acc-body-b") > 2)

            # ── Pagination ─────────────────────────────────────────────
            # Page buttons get their number from bz-text at runtime ; the
            # active page is shown via the bz-class active style (no
            # aria-current). Match button text exactly, check the class.
            print("\nPagination")
            page3 = (
                page.locator("#bench-pagination button")
                .filter(has_text=re.compile(r"^3$"))
                .first
            )
            page3.click()
            # ⚠️ La page active se peint aux PALIERS depuis la phase 3 des
            # jetons de couleur : `bg-(--bz-solid)`, plus `bg-primary`.
            # Ce probe a donc attendu trente secondes une classe morte —
            # et il n'a rien dit pendant tout ce temps, parce qu'une suite
            # de quatorze minutes ne se lance pas. Trouvé le 2026-08-31.
            page.wait_for_function(
                """() => {
                    const b = [...document.querySelectorAll('#bench-pagination button')]
                        .find(b => b.textContent.trim() === '3');
                    return b && b.className.includes('bg-(--bz-solid)');
                }"""
            )
            check("clicking page 3 marks it active", True)

            # ── Slider ─────────────────────────────────────────────────
            print("\nSlider — keyboard")
            handle = page.locator("#bench-slider [role='slider']").first
            before = handle.get_attribute("aria-valuenow")
            handle.focus()
            page.keyboard.press("ArrowRight")
            page.wait_for_function(
                f"document.querySelector('#bench-slider [role=slider]')"
                f".getAttribute('aria-valuenow') !== '{before}'"
            )
            after = handle.get_attribute("aria-valuenow")
            check("ArrowRight increments slider", float(after) > float(before),
                  f"before={before}, after={after}")

            # ── NumberInput ────────────────────────────────────────────
            print("\nNumberInput — stepper")
            num_input = page.locator("#bench-number input").first
            v0 = num_input.input_value()
            page.locator("#bench-number").get_by_role("button", name="Increment").click()
            page.wait_for_function(
                f"document.querySelector('#bench-number input').value !== '{v0}'"
            )
            check("+ increments the field", float(num_input.input_value()) > float(v0),
                  f"v0={v0}, v1={num_input.input_value()}")

            # ── Sidebar — collapse toggle ──────────────────────────────
            print("\nSidebar — collapse")
            aside = page.locator("#bench-sidebar")
            check(
                "sidebar expanded at rest (data-open=true)",
                aside.get_attribute("data-open") == "true",
            )
            page.click("#sb-toggle")
            page.wait_for_function(
                "document.querySelector('#bench-sidebar')"
                ".getAttribute('data-open') === 'false'"
            )
            check("toggle collapses it (data-open=false)", True)

            check("no JS console errors", not console_errors, "; ".join(console_errors[:5]))
            page.screenshot(path=str(HERE / "batch3_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"BATCH3 PROBE FAILED — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("BATCH3 PROBE PASSED — les composants scopés batch 3 sont fonctionnels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

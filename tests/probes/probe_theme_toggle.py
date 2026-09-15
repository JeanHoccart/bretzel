"""Playwright probe — un clic sur le bascule de thème change TOUJOURS l'écran.

Sert ``examples.pomodoro.main:app`` (uvicorn, port 8955) — une app de
démo qui câble ``ColorScheme.toggle()`` sur un contrôle à deux positions,
là où les coques de ``docs`` et ``playground`` offrent les trois modes via
``ColorScheme.set``.

⚠️ Ce probe servait ``examples.calculator`` jusqu'au 2026-09-07, et disait
« la seule app » — c'était faux le jour où ça a été écrit : ``pomodoro``
portait déjà le même couple d'``icon_button``, à l'identique. Calculator
est partie à l'élagage des exemples ; le probe a changé d'hôte, pas de
sujet.

Ce que ça mesure, et pourquoi aucune suite ne le mesurait
---------------------------------------------------------
Le bug corrigé le 2026-09-04 n'existait QUE au départ de ``system`` sur
un OS sombre : le bascule comparait le JETON (``mode === 'dark'``), donc
le premier clic écrivait ``dark``, déjà la valeur peinte. Rien ne
bougeait à l'écran.

Un banc parti de ``light`` — le défaut de tout navigateur de test —
serait passé. C'est pour ça que ce probe ouvre **deux** contextes, un
par préférence d'OS, et qu'il vérifie le PREMIER clic dans chacun. La
gate sœur (``tests/consistency/
test_the_theme_flip_and_the_paint_share_one_resolution.py``) garde
l'unicité de la résolution ; celle-ci garde son EFFET.

Run :  py tests/probes/probe_theme_toggle.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
REPO = HERE.parent.parent
PORT = 8955
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
    raise RuntimeError(f"calculator never came up on :{PORT}")


def run_scenario(browser, os_scheme: str) -> None:
    """Un OS, un départ en ``system``, trois clics."""
    print(f"\nOS en {os_scheme} — départ en « system »")
    context = browser.new_context(color_scheme=os_scheme)
    page = context.new_page()
    page.goto(BASE + "/")
    page.wait_for_selector("html.bz-ready", timeout=15000)

    # Départ propre : aucune préférence enregistrée, donc ``system``.
    page.evaluate("localStorage.removeItem('$bz:ColorScheme.default')")
    page.reload()
    page.wait_for_selector("html.bz-ready", timeout=15000)

    dark = lambda: page.evaluate(  # noqa: E731 — une sonde, pas une fonction
        "document.documentElement.classList.contains('dark')"
    )
    mode = lambda: page.evaluate(  # noqa: E731
        "$bz.state.ColorScheme.default.mode"
    )

    check("le mode part bien de « system »", mode() == "system", f"got: {mode()}")
    check(
        f"la peinture suit l'OS ({os_scheme})",
        dark() is (os_scheme == "dark"),
        f"dark={dark()}",
    )

    # Le bouton visible est celui que la variante ``dark:`` laisse
    # passer — on clique par son libellé accessible, pas par sa place.
    label = "Light mode" if dark() else "Dark mode"
    seen = [dark()]
    for step in range(1, 4):
        page.get_by_role("button", name=label).click()
        # L'attente EST la mesure, donc son expiration est un FAIL et non
        # une exception : sans ce garde, le premier clic mort remontait une
        # trace Playwright et les checks suivants ne tournaient jamais —
        # une trace ne dit pas QUEL clic n'a rien fait.
        try:
            page.wait_for_function(
                "document.documentElement.classList.contains('dark') === "
                f"{str(not seen[-1]).lower()}",
                timeout=3000,
            )
        except PlaywrightTimeout:
            pass
        seen.append(dark())
        check(
            f"clic {step} : l'écran change ({seen[-2]} → {seen[-1]})",
            seen[-1] is not seen[-2],
            f"dark reste {seen[-1]} après le clic {step}",
        )
        label = "Light mode" if seen[-1] else "Dark mode"

    check(
        "le mode a quitté « system » (le bascule est à deux états)",
        mode() in ("light", "dark"),
        f"got: {mode()}",
    )
    context.close()


def main() -> int:
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "examples.pomodoro.main:app",
            "--host", "127.0.0.1", "--port", str(PORT),
        ],
        cwd=REPO,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            # Les DEUX préférences : c'est la sombre qui portait le bug,
            # et la claire qui l'aurait masqué.
            for os_scheme in ("dark", "light"):
                run_scenario(browser, os_scheme)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAIL")
        for line in FAILURES:
            print("  -", line)
        return 1
    print("Tout vert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

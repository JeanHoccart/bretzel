"""Probe — un `open`/`close` d'overlay imbriqué fuit-il vers l'ancêtre ?

Pilote ``bench_overlay_bubble.py`` (uvicorn :8968).

Le soupçon vient de `probe_overflow_card`, section B : ouvrir le panneau
d'un combobox DANS un ``ui.dialog(on_open=…)`` faisait partir un POST du
handler du DIALOG. Ce probe-ci isole le mécanisme et le mesure sur les
DEUX formes d'émission :

- **racine** — ``ui.select`` : ``dispatch_root_effect`` fire l'événement
  SUR la racine de l'overlay ;
- **enfant** — ``ui.alert(dismissible=True)`` : le ``×`` est un
  descendant, son ``close`` doit remonter à sa propre racine.

Les deux passent par ``$dispatch``, qui construit un ``CustomEvent`` avec
``bubbles: true`` (``02_directives.js``, ``makeDispatch``). Un
``hx-trigger="open"`` posé sur une racine ancêtre l'attrape donc aussi.

Run :  py tests/probes/probe_overlay_bubble.py
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

from tests.probes._serve import free_port

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(f"{label} — {detail}")


def wait_server(timeout: float = 25.0) -> None:
    """Attend le banc — et DISTINGUE « pas encore là » de « 500 ».

    ``urllib`` lève ``HTTPError`` pour un 500, et ``HTTPError`` hérite
    d'``OSError`` : un ``except OSError`` qui réessaie en boucle
    transforme une page cassée en « le serveur n'est jamais venu ».
    C'est exactement ce qui a caché un kwarg mort dans ``bench_batch3``
    pendant des mois.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"le banc répond {exc.code} sur {BASE}/ — il DÉMARRE, c'est "
                f"la page qui casse. Lance `py tests/probes/"
                f"bench_overlay_bubble.py` et lis la trace."
            ) from exc
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"le banc n'a jamais écouté sur {BASE}")


def run(page) -> None:
    posts: list[str] = []
    page.on(
        "response",
        lambda r: posts.append(r.url.split("::")[-1])
        if "/_bretzel/action" in r.url and r.request.method == "POST"
        else None,
    )

    def log() -> list[str]:
        return [t.split(". ", 1)[1] for t in page.locator(".evt").all_text_contents()]

    # ── témoin — un dialog SEUL ────────────────────────────────────────
    print("\n-- témoin : dialog vide --")
    page.click("#btn-witness")
    page.wait_for_timeout(900)
    check("ouvrir logge exactement un 'open'", log() == ["witness:open"], f"log={log()}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(900)
    check("fermer logge exactement un 'close'",
          log() == ["witness:open", "witness:close"], f"log={log()}")
    base = len(log())

    # ── A — l'émetteur dispatche sur SA PROPRE racine ─────────────────
    print("\n-- A : ui.select DANS le dialog (émission sur la racine) --")
    page.click("#btn-root")
    page.wait_for_timeout(900)
    check("ouvrir le dialog logge un 'open'", log()[base:] == ["root:open"], f"log={log()[base:]}")
    n = len(posts)

    page.click("#sel-in-root button")
    page.wait_for_timeout(700)
    check("ouvrir le panneau du select ne logge RIEN",
          log()[base:] == ["root:open"],
          f"log={log()[base:]} ; POSTs +{len(posts) - n} : {posts[n:]}")

    n = len(posts)
    panel_open = page.evaluate(
        "() => { const p = document.querySelector('#sel-in-root [role=listbox]');"
        "  return !!p && getComputedStyle(p).display !== 'none'; }"
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(700)
    # ⚠️ ``display !== 'none'`` NE SUFFIT PAS : un dialog fermé garde
    # ``display: flex`` et part en ``visibility: hidden; opacity: 0``.
    # Mesuré — cette version-là du test a fait passer « le dialog s'est
    # fermé tout seul » pour « une fuite ».
    dialog_still_open = page.evaluate(
        "() => { const d = document.querySelector('[role=dialog]');"
        "  if (!d) return false;"
        "  const cs = getComputedStyle(d);"
        "  return cs.display !== 'none' && cs.visibility !== 'hidden'"
        "    && cs.opacity !== '0'; }"
    )
    # Échap peut légitimement fermer le DIALOG lui-même — auquel cas un
    # ``root:close`` est le sien, pas une fuite. Ce qui est interdit,
    # c'est un ``close`` alors que le dialog est TOUJOURS OUVERT.
    leaked = log()[base:] != ["root:open"] and dialog_still_open
    check("fermer le panneau du select ne fait pas fuir de 'close'",
          not leaked,
          f"panneau ouvert avant Échap={panel_open} ; dialog encore "
          f"ouvert={dialog_still_open} ; log={log()[base:]} ; "
          f"POSTs +{len(posts) - n} : {posts[n:]}")

    if dialog_still_open:
        page.keyboard.press("Escape")
        page.wait_for_timeout(900)
    base = len(log())

    # ── B — l'émetteur est un DESCENDANT de sa propre racine ──────────
    print("\n-- B : ui.alert(dismissible) DANS le dialog (émission par l'enfant) --")
    page.click("#btn-child")
    page.wait_for_timeout(900)
    check("ouvrir le dialog logge un 'open'", log()[base:] == ["child:open"], f"log={log()[base:]}")
    n = len(posts)

    page.click("#alert-in-child button")
    page.wait_for_timeout(900)
    check("congédier l'alerte ne logge PAS un 'close' du dialog",
          log()[base:] == ["child:open"],
          f"log={log()[base:]} ; POSTs +{len(posts) - n} : {posts[n:]}")


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_overlay_bubble.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready", timeout=15000)
            run(page)
            check("zéro erreur console", not errors, str(errors[:3]))
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    if FAILURES:
        print(f"\nOVERLAY-BUBBLE PROBE — {len(FAILURES)} rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nOVERLAY-BUBBLE PROBE PASSED — aucun événement ne quitte sa racine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

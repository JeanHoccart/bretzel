"""Playwright probe — cinq frictions relevées EN SE SERVANT du CRM (:8983).

Pilote ``bench_crm_findings.py``, qui reconstruit chaque situation hors
de l'app (une zone, un composant, rien d'autre) pour que ce qui rougit
désigne le framework et pas ``examples/crm``.

Ce probe est un CONSTAT, pas une gate : il rougit tant que les findings
de [`bugs-usage-2026-08-21.md`](../../.claude/work/bugs-usage-2026-08-21.md)
ne sont pas réparés. Il vert = ils le sont.

Run :  py tests/probes/probe_crm_findings.py
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
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def wait_server(timeout=25.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/", timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError("crm-findings bench never came up on :8983")


def cells(page):
    return page.evaluate(
        "document.querySelectorAll('#cal [data-bz-cal-grid] > *').length")


def main():
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_crm_findings.py"), str(PORT)],
        cwd=HERE.parent.parent,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_server()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            errs = []
            page.on("console",
                    lambda m: errs.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errs.append(str(e)))
            posts = []
            page.on("request", lambda r: posts.append(r.url)
                    if "/_bretzel/action/" in r.url else None)
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")
            page.wait_for_timeout(400)

            # ── A. un calendrier survit-il au refresh de SA zone ? ────
            print()
            print("A. ui.calendar dans une zone @refreshable")
            before = cells(page)
            check("grille peinte au premier rendu", before > 0,
                  f"{before} cellules")
            page.click("#bumpbtn")
            page.wait_for_timeout(600)
            after1 = cells(page)
            check("grille encore là après 1 refresh", after1 > 0,
                  f"{after1} cellules (avant : {before})")
            page.click("#bumpbtn")
            page.wait_for_timeout(600)
            check("grille encore là après 2 refreshs", cells(page) > 0,
                  f"{cells(page)} cellules")

            # ── B. une carte s'écrase-t-elle sous son contenu ? ───────
            print()
            print("B. ui.card dans une colonne qui défile")
            free_h = page.evaluate(
                "document.querySelector('#free > *')"
                ".getBoundingClientRect().height")
            squeezed_h = page.evaluate(
                "document.querySelector('#squeezed > *')"
                ".getBoundingClientRect().height")
            clipped = page.evaluate(
                "(() => { const c = document.querySelector('#squeezed > *');"
                " return c.scrollHeight - c.clientHeight; })()")
            check("carte contrainte = carte libre",
                  abs(free_h - squeezed_h) < 1,
                  f"libre {free_h:.0f}px, contrainte {squeezed_h:.0f}px")
            check("rien n'est coupé dans la carte", clipped <= 0,
                  f"{clipped:.0f}px de contenu coupés")

            # ── C. pagination cliquée vite (zone à 250 ms) ────────────
            print()
            print("C. ui.pagination, 6 clics « suivant » sans attendre")
            errs.clear()
            nxt = "#pager [aria-label='Next page'], #pager nav > *:last-child"
            for _ in range(6):
                page.click(nxt, force=True)
            page.wait_for_timeout(3000)
            server_page = page.inner_text("#pageno")
            pill = page.evaluate(
                "(() => { const a = document.querySelector("
                "'#pager [aria-current=\"page\"], #pager [data-active=\"true\"]');"
                " return a ? a.textContent.trim() : null; })()")
            check("le serveur a suivi les 6 clics", "page = 7" in server_page,
                  f"{server_page!r}")
            check("la pastille montre la page du serveur",
                  pill == server_page.split("=")[-1].strip(),
                  f"pastille {pill!r} vs {server_page!r}")
            check("aucune erreur JS pendant la rafale", not errs,
                  "; ".join(errs[:3]))

            # ── D. une période choisie remonte-t-elle au serveur ? ────
            print()
            print("D. ui.date_range_picker en filtre")
            errs.clear()
            posts.clear()
            before_p = page.inner_text("#periode")
            # ⚠️ On mesure la RACINE des deux contrôles, pas un descendant
            # choisi par sélecteur. La version d'avant prenait
            # ``#rng input:not([type=hidden])`` d'un côté et
            # ``#sel [role=combobox]`` de l'autre — donc la boîte
            # INTÉRIEURE du picker contre la boîte EXTÉRIEURE du select.
            #
            # Ça a marché par coïncidence jusqu'au 2026-08-23 : la hauteur
            # du palier vivait alors sur l'``<input>``. `b5280f20` l'a
            # déplacée sur ``input_frame``, l'élément QUI PORTE LA BORDURE
            # — le vrai correctif — et l'``<input>`` est depuis à 30 px
            # dans un cadre de 32, ce qui est exactement juste. Le probe,
            # lui, s'est mis à accuser le fix : 2 px d'écart annoncés là
            # où les deux contrôles s'alignent au pixel.
            #
            # La racine est la seule boîte comparable entre deux
            # structures différentes, et c'est celle que l'œil voit
            # s'aligner. La version SYSTÉMATIQUE de cette mesure — tous
            # les contrôles, aux cinq paliers — vit dans
            # ``tests/runtime_js/test_form_controls_share_one_height.py``.
            box = "(sel) => document.querySelector(sel).getBoundingClientRect().height"
            h_rng = page.evaluate(box, "#rng")
            h_sel = page.evaluate(box, "#sel")
            check("picker(size=sm) et select(size=sm) ont la même hauteur",
                  abs(h_rng - h_sel) < 1,
                  f"picker {h_rng:.0f}px, select {h_sel:.0f}px")
            page.click("#rng [aria-label='Open date range picker']")
            page.wait_for_timeout(500)
            cellsel = "#rng [data-bz-cal-grid] button"
            vis = page.locator(cellsel + ":visible").count()
            check("le calendrier du picker s'ouvre", vis > 20,
                  f"{vis} cellules visibles")
            if vis > 20:
                page.locator(cellsel + ":visible").nth(8).click()
                page.wait_for_timeout(200)
                page.locator(cellsel + ":visible").nth(15).click()
                page.wait_for_timeout(1500)
            client_val = page.evaluate(
                "(() => { const h = document.querySelector("
                "'#rng input[type=hidden]'); return h && h.value; })()")
            check("le choix a bien été fait côté client",
                  bool(client_val and client_val != "[]"), repr(client_val))
            check("le choix POSTe une action serveur", len(posts) > 0,
                  f"{len(posts)} POST — le client tient "
                  f"{client_val}, le serveur n'en sait rien")
            check("la période choisie est remontée au serveur",
                  page.inner_text("#periode") != before_p,
                  f"{before_p!r} inchangé")

            # ── E. et le date_picker SIMPLE, même famille ? ───────────
            print()
            print("E. ui.date_picker (valeur scalaire), même question")
            posts.clear()
            before_j = page.inner_text("#jour")
            hid = ("(() => Array.from(document.querySelectorAll("
                   "'#dp input[type=hidden]')).map(h => [h.name, h.value]))()")
            print("    cachés avant :", page.evaluate(hid))
            page.click("#dp [aria-label='Open date picker']")
            page.wait_for_timeout(500)
            dsel = "#dp [data-bz-cal-grid] button:visible"
            if page.locator(dsel).count() > 20:
                page.locator(dsel).nth(20).click()
                page.wait_for_timeout(1500)
            print("    cachés après :", page.evaluate(hid))
            dp_client = page.evaluate(
                "(() => { const h = document.querySelector("
                "'#dp input[type=hidden]'); return h && h.value; })()")
            check("le jour a bien été choisi côté client",
                  bool(dp_client) and dp_client != "2026-08-05", repr(dp_client))
            check("le jour choisi POSTe une action serveur", len(posts) > 0,
                  f"{len(posts)} POST — le client tient {dp_client}")
            check("le jour choisi est remonté au serveur",
                  page.inner_text("#jour") != before_j,
                  f"{before_j!r} inchangé")

            # ── F. entrer sur l'écran de préférences ─────────────────
            print()
            print("F. ui.toggle_group lié à ColorScheme (ClientState)")
            page.goto(BASE + "/prefs")
            page.wait_for_selector("html.bz-ready")
            page.evaluate(
                "window.$bz.state.ColorScheme.default.mode = 'dark'")
            page.wait_for_timeout(400)
            stored = page.evaluate(
                "window.$bz.state.ColorScheme.default.mode")
            check("le choix 'dark' tient sur la page", stored == "dark",
                  repr(stored))
            page.reload()
            page.wait_for_selector("html.bz-ready")
            page.wait_for_timeout(600)
            after_nav = page.evaluate(
                "window.$bz.state.ColorScheme.default.mode")
            check("un rechargement complet ne réécrit pas le thème",
                  after_nav == "dark",
                  f"choisi 'dark', retrouvé {after_nav!r}")

            # …et la MÊME arrivée, mais par une navigation boostée —
            # c'est comme ça qu'on entre dans un écran du CRM.
            page.goto(BASE + "/")
            page.wait_for_selector("html.bz-ready")
            page.wait_for_timeout(300)
            page.click("#toprefs")
            page.wait_for_timeout(900)
            after_boost = page.evaluate(
                "window.$bz.state.ColorScheme.default.mode")
            check("y arriver par un lien (hx-boost) ne réécrit pas le thème",
                  after_boost == "dark",
                  f"choisi 'dark', retrouvé {after_boost!r}")
            # …et ce que le CONTRÔLE montre, qui est ce que l'utilisateur
            # lit. Le serveur ne connaît pas l'état client : il rend le
            # DÉFAUT de la classe.
            shown = page.evaluate(
                "(() => { const a = document.querySelector("
                "'#theme [data-state=\"on\"], #theme [aria-pressed=\"true\"],"
                " #theme [data-active=\"true\"]');"
                " return a ? a.textContent.trim() : null; })()")
            page.click("#pbumpbtn")
            page.wait_for_timeout(800)
            after_zone = page.evaluate(
                "window.$bz.state.ColorScheme.default.mode")
            check("un refresh de la zone qui le contient ne le réécrit pas",
                  after_zone == "dark",
                  f"choisi 'dark', retrouvé {after_zone!r}")
            check("le contrôle montre le thème RÉELLEMENT actif",
                  shown == "Sombre",
                  f"état client 'dark', contrôle sur {shown!r}")

            # ── G. le tactile peut-il encore faire défiler ? ─────────
            print()
            print("G. ui.draggable — ce que la CSS laisse au doigt")
            page.goto(BASE + "/kanban")
            page.wait_for_selector("html.bz-ready", state="attached")
            page.wait_for_timeout(300)
            ta = page.evaluate(
                "getComputedStyle(document.querySelector("
                "'#col [data-bz-draggable]')).touchAction")
            # Ce qui compte est le PAN VERTICAL, pas une valeur exacte :
            # ``pan-x pan-y`` (ce que pose le thème depuis le correctif)
            # le laisse passer autant que ``pan-y``, et n'interdit que le
            # pinch. Une liste fermée de trois chaînes faisait rougir le
            # probe SUR LE FIX — la façon la plus coûteuse de mentir.
            check("une carte déplaçable laisse le défilement vertical",
                  ta in ("auto", "manipulation") or "pan-y" in ta,
                  f"touch-action = {ta!r} — le doigt ne peut plus "
                  f"faire défiler la colonne")

            # ── H. le rail replié et ses bandes fantômes ─────────────
            print()
            print("H. ui.sidebar repliée — ce que coûte un titre de section")
            page.goto(BASE + "/rail")
            page.wait_for_selector("html.bz-ready", state="attached")
            page.wait_for_timeout(400)
            band = page.evaluate(
                "(() => { const l = document.querySelector("
                "'#side [class*=uppercase]');"
                " const b = l.getBoundingClientRect();"
                " return [Math.round(b.height),"
                " getComputedStyle(l).visibility]; })()")
            check("un titre de section invisible ne prend pas de place",
                  band[0] == 0,
                  f"{band[0]}px réservés pour un libellé {band[1]}")

            page.screenshot(path=str(HERE / "crm_findings_screenshot.png"),
                            full_page=True)
            browser.close()
    finally:
        server.terminate()

    print()
    print("ÉCHECS :\n  " + "\n  ".join(FAILURES) if FAILURES else "tout vert")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())

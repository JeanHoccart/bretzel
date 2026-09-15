"""Playwright probe — tranche les 2 questions de l'audit 2026-07-15.

Pilote ``bench_overflow_card.py`` (uvicorn :8963).

A. ``OVERFLOWS_CONTAINER`` : les panels ancrés étant repositionnés
   ``position:fixed`` à l'ouverture, le swap Card ``overflow-hidden →
   overflow-visible`` protège-t-il encore quelque chose ?
   - plain  : baseline (swap actif) — le panel doit déborder la card ;
   - hidden : ``!overflow-hidden`` forcé — si le panel reste visible,
     le swap est vestigial pour le cas STATIQUE ;
   - hover  : hoverable + hidden — le hover lift pose un transform →
     containing block → le fixed se re-ancre sur la card et devient
     clippable. Si le panel se fait clipper au hover, le marker protège
     ENCORE ce cas → décision ≠ « retirer silencieusement ».

B. Combobox dispatch ``open``/``close`` bullants non déclarés dans son
   ``EVENTS`` : ouvrir le panel du combobox DANS un dialog à
   ``on_open=`` serveur fire-t-il un POST fantôme ?

Run :  py tests/probes/probe_overflow_card.py
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


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(f"{label} — {detail}")


def info(label: str, detail: str) -> None:
    print(f"  info  {label}  ({detail})")


_MEASURE = """
([cardId, selId]) => {
    const card = document.getElementById(cardId);
    const panel = document.querySelector('#' + selId + ' [role=listbox]');
    const pr = panel.getBoundingClientRect();
    const cr = card.getBoundingClientRect();
    const probeY = Math.min(pr.bottom - 8, innerHeight - 1);
    const hit = document.elementFromPoint(pr.left + pr.width / 2, probeY);
    const cardCs = getComputedStyle(card);
    const trigger = document.querySelector('#' + selId + ' button');
    const tr = trigger.getBoundingClientRect();
    return {
        position: getComputedStyle(panel).position,
        escapes: pr.bottom > cr.bottom + 4,
        visible: !!(hit && (panel.contains(hit) || hit === panel)),
        hitDesc: hit ? hit.tagName + '.' + String(hit.className).slice(0, 60) : 'null',
        panelTop: Math.round(pr.top),
        panelBottom: Math.round(pr.bottom),
        cardBottom: Math.round(cr.bottom),
        triggerBottom: Math.round(tr.bottom),
        // Un panel bien ancré s'ouvre à ≤ ~12px sous son trigger.
        anchored: Math.abs(pr.top - tr.bottom) < 24,
        // Tailwind v4 pose la propriété INDIVIDUELLE `translate`, pas
        // `transform` (cf. traps.md § -translate-x-*) — les deux créent
        // un containing block pour les descendants fixed. Le lift Card
        // est désormais en `top` (offset de position, AUCUN containing
        // block) — c'est précisément ce que ce probe verrouille.
        cardTransform: cardCs.transform,
        cardTranslate: cardCs.translate,
        cardTop: cardCs.top,
    };
}
"""


def open_select(page, sel_id: str):
    page.click(f"#{sel_id} button")
    page.wait_for_selector(f"#{sel_id} [role=listbox]", state="visible", timeout=5000)
    page.wait_for_timeout(150)  # laisse floating() positionner


def close_overlays(page, sel_id: str) -> None:
    # Click-outside (zone vide à droite) plutôt qu'Escape, et on VÉRIFIE
    # la fermeture — un panel resté ouvert fausse l'elementFromPoint du
    # cas suivant.
    page.mouse.click(1100, 100)
    page.wait_for_selector(
        f"#{sel_id} [role=listbox]", state="hidden", timeout=5000
    )
    page.wait_for_timeout(100)


def probe_overflow(page) -> None:
    print("\n-- A. OVERFLOWS_CONTAINER --")

    open_select(page, "sel-plain")
    m = page.evaluate(_MEASURE, ["card-plain", "sel-plain"])
    info("plain — position runtime du panel", m["position"])
    check("plain — panel visible hors de la card (fixed au runtime)",
          m["escapes"] and m["visible"],
          f"panel bas={m['panelBottom']} card bas={m['cardBottom']} "
          f"visible={m['visible']} hit={m['hitDesc']}")
    close_overlays(page, "sel-plain")

    open_select(page, "sel-hidden")
    m = page.evaluate(_MEASURE, ["card-hidden", "sel-hidden"])
    check("hidden forcé — panel TOUJOURS visible (un clip ne mord pas un fixed)",
          m["escapes"] and m["visible"],
          f"position={m['position']} visible={m['visible']} hit={m['hitDesc']}")
    close_overlays(page, "sel-hidden")

    open_select(page, "sel-hover")
    before = page.evaluate(_MEASURE, ["card-hover", "sel-hover"])
    check("hover (avant hover) — panel ouvert visible",
          before["visible"],
          f"bas={before['panelBottom']} hit={before['hitDesc']}")
    # Hover le COIN de la card (pas le panel) pour déclencher le lift.
    box = page.locator("#card-hover").bounding_box()
    page.mouse.move(box["x"] + 6, box["y"] + 6)
    page.wait_for_timeout(350)  # transition duration-200 + marge
    after = page.evaluate(_MEASURE, ["card-hover", "sel-hover"])
    info("hover — top/transform/translate de la card pendant le hover",
         f"top={after['cardTop']} transform={after['cardTransform']} "
         f"translate={after['cardTranslate']}")
    lift = after["cardTop"] not in ("auto", "0px", "")
    check("hover — le lift s'applique bien (top < 0, PAS de transform/translate)",
          lift
          and after["cardTransform"] in ("none", "")
          and after["cardTranslate"] in ("none", ""),
          f"top={after['cardTop']} transform={after['cardTransform']} "
          f"translate={after['cardTranslate']}")
    check(
        "hover + hidden — le panel SURVIT-il au containing block ?",
        after["visible"],
        f"avant : visible={before['visible']} bas={before['panelBottom']} ; "
        f"après hover : visible={after['visible']} bas={after['panelBottom']} "
        f"hit={after['hitDesc']}",
    )
    close_overlays(page, "sel-hover")

    # PROD : hoverable + swap actif. Le clic du trigger met FORCÉMENT la
    # souris sur la card → lift actif au moment du positionnement. Si le
    # panel n'est pas ancré sous son trigger ici, c'est un bug de prod
    # latent (containing block du hover lift), indépendant du swap.
    open_select(page, "sel-hover-prod")
    m = page.evaluate(_MEASURE, ["card-hover-prod", "sel-hover-prod"])
    info("hover-prod — ancrage", f"panel top={m['panelTop']} vs trigger bas={m['triggerBottom']} "
         f"translate={m['cardTranslate']}")
    check(
        "hover-PROD — panel ancré sous son trigger et visible",
        m["anchored"] and m["visible"],
        f"anchored={m['anchored']} visible={m['visible']} "
        f"panel top={m['panelTop']} trigger bas={m['triggerBottom']} hit={m['hitDesc']}",
    )
    close_overlays(page, "sel-hover-prod")


def probe_combobox_bubble(page) -> None:
    print("\n-- B. Combobox open/close bullants dans un Dialog --")

    posts: list[str] = []
    page.on(
        "response",
        lambda r: posts.append(f"{r.url.split('::')[-1]}={r.status}")
        if "/_bretzel/action" in r.url and r.request.method == "POST"
        else None,
    )

    page.click("#btn-dialog")
    page.wait_for_timeout(1200)
    n0 = len(posts)
    log0 = page.locator(".evt").all_text_contents()
    evlog_html = page.evaluate(
        "() => (document.getElementById('evlog') || {}).outerHTML || 'ABSENT'"
    )[:200]
    dialog_open = page.evaluate(
        "() => !!document.querySelector('[role=dialog]')"
        "  && getComputedStyle(document.querySelector('[role=dialog]')).display !== 'none'"
    )
    info("après clic — dialog / POSTs / log / zone",
         f"dialog={dialog_open} posts={posts} log={log0} evlog={evlog_html!r}")
    check("ouvrir le dialog log EXACTEMENT un 'open'",
          [t.split(". ")[1] for t in log0] == ["open"],
          f"log={log0} posts={posts} dialog_visible={dialog_open}")

    # Ouvre le panel du combobox DANS le dialog.
    page.click("#cb-in-dialog input")
    page.keyboard.type("It")
    page.wait_for_timeout(600)
    n1 = len(posts)
    log1 = page.locator(".evt").all_text_contents()
    check(
        "ouvrir le PANEL du combobox ne fire AUCUN POST parasite",
        n1 == n0,
        f"POSTs avant={n0} après : {posts} ; log={log1}",
    )

    # Ferme le panel du combobox (Escape). ⚠️ Échap ferme AUSSI le dialog :
    # un `close` du dialog est alors le SIEN, pas une fuite. Et un dialog
    # fermé garde `display: flex` — il part en `visibility: hidden;
    # opacity: 0`, donc un test sur `display` seul le voit encore ouvert
    # et transforme sa fermeture normale en fuite.
    page.keyboard.press("Escape")
    page.wait_for_timeout(600)
    n2 = len(posts)
    log2 = page.locator(".evt").all_text_contents()
    dialog_still_open = page.evaluate(
        "() => { const d = document.querySelector('[role=dialog]');"
        "  if (!d) return false;"
        "  const cs = getComputedStyle(d);"
        "  return cs.display !== 'none' && cs.visibility !== 'hidden'"
        "    && cs.opacity !== '0'; }"
    )
    leaked = "close" in [t.split(". ")[1] for t in log2] and dialog_still_open
    check(
        "fermer le panel du combobox ne fait pas fuir de 'close'",
        not leaked and n2 - n1 <= 1,
        f"dialog encore ouvert={dialog_still_open} ; POSTs : {posts} ; log={log2}",
    )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, str(HERE / "bench_overflow_card.py"), str(PORT)],
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
            print("le bench n'a pas démarré sur :8963")
            return 1

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1200})
            console_errors: list[str] = []
            page.on("console", lambda m: (
                console_errors.append(m.text) if m.type == "error" else None
            ))
            page.goto(BASE)
            page.wait_for_selector("html.bz-ready", timeout=15000)

            probe_overflow(page)
            probe_combobox_bubble(page)

            print()
            check("zéro erreur console", not console_errors, "; ".join(console_errors[:6]))
            page.screenshot(path=str(HERE / "overflow_card_screenshot.png"), full_page=True)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    print()
    if FAILURES:
        print(f"OVERFLOW/BUBBLE PROBE — {len(FAILURES)} probe(s) rouge(s) :")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("OVERFLOW/BUBBLE PROBE PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Runtime probe for the MODAL overlays (Dialog / Drawer) enter/leave
animations — the V3 migration replaced Alpine x-transition with a display
toggle (bz-show), killing the animations. They now animate CSS-only off
``data-open`` ; this probe confirms the fade/scale (dialog) and slide
(drawer) actually run, caught mid-flight.

Run :  py tests/probes/probe_modals.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from bretzel import runtime as _bz_runtime
from bretzel.components.base.testing import render_isolated
from bretzel.components.overlay.dialog import Dialog
from bretzel.components.overlay.drawer import Drawer
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.render.shell import (
    DEFAULT_HTMX_URL,
    DEFAULT_ICONIFY_URL,
    DEFAULT_IDIOMORPH_URL,
    default_shell,
)
from bretzel.theme import Theme
from tests.probes._serve import absolutise_vendor
import sys

HERE = Path(__file__).parent
# Le runtime se localise par le PAQUET, jamais en comptant des ``parents[N]``.
# Sept probes comptaient ``parents[3]`` et visaient
# ``<repo>/runtime/runtime.js`` — un niveau trop haut, vestige d'une
# disposition disparue. Le ``<script>`` 404ait donc en silence, ``$bz``
# n'existait jamais, et la page restait en ``visibility: hidden`` : les
# probes lisaient « l'élément n'est pas visible » et accusaient le
# composant. Trois d'entre eux passaient même au VERT sans runtime.
RUNTIME_JS = (Path(_bz_runtime.__file__).resolve().parent / "runtime.js").as_uri()


def page_html(kind: str) -> str:
    with render_isolated():
        if kind == "dialog":
            comp = Dialog(title="Test dialog")
            with comp:
                Text("Dialog body content.")
        else:
            comp = Drawer(title="Test drawer", side="right")
            with comp:
                Text("Drawer body content.")
        body = serialize(comp.render())
    return default_shell(
        body, envelope_json="", page_uuid=f"{kind}-probe", title=f"{kind} probe",
        browser_css=True, theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def panel_state(page):
    return page.evaluate(
        """() => {
            const p = document.querySelector('[role="dialog"]');
            if (!p) return null;
            const cs = getComputedStyle(p);
            const b = p.getBoundingClientRect();
            return { opacity: parseFloat(cs.opacity), visibility: cs.visibility,
                     x: b.x, transitionDuration: cs.transitionDuration }; }"""
    )


def dispatch(page, ev):
    page.evaluate(
        """(ev) => { const p = document.querySelector('[role="dialog"]');
            p.dispatchEvent(new CustomEvent(ev, {bubbles: true})); }""",
        ev,
    )


def run(kind, findings):
    html = HERE / f"_probe_{kind}.html"
    # Une page `file://` ne resout aucune route relative : le
    # compilateur rapatrie doit y etre absolu (cf. `_serve`).
    html.write_text(absolutise_vendor(page_html(kind)), encoding="utf-8")
    ok = True
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1100, "height": 800})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(html.as_uri())
        pg.evaluate("() => document.documentElement.classList.add('dark')")
        try:
            pg.wait_for_function("() => !!window.$bz", timeout=8000)
        except Exception:
            findings.append(f"!! [{kind}] runtime never booted"); b.close(); return False
        pg.wait_for_timeout(600)

        closed = panel_state(pg)
        c_ok = closed and (closed["visibility"] == "hidden" or closed["opacity"] < 0.05)
        has_transition = closed and closed["transitionDuration"] not in ("0s", "", "0ms")
        ok &= bool(c_ok and has_transition)
        findings.append(f"[{'OK' if c_ok else 'FAIL'}] [{kind}] closed = inert "
                        f"(vis={closed and closed['visibility']}, op={closed and closed['opacity']})")
        findings.append(f"[{'OK' if has_transition else 'FAIL'}] [{kind}] panel HAS a transition "
                        f"(duration={closed and closed['transitionDuration']})")

        # OPEN → catch mid-flight, then settled.
        dispatch(pg, "bz-open")
        pg.wait_for_timeout(90)
        mid = panel_state(pg)
        pg.wait_for_timeout(450)
        opened = panel_state(pg)
        if kind == "dialog":
            animating = mid and 0.05 < mid["opacity"] < 0.95
            settled = opened and opened["opacity"] > 0.95 and opened["visibility"] == "visible"
            detail = f"mid-opacity={mid and round(mid['opacity'],2)} -> settled op={opened and round(opened['opacity'],2)}"
        else:  # drawer slides : x moves from off-screen toward in-view
            animating = mid and opened and abs(mid["x"] - opened["x"]) > 20
            settled = opened and opened["visibility"] == "visible" and opened["opacity"] > 0.95
            detail = f"mid-x={mid and round(mid['x'])} -> settled x={opened and round(opened['x'])}"
        ok &= bool(animating and settled)
        findings.append(f"[{'OK' if animating else 'FAIL'}] [{kind}] ENTER animates ({detail})")
        findings.append(f"[{'OK' if settled else 'FAIL'}] [{kind}] settles open")

        # CLOSE → catch mid-flight leaving.
        dispatch(pg, "bz-close")
        pg.wait_for_timeout(90)
        midc = panel_state(pg)
        pg.wait_for_timeout(450)
        gone = panel_state(pg)
        if kind == "dialog":
            leaving = midc and 0.05 < midc["opacity"] < 0.95
        else:
            leaving = midc and gone and abs(midc["x"] - gone["x"]) > 20
        hidden = gone and (gone["visibility"] == "hidden" or gone["opacity"] < 0.05)
        ok &= bool(leaving and hidden)
        findings.append(f"[{'OK' if leaving else 'FAIL'}] [{kind}] LEAVE animates")
        findings.append(f"[{'OK' if hidden else 'FAIL'}] [{kind}] hidden after close")

        if kind == "dialog":
            dispatch(pg, "bz-open"); pg.wait_for_timeout(350)
            pg.screenshot(path=str(HERE / "probe_dialog_open.png"))
        if errs:
            findings.append(f"!! [{kind}] errors: {errs[:2]}"); ok = False
        b.close()
    return ok


def main() -> int:
    findings = []
    ok = True
    for kind in ("dialog", "drawer"):
        ok &= run(kind, findings)
    print("\n".join(findings))
    print("\n" + ("==> MODAL ANIMATIONS WORK" if ok else "==> SOME MODAL ANIMATIONS BROKEN"))

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

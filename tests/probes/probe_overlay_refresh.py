"""Reproduce the two overlay-in-refreshable bugs the user reported :

  1. POPOVER POSITIONING — open a popover, then simulate a server refresh
     (idiomorph morph of the subtree + htmx:afterSwap rescan, exactly what
     ``refresh(events_panel)`` does). The panel must STAY position:fixed at
     its floating coordinates. Bug = it loses its inline top/left/position
     (morph re-stamps the SSR ``display:none`` style) and the _bzFloat guard
     skips re-positioning, so it paints in normal flow ON TOP of the trigger.

  2. CLOSE EVENT — after the same morph, closing the overlay must still fire
     the ``close`` event (caught by bz-on:close) and actually hide the panel.

Run :  py tests/probes/probe_overlay_refresh.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from bretzel import runtime as _bz_runtime
from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.stack import VStack
from bretzel.components.overlay.dialog import Dialog
from bretzel.components.overlay.popover import Popover
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
HTML = HERE / "_probe_overlay_refresh.html"
# Le runtime se localise par le PAQUET, jamais en comptant des ``parents[N]``.
# Sept probes comptaient ``parents[3]`` et visaient
# ``<repo>/runtime/runtime.js`` — un niveau trop haut, vestige d'une
# disposition disparue. Le ``<script>`` 404ait donc en silence, ``$bz``
# n'existait jamais, et la page restait en ``visibility: hidden`` : les
# probes lisaient « l'élément n'est pas visible » et accusaient le
# composant. Trois d'entre eux passaient même au VERT sans runtime.
RUNTIME_JS = (Path(_bz_runtime.__file__).resolve().parent / "runtime.js").as_uri()


def render_popover() -> str:
    """The popover subtree, serialized — used both for the initial page
    AND as the 'refreshed' HTML fed to idiomorph (identical, like a
    refreshable that re-renders the same tree)."""
    with render_isolated():
        pop = Popover(
            trigger=Button("Open + close logger", color="primary"),
            id="evpop",
            on_open="window.__log.push('open')",
            on_close="window.__log.push('close')",
        )
        with pop:
            Text("Click outside or Escape to close.")
        return serialize(pop.render())


def render_dialog() -> str:
    with render_isolated():
        dlg = Dialog(
            title="Event dialog",
            id="evdlg",
            on_open="window.__log.push('dlg-open')",
            on_close="window.__log.push('dlg-close')",
        )
        with dlg:
            Text("Body")
        return serialize(dlg.render())


def build_page() -> str:
    pop_html = render_popover()
    dlg_html = render_dialog()
    with render_isolated():
        col = VStack(gap="xl", classes="p-16 items-start")
        body = serialize(col.render())
    # Inject the two overlay subtrees inside the column manually so the
    # surrounding wrapper has a known id we can morph.
    body = body.replace(
        "</div>",
        f'<div id="popwrap">{pop_html}</div>'
        f'<div id="dlgwrap">{dlg_html}</div></div>',
        1,
    )
    return default_shell(
        body,
        envelope_json="",
        page_uuid="overlay-refresh-probe",
        title="Overlay refresh probe",
        browser_css=True,
        theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def rect(page, sel):
    return page.evaluate(
        """(sel) => { const el = document.querySelector(sel); if (!el) return null;
           const cs = getComputedStyle(el); const b = el.getBoundingClientRect();
           return { display: cs.display, position: cs.position,
                    opacity: cs.opacity, visibility: cs.visibility,
                    dataOpen: el.getAttribute('data-open'),
                    top: b.top, left: b.left, w: b.width, h: b.height,
                    styleTop: el.style.top, styleLeft: el.style.left,
                    stylePos: el.style.position, styleDisplay: el.style.display }; }""",
        sel,
    )


def visible(s):
    return s is not None and s["display"] != "none" and s["w"] > 0


def shown(s):
    """True visibility incl. opacity/visibility (dialog hides via CSS,
    not display)."""
    return (
        visible(s)
        and s["visibility"] != "hidden"
        and float(s["opacity"]) > 0.01
    )


def overlaps(a, b):
    """Do rects a and b overlap (panel covering trigger) ?"""
    if not a or not b:
        return False
    return not (
        a["left"] + a["w"] <= b["left"]
        or b["left"] + b["w"] <= a["left"]
        or a["top"] + a["h"] <= b["top"]
        or b["top"] + b["h"] <= a["top"]
    )


def simulate_refresh(page, wrap_sel, fresh_html):
    """Morph the wrapper's child subtree with fresh (identical) SSR HTML,
    then fire the bridge's afterSwap rescan — exactly what a server
    @refreshable refresh does."""
    page.evaluate(
        """([wrapSel, html]) => {
            const wrap = document.querySelector(wrapSel);
            // Idiomorph morphs innerHTML of the wrapper (children).
            Idiomorph.morph(wrap, html, { morphStyle: 'innerHTML' });
            document.body.dispatchEvent(new CustomEvent('htmx:afterSwap', {
                detail: { target: wrap }, bubbles: true,
            }));
        }""",
        [wrap_sel, fresh_html],
    )


def main() -> int:
    # Une page `file://` ne resout aucune route relative : le
    # compilateur rapatrie doit y etre absolu (cf. `_serve`).
    HTML.write_text(absolutise_vendor(build_page()), encoding="utf-8")
    pop_html = render_popover()
    dlg_html = render_dialog()
    findings: list[str] = []
    ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        page.on("console", lambda m: errors.append("console." + m.type + ": " + m.text)
                if m.type in ("error", "warning") else None)
        page.goto(HTML.as_uri())
        page.evaluate("() => { window.__log = []; document.documentElement.classList.add('dark'); }")
        page.wait_for_function("() => !!window.$bz", timeout=8000)
        page.wait_for_timeout(500)

        trig_sel = '#popwrap [bz-ref="bztrigger"] > *'
        # ⚠️ Le panneau est TÉLÉPORTÉ sous ``<body>`` à l'ouverture : un
        # sélecteur descendant de ``#popwrap`` ne le trouve plus, et
        # ``rect()`` rendait ``None`` — le probe plantait sur un
        # ``NoneType`` au lieu de mesurer. ``bz-ref="bzpanel"`` est le nom
        # que TOUT overlay ancré donne à son panneau (cf.
        # ``_wiring.anchored_dismiss_init``), donc il survit au voyage.
        panel_sel = '[bz-ref="bzpanel"]'

        def js_click(sel):
            page.evaluate("(s) => document.querySelector(s).click()", sel)

        # ── 1. Open the popover ──────────────────────────────────────
        js_click(trig_sel)
        page.wait_for_timeout(300)
        n_panels = page.locator(panel_sel).count()
        if n_panels != 1:
            findings.append(
                f"[FAIL] le panneau du popover n'est pas identifié sans "
                f"ambiguïté : {n_panels} nœud(s) matchent {panel_sel}"
            )
            ok = False
        trig = rect(page, trig_sel)
        before = rect(page, panel_sel)
        open_ok = visible(before) and before["position"] == "fixed"
        cover_before = overlaps(before, trig)
        findings.append(
            f"[{'OK' if open_ok and not cover_before else 'FAIL'}] popover open: "
            f"fixed={before['position']=='fixed'} visible={visible(before)} "
            f"covers_trigger={cover_before} top={before['top']:.0f} left={before['left']:.0f}"
        )
        ok &= open_ok and not cover_before

        # ── 2. Simulate the on_open refresh (morph) ─────────────────
        simulate_refresh(page, "#popwrap", pop_html)
        page.wait_for_timeout(300)
        after = rect(page, panel_sel)
        trig2 = rect(page, trig_sel)
        still_fixed = after and after["position"] == "fixed"
        cover_after = overlaps(after, trig2)
        bug1 = (not still_fixed) or cover_after
        findings.append(
            f"[{'FAIL' if bug1 else 'OK'}] popover AFTER refresh: "
            f"visible={visible(after)} pos={after['position'] if after else None} "
            f"stylePos='{after['stylePos'] if after else ''}' "
            f"styleTop='{after['styleTop'] if after else ''}' "
            f"styleDisplay='{after['styleDisplay'] if after else ''}' "
            f"covers_trigger={cover_after}"
        )
        ok &= not bug1

        # ── 3. Close event after refresh (click trigger to toggle) ──
        log_before = page.evaluate("() => window.__log.slice()")
        js_click(trig_sel)
        page.wait_for_timeout(300)
        closed = rect(page, panel_sel)
        log_after = page.evaluate("() => window.__log.slice()")
        fired_close = "close" in log_after and log_after.count("close") > log_before.count("close")
        hid = not visible(closed)
        bug2 = not (fired_close and hid)
        findings.append(
            f"[{'FAIL' if bug2 else 'OK'}] popover close after refresh: "
            f"close_event_fired={fired_close} panel_hidden={hid} log={log_after}"
        )
        ok &= not bug2

        # ── 4. DIALOG : open (imperative) → refresh → close via × ───
        page.evaluate("() => window.__log.length = 0")
        page.evaluate(
            "() => document.getElementById('evdlg').dispatchEvent("
            "new CustomEvent('bz-open', {bubbles:true}))"
        )
        page.wait_for_timeout(300)
        dlg_panel = '#dlgwrap [role="dialog"]'
        d_open = rect(page, dlg_panel)
        log_open = page.evaluate("() => window.__log.slice()")
        findings.append(
            f"[{'OK' if shown(d_open) and 'dlg-open' in log_open else 'FAIL'}] "
            f"dialog open: shown={shown(d_open)} dataOpen={d_open['dataOpen']} log={log_open}"
        )

        simulate_refresh(page, "#dlgwrap", dlg_html)
        page.wait_for_timeout(300)
        d_after = rect(page, dlg_panel)
        findings.append(
            f"[{'OK' if shown(d_after) else 'FAIL'}] dialog stays open after refresh: "
            f"shown={shown(d_after)} dataOpen={d_after['dataOpen']}"
        )

        log_pre_close = page.evaluate("() => window.__log.slice()")
        page.evaluate("() => document.querySelector('#dlgwrap [aria-label=\"Close\"]').click()")
        page.wait_for_timeout(300)
        d_closed = rect(page, dlg_panel)
        log_post = page.evaluate("() => window.__log.slice()")
        d_close_fired = log_post.count("dlg-close") > log_pre_close.count("dlg-close")
        d_hid = not shown(d_closed)
        findings.append(
            f"[{'FAIL' if not (d_close_fired and d_hid) else 'OK'}] dialog close after refresh: "
            f"close_event_fired={d_close_fired} hidden={d_hid} "
            f"dataOpen={d_closed['dataOpen']} opacity={d_closed['opacity']} "
            f"visibility={d_closed['visibility']} log={log_post}"
        )
        ok &= d_close_fired and d_hid

        if errors:
            findings.append("!! page errors: " + " | ".join(dict.fromkeys(errors))[:400])
            ok = False

        browser.close()

    print("\n".join(findings))
    print("\n" + ("==> NO BUG REPRODUCED" if ok else "==> BUG(S) REPRODUCED"))

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

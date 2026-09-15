"""Verify a single overlay can wire BOTH on_open AND on_close to the
SERVER (the second handler rides a hidden HTMX carrier listening for the
event ``from:#<root>``). We render server handlers, intercept the action
POSTs (fulfilling them so HTMX is happy), and assert :

  - opening the overlay POSTs to the on_open action (root hx-post),
  - closing it POSTs to the on_close action (the CARRIER),
  - the carrier still fires after a refresh (idiomorph morph + rescan).

Run :  py tests/probes/probe_overlay_dual_event.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from bretzel import runtime as _bz_runtime

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.stack import VStack
from bretzel.components.overlay.dialog import Dialog
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

HERE = Path(__file__).parent
HTML = HERE / "_probe_overlay_dual_event.html"
# Le runtime se localise par le PAQUET, jamais en comptant des ``parents[N]``.
# Sept probes comptaient ``parents[3]`` et visaient
# ``<repo>/runtime/runtime.js`` — un niveau trop haut, vestige d'une
# disposition disparue. Le ``<script>`` 404ait donc en silence, ``$bz``
# n'existait jamais, et la page restait en ``visibility: hidden`` : les
# probes lisaient « l'élément n'est pas visible » et accusaient le
# composant. Trois d'entre eux passaient même au VERT sans runtime.
RUNTIME_JS = (Path(_bz_runtime.__file__).resolve().parent / "runtime.js").as_uri()


# Distinct functions → distinct action ids → distinguishable POST URLs.
def dlg_open() -> None: ...
def dlg_close() -> None: ...


def render_dialog() -> str:
    with render_isolated():
        dlg = Dialog(title="Dual", id="evdlg", on_open=dlg_open, on_close=dlg_close)
        with dlg:
            Text("Body")
        return serialize(dlg.render())


def build_page() -> str:
    dlg_html = render_dialog()
    with render_isolated():
        col = VStack(gap="xl", classes="p-16 items-start")
        body = serialize(col.render())
    body = body.replace("</div>", f'<div id="dlgwrap">{dlg_html}</div></div>', 1)
    return default_shell(
        body,
        envelope_json="",
        page_uuid="dual-event-probe",
        title="Dual event probe",
        browser_css=True,
        theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def main() -> int:
    # Une page `file://` ne resout aucune route relative : le
    # compilateur rapatrie doit y etre absolu (cf. `_serve`).
    HTML.write_text(absolutise_vendor(build_page()), encoding="utf-8")
    dlg_html = render_dialog()
    findings: list[str] = []
    ok = True
    posts: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        # Intercept the action POSTs : record the URL, fulfill with an
        # empty 200 so HTMX swaps nothing and stays quiet.
        def handle(route):
            req = route.request
            if req.method == "POST" and "/_bretzel/action/" in req.url:
                posts.append(req.url)
                route.fulfill(status=200, content_type="text/html", body="")
            else:
                route.continue_()

        page.route("**/*", handle)
        page.goto(HTML.as_uri())
        page.evaluate("() => document.documentElement.classList.add('dark')")
        page.wait_for_function("() => !!window.$bz", timeout=8000)
        page.wait_for_timeout(400)

        def open_dlg():
            page.evaluate(
                "() => document.getElementById('evdlg').dispatchEvent("
                "new CustomEvent('bz-open', {bubbles:true}))"
            )
            page.wait_for_timeout(300)

        def close_dlg():
            page.evaluate(
                "() => document.querySelector('#dlgwrap [aria-label=\"Close\"]').click()"
            )
            page.wait_for_timeout(300)

        # ── open → expect a POST to dlg_open ─────────────────────────
        posts.clear()
        open_dlg()
        opened_posted = any("dlg_open" in u for u in posts)
        findings.append(
            f"[{'OK' if opened_posted else 'FAIL'}] open → server POST(on_open): {posts}"
        )
        ok &= opened_posted

        # ── close → expect a POST to dlg_close (the CARRIER) ────────
        posts.clear()
        close_dlg()
        closed_posted = any("dlg_close" in u for u in posts)
        findings.append(
            f"[{'FAIL' if not closed_posted else 'OK'}] close → server POST(on_close via carrier): {posts}"
        )
        ok &= closed_posted

        # ── after a refresh : carrier must still fire on close ──────
        open_dlg()
        page.evaluate(
            """([html]) => {
                const wrap = document.querySelector('#dlgwrap');
                Idiomorph.morph(wrap, html, { morphStyle: 'innerHTML' });
                document.body.dispatchEvent(new CustomEvent('htmx:afterSwap', {
                    detail: { target: wrap }, bubbles: true }));
            }""",
            [dlg_html],
        )
        page.wait_for_timeout(300)
        posts.clear()
        close_dlg()
        closed_after_refresh = any("dlg_close" in u for u in posts)
        findings.append(
            f"[{'FAIL' if not closed_after_refresh else 'OK'}] close after refresh → "
            f"carrier still POSTs(on_close): {posts}"
        )
        ok &= closed_after_refresh

        if errors:
            findings.append("!! page errors: " + " | ".join(dict.fromkeys(errors))[:400])
            ok = False
        browser.close()

    print("\n".join(findings))
    print("\n" + ("==> DUAL SERVER EVENTS WORK" if ok else "==> DUAL SERVER EVENTS BROKEN"))

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

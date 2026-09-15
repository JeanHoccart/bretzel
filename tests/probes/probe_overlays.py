"""Runtime behaviour probe for the anchored overlays (Dropdown / Popover /
Tooltip) — boots the FULL runtime and drives each : open-on-click (dropdown,
popover) or show-on-hover (tooltip), position:fixed via floating, and
dismiss. These were ported from Alpine to the bz-* runtime but never
exercised end-to-end.

Run :  py tests/probes/probe_overlays.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from bretzel import runtime as _bz_runtime
from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.stack import VStack
from bretzel.components.overlay.dropdown import Dropdown, DropdownItem
from bretzel.components.overlay.popover import Popover
from bretzel.components.overlay.tooltip import Tooltip
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
HTML = HERE / "_probe_overlays.html"
# Le runtime se localise par le PAQUET, jamais en comptant des ``parents[N]``.
# Sept probes comptaient ``parents[3]`` et visaient
# ``<repo>/runtime/runtime.js`` — un niveau trop haut, vestige d'une
# disposition disparue. Le ``<script>`` 404ait donc en silence, ``$bz``
# n'existait jamais, et la page restait en ``visibility: hidden`` : les
# probes lisaient « l'élément n'est pas visible » et accusaient le
# composant. Trois d'entre eux passaient même au VERT sans runtime.
RUNTIME_JS = (Path(_bz_runtime.__file__).resolve().parent / "runtime.js").as_uri()


def build_page() -> str:
    with render_isolated():
        col = VStack(gap="xl", classes="p-16 items-start")
        with col:
            dd = Dropdown(
                trigger=IconButton("more-horizontal", aria_label="dd-trigger")
            )
            with dd:
                DropdownItem(label="Edit", icon_left="pencil")
                DropdownItem(label="Delete", icon_left="trash-2", color="error")
            pop = Popover(trigger=IconButton("info", aria_label="pop-trigger"))
            with pop:
                Text("Popover body content here.")
            tip = Tooltip("A helpful tip.")
            with tip:
                IconButton("help-circle", aria_label="tip-trigger")
        body = serialize(col.render())
    return default_shell(
        body,
        envelope_json="",
        page_uuid="overlay-probe",
        title="Overlay probe",
        browser_css=True,
        theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def state(page, sel):
    return page.evaluate(
        """(sel) => { const el = document.querySelector(sel); if (!el) return null;
           const cs = getComputedStyle(el);
           const b = el.getBoundingClientRect();
           return { display: cs.display, position: cs.position, w: b.width, h: b.height }; }""",
        sel,
    )


def visible(s):
    return s is not None and s["display"] != "none" and s["w"] > 0


def main() -> int:
    # Une page `file://` ne resout aucune route relative : le
    # compilateur rapatrie doit y etre absolu (cf. `_serve`).
    HTML.write_text(absolutise_vendor(build_page()), encoding="utf-8")
    findings: list[str] = []
    ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(HTML.as_uri())
        page.evaluate("() => document.documentElement.classList.add('dark')")
        try:
            page.wait_for_function("() => !!window.$bz", timeout=8000)
        except Exception:
            findings.append("!! runtime never booted ($bz absent)")
            ok = False
        page.wait_for_timeout(700)

        def click_open_close(name, trigger_sel, panel_sel):
            nonlocal ok
            closed0 = state(page, panel_sel)
            c0 = not visible(closed0)
            page.click(trigger_sel)
            page.wait_for_timeout(350)
            opened = state(page, panel_sel)
            op = visible(opened) and opened["position"] == "fixed"
            # dismiss by clicking far away
            page.mouse.click(1000, 850)
            page.wait_for_timeout(350)
            closed1 = state(page, panel_sel)
            c1 = not visible(closed1)
            good = c0 and op and c1
            ok &= good
            findings.append(
                f"[{'OK' if good else 'FAIL'}] {name}: closed0={c0} "
                f"open(fixed)={op} dismissed={c1}"
            )

        click_open_close("dropdown", 'button[aria-label="dd-trigger"]', '[role="menu"]')
        click_open_close("popover", 'button[aria-label="pop-trigger"]', '[role="dialog"]')

        # Tooltip : hover shows (after the debounce), move-away hides.
        tip_closed0 = not visible(state(page, '[role="tooltip"]'))
        page.hover('button[aria-label="tip-trigger"]')
        page.wait_for_timeout(600)  # > 300ms delay
        tip_open = state(page, '[role="tooltip"]')
        tip_shows = visible(tip_open) and tip_open["position"] == "fixed"
        page.mouse.move(20, 20)
        page.wait_for_timeout(500)
        tip_hidden = not visible(state(page, '[role="tooltip"]'))
        tip_good = tip_closed0 and tip_shows and tip_hidden
        ok &= tip_good
        findings.append(
            f"[{'OK' if tip_good else 'FAIL'}] tooltip: closed0={tip_closed0} "
            f"show-on-hover(fixed)={tip_shows} hide-on-leave={tip_hidden}"
        )

        if errors:
            findings.append("!! page errors: " + " | ".join(dict.fromkeys(errors))[:300])
            ok = False

        browser.close()

    print("\n".join(findings))
    print("\n" + ("==> ALL OVERLAYS WORK" if ok else "==> SOME OVERLAYS BROKEN"))

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

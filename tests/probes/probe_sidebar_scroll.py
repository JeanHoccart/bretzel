"""Runtime probe : the sidebar FOOTER stays pinned while an overflowing
nav list scrolls inside its own middle region.

The bug it guards : ``overflow-y-auto`` used to live on the ``<aside>``
itself, so a long item list scrolled the whole column — footer included.
The fix moves the scroll to a ``flex-1 min-h-0`` middle box ; title +
footer are ``shrink-0`` siblings. This MEASURES, with the real runtime
booted and a viewport short enough to force overflow :

  • the middle box actually overflows (scrollHeight > clientHeight),
  • the footer sits at the viewport bottom and is fully visible,
  • after scrolling the middle to the end, the footer AND title bounding
    boxes are UNCHANGED (they didn't scroll away).

Run :  py tests/probes/probe_sidebar_scroll.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from bretzel import runtime as _bz_runtime
from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.sidebar import (
    Sidebar,
    SidebarFooter,
    SidebarFooterItem,
    SidebarItem,
    SidebarSection,
    SidebarTitle,
)
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
HTML = HERE / "_probe_sidebar_scroll.html"
# Le runtime se localise par le PAQUET, jamais en comptant des ``parents[N]``.
# Sept probes comptaient ``parents[3]`` et visaient
# ``<repo>/runtime/runtime.js`` — un niveau trop haut, vestige d'une
# disposition disparue. Le ``<script>`` 404ait donc en silence, ``$bz``
# n'existait jamais, et la page restait en ``visibility: hidden`` : les
# probes lisaient « l'élément n'est pas visible » et accusaient le
# composant. Trois d'entre eux passaient même au VERT sans runtime.
RUNTIME_JS = (Path(_bz_runtime.__file__).resolve().parent / "runtime.js").as_uri()


def build() -> str:
    with render_isolated():
        with Sidebar() as s:
            SidebarTitle("Flat app", icon="box")
            with SidebarSection(label="MAIN"):
                # Enough rows to overflow a short viewport.
                for i in range(40):
                    SidebarItem(f"Item {i}", icon="circle", href=f"/i{i}")
            with SidebarFooter(name="Jean Hoccart", subtitle="jean@acme.com"):
                SidebarFooterItem(label="Settings", icon_left="settings", href="/me")
                SidebarFooterItem(label="Log out", icon_left="log-out", color="error")
        body = serialize(s.render())
    return default_shell(
        body, envelope_json="", page_uuid="sbscroll", title="sidebar scroll",
        browser_css=True, theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def rect(page, selector_js: str):
    return page.evaluate(
        "(js) => { const el = eval(js); if (!el) return null;"
        " const r = el.getBoundingClientRect();"
        " return {top: r.top, bottom: r.bottom, height: r.height,"
        "         sh: el.scrollHeight, ch: el.clientHeight}; }",
        selector_js,
    )


# DOM handles : aside, the scroll box (flex-1 min-h-0), the footer (mt-auto),
# the title (the brand row), all addressed structurally.
ASIDE = "document.querySelector('aside')"
SCROLL = "document.querySelector('aside > div.min-h-0')"
FOOTER = "document.querySelector('aside > div.mt-auto')"
TITLE = "document.querySelector('aside > div.flex-row')"


def main() -> int:
    # Une page `file://` ne resout aucune route relative : le
    # compilateur rapatrie doit y etre absolu (cf. `_serve`).
    HTML.write_text(absolutise_vendor(build()), encoding="utf-8")
    findings = []
    ok = True
    with sync_playwright() as p:
        b = p.chromium.launch()
        # SHORT viewport so 40 items must overflow.
        pg = b.new_page(viewport={"width": 1100, "height": 500})
        pg.goto(HTML.as_uri())
        pg.evaluate("() => document.documentElement.classList.add('dark')")
        try:
            pg.wait_for_function("() => !!window.$bz", timeout=8000)
        except Exception:
            print("!! runtime never booted"); b.close(); return
        pg.wait_for_timeout(400)

        vh = pg.evaluate("() => window.innerHeight")
        scroll0 = rect(pg, SCROLL)
        footer0 = rect(pg, FOOTER)
        title0 = rect(pg, TITLE)

        # 1. middle overflows
        overflows = bool(scroll0 and scroll0["sh"] > scroll0["ch"] + 1)
        findings.append(
            f"[{'OK' if overflows else 'FAIL'}] middle overflows : "
            f"scrollHeight={scroll0 and scroll0['sh']} > clientHeight={scroll0 and scroll0['ch']}"
        )
        ok &= overflows

        # 2. footer fully visible, glued to the viewport bottom
        footer_visible = bool(
            footer0 and footer0["bottom"] <= vh + 1 and footer0["top"] >= 0
        )
        footer_at_bottom = bool(footer0 and abs(footer0["bottom"] - vh) <= 12)
        findings.append(
            f"[{'OK' if footer_visible and footer_at_bottom else 'FAIL'}] footer pinned bottom : "
            f"footer.bottom={footer0 and round(footer0['bottom'])} vh={vh}"
        )
        ok &= footer_visible and footer_at_bottom

        # 3. scroll the middle to the END, then re-measure footer + title
        pg.evaluate(f"() => {{ const el = {SCROLL}; el.scrollTop = el.scrollHeight; }}")
        pg.wait_for_timeout(200)
        footer1 = rect(pg, FOOTER)
        title1 = rect(pg, TITLE)
        footer_static = bool(
            footer0 and footer1 and abs(footer0["top"] - footer1["top"]) <= 1
        )
        title_static = bool(
            title0 and title1 and abs(title0["top"] - title1["top"]) <= 1
        )
        findings.append(
            f"[{'OK' if footer_static else 'FAIL'}] footer DID NOT move on scroll : "
            f"top {footer0 and round(footer0['top'])} -> {footer1 and round(footer1['top'])}"
        )
        findings.append(
            f"[{'OK' if title_static else 'FAIL'}] title DID NOT move on scroll : "
            f"top {title0 and round(title0['top'])} -> {title1 and round(title1['top'])}"
        )
        ok &= footer_static and title_static

        pg.screenshot(path=str(HERE / "sidebar_scroll_screenshot.png"))
        b.close()

    print("\n".join(findings))
    print("\n" + ("==> FOOTER PINNED, MIDDLE SCROLLS" if ok else "==> STILL BROKEN"))

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

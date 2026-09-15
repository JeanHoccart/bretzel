"""Runtime probe : dropdown item HOVER works for BOTH a button row
(on_click) and a LINK row (href → <a>). The bug : ``enabled:hover:`` only
matches form controls, so link items lost their hover bg. This confirms
the plain-``hover:`` fix tints both on hover and neither at rest.

Run :  py tests/probes/probe_dropdown_hover.py
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from bretzel import runtime as _bz_runtime
from bretzel.components.actions.icon_button import IconButton
from bretzel.components.base.testing import render_isolated
from bretzel.components.overlay.dropdown import Dropdown, DropdownItem
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
HTML = HERE / "_probe_dropdown_hover.html"
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
        d = Dropdown(trigger=IconButton("more-horizontal", aria_label="trig"))
        with d:
            DropdownItem(label="Edit", icon_left="pencil")          # button (on_click-less)
            DropdownItem(label="Profile", icon_left="user", href="/me")  # LINK
            DropdownItem(label="Delete", icon_left="trash-2", color="error", href="/x")  # LINK + color
        body = serialize(d.render())
    return default_shell(
        body, envelope_json="", page_uuid="ddh", title="dropdown hover",
        browser_css=True, theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def bg(page, text):
    return page.evaluate(
        """(t) => { const el = [...document.querySelectorAll('[role="menuitem"]')]
              .find(e => e.textContent.includes(t));
            if (!el) return null;
            return { tag: el.tagName, bg: getComputedStyle(el).backgroundColor }; }""",
        text,
    )


def opaque(c):
    # non-transparent background = the hover tint is applied
    return c and c["bg"] not in ("rgba(0, 0, 0, 0)", "transparent")


def main() -> int:
    # Une page `file://` ne resout aucune route relative : le
    # compilateur rapatrie doit y etre absolu (cf. `_serve`).
    HTML.write_text(absolutise_vendor(build()), encoding="utf-8")
    findings = []
    ok = True
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 900, "height": 700})
        pg.goto(HTML.as_uri())
        pg.evaluate("() => document.documentElement.classList.add('dark')")
        try:
            pg.wait_for_function("() => !!window.$bz", timeout=8000)
        except Exception:
            print("!! runtime never booted"); b.close(); return
        pg.wait_for_timeout(500)
        pg.click('button[aria-label="trig"]')
        pg.wait_for_timeout(350)

        for label, is_link in [("Edit", False), ("Profile", True), ("Delete", True)]:
            at_rest = bg(pg, label)
            rest_clear = not opaque(at_rest)
            # hover by moving the mouse to the row centre
            pg.evaluate(
                """(t) => { const el = [...document.querySelectorAll('[role="menuitem"]')]
                      .find(e => e.textContent.includes(t)); el.scrollIntoView(); }""",
                label,
            )
            box = pg.evaluate(
                """(t) => { const el = [...document.querySelectorAll('[role="menuitem"]')]
                      .find(e => e.textContent.includes(t)); const b = el.getBoundingClientRect();
                    return {x: b.x + b.width/2, y: b.y + b.height/2}; }""",
                label,
            )
            pg.mouse.move(box["x"], box["y"])
            pg.wait_for_timeout(150)
            hovered = bg(pg, label)
            tag = (hovered or {}).get("tag")
            hov_ok = opaque(hovered)
            good = rest_clear and hov_ok
            ok &= good
            findings.append(
                f"[{'OK' if good else 'FAIL'}] {label} ({tag}, link={is_link}) : "
                f"rest={at_rest and at_rest['bg']} -> hover={hovered and hovered['bg']}"
            )
            pg.mouse.move(10, 10)
            pg.wait_for_timeout(100)
        b.close()
    print("\n".join(findings))
    print("\n" + ("==> HOVER WORKS ON BUTTON + LINK ITEMS" if ok else "==> HOVER STILL BROKEN"))

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

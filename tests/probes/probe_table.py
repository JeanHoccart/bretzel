"""Visual + interaction probe for the rebuilt ``Table``.

Verifies the three things the user asked for :

  1. HOVER applies to EVERY row, not 1-out-of-2. With striped on, the
     even rows used to keep their zebra background on hover (equal CSS
     specificity → striped won), so only odd rows lit up. After the
     ``!important`` fix both odd AND even rows must change on hover.
  2. COLOR tints the header (``bg-<color>/5``).
  3. CLICKABLE rows POST on a click in a blank cell, but a click on an
     interactive child (the actions button) does NOT fire the row click.

Boots the full runtime + the in-browser Tailwind v4 compiler (so the
arbitrary utility classes actually compile), then drives the table.

Run :  py tests/probes/probe_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from bretzel import runtime as _bz_runtime
from bretzel.components.actions.button import Button
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.table import Table, column
from bretzel.components.layout.stack import VStack
from bretzel.core.serialize import serialize
from bretzel.render.shell import (
    DEFAULT_HTMX_URL,
    DEFAULT_ICONIFY_URL,
    DEFAULT_IDIOMORPH_URL,
    default_shell,
)
from bretzel.theme import Theme
from tests.probes._serve import absolutise_vendor

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
HTML = HERE / "_probe_table.html"
# Le runtime se localise par le PAQUET, jamais en comptant des ``parents[N]``.
# Sept probes comptaient ``parents[3]`` et visaient
# ``<repo>/runtime/runtime.js`` — un niveau trop haut, vestige d'une
# disposition disparue. Le ``<script>`` 404ait donc en silence, ``$bz``
# n'existait jamais, et la page restait en ``visibility: hidden`` : les
# probes lisaient « l'élément n'est pas visible » et accusaient le
# composant. Trois d'entre eux passaient même au VERT sans runtime.
RUNTIME_JS = (Path(_bz_runtime.__file__).resolve().parent / "runtime.js").as_uri()


def row_action(id) -> None:  # noqa: A002 - mirrors a real handler signature
    ...


ROWS = [
    {"id": 1, "title": "Alpha"},
    {"id": 2, "title": "Bravo"},
    {"id": 3, "title": "Charlie"},
    {"id": 4, "title": "Delta"},
]


def _action_cell(_value, row):
    return Button("Act", id=f"act-{row['id']}", size="sm", variant="ghost")


COLORS = ["primary", "secondary", "success", "warning",
          "error", "info", "muted"]


def build_page() -> str:
    with render_isolated():
        col = VStack(gap="xl", classes="p-16")
        with col:
            # Striped + hover are the baked-in default look → the
            # 1-out-of-2 hover test runs on a plain table.
            Table(
                columns=[column("id", label="#"), column("title", label="Title")],
                rows=ROWS, id="hovertbl", color="success",
            )
            # Clickable table with an action button in a cell.
            Table(
                columns=[
                    column("id", label="#"),
                    column("title", label="Title"),
                    column("", label="", render=_action_cell),
                ],
                rows=ROWS, id="clicktbl",
                on_item_click=row_action,
            )
            # One table per colour → header-tint distinctness probe.
            for c in COLORS:
                Table(
                    columns=[column("id", label="#"), column("title", label="T")],
                    rows=ROWS[:1], id=f"ctbl-{c}", color=c,
                )
        body = serialize(col.render())
    return default_shell(
        body,
        envelope_json="",
        page_uuid="table-probe",
        title="Table probe",
        browser_css=True,
        theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def bg(page, sel):
    return page.evaluate(
        "(s) => { const el = document.querySelector(s);"
        " return el ? getComputedStyle(el).backgroundColor : null; }",
        sel,
    )


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

        posts: list[str] = []

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
        # Wait for the in-browser Tailwind compiler to paint the header
        # tint (proof utilities have compiled).
        try:
            page.wait_for_function(
                "() => { const h = document.querySelector('#hovertbl thead');"
                " if (!h) return false; const c = getComputedStyle(h).backgroundColor;"
                " return c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent'; }",
                timeout=15000,
            )
        except Exception:
            findings.append("!! Tailwind header tint never compiled (color test inconclusive)")

        # ── 1. HOVER on every row (odd + even) ───────────────────────
        odd_sel = "#hovertbl tbody tr:nth-child(1)"   # odd  (no stripe)
        even_sel = "#hovertbl tbody tr:nth-child(2)"  # even (striped)
        odd_rest, even_rest = bg(page, odd_sel), bg(page, even_sel)
        page.hover(odd_sel)
        page.wait_for_timeout(150)
        odd_hover = bg(page, odd_sel)
        page.hover(even_sel)
        page.wait_for_timeout(150)
        even_hover = bg(page, even_sel)
        odd_changed = odd_hover != odd_rest
        even_changed = even_hover != even_rest          # THE bug : was False before
        same_hover = odd_hover == even_hover            # uniform hover colour
        hover_ok = odd_changed and even_changed and same_hover
        ok &= hover_ok
        findings.append(
            f"[{'OK' if hover_ok else 'FAIL'}] hover on every row: "
            f"odd {odd_rest}->{odd_hover} (changed={odd_changed}) | "
            f"even {even_rest}->{even_hover} (changed={even_changed}) | "
            f"uniform={same_hover}"
        )

        # ── 2. COLOR header tint ─────────────────────────────────────
        head_bg = bg(page, "#hovertbl thead")
        color_ok = head_bg not in (None, "rgba(0, 0, 0, 0)", "transparent")
        ok &= color_ok
        findings.append(
            f"[{'OK' if color_ok else 'FAIL'}] header colour tint: {head_bg}"
        )

        # ── 3. CLICKABLE rows + interactive-child guard ──────────────
        posts.clear()
        page.eval_on_selector("#clicktbl tbody tr:nth-child(1) td:nth-child(2)",
                              "el => el.click()")
        page.wait_for_timeout(200)
        row_posted = len(posts)
        posts.clear()
        page.eval_on_selector("#act-2", "el => el.click()")
        page.wait_for_timeout(200)
        btn_posted = len(posts)
        click_ok = row_posted == 1 and btn_posted == 0
        ok &= click_ok
        findings.append(
            f"[{'OK' if click_ok else 'FAIL'}] clickable rows: "
            f"click_row_cell->posts={row_posted} (want 1), "
            f"click_action_button->posts={btn_posted} (want 0, guard)"
        )

        # ── 4. COLOR distinctness across the 7 header tints ──────────
        tints = [bg(page, f"#ctbl-{c} thead") for c in COLORS]
        distinct = len(set(tints)) == len(tints)
        ok &= distinct
        findings.append(
            f"[{'OK' if distinct else 'FAIL'}] header-tint distinctness: "
            f"{len(set(tints))}/{len(tints)} distinct"
        )

        # ── 5. No double scrollbar (viewport sanity) ─────────────────
        overflow = page.evaluate(
            "() => document.body.scrollWidth - document.body.clientWidth"
        )
        no_xscroll = overflow <= 0
        ok &= no_xscroll
        findings.append(
            f"[{'OK' if no_xscroll else 'FAIL'}] no horizontal scrollbar: "
            f"overflow={overflow}px"
        )

        if errors:
            findings.append("!! page errors: " + " | ".join(dict.fromkeys(errors))[:400])
            ok = False
        browser.close()

    print("\n".join(findings))
    print("\n" + ("==> TABLE OK" if ok else "==> TABLE HAS ISSUES"))

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

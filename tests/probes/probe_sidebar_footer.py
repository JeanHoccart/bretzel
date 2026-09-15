"""Autonomous behaviour probe for SidebarFooter — boots the FULL runtime
(htmx + idiomorph + iconify + runtime.js) on a standalone page and drives
the account popover : click-to-open, position:fixed (escapes the sidebar
overflow), placement above the trigger, click-outside dismiss, and the
collapsed-rail avatar-only layout.

Run :  py tests/probes/probe_sidebar_footer.py
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
HTML = HERE / "_probe_sidebar_footer.html"
# Le runtime se localise par le PAQUET, jamais en comptant des ``parents[N]``.
# Sept probes comptaient ``parents[3]`` et visaient
# ``<repo>/runtime/runtime.js`` — un niveau trop haut, vestige d'une
# disposition disparue. Le ``<script>`` 404ait donc en silence, ``$bz``
# n'existait jamais, et la page restait en ``visibility: hidden`` : les
# probes lisaient « l'élément n'est pas visible » et accusaient le
# composant. Trois d'entre eux passaient même au VERT sans runtime.
RUNTIME_JS = (Path(_bz_runtime.__file__).resolve().parent / "runtime.js").as_uri()
TRIGGER = '[class*="group/acct"]'
PANEL = '[role="menu"]'


def build_page() -> str:
    with render_isolated():
        sb = Sidebar(open=True, collapsible="rail")
        with sb:
            SidebarTitle("Flat app", icon="zap")
            with SidebarSection(label="MENU"):
                SidebarItem("Home", icon="home", href="/")
            with SidebarFooter(
                name="Jean Hoccart", subtitle="jean.hoccart@gmail.com", avatar="JH"
            ):
                SidebarFooterItem(label="Retour au portail", icon_left="home", href="/")
                SidebarFooterItem(
                    label="Déconnexion", icon_left="log-out", color="error"
                )
        body = serialize(sb.render())
    return default_shell(
        body,
        envelope_json="",
        page_uuid="footer-probe",
        title="Footer probe",
        browser_css=True,
        theme_css_content=Theme().generate_css(),
        js_urls=[DEFAULT_HTMX_URL, DEFAULT_IDIOMORPH_URL, DEFAULT_ICONIFY_URL, RUNTIME_JS],
    )


def rect(page, sel):
    return page.evaluate(
        """(sel) => { const el = document.querySelector(sel); if (!el) return null;
           const b = el.getBoundingClientRect();
           const cs = getComputedStyle(el);
           return { x:b.x, y:b.y, w:b.width, h:b.height, top:b.top, bottom:b.bottom,
                    display: cs.display, position: cs.position }; }""",
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
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(HTML.as_uri())
        page.evaluate("() => document.documentElement.classList.add('dark')")
        # Wait for the runtime to boot.
        try:
            page.wait_for_function("() => !!window.$bz", timeout=8000)
        except Exception:
            findings.append("!! runtime.js never booted ($bz absent) — cannot drive the popover")
            ok = False
        page.wait_for_timeout(800)

        # ── 1. Initially closed ──────────────────────────────────────
        panel0 = rect(page, PANEL)
        closed_ok = panel0 is not None and panel0["display"] == "none"
        ok &= closed_ok
        findings.append(f"[{'OK' if closed_ok else 'FAIL'}] panel hidden on load (display={panel0 and panel0['display']})")

        # ── 2. Première ouverture : fixed + ancré AU-DESSUS ──────────
        #
        # ⚠️ Ce probe a exigé « à DROITE du déclencheur » jusqu'au
        # 2026-08-26, et il rougissait. Le composant DÉCLARE l'inverse :
        # ``anchored_panel_effect(open_expr, "auto")``, dont le commentaire
        # dit mot pour mot « the footer sits at the bottom so there's no
        # room below → it opens UPWARD ». Mesuré : déclencheur à y=736,
        # panneau à y=656 h=74, donc juste au-dessus, aligné à gauche
        # (x=16 contre 12). C'est le placement d'un menu de compte en bas
        # de barre — celui de VS Code et de shadcn.
        #
        # Ce qu'on mesure maintenant, c'est ce qui compte à l'œil : le
        # panneau est ANCRÉ sur son déclencheur et ne le RECOUVRE pas. Un
        # « auto » qui déciderait d'ouvrir vers le bas ou de se poser au
        # milieu de l'écran ferait rougir les deux.
        page.click(TRIGGER)
        page.wait_for_timeout(400)
        trig = rect(page, TRIGGER)
        p1 = rect(page, PANEL)
        if p1 and trig:
            opened = p1["display"] != "none"
            is_fixed = p1["position"] == "fixed"
            clears = p1["y"] + p1["h"] <= trig["y"] + 8
            aligned = abs(p1["x"] - trig["x"]) <= 12
            ok &= opened and is_fixed and clears and aligned
            findings.append(f"[{'OK' if opened else 'FAIL'}] opens on click (display={p1['display']})")
            findings.append(f"[{'OK' if is_fixed else 'FAIL'}] panel position:fixed -> {p1['position']}")
            findings.append(
                f"[{'OK' if clears else 'FAIL'}] s'ouvre VERS LE HAUT sans "
                f"recouvrir le déclencheur (bas du panneau "
                f"{p1['y'] + p1['h']:.0f} <= haut du déclencheur {trig['y']:.0f})"
            )
            findings.append(
                f"[{'OK' if aligned else 'FAIL'}] aligné sur le déclencheur "
                f"(panneau x={p1['x']:.0f}, déclencheur x={trig['x']:.0f})"
            )
        else:
            findings.append("!! could not measure panel/trigger after click")
            ok = False

        # Selected state : trigger carries data-menu-open=true + a bg while open.
        sel = page.evaluate(
            """() => { const t = document.querySelector('[class*="group/acct"]');
               return { attr: t.getAttribute('data-menu-open'),
                        bg: getComputedStyle(t).backgroundColor }; }"""
        )
        selected = sel["attr"] == "true" and sel["bg"] not in ("rgba(0, 0, 0, 0)", "transparent")
        ok &= selected
        findings.append(f"[{'OK' if selected else 'FAIL'}] trigger SELECTED while open "
                        f"(data-menu-open={sel['attr']}, bg={sel['bg']})")

        page.screenshot(path=str(HERE / "probe_footer_open.png"))

        # ── 3. Close + reopen : SAME position (first-click bug fixed) ─
        page.mouse.click(1000, 300)
        page.wait_for_timeout(400)
        page.click(TRIGGER)
        page.wait_for_timeout(400)
        p2 = rect(page, PANEL)
        if p1 and p2:
            consistent = abs(p1["x"] - p2["x"]) <= 2 and abs(p1["top"] - p2["top"]) <= 2
            ok &= consistent
            findings.append(
                f"[{'OK' if consistent else 'FAIL'}] 1st-open == 2nd-open position "
                f"(1st x={p1['x']:.0f} top={p1['top']:.0f} | 2nd x={p2['x']:.0f} top={p2['top']:.0f})"
            )
        # close again before the rail check
        page.mouse.click(1000, 300)
        page.wait_for_timeout(300)
        dismissed = (rect(page, PANEL) or {}).get("display") == "none"
        ok &= dismissed
        findings.append(f"[{'OK' if dismissed else 'FAIL'}] click-outside dismiss")

        # ── 4. Collapsed rail : avatar only, meta hidden ─────────────
        # ⚠️ ``[data-collapse]``, pas ``[data-variant]``. L'attribut a été
        # renommé quand ``variant=`` et ``collapsible=`` ont fusionné en un
        # seul axe (2026-08-15) ; ce sélecteur est resté cinq jours à ne
        # matcher RIEN, donc la barre ne se repliait jamais et le probe
        # rapportait « meta hidden=False, avatar shown=True » — un faux
        # échec contre un composant correct. Le forçage doit LEVER s'il
        # ne trouve pas sa cible, sinon il ment en silence.
        forced = page.evaluate(
            """() => { const r = document.querySelector('[data-collapse]');
                       if (r) r.setAttribute('data-open', 'false');
                       return !!r; }"""
        )
        if not forced:
            findings.append(
                "!! aucun `[data-collapse]` dans la page : le repli n'a pas "
                "été forcé, la mesure qui suit ne veut rien dire."
            )
            ok = False
        page.wait_for_timeout(300)
        meta = rect(page, '[class*="group/acct"] > div')  # the meta column
        avatar = rect(page, '[class*="group/acct"] > span')  # avatar chip
        meta_hidden = meta is None or meta["display"] == "none"
        avatar_shown = avatar is not None and avatar["display"] != "none"
        ok &= meta_hidden and avatar_shown
        findings.append(
            f"[{'OK' if meta_hidden and avatar_shown else 'FAIL'}] rail collapse : "
            f"meta hidden={meta_hidden}, avatar shown={avatar_shown}"
        )

        if errors:
            findings.append("!! page errors: " + " | ".join(errors[:3]))

        browser.close()

    print("\n".join(findings))
    print("\n" + ("==> ALL CHECKS PASSED" if ok else "==> SOME CHECKS FAILED"))
    print(f"screenshot -> {HERE / 'probe_footer_open.png'}")

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

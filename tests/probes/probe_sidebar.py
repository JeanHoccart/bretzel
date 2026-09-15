"""Probe visuel autonome de la Sidebar — rend le composant dans une page
dev autonome (Tailwind navigateur + Iconify + CSS du thème), l'ouvre dans
un Chromium headless et MESURE la mise en page réelle : boîte et
centrage du LOGO du rail replié, centrage des glyphes d'items. Aucun
serveur d'exemple.

⚠️ La section « glissement du tiroir mobile » a été RETIRÉE le
2026-08-19 : elle pilotait ``data-mob-open``, un attribut que la Sidebar
n'émet plus depuis que le responsive est serveur-autoritaire
(`4778021a`). Détail au point de retrait, dans ``main()``.

Run :  py tests/probes/probe_sidebar.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout

from bretzel.theme import DEFAULT_SPACING_PX
from playwright.sync_api import sync_playwright

from bretzel.components.base.testing import render_isolated
from bretzel.components.navigation.sidebar import (
    Sidebar,
    SidebarItem,
    SidebarSection,
    SidebarTitle,
)
from bretzel.core.serialize import serialize
from bretzel.render.shell import DEFAULT_ICONIFY_URL, default_shell
from bretzel.theme import Theme
from tests.probes._serve import absolutise_vendor

HERE = Path(__file__).parent
HTML = HERE / "_probe_sidebar.html"

# Le logo du rail replié : slot ``title_rail_brand``. C'est un ``<a>``,
# pas un bouton — et c'est le cœur de ce que ce probe a raté.
#
# Jusqu'au 2026-08-21 c'était ``button.group/railtoggle`` : un bouton qui
# portait le logo et le remplaçait par un chevron AU SURVOL, le clic
# repliant la barre. Le finding [29] l'a supprimé, parce que sur une
# machine sans pointeur fin — celle de l'utilisateur, mesurée — le geste
# existait sans que personne puisse le découvrir. Le logo est redevenu un
# lien, et le repli a son arête (``rail_edge``), visible dans les deux
# états.
#
# Ce probe a continué de chercher ``button[class*="railtoggle"]`` pendant
# cinq jours. La classe n'existant plus, le sélecteur ne matchait RIEN :
# il rendait « Tailwind n'a pas compilé w-10 » et « btn=False logo=False »,
# donc il accusait la CSS d'un bug qui était le sien. C'est la troisième
# fois qu'un probe périmé crie contre un fix correct dans ce dépôt.
RAIL_BRAND = 'aside a[class*="place-items-center"]'

#: Dix crans de l'échelle du THÈME — ``w-10`` sur le logo du rail.
#: Dérivée, jamais recopiée : cf. le commentaire au point d'attente.
RAIL_BRAND_WIDTH = f"{10 * DEFAULT_SPACING_PX}px"


def build_page() -> str:
    with render_isolated():
        sb = Sidebar(open=False, collapsible="rail")  # open=False → rail collapsed
        with sb:
            SidebarTitle("Probe", icon="zap")
            with SidebarSection(label="MENU"):
                SidebarItem("Home", icon="home", href="/")
                SidebarItem("Notes", icon="file-text", href="/notes")
                SidebarItem("Account", icon="user", href="/account")
        body_html = serialize(sb.render())

    theme_css = Theme().generate_css()
    # Only Iconify is needed (icons render) ; skip htmx/idiomorph/runtime —
    # we drive the data-* states ourselves from the probe.
    return default_shell(
        body_html,
        envelope_json="",
        page_uuid="probe",
        title="Sidebar probe",
        browser_css=True,
        theme_css_content=theme_css,
        js_urls=[DEFAULT_ICONIFY_URL],
    )


# ── geometry helpers (run in-page) ──────────────────────────────────────────
_RECT_JS = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const b = el.getBoundingClientRect();
  return { x: b.x, y: b.y, w: b.width, h: b.height,
           cx: b.x + b.width / 2, cy: b.y + b.height / 2 };
}
"""

_FORCE_COLLAPSE_JS = """
() => {
  const root = document.querySelector('[data-collapse]');
  if (root) root.setAttribute('data-open', 'false');
  return !!root;
}
"""

# Measures the ACTUAL painted glyph (the shadow-root <svg>), not the
# iconify-icon element box — the element box can be centered while the
# glyph sits top-left inside it (the w/h-vs-font-size bug).
_GLYPH_RECT_JS = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el || !el.shadowRoot) return null;
  const svg = el.shadowRoot.querySelector('svg');
  if (!svg) return null;
  const b = svg.getBoundingClientRect();
  return { x: b.x, y: b.y, w: b.width, h: b.height,
           cx: b.x + b.width / 2, cy: b.y + b.height / 2 };
}
"""


def center_delta(a, b):
    return (round(a["cx"] - b["cx"], 1), round(a["cy"] - b["cy"], 1))


def _wait_icons(pg) -> None:
    """Wait until Iconify has painted the glyphs. Lucide icons are fetched
    in one batched API call, so once any shadow SVG exists, all do."""
    try:
        pg.wait_for_function(
            """() => {
                const all = [...document.querySelectorAll('iconify-icon')];
                return all.length && all.every(
                    i => i.shadowRoot && i.shadowRoot.querySelector('svg'));
            }""",
            timeout=8000,
        )
    except Exception:
        pass
    pg.wait_for_timeout(200)


def main() -> int:
    # Une page `file://` ne resout aucune route relative : le
    # compilateur rapatrie doit y etre absolu (cf. `_serve`).
    HTML.write_text(absolutise_vendor(build_page()), encoding="utf-8")
    findings: list[str] = []
    ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ── DESKTOP : rail collapsed ────────────────────────────────────
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(HTML.as_uri())
        # ``_FORCE_COLLAPSE_JS`` renvoie déjà « ai-je trouvé ma cible ? ».
        # Ce retour était JETÉ : un sélecteur périmé laissait la barre
        # dépliée et toutes les mesures suivantes parlaient d'autre chose.
        # C'est ce qui est arrivé au probe voisin (``probe_sidebar_footer``,
        # ``[data-variant]`` renommé), et le forçage doit dire quand il
        # n'a rien forcé.
        if not page.evaluate(_FORCE_COLLAPSE_JS):
            findings.append(
                "!! aucun `[data-collapse]` dans la page : la barre n'a pas "
                "été repliée, donc rien de ce qui suit ne mesure le rail."
            )
            ok = False
        page.evaluate("() => document.documentElement.classList.add('dark')")
        # Wait until Tailwind compiled the collapse width (``w-10``).
        #
        # ⚠️ La largeur se DÉRIVE du pas du thème. Elle était écrite
        # « 40px », c'est-à-dire dix crans de l'échelle de Tailwind, et le
        # jour où Bretzel a choisi la sienne (3 px, 2026-09-13) ce nombre
        # est devenu faux — le probe accusait alors Tailwind de ne pas
        # compiler une classe parfaitement compilée. Un chiffre recopié
        # d'une échelle qu'on ne contrôle plus accuse toujours le mauvais
        # coupable.
        try:
            page.wait_for_function(
                """([sel, largeur]) => {
                    const b = document.querySelector(sel);
                    return b && getComputedStyle(b).width === largeur;
                }""",
                arg=[RAIL_BRAND, RAIL_BRAND_WIDTH],
                timeout=10000,
            )
        # ⚠️ ``PWTimeout`` et pas ``Exception``. Un ``except Exception`` ici
        # avale les erreurs du PROBE lui-même et les rebaptise « la CSS
        # n'est pas compilée » — mesuré le 2026-08-26 : un ``arg`` passé en
        # positionnel au lieu du mot-clé levait un ``TypeError``, capturé et
        # rapporté comme un bug de Tailwind. Une capture large transforme
        # une faute de frappe en enquête de trois heures.
        except PWTimeout:
            present = page.evaluate(
                "(sel) => !!document.querySelector(sel)", RAIL_BRAND)
            # ⚠️ On DISTINGUE les deux causes. La version d'avant disait
            # « Tailwind n'a pas compilé » quoi qu'il arrive — y compris
            # quand le sélecteur ne matchait rien, ce qui était le cas.
            # Un message qui accuse toujours le même coupable ne diagnostique
            # rien : il envoie chercher un bug de CSS pendant cinq jours.
            findings.append(
                f"!! le logo du rail n'atteint pas w-10 "
                f"({RAIL_BRAND_WIDTH}) — "
                + ("l'élément EXISTE, donc c'est bien la classe de repli qui "
                   "n'est pas compilée"
                   if present else
                   f"et le sélecteur {RAIL_BRAND!r} ne matche RIEN : c'est le "
                   "PROBE qui est périmé, pas la CSS. Vérifie le slot "
                   "``title_rail_brand`` du thème.")
            )
            ok = False

        # Measure the ACTUAL painted glyphs (shadow SVG) vs the button —
        # the element box can be centered while the glyph sits top-left.
        _wait_icons(page)
        btn = page.evaluate(_RECT_JS, RAIL_BRAND)
        logo = page.evaluate(
            _GLYPH_RECT_JS, f'{RAIL_BRAND} iconify-icon[icon="lucide:zap"]')
        if btn and logo:
            dx, dy = center_delta(logo, btn)
            centered = abs(dx) <= 1.5 and abs(dy) <= 1.5
            ok &= centered
            findings.append(
                f"[{'OK' if centered else 'FAIL'}] rail LOGO glyph centering : "
                f"btn {btn['w']:.0f}x{btn['h']:.0f}, glyph {logo['w']:.0f}px, "
                f"offset dx={dx} dy={dy} (want ~0,0)"
            )
        else:
            findings.append(
                f"!! impossible de mesurer le logo du rail "
                f"(lien={bool(btn)} glyphe={bool(logo)}) — "
                f"sélecteur {RAIL_BRAND!r}"
            )
            ok = False

        # ── Le CHEVRON du rail — RETIRÉ le 2026-08-26 ───────────────────
        #
        # Ce probe mesurait le centrage d'un ``chevron-right`` qui
        # apparaissait DANS le logo au survol. Ce mécanisme n'existe plus
        # depuis le finding [29] (2026-08-21) : sur une machine sans
        # pointeur fin, il était indécouvrable. Le repli est passé sur
        # ``rail_edge``, une arête visible dans les deux états.
        #
        # Il n'y a donc plus de sujet à mesurer, pas une mesure en panne —
        # même forme que la section MOBILE retirée plus bas. Le geste de
        # repli, lui, est gardé par
        # ``tests/consistency/test_a_sidebar_can_always_come_back.py``.

        _wait_icons(page)
        page.screenshot(path=str(HERE / "probe_sidebar_rail_default.png"),
                        clip={"x": 0, "y": 0, "width": 120, "height": 320})

        # Item icon GLYPH centering (shadow SVG vs the row).
        items = page.evaluate(
            """() => {
              const rows = [...document.querySelectorAll('[class*="group/row"]')];
              return rows.map(row => {
                const icon = row.querySelector('iconify-icon');
                const svg = icon && icon.shadowRoot ? icon.shadowRoot.querySelector('svg') : null;
                const rb = row.getBoundingClientRect();
                const ib = svg ? svg.getBoundingClientRect() : null;
                return ib ? {
                  glyphW: Math.round(ib.width),
                  dx: Math.round((ib.x+ib.width/2)-(rb.x+rb.width/2)),
                  dy: Math.round((ib.y+ib.height/2)-(rb.y+rb.height/2)),
                } : null;
              }).filter(Boolean);
            }"""
        )
        bad = [i for i in items if abs(i["dx"]) > 1.5 or abs(i["dy"]) > 1.5]
        ok &= bool(items) and not bad
        findings.append(
            f"[{'OK' if items and not bad else 'FAIL'}] item GLYPH centering : "
            f"{len(items)} rows, offsets={[(i['dx'], i['dy']) for i in items]}"
        )

        page.screenshot(path=str(HERE / "probe_sidebar_rail_hover.png"),
                        clip={"x": 0, "y": 0, "width": 120, "height": 320})

        # ── MOBILE : le glissement du tiroir — RETIRÉ le 2026-08-19 ─────
        #
        # Cette section pilotait ``data-mob-open`` sur la racine et
        # mesurait le ``transform`` du tiroir. **Le mécanisme n'existe
        # plus** : le responsive est devenu SERVEUR-autoritaire (viewport
        # en cookie, `4778021a`), la Sidebar n'émet plus ``data-mob-open``
        # du tout, et poser l'attribut à la main ne déclenche rien.
        #
        # Ce n'était donc pas une mesure en panne, c'était une mesure SANS
        # SUJET — elle plantait sur ``document.querySelector('[data-collapse]')``
        # rendant ``null``, l'attribut ayant lui aussi été renommé en
        # ``data-collapse``.
        #
        # Ce qui a pris sa place est déterministe et déjà gardé :
        # ``tests/integration/server/test_screen_responsive.py`` (branche
        # mobile/desktop selon le cookie, absence de machinerie live).
        # Le rendre ici en probe n'ajouterait rien qu'un navigateur voie.
        browser.close()

    print("\n".join(findings))
    print("\n" + ("==> ALL CHECKS PASSED" if ok else "==> SOME CHECKS FAILED"))
    print(f"captures -> probe_sidebar_rail_default.png / _rail_hover.png "
          f"(dans {HERE})")

    # Le verdict rejoint le CODE DE SORTIE, seul signal que
    # ``test_probes.py`` regarde. Sans ce ``return``, ce probe
    # imprimait son echec et sortait 0 : vert dans ``-m probes``,
    # quoi qu'il mesure.
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

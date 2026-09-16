"""HTML5 document shell — assembles the bytes that go on the wire.

A *shell* is the framing around the rendered body : doctype, ``<html>``,
``<head>`` (charset / viewport / title / description / theme + style
links / CDN scripts / runtime.js / FOUC-prevention inline) and the
``<body>`` containing the ``bz-page-<uuid>`` wrapper around the actual
page content.

Pure function — no I/O, no contextvars. The pipeline composes a shell
from the data it has at hand and serialises the result. Apps can swap
out the entire shell per-page via ``@page(shell=…)``.

"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from pygments.formatters import HtmlFormatter as _PygmentsHtmlFormatter

from bretzel.core.escape import escape_attr, escape_html
from bretzel.core.serialize import serialize
from bretzel.core.tree import Node
from bretzel.runtime.protocol import (
    HEADER_PAGE_ID,
    NAV_PENDING_KEY,
    ROUTE_FAVICON,
    ROUTE_ICONS,
    ROUTE_RUNTIME_JS,
    ROUTE_STYLE_CSS,
    ROUTE_TOUCH_ICON,
    SCREEN_COOKIE,
    SCREEN_SYNC_FN,
    SINK_ELEMENT_ID,
)

# Light + dark rules layered : ``.bz-code`` carries the light style ;
# ``html.dark .bz-code`` overrides with the dark style so toggling the
# FOUC-prevention ``.dark`` class on ``<html>`` (cf. ``_FOUC_SCRIPT``)
# swaps both the page palette AND the code highlighting in one stroke.
_PYGMENTS_STYLE = (
    _PygmentsHtmlFormatter(style="default").get_style_defs(".bz-code")
    + "\n"
    + _PygmentsHtmlFormatter(style="monokai").get_style_defs("html.dark .bz-code")
)

# ───────────────────────────────────────────────────────────────────────────
# CDN versions — single source of truth, bumped only by explicit PR.
# ───────────────────────────────────────────────────────────────────────────

DEFAULT_HTMX_URL = "https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"
# Idiomorph 0.7+ ships an htmx-2 compatible extension. Loaded after
# htmx so its ``htmx.defineExtension('morph', ...)`` registration sees
# the global. ``hx-ext="morph"`` on ``<body>`` (cf. shell HTML below)
# makes every swap go through it ; OOB fragments use ``hx-swap-oob
# ="morph"`` which preserves child elements by id — ``bz-data``
# scopes on the accordion, popovers, tabs etc. survive in place
# instead of being destroyed + re-initialised by an outerHTML swap.
DEFAULT_IDIOMORPH_URL = (
    "https://unpkg.com/idiomorph@0.7.3/dist/idiomorph-ext.min.js"
)
# iconify-icon web component — registered globally, lazy-fetches each
# icon set on first use. Required for ``ui.icon`` to render anything.
DEFAULT_ICONIFY_URL = (
    "https://code.iconify.design/iconify-icon/2.1.0/iconify-icon.min.js"
)

# Tailwind v4 in-browser compiler — mirrors v1's "Play CDN" strategy
# but for v4. Reads ``<style type="text/tailwindcss">`` blocks, scans
# the DOM for utility classes, generates CSS at runtime. Slow for
# prod, perfect for the dev loop.
#
# ⚠️ **Version EXACTE, et c'est ce qui a changé le 2026-09-13.** L'URL
# était ``@4`` tout court, donc un intervalle : unpkg résolvait vers la
# dernière 4.x du jour, et le compilateur de dev pouvait changer sous les
# pieds sans qu'une ligne du dépôt bouge. Une empreinte n'a aucun sens
# sur un intervalle, donc ce script était le seul des quatre à ne pas
# pouvoir être vérifié ni rapatrié (cf. :mod:`bretzel.render.vendor`).
DEFAULT_TAILWIND_BROWSER_URL = (
    "https://unpkg.com/@tailwindcss/browser@4.3.3/dist/index.global.js"
)


# ───────────────────────────────────────────────────────────────────────────
# FOUC-prevention inline script (cf. theme spec)
# ───────────────────────────────────────────────────────────────────────────


# Minified-by-hand : runs synchronously before paint to add the .dark
# class onto <html> if the user has explicitly chosen dark mode or
# the OS reports a dark preference. Must NEVER block — no async, no I/O.
#
# Reads the same localStorage key the ``bretzel.theme.ColorScheme``
# ClientState persists into (``$bz:`` prefix from
# ``runtime/_src/04_persistence.js`` + ``ClassName.<key>`` from the
# state envelope). ``ColorScheme`` is framework-owned, so the key is
# present as soon as the user has ever picked a mode ; when it's absent
# (first visit) we fall back to the OS preference — same result as the
# ``"system"`` default.
#
# ⚠️ The ``mode`` → dark? resolution here MUST stay in lockstep with the
# runtime effect in ``runtime/_src/00_index.js`` (boot). This script
# runs BEFORE the runtime loads (no-flash), so the logic is necessarily
# duplicated — ``"system"`` (canonical) and ``"auto"`` (legacy alias)
# both follow ``prefers-color-scheme``.
_FOUC_SCRIPT = (
    "(function(){"
    "var r=localStorage.getItem('$bz:ColorScheme.default');"
    "var d=false;"
    "if(r){try{var s=JSON.parse(r);d=s&&s.mode==='dark';"
    "if(s&&(s.mode==='system'||s.mode==='auto'))"
    "d=window.matchMedia('(prefers-color-scheme: dark)').matches;"
    "}catch(e){}}"
    "else if(window.matchMedia('(prefers-color-scheme: dark)').matches)d=true;"
    "if(d)document.documentElement.classList.add('dark');"
    "})();"
)


# Screen viewport scripts (cf. screen-responsive-nav.md).
# ───────────────────────────────────────────────────────────────────────────
# Two inline scripts, both pre-paint, siblings of ``_FOUC_SCRIPT``. They are
# split because they own two different questions, and the second one is not the
# only caller of the first :
#
#   1. :func:`_screen_sync_script` defines ``window.$bzScreenSync()`` — «*what
#      shape is this viewport, and did the server paint it?*». It reads
#      ``matchMedia``, rewrites the ``bz_screen`` cookie so the NEXT request
#      renders from a real bool server-side (``bretzel.render.screen.Screen``),
#      and returns whether the document just painted already matches. Wire
#      format ``bz_screen="{mobile},{touch}"`` (``1``/``0``), mirroring
#      :func:`bretzel.render.screen._parse_cookie`.
#   2. :func:`_screen_boot_script` decides «*what to do about a stale paint*» on
#      a full load : spend one corrective reload, bounded by a flag.
#
# The second caller is the **runtime** : ``_src/05_bridge.js`` calls
# ``$bzScreenSync()`` before a boosted navigation. Splitting keeps the
# ``matchMedia`` logic and the interpolated breakpoint in ONE place instead of
# duplicating them into the bundle — which is what a lockstep pair becomes when
# nobody gates it.
#
# There is deliberately NO resize listener : the layout never re-arranges under
# the user's fingers. Every correction is tied to a user-initiated navigation.
#
# ⚠️ The anti-loop flag is CONSUMED BY THE VERY LOAD IT GUARDS, and that
# consumption is the whole subtlety. Until 2026-08-16 it was a plain one-shot
# boolean, never cleared : the FIRST correction of the tab spent it and every
# later one was swallowed — the cookie got rewritten but the stale paint stayed
# on screen, so the user had to press F5 a second time to see the other layout.
# Measured on a since-removed demo app : two F5 per switch, both ways.
#
# The flag is therefore read AND removed on every load, before any early exit.
# It can only ever suppress the one load this script itself forced :
#
#   * legitimate switch — load N mismatches, no flag → set flag, reload. Load
#     N+1 clears the flag and the cookie now agrees : done, in one F5. The next
#     switch starts from a clean flag, so corrections are unlimited.
#   * pathological oscillation — a layout swap that adds/removes the document
#     scrollbar moves the viewport by ~15px, which can flip ``max-width`` back
#     and forth when the window sits right on the breakpoint. Load N+1 finds
#     the flag we just set AND still mismatches → give up rather than loop. The
#     cost is capped at one wasted reload per user-initiated load, never a loop.

#: ``sessionStorage`` key of the anti-loop flag. Deliberately NOT in
#: ``runtime/protocol.py`` : that module admits *wire* strings only (its own
#: rule, and the reason ``SCREEN_COOKIE`` is there), and this key never crosses
#: the wire. A module constant is the right layer ; it exists to kill the
#: hand-copies, which is how the sibling ``'$bz:ColorScheme.default'`` drifts.
_SCREEN_SYNC_KEY = "bz:screen-synced"


# The ``{breakpoint}`` is interpolated server-side from
# ``config.mobile_breakpoint`` — never hardcoded (anti-rule 3). The cookie NAME
# comes from the single-source ``protocol.SCREEN_COOKIE`` (same string the
# render-side ``Screen`` reads — no lockstep drift). The cookie is functional
# (viewport, not tracking) : path-wide, 1-year, ``SameSite=Lax``. Cached : the
# output depends only on the per-process ``breakpoint``, so build it once.
@functools.cache
def _screen_sync_script(breakpoint: int) -> str:
    """``window.$bzScreenSync()`` — rewrite the cookie, report on the paint.

    Returns ``true`` when the document the server just produced already matches
    the real viewport. Callers : the boot script below (full load) and
    ``_src/05_bridge.js`` (boosted navigation).
    """
    bp = int(breakpoint)
    c = SCREEN_COOKIE
    return (
        f"window.{SCREEN_SYNC_FN}=function(){{"
        # The cookie the SERVER rendered from (absent → '' → '0,0' desktop).
        f"var e=document.cookie.match(/(?:^|; ){c}=([^;]*)/);e=e?e[1]:'';"
        f"var m=window.matchMedia('(max-width: {bp}px)').matches?1:0;"
        "var t=window.matchMedia('(pointer: coarse)').matches?1:0;"
        "var f=m+','+t;"
        f"document.cookie='{c}='+f+';path=/;max-age=31536000;SameSite=Lax';"
        "return f===(e||'0,0');};"
    )


@functools.cache
def _screen_boot_script() -> str:
    """Spend one corrective reload when the paint is stale — bounded by a flag.

    Breakpoint-free (the sync function owns it), so there is nothing to cache
    per-app ; the ``lru_cache`` just builds the string once per process.
    """
    k = _SCREEN_SYNC_KEY
    return (
        "(function(){"
        # Sync FIRST, outside the storage ``try`` : the cookie must be written
        # even where ``sessionStorage`` throws (privacy modes), otherwise the
        # server would render from a cookie that never appears.
        f"var ok=window.{SCREEN_SYNC_FN}();"
        # One ``try`` for the whole tail : ``return`` inside it still returns
        # from the IIFE, and a storage that throws lands in the same ``catch``
        # — no reload rather than a loop.
        #
        # Read AND consume the flag FIRST, before either exit below, so it can
        # only ever describe THIS load.
        f"try{{var g=sessionStorage.getItem('{k}');"
        f"sessionStorage.removeItem('{k}');"
        # Cookie already agreed with the viewport → the paint is right, done.
        "if(ok)return;"
        # Still wrong on the load we ourselves forced → oscillation, give up.
        "if(g)return;"
        # Stale paint, nobody has tried yet : flag then reload. This is the ONLY
        # write, and it lives past every exit — a write on any other path would
        # re-arm the flag for a load that isn't ours and bring the bug back.
        f"sessionStorage.setItem('{k}','1');"
        "location.reload();}catch(x){}"
        "})();"
    )

# Anti-flash CSS (V3 — .claude/bretzel/runtime.md §FOUC strategy). Server-side
# rendering pre-stamps every directive's initial visible state, so the
# only flash risk is ``bz-data`` scopes whose object literal must be
# evaluated before the runtime knows what to show : hidden until
# ``00_index.js`` adds ``.bz-ready`` on <html> (10-30ms, invisible).
# ``<bz-envelope>`` / ``<bz-patch>`` are data tags, never displayed.
_ANTI_FLASH_STYLE = (
    # ⚠️ Portée ``html:not(.bz-ready)`` — c'est UNE règle, pas une paire.
    # Elle en était une : ``[bz-data]{visibility:hidden}`` global, puis
    # ``html.bz-ready [bz-data]{visibility:visible}`` pour le relever.
    # Écrire ``visible`` explicitement sur chaque scope l'affranchit de
    # TOUT ancêtre masqué, or ``visibility`` est justement la propriété
    # qu'un descendant peut reprendre. Un ``ui.dialog`` fermé se cache en
    # ``visibility:hidden`` (``data-[open=false]:invisible``) : le premier
    # composant à état client qu'il contient redevenait donc visible —
    # invisible à l'œil, il n'occupe pas de place et rien ne le peint,
    # mais FOCUSABLE. Mesuré le 2026-09-07 sur ``examples/messagerie`` :
    # la 2ᵉ tabulation de la page atterrissait dans le ``ui.file_upload``
    # d'un dialogue fermé, puis rejoué sur banc le 2026-09-10.
    #
    # Une seule règle bornée au pré-boot dit la même chose sans jamais
    # relever quoi que ce soit : après ``.bz-ready`` plus aucune
    # déclaration ne vise ces éléments, donc l'héritage reprend. Les
    # sous-arbres insérés APRÈS le boot (morph de nav partielle) sont
    # visibles dans les deux versions — la paire les relevait, celle-ci
    # ne les masque pas.
    "html:not(.bz-ready) [bz-data]{visibility:hidden}"
    "bz-envelope,bz-patch{display:none}"
    # Etat fermé des overlays (dialog / drawer), déclaré AVANT le premier
    # paint. Sans ça, le décor Tailwind du backdrop (``fixed inset-0
    # bg-black/50 backdrop-blur-sm``) arrive après le premier paint et
    # ``opacity`` / ``visibility``, qui sont dans un ``transition``,
    # animent depuis leur valeur non-stylée (1 / visible) : un voile
    # flouté plein écran s'efface en 200 ms sur toute page portant un
    # overlay. En le déclarant ici, la valeur ne bouge plus à l'arrivée
    # de la feuille, donc aucune transition ne démarre.
    #
    # La règle ne peut pas rouler sur Tailwind (elle doit être là au
    # premier paint, avant lui) et ne peut pas viser ``[data-open=false]``
    # nu : sidebar (rail replié) et accordion portent le même attribut et
    # se feraient masquer. D'où le marqueur ``data-bz-overlay``, posé par
    # ``components.base._wiring.show_attrs``.
    #
    # ⚠️ Portée ``html:not(.bz-ready)`` — la règle ne vit QUE avant le
    # boot, ce pour quoi elle existe. Elle était globale, et le
    # raisonnement d'origine (« pas de ``!important``, l'utilitaire
    # Tailwind reprend la main ») ne vaut que pour le FOND assombri, qui
    # porte bien un ``data-[open=false]:opacity-0``. Le PANNEAU d'un
    # drawer n'a aucun utilitaire d'opacité — il ne doit que glisser
    # (``transition-[translate,visibility]``). Rien ne reprenait donc la
    # main, et cette règle lui imposait ``opacity:0`` SANS transition.
    #
    # Mesuré image par image le 2026-08-18, à la fermeture : opacité 1 →
    # 0 en moins de 145 ms pendant que le ``translate`` courait jusqu'à
    # 400 ms. Le panneau finissait sa glissade invisible — on voyait un
    # fondu sec, jamais le glissement. Signalé à l'œil : « ça fait un
    # fade et pas un slide de fermeture ».
    'html:not(.bz-ready) [data-bz-overlay][data-open="false"]'
    "{opacity:0;visibility:hidden}"
)


# htmx history cache OFF. Bretzel partial-nav (sidebar / navbar) sets
# ``hx-push-url=true`` ; htmx then snapshots the WHOLE page into
# ``localStorage['htmx-history-cache']`` on every navigation. Bretzel
# pages carry the full design-system markup, so a couple of navigations
# blow the ~5 MB localStorage quota → ``htmx:historyCacheError`` in the
# console + a failed ``setItem``. Bretzel is server-driven : on a back
# button htmx hits a history-miss and re-fetches from the server (AJAX
# GET restore), so the client-side snapshot buys nothing. Size 0 turns
# the snapshot off entirely. htmx reads this from ``meta[name=htmx-
# config]`` at load — emitted in <head> before the deferred runtime.
_HTMX_CONFIG = '{"historyCacheSize":0}'


# ───────────────────────────────────────────────────────────────────────────
# Chart entry-animation keyframes
# ───────────────────────────────────────────────────────────────────────────
#
# Refresh transitions for charts (line/area/bar/slice morphing on
# ``@refreshable`` swaps) ride pure CSS transitions on SVG attrs
# and need no keyframes. Entry animations DO — they require an
# explicit ``from`` state different from the rendered SVG attrs.
#
# All animations are gated behind ``@media (prefers-reduced-motion:
# no-preference)`` so users with reduced-motion preferences see
# charts paint instantly.
#
# - ``bz-line-draw`` : stroke-dashoffset reveal. The chart's line /
#   area applies ``stroke-dasharray: 2000`` (larger than any
#   reasonable polyline length) and animates ``dashoffset`` from
#   ``2000`` (line hidden) to ``0`` (full line). Reads as "the line
#   draws itself" left-to-right.
# - ``bz-bar-grow``  : ``transform: scaleY(0 → 1)`` with
#   ``transform-origin: 50% 100%`` so each bar grows from its
#   baseline. Mixed positive / negative bars use the same animation
#   for v1 — negative bars effectively grow downward (still reads
#   well because the user sees the bar emerge).
# - ``bz-slice-pop`` : ``transform: scale(0.7 → 1)`` with
#   ``transform-origin`` set per-slice from the SVG path's centroid.
#   v1 uses ``50% 50%`` (chart centre) for simplicity ; per-slice
#   centroid wakes the whole composition into place.
_CHARTS_ENTRY_STYLE = """
@media (prefers-reduced-motion: no-preference) {
  @keyframes bz-line-draw {
    from { stroke-dashoffset: 1; }
    to   { stroke-dashoffset: 0; }
  }
  @keyframes bz-area-reveal {
    from { clip-path: inset(0 100% 0 0); }
    to   { clip-path: inset(0 0% 0 0); }
  }
  @keyframes bz-bar-grow {
    from { transform: scaleY(0); }
    to   { transform: scaleY(1); }
  }
  @keyframes bz-slice-pop {
    from { transform: scale(0.7); opacity: 0; }
    to   { transform: scale(1);   opacity: 1; }
  }
  /* ``stroke-dasharray: 1`` paired with ``pathLength="1"`` on the
     <path> element normalises the dash to the path's full length —
     any line, however short or long, animates over the full
     duration without ``stroke-dasharray: 2000`` race-to-the-end
     artefacts on short polylines. */
  .bz-line-entry {
    stroke-dasharray: 1;
    animation: bz-line-draw 1100ms cubic-bezier(.4,0,.2,1) forwards;
  }
  .bz-area-entry {
    animation: bz-area-reveal 1100ms cubic-bezier(.4,0,.2,1) forwards;
  }
  .bz-bar-entry {
    transform-origin: 50% 100%;
    animation: bz-bar-grow 500ms cubic-bezier(.4,0,.2,1) backwards;
  }
  .bz-slice-entry {
    transform-origin: 50% 50%;
    animation: bz-slice-pop 450ms cubic-bezier(.4,0,.2,1) backwards;
  }
}
"""


# Toast enter / leave keyframes. The V2 Alpine port drove these via
# ``x-transition`` ; V3 does it with pure CSS + a two-phase dismiss in
# ``09_notification.js`` (mark ``_leaving`` → wait ``bz-toast-out``'s
# duration → splice). ``bz-for`` is keyed on ``t.id``, so ``.bz-toast-enter``
# fires only when a NEW toast node mounts — existing toasts don't re-animate
# when another arrives. ``.bz-toast-leave`` is defined AFTER ``.bz-toast-enter``
# so, when both classes are present on a leaving toast, its ``animation``
# wins the cascade. Gated behind ``prefers-reduced-motion: no-preference`` ;
# the runtime skips the leave delay entirely under reduced-motion.
#
# NB : the 200ms of ``bz-toast-out`` is mirrored by ``LEAVE_MS`` in
# ``09_notification.js`` — keep them in sync.
_NOTIFICATION_ANIM_STYLE = """
@media (prefers-reduced-motion: no-preference) {
  @keyframes bz-toast-in {
    from { opacity: 0; transform: translateY(-6px) scale(0.96); }
    to   { opacity: 1; transform: none; }
  }
  @keyframes bz-toast-out {
    from { opacity: 1; transform: none; }
    to   { opacity: 0; transform: scale(0.96); }
  }
  .bz-toast-enter { animation: bz-toast-in 300ms cubic-bezier(.4,0,.2,1) backwards; }
  .bz-toast-leave { animation: bz-toast-out 200ms cubic-bezier(.4,0,.2,1) forwards; }
}
"""

#: La bande qui glisse pendant une navigation. Une keyframe de shell,
#: comme les deux du toast juste au-dessus, et pour la même raison :
#: Tailwind n'a pas de glissement intégré, et une classe ASSEMBLÉE
#: n'existerait qu'en dev. Le repli sans mouvement n'est pas décoratif —
#: hors ``no-preference`` la bande reste pleine largeur et immobile,
#: donc elle dit toujours « ça travaille » sans bouger.
_NAV_PROGRESS_ANIM_STYLE = """
#bz-nav-progress > div { width: 100%; }
@media (prefers-reduced-motion: no-preference) {
  @keyframes bz-nav-slide {
    from { transform: translateX(-100%); }
    to   { transform: translateX(320%); }
  }
  #bz-nav-progress > div {
    width: 32%;
    animation: bz-nav-slide 1.1s cubic-bezier(.4,0,.2,1) infinite;
  }
}
"""


def nav_progress_html() -> str:
    """La barre de navigation, injectée une fois par page.

    **Elle n'a aucun mécanisme à elle.** C'est le signal de
    ``ui.pending()`` lu sur une clé RÉSERVÉE : le bridge arme ``@nav``
    quand la requête en vol est une navigation (boostée, ou portant
    ``hx-push-url``), et cette bande n'est qu'un ``bz-show`` de plus.
    Un ``action_id`` vaut ``module::qualname`` et ne peut donc jamais
    commencer par ``@`` — la clé est à l'abri d'une collision.

    Le seuil de 200 ms est celui de ``ui.pending()``, et il compte
    davantage ici : une navigation partielle rapide est la norme, donc
    sans lui chaque clic de menu ferait clignoter une barre.

    Ce n'est **pas** un ``ui.progress`` : aucune progression n'est
    connue (le serveur ne dit pas où il en est du rendu), et une
    fraction inventée serait un mensonge. C'est un témoin d'activité,
    donc une bande indéterminée. Sa couleur est littérale (``bg-primary``)
    — le chrome de l'app suit l'accent, et une classe composée depuis
    une variable ne survivrait pas au compilateur de prod.

    ``z-50`` est le HAUT de l'échelle de la maison (le toaster et le
    dialogue y sont) — pas un cran neuf au-dessus. Une barre de 2 px en
    bord d'écran n'a rien à disputer à une modale, et inventer un
    échelon pour elle seule ferait dériver l'échelle.

    ``style="display:none"`` est pré-posé : rien ne peut être en vol au
    moment où le serveur rend, donc la barre ne doit pas clignoter au
    chargement — même garde que le ``ssr_value=False`` côté Python.
    """
    return (
        '<div id="bz-nav-progress" role="presentation" '
        'class="fixed inset-x-0 top-0 z-50 h-0.5 overflow-hidden '
        'pointer-events-none" '
        f"bz-show=\"$bz.pending('{NAV_PENDING_KEY}', 200)\" "
        'style="display:none">'
        '<div class="h-full bg-primary"></div>'
        "</div>"
    )


# ───────────────────────────────────────────────────────────────────────────
# Public — default shell
# ───────────────────────────────────────────────────────────────────────────


def default_shell(
    body_html: str,
    envelope_json: str,
    *,
    page_uuid: str,
    title: str = "Bretzel",
    description: str | None = None,
    lang: str = "en",
    charset: str = "utf-8",
    head_extras: Iterable[Node] = (),
    css_urls: Iterable[str] | None = None,
    js_urls: Iterable[str] | None = None,
    meta_tags: Iterable[Mapping[str, str]] = (),
    favicon: str | bool | None = None,
    cache_bust: str | None = None,
    # Le pipeline CSS effectif, pas le mode : c'est la seule chose qui
    # décidait du RENDU depuis un booléen d'environnement. Cf.
    # ``config.css_pipeline``.
    browser_css: bool = False,
    theme_css_content: str = "",
    mobile_breakpoint: int = 768,
    nav_progress: bool = True,
    manifest_url: str | None = None,
    theme_color: str | None = None,
) -> str:
    """Assemble the complete HTML5 document."""
    if css_urls is not None:
        css_list = list(css_urls)
    elif browser_css:
        # Compilateur navigateur : aucun ``<link>``, il lit le bloc
        # ``<style type="text/tailwindcss">`` inline plus bas.
        css_list = []
    else:
        css_list = _default_css(cache_bust)

    js_list = list(js_urls) if js_urls is not None else _default_js(cache_bust)

    head = _build_head(
        title=title,
        description=description,
        charset=charset,
        css_urls=css_list,
        js_urls=js_list,
        meta_tags=meta_tags,
        favicon=favicon,
        cache_bust=cache_bust,
        head_extras=head_extras,
        envelope_json=envelope_json,
        browser_css=browser_css,
        theme_css_content=theme_css_content,
        mobile_breakpoint=mobile_breakpoint,
        nav_progress=nav_progress,
        manifest_url=manifest_url,
        theme_color=theme_color,
    )
    body = _build_body(body_html, page_uuid, nav_progress=nav_progress)

    return (
        "<!doctype html>\n"
        f'<html lang="{escape_attr(lang)}">\n'
        f"{head}\n"
        f"{body}\n"
        "</html>"
    )


# ───────────────────────────────────────────────────────────────────────────
# Internals
# ───────────────────────────────────────────────────────────────────────────


def _default_css(cache_bust: str | None) -> list[str]:
    # Prod : the compiled style.css already inlines what theme.css
    # provided as source, so a single link is enough. We keep
    # theme.css served (for tooling / inspection) but don't link it
    # from the page.
    return [_bust(ROUTE_STYLE_CSS, cache_bust)]


def _default_js(cache_bust: str | None) -> list[str]:
    # Order matters with ``defer`` scripts :
    # 1. HTMX must load first ; the runtime bridge wires its events.
    # 2. Idiomorph (htmx-2 extension) must load AFTER htmx so its
    #    ``htmx.defineExtension('morph', ...)`` can register before
    #    the first swap.
    # 3. ``runtime.js`` last — its bootstrap runs at DOMContentLoaded
    #    and expects ``window.htmx`` to exist. No Alpine in V3.
    #
    # Les trois premiers sortent du CDN **tant qu'ils n'ont pas été
    # rapatriés**. Mesuré le 2026-08-27 en prod, cache froid : 593 / 592 /
    # 489 ms contre 20-40 ms pour une ressource servie par l'app. Un
    # ``python -m bretzel.render.vendor`` les met dans ``.bretzel/vendor/``
    # et cette liste bascule d'elle-même (cf. ``vendor.url_for``).
    from bretzel.render import vendor  # casse un cycle : vendor lit d'ici

    return [
        *(vendor.url_for(asset) for asset in vendor.vendored_assets()),
        _bust(ROUTE_RUNTIME_JS, cache_bust),
    ]


_TAILWIND_IMPORT_RE = re.compile(r'^\s*@import\s+["\']tailwindcss["\']\s*;?\s*$', re.MULTILINE)


def _strip_tailwind_import(theme_css: str) -> str:
    """Remove the ``@import "tailwindcss"`` directive line.

    Required for the browser-side CDN path (it imports tailwindcss
    itself and choking on the directive yields a spurious 404 for
    ``/tailwindcss``). Only the literal directive line is removed —
    the rest of the theme CSS (``@theme`` block, autofill fix,
    transitions, scrollbar) is preserved unchanged.
    """
    return _TAILWIND_IMPORT_RE.sub("", theme_css)


def _bust(url: str, cache_bust: str | None) -> str:
    if cache_bust is None:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}h={cache_bust}"


def _theme_payload_js() -> str:
    """Build the inline JS that exposes the framework theme to the
    runtime as ``window.$bz_theme``.

    Currently carries the notification toaster theme ; future
    runtime-managed components add their entries here. Single-quoted
    JSON inside ``</script>`` is safe because the keys + class
    strings never contain ``</script>``.

    ⚠️ **Ce n'est PAS ``json.dumps`` qui protège** : il n'échappe ni
    ``<`` ni ``>`` (``json.dumps('<a>')`` rend ``"<a>"``). La phrase le
    prétendait jusqu'au 2026-08-01. La sûreté ici repose sur le fait que
    le payload est construit par le framework à partir de la palette du
    thème — pas sur un échappement. Un payload user-influençable devrait
    passer par ``escape_inline_json``, comme ``serialize_envelope``.
    """
    import json

    from bretzel.components.feedback.notification.theme import (
        runtime_payload as _notification_payload,
    )

    payload = {
        "notification": _notification_payload(),
    }
    # ``ensure_ascii=False`` keeps non-ASCII chars readable in source
    # ; combined with ``separators=(",",":")`` to shave a few bytes.
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"),
    )
    return f"window.$bz_theme={encoded};"


#: Les types MIME que le navigateur veut voir sur un ``rel="icon"``.
#: Un ``type=`` juste laisse Chrome préférer le SVG sans télécharger le
#: reste ; un ``type=`` faux le lui fait ignorer. On ne le pose donc que
#: sur les extensions qu'on reconnaît, et on se tait sur les autres.
_ICON_TYPES: Final[dict[str, str]] = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@functools.cache
def _inline_scripts(mobile_breakpoint: int) -> tuple[tuple[str, str], ...]:
    """Les CORPS des ``<script>`` inline que la coque émet, nommés.

    Source unique, et c'est tout son intérêt : la politique de sécurité
    (:mod:`bretzel.server.security`) publie le ``sha256`` de chacun de
    ces corps dans ``script-src``, et ``_build_head`` émet ces mêmes
    corps. Un quatrième script inline ajouté ici est haché sans qu'on y
    pense ; ajouté ailleurs, il ne l'est pas et la page casse sous CSP.
    C'est la raison d'être de cette fonction, et
    ``tests/consistency/test_every_inline_script_is_in_the_policy.py``
    est ce qui l'empêche d'être contournée.

    Les trois corps sont **déterministes** — ils ne dépendent que du
    thème et de ``mobile_breakpoint``, jamais de la requête. Mesuré le
    2026-09-05 : 3 empreintes distinctes sur 77 pages × 2 requêtes.
    C'est ce qui autorise des hashes plutôt qu'un ``nonce``, lequel
    aurait imposé une valeur par réponse (donc une page non cachable)
    et un paramètre de plus à toute coque personnalisée.
    """
    return (
        # Avant toute feuille de style : la classe ``.dark`` doit être
        # sur <html> au moment où les styles se calculent.
        ("fouc", _FOUC_SCRIPT),
        # Même créneau. La fonction de synchro d'abord (elle écrit
        # ``bz_screen`` depuis matchMedia pour que le rendu suivant le
        # lise côté serveur), puis l'amorce qui dépense le rechargement
        # correctif si cette peinture est périmée.
        (
            "screen",
            f"{_screen_sync_script(mobile_breakpoint)}{_screen_boot_script()}",
        ),
        # Le thème du framework exposé au runtime en ``window.$bz_theme``.
        ("theme", _theme_payload_js()),
        # Où le composant iconify doit chercher ses GLYPHES. Sans ce
        # réglage il interroge trois hôtes tiers ; avec, il passe par
        # notre route, qui relaie une fois puis sert de son cache.
        ("icons", _icon_provider_script()),
    )


def _icon_provider_script() -> str:
    """``window.IconifyProviders`` — la route locale plutôt que trois CDN.

    Le composant web iconify lit ce global à son initialisation. Rapatrier
    le composant (cf. :mod:`bretzel.render.vendor`) ne rapatrie QUE lui :
    ses glyphes partent à l'exécution chez ``api.iconify.design`` et deux
    hôtes de secours. Mesuré le 2026-09-13, les trois coupés : **0 glyphe
    sur 25**.

    ⚠️ Il doit s'exécuter AVANT le script du composant, donc sans
    ``defer`` — posé après, le réglage arrive quand les glyphes sont déjà
    partis.
    """
    return f'window.IconifyProviders={{"":{{resources:["{ROUTE_ICONS}"]}}}};'


def inline_scripts(mobile_breakpoint: int) -> dict[str, str]:
    """Les corps inline, nommés. Cf. :func:`_inline_scripts`.

    Le calcul est mémorisé (le tuple hashable d'à côté) et cette
    enveloppe rend un dict NEUF : mémoriser un dict le rendrait
    mutable par ses appelants. Mesuré le 2026-09-06 :
    ``_theme_payload_js()`` coûtait 26 µs à CHAQUE rendu de page pour
    resérialiser la même palette — sa propre docstring disait déjà que
    les trois corps sont déterministes.
    """
    return dict(_inline_scripts(mobile_breakpoint))


@dataclass(frozen=True, slots=True)
class ShellSources:
    """Tout ce que la coque charge ou exécute — la surface qu'une CSP couvre.

    ``scripts`` et ``styles`` sont séparés parce qu'une origine de script
    n'a rien à faire dans ``style-src``. ``inline`` porte les corps que
    :func:`inline_scripts` déclare, dont la politique publie l'empreinte.
    """

    scripts: tuple[str, ...]
    styles: tuple[str, ...]
    inline: tuple[str, ...]


def shell_sources(
    *, browser_css: bool, mobile_breakpoint: int = 768
) -> ShellSources:
    """Return the sources the HTML shell will actually emit."""
    from bretzel.render import vendor  # casse un cycle : vendor lit d'ici

    scripts = list(_default_js(None))
    if browser_css:
        scripts.append(vendor.url_for(vendor.browser_css_asset()))
    return ShellSources(
        scripts=tuple(scripts),
        styles=tuple(_default_css(None)),
        inline=tuple(inline_scripts(mobile_breakpoint).values()),
    )


def _icon_links(favicon: str | bool | None, cache_bust: str | None) -> list[str]:
    """Les ``<link>`` d'icône du document. Il y en a TOUJOURS au moins un.

    C'est le point de la fonction : sans aucun ``<link rel="icon">``, un
    navigateur demande ``/favicon.ico`` de sa propre initiative, et une
    app Bretzel n'a pas cette route — donc un 404 par page, invisible
    partout sauf dans les logs. Retirer la marque ne doit pas coûter ça,
    d'où le ``href="data:,"`` du cas ``False`` : une URL vide et valide,
    qui satisfait le navigateur sans rien télécharger.

    Trois cas :

    - ``None`` → la marque du framework, SVG + l'icône tactile iOS ;
    - une chaîne → l'URL de l'app, avec son type MIME s'il se devine ;
    - ``False`` → le ``<link>`` vide décrit ci-dessus.
    """
    if favicon is False:
        return ['<link rel="icon" href="data:,"/>']
    if favicon is None or favicon is True:
        return [
            '<link rel="icon" type="image/svg+xml" '
            f'href="{escape_attr(_bust(ROUTE_FAVICON, cache_bust))}"/>',
            '<link rel="apple-touch-icon" '
            f'href="{escape_attr(_bust(ROUTE_TOUCH_ICON, cache_bust))}"/>',
        ]
    href = str(favicon)
    suffix = href.rsplit("?", 1)[0].rsplit("#", 1)[0].lower()
    mime = next((v for k, v in _ICON_TYPES.items() if suffix.endswith(k)), None)
    type_attr = f' type="{mime}"' if mime else ""
    return [f'<link rel="icon"{type_attr} href="{escape_attr(href)}"/>']


def _build_head(
    *,
    title: str,
    description: str | None,
    charset: str,
    css_urls: list[str],
    js_urls: list[str],
    meta_tags: Iterable[Mapping[str, str]],
    favicon: str | bool | None,
    cache_bust: str | None,
    head_extras: Iterable[Node],
    envelope_json: str,
    browser_css: bool,
    theme_css_content: str,
    mobile_breakpoint: int = 768,
    nav_progress: bool = True,
    manifest_url: str | None = None,
    theme_color: str | None = None,
) -> str:
    parts: list[str] = [
        f'<meta charset="{escape_attr(charset)}"/>',
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>',
        # htmx history snapshot off (cf. _HTMX_CONFIG) — must precede the
        # deferred htmx <script> so it's read at load. Single-quoted attr
        # value : the content is JSON with double quotes.
        f"<meta name=\"htmx-config\" content='{_HTMX_CONFIG}'/>",
        f"<title>{escape_html(title)}</title>",
    ]
    if description is not None:
        parts.append(
            f'<meta name="description" content="{escape_attr(description)}"/>'
        )
    # ── PWA ──────────────────────────────────────────────────────────
    # Le ``<link rel="manifest">`` est ce qui RATTACHE le manifeste au
    # document : servir le fichier ne suffit pas, aucun navigateur ne le
    # cherche de lui-même. Et il vient AVANT les icônes de favicon, qui
    # sont une autre affaire — le favicon habille l'onglet, le manifeste
    # habille l'app installée.
    if manifest_url:
        parts.append(f'<link rel="manifest" href="{escape_attr(manifest_url)}"/>')
    if theme_color:
        parts.append(
            f'<meta name="theme-color" content="{escape_attr(theme_color)}"/>'
        )
    parts.extend(_icon_links(favicon, cache_bust))
    # User-supplied <meta> tags (key/value pairs).
    for tag in meta_tags:
        attrs = " ".join(
            f'{escape_attr(k)}="{escape_attr(str(v))}"' for k, v in tag.items()
        )
        parts.append(f"<meta {attrs}/>")

    # Les corps viennent de ``inline_scripts`` — la MÊME source que les
    # empreintes publiées dans ``script-src``. Cf. sa docstring.
    _inline = inline_scripts(mobile_breakpoint)
    parts.append(f"<script>{_inline['fouc']}</script>")
    parts.append(f"<script>{_inline['screen']}</script>")
    # Anti-flash style — même idée, pour les éléments encore non
    # hydratés : ``[bz-data]`` reste invisible jusqu'à
    # ``html.bz-ready``, et un overlay ``data-open="false"`` ne
    # flashe pas. (La V3 n'a plus de ``x-cloak`` : c'est ce
    # sélecteur-là qui fait le travail.) Voir la docstring de la
    # constante pour pourquoi ça ne peut pas passer par Tailwind.
    parts.append(f"<style>{_ANTI_FLASH_STYLE}</style>")
    # Pygments .bz-code rules — coloured spans inside ui.code blocks.
    parts.append(f"<style>{_PYGMENTS_STYLE}</style>")
    # Chart entry-animation keyframes (line draw, bar grow, slice
    # pop). Gated behind ``prefers-reduced-motion: no-preference`` so
    # accessibility preferences win automatically.
    parts.append(f"<style>{_CHARTS_ENTRY_STYLE}</style>")
    # Toast enter / leave keyframes (paired with the two-phase dismiss in
    # ``09_notification.js``). Same reduced-motion gate as the charts.
    parts.append(f"<style>{_NOTIFICATION_ANIM_STYLE}</style>")
    if nav_progress:
        parts.append(f"<style>{_NAV_PROGRESS_ANIM_STYLE}</style>")

    # Dev : load the in-browser Tailwind v4 compiler + inline the
    # theme source. ``@tailwindcss/browser`` watches the DOM for
    # utility classes and reads ``<style type="text/tailwindcss">``
    # blocks. No build step required.
    #
    # Note : the browser CDN already imports ``tailwindcss`` itself —
    # leaving the literal ``@import "tailwindcss"`` line in the inline
    # block makes the browser fetch ``/tailwindcss`` and bail with a
    # 404. Strip it before injection. The standalone CLI (prod) still
    # needs the @import, so we only mutate here in dev.
    if browser_css:
        from bretzel.render import vendor  # casse un cycle : vendor lit d'ici

        compilateur = vendor.url_for(vendor.browser_css_asset())
        parts.append(f'<script src="{escape_attr(compilateur)}"></script>')
        if theme_css_content:
            inline_css = _strip_tailwind_import(theme_css_content)
            parts.append(
                f'<style type="text/tailwindcss">{inline_css}</style>'
            )

    # Stylesheets : framework first, app overrides ride on css_urls.
    for url in css_urls:
        parts.append(f'<link rel="stylesheet" href="{escape_attr(url)}"/>')

    # Bootstrap envelope — ``serialize_envelope`` already produced the
    # complete ``<bz-envelope>…</bz-envelope>`` tag (V3 wire format) ;
    # interpolated VERBATIM, runtime.js parses it on DOMContentLoaded.
    parts.append(envelope_json)

    # Theme payload — read by 09_notification.js (and any future
    # runtime-managed component that needs Tailwind classes resolved
    # from a Python source of truth). Injected synchronously so it's
    # available the moment the deferred ``runtime.js`` evaluates.
    # Keeps the theme as the single source of truth in Python ; the
    # JS never carries its own copy of the class strings.
    parts.append(f"<script>{_inline['theme']}</script>")

    # ⚠️ **Avant les scripts, et sans ``defer``.** Le composant web
    # iconify lit ``window.IconifyProviders`` à son initialisation ; posé
    # après lui, le réglage arrive trop tard et les glyphes sont déjà
    # partis chez le tiers.
    #
    # Ce que ça change : le navigateur du visiteur ne parle plus à
    # ``api.iconify.design`` (ni à ses deux secours) — c'est l'app qui
    # relaie, une fois, puis sert de son cache de projet. Mesuré le
    # 2026-09-13 : les trois hôtes coupés rendaient **0 glyphe sur 25**,
    # et rapatrier le composant n'y changeait rien, parce que c'est la
    # DONNÉE qui vient de chez eux.
    parts.append(f"<script>{_inline['icons']}</script>")

    # Framework JS — defer so the body can render before they execute.
    for url in js_urls:
        parts.append(f'<script defer src="{escape_attr(url)}"></script>')

    # User-supplied <head> extras (ui.title() / ui.meta_tag() / og:image).
    # We accept any Node ; serialize each through the core serializer.
    for node in head_extras:
        parts.append(serialize(node))

    return "<head>\n  " + "\n  ".join(parts) + "\n</head>"


def _build_body(body_html: str, page_uuid: str, *, nav_progress: bool = True) -> str:
    """Wrap the inner body in the ``bz-page-<uuid>`` div (CR-3).

    The wrapper carries :

    - A fresh per-render UUID so idiomorph treats consecutive page
      renders as distinct elements (forces destroy + create on
      navigation, eliminating stale ``bz-*`` bindings).
    - ``data-bretzel-page-id`` mirrors the UUID for tooling.
    - ``hx-headers`` echoes the page id back on every HTMX action, so
      the server can tell stale-tab requests apart.

    The body itself paints ``bg-background text-text`` so the page has
    the design system's neutrals from frame zero, descendants inherit
    text-colour through the cascade, and ``ring-offset-background``
    on focus rings actually matches what's underneath the button —
    no more cream halo on a pure-white body.

    Refreshable swaps ride ``hx-swap-oob="morph"`` through the
    idiomorph htmx-2 extension (``hx-ext="morph"`` on the body) ; the
    V3 runtime re-binds ``bz-*`` directives on every swapped subtree.
    """
    safe_uuid = escape_attr(page_uuid)
    wrapper_id = f"bz-page-{safe_uuid}"
    # ``hx-headers`` était le SEUL attribut du dépôt émis entre simples
    # quotes — parce que sa valeur est du JSON, donc pleine de ``"``. Ça
    # tenait tant qu'``escape_attr`` échappait aussi ``'`` ; ce n'est plus
    # le cas (mesuré : 6 octets par apostrophe, ~4 % de chaque page, et
    # les expressions ``bz-*`` en sont truffées). On repasse donc en
    # doubles quotes et on laisse ``escape_attr`` plier les ``"``
    # intérieurs en ``&quot;`` — le parseur HTML les rend à htmx tels
    # quels, et il lit du JSON valide. Quatre entités par page, une fois.
    #
    # ⚠️ Ne réintroduis pas de simple quote ici : la précondition
    # d'``escape_attr`` est désormais « valeur entre DOUBLES quotes »,
    # et ``test_escape_attr_result_is_quoted`` la fait respecter.
    hx_headers = escape_attr(f'{{"{HEADER_PAGE_ID}": "{page_uuid}"}}')
    # Notification toaster skeleton — six empty position stacks with
    # all Tailwind classes + transitions as literal attribute values.
    # Pre-rendered server-side so the CSS compiler scans them on the
    # SSR pass : transitions, accents, chrome are all available the
    # moment the page paints, before the first toast is queued. The
    # runtime only pushes data into the toaster's ``bz-data`` scope via a
    # ``bz:notify`` DOM event — the ``<template bz-for>`` materialises each
    # toast.
    from bretzel.components.feedback.notification.notification import (
        skeleton_html as _notification_skeleton,
    )
    toaster_html = _notification_skeleton()
    nav_bar_html = nav_progress_html() if nav_progress else ""
    # Automatic partial-nav : when the page carries an outlet, boost every
    # plain internal ``<a>`` into a SPA swap of that outlet — the shell /
    # sidebar stay mounted, no per-link opt-in. ``hx-target``/``hx-swap``
    # are inherited but harmless to the rest : action buttons set an
    # explicit ``hx-target=#bz-sink`` (events.py), refreshables ride
    # ``hx-swap-oob``, the SSE refetch uses ``swap:'none'`` — only boosted
    # links (no explicit ``hx-*``) pick up this target. Forms opt out via
    # ``hx-boost="false"`` (Form.render). External links (``target=_blank``)
    # and ``#hash`` are skipped by htmx natively. Gated on an outlet
    # actually being present so layout-less pages keep plain anchors.
    boost = (
        ' hx-boost="true" hx-target="[data-bz-outlet]" '
        'hx-swap="morph:innerHTML"'
        if "data-bz-outlet" in body_html
        else ""
    )
    # Embed the body html as-is — caller is responsible for it being
    # already-serialised + safe.
    return (
        "<body "
        # ``hx-ext="morph"`` opts the whole document into idiomorph for
        # every htmx swap (partial nav, action OOB fragments, realtime
        # refetches). Idiomorph matches by ``id``/``bz-id`` ; the V3
        # runtime keeps bz-data scope state in its own Map keyed by
        # bz-id, so swapped subtrees keep their client state and the
        # bridge re-binds directives after each swap.
        'hx-ext="morph" '
        'class="bg-background text-text transition-colors duration-200">\n'
        f'  <div id="{wrapper_id}" data-bretzel-page-id="{safe_uuid}"{boost} '
        f'hx-headers="{hx_headers}">\n'
        f"    {body_html}\n"
        "  </div>\n"
        f"  {nav_bar_html}\n"
        f"  {toaster_html}\n"
        # Permanent action sink : actions target it so the non-OOB part
        # of the response (where <bz-patch> rides) lands in the DOM
        # instead of being dropped by hx-swap="none" (Phase 0 learning).
        # Notifications ride the same <bz-patch> path (the V2
        # #bz-script-outbox is gone).
        f'  <div id="{SINK_ELEMENT_ID}" hidden></div>\n'
        "</body>"
    )


__all__ = [
    "DEFAULT_HTMX_URL",
    "default_shell",
    "inline_scripts",
    "shell_sources",
]


# Convenience for tests : expose the FOUC body so it can be asserted
# on (without callers having to know the exact minified text).
def _fouc_script() -> str:
    return _FOUC_SCRIPT

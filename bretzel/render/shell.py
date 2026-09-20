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
# ⚠️ **EXACT version, and that is what changed on 2026-09-13.** The URL
# was plain ``@4``, so a range: unpkg resolved to the latest 4.x of the
# day, and the dev compiler could change under our feet without a line of
# the repository moving. A fingerprint means nothing on a range, so this
# script was the only one of the four that could be neither verified nor
# vendored (cf. :mod:`bretzel.render.vendor`).
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
    # ⚠️ Scoped to ``html:not(.bz-ready)`` — that is ONE rule, not a
    # pair. It used to be a pair: a global ``[bz-data]{visibility:hidden}``,
    # then ``html.bz-ready [bz-data]{visibility:visible}`` to lift it.
    # Writing ``visible`` explicitly on every scope frees it from EVERY
    # hidden ancestor, and ``visibility`` is precisely the property a
    # descendant can take back. A closed ``ui.dialog`` hides itself with
    # ``visibility:hidden`` (``data-[open=false]:invisible``): the first
    # client-state component it contains therefore became visible again —
    # invisible to the eye, it takes no space and nothing paints it, but
    # FOCUSABLE. Measured on 2026-09-07 on ``examples/messagerie``: the
    # page's 2nd tab landed in the ``ui.file_upload`` of a closed dialog,
    # then replayed on a bench on 2026-09-10.
    #
    # A single rule bounded to pre-boot says the same thing without ever
    # lifting anything: after ``.bz-ready`` no declaration targets those
    # elements any more, so inheritance takes over. Subtrees inserted
    # AFTER boot (partial-nav morph) are visible in both versions — the
    # pair lifted them, this one does not hide them.
    "html:not(.bz-ready) [bz-data]{visibility:hidden}"
    "bz-envelope,bz-patch{display:none}"
    # Closed state of overlays (dialog / drawer), declared BEFORE the
    # first paint. Without it, the backdrop's Tailwind decoration
    # (``fixed inset-0 bg-black/50 backdrop-blur-sm``) arrives after the
    # first paint and ``opacity`` / ``visibility``, which are inside a
    # ``transition``, animate from their unstyled value (1 / visible): a
    # full-screen blurred veil fades out over 200 ms on every page
    # carrying an overlay. Declaring it here means the value no longer
    # moves when the sheet arrives, so no transition starts.
    #
    # The rule cannot ride on Tailwind (it must be there at the first
    # paint, before it) and cannot target bare ``[data-open=false]``:
    # sidebar (collapsed rail) and accordion carry the same attribute and
    # would be hidden. Hence the ``data-bz-overlay`` marker, set by
    # ``components.base._wiring.show_attrs``.
    #
    # ⚠️ Scoped to ``html:not(.bz-ready)`` — the rule lives ONLY before
    # boot, which is what it exists for. It used to be global, and the
    # original reasoning ("no ``!important``, the Tailwind utility takes
    # over") only holds for the darkened BACKDROP, which does carry a
    # ``data-[open=false]:opacity-0``. A drawer's PANEL has no opacity
    # utility — it must only slide
    # (``transition-[translate,visibility]``). Nothing took over,
    # therefore, and this rule forced ``opacity:0`` on it WITHOUT a
    # transition.
    #
    # Measured frame by frame on 2026-08-18, on close: opacity 1 → 0 in
    # under 145 ms while the ``translate`` ran to 400 ms. The panel
    # finished its slide invisibly — one saw an abrupt fade, never the
    # slide. Reported by eye: "it fades instead of sliding closed".
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

#: The strip that slides during a navigation. A shell keyframe, like
#: the toast's two just above, and for the same reason: Tailwind has no
#: built-in slide, and an ASSEMBLED class would exist only in dev. The
#: motionless fallback is not decorative — outside ``no-preference`` the
#: strip stays full width and still, so it still says "working" without
#: moving.
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
    """The navigation bar, injected once per page.

    **It has no mechanism of its own.** It is ``ui.pending()``'s signal
    read on a RESERVED key: the bridge arms ``@nav`` when the in-flight
    request is a navigation (boosted, or carrying ``hx-push-url``), and
    this strip is nothing but one more ``bz-show``. An ``action_id`` is
    ``module::qualname`` and can therefore never start with ``@`` — the
    key is safe from a collision.

    The 200 ms threshold is ``ui.pending()``'s, and it matters more here:
    a fast partial navigation is the norm, so without it every menu click
    would flash a bar.

    This is **not** a ``ui.progress``: no progress is known (the server
    does not say how far along its render is), and an invented fraction
    would be a lie. It is an activity indicator, therefore an
    indeterminate strip. Its colour is literal (``bg-primary``) — the
    app's chrome follows the accent, and a class composed from a variable
    would not survive the production compiler.

    ``z-50`` is the TOP of the house scale (the toaster and the dialog
    are there) — not a new rung above. A 2 px bar at the screen edge has
    nothing to dispute with a modal, and inventing a rung for it alone
    would make the scale drift.

    ``style="display:none"`` is pre-set: nothing can be in flight at the
    moment the server renders, so the bar must not flash on load — same
    guard as ``ssr_value=False`` on the Python side.
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
    # The effective CSS pipeline, not the mode: it is the only thing
    # that decided the RENDER from an environment boolean. Cf.
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
        # Browser compiler: no ``<link>``, it reads the inline
        # ``<style type="text/tailwindcss">`` block below.
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
    # Order matters with ``defer`` scripts:
    # 1. HTMX must load first; the runtime bridge wires its events.
    # 2. Idiomorph (htmx-2 extension) must load AFTER htmx so its
    #    ``htmx.defineExtension('morph', ...)`` can register before
    #    the first swap.
    # 3. ``runtime.js`` last — its bootstrap runs at DOMContentLoaded
    #    and expects ``window.htmx`` to exist. No Alpine in V3.
    #
    # The first three come from the CDN **as long as they have not been
    # vendored**. Measured on 2026-08-27 in prod, cold cache: 593 / 592 /
    # 489 ms against 20-40 ms for a resource served by the app. A
    # ``python -m bretzel.render.vendor`` puts them in
    # ``.bretzel/vendor/`` and this list switches over by itself (cf.
    # ``vendor.url_for``).
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

    Currently carries the notification toaster theme; future
    runtime-managed components add their entries here. Single-quoted
    JSON inside ``</script>`` is safe because the keys + class
    strings never contain ``</script>``.

    ⚠️ **It is NOT ``json.dumps`` that protects**: it escapes neither
    ``<`` nor ``>`` (``json.dumps('<a>')`` returns ``"<a>"``). This
    sentence claimed otherwise until 2026-08-01. Safety here rests on the
    payload being built by the framework from the theme's palette — not
    on an escape. A user-influenceable payload would have to go through
    ``escape_inline_json``, like ``serialize_envelope``.
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


#: The MIME types the browser wants to see on a ``rel="icon"``. A
#: correct ``type=`` lets Chrome prefer the SVG without downloading the
#: rest; a wrong ``type=`` makes it ignore it. So we only set it on the
#: extensions we recognise, and stay silent about the others.
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
    """The BODIES of the inline ``<script>`` the shell emits, named.

    A single source, and that is its whole point: the security policy
    (:mod:`bretzel.server.security`) publishes the ``sha256`` of each of
    those bodies in ``script-src``, and ``_build_head`` emits those same
    bodies. A fourth inline script added here is hashed without anyone
    thinking about it; added elsewhere, it is not, and the page breaks
    under CSP. That is this function's reason to exist, and
    ``tests/consistency/test_every_inline_script_is_in_the_policy.py``
    is what keeps it from being bypassed.

    The three bodies are **deterministic** — they depend only on the
    theme and on ``mobile_breakpoint``, never on the request. Measured on
    2026-09-05: 3 distinct fingerprints across 77 pages × 2 requests.
    That is what allows hashes rather than a ``nonce``, which would have
    forced one value per response (hence an uncacheable page) and one
    more parameter on every custom shell.
    """
    return (
        # Before any stylesheet: the ``.dark`` class must be on <html>
        # by the time styles are computed.
        ("fouc", _FOUC_SCRIPT),
        # Same slot. The sync function first (it writes ``bz_screen``
        # from matchMedia so the next render reads it server-side), then
        # the bootstrap that spends the corrective reload if this paint
        # is stale.
        (
            "screen",
            f"{_screen_sync_script(mobile_breakpoint)}{_screen_boot_script()}",
        ),
        # The framework theme exposed to the runtime as ``window.$bz_theme``.
        ("theme", _theme_payload_js()),
        # Where the iconify component must look for its GLYPHS. Without
        # this setting it queries three third-party hosts; with it, it
        # goes through our route, which relays once then serves from its
        # cache.
        ("icons", _icon_provider_script()),
    )


def _icon_provider_script() -> str:
    """``window.IconifyProviders`` — the local route rather than three CDNs.

    The iconify web component reads this global at initialisation.
    Vendoring the component (cf. :mod:`bretzel.render.vendor`) vendors
    ONLY the component: its glyphs go out at runtime to
    ``api.iconify.design`` and two fallback hosts. Measured on
    2026-09-13, with all three cut off: **0 glyphs out of 25**.

    ⚠️ It must run BEFORE the component's script, so without ``defer`` —
    placed after, the setting arrives when the glyphs have already gone
    out.
    """
    return f'window.IconifyProviders={{"":{{resources:["{ROUTE_ICONS}"]}}}};'


def inline_scripts(mobile_breakpoint: int) -> dict[str, str]:
    """The inline bodies, named. Cf. :func:`_inline_scripts`.

    The computation is memoised (the hashable tuple next door) and this
    wrapper returns a FRESH dict: memoising a dict would make it mutable
    by its callers. Measured on 2026-09-06: ``_theme_payload_js()`` cost
    26 µs on EVERY page render to re-serialise the same palette — its own
    docstring already said the three bodies are deterministic.
    """
    return dict(_inline_scripts(mobile_breakpoint))


@dataclass(frozen=True, slots=True)
class ShellSources:
    """Everything the shell loads or runs — the surface a CSP covers.

    ``scripts`` and ``styles`` are separate because a script origin has
    no business in ``style-src``. ``inline`` carries the bodies
    :func:`inline_scripts` declares, whose fingerprint the policy
    publishes.
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
    """The document's icon ``<link>``. There is ALWAYS at least one.

    That is the function's point: with no ``<link rel="icon">`` at all, a
    browser requests ``/favicon.ico`` on its own initiative, and a
    Bretzel app does not have that route — so a 404 per page, invisible
    everywhere but in the logs. Removing the mark must not cost that,
    hence the ``href="data:,"`` of the ``False`` case: an empty, valid
    URL that satisfies the browser without downloading anything.

    Three cases:

    - ``None`` → the framework's mark, SVG + the iOS touch icon;
    - a string → the app's URL, with its MIME type if it can be guessed;
    - ``False`` → the empty ``<link>`` described above.
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
    # The ``<link rel="manifest">`` is what ATTACHES the manifest to the
    # document: serving the file is not enough, no browser looks for it
    # on its own. And it comes BEFORE the favicon icons, which are
    # another matter — the favicon dresses the tab, the manifest dresses
    # the installed app.
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

    # The bodies come from ``inline_scripts`` — the SAME source as the
    # fingerprints published in ``script-src``. Cf. its docstring.
    _inline = inline_scripts(mobile_breakpoint)
    parts.append(f"<script>{_inline['fouc']}</script>")
    parts.append(f"<script>{_inline['screen']}</script>")
    # Anti-flash style — same idea, for the elements not yet
    # hydrated: ``[bz-data]`` stays invisible until
    # ``html.bz-ready``, and an overlay with ``data-open="false"``
    # does not flash. (V3 no longer has ``x-cloak``: that selector
    # does the work.) See the constant's docstring for why this
    # cannot go through Tailwind.
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

        compiler = vendor.url_for(vendor.browser_css_asset())
        parts.append(f'<script src="{escape_attr(compiler)}"></script>')
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

    # ⚠️ **Before the scripts, and without ``defer``.** The iconify web
    # component reads ``window.IconifyProviders`` at initialisation;
    # placed after it, the setting arrives too late and the glyphs have
    # already gone out to the third party.
    #
    # What it changes: the visitor's browser no longer talks to
    # ``api.iconify.design`` (nor to its two fallbacks) — the app relays,
    # once, then serves from its project cache. Measured on 2026-09-13:
    # the three hosts cut off returned **0 glyphs out of 25**, and
    # vendoring the component changed nothing, because it is the DATA
    # that comes from them.
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
    # ``hx-headers`` was the ONLY attribute in the repository emitted
    # between single quotes — because its value is JSON, hence full of
    # ``"``. That held as long as ``escape_attr`` also escaped ``'``;
    # that is no longer the case (measured: 6 bytes per apostrophe, ~4 %
    # of every page, and the ``bz-*`` expressions are riddled with them).
    # So we go back to double quotes and let ``escape_attr`` fold the
    # inner ``"`` into ``&quot;`` — the HTML parser hands them back to
    # htmx as-is, and it reads valid JSON. Four entities per page, once.
    #
    # ⚠️ Do not reintroduce a single quote here: ``escape_attr``'s
    # precondition is now "value between DOUBLE quotes", and
    # ``test_escape_attr_result_is_quoted`` enforces it.
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

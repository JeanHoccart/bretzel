"""What the page carries hidden — measured where it is decided, in the browser.

``visible=`` bound to a ``ClientState`` hides; it removes nothing from the
HTML. Every hidden branch is rendered by the server, shipped, and redrawn
by the actions that touch it. ``bretzel check`` notes the shape
(``hidden-branch-rendered``); the weight is read here:

- **at each load** (``Window.goto``): the bytes of the page under a
  computed ``display: none``, and, among them, those hidden by a
  ``visible=`` bound to a state (a ``bz-show`` that reads ``$bz.state``).
  Beyond :data:`HIDDEN_KB` or :data:`HIDDEN_SHARE` of the page, the
  finding names the biggest hidden subtrees and the state expression that
  hides them. Only that is judged: a closed menu, dialog or tree branch is
  the component's own state, and its weight belongs to the speed
  measures, not here;
- **at each action**: every zone the server rendered for the response
  (``X-Bretzel-Zone-Hashes``, sent or kept quiet alike — the render is
  paid either way) whose root is hidden once the swap has landed.

Measured on Orga: half of a 338 KB page hidden by the shell's
``Disposition``, and the compact thread list redrawn at every opened
thread, panel closed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any

from bretzel.runtime.protocol import (
    BZ_ID_ATTR,
    BZ_SHOW_PREFIX,
    DATA_ZONE,
    HEADER_PAGE_ID,
    HEADER_ZONE_HASHES,
)

#: What the sweep can do with a finding. It receives the function, not
#: the ``Probe``: a policy does not consume the object calling it.
Check = Callable[[str, bool, object], None]

#: Beyond this much content hidden by ``visible=``, the load is red…
HIDDEN_KB = 20
#: … or beyond this share of the page.
HIDDEN_SHARE = 0.25


def _with_protocol(js: str) -> str:
    """The protocol's names put into a script — never retyped there: a
    renamed attribute would leave the measure silent, and green."""
    for token, value in (("@SHOW@", BZ_SHOW_PREFIX), ("@ID@", BZ_ID_ATTR),
                         ("@ZONE@", DATA_ZONE), ("@HASHES@", HEADER_ZONE_HASHES),
                         ("@PAGE@", HEADER_PAGE_ID)):
        js = js.replace(token, value)
    return js


#: The topmost elements under ``display: none`` in ``<body>``, their bytes
#: (UTF-8, as they travel) and the state expression hiding them.
LOAD_JS = _with_protocol(r"""
() => {
    const size = (s) => new TextEncoder().encode(s).length;
    const skip = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT', 'LINK', 'META']);
    const roots = [];
    const walk = (el) => {
        for (const child of el.children) {
            if (skip.has(child.tagName)) continue;
            if (getComputedStyle(child).display === 'none') roots.push(child);
            else walk(child);
        }
    };
    walk(document.body);
    const subtrees = roots.map((el) => {
        const show = el.getAttribute('@SHOW@') || '';
        return {
            bytes: size(el.outerHTML),
            by: show.includes('$bz.state.') ? show : null,
            what: el.tagName.toLowerCase(),
            text: (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40),
        };
    });
    const bound = subtrees.filter((s) => s.by).sort((a, b) => b.bytes - a.bytes);
    return {
        page: size(document.documentElement.outerHTML),
        hidden: subtrees.reduce((n, s) => n + s.bytes, 0),
        byVisible: bound.reduce((n, s) => n + s.bytes, 0),
        biggest: bound.slice(0, 3),
    };
}
""")

#: Installed before any page script: after each action response, the zones
#: the server rendered for it, and what hides each once the swap has
#: landed (``display: none`` on it or an ancestor — not
#: ``checkVisibility()``, which a ``display: contents`` zone fails). A
#: response that starts a page is a load, not an action. Reported through
#: the binding ``__bzProbeRedrawn``, which survives navigations.
REDRAWN_JS = _with_protocol(r"""
(() => {
    const judge = (ids) => {
        for (const id of ids) {
            const live = document.querySelector('[@ZONE@][@ID@="' + CSS.escape(id) + '"]');
            if (!live) continue;
            let up = live, by = null;
            while (up && up.nodeType === 1) {
                if (getComputedStyle(up).display === 'none') {
                    by = up.getAttribute('@SHOW@') || up.tagName.toLowerCase();
                    break;
                }
                up = up.parentElement;
            }
            window.__bzProbeRedrawn(by === null ? {zone: id, by} : {
                zone: id, by,
                bytes: new TextEncoder().encode(live.outerHTML).length,
                text: (live.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40),
            });
        }
    };
    document.addEventListener('htmx:afterRequest', (e) => {
        const xhr = e.detail && e.detail.xhr;
        if (!xhr || !xhr.getResponseHeader || xhr.getResponseHeader('@PAGE@')) return;
        const ids = (xhr.getResponseHeader('@HASHES@') || '').split(',')
            .map((pair) => pair.slice(0, pair.indexOf(':'))).filter(Boolean);
        if (ids.length) setTimeout(() => judge(ids), 0);
    }, true);
})();
""")


def _kb(n: int) -> str:
    return f"{n / 1024:.0f} KB"


def judge_loads(check: Check, name: str, loads: list[tuple[str, dict[str, Any]]]) -> None:
    """One finding per page loaded: is what ``visible=`` hides light?"""
    for path, seen in loads:
        page, hidden = seen["page"], seen["byVisible"]
        heavy = hidden > HIDDEN_KB * 1024 or hidden > HIDDEN_SHARE * page
        biggest = "; ".join(
            f"{_kb(s['bytes'])} {s['what']} hidden by `{s['by']}` ({s['text']!r})"
            for s in seen["biggest"])
        check(
            f"[{name}] {path} — what visible= hides stays light",
            not heavy,
            f"{_kb(hidden)} of {_kb(page)} hidden by a visible= "
            f"({100 * hidden // max(page, 1)} %, {_kb(seen['hidden'])} under display:none "
            f"in all) — biggest: {biggest}. Heavy content is chosen on the server "
            f"(PageState field(url=...) or UserState) — choisir-etat-et-composant.md",
        )


def judge_redraws(check: Check, name: str, redrawn: list[dict[str, Any]]) -> None:
    """The zones the actions rendered while they were hidden."""
    hidden = [r for r in redrawn if r["by"] is not None]
    counted = Counter((r["zone"], r["by"], r["text"]) for r in hidden)
    check(
        f"[{name}] no action redraws a hidden zone",
        not hidden,
        f"{len(hidden)} of {len(redrawn)} zone renders landed hidden "
        f"(zones of {_kb(sum(r['bytes'] for r in hidden))} rendered for nobody): "
        + "; ".join(f"{zone} ×{n} hidden by `{by}` ({text!r})"
                    for (zone, by, text), n in counted.most_common(3)),
    )

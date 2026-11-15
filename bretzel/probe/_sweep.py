"""The free sweep — what nobody rewrites, so nobody forgets.

It runs when the ``with`` exits, on every window, without a probe having
to ask for it.

What it does NOT do, and why: the "distinct colours" and "distinct
sizes" probes of ``creating-a-component.md`` § 9 compare the VARIANTS of
a component mounted on its own. They make no sense on an assembled app,
where there are no two variants to compare. They stay with the component
harness; claiming them here would make two green lines that measure
nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from bretzel.probe._hidden import Check, judge_loads, judge_redraws
from bretzel.probe._window import Window

#: C1 — "the SMALLEST plausible window, never the largest". Measuring at
#: 1500×940 validates the size where everything fits. The second size is
#: not a luxury: a probe's "every column fits" may hold at its own size
#: only.
SECOND_SIZE = (1366, 640)

#: ⚠️ A RAW string: the JS below carries regular expressions, and a
#: ``\s`` interpreted by Python would arrive at the browser as a literal
#: space — a syntax error at evaluation time, so a sweep that RAISES
#: instead of measuring.
_GEOMETRY_JS = r"""
() => {
    const doc = document.documentElement;
    const vw = doc.clientWidth, vh = doc.clientHeight;
    const scrollers = [];
    const clipped = [];
    const scrolls = (el) => /auto|scroll/.test(getComputedStyle(el).overflowY)
        && el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 1;
    // A region inside a region that scrolls is CAUGHT when that one, scrolled
    // to its end, shows its bottom: the page's ``ui.pane`` brings a plan as
    // tall as the screen into view. Measured at its ancestor's end, not
    // where the scroll stands: otherwise the verdict goes with wherever
    // the 20th Tab of ``_tab_order`` left the page.
    const caught = (el, r) => {
        let up = el.parentElement;
        while (up && up !== document.body && !scrolls(up)) up = up.parentElement;
        if (!up || up === document.body) return false;
        const left = up.scrollHeight - up.clientHeight - up.scrollTop;
        const shown = up.getBoundingClientRect().top + up.clientTop + up.clientHeight;
        return r.bottom - left <= shown + 1;
    };
    for (const el of document.querySelectorAll('*')) {
        const st = getComputedStyle(el);
        const overflows = el.scrollHeight > el.clientHeight + 1
            && el.clientHeight > 0;
        if (/auto|scroll/.test(st.overflowY) && overflows
            && !caught(el, el.getBoundingClientRect())) {
            const r = el.getBoundingClientRect();
            scrollers.push({
                tag: el.tagName.toLowerCase(),
                cls: (el.getAttribute('class') || '').slice(0, 60),
                bottom: Math.round(r.bottom),
            });
        }
        // Clipped FOR GOOD: no scrollbar, no recourse. The 2 px margin
        // sets aside the sub-pixel rounding of a line of text, which
        // hides nothing. A box of 1 px both ways is hidden ON PURPOSE —
        // ``sr-only``: a native input a component drives, a label for
        // screen readers — and shows nothing a reader would miss.
        const visuallyHidden = el.clientWidth <= 1 && el.clientHeight <= 1;
        if (/hidden|clip/.test(st.overflowY)
            && el.clientHeight > 0
            && !visuallyHidden
            && el.scrollHeight > el.clientHeight + 2
            && el.offsetParent !== null) {
            clipped.push({
                tag: el.tagName.toLowerCase(),
                cls: (el.getAttribute('class') || '').slice(0, 40),
                shown: el.clientHeight,
                needed: el.scrollHeight,
                text: (el.innerText || '').split('\n')[0].slice(0, 30),
            });
        }
    }
    return {
        overflowX: Math.max(0, doc.scrollWidth - vw),
        documentScrolls: doc.scrollHeight > vh + 1,
        viewport: [vw, vh],
        scrollers: scrollers.slice(0, 12),
        clipped: clipped.slice(0, 8),
    };
}
"""

#: The focused element, and whether its focus ring is CLIPPED.
#:
#: A ring is a shadow, not a box: no ``scrollWidth`` sees it, and it only
#: exists while the element has focus — so the geometry sweep, which runs
#: with nothing focused, cannot catch a field flush against the edge of a
#: pane whose ``overflow`` cuts the 4 px of its ``ring-2 ring-offset-2``.
#: It is measured here, at each Tab.
#:
#: WHERE the ring is: on the focused element, or on the wrapper that
#: draws it for its field (``focus-within:ring-2`` — ``ui.input`` with an
#: affix, ``ui.textarea``), recognised by that variant in its classes.
#: WHAT it reaches: every spread-only shadow (blur 0, not transparent — a
#: drop shadow has a blur) and the outline. The transition is cut for the
#: read: ``ui.input`` slides its ring in over 200 ms, and a value read
#: mid-way would be a smaller ring than the one painted.
#:
#: Clipped means past the padding box of an ancestor that clips
#: (``overflow`` not ``visible`` on that axis, ``contain: paint``) — on a
#: side it cannot scroll further towards. Tabbing scrolls a field flush to
#: the edge of the region that holds it; that edge is not clipped for
#: good, the region scrolls on.
_TAB_JS = r"""
() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const r = el.getBoundingClientRect();
    const name = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id
        : (e.getAttribute('class') || '').split(/\s+/).filter(Boolean)
            .slice(0, 3).map((c) => '.' + c).join(''));
    const reach = (e) => {
        const had = e.hasAttribute('style'), prev = e.style.transition;
        e.style.transition = 'none';
        const st = getComputedStyle(e);
        const out = {top: 0, right: 0, bottom: 0, left: 0};
        const grow = (t, rt, b, l) => {
            out.top = Math.max(out.top, t); out.right = Math.max(out.right, rt);
            out.bottom = Math.max(out.bottom, b); out.left = Math.max(out.left, l);
        };
        for (const one of (st.boxShadow || 'none').split(/,(?![^(]*\))/)) {
            if (one === 'none' || /inset/.test(one)) continue;
            if (/transparent|,\s*0\)|\/\s*0\)/.test(one)) continue;
            const n = (one.match(/-?[\d.]+px/g) || []).map(parseFloat);
            if (n.length < 4 || n[2] !== 0 || n[3] <= 0) continue;
            const [ox, oy, , spread] = n;
            grow(spread - oy, spread + ox, spread + oy, spread - ox);
        }
        if (st.outlineStyle !== 'none') {
            const w = (parseFloat(st.outlineWidth) || 0) + (parseFloat(st.outlineOffset) || 0);
            if (parseFloat(st.outlineWidth) > 0) grow(w, w, w, w);
        }
        e.style.transition = prev;
        if (!had) e.removeAttribute('style');
        return out;
    };
    const clipped = (e) => {
        const ext = reach(e);
        if (!(ext.top > 0 || ext.right > 0 || ext.bottom > 0 || ext.left > 0)) return null;
        const b = e.getBoundingClientRect();
        if (b.width <= 1 && b.height <= 1) return null;
        const ring = {top: b.top - ext.top, right: b.right + ext.right,
                      bottom: b.bottom + ext.bottom, left: b.left - ext.left};
        for (let up = e.parentElement; up && up !== document.body; up = up.parentElement) {
            const st = getComputedStyle(up);
            const paint = /paint|strict|content/.test(st.contain);
            const cx = paint || st.overflowX !== 'visible';
            const cy = paint || st.overflowY !== 'visible';
            if (!cx && !cy) continue;
            const u = up.getBoundingClientRect();
            const left = u.left + up.clientLeft, top = u.top + up.clientTop;
            const right = left + up.clientWidth, bottom = top + up.clientHeight;
            const sx = /auto|scroll/.test(st.overflowX), sy = /auto|scroll/.test(st.overflowY);
            const sides = [];
            if (cy && ring.top < top - 0.5 && !(sy && up.scrollTop > 0)) sides.push('top');
            if (cy && ring.bottom > bottom + 0.5
                && !(sy && up.scrollTop < up.scrollHeight - up.clientHeight - 1)) sides.push('bottom');
            if (cx && ring.left < left - 0.5 && !(sx && up.scrollLeft > 0)) sides.push('left');
            if (cx && ring.right > right + 0.5
                && !(sx && up.scrollLeft < up.scrollWidth - up.clientWidth - 1)) sides.push('right');
            if (sides.length) return {ring: name(e), sides: sides, by: name(up)};
        }
        return null;
    };
    let wrapper = null;
    for (let up = el.parentElement, i = 0; up && i < 4; up = up.parentElement, i++) {
        if (/(^|\s)(focus-within|has-\[[^\]]*focus[^\]]*\]):(ring|outline)/.test(
                up.getAttribute('class') || '')) { wrapper = up; break; }
    }
    return {
        tag: el.tagName.toLowerCase(),
        x: Math.round(r.x), y: Math.round(r.y),
        w: Math.round(r.width), h: Math.round(r.height),
        closed: el.closest('[data-bz-overlay][data-open="false"]') !== null,
        ring: clipped(el) || (wrapper && clipped(wrapper)),
    };
}
"""


#: What shows BETWEEN a stuck element and the edge it sticks to.
#:
#: ``position: sticky`` sticks at its ``top`` (``bottom``, ``left``,
#: ``right``) measured inside the region's padding: a ``ui.pane`` with
#: ``padding="xs"`` and a ``sticky top-0`` search leaves a 12 px band
#: ABOVE the search, and the rows that scroll under the search reappear in
#: it (Orga's mail list). Nothing measured it: the page is
#: never scrolled while the probe looks. So each sticky element's region is
#: scrolled until content passes under it, the band between the region's
#: edge and the element is searched for a box that paints (text, a
#: background, a border, an image or a control), and the region goes back
#: where it was. Another stuck element in the band is not content: two
#: headers stacked on purpose.
_STICKY_JS = r"""
() => {
    const name = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id
        : (e.getAttribute('class') || '').split(/\s+/).filter(Boolean)
            .slice(0, 3).map((c) => '.' + c).join(''));
    const AXES = {
        top: {y: true, start: true}, bottom: {y: true, start: false},
        left: {y: false, start: true}, right: {y: false, start: false},
    };
    const scrolls = (e, y) => {
        const st = getComputedStyle(e);
        return y ? /auto|scroll/.test(st.overflowY) && e.scrollHeight > e.clientHeight + 1
                 : /auto|scroll/.test(st.overflowX) && e.scrollWidth > e.clientWidth + 1;
    };
    const visible = (e) => {
        if (e.offsetParent === null && getComputedStyle(e).position !== 'fixed') return false;
        const st = getComputedStyle(e);
        if (st.visibility === 'hidden' || parseFloat(st.opacity) === 0) return false;
        if (/^(img|svg|iconify-icon|input|textarea|select|button|canvas|video)$/i.test(e.tagName)) return true;
        if (st.backgroundColor !== 'rgba(0, 0, 0, 0)' && st.backgroundColor !== 'transparent') return true;
        if (parseFloat(st.borderTopWidth) > 0 && !/transparent|, 0\)/.test(st.borderTopColor)) return true;
        for (const n of e.childNodes) if (n.nodeType === 3 && n.textContent.trim()) return true;
        return false;
    };
    // Another stuck or fixed element is not content passing by: two
    // headers stacked on purpose (``top-0`` then ``top-10``).
    const pinned = (e, box) => {
        for (let up = e; up && up !== box; up = up.parentElement)
            if (/sticky|fixed/.test(getComputedStyle(up).position)) return true;
        return false;
    };
    const found = [];
    for (const el of document.querySelectorAll('*')) {
        const st = getComputedStyle(el);
        if (st.position !== 'sticky' || el.offsetParent === null) continue;
        for (const [side, ax] of Object.entries(AXES)) {
            if (st[side] === 'auto') continue;
            let box = el.parentElement;
            while (box && box !== document.documentElement && !scrolls(box, ax.y)) box = box.parentElement;
            if (!box || box === document.documentElement) continue;
            const was = [box.scrollTop, box.scrollLeft];
            const max = ax.y ? box.scrollHeight - box.clientHeight : box.scrollWidth - box.clientWidth;
            // Scroll so content passes under the stuck element — well past
            // the start for a start edge, from the start for an end edge —
            // at nine positions 6 px apart: at one instant the band may sit
            // in the gap between two rows.
            const s0 = el.getBoundingClientRect();
            const depth = ax.start ? (ax.y ? s0.height : s0.width) + 80 : 0;
            let through = null, gap = 0;
            for (let k = 0; k < 9 && !through; k++) {
                const to = Math.min(max, depth + 6 * k);
                box.scrollTo({[ax.y ? 'top' : 'left']: to, behavior: 'instant'});
                const b = box.getBoundingClientRect(), s = el.getBoundingClientRect();
                const edge = {
                    top: b.top + box.clientTop, left: b.left + box.clientLeft,
                    bottom: b.top + box.clientTop + box.clientHeight,
                    right: b.left + box.clientLeft + box.clientWidth,
                }[side];
                // The band between the region's edge and the stuck element.
                const band = ax.y
                    ? (ax.start ? [edge, s.top] : [s.bottom, edge])
                    : (ax.start ? [edge, s.left] : [s.right, edge]);
                gap = band[1] - band[0];
                if (gap <= 0.5) break;
                for (const other of box.querySelectorAll('*')) {
                    if (other === el || el.contains(other) || other.contains(el)) continue;
                    if (pinned(other, box) || !visible(other)) continue;
                    const r = other.getBoundingClientRect();
                    // The part of ``other`` inside the band, across the
                    // stuck element's extent.
                    const x0 = Math.max(r.left, ax.y ? s.left : band[0]);
                    const x1 = Math.min(r.right, ax.y ? s.right : band[1]);
                    const y0 = Math.max(r.top, ax.y ? band[0] : s.top);
                    const y1 = Math.min(r.bottom, ax.y ? band[1] : s.bottom);
                    if (x1 - x0 <= 0.5 || y1 - y0 <= 0.5) continue;
                    // Painted THERE, not under something else that covers
                    // the band (a header stuck above this one).
                    const hit = document.elementFromPoint((x0 + x1) / 2, (y0 + y1) / 2);
                    if (hit && (hit === other || other.contains(hit))) { through = name(other); break; }
                }
            }
            box.scrollTo({top: was[0], left: was[1], behavior: 'instant'});
            if (through) found.push({
                stuck: name(el), side: side, gap: Math.round(gap),
                region: name(box), through: through,
            });
        }
    }
    return found.slice(0, 6);
}
"""


#: The controls with NO accessible name.
#:
#: An icon-only button, tab or toggle is announced "button" by a screen
#: reader, and ``get_by_role("tab", name="Drafts")`` finds nothing: no
#: verdict saw it, since the tab order and the geometry pass with an
#: unnamed control. The name is approximated as the accessible-name
#: computation does: ``aria-label``, ``aria-labelledby``, the text
#: (``aria-hidden`` content left out), an image's ``alt``, ``title``; a
#: field adds its ``<label>``, its placeholder, a button-like input its
#: value. Every rendered control is read, not only the ones Tab reaches: a
#: tab list lets ONE tab into the tab order.
_NAMES_JS = r"""
() => {
    const CONTROLS = 'button, a[href], input:not([type=hidden]), select, textarea, summary, '
        + '[role=button], [role=link], [role=tab], [role=menuitem], [role=menuitemcheckbox], '
        + '[role=menuitemradio], [role=option], [role=switch], [role=checkbox], [role=radio], '
        + '[role=treeitem]';
    const words = (e) => {
        if (e.nodeType === 3) return e.textContent;
        if (e.nodeType !== 1 || e.getAttribute('aria-hidden') === 'true') return '';
        if (e.tagName === 'IMG') return e.getAttribute('alt') || '';
        let out = '';
        for (const c of e.childNodes) out += words(c);
        return out;
    };
    const name = (e) => {
        const label = (e.getAttribute('aria-label') || '').trim();
        if (label) return label;
        const by = (e.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)
            .map((id) => document.getElementById(id)).filter(Boolean)
            .map((r) => r.textContent).join(' ').trim();
        if (by) return by;
        if (e.labels && e.labels.length) {
            const l = [...e.labels].map((x) => x.textContent).join(' ').trim();
            if (l) return l;
        }
        if (/^(button|submit|reset)$/.test(e.type || '') && e.tagName === 'INPUT') return e.value;
        if (!/^(INPUT|SELECT|TEXTAREA)$/.test(e.tagName)) {
            const t = words(e).trim();
            if (t) return t;
        }
        return (e.getAttribute('placeholder') || e.getAttribute('title') || '').trim();
    };
    const shown = (e) => {
        if (e.closest('[aria-hidden="true"], [inert]')) return false;
        const r = e.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return false;
        const st = getComputedStyle(e);
        return st.visibility !== 'hidden' && st.display !== 'none';
    };
    const tag = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id
        : (e.getAttribute('role') ? '[role=' + e.getAttribute('role') + ']' : ''));
    return [...document.querySelectorAll(CONTROLS)]
        .filter((e) => shown(e) && !name(e))
        .slice(0, 6)
        .map((e) => ({control: tag(e), html: e.outerHTML.slice(0, 120)}));
}
"""


#: Controls side by side on one row that do not have the same height.
#:
#: A ``ui.button`` (``md``, 40 px) beside a ``ui.icon_button(size="sm")``
#: (32 px) in an ``hstack``: two heights, not aligned, seen at once on
#: Orga's reply bar — and green everywhere, since each control is right on
#: its own. For each flex row, the controls of the field/button family it
#: holds (a button, a field, a select, a toggle group, a link drawn as a
#: box), each measured on its FRAME — ``ui.input`` draws its border on a
#: wrapper — must share one height, give or take 1 px. Not judged: a row
#: child holding none or several controls, anything over 64 px (a
#: textarea, a card, a list), a child out of the flow (a field's clear
#: button), tabs, options, switches, checkboxes — controls that are not a
#: line's box —, the inside of one field (a bordered frame holding its text
#: and its own small buttons), and a size LADDER: three or more controls,
#: every one a different height, shown on purpose. Heights are LAYOUT
#: heights: a transform is decoration.
_ROWS_JS = r"""
() => {
    // A control of the field/button family: the box a person lines up.
    const FIELD_INPUT = /^(text|search|email|url|tel|password|number|date|time|datetime-local|month|week)$/;
    const isControl = (e) => {
        const tag = e.tagName;
        const role = e.getAttribute('role') || '';
        if (/^(tab|menuitem|menuitemcheckbox|menuitemradio|option|switch|checkbox|radio|treeitem)$/.test(role)) return false;
        if (tag === 'BUTTON' || role === 'button' || role === 'combobox') return true;
        if (tag === 'SELECT') return true;
        if (tag === 'INPUT') return FIELD_INPUT.test(e.type || 'text');
        if (role === 'group' && e.querySelector('button')) return true;   // a toggle group
        if (tag === 'A') {
            // A link drawn as a button (a box), not a text link.
            const st = getComputedStyle(e);
            return /flex/.test(st.display) && (st.backgroundColor !== 'rgba(0, 0, 0, 0)'
                || parseFloat(st.borderTopWidth) > 0);
        }
        return false;
    };
    // The box that stands for a row's child: the ONE control it is or
    // wraps (a tooltip's wrapper, a field's frame) — none, or several, and
    // the child is not a line of controls.
    const controlOf = (child) => {
        if (isControl(child)) return child;
        const all = [...child.querySelectorAll('*')].filter(isControl);
        // A toggle group's buttons belong to the group: the outermost only.
        const inner = all.filter((x) => !all.some((y) => y !== x && y.contains(x)));
        return inner.length === 1 ? inner[0] : null;
    };
    // What the eye lines up is the control's FRAME: ``ui.input`` draws its
    // border on a wrapper around the ``<input>``. Climb while the parent is
    // the same box give or take 4 px, never past the row.
    const frameOf = (control, row) => {
        let f = control;
        // The LAYOUT height (``offsetHeight``): a transform is decoration —
        // the current page of ``ui.pagination`` is drawn at ``scale-110`` on
        // purpose, and is the same box as its neighbours.
        const h = control.offsetHeight;
        while (f.parentElement && f.parentElement !== row
               && f.parentElement.offsetHeight - h <= 4) f = f.parentElement;
        return f;
    };
    const shown = (e) => {
        const r = e.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        const st = getComputedStyle(e);
        return st.visibility !== 'hidden' && st.display !== 'none';
    };
    const name = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id
        : (e.getAttribute('class') || '').split(/\s+/).filter(Boolean)
            .slice(0, 3).map((c) => '.' + c).join(''));
    const found = [];
    for (const row of document.querySelectorAll('*')) {
        const st = getComputedStyle(row);
        if (!/flex/.test(st.display) || !/^row/.test(st.flexDirection)) continue;
        // The inside of ONE field — its bordered frame holding the text
        // and its own small buttons (a date picker's clear and calendar):
        // not controls side by side.
        if (parseFloat(st.borderTopWidth) > 0
            && row.querySelector('input:not([type=hidden]), textarea')) continue;
        const items = [];
        for (const child of row.children) {
            if (!shown(child)) continue;
            // Out of the flow (a field's clear button, laid over it): not
            // on the line.
            if (/absolute|fixed/.test(getComputedStyle(child).position)) continue;
            const control = controlOf(child);
            if (!control) continue;
            const h = frameOf(control, row).offsetHeight;
            if (h > 64) continue;          // a textarea, a card, a list: not a line
            items.push({control: name(control), height: Math.round(h * 10) / 10});
        }
        if (items.length < 2) continue;
        const hs = items.map((i) => i.height);
        // Three or more controls, every one a different height: a size
        // ladder shown on purpose (a catalogue's xs → xl), not a slip.
        const ladder = hs.length >= 3
            && new Set(hs.map((h) => Math.round(h))).size === hs.length;
        if (!ladder && Math.max(...hs) - Math.min(...hs) > 1) {
            found.push({row: name(row), controls: items});
        }
    }
    return found.slice(0, 6);
}
"""


#: C8 — the header's text and the page's column start at the same x.
#:
#: A header and a page both clamped and centred are meant to be ONE
#: column; two widths or two margins break that with no error and every
#: other check green — and the eye sees it at once.
#:
#: Judged only when it means something:
#: - the header is the PAGE's banner (``<header>`` or ``role=banner``,
#:   spanning the window), and something in it is clamped (``max-width``);
#: - the page column is the first clamped, centred block below it
#:   (``margin-left`` = ``margin-right``, at least half the window wide);
#: - both are centred on the SAME axis. A page beside a sidebar is centred
#:   elsewhere, and nobody expects it to line up with the bar above.
#:
#: The header's edge is that of its leftmost CONTENT (text, icon, image):
#: what the eye lines up, not a box. The page's is its column's content
#: box (border and padding inside).
_ALIGNED_JS = r"""
() => {
    const vw = document.documentElement.clientWidth;
    const shown = (e) => {
        const r = e.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        const st = getComputedStyle(e);
        return st.visibility !== 'hidden' && st.display !== 'none';
    };
    const clamped = (e) => getComputedStyle(e).maxWidth !== 'none';
    const name = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id
        : (e.getAttribute('class') || '').split(/\s+/).filter(Boolean)
            .slice(0, 3).map((c) => '.' + c).join(''));
    const header = [...document.querySelectorAll('header, [role=banner]')]
        .find((h) => shown(h) && h.getBoundingClientRect().width >= vw * 0.9);
    if (!header) return null;
    const hr = header.getBoundingClientRect();
    const bar = [header, ...header.querySelectorAll('*')].find((e) =>
        clamped(e) && shown(e) && e.getBoundingClientRect().width >= hr.width * 0.5);
    if (!bar) return null;
    // The leftmost thing drawn in the header: a text run, an icon, an image.
    let left = Infinity, what = '';
    const walker = document.createTreeWalker(header, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!n.textContent.trim() || !shown(n.parentElement)) continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        for (const r of range.getClientRects()) {
            if (r.width > 0 && r.left < left) {
                left = r.left; what = n.textContent.trim().slice(0, 30);
            }
        }
    }
    for (const e of header.querySelectorAll('svg, img, iconify-icon, canvas, picture')) {
        if (!shown(e)) continue;
        const r = e.getBoundingClientRect();
        if (r.left < left) { left = r.left; what = name(e); }
    }
    if (left === Infinity) return null;
    const column = [...document.body.querySelectorAll('*')].find((e) => {
        if (header.contains(e) || e.contains(header) || !clamped(e) || !shown(e)) return false;
        const r = e.getBoundingClientRect();
        if (r.top < hr.bottom - 1 || r.width < vw * 0.5) return false;
        const st = getComputedStyle(e);
        return Math.abs(parseFloat(st.marginLeft) - parseFloat(st.marginRight)) <= 1;
    });
    if (!column) return null;
    const br = bar.getBoundingClientRect();
    const cr = column.getBoundingClientRect();
    if (Math.abs((br.left + br.right) / 2 - (cr.left + cr.right) / 2) > 2) return null;
    const st = getComputedStyle(column);
    const edge = cr.left + column.clientLeft + parseFloat(st.paddingLeft);
    return {
        header: Math.round(left * 10) / 10, first: what,
        page: Math.round(edge * 10) / 10, column: name(column),
    };
}
"""


def sweep(
    windows: Sequence[Window],
    size: tuple[int, int],
    check: Check,
) -> None:
    """Measure every window, at two sizes and in both themes.

    The window is already at its first size, so it is not resized before
    the first measure, and the two theme toggles are not waited for: they
    mutate no DOM, and a screenshot synchronises itself on the render.
    """
    for window in windows:
        # Once only, to absorb what the scenario left in flight. The
        # waits that follow FOLLOW NO GESTURE, so they have no floor to
        # pay.
        window.settle(timeout=2.0)
        _errors_and_requests(check, window)
        # What visible= hid at each load, and the zones redrawn hidden.
        judge_loads(check, window.name, window.loads)
        judge_redraws(check, window.name, window.redrawn)
        _tab_order(check, window)
        _names(check, window)

        for measure in _AT_EACH_SIZE:
            measure(check, window, f"size-1 {size[0]}×{size[1]}")
        window.resize(SECOND_SIZE)
        window.settle(timeout=2.0, floor=0)
        for measure in _AT_EACH_SIZE:
            measure(check, window, f"size-2 {SECOND_SIZE[0]}×{SECOND_SIZE[1]}")
        window.resize(size)

        # C4 — light first: it is the one an author who codes in dark
        # never looks at.
        for theme in ("light", "dark"):
            window.page.emulate_media(color_scheme=theme)
            window.shot(theme)


def _errors_and_requests(check: Check, window: Window) -> None:
    check(
        f"[{window.name}] aucune erreur JS",
        not window.errors,
        window.errors[:3],
    )
    check(
        f"[{window.name}] no failed request",
        not window.broken,
        window.broken[:3],
    )
    check(
        f"[{window.name}] aucun avertissement de console",
        not window.console,
        window.console[:3],
    )


def _geometry(check: Check, window: Window, label: str) -> None:
    geo: dict[str, Any] = window.page.evaluate(_GEOMETRY_JS)
    check(
        f"[{window.name}] {label} — the page does not overflow sideways",
        geo["overflowX"] == 0,
        f"{geo['overflowX']} px too many",
    )
    if not geo["documentScrolls"]:
        # FROZEN document: every scrolling region must end ABOVE the
        # edge. A region overflowing at the bottom has nothing to catch it.
        # One that a scrolling ancestor brings into view is caught, and
        # left out (``_GEOMETRY_JS``).
        below = [s for s in geo["scrollers"] if s["bottom"] > geo["viewport"][1] + 1]
        check(
            f"[{window.name}] {label} — the regions end above the edge",
            not below,
            below[:3],
        )
    # C5 — what is CLIPPED, with no bar to catch it.
    #
    # ⚠️ **Overflow and clipping are not the same fault.** The two
    # findings above measure what goes OUT — of a page, of a region. This
    # one measures what stays IN and is not painted: a box with an
    # imposed height on which a theme sets ``overflow:hidden`` keeps its
    # content in the DOM and shows only part of it. No error, no failed
    # request, complete and correct HTML — it is a screen's most
    # expensive failure mode, because one cannot know one is looking at
    # missing information.
    #
    # An author's count of what fits is unreliable: the height is written
    # in the app and the padding in a component theme, and their sum lives
    # nowhere.
    #
    # The cost is nil: this reuses the loop above.
    check(
        f"[{window.name}] {label} — nothing is clipped without recourse",
        not geo["clipped"],
        geo["clipped"][:3],
    )


def _names(check: Check, window: Window) -> None:
    """Every control a person operates has a name to be announced by."""
    unnamed: list[dict[str, Any]] = window.page.evaluate(_NAMES_JS)
    check(
        f"[{window.name}] every control has a name",
        not unnamed,
        unnamed[:3],
    )


def _rows(check: Check, window: Window, label: str) -> None:
    """C7 — the controls of one row share one height."""
    uneven: list[dict[str, Any]] = window.page.evaluate(_ROWS_JS)
    check(
        f"[{window.name}] {label} — the controls of a row share one height",
        not uneven,
        uneven[:3],
    )


def _aligned(check: Check, window: Window, label: str) -> None:
    """C8 — a clamped header and the page under it share their left edge.

    Not judged when there is no such pair (``_ALIGNED_JS`` returns
    ``None``): an app with no header, or a page beside a sidebar, has
    nothing to line up, and a green line there would measure nothing.
    """
    found: dict[str, Any] | None = window.page.evaluate(_ALIGNED_JS)
    if found is None:
        return
    check(
        f"[{window.name}] {label} — the header lines up with the page",
        abs(found["header"] - found["page"]) <= 1,
        f"header text at {found['header']} px ({found['first']!r}), page "
        f"column at {found['page']} px ({found['column']}) — "
        f"ui.navbar(width=…) with the word of the page's ui.container",
    )


def _stuck(check: Check, window: Window, label: str) -> None:
    """C6 — a stuck element lets nothing show between it and its edge."""
    stuck: list[dict[str, Any]] = window.page.evaluate(_STICKY_JS)
    check(
        f"[{window.name}] {label} — nothing scrolls into view past a stuck element",
        not stuck,
        stuck[:3],
    )


#: Plants the walk's starting point at the head of ``<body>``.
_TAB_START_JS = """() => {
  const start = document.createElement('span');
  start.id = 'bz-probe-tab-start';
  start.tabIndex = -1;
  document.body.prepend(start);
  start.focus();
}"""


#: What is measured again at each window size.
_AT_EACH_SIZE: tuple[Callable[[Check, Window, str], None], ...] = (
    _geometry, _stuck, _rows, _aligned,
)


def _tab_order(check: Check, window: Window) -> None:
    """Where tabbing lands — and where it has no business being.

    Off-screen is not enough. A closed ``ui.dialog`` is CENTRED: its
    fields sit right in the middle of the viewport, so a control
    reachable inside a closed dialog would pass this sweep green.

    The marker targeted (``data-bz-overlay``) is that of MODAL overlays —
    ``dialog`` and ``drawer``. The anchored ones (``popover``,
    ``dropdown``) close with ``display:none``, so nothing can take focus
    there and there is nothing to measure; the day one of them moved to
    ``visibility`` to animate its exit, it is the component gate
    (``test_a_closed_overlay_is_out_of_the_tab_order``) that would say
    so, not this sweep.
    """
    reached = False
    offscreen: list[dict[str, Any]] = []
    in_closed: list[dict[str, Any]] = []
    rings: list[dict[str, Any]] = []
    vw, vh = window.page.evaluate(
        "() => [document.documentElement.clientWidth, "
        "document.documentElement.clientHeight]"
    )
    # The walk starts at the TOP of the document, not where the scenario
    # left the focus: ended on the page's last control, the first Tab
    # would leave the document and "tabbing reaches something" would go
    # red on a sound page. ``blur()`` is not enough:
    # Chrome keeps its starting point where the click landed. Focusing a
    # marker at the head of ``<body>`` moves it; ``tabindex=-1`` keeps the
    # marker itself out of the walk.
    window.page.evaluate(_TAB_START_JS)
    for _ in range(20):
        window.press("Tab")
        focused = window.page.evaluate(_TAB_JS)
        if focused is None:
            break
        reached = True
        if focused["closed"]:
            in_closed.append(focused)
        if focused["ring"]:
            rings.append(focused["ring"])
        if focused["w"] == 0 and focused["h"] == 0:
            continue  # a deliberately invisible control, not a fault
        if (
            focused["x"] + focused["w"] < 0
            or focused["y"] + focused["h"] < 0
            or focused["x"] > vw
            or focused["y"] > vh
        ):
            offscreen.append(focused)
    window.page.evaluate(
        "() => document.getElementById('bz-probe-tab-start')?.remove()"
    )
    check(
        f"[{window.name}] tabbing reaches something",
        reached,
        "no focusable element",
    )
    check(
        f"[{window.name}] tabbing does not leave the screen",
        not offscreen,
        offscreen[:3],
    )
    check(
        f"[{window.name}] tabbing does not enter a closed overlay",
        not in_closed,
        in_closed[:3],
    )
    # The focus ring, CUT by an ancestor that clips: a field flush
    # against the edge of a pane. Measured on each Tab (``_TAB_JS``),
    # because a ring exists only while its element has focus.
    check(
        f"[{window.name}] no focus ring is clipped",
        not rings,
        rings[:3],
    )

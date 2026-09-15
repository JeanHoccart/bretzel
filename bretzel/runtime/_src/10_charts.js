/* 10_charts.js — shared chart tooltip + legend scope factories. */
// ════════════════════════════════════════════════════════════════════════
// 10 CHARTS — shared tooltip for bar / line / pie / sparkline.
//
// Why a runtime slab at all
// ─────────────────────────
// The charts are server-rendered SVG ; the framework already paints the
// silhouette on first paint with zero JS. What we DON'T render server-
// side is the floating tooltip — its position depends on the cursor
// (mouse) or the trigger rect (keyboard focus), neither of which Python
// can know. So this slab :
//
// 1. Lazily mounts a single ``<div class="bz-chart-tooltip">`` on
//    ``<body>`` the first time a chart needs it (zero cost on a page
//    with no charts at all).
// 2. Exposes ``$bz.charts.tooltipScope()`` — a bz-data scope factory
//    every chart wrapper drops on its root. Bars / segments / points
//    handle ``bz-on:mouseenter="show($event)"`` / ``bz-on:mouseleave="hide()"``.
//    The factory reads ``data-bz-display`` off ``event.currentTarget``,
//    formats it server-side (so there's nothing for the JS to know about
//    locale / units), and positions the panel above the trigger.
//
// V3 : ``toggleSeries`` REASSIGNS the ``visible`` array (V3 signals are
// identity-compared — an in-place ``visible[i] = …`` wouldn't re-render
// the ``bz-show``'d paths/dots/legend slots).
//
// Public DOM API
// ──────────────
//   $bz.charts.tooltipScope() → bz-data scope object (bar / pie / sparkline)
//   $bz.charts.lineScope()    → bz-data scope tracking ``active`` for the
//                               line-chart hover state + per-series
//                               ``visible`` toggles.
//   $bz.charts.scatterScope() → bz-data scope (per-dot tooltip + legend)
//   $bz.charts.hide()         → force-hide (e.g. on htmx swap)
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    var $bz = window.$bz;
    if (!$bz) return;

    var tip = null;
    var hideTimer = null;
    // Closure that recomputes the visible tooltip's viewport rect from
    // live geometry (returns null when it can't). Each show path installs
    // one capturing whatever it needs — a bar's ``.bz-bar-fill``, a
    // scatter dot, a pie centroid, a line column + fraction. Scroll /
    // resize replay it so a ``fixed`` panel positioned once stays glued
    // to its data point instead of drifting as the page scrolls.
    var activeReposition = null;

    // Tailwind classes carry the Bretzel theme tokens (``bg-text`` /
    // ``text-background`` resolve to the semantic palette set by the
    // user's ``Theme(...)``). The framework already ships these
    // classes (line_chart's tooltip slot uses the same recipe) so
    // they're guaranteed to be in the compiled CSS.
    var TOOLTIP_CLASSES = (
        'bz-chart-tooltip fixed z-50 pointer-events-none ' +
        'px-2.5 py-1.5 rounded-box bg-text/95 text-background ' +
        'text-xs font-medium leading-relaxed whitespace-pre-line ' +
        'shadow-md opacity-0 transition-opacity duration-150'
    );

    function ensureTooltip() {
        if (tip) return tip;
        tip = document.createElement('div');
        tip.className = TOOLTIP_CLASSES;
        tip.setAttribute('role', 'tooltip');
        document.body.appendChild(tip);
        return tip;
    }

    // Set the panel's left/top for a viewport-space ``rect`` — top-
    // anchored, flips below when the trigger hugs the top edge. Reads
    // the panel's own size first (textContent is already set).
    function placeAt(rect) {
        var t = ensureTooltip();
        var tw = t.offsetWidth;
        var th = t.offsetHeight;
        var cx = rect.left + rect.width / 2;
        var aboveY = rect.top - th - 8;
        var flipped = aboveY < 4;
        var y = flipped ? (rect.bottom + 8) : aboveY;
        var x = Math.max(4, Math.min(window.innerWidth - tw - 4, cx - tw / 2));
        t.style.left = x + 'px';
        t.style.top = y + 'px';
    }

    function position(rect) {
        var t = ensureTooltip();
        t.style.left = '0px';
        t.style.top = '0px';
        placeAt(rect);
        t.style.opacity = '1';
    }

    // Viewport rect for an anchor element — a pie wedge's ``data-bz-ax/ay``
    // centroid (SVG-space → screen via the CTM) when present, else the
    // ``rect`` / ``circle`` bounding box. ``null`` when the element can't
    // be resolved (e.g. a path with no centroid attrs) so callers fall
    // back to the cursor.
    function rectForAnchor(anchor) {
        if (!anchor) return null;
        var ax = anchor.getAttribute('data-bz-ax');
        var ay = anchor.getAttribute('data-bz-ay');
        var svg = anchor.ownerSVGElement;
        var ctm = svg && svg.getScreenCTM && svg.getScreenCTM();
        if (ax !== null && ay !== null && ctm) {
            var pt = svg.createSVGPoint();
            pt.x = parseFloat(ax);
            pt.y = parseFloat(ay);
            var screen = pt.matrixTransform(ctm);
            return {
                left: screen.x, right: screen.x,
                top: screen.y, bottom: screen.y,
                width: 0, height: 0,
            };
        }
        var tag = anchor.tagName && anchor.tagName.toLowerCase();
        if (tag === 'rect' || tag === 'circle') {
            return anchor.getBoundingClientRect();
        }
        return null;
    }

    // Keep the visible panel glued to its anchor across scroll / resize —
    // recompute geometry and move (no opacity toggle, so no re-fade).
    function reposition() {
        if (!tip || tip.style.opacity !== '1' || !activeReposition) return;
        var rect = activeReposition();
        if (rect) placeAt(rect);
    }
    // Capture phase so scrolls inside any nested scroll container (not
    // just the window) reach us — scroll events don't bubble.
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);

    function hideTooltip() {
        activeReposition = null;
        if (!tip) return;
        // Tiny grace period so a fast cursor leaving one bar and entering
        // the next doesn't flash the tooltip in/out — the next ``show``
        // cancels the pending hide.
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            if (tip) tip.style.opacity = '0';
        }, 60);
    }

    // The ``show`` handshake every hover path repeats : resolve the
    // hovered element, read its pre-formatted label, cancel a pending
    // hide, make sure the tooltip node exists, and write the text ONLY
    // when it changed (writing the same string would invalidate layout
    // before ``offsetWidth`` is read, for nothing).
    //
    // Returns the hovered element when a label is on screen, or null
    // when there was nothing to show — each caller then does its own
    // anchoring, which is where they genuinely differ (bar-fill lookup,
    // dot rect, line-column band). Three copies before (audit F59).
    function showLabel(event) {
        var el = event && event.currentTarget;
        if (!el) return null;
        var label = el.getAttribute('data-bz-display');
        if (!label) return null;
        clearTimeout(hideTimer);
        var t = ensureTooltip();
        if (t.textContent !== label) t.textContent = label;
        return el;
    }

    function tooltipScope() {
        return {
            show: function (event) {
                var el = showLabel(event);
                if (!el) return;
                // Bar charts widen the hit target to the whole column via
                // a transparent ``.bz-bar-hit`` overlay that spans the
                // plot. Anchoring on the overlay itself would float the
                // tooltip at the top of the column ; anchor on the sibling
                // ``.bz-bar-fill`` instead so it lands on the data point.
                var anchor = el;
                if (el.classList && el.classList.contains('bz-bar-hit')) {
                    var fill = el.parentNode &&
                        el.parentNode.querySelector('.bz-bar-fill');
                    if (fill) anchor = fill;
                }
                // Anchor on the data point : a bar's ``.bz-bar-fill``, a
                // scatter/line dot, or a pie wedge's ``data-bz-ax/ay``
                // centroid (a ``<path>`` bbox would float the panel at the
                // pie's centre). ``rectForAnchor`` resolves all three ;
                // stash the element so scroll / resize can re-anchor.
                var rect = rectForAnchor(anchor);
                if (rect) {
                    activeReposition = function () {
                        return rectForAnchor(anchor);
                    };
                    position(rect);
                } else {
                    // Last-resort fallback (path with no centroid attrs) —
                    // pin to the cursor ; nothing to re-anchor on scroll.
                    activeReposition = null;
                    position({
                        left: event.clientX, right: event.clientX,
                        top: event.clientY, bottom: event.clientY,
                        width: 0, height: 0,
                    });
                }
            },
            hide: function () { hideTooltip(); },
        };
    }

    // Force-hide on htmx swap so a refresh that replaces the chart
    // doesn't leave the tooltip pointing at thin air.
    document.addEventListener('htmx:before-swap', function () {
        activeReposition = null;
        if (tip) tip.style.opacity = '0';
    });

    function parseJSON(attr, fallback) {
        if (!attr) return fallback;
        try { return JSON.parse(attr); } catch (e) { return fallback; }
    }

    // Legend visibility, shared by every multi-series chart scope.
    // ``visible[i]`` drives ``bz-show`` on the path / dots / markers the
    // server rendered with series index ``i``.
    //
    // Two load-bearing details lived in two copies (audit F18) : the
    // "never toggle the last one off" guard (an all-hidden chart reads
    // as broken — Vercel and Stripe ship the same rule), and the
    // REASSIGN in toggleSeries (V3 signals are identity-compared, so an
    // in-place ``visible[i] = …`` would not re-render).
    function seriesVisibility(nSeries) {
        var visible = [];
        for (var i = 0; i < nSeries; i++) visible.push(true);
        return {
            visible: visible,
            isVisible: function (i) { return !!this.visible[i]; },
            toggleSeries: function (i) {
                if (i < 0 || i >= this.visible.length) return;
                var on = this.visible.filter(Boolean).length;
                if (this.visible[i] && on <= 1) return;
                this.visible = this.visible.map(function (v, j) {
                    return j === i ? !v : v;
                });
            },
        };
    }

    function lineScope(opts) {
        var nSeries = (opts && opts.n_series) || 1;
        var vis = seriesVisibility(nSeries);
        return {
            active: -1,
            visible: vis.visible,
            isVisible: vis.isVisible,
            // Full-column hover (single + multi). Sets the ``active``
            // index (drives the crosshair + per-series active dots via
            // bz-attr) AND positions the shared floating tooltip above
            // the active column. The hit rect (``event.currentTarget``)
            // spans the plot vertically, so its screen bbox gives us
            // both the column's screen-x band and the plot top —
            // scale-robust, no SVG CTM. ``data-bz-anchor-x`` is the
            // data-x's fraction within the rect, mapped onto that band.
            onHover: function (event, idx) {
                this.active = idx;
                var el = showLabel(event);
                // Nothing to show (no target, or a column with no
                // label) → hide. The pre-shared version returned early
                // without hiding in the no-target case ; a dispatched
                // mouseenter always has a currentTarget, and hideTooltip
                // no-ops when no tooltip node exists yet.
                if (!el) { hideTooltip(); return; }
                // Zero-size anchor at (column-x, plot-top) → the tooltip
                // floats above the plot, never over the curve. ``bottom
                // = r.top`` so the near-top flip lands just inside the
                // plot instead of at the far plot bottom. Recomputed from
                // the live hit rect so scroll / resize keep it glued.
                var lineRect = function () {
                    var r = el.getBoundingClientRect();
                    var frac = parseFloat(el.getAttribute('data-bz-anchor-x'));
                    if (isNaN(frac)) frac = 0.5;
                    var ax = r.left + frac * r.width;
                    return {
                        left: ax, right: ax, top: r.top, bottom: r.top,
                        width: 0, height: 0,
                    };
                };
                activeReposition = lineRect;
                position(lineRect());
            },
            onLeave: function () { this.active = -1; hideTooltip(); },
            // The shared toggle, plus line's own extra : drop the hover
            // index when the series it points at goes hidden. Wrapped
            // rather than re-copied, so the guard and the reassign stay
            // in one place.
            toggleSeries: function (i) {
                vis.toggleSeries.call(this, i);
                if (!this.visible[i]) this.active = -1;
            },
        };
    }

    function scatterScope(opts) {
        var vis = seriesVisibility((opts && opts.n_series) || 1);
        return {
            visible: vis.visible,
            isVisible: vis.isVisible,
            toggleSeries: vis.toggleSeries,
            // Floating tooltip on per-dot hover. Each ``<circle>``
            // dot carries ``data-bz-display`` ; the circle's
            // ``getBoundingClientRect()`` is tight (``r × 2`` box)
            // so anchoring above it lands cleanly on the dot.
            show: function (event) {
                var el = showLabel(event);
                if (!el) return;
                activeReposition = function () {
                    return el.getBoundingClientRect();
                };
                position(el.getBoundingClientRect());
            },
            hide: function () { hideTooltip(); },
        };
    }

    $bz.charts = {
        tooltipScope: tooltipScope,
        lineScope: lineScope,
        scatterScope: scatterScope,
        hide: hideTooltip,
    };
})();

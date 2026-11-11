/* charts.js — shared chart tooltip + legend scope factories. */
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
// 1. Shows the PAGE's one tooltip panel (``tip.js``, ``#bz-tip``) on
//    the hovered data point. A panel of its own, with the tooltip's look
//    copied as classes, would ignore the app's
//    ``Theme(components={"tooltip": …})``.
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
//   $bz.charts.barScope()     → bz-data scope (per-bar tooltip + legend,
//                               grouped bars only — a stack with a hole lies)
//
// Every scope also carries ``key`` / ``unkey``: the chart is ONE tab
// stop, the arrows walk its points, Enter clicks one, Escape leaves.
//   $bz.charts.hide()         → force-hide (e.g. on htmx swap)
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    var $bz = window.$bz;
    if (!$bz) return;

    var hideTimer = null;
    // Whether the shared panel is showing a CHART's label — the swap
    // guard and the hide must not close a tooltip someone else opened.
    var owns = false;
    var ZERO = { left: 0, right: 0, top: 0, bottom: 0, width: 0, height: 0 };

    // Open the page's panel on a data point. ``rectFn`` is re-read by
    // ``floating`` on every scroll / resize, so the panel stays glued to
    // its point — the job an ``activeReposition`` closure did here by
    // hand. Above the point, flipped below when it hugs the top edge:
    // ``floating``'s ``top`` placement. ``whitespace-pre-line``: a label
    // is pre-formatted server-side, on several lines.
    function openAt(rectFn, label) {
        clearTimeout(hideTimer);
        if (!$bz.tip) return;
        owns = true;
        $bz.tip.open(
            { getBoundingClientRect: function () { return rectFn() || ZERO; } },
            { text: label, position: 'top', extraClass: 'whitespace-pre-line' }
        );
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

    function hideTooltip() {
        if (!owns) return;
        // Tiny grace period so a fast cursor leaving one bar and entering
        // the next doesn't flash the tooltip in/out — the next ``show``
        // cancels the pending hide.
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            owns = false;
            if ($bz.tip) $bz.tip.close();
        }, 60);
    }

    // The hovered element and its pre-formatted label, or null when there
    // is nothing to show — each caller then anchors where it genuinely
    // differs (bar-fill lookup, dot rect, line-column band).
    function labelled(event) {
        var el = event && event.currentTarget;
        if (!el) return null;
        var label = el.getAttribute('data-bz-display');
        return label ? { el: el, label: label } : null;
    }

    function tooltipScope() {
        return scope({
            show: function (event) {
                var hit = labelled(event);
                if (!hit) return;
                // Bar charts widen the hit target to the whole column via
                // a transparent ``.bz-bar-hit`` overlay that spans the
                // plot. Anchoring on the overlay itself would float the
                // tooltip at the top of the column ; anchor on the sibling
                // ``.bz-bar-fill`` instead so it lands on the data point.
                var anchor = hit.el;
                if (anchor.classList && anchor.classList.contains('bz-bar-hit')) {
                    var fill = anchor.parentNode &&
                        anchor.parentNode.querySelector('.bz-bar-fill');
                    if (fill) anchor = fill;
                }
                // Anchor on the data point : a bar's ``.bz-bar-fill``, a
                // scatter/line dot, or a pie wedge's ``data-bz-ax/ay``
                // centroid (a ``<path>`` bbox would float the panel at the
                // pie's centre). ``rectForAnchor`` resolves all three.
                if (rectForAnchor(anchor)) {
                    openAt(function () { return rectForAnchor(anchor); }, hit.label);
                } else {
                    // Last-resort fallback (path with no centroid attrs) —
                    // pin to the cursor.
                    var cursor = {
                        left: event.clientX, right: event.clientX,
                        top: event.clientY, bottom: event.clientY,
                        width: 0, height: 0,
                    };
                    openAt(function () { return cursor; }, hit.label);
                }
            },
            hide: function () { hideTooltip(); },
        });
    }

    // Force-hide on htmx swap so a refresh that replaces the chart
    // doesn't leave the tooltip pointing at thin air.
    document.addEventListener('htmx:before-swap', function () {
        if (!owns) return;
        owns = false;
        clearTimeout(hideTimer);
        if ($bz.tip) $bz.tip.close();
    });

    // The keyboard, shared by every chart scope. The chart is ONE tab stop
    // (21 bars are not 21 tabs, as Highcharts' module does it); the arrows
    // walk the points that carry a tooltip — those of a hidden series have
    // no box and are skipped — and each step REPLAYS the hover, so the
    // tooltip, the line's crosshair and the bar's spotlight follow with no
    // second code path. Enter replays the click (``on_item_click``),
    // Escape and leaving the chart close.
    function keyboard() {
        return {
            kbd: -1,
            key: function (event) {
                // A legend button inside the chart keeps its own keys.
                if (event.target !== event.currentTarget) return;
                var points = Array.prototype.filter.call(
                    event.currentTarget.querySelectorAll('[data-bz-display]'),
                    function (el) { return el.getClientRects().length > 0; });
                if (!points.length) return;
                var k = event.key, at = this.kbd;
                if (k === 'ArrowRight' || k === 'ArrowDown') at = Math.min(at + 1, points.length - 1);
                else if (k === 'ArrowLeft' || k === 'ArrowUp') at = Math.max(at - 1, 0);
                else if (k === 'Home') at = 0;
                else if (k === 'End') at = points.length - 1;
                else if (k === 'Enter' || k === ' ') {
                    if (points[at]) points[at].dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    if (k === ' ') event.preventDefault();
                    return;
                } else if (k === 'Escape') { this.unkey(event); return; }
                else return;
                event.preventDefault();
                if (points[this.kbd]) points[this.kbd].dispatchEvent(new MouseEvent('mouseleave'));
                this.kbd = at;
                points[at].dispatchEvent(new MouseEvent('mouseenter'));
            },
            unkey: function (event) {
                var root = event && event.currentTarget;
                var points = root ? root.querySelectorAll('[data-bz-display]') : [];
                Array.prototype.forEach.call(points, function (el) {
                    el.dispatchEvent(new MouseEvent('mouseleave'));
                });
                this.kbd = -1;
                hideTooltip();
            },
        };
    }

    // One scope object out of the pieces: the keyboard is in every one.
    function scope() {
        var out = keyboard();
        for (var i = 0; i < arguments.length; i++) {
            var part = arguments[i];
            for (var name in part) {
                if (Object.prototype.hasOwnProperty.call(part, name)) out[name] = part[name];
            }
        }
        return out;
    }

    function parseJSON(attr, fallback) {
        if (!attr) return fallback;
        try { return JSON.parse(attr); } catch (e) { return fallback; }
    }

    // Legend visibility, shared by every multi-series chart scope.
    // ``visible[i]`` drives ``bz-show`` on the path / dots / markers the
    // server rendered with series index ``i``.
    //
    // Two load-bearing details live here : the "never toggle the last
    // one off" guard (an all-hidden chart reads as broken — Vercel and
    // Stripe ship the same rule), and the REASSIGN in toggleSeries (V3
    // signals are identity-compared, so an in-place ``visible[i] = …``
    // would not re-render).
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
        return scope({
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
                var hit = labelled(event);
                // Nothing to show (no target, or a column with no
                // label) → hide.
                if (!hit) { hideTooltip(); return; }
                var el = hit.el;
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
                openAt(lineRect, hit.label);
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
        });
    }

    function scatterScope(opts) {
        var vis = seriesVisibility((opts && opts.n_series) || 1);
        return scope({
            visible: vis.visible,
            isVisible: vis.isVisible,
            toggleSeries: vis.toggleSeries,
            // Floating tooltip on per-dot hover. Each ``<circle>``
            // dot carries ``data-bz-display`` ; the circle's
            // ``getBoundingClientRect()`` is tight (``r × 2`` box)
            // so anchoring above it lands cleanly on the dot.
            show: function (event) {
                var hit = labelled(event);
                if (!hit) return;
                openAt(function () { return hit.el.getBoundingClientRect(); }, hit.label);
            },
            hide: function () { hideTooltip(); },
        });
    }

    // Grouped bars with a clickable legend: the bar tooltip, plus the
    // series' visibility (a hidden series leaves its slot empty in each
    // group — the others keep their place and their height).
    function barScope(opts) {
        var vis = seriesVisibility((opts && opts.n_series) || 1);
        var bars = tooltipScope();
        return scope(bars, {
            visible: vis.visible,
            isVisible: vis.isVisible,
            toggleSeries: vis.toggleSeries,
        });
    }

    $bz.charts = {
        tooltipScope: tooltipScope,
        lineScope: lineScope,
        scatterScope: scatterScope,
        barScope: barScope,
        hide: hideTooltip,
    };
})();

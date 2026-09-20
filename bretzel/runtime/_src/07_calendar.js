/* 07_calendar.js — <bz-calendar> custom element (stateful day grid). */
// ════════════════════════════════════════════════════════════════════════
// 07 CALENDAR — <bz-calendar> custom element.
//
// A stateful widget as a custom element : the day-grid logic (month
// math, range preview, keyboard grid nav) is genuinely complex and a
// custom element with its own state + attribute observers is the right
// tool — framework-agnostic, survives idiomorph for free (the element
// node persists by id, only observed attributes morph).
//
// The custom element owns its internal state ; configuration lives in
// observed HTML attributes that idiomorph can morph freely. Each
// attribute change triggers ``attributeChangedCallback`` which schedules
// a re-render. Form participation rides a child ``<input type="hidden">``
// onto which the V3 server-action attrs (hx-post / bz-on:change) are
// relocated by Python — the element fires a synthetic ``change`` on it
// whenever the value mutates.
//
// Public DOM API (callable from imperative handlers) :
//   .set(value), .clear(), .focus(), .blur(),
//   .prevMonth(), .nextMonth()
//
// Custom events dispatched :
//   change       — { value: string | [start, end] }
//   month-change — { year: int, month: 1..12 }
//
// Theme classes arrive via a JSON blob in the ``data-bz-theme`` attr ;
// Python's ``Calendar.render()`` composes the slot strings once and
// hands them over.
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    if (typeof customElements === 'undefined') return;
    if (customElements.get('bz-calendar')) return;

    // Derived from ``<html lang>`` by 22_locale.js, not written here: a
    // hard-coded table rendered "August / MON TUE WED" to every app,
    // whatever its language, and the only handle was to pass
    // ``month_names=`` AT EVERY MOUNT (three times on a single CRM
    // screen). The component's explicit lists always win — they arrive
    // as attributes and these defaults only serve their absence.
    function DEFAULT_WEEKDAYS() { return window.$bz.locale.weekdayNames(); }
    function DEFAULT_WEEKDAYS_LONG() {
        return window.$bz.locale.weekdayLongNames();
    }
    function DEFAULT_MONTHS() { return window.$bz.locale.monthNames(); }

    function iso(d) {
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    /* The ISO day shifted by ``n`` days. Goes through a ``Date`` rather
     * than through string arithmetic: only it knows about month ends and
     * leap years. */
    function addDays(isoStr, n) {
        var p = isoStr.split('-');
        return iso(new Date(+p[0], +p[1] - 1, +p[2] + n));
    }

    /* The first day of the week that CONTAINS ``isoStr``, according to
     * ``weekstart`` (0 = Sunday, 1 = Monday…).
     *
     * It is the ``week`` mode's only rule: clicking any day picks its
     * week, and the returned value is that first day. The modulo is
     * doubled (``% 7 + 7) % 7``) because JS returns a NEGATIVE remainder
     * for a negative dividend — without it, any week whose clicked day
     * falls before ``weekstart`` would go back one week.
     */
    function weekStartOf(isoStr, weekstart) {
        var p = isoStr.split('-');
        var d = new Date(+p[0], +p[1] - 1, +p[2]);
        var back = (d.getDay() - weekstart + 7) % 7;
        return iso(new Date(+p[0], +p[1] - 1, +p[2] - back));
    }

    function parseJSON(value, fallback) {
        if (!value) return fallback;
        try { return JSON.parse(value); } catch (e) { return fallback; }
    }

    function escapeAttr(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    class BzCalendar extends HTMLElement {
        static get observedAttributes() {
            return [
                'mode', 'value', 'month', 'weekstart',
                'min', 'max', 'disabled',
                'disabled-dates', 'marks', 'weekday-names', 'month-names',
                'data-bz-theme',
                // ``data-bz-value-path`` / ``data-bz-month-path`` carry the
                // ``$bz.state.X.y`` dotted path the framework wants the
                // custom element to write into when the user picks a
                // value or navigates a month. Without these the binding
                // is one-way only (state → attribute) and the Client
                // playground / Client events cards stay silent.
                'data-bz-value-path',
                'data-bz-month-path',
            ];
        }

        constructor() {
            super();
            this._displayedYear = null;
            this._displayedMonth = null;
            this._hoverDate = null;
            // The start of a range BEING selected, ``range`` mode only.
            // It lives here and NOT in the ``value`` attribute — that is
            // the whole point.
            //
            // A range's first click emits no ``change`` (there is no
            // value to announce yet), so the picker's scope cannot
            // represent that state: it has only ``vstart`` / ``vend``,
            // both empty. Yet the wrapper's mirror ``bz-effect`` treats
            // that scope as the source of truth and pushes ``''`` into
            // the attribute as soon as it runs again — which happens at
            // EVERY HTMX swap, the bridge rescanning the target. As long
            // as the pending start lived in the attribute, that mirror
            // erased it and the second click reopened a range instead of
            // closing it: the field stayed empty and the user clicked
            // endlessly.
            //
            // Here the mirror has nothing left to overwrite — it
            // rewrites ``''`` over ``''``, so no
            // ``attributeChangedCallback``, so the pending state
            // survives. The attribute now carries only what is
            // COMMITTED; it is the sync surface with the outside, not a
            // buffer of transient state. ``_hoverDate`` already had
            // exactly that status, hence the neighbourhood.
            this._pendingStart = null;
            this._initialized = false;
            this._renderScheduled = false;
        }

        connectedCallback() {
            if (this._initialized) return;
            this._initialized = true;

            // Seed the displayed month from the ``month`` attribute or
            // today. We never re-read this from the attribute after
            // init — prev/next clicks mutate it internally and write
            // back to the attribute so external observers see the
            // current displayed month.
            var monthAttr = this.getAttribute('month');
            if (monthAttr) {
                var parts = monthAttr.split('-');
                this._displayedYear = parseInt(parts[0], 10);
                this._displayedMonth = parseInt(parts[1], 10) - 1;
            }
            if (this._displayedYear == null || isNaN(this._displayedYear)) {
                var t = new Date();
                this._displayedYear = t.getFullYear();
                this._displayedMonth = t.getMonth();
            }

            // Bretzel SSR emits the header + weekday row + an EMPTY
            // grid container (``data-bz-cal-grid`` with no children).
            // Fill the grid here on first connect ; subsequent attr
            // changes go through ``attributeChangedCallback`` →
            // ``_render`` which replaces all rendered children.
            this._render();
        }

        attributeChangedCallback(name, oldVal, newVal) {
            if (!this._initialized) return;     // initial attr setting
            if (oldVal === newVal) return;

            // A write of ``value`` that GETS THROUGH is authoritative:
            // it comes either from our own commit, or from outside (the
            // wrapper's mirror, a ``.set()``). In both cases the
            // selection in progress is void. The mirror pushing the same
            // value back does NOT come through here (the ``oldVal ===
            // newVal`` guard above), so a pending state never dies of a
            // mere rescan — which is exactly the invariant sought.
            if (name === 'value') this._pendingStart = null;

            // Sync the displayed month if the external observer (e.g.
            // a ClientBinding) wrote back through ``month=``.
            if (name === 'month' && newVal) {
                var parts = newVal.split('-');
                var y = parseInt(parts[0], 10);
                var m = parseInt(parts[1], 10) - 1;
                if (!isNaN(y) && !isNaN(m) &&
                    (y !== this._displayedYear ||
                     m !== this._displayedMonth)) {
                    this._displayedYear = y;
                    this._displayedMonth = m;
                }
            }

            this._scheduleRender();
        }

        _scheduleRender() {
            // Batch multiple attribute changes (typical when idiomorph
            // morphs several attrs in one tick) into a single render.
            if (this._renderScheduled) return;
            this._renderScheduled = true;
            queueMicrotask(() => {
                this._renderScheduled = false;
                this._render();
            });
        }

        // ── Public DOM API ───────────────────────────────────────────

        set(value) {
            var mode = this.getAttribute('mode') || 'picker';
            var serialized;
            if (mode === 'range' && Array.isArray(value)) {
                serialized = JSON.stringify(value);
            } else if (value == null) {
                serialized = '';
            } else {
                serialized = String(value);
            }
            // Explicit, and not only through
            // ``attributeChangedCallback``: a ``.clear()`` on a calendar
            // whose attribute is already ``''`` triggers no callback, and
            // would otherwise let a pending selection survive a
            // requested clear.
            this._pendingStart = null;
            this.setAttribute('value', serialized);
            this._syncHiddenAndFireChange(serialized, value);
        }

        clear() {
            this.set(null);
        }

        /* Repaint AFTER a morph that erased the body rendered here.
         *
         * The hole, measured on 2026-08-21: the SSR emits an EMPTY grid
         * container that ``connectedCallback`` fills. When idiomorph
         * morphs the calendar IN PLACE — the refresh of a
         * ``@refreshable`` zone containing it — the children go back to
         * the server version, so empty. ``connectedCallback`` does not
         * run again (the node SURVIVED), nor does
         * ``attributeChangedCallback`` (no attribute changed): nobody
         * refills, and the calendar stays amputated FOR GOOD.
         *
         * The file's header says the configuration lives in attributes
         * "that idiomorph can morph freely". That is true of the
         * ATTRIBUTES; it is not true of the CHILDREN, and that is the
         * counterpart the "custom element" choice had not honoured.
         *
         * Called by the ``bz-effect`` the Python sets on the root, and it
         * is indeed ``bz-effect`` and NOT ``bz-init``: the latter is
         * one-shot per NODE (``el._bzInitDone``, which explicitly
         * survives a rebind), yet idiomorph morphs IN PLACE — the node
         * survives, so a ``bz-init`` would never run again. A
         * ``bz-effect`` is disposed then redone by ``bindEl`` at every
         * rescan, and the bridge rescans its target at every swap. Same
         * choice and same reason as SignaturePad's ``_observe()``, which
         * writes in black and white "at every rescan rather than at the
         * bz-init".
         *
         * No new vocabulary, then: no ``hx-preserve``, no home-made morph
         * hook. The day a SECOND custom element exists, that will be the
         * moment to make it a runtime policy — not before.
         *
         * The guard is a DOM measurement, and it is legitimate here: it
         * DERIVES nothing (no display depends on it), it observes a
         * one-off fact — have my children been erased — at the only
         * moment the question arises. Without it, every unrelated swap
         * would repaint the grid and kill the range preview being
         * hovered.
         */
        rehydrate() {
            if (!this._initialized) return;   // connectedCallback rendra
            var body = this.querySelector('[data-bz-cal-grid]') ||
                       this.querySelector('[data-bz-cal-months]');
            if (!body || body.firstElementChild) return;
            this._render();
        }

        // The picker's selected date (single) or range start, as an ISO
        // string — or null when nothing is picked. Used by ``focus()`` to
        // know where to navigate.
        _selectedDate() {
            var mode = this.getAttribute('mode') || 'picker';
            // ``week`` returns a scalar DATE like ``picker`` (the
            // week's first day), not a pair — so the same reading.
            if (mode === 'picker' || mode === 'week') {
                var v = this.getAttribute('value');
                return (v && /^\d{4}-\d{2}-\d{2}$/.test(v)) ? v : null;
            }
            // A range being selected HAS a start, even if it is not in
            // the attribute yet: ``.focus()`` must navigate to IT, not to
            // the old committed range.
            if (this._pendingStart) return this._pendingStart;
            var arr = parseJSON(this.getAttribute('value') || '', []);
            return (Array.isArray(arr) && arr[0]
                && /^\d{4}-\d{2}-\d{2}$/.test(arr[0])) ? arr[0] : null;
        }

        focus() {
            // If a date is SELECTED but sits outside the displayed month,
            // navigate the grid to it FIRST — otherwise its cell doesn't
            // exist in the DOM and ``.focus()`` silently lands on the
            // current view's first cell (no visible movement). This is
            // what makes ``.focus()`` truly "focus the selected date".
            var self = this;
            var sel = this._selectedDate();
            if (sel) {
                var y = +sel.slice(0, 4);
                var m = +sel.slice(5, 7) - 1;
                if (y !== this._displayedYear || m !== this._displayedMonth) {
                    this._displayedYear = y;
                    this._displayedMonth = m;
                    // Sync the Python header scope + any ``month`` binding.
                    // ``_dispatchMonthChange`` sets the ``month`` attr, which
                    // schedules a microtask ``_render`` — so DON'T render
                    // synchronously here (that cell would be blown away and
                    // focus stolen). Defer the focus one microtask so it runs
                    // AFTER that render rebuilds the grid.
                    this._dispatchMonthChange();
                    queueMicrotask(function () { self._focusBestCell(); });
                    return;
                }
            }
            this._focusBestCell();
        }

        // Focus the SELECTED date, then TODAY, then the first focusable
        // cell in the CURRENT view. ``data-selected`` / ``data-today`` are
        // stamped per cell in ``_render`` ; each falls through gracefully
        // (querySelector → null) to the next candidate.
        _focusBestCell() {
            var target =
                this.querySelector(
                    '[data-day-cell][data-selected="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-day-cell][data-today="true"]'
                    + ':not([aria-disabled="true"])'
                ) ||
                this.querySelector(
                    '[data-day-cell]:not([aria-disabled="true"])'
                );
            if (target) target.focus();
        }

        blur() {
            var focused = this.querySelector('[data-day-cell]:focus');
            if (focused) focused.blur();
        }

        prevMonth() {
            if (this._displayedMonth === 0) {
                this._displayedMonth = 11;
                this._displayedYear -= 1;
            } else {
                this._displayedMonth -= 1;
            }
            this._dispatchMonthChange();
            this._scheduleRender();
        }

        nextMonth() {
            if (this._displayedMonth === 11) {
                this._displayedMonth = 0;
                this._displayedYear += 1;
            } else {
                this._displayedMonth += 1;
            }
            this._dispatchMonthChange();
            this._scheduleRender();
        }

        // ── Internals ────────────────────────────────────────────────

        _dispatchMonthChange() {
            this.dispatchEvent(new CustomEvent('month-change', {
                detail: {
                    year: this._displayedYear,
                    month: this._displayedMonth + 1,
                },
                bubbles: true,
            }));
            var newIso = this._displayedYear + '-' +
                String(this._displayedMonth + 1).padStart(2, '0') + '-01';
            this._suppressMonthSync = true;
            this.setAttribute('month', newIso);
            this._suppressMonthSync = false;
            // Write back to bound ClientState (``month=binding`` at the
            // Python call site). Without this the Client playground
            // ``ui.text(client.displayed_month)`` echo stays empty.
            this._writeBinding(
                this.getAttribute('data-bz-month-path'), newIso
            );
        }

        _syncHiddenAndFireChange(serializedAttr, detailValue) {
            var hidden = this.querySelector('input[type="hidden"]');
            if (hidden) {
                hidden.value = serializedAttr;
                hidden.dispatchEvent(
                    new Event('change', { bubbles: true })
                );
            }
            // Write back to bound ClientState (``value=binding`` at the
            // Python call site). Without this the Client playground
            // ``ui.text(client.picked)`` echo stays empty.
            this._writeBinding(
                this.getAttribute('data-bz-value-path'), detailValue
            );
            this.dispatchEvent(new CustomEvent('change', {
                detail: { value: detailValue },
                bubbles: true,
            }));
        }

        _writeBinding(path, value) {
            // Walk a ``$bz.state.X.y.field`` dotted path and assign
            // ``value`` to the leaf. Bails silently if the runtime
            // store hasn't booted yet (defensive — connectedCallback
            // can race with bootstrap in pathological cases).
            if (!path) return;
            var bz = window.$bz;
            if (!bz || !bz.state) return;
            var parts = path.split('.');
            if (parts[0] === '$bz') parts.shift();
            if (parts[0] === 'state') parts.shift();
            if (parts.length === 0) return;
            var obj = bz.state;
            for (var i = 0; i < parts.length - 1; i++) {
                if (obj[parts[i]] == null) return;
                obj = obj[parts[i]];
            }
            obj[parts[parts.length - 1]] = value;
        }

        _parseConfig() {
            var thisYear = new Date().getFullYear();
            return {
                mode: this.getAttribute('mode') || 'picker',
                value: this.getAttribute('value') || '',
                weekstart:
                    (parseInt(this.getAttribute('weekstart') || '1', 10)
                        % 7 + 7) % 7,
                min: this.getAttribute('min') || '',
                max: this.getAttribute('max') || '',
                disabled: this.hasAttribute('disabled'),
                disabledSet: new Set(
                    parseJSON(this.getAttribute('disabled-dates'), [])
                ),
                // ``marks``: {iso: count}. The accessible name's
                // template arrives RESOLVED from the server — the
                // framework's word table is in Python, and this grid is
                // built here.
                marks: parseJSON(this.getAttribute('marks'), {}),
                markLabel: this.getAttribute('data-bz-mark-label')
                    || '{day}, {n} events',
                weekdayNames: parseJSON(
                    this.getAttribute('weekday-names'), DEFAULT_WEEKDAYS()
                ),
                // The FULL names, for the headers' ``title=``.
                //
                // Empty as soon as the app supplies its own
                // abbreviations: guessing "mer." → "mercredi" would work
                // in French and nowhere else, and a WRONG title is worse
                // than no title. An app that wants its own declares its
                // language and lets the locale do the work.
                weekdayLongNames: this.getAttribute('weekday-names')
                    ? []
                    : DEFAULT_WEEKDAYS_LONG(),
                monthNames: parseJSON(
                    this.getAttribute('month-names'), DEFAULT_MONTHS()
                ),
                theme: parseJSON(
                    this.getAttribute('data-bz-theme'), {}
                ),
                yearMin: parseInt(
                    this.getAttribute('data-bz-year-min') || (thisYear - 10),
                    10,
                ),
                yearMax: parseInt(
                    this.getAttribute('data-bz-year-max') || (thisYear + 10),
                    10,
                ),
            };
        }

        /* The YEAR grid of ``month`` mode — 12 cells instead of the
         * weekday-row + day-grid pair.
         *
         * It is the component's SECOND kind of grid, and the only place
         * where it does not render days. Everything else (Python header,
         * hidden input, change dispatch, imperative listeners) is shared
         * — hence the early return in ``_render`` rather than a separate
         * class.
         *
         * The bounds compare in ``"YYYY-MM"``, never as dates: the format
         * is zero-padded, so it sorts lexicographically as it sorts
         * chronologically. ``min`` / ``max`` arrive as ``YYYY-MM-DD`` —
         * we truncate them, which makes a PARTIALLY allowed month
         * clickable, and it is intended: a ``min`` on 15 March does not
         * forbid "March".
         */
        _renderMonthGrid(cfg) {
            var theme = cfg.theme || {};
            var cellCls = escapeAttr(theme.month_cell || '');
            var selected = /^\d{4}-\d{2}$/.test(cfg.value) ? cfg.value : '';
            var now = new Date();
            var currentYm = now.getFullYear() + '-' +
                String(now.getMonth() + 1).padStart(2, '0');
            var lo = cfg.min ? cfg.min.slice(0, 7) : '';
            var hi = cfg.max ? cfg.max.slice(0, 7) : '';
            var html = '';
            for (var m = 0; m < 12; m++) {
                var ym = this._displayedYear + '-' +
                    String(m + 1).padStart(2, '0');
                var dis = (lo && ym < lo) || (hi && ym > hi);
                html +=
                    '<button type="button" data-month-cell ' +
                    'class="' + cellCls + '" ' +
                    'data-value="' + ym + '" ' +
                    'data-selected="' + (ym === selected) + '" ' +
                    'data-current="' + (ym === currentYm) + '" ' +
                    'aria-disabled="' + dis + '" ' +
                    'tabindex="' + (dis ? -1 : 0) + '"' +
                    (cfg.disabled ? ' disabled' : '') +
                    '><span>' + escapeAttr(cfg.monthNames[m]) + '</span>' +
                    '</button>';
            }
            return '<div data-bz-cal-months class="' +
                escapeAttr(theme.month_grid || '') + '">' + html + '</div>';
        }

        _render() {
            var cfg = this._parseConfig();
            if (cfg.mode === 'month') {
                this._replaceBody(this._renderMonthGrid(cfg));
                return;
            }
            var label = cfg.monthNames[this._displayedMonth] + ' ' +
                this._displayedYear;
            var rotatedWeekdays = cfg.weekdayNames
                .slice(cfg.weekstart)
                .concat(cfg.weekdayNames.slice(0, cfg.weekstart));
            // Rotated by the SAME number of steps, otherwise a
            // column's title would name the day next to it — worse than
            // nothing.
            var longs = cfg.weekdayLongNames || [];
            var rotatedLong = longs.length === 7
                ? longs.slice(cfg.weekstart).concat(longs.slice(0, cfg.weekstart))
                : [];

            // Range bounds for highlighting
            var rangeStart = '', rangeEnd = '';
            if (cfg.mode === 'range') {
                // The mode guard is load-bearing and stays a SINGLE
                // condition: a ``mode`` attribute that flips while a
                // pending state is alive does not clean it.
                if (this._pendingStart) {
                    // A selection in progress: the pending start beats
                    // the committed value, still the OLD range.
                    rangeStart = this._pendingStart;
                } else if (cfg.value) {
                    var arr = parseJSON(cfg.value, []);
                    if (Array.isArray(arr) && arr.length >= 1) {
                        rangeStart = arr[0] || '';
                        rangeEnd = arr[1] || '';
                    }
                }
            } else if (cfg.mode === 'week' && cfg.value) {
                // A week IS a closed range of 7 days. Rendering it as
                // such reuses ALL of the range mode's band rendering —
                // flat ends on the inner side, tinted middle — instead
                // of inventing a second visual vocabulary for the same
                // idea.
                rangeStart = weekStartOf(cfg.value, cfg.weekstart);
                rangeEnd = addDays(rangeStart, 6);
            }
            var picked = cfg.mode === 'picker' ? cfg.value : '';

            var self = this;
            function isSelected(s) {
                if (cfg.mode === 'picker') return s === picked;
                return s === rangeStart || s === rangeEnd;
            }
            function rangeBounds() {
                if (cfg.mode === 'week') {
                    // No progressive hover here: a week is chosen in a
                    // single click, so its bounds are always known and
                    // complete.
                    return rangeStart
                        ? { lo: rangeStart, hi: rangeEnd }
                        : { lo: null, hi: null };
                }
                if (cfg.mode !== 'range' || !rangeStart) {
                    return { lo: null, hi: null };
                }
                var effEnd = rangeEnd || self._hoverDate;
                if (!effEnd) {
                    return { lo: rangeStart, hi: rangeStart };
                }
                var lo = rangeStart < effEnd ? rangeStart : effEnd;
                var hi = rangeStart < effEnd ? effEnd : rangeStart;
                return { lo: lo, hi: hi };
            }
            function isInRange(s) {
                var b = rangeBounds();
                return b.lo !== null && s > b.lo && s < b.hi;
            }
            function isRangeStart(s) {
                var b = rangeBounds();
                return b.lo !== null && s === b.lo && b.lo !== b.hi;
            }
            function isRangeEnd(s) {
                var b = rangeBounds();
                return b.hi !== null && s === b.hi && b.lo !== b.hi;
            }
            function isCellDisabled(s) {
                if (cfg.disabledSet.has(s)) return true;
                if (cfg.min && s < cfg.min) return true;
                if (cfg.max && s > cfg.max) return true;
                return false;
            }

            // Compute the 6 × 7 grid
            var first = new Date(
                this._displayedYear, this._displayedMonth, 1
            );
            var offset = (first.getDay() - cfg.weekstart + 7) % 7;
            var todayStr = iso(new Date());
            var theme = cfg.theme || {};
            var cellsHTML = '';
            for (var w = 0; w < 6; w++) {
                for (var c = 0; c < 7; c++) {
                    var d = new Date(
                        this._displayedYear, this._displayedMonth,
                        1 + w * 7 + c - offset
                    );
                    var s = iso(d);
                    var day = d.getDate();
                    var inMonth = d.getMonth() === this._displayedMonth;
                    var isDis = isCellDisabled(s);
                    // A mark only lives in the DISPLAYED month: the
                    // grid overflows by six days on either side, and
                    // dotting a 31 July visible from August would make
                    // one read a load that is not that of the month
                    // being looked at.
                    var mark = inMonth ? (cfg.marks[s] | 0) : 0;
                    var markHTML = mark > 0
                        ? '<span class="' + escapeAttr(theme.day_mark || '') +
                          '" aria-hidden="true"></span>'
                        : '';
                    var markLabel = mark > 0
                        ? ' aria-label="' + escapeAttr(
                              cfg.markLabel
                                  .replace('{day}', day)
                                  .replace('{n}', mark)
                          ) + '"'
                        : '';
                    cellsHTML +=
                        '<button type="button" data-day-cell ' +
                        'class="' + escapeAttr(theme.day_cell || '') + '" ' +
                        'data-date="' + s + '" ' +
                        'data-mark="' + mark + '"' + markLabel + ' ' +
                        'data-outside="' + (!inMonth) + '" ' +
                        'data-today="' + (s === todayStr) + '" ' +
                        'data-selected="' + isSelected(s) + '" ' +
                        'data-in-range="' + isInRange(s) + '" ' +
                        'data-range-start="' + isRangeStart(s) + '" ' +
                        'data-range-end="' + isRangeEnd(s) + '" ' +
                        'aria-disabled="' + isDis + '" ' +
                        'tabindex="' + (isDis ? -1 : 0) + '"' +
                        (cfg.disabled ? ' disabled' : '') +
                        '><span>' + day + '</span>' + markHTML + '</button>';
                }
            }

            var chevronCls = escapeAttr(theme.chevron_class || '');
            var navCls = escapeAttr(theme.nav_button || '');
            var labelCls = escapeAttr(theme.month_label || '');
            var weekdayRowCls = escapeAttr(theme.weekday_row || '');
            var weekdayCls = escapeAttr(theme.weekday || '');
            var weekRowCls = escapeAttr(theme.week_row || '');
            var headerCls = escapeAttr(theme.header || '');
            var disabledAttr = cfg.disabled ? ' disabled' : '';

            var weekdaysHTML = '';
            for (var i = 0; i < rotatedWeekdays.length; i++) {
                // ``title`` only if it BRINGS something: the fallback
                // with no Intl renders the same abbreviations on both
                // sides, and a title identical to the visible text is
                // noise for a screen reader.
                var entier = rotatedLong[i];
                var titre = (entier && entier !== rotatedWeekdays[i])
                    ? ' title="' + escapeAttr(entier) + '"'
                    : '';
                weekdaysHTML +=
                    '<div class="' + weekdayCls + '"' + titre + '>' +
                    escapeAttr(rotatedWeekdays[i]) + '</div>';
            }

            // The header (prev/next + month/year selectors) is now
            // rendered by Python using ``ui.dropdown`` + ``ui.icon_button``
            // so it inherits the framework theme. We preserve any
            // ``data-bz-cal-header`` child the Python side emitted and
            // never generate one here.
            var html =
                '<div data-bz-cal-weekdays class="' + weekdayRowCls + '">' +
                  weekdaysHTML +
                '</div>' +
                '<div data-bz-cal-grid class="' + weekRowCls + '">' +
                  cellsHTML +
                '</div>';

            this._replaceBody(html);
        }

        /* Replace the calendar's BODY while preserving the two children
         * that do not come from here: the hidden input (the form-data
         * carrier) and the header rendered by Python
         * (``data-bz-cal-header``, which contains the theme's IconButton
         * and dropdowns).
         *
         * Extracted from ``_render`` when ``month`` mode arrived: it
         * renders a TOTALLY different grid but must preserve exactly the
         * same two children. Copying the loop would have guaranteed that
         * one of the two modes forgets one of them one day.
         */
        _replaceBody(html) {
            var hidden = this.querySelector('input[type="hidden"]');
            var pyHeader = this.querySelector('[data-bz-cal-header]');
            var children = Array.from(this.childNodes);
            for (var i = 0; i < children.length; i++) {
                var child = children[i];
                if (child === hidden) continue;
                if (child === pyHeader) continue;
                this.removeChild(child);
            }
            this.insertAdjacentHTML('beforeend', html);
            this._wireListeners();
        }

        _paintHoverPreview() {
            // Patch only the ``data-in-range`` / ``data-range-start`` /
            // ``data-range-end`` attributes on EXISTING cells. No
            // children removal, no listener re-bind. Used during
            // mouse hover preview to avoid the "cell vanishes under
            // the cursor" bug.
            // This path exists ONLY during a selection in progress: its
            // two callers are behind ``_pendingStart`` (the
            // ``mouseenter`` directly, the ``mouseleave`` through
            // ``_hoverDate`` which is only set there). So it never has
            // to read the attribute — which, since the fix, cannot carry
            // a half-open pair anyway. Testing it here would contradict
            // the rest of the file.
            //
            // The mode guard is implicit: ``_pendingStart`` is only set
            // in ``_handleCellClick``'s ``range`` branch.
            var rangeStart = this._pendingStart;
            if (!rangeStart) return;
            var effEnd = this._hoverDate || '';
            var lo = '', hi = '';
            if (effEnd && effEnd !== rangeStart) {
                lo = rangeStart < effEnd ? rangeStart : effEnd;
                hi = rangeStart < effEnd ? effEnd : rangeStart;
            }
            var cells = this.querySelectorAll('[data-day-cell]');
            cells.forEach(function (cell) {
                var s = cell.getAttribute('data-date');
                var inRange = !!(lo && s > lo && s < hi);
                var isStart = !!(lo && s === lo);
                var isEnd = !!(hi && s === hi && lo !== hi);
                cell.setAttribute('data-in-range', inRange.toString());
                cell.setAttribute('data-range-start', isStart.toString());
                cell.setAttribute('data-range-end', isEnd.toString());
            });
        }

        _wireListeners() {
            var self = this;
            // ``month`` mode: cells of another kind, a click of
            // another nature. Wired BEFORE the day loop because in month
            // mode there is no day cell at all — the loop below runs
            // empty.
            this.querySelectorAll('[data-month-cell]').forEach(function (c) {
                c.onclick = function () {
                    if (c.getAttribute('aria-disabled') === 'true') return;
                    var ym = c.getAttribute('data-value');
                    self.setAttribute('value', ym);
                    self._syncHiddenAndFireChange(ym, ym);
                };
            });
            // Prev / next buttons live in the Python-rendered header
            // (``data-bz-cal-header``). They're ``bz-on:click``
            // handlers that mutate the wrapper's ``year`` / ``month``
            // scope ; nothing to wire here.

            var cells = this.querySelectorAll('[data-day-cell]');
            var mode = this.getAttribute('mode') || 'picker';
            cells.forEach(function (cell) {
                cell.onclick = function () { self._handleCellClick(cell); };
                if (mode === 'range') {
                    // CRITICAL : mouse events must NOT trigger a full
                    // re-render. Each ``_render`` removes + re-inserts
                    // every cell, which means the cell currently under
                    // the cursor is replaced with a fresh DOM node — but
                    // that node never receives a ``mouseenter`` (the
                    // cursor was already over the position when it
                    // appeared), so ``_hoverDate`` freezes at the last
                    // value AND the new cell's ``onclick`` may not have
                    // settled by the time the user clicks. Bug visible
                    // on every range pick : the hover bar gets stuck
                    // mid-flight and the second click vanishes.
                    //
                    // Fix : ``_paintHoverPreview`` patches the data-*
                    // attrs IN PLACE on the existing cells. No DOM
                    // mutation beyond the affected attributes, so the
                    // cursor stays over the SAME node from start to
                    // finish, listeners stay live.
                    cell.onmouseenter = function () {
                        // "Are we between the two clicks?" now reads on
                        // ``_pendingStart`` — the attribute never carries
                        // a half-open pair any more.
                        if (!self._pendingStart) return;
                        self._hoverDate = cell.getAttribute('data-date');
                        self._paintHoverPreview();
                    };
                    cell.onmouseleave = function () {
                        if (self._hoverDate) {
                            self._hoverDate = null;
                            self._paintHoverPreview();
                        }
                    };
                }
            });

            // Listen for the imperative ``bz-set`` / ``bz-prev-month`` /
            // ``bz-next-month`` events dispatched by Python's
            // ``.set()`` / ``.prev_month()`` / ``.next_month()`` methods.
            // Also relay ``focusin``/``focusout`` (which DO bubble from
            // the cells) as ``focus``/``blur`` CustomEvents on the root —
            // this is what makes ``on_focus`` / ``on_blur`` Python
            // kwargs fire when a cell receives keyboard focus, since
            // native focus / blur don't bubble.
            if (!this._wiredImperativeListeners) {
                this._wiredImperativeListeners = true;
                this.addEventListener('bz-set', function (e) {
                    self.set(e.detail && e.detail.value);
                });
                this.addEventListener('bz-prev-month', function () {
                    self.prevMonth();
                });
                this.addEventListener('bz-next-month', function () {
                    self.nextMonth();
                });
                this.addEventListener('focusin', function (e) {
                    // Only relay child focus, not focus on the root
                    // itself (which would be ambiguous and rare).
                    if (e.target !== self) {
                        self.dispatchEvent(new CustomEvent('focus', {
                            detail: { target: e.target },
                            bubbles: true,
                        }));
                    }
                });
                this.addEventListener('focusout', function (e) {
                    if (e.target !== self) {
                        self.dispatchEvent(new CustomEvent('blur', {
                            detail: { target: e.target },
                            bubbles: true,
                        }));
                    }
                });
            }
        }

        _handleCellClick(cell) {
            if (cell.getAttribute('aria-disabled') === 'true') return;
            var s = cell.getAttribute('data-date');
            var mode = this.getAttribute('mode') || 'picker';

            if (mode === 'picker') {
                this.setAttribute('value', s);
                this._syncHiddenAndFireChange(s, s);
                return;
            }

            if (mode === 'week') {
                // Clicking ANY day picks its week, and what comes out
                // is that week's FIRST day — never the clicked day.
                // Without that snapping, two clicks in the same week
                // would produce two different values for the same
                // selection.
                var ws = (parseInt(
                    this.getAttribute('weekstart') || '1', 10
                ) % 7 + 7) % 7;
                var start = weekStartOf(s, ws);
                this.setAttribute('value', start);
                this._syncHiddenAndFireChange(start, start);
                return;
            }

            // range mode — two steps: we open on a PENDING start, we
            // close on the second click. Only the closing touches the
            // ``value`` attribute (cf. ``_pendingStart``).
            var rangeStart = this._pendingStart;

            if (!rangeStart) {
                this._hoverDate = null;
                this._pendingStart = s;
                // Repaint: with no attribute write there is no
                // ``attributeChangedCallback`` left to do it. We go
                // through ``_scheduleRender`` and not ``_render`` to keep
                // the render ASYNCHRONOUS as before — the attribute path
                // already batched in a microtask.
                this._scheduleRender();
                return;
            }

            // Close the range
            var newStart = rangeStart, newEnd = s;
            if (s < rangeStart) {
                newStart = s;
                newEnd = rangeStart;
            }
            this._hoverDate = null;
            this._pendingStart = null;
            var newVal = JSON.stringify([newStart, newEnd]);
            this.setAttribute('value', newVal);
            this._syncHiddenAndFireChange(newVal, [newStart, newEnd]);
        }
    }

    customElements.define('bz-calendar', BzCalendar);
})();

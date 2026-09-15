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

    // Dérivés de ``<html lang>`` par 22_locale.js, pas écrits ici : une
    // table en dur rendait « August / MON TUE WED » à toute app, quelle
    // que soit sa langue, et la seule prise était de repasser
    // ``month_names=`` À CHAQUE MONTAGE (trois fois sur un seul écran du
    // CRM). Les listes explicites du composant gagnent toujours — elles
    // arrivent par attribut et ces défauts ne servent qu'à leur absence.
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

    /* Le jour ISO décalé de ``n`` jours. Passe par un ``Date`` plutôt que
     * par de l'arithmétique sur la chaîne : lui seul connaît les fins de
     * mois et les années bissextiles. */
    function addDays(isoStr, n) {
        var p = isoStr.split('-');
        return iso(new Date(+p[0], +p[1] - 1, +p[2] + n));
    }

    /* Le premier jour de la semaine qui CONTIENT ``isoStr``, selon
     * ``weekstart`` (0 = dimanche, 1 = lundi…).
     *
     * C'est la seule règle du mode ``week`` : cliquer n'importe quel jour
     * choisit sa semaine, et la valeur rendue est ce premier jour. Le
     * modulo est doublé (``% 7 + 7) % 7``) parce que JS rend un reste
     * NÉGATIF pour un dividende négatif — sans lui, toute semaine dont le
     * jour cliqué tombe avant ``weekstart`` remonterait d'une semaine.
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
            // Le début d'une plage EN COURS de sélection, mode ``range``
            // seulement. Il vit ici et PAS dans l'attribut ``value`` —
            // c'est tout le point.
            //
            // Le premier clic d'une plage n'émet aucun ``change`` (il n'y
            // a pas encore de valeur à annoncer), donc le scope du picker
            // ne peut pas représenter cet état : il n'a que ``vstart`` /
            // ``vend``, tous deux vides. Or le ``bz-effect`` miroir du
            // wrapper traite ce scope comme la source de vérité et pousse
            // ``''`` dans l'attribut dès qu'il re-tourne — ce qui arrive à
            // CHAQUE swap HTMX, le bridge rescannant la cible. Tant que le
            // début en attente vivait dans l'attribut, ce miroir l'effaçait
            // et le second clic rouvrait une plage au lieu de la fermer :
            // le champ restait vide et l'utilisateur cliquait sans fin.
            //
            // Ici le miroir n'a plus rien à écraser — il réécrit ``''``
            // par-dessus ``''``, donc aucun ``attributeChangedCallback``,
            // donc l'attente survit. L'attribut ne porte plus que du
            // COMMITÉ ; c'est la surface de synchro avec l'extérieur, pas
            // un tampon d'état transitoire. ``_hoverDate`` avait déjà
            // exactement ce statut, d'où le voisinage.
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

            // Une écriture de ``value`` qui PASSE est autoritaire : elle
            // vient soit de notre propre commit, soit de l'extérieur (le
            // miroir du wrapper, un ``.set()``). Dans les deux cas la
            // sélection en cours est caduque. Le miroir qui repousse la
            // même valeur ne passe PAS par ici (garde ``oldVal ===
            // newVal`` ci-dessus), donc une attente ne meurt jamais d'un
            // simple rescan — c'est exactement l'invariant recherché.
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
            // Explicite, et pas seulement via ``attributeChangedCallback``:
            // un ``.clear()`` sur un calendrier dont l'attribut vaut déjà
            // ``''`` ne déclenche aucun callback, et laisserait sinon une
            // sélection en attente survivre à un effacement demandé.
            this._pendingStart = null;
            this.setAttribute('value', serialized);
            this._syncHiddenAndFireChange(serialized, value);
        }

        clear() {
            this.set(null);
        }

        /* Repeindre APRÈS un morph qui a effacé le corps rendu ici.
         *
         * Le trou, mesuré le 2026-08-21 : le SSR émet un conteneur de
         * grille VIDE que ``connectedCallback`` remplit. Quand idiomorph
         * morphe le calendrier EN PLACE — le refresh d'une zone
         * ``@refreshable`` qui le contient — les enfants reviennent à la
         * version serveur, donc vides. ``connectedCallback`` ne re-tourne
         * pas (le nœud a SURVÉCU), ``attributeChangedCallback`` non plus
         * (aucun attribut n'a changé) : personne ne re-remplit, et le
         * calendrier reste amputé DÉFINITIVEMENT.
         *
         * L'en-tête du fichier dit que la configuration vit dans des
         * attributs « que idiomorph peut morpher librement ». C'est vrai
         * des ATTRIBUTS ; ça ne l'est pas des ENFANTS, et c'est la
         * contrepartie que le choix « custom element » n'avait pas tenue.
         *
         * Appelé par le ``bz-effect`` que le Python pose sur la racine,
         * et c'est bien ``bz-effect`` et PAS ``bz-init`` : ce dernier est
         * one-shot par NŒUD (``el._bzInitDone``, qui survit
         * explicitement au rebind), or idiomorph morphe EN PLACE — le
         * nœud survit, donc un ``bz-init`` ne re-tournerait jamais. Un
         * ``bz-effect`` est disposé puis refait par ``bindEl`` à chaque
         * rescan, et le bridge rescanne sa cible à chaque swap. Même
         * choix et même raison que ``_observe()`` du SignaturePad, qui
         * écrit noir sur blanc « à chaque rescan plutôt qu'au bz-init ».
         *
         * Aucun vocabulaire neuf, donc : pas de ``hx-preserve``, pas de
         * hook de morph maison. Le jour où un DEUXIÈME custom element
         * existera, ce sera le moment d'en faire une politique du
         * runtime — pas avant.
         *
         * La garde est une mesure du DOM, et c'est ici légitime : elle ne
         * DÉRIVE rien (aucun affichage n'en dépend), elle constate un
         * fait ponctuel — mes enfants ont-ils été effacés — au seul
         * moment où la question se pose. Sans elle, chaque swap sans
         * rapport repeindrait la grille et tuerait l'aperçu de plage en
         * cours de survol.
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
            // ``week`` rend une DATE scalaire comme ``picker`` (le premier
            // jour de la semaine), pas une paire — donc même lecture.
            if (mode === 'picker' || mode === 'week') {
                var v = this.getAttribute('value');
                return (v && /^\d{4}-\d{2}-\d{2}$/.test(v)) ? v : null;
            }
            // Une plage en cours de sélection A un début, même s'il n'est
            // pas encore dans l'attribut : ``.focus()`` doit naviguer vers
            // LUI, pas vers l'ancienne plage commitée.
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
                // ``marks`` : {iso: compte}. Le gabarit du nom
                // accessible arrive RESOLU du serveur — la table des
                // mots du framework est en Python, et cette grille est
                // batie ici.
                marks: parseJSON(this.getAttribute('marks'), {}),
                markLabel: this.getAttribute('data-bz-mark-label')
                    || '{day}, {n} events',
                weekdayNames: parseJSON(
                    this.getAttribute('weekday-names'), DEFAULT_WEEKDAYS()
                ),
                // Les noms ENTIERS, pour le ``title=`` des en-tetes.
                //
                // Vide des que l'app fournit ses propres abreviations :
                // deviner « mer. » -> « mercredi » marcherait en francais
                // et nulle part ailleurs, et un title FAUX est pire que
                // pas de title. Une app qui veut les siens declare sa
                // langue et laisse la locale faire.
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

        /* La grille d'ANNÉE du mode ``month`` — 12 cellules au lieu du
         * couple ligne-de-jours + grille-de-jours.
         *
         * C'est le SECOND type de grille du composant, et le seul point
         * où il ne rend pas des jours. Tout le reste (header Python,
         * input caché, dispatch du change, listeners impératifs) est
         * partagé — d'où le retour anticipé dans ``_render`` plutôt
         * qu'une classe séparée.
         *
         * Les bornes se comparent en ``"YYYY-MM"``, jamais en dates :
         * le format est zéro-paddé, donc il se trie lexicographiquement
         * comme chronologiquement. ``min`` / ``max`` arrivent en
         * ``YYYY-MM-DD`` — on les tronque, ce qui rend un mois PARTIEL-
         * lement autorisé cliquable, et c'est voulu : un ``min`` au
         * 15 mars n'interdit pas « mars ».
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
            // Tournee du MEME nombre de crans, sinon le title d'une
            // colonne nommerait le jour d'a cote — pire que rien.
            var longs = cfg.weekdayLongNames || [];
            var rotatedLong = longs.length === 7
                ? longs.slice(cfg.weekstart).concat(longs.slice(0, cfg.weekstart))
                : [];

            // Range bounds for highlighting
            var rangeStart = '', rangeEnd = '';
            if (cfg.mode === 'range') {
                // Le garde de mode est load-bearing et reste UNE seule
                // condition : un attribut ``mode`` qui bascule pendant
                // qu'une attente est vivante ne la nettoie pas.
                if (this._pendingStart) {
                    // Sélection en cours : le début en attente prime sur
                    // la valeur commitée, encore l'ANCIENNE plage.
                    rangeStart = this._pendingStart;
                } else if (cfg.value) {
                    var arr = parseJSON(cfg.value, []);
                    if (Array.isArray(arr) && arr.length >= 1) {
                        rangeStart = arr[0] || '';
                        rangeEnd = arr[1] || '';
                    }
                }
            } else if (cfg.mode === 'week' && cfg.value) {
                // Une semaine EST une plage fermée de 7 jours. La rendre
                // comme telle réutilise TOUT le rendu de bande du mode
                // range — extrémités plates côté intérieur, milieu
                // teinté — au lieu d'inventer un second vocabulaire
                // visuel pour la même idée.
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
                    // Pas de survol progressif ici : une semaine est
                    // choisie d'un seul clic, donc ses bornes sont
                    // toujours connues et complètes.
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
                    // Une marque ne vit QUE dans le mois affiche : la
                    // grille deborde de six jours de part et d'autre, et
                    // pastiller un 31 juillet visible depuis aout ferait
                    // lire une charge qui n'est pas celle du mois qu'on
                    // regarde.
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
                // ``title`` seulement s'il APPORTE quelque chose : le
                // reflux sans Intl rend les memes abreviations des deux
                // cotes, et un title identique au texte visible est du
                // bruit pour un lecteur d'ecran.
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

        /* Remplacer le CORPS du calendrier en préservant les deux enfants
         * qui ne viennent pas d'ici : l'input caché (porteur de form
         * data) et le header rendu par Python (``data-bz-cal-header``,
         * qui contient les IconButton et les dropdowns du thème).
         *
         * Extrait de ``_render`` quand le mode ``month`` est arrivé : il
         * rend une grille TOTALEMENT différente mais doit préserver
         * exactement les mêmes deux enfants. Recopier la boucle aurait
         * garanti qu'un des deux modes oublie l'un d'eux un jour.
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
            // Ce chemin n'existe QUE pendant une sélection en cours : ses
            // deux appelants sont derrière ``_pendingStart`` (le
            // ``mouseenter`` directement, le ``mouseleave`` via
            // ``_hoverDate`` qui n'est posé que là). Il n'a donc jamais à
            // lire l'attribut — qui, depuis le fix, ne peut de toute façon
            // plus porter de paire à moitié ouverte. Le tester ici
            // contredirait le reste du fichier.
            //
            // Le garde de mode est implicite : ``_pendingStart`` n'est posé
            // que dans la branche ``range`` de ``_handleCellClick``.
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
            // Mode ``month`` : des cellules d'un autre type, un clic d'une
            // autre nature. Câblé AVANT la boucle des jours parce qu'en
            // mode month il n'y a aucune cellule de jour — la boucle
            // ci-dessous tourne à vide.
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
                        // « Sommes-nous entre les deux clics ? » se lit
                        // désormais sur ``_pendingStart`` — l'attribut ne
                        // porte plus jamais de paire à moitié ouverte.
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
                // Cliquer N'IMPORTE quel jour choisit sa semaine, et ce
                // qui sort est le PREMIER jour de cette semaine — jamais
                // le jour cliqué. Sans ce recalage, deux clics dans la
                // même semaine produiraient deux valeurs différentes
                // pour la même sélection.
                var ws = (parseInt(
                    this.getAttribute('weekstart') || '1', 10
                ) % 7 + 7) % 7;
                var start = weekStartOf(s, ws);
                this.setAttribute('value', start);
                this._syncHiddenAndFireChange(start, start);
                return;
            }

            // range mode — deux temps : on ouvre sur un début EN ATTENTE,
            // on ferme sur le second clic. Seule la fermeture touche
            // l'attribut ``value`` (cf. ``_pendingStart``).
            var rangeStart = this._pendingStart;

            if (!rangeStart) {
                this._hoverDate = null;
                this._pendingStart = s;
                // Repeindre : sans écriture d'attribut il n'y a plus de
                // ``attributeChangedCallback`` pour le faire. On passe par
                // ``_scheduleRender`` et pas ``_render`` pour garder le
                // rendu ASYNCHRONE comme avant — le chemin par l'attribut
                // batchait déjà en microtask.
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

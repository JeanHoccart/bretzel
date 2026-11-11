/* locale.js — month and weekday names, derived from the language.
 *
 * ⚠️ **This slab's place in ``runtime/sources.py`` is an ORDERING
 * CONSTRAINT.** It must load before ``calendar.js``, which calls
 * ``customElements.define('bz-calendar', …)``: that IMMEDIATELY upgrades
 * every calendar already in the DOM, and their constructor then reads
 * ``$bz.locale.weekdayNames()``.
 *
 * Loaded later, it costs **one exception thrown per calendar**. The
 * screen recovers — the ``bz-text`` directive comes back later — but the
 * flood of errors stops ``networkidle`` arriving, and a suite waiting
 * for it hangs.
 *
 * This file depends on nothing (it creates ``window.$bz`` if needed), so
 * it could live anywhere before that consumer. It is placed JUST before
 * it so that a reader wondering "why here?" finds the answer on the
 * list's next line.
 *
 * Guarded by ``tests/runtime_js/test_no_page_throws_on_load.py``, which
 * loads the component pages and requires ZERO exception. A STATIC
 * gate (forbidding a read of a ``$bz.<ns>`` set later) would flag
 * legitimate cases: DEFERRED reads, in functions called well after load.
 * What sets the defect apart is the MOMENT of the read, and only a
 * browser separates them.
 *
 * Exposed as window.$bz.locale, read by calendar.js and by the bz-*
 * expressions (``bz-text="$bz.locale.monthName(month)"``).
 *
 * Why here rather than on the server side
 * ----------------------------------------
 * Python has no safe way of naming a month in a given language: the
 * stdlib's ``locale`` module is process-GLOBAL state (and depends on the
 * locales installed on the machine), and Babel would be a dependency —
 * which the charter excludes. The browser, for its part, already ships
 * the complete table: ``Intl.DateTimeFormat`` gives it for any BCP-47
 * tag, without one extra byte.
 *
 * The language comes from ``<html lang>``, which ``Bretzel(lang=...)``
 * sets — not from an ad hoc attribute. It is the standard place, the one
 * a screen reader already reads to choose its voice, and the only one
 * that stays right if the app changes it by hand.
 *
 *   $bz.locale.tag()            the current tag ("fr", "en"…)
 *   $bz.locale.monthNames()     12 long names, January first
 *   $bz.locale.monthName(i)     a single one, 0-indexed
 *   $bz.locale.weekdayNames()     7 NARROW names ("M", "T"…), SUNDAY first
 *   $bz.locale.weekdayLongNames() the same in full, for a ``title=``
 *
 * ⚠️ NARROW, not short: the calendar's column is written in density
 * steps and its text in text steps, and only the first follows
 * ``--spacing``. "Wed" / "mer." overflow their column, even at the
 * DEFAULT density. One letter fits any step; the full name rides the
 * column's ``title=``.
 *
 * ⚠️ Sunday first, always: it is ``Date.getDay()``'s order, and it is
 * the component that rotates the list according to ``weekstart``. A list
 * written Monday-first — the French reflex — shifts every column by a
 * day.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // A fallback if the engine has no usable Intl, or if the tag is
  // invalid (Intl RAISES on "français"). It is exactly what the
  // framework returned before, so a fallback changes nothing for
  // anybody.
  const FALLBACK_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const FALLBACK_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const FALLBACK_NARROW = FALLBACK_WEEKDAYS.map(function (d) { return d[0]; });

  // ``2023-01-01`` IS a Sunday, and 2023 has twelve months — the two
  // anchors we need. Everything is computed in UTC: building these dates
  // in local time would shift by a day west of Greenwich, so the day's
  // name too.
  const SUNDAY = Date.UTC(2023, 0, 1);
  const DAY_MS = 86400000;

  const memo = Object.create(null);

  function names(tag) {
    let entry = memo[tag];
    if (entry) return entry;
    try {
      const month = new Intl.DateTimeFormat(tag, {
        month: "long",
        timeZone: "UTC",
      });
      const weekday = new Intl.DateTimeFormat(tag, {
        weekday: "narrow",
        timeZone: "UTC",
      });
      // The FULL name, for the column headers' ``title=``. Same memo,
      // same construction: seven more calls, once per language tag,
      // never per calendar.
      const weekdayLong = new Intl.DateTimeFormat(tag, {
        weekday: "long",
        timeZone: "UTC",
      });
      entry = {
        months: FALLBACK_MONTHS.map(function (_, i) {
          return month.format(new Date(Date.UTC(2023, i, 15)));
        }),
        weekdays: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekday.format(new Date(SUNDAY + i * DAY_MS));
        }),
        weekdaysLong: FALLBACK_WEEKDAYS.map(function (_, i) {
          return weekdayLong.format(new Date(SUNDAY + i * DAY_MS));
        }),
      };
    } catch (e) {
      // The fallback has no full names: the abbreviation is the
      // longest thing it knows, so it is what the ``title`` carries.
      entry = {
        months: FALLBACK_MONTHS,
        weekdays: FALLBACK_NARROW,
        weekdaysLong: FALLBACK_WEEKDAYS,
      };
    }
    memo[tag] = entry;
    return entry;
  }

  $bz.locale = {
    tag: function () {
      return (document.documentElement.getAttribute("lang") || "en").trim() || "en";
    },
    monthNames: function () {
      return names(this.tag()).months;
    },
    monthName: function (index) {
      return this.monthNames()[index] || "";
    },
    weekdayNames: function () {
      return names(this.tag()).weekdays;
    },
    weekdayLongNames: function () {
      return names(this.tag()).weekdaysLong;
    },
  };

  /* ── $bz.dates — THE date arithmetic and the ONE reader of a typed date ──
   *
   * One place, because copies drift. ``new Date("2026-08-01")`` is UTC
   * midnight — west of Greenwich, July 31 — so a month computed from it
   * can land a month off. Every date here is LOCAL and every string ISO.
   */
  function iso(d) {
    return d.getFullYear() + "-" +
      String(d.getMonth() + 1).padStart(2, "0") + "-" +
      String(d.getDate()).padStart(2, "0");
  }

  /* An ISO day as a LOCAL Date (never `new Date(isoStr)`, which is UTC),
   * or null when it is not one. */
  function fromIso(isoStr) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(isoStr || ""));
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }

  function addDays(isoStr, n) {
    const p = isoStr.split("-");
    return iso(new Date(+p[0], +p[1] - 1, +p[2] + n));
  }

  /* The first day of the month `n` months after the one of `isoStr`. */
  function addMonths(isoStr, n) {
    const d = fromIso(isoStr) || new Date();
    return iso(new Date(d.getFullYear(), d.getMonth() + n, 1));
  }

  /* The first day of the week that CONTAINS `isoStr`, according to
   * `weekstart` (0 = Sunday, 1 = Monday…). The modulo is doubled
   * (`% 7 + 7) % 7`) because JS returns a NEGATIVE remainder for a
   * negative dividend — without it, any day before `weekstart` in its
   * week would go back one week. */
  function weekStartOf(isoStr, weekstart) {
    const p = isoStr.split("-");
    const d = new Date(+p[0], +p[1] - 1, +p[2]);
    const back = (d.getDay() - weekstart + 7) % 7;
    return iso(new Date(+p[0], +p[1] - 1, +p[2] - back));
  }

  /* What the person TYPED, as an ISO day — or `""` when it is empty or
   * names no day (the field then clears). A clean ISO day passes. A
   * numeric date (`02/07/2027`, `2.7.27`, `2-7-2027`) is read in the order
   * of `<html lang>`: `new Date()` reads `MM/DD/YYYY` whatever the
   * language, so in French « 02/07/2027 » would become 7 February. The
   * order is asked of `Intl.DateTimeFormat` —
   * the day's place before or after the month's in that language's own
   * short date — so no table of locales; a day that does not exist
   * (`31/02/2027`) is refused, not rolled over. Anything else is free-form
   * (`July 19 2018`) and goes to `new Date()`. */
  function typed(text) {
    const s = String(text || "").trim();
    if (!s) return "";
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return fromIso(s) ? s : "";
    const n = s.match(/^(\d{1,2})[\/.\- ](\d{1,2})[\/.\- ](\d{4}|\d{2})$/);
    if (n) {
      const parts = new Intl.DateTimeFormat(document.documentElement.lang || undefined)
        .formatToParts(new Date(2000, 10, 22));
      const at = function (k) { return parts.findIndex(function (p) { return p.type === k; }); };
      const dayFirst = at("day") < at("month");
      const d = +n[dayFirst ? 1 : 2];
      const mo = +n[dayFirst ? 2 : 1];
      let y = +n[3];
      if (y < 100) y += 2000;
      const c = new Date(y, mo - 1, d);
      if (c.getFullYear() !== y || c.getMonth() !== mo - 1 || c.getDate() !== d) return "";
      return iso(c);
    }
    const named = byName(s);
    if (named) return named.day ? iso(named.date) : "";
    const c = new Date(s);
    return isNaN(c.getTime()) ? "" : iso(c);
  }

  /* A month named in the page's language — « 4 nov. 2026 », « novembre
   * 2026 », « Nov 4, 2026 », « mer. 4 nov. 2026 » —: the words are
   * compared, accents and dots aside, to the month names `Intl` gives for
   * `<html lang>`, short and long; a weekday name matches none (« mar. »
   * is Tuesday, « mars » March). `null` when no word names a month;
   * `{date, day}` else, `day` false when no day was written. */
  /* The ONE form a search compares, twin of Python's ``fold``
   * (``bretzel/core/text.py``) — the two must give the same string: the
   * server bakes folded options, the browser folds what is typed. The
   * twin is held by ``tests/runtime_js/test_one_fold_on_both_sides.py``. */
  function fold(text) {
    return String(text == null ? "" : text).toLowerCase().normalize("NFKD")
      .replace(/\p{M}/gu, "").toLowerCase()
      .replace(/ß/g, "ss").replace(/ς/g, "σ");
  }
  $bz.fold = fold;

  const monthWords = {};
  function plain(word) {
    return fold(word).replace(/\./g, "");
  }
  function months() {
    const tag = document.documentElement.lang || "";
    if (!monthWords[tag]) {
      const found = {};
      ["short", "long"].forEach(function (width) {
        const f = new Intl.DateTimeFormat(tag || undefined, { month: width });
        for (let m = 0; m < 12; m++) found[plain(f.format(new Date(2000, m, 1)))] = m;
      });
      monthWords[tag] = found;
    }
    return monthWords[tag];
  }
  function byName(text) {
    const words = months();
    let month = -1, year = 0, day = 0;
    String(text).split(/[\s,\u2013\u2014\-]+/).forEach(function (token) {
      if (!token) return;
      if (/^\d{4}$/.test(token)) { year = +token; return; }
      if (/^\d{1,2}$/.test(token)) { if (!day) day = +token; return; }
      const m = words[plain(token)];
      if (m !== undefined && month < 0) month = m;
    });
    if (month < 0 || !year) return null;
    const date = new Date(year, month, day || 1);
    if (day && date.getDate() !== day) return { date: date, day: false };
    return { date: date, day: !!day };
  }

  /* A typed month, as ``YYYY-MM`` — or `""`. Digits (`2026-08`,
   * `08/2026`), or the month's name (« novembre 2026 »). */
  function typedMonth(text) {
    const s = String(text || "").trim();
    if (!s) return "";
    const m = s.match(/^(\d{1,4})[^\d](\d{1,4})$/);
    if (m) {
      const y = m[1].length === 4 ? +m[1] : +m[2];
      const mo = m[1].length === 4 ? +m[2] : +m[1];
      if (mo < 1 || mo > 12 || y < 1) return "";
      return String(y).padStart(4, "0") + "-" + String(mo).padStart(2, "0");
    }
    const named = byName(s);
    return named ? iso(named.date).slice(0, 7) : "";
  }

  /* What a field SHOWS of its value, in the page's language — the value
   * itself stays ISO, it is what is posted. A day is shown in the
   * language's short NUMERIC form — « 16/10/2026 », « 10/16/2026 » in
   * American English —, the one people write, so what is shown is what
   * one types. A value that is not one (half typed) is shown as it is. */
  const formats = {};
  const NUMERIC = { day: "2-digit", month: "2-digit", year: "numeric" };
  function format(options) {
    const tag = document.documentElement.lang || "";
    const key = tag + JSON.stringify(options);
    if (!formats[key]) formats[key] = new Intl.DateTimeFormat(tag || undefined, options);
    return formats[key];
  }
  function shown(isoStr) {
    const d = fromIso(isoStr);
    return d ? format(NUMERIC).format(d) : String(isoStr || "");
  }
  /* A chart's date tick, in the page's language: « 14h30 » / « 2:30 PM »
   * (`time`), « 02 févr. » / « Feb 02 » (`day`), « févr. 2026 » (`month`),
   * « 2026 » (`year`). The server wrote it with `strftime`, in English. */
  const AXIS = {
    day: { day: "2-digit", month: "short" },
    month: { month: "short", year: "numeric" },
    year: { year: "numeric" },
  };
  function axis(stamp, style) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(String(stamp || ""));
    if (!m) return String(stamp || "");
    if (style === "time") return shownTime((m[4] || "00") + ":" + (m[5] || "00"));
    const d = new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0));
    return format(AXIS[style] || AXIS.day).format(d);
  }
  /* A day in words, « mardi 3 novembre 2026 » — what a screen reader
   * says of an event's day (the scheduler's cards). */
  function shownLong(isoStr) {
    const d = fromIso(isoStr);
    return d ? format({ weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(d)
      : String(isoStr || "");
  }
  function shownMonth(ym) {
    const m = /^(\d{4})-(\d{2})$/.exec(String(ym || ""));
    return m ? format({ month: "long", year: "numeric" }).format(new Date(+m[1], +m[2] - 1, 1))
      : String(ym || "");
  }
  /* A week by its seven days, from the first one (`weekstart`: 0 =
   * Sunday, 1 = Monday…), whatever day of it the value names: « 02/11/2026
   * – 08/11/2026 ». */
  function shownWeek(isoStr, weekstart) {
    if (!fromIso(isoStr)) return String(isoStr || "");
    const d = fromIso(weekStartOf(isoStr, weekstart || 0));
    const end = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 6);
    const f = format(NUMERIC);
    return f.formatRange ? f.formatRange(d, end) : f.format(d) + " – " + f.format(end);
  }

  /* What a field ASKS for when it is empty: the numeric form one types,
   * in the page's order and separators — « JJ/MM/AAAA » in French,
   * « MM/DD/YYYY » in American English, « DD.MM.YYYY » in German —, as the
   * browser's own date field does. The order comes from the formatter
   * `shown` uses, so the hint, what is shown and what `typed` reads agree;
   * the letters are the framework's texts (`date.typed_day`…), baked by
   * the server. */
  function letters(options, map) {
    return format(options).formatToParts(new Date(2000, 10, 22))
      .map(function (p) { return p.type in map ? map[p.type] : p.value; }).join("");
  }
  function pattern(day, month, year) {
    return letters(NUMERIC, { day: day, month: month, year: year });
  }
  function patternMonth(month, year) {
    return letters({ month: "2-digit", year: "numeric" }, { month: month, year: year });
  }

  /* ── $bz.times — THE clock: an "HH:MM" as the page's language writes it ──
   * One rule for every hour the framework shows (the time picker's field,
   * the scheduler's axis, the hour beside a dragged card): « 14h30 »,
   * « 8h » in French — the form a French reader writes, which `Intl` does
   * not give (« 14:30 ») —, otherwise `Intl`'s, « 2:30 PM » in American
   * English, « 14:30 » in British. The value stays "HH:MM". */
  function french() {
    return (document.documentElement.lang || "").split("-")[0].toLowerCase() === "fr";
  }
  const CLOCK = { hour: "numeric", minute: "2-digit" };
  /* `compact`: a whole hour without its minutes, « 9 AM » — the
   * scheduler's axis, where « 9:00 AM » broke on two lines. French is
   * already compact (« 9h »). */
  function shownTime(hhmm, compact) {
    const m = /^(\d{2}):(\d{2})$/.exec(String(hhmm || ""));
    if (!m) return String(hhmm || "");
    const h = +m[1], mi = +m[2];
    if (french()) return h + "h" + (mi ? m[2] : "");
    const when = new Date(2000, 0, 1, h, mi);
    if (compact && !mi) return format({ hour: "numeric" }).format(when);
    return format(CLOCK).format(when);
  }
  /* What is typed, as "HH:MM" — or "". « 14h30 », « 14:30 », « 14.30 »,
   * « 1430 », « 9 », and a half day in English or in the page's language
   * (« 2:30 PM », « 2 pm », « 2.30p.m. »). */
  function periods() {
    const parts = format(CLOCK).formatToParts(new Date(2000, 0, 1, 15, 0));
    const pm = parts.find(function (p) { return p.type === "dayPeriod"; });
    const am = format(CLOCK).formatToParts(new Date(2000, 0, 1, 3, 0))
      .find(function (p) { return p.type === "dayPeriod"; });
    return { am: am ? foldPeriod(am.value) : "", pm: pm ? foldPeriod(pm.value) : "" };
  }
  function foldPeriod(text) { return String(text).toLowerCase().replace(/[\s.]/g, ""); }
  function typedTime(text) {
    let s = foldPeriod(text);
    if (!s) return "";
    let half = null;
    const local = periods();
    const tail = /(am|pm|a|p)$/.exec(s);
    if (local.pm && s.endsWith(local.pm)) { half = "pm"; s = s.slice(0, -local.pm.length); }
    else if (local.am && s.endsWith(local.am)) { half = "am"; s = s.slice(0, -local.am.length); }
    else if (tail) { half = tail[1][0] === "p" ? "pm" : "am"; s = s.slice(0, -tail[1].length); }
    const m = s.match(/^(\d{1,2})(?:[^\d]?(\d{2}))?[^\d]?$/);
    if (!m) return "";
    let h = +m[1];
    const mi = +(m[2] || 0);
    if (half) {
      if (h < 1 || h > 12) return "";
      h = (h % 12) + (half === "pm" ? 12 : 0);
    }
    if (h > 23 || mi > 59) return "";
    return String(h).padStart(2, "0") + ":" + String(mi).padStart(2, "0");
  }
  /* The empty field's hint, as the browser's own time field writes it:
   * « --h-- » in French, « --:-- -- » in American English. */
  function patternTime() {
    if (french()) return "--h--";
    return format(CLOCK).formatToParts(new Date(2000, 0, 1, 15, 30))
      .map(function (p) { return p.type === "literal" ? p.value : "--"; }).join("");
  }
  /* Does the page's language count its hours by twelve? Never French
   * (the clock above); otherwise `Intl`'s hour cycle — American English
   * yes, British no. The time picker's panel follows it. */
  function twelve() {
    if (french()) return false;
    const cycle = format(CLOCK).resolvedOptions().hourCycle;
    return cycle === "h11" || cycle === "h12";
  }
  /* The two half days as the language names them, « AM » / « PM ». */
  function halves() {
    return [3, 15].map(function (h) {
      const p = format(CLOCK).formatToParts(new Date(2000, 0, 1, h, 0))
        .find(function (x) { return x.type === "dayPeriod"; });
      return p ? p.value : (h < 12 ? "AM" : "PM");
    });
  }
  $bz.times = { shown: shownTime, typed: typedTime, pattern: patternTime,
                twelve: twelve, halves: halves };

  $bz.dates = {
    iso: iso,
    fromIso: fromIso,
    addDays: addDays,
    addMonths: addMonths,
    weekStartOf: weekStartOf,
    typed: typed,
    typedMonth: typedMonth,
    shown: shown,
    shownMonth: shownMonth,
    shownWeek: shownWeek,
    shownLong: shownLong,
    axis: axis,
    pattern: pattern,
    patternMonth: patternMonth,
    /* A typed date, as the first day of its week — the week picker. The
     * field shows the week as a range (« 02/11/2026 – 08/11/2026 »): its
     * first day is what is read. */
    typedWeek: function (text, weekstart) {
      const day = typed(String(text || "").split(/\s[\u2013\u2014-]\s/)[0]);
      return day ? weekStartOf(day, weekstart) : "";
    },
  };
})();

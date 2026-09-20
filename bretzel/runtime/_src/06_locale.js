/* 06_locale.js — month and weekday names, derived from the language.
 *
 * ⚠️ **The number 06 is an ORDERING CONSTRAINT, not an identity.** This
 * slab was called ``22_locale.js`` until 2026-08-27, so loaded FIFTEEN
 * slabs after its only consumer, ``07_calendar.js``. Yet that one calls
 * ``customElements.define('bz-calendar', …)``, which IMMEDIATELY
 * upgrades every calendar already in the DOM — their constructor then
 * reads ``$bz.locale.weekdayNames()`` on a ``$bz.locale`` that does not
 * exist yet.
 *
 * Measured: **one exception thrown per calendar**, that is 54 on the
 * playground's ``/calendar`` page, 44 on ``/date_picker``, 45 on
 * ``/date_range_picker``, 35 on ``/month_picker``. The screen recovered
 * — the ``bz-text`` directive comes back later — but the flood of errors
 * stopped ``networkidle`` arriving, and ``pytest -m audit`` HUNG on it.
 * An hour-long suite made unusable by a line of ordering.
 *
 * This file depends on nothing (it creates ``window.$bz`` if needed), so
 * it could live anywhere before 07. It is placed JUST before its
 * consumer so that a reader wondering "why here?" finds the answer on
 * the folder's next line.
 *
 * Guarded by ``tests/runtime_js/test_no_page_throws_on_load.py``, which
 * loads the 74 component pages and requires ZERO exception. A STATIC
 * gate (forbidding a read of a ``$bz.<ns>`` set later) was ruled out
 * after measurement: 9 cases in the repository, and all 9 are legitimate
 * — DEFERRED reads, in functions called well after load. What sets the
 * defect apart is the MOMENT of the read, and only a browser separates
 * them.
 *
 * Exposed as window.$bz.locale, read by 07_calendar.js and by the bz-*
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
 *   $bz.locale.weekdayNames()     7 short names, SUNDAY first
 *   $bz.locale.weekdayLongNames() the same in full, for a ``title=``
 *
 * ⚠️ Sunday first, always: it is ``Date.getDay()``'s order, and it is
 * the component that rotates the list according to ``weekstart``. A list
 * written Monday-first — the French reflex — shifts every column by a
 * day (trap [14] of the CRM work).
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

  // 2023-01-01 IS a Sunday, and 2023 has twelve months — the two
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
        weekday: "short",
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
      // The fallback has ONLY abbreviations. ``weekdaysLong`` is
      // therefore the same thing there: a ``title`` identical to the
      // visible text is useless but never wrong, where inventing a full
      // name would be.
      entry = {
        months: FALLBACK_MONTHS,
        weekdays: FALLBACK_WEEKDAYS,
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
})();

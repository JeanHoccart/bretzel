/* 17_carousel.js — the Carousel component's shared scope.
 *
 * The scrolling is **CSS scroll-snap**, not a translateX driven from
 * here: the track is an `overflow-x-auto snap-x snap-mandatory`
 * container and each slide carries `snap-start`. That choice decides
 * this whole file.
 *
 * What the browser does, and what we therefore do not write: the touch
 * swipe with its inertia and its rubber-banding, the wheel scroll, the
 * keyboard, and the snapping itself. Two things are left here — going
 * to an index, and reading the index from the scroll position.
 *
 *   bz-data="{...$bz.carousel.scope, current: 0, _track: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ``_track`` is captured at the root's ``bz-init``
 * (`_track = $refs.bztrack`): a scope method has **no** access to
 * ``$refs``, only directives do (same constraint as Slider, cf. its
 * docstring).
 *
 * ⚠️ **All the geometry is READ from the DOM, never computed.** The
 * stride comes from the real gap between two slides, the bound from
 * ``scrollWidth - clientWidth``. That is what makes a responsive
 * ``per_view`` (`{"base": 1, "md": 3}`) free: the JS has no breakpoint
 * to know, it measures what CSS decided.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The silence after the last scroll event before considering the
  //: position settled. Without that delay, a smooth scroll from 0 to 3
  //: would publish 1 then 2 on the way — and on a server-bound
  //: ``value``, every intermediate value would leave as a ``change``.
  const SETTLE_MS = 120;

  $bz.carousel = {
    scope: {
      // ── Geometry ─────────────────────────────────────────────────
      // METHODS, never getters: ``scope.absorb`` invokes each key at
      // registration and would freeze a getter on its first value (cf.
      // traps.md).
      _step() {
        const t = this._track;
        if (!t || !t.children.length) return 0;
        const a = t.children[0];
        // The gap between TWO slides, not the width of one: it
        // includes the gap, so it stays right whatever the theme's
        // spacing.
        if (t.children.length > 1) {
          return (
            t.children[1].getBoundingClientRect().left -
            a.getBoundingClientRect().left
          );
        }
        return a.getBoundingClientRect().width;
      },
      _maxIndex() {
        // ``void this._geom`` is NOT dead: it is the read that
        // REGISTERS the reactive dependency of everything that
        // measures. A DOM measurement is not a signal — without that
        // link, a ``bz-attr:disabled="_atEnd()"`` evaluates once at scan
        // time, with that instant's layout, and is never re-read. Paid
        // for real: hydrated before the Tailwind sheet applies, the
        // track is not yet ``flex``, so ``scrollWidth === clientWidth``,
        // so the bound is 0, so BOTH arrows are disabled — and
        // ``disabled:opacity-0`` erases them. No arrow at the first
        // visit, all of them on refresh. Cf. ``_observeGeom`` for what
        // moves this signal.
        void this._geom;
        // ``_step()`` already returns 0 with no track, so this test
        // covers both cases — and ``_geomIndex`` just below leans on the
        // same property. Doubling the guard here would suggest the two
        // neighbours disagree.
        const step = this._step();
        if (!step) return 0;
        const t = this._track;
        return Math.max(0, Math.round((t.scrollWidth - t.clientWidth) / step));
      },
      _geomIndex() {
        const step = this._step();
        return step ? Math.round(this._track.scrollLeft / step) : 0;
      },

      // ── What makes the measurement re-evaluable ──────────────────
      // Called from a ``bz-effect`` carried by the TRACK, and most
      // certainly not from the root's ``bz-init``: ``bz-init`` is
      // one-shot per NODE (``el._bzInitDone``), yet idiomorph morphs IN
      // PLACE — the root's node survives, so the hook does not run
      // again, so the slides added by a morph would never be observed. A
      // ``bz-effect`` is thrown away and redone at every rescan, which
      // re-observes the current set with nothing more to write.
      // (``ui.carousel`` + ``ui.each`` inside a refreshed zone is the
      // component's number-one use case: that path is not a corner.)
      //
      // It must NOT join the root's effect, which already depends on
      // ``_geom`` through ``_syncFromValue`` → ``_maxIndex``: the bump
      // of the observer's first report would relaunch it, which would
      // re-wire the observer, which would report again — a loop.
      //
      // Why a ResizeObserver and not a ``window.resize``: the bound
      // moves without the window moving. A responsive ``per_view``
      // changes the SLIDES' width at a breakpoint; a carousel hydrated
      // in a collapsed panel measures zero until it opens; a stylesheet
      // arriving after the scan turns the track from ``block`` to
      // ``flex``. All three show on an observed box, none goes through a
      // window event.
      //
      // ONE slide is observed in addition to the track, and one is
      // enough: they all carry the SAME class string (``slide_class`` is
      // composed once on the Python side then applied to each), so they
      // change size together. The first is a faithful witness of the
      // group; observing the other eighty would bring no extra
      // information.
      _observeGeom() {
        const t = this._track;
        if (!t) return;
        // The observer is filed on the OBSERVED node, not on the scope
        // — the same choice as ``$bz._tick`` with ``el._bzTickId``, and
        // for the same reason: its lifetime is the track's, so a
        // detached track takes its observer with it. On the scope, it
        // would outlive its subject.
        //
        // Filing it there ALSO avoids a loop: this method runs in an
        // effect, and a scope field written from an effect that reads it
        // would call itself endlessly (an undeclared field becomes a
        // signal at the first write — cf. ``03_scope.js``). A node
        // property is not reactive, so nothing relaunches.
        if (t._bzGeomRo) t._bzGeomRo.disconnect();
        const self = this;
        // Bumping a counter rather than publishing the measurement:
        // the measurement stays read at the moment it is needed (a
        // single source), the signal only says "read again". No loop
        // possible — what the effect writes behind it (``disabled``, so
        // an opacity) changes no box.
        const ro = new ResizeObserver(function () {
          self._geom = self._geom + 1;
        });
        ro.observe(t);
        if (t.children[0]) ro.observe(t.children[0]);
        t._bzGeomRo = ro;
      },

      // ── Bounds — the arrows' disabled state ──────────────────────
      // Reading ``_read()`` registers the reactive dependency (it is
      // what moves); the BOUND, for its part, comes from the geometry —
      // so no per_view or breakpoint computation.
      _atStart() {
        return Number(this._read()) <= 0;
      },
      _atEnd() {
        return Number(this._read()) >= this._maxIndex();
      },

      // ── Navigation ───────────────────────────────────────────────
      goTo(i) {
        const t = this._track;
        if (!t) return;
        const n = Math.max(0, Math.min(this._maxIndex(), Number(i) || 0));
        t.scrollTo({ left: n * this._step(), behavior: "smooth" });
        // We do NOT write the state here: ``_onScroll`` is the index's
        // single source, and it will publish it when the position has
        // settled. Writing on both sides would make the signal diverge
        // from what the user sees as soon as they interrupt the
        // animation with a finger.
      },
      // ``next`` / ``prev`` LOOP, and it does not contradict arrows
      // that stop: the arrows are disabled at the edges, so they never
      // arrive here at the end. What arrives here at the end is the
      // autoplay — and a rotation that stops is no longer a rotation.
      next() {
        const max = this._maxIndex();
        const cur = Number(this._read()) || 0;
        this.goTo(cur >= max ? 0 : cur + 1);
      },
      prev() {
        const cur = Number(this._read()) || 0;
        this.goTo(cur <= 0 ? this._maxIndex() : cur - 1);
      },

      // ── The position → state bridge ──────────────────────────────
      _onScroll() {
        clearTimeout(this._settleId);
        this._settleId = setTimeout(() => {
          const i = this._geomIndex();
          if (Number(this._read()) !== i) this._write(i);
        }, SETTLE_MS);
      },

      // ── The state → position bridge ──────────────────────────────
      // Called from the root's ``bz-effect``: reading ``_read()``
      // registers the dependency, so an EXTERNAL writer (a binding
      // driven elsewhere, a `.set(i)`) scrolls the track.
      //
      // The ``!==`` guard is what stops the loop with ``_onScroll``, and
      // it is enough: during a smooth scroll, the published position
      // ends up equalling the target, the effect relaunches, finds no
      // gap any more, and does not call ``scrollTo`` a second time.
      _syncFromValue() {
        const t = this._track;
        if (!t) return;
        const target = Math.max(
          0,
          Math.min(this._maxIndex(), Number(this._read()) || 0)
        );
        if (this._geomIndex() === target) return;
        // The very first snap is INSTANT: a carousel rendered at
        // value=2 must show on slide 2, not scroll from 0 under the
        // user's eyes on load.
        const behavior = this._booted ? "smooth" : "auto";
        this._booted = true;
        t.scrollTo({ left: target * this._step(), behavior: behavior });
      },

      // ── Autoplay ─────────────────────────────────────────────────
      // A single gesture from the user and the rotation stops, for
      // good. No resumption after a delay: a content that starts moving
      // again while you are reading it is the number-one accessibility
      // complaint about carousels. No pause on hover either — it does
      // not exist on a coarse pointer.
      //
      // ``still`` is a SIGNAL declared in the ``bz-data`` (not a field
      // set on the fly): it is the root's effect that reads it, as
      // ``$bz._tick($el, !still, ms)``, and an undeclared field would
      // never relaunch that effect — the autoplay would run forever.
      _touch() {
        if (!this.still) this.still = true;
      },
    },
  };
})();

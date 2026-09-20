/* 20_resizable.js — the shared scope of the Resizable component (split panes).
 *
 * ⚠️ **The repository's third "drag" family, and confusing it costs**:
 *   - `12_slider.js`      = pointer → a VALUE on a scale;
 *   - `19_dnd.js`         = moving a NODE from one position to another;
 *   - here                = pointer → a DIMENSION. Nothing moves,
 *                           nothing changes parent: two neighbours
 *                           re-share the room they already occupy.
 * It is the slider's family (pointer-drag, continuous delta), not the
 * node-DnD's — the roadmap has said so since framing #6, and this file
 * therefore has NO dependency on `19_dnd.js`.
 *
 *   bz-data="{...$bz.resizable.scope, sizes: [30,70], _mins: [10,10],
 *             _vertical: false, _group: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ``_group`` is captured at the root's ``bz-init`` (`_group = $el`): a
 * scope method has no access to ``$el``, only directives do (same
 * constraint and same remedy as Slider and Carousel).
 *
 * ── The split is in WEIGHTS, never in pixels ──────────────────────────
 * Each panel is a ``flex-grow: w`` on a zero basis, so the browser
 * shares the remaining room pro rata to the weights — the handles'
 * width is deducted BEFORE the split, without our knowing it, and a
 * group that shrinks keeps its proportions without our listening to any
 * ``resize``. Pixels enter here in a single place: the conversion of the
 * pointer's delta, measured at every gesture.
 *
 * ── Two neighbours, never more ────────────────────────────────────────
 * Dragging a handle redistributes ONLY the pair it separates: their sum
 * is invariant during the gesture, so the other panels do not move a
 * pixel. It is the behaviour of every real splitter, and it is what
 * makes the gesture predictable — a user widening their left column does
 * not want to see the right one reorganise itself.
 *
 * ── Why nothing is published DURING the gesture ───────────────────────
 * The drag writes the styles live (the fast path, no signal tick); the
 * state is only published on release. Publishing every frame would send
 * one ``change`` per pixel to the server, and would write localStorage a
 * hundred times a second when the ClientState is ``persist="local"``.
 * Same reason as the Carousel's ``SETTLE_MS``.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The step of a keyboard arrow, in percentage points. The ARIA
  //: "window splitter" pattern requires the handle to be drivable
  //: without a pointer — it is the only way to resize from the
  //: keyboard, and it is also the only one that works with no mouse AND
  //: no touch screen.
  const KEY_STEP = 2;

  $bz.resizable = {
    scope: {
      // ── Reading the DOM ──────────────────────────────────────────
      // ``:scope >`` and not a bare querySelectorAll: a Resizable NESTED
      // in a panel (the "editor + preview inside a resizable column" use
      // case) would otherwise see its child's panels as its own.
      _panels() {
        if (!this._group) return [];
        return Array.prototype.slice.call(
          this._group.querySelectorAll(":scope > [data-bz-rz-panel]")
        );
      },
      _px(el) {
        const r = el.getBoundingClientRect();
        return this._vertical ? r.height : r.width;
      },

      // ── State → layout ───────────────────────────────────────────
      // Called from the root's ``bz-effect``: reading ``_read()``
      // registers the dependency, so an EXTERNAL writer (a binding
      // driven elsewhere, a `.set([…])`, a restore from localStorage at
      // boot) re-lays the panels by itself.
      //
      // It is also what makes the anti-FOUC free: the root carries a
      // ``bz-data``, so it stays ``visibility:hidden`` until
      // ``html.bz-ready`` (cf. ``render/shell.py`` § _ANTI_FLASH_STYLE),
      // and the boot hydrates the store from localStorage BEFORE the
      // scan that runs this effect. The remembered sizes are therefore
      // in place at the first painted pixel — no pre-paint script to
      // write.
      _apply() {
        // The panels first, their COUNT then passed to ``_weights``:
        // without that both methods each launch the same
        // ``querySelectorAll``, at every tick of the effect.
        const panels = this._panels();
        const sizes = this._weights(panels.length);
        for (let i = 0; i < panels.length; i++) {
          const w = sizes[i];
          if (w === undefined) continue;
          // An INLINE style and not a class: the value is continuous
          // (a user stops where they want), so no Tailwind class can
          // express it — and an assembled class would not exist in
          // production's compiled CSS.
          panels[i].style.flexGrow = String(w);
        }
        // ``aria-valuenow`` is set back HERE, in the single reactive
        // pass, and not only in the gestures. It is what makes the FOUR
        // write paths correct by construction: pointer, keyboard,
        // `.set()` / `.reset()`, and a binding driven elsewhere. Copied
        // into each gesture, it only covered the first two —
        // `.set([20, 80])` left a screen reader on the first render's
        // value.
        if (this._group) {
          const handles = this._group.querySelectorAll(
            ":scope > [data-bz-rz-handle]"
          );
          for (let i = 0; i < handles.length; i++) {
            this._announce(handles[i], sizes[i]);
          }
        }
      },

      // The weight array **normalised to 100**. A panel added by a
      // morph without ``sizes`` following (a list of panels coming from
      // data) would otherwise get ``undefined``: it falls back to an
      // equal share rather than disappearing.
      //
      // ⚠️ **The normalisation is not cosmetic, and forgetting it here
      // made the component inert.** ``_mins`` travels in PERCENTAGE
      // POINTS; if the weights stay raw, the two scales no longer talk
      // to each other. Measured: ``sizes=[1, 3]`` (a documented writing
      // — it is the RATIO that counts) with ``min_size=15`` gives
      // ``pair = 4``, ``lo = 15``, so ``hi < lo`` at every frame, so a
      // handle that NEVER moves — with no error, nothing in the console.
      // In local mode the defect was invisible because the ``bz-data``
      // seeded by the server is already normalised; it only showed in
      // binding mode, the very one the component puts forward for
      // ``persist="local"``.
      //
      // An EXACT MIRROR of ``normalize_weights`` (``resizable.py``),
      // gated by ``tests/runtime_js/test_resizable_mirrors_python.py``,
      // which runs both halves over the same table.
      //
      // ``count`` is optional: a caller that has ALREADY counted the
      // panels passes it (``_apply``), the others let it be derived.
      // ⚠️ The ``_read()`` call stays the FIRST line: it is what
      // registers the effect's reactive dependency, and moving it after
      // an early return would lose it in silence.
      _weights(count) {
        const raw = this._read();
        const n = count === undefined ? this._panels().length : count;
        if (n <= 0) return [];
        const share = 100 / n;
        const out = [];
        let total = 0;
        for (let i = 0; i < n; i++) {
          const v = Array.isArray(raw) ? Number(raw[i]) : NaN;
          const w = isFinite(v) && v >= 0 ? v : share;
          out.push(w);
          total += w;
        }
        if (total <= 0) return out.map(() => Math.round(share * 100) / 100);
        return out.map((w) => Math.round((w * 100) / total * 100) / 100);
      },

      _min(i) {
        const m = Array.isArray(this._mins) ? Number(this._mins[i]) : 0;
        return isFinite(m) && m > 0 ? m : 0;
      },

      // The CEILING, in percentage points. ``100`` is the neutral value
      // and not a sentinel: a panel that can take all the room is not
      // bounded. Added on 2026-08-23 — ``_min`` lived alone, which was
      // an asymmetry and not a decision.
      _max(i) {
        const m = Array.isArray(this._maxs) ? Number(this._maxs[i]) : 100;
        return isFinite(m) && m > 0 && m <= 100 ? m : 100;
      },

      // ── The gesture ──────────────────────────────────────────────
      // No activation threshold, unlike the node-DnD: a splitter's
      // handle has no competing "click" to preserve (it does nothing
      // else), and it is already a dedicated target. The DnD's threshold
      // exists so that clicking a CARD stays a click; here it would
      // protect nothing and would add latency to the first pixel.
      _start(e, i) {
        const panels = this._panels();
        const a = panels[i];
        const b = panels[i + 1];
        if (!a || !b) return;
        const totalPx = panels.reduce((s, p) => s + this._px(p), 0);
        if (!totalPx) return;
        const weights = this._weights(panels.length);
        this._drag = {
          i: i,
          from: this._vertical ? e.clientY : e.clientX,
          // The px → weight factor is frozen at the START of the
          // gesture, and it is deliberate: the sum of the weights does
          // not move while you drag (we only redistribute it), so the
          // ratio stays right until release.
          factor: weights.reduce((s, w) => s + w, 0) / totalPx,
          // The left panel's weight at the START of the gesture: it is
          // the base the delta adds to, so it must not follow the
          // intermediate values (otherwise the movement accumulates and
          // the pointer "slides" under the handle). The right weight is
          // derived from the pair — no need to remember it.
          a: weights[i],
          sizes: weights,
          // Both panels and the handle are HELD here, not re-searched
          // at every frame: ``_move`` runs at the pointer's cadence, and
          // none of this can change during a gesture. Without that
          // capture, each frame relaunched TWO ``querySelectorAll`` (the
          // panels, then the handles for ``aria-valuenow``) to reach
          // three known nodes.
          aEl: a,
          bEl: b,
          handle: e.currentTarget,
        };
        // Capture on the HANDLE: the cursor leaves its box at the very
        // first pixel (it is a few points wide), and with no capture the
        // gesture would stop there.
        $bz.helpers.capturePointer(e.currentTarget, e);
      },

      // Distribute ``want`` over the pair ``i`` / ``i+1``, in place,
      // respecting both minimums. Returns ``false`` when the pair is
      // FROZEN — the case where the two minimums do not fit inside it
      // (60 + 60 in 100): we prefer to move nothing rather than violate
      // one of them on the grounds that the other requires it too.
      //
      // A single copy for the pointer AND the keyboard: it is the same
      // arithmetic, only ``want``'s origin differs (a pointer delta, or
      // an arrow step). Written twice, it would have been fixed one time
      // in two.
      _pair(sizes, i, want) {
        const pair = sizes[i] + sizes[i + 1];
        // The four constraints cross: the LEFT floor and the RIGHT
        // ceiling push the handle the same way (to the right), the other
        // two the other way. Hence the ``max`` on the floors and the
        // ``min`` on the ceilings, expressed in the same unit — the left
        // panel's size.
        const lo = Math.max(this._min(i), pair - this._max(i + 1));
        const hi = Math.min(pair - this._min(i + 1), this._max(i));
        // A FROZEN pair: the constraints do not hold together (60 + 60
        // in 100, or a ceiling under a floor). We prefer to move nothing
        // rather than violate one on the grounds that another requires
        // it.
        if (hi < lo) return false;
        sizes[i] = Math.max(lo, Math.min(hi, want));
        sizes[i + 1] = pair - sizes[i];
        return true;
      },

      // Publish: it is here, and only here, that the state leaves the
      // gesture. Rounding to two decimals avoids persisting
      // seventeen-digit floats in localStorage.
      _publish(sizes) {
        this._write(sizes.map((w) => Math.round(w * 100) / 100));
      },

      _move(e) {
        const d = this._drag;
        if (!d) return;
        const delta =
          ((this._vertical ? e.clientY : e.clientX) - d.from) * d.factor;
        if (!this._pair(d.sizes, d.i, d.a + delta)) return;
        // A DIRECT write, not going through the state: see the file's
        // header. Publication happens once, on release.
        d.aEl.style.flexGrow = String(d.sizes[d.i]);
        d.bEl.style.flexGrow = String(d.sizes[d.i + 1]);
        this._announce(d.handle, d.sizes[d.i]);
      },

      _end(e) {
        const d = this._drag;
        this._drag = null;
        if (!d) return;
        $bz.helpers.releasePointer(d.handle, e);
        this._publish(d.sizes);
      },

      // ── a11y ─────────────────────────────────────────────────────
      // ``aria-valuenow`` says "the panel before me occupies N %". The
      // server renders it only once, statically — the handle is not a
      // component, it has no reactive prop to bind — so it is the JS
      // that keeps it up to date.
      //
      // **A single author for the published state**: ``_apply``, the
      // reactive pass. Everything that writes the state goes back
      // through it, so the four paths are covered without any of them
      // having to think about it. ``_move`` calls it IN ADDITION, and
      // only because it is the only one that publishes nothing before
      // release — without that a screen reader would announce the
      // previous value for the whole duration of the drag.
      _announce(handle, value) {
        if (handle && value !== undefined) {
          handle.setAttribute("aria-valuenow", String(Math.round(value)));
        }
      },

      // ── Collapsing ───────────────────────────────────────────────
      // Put panel ``i`` away by giving its place to ``j``, its opposite
      // neighbour. Replaying the gesture restores it.
      //
      // ⚠️ **Collapsing OVERRIDES ``min_size``, and that is the point.**
      // It therefore does NOT go through ``_pair``, which exists to stop
      // a minimum being crossed by DRAGGING. The minimum says "do not
      // shrink me by accident"; collapsing is an explicit gesture that
      // says "put it away". Without that way out, ``min_size=20`` would
      // make a collapsible panel non-collapsible, and a second
      // vocabulary would be needed to say the same thing. VS Code and
      // shadcn do the same.
      //
      // ``_folded`` remembers the previous size, by index. It lives in
      // the scope — so it survives a morph, like the rest of the
      // component's state — and not on the server, which has no idea
      // what somebody put away three seconds ago.
      _fold(i, j) {
        const sizes = this._weights();
        if (sizes[i] === undefined || sizes[j] === undefined) return;
        const memo = this._folded || (this._folded = {});
        const back = memo[i];
        const pair = sizes[i] + sizes[j];

        if (back !== undefined) {
          // Restore. The neighbour keeps its own floor: giving the
          // stored panel back more than the pair contains would crush
          // it.
          const want = Math.min(back, Math.max(0, pair - this._min(j)));
          sizes[i] = want;
          sizes[j] = pair - want;
          delete memo[i];
        } else if (sizes[i] <= 0.01) {
          // Collapsed WITH NO memory: the case of a split restored
          // from localStorage, where a panel was at zero before the F5.
          // Without that branch, double-clicking would do nothing at all
          // — the panel would stay put away forever. It comes back to
          // its floor, or to an equal share if it has none.
          const want = Math.min(
            this._min(i) || 100 / Math.max(1, this._panels().length),
            Math.max(0, pair - this._min(j))
          );
          sizes[i] = want;
          sizes[j] = pair - want;
        } else {
          memo[i] = sizes[i];
          sizes[j] = pair;
          sizes[i] = 0;
        }
        this._publish(sizes);
      },

      // ── Keyboard ─────────────────────────────────────────────────
      // The handle is a focusable ``role="separator"``: the arrows move
      // it, like a slider. The step is in percentage points, so
      // independent of the group's width.
      _key(e, i, fold) {
        const key = e.key;
        // ``Enter`` collapses, when the handle touches a collapsible
        // panel. It is the double-click's keyboard twin, and the ARIA
        // "window splitter" pattern prescribes it: a focusable handle
        // whose only collapse command were a mouse gesture has no
        // collapse at all for whoever has no mouse.
        if (key === "Enter" && Array.isArray(fold)) {
          e.preventDefault();
          this._fold(fold[0], fold[1]);
          return;
        }
        const back = this._vertical ? "ArrowUp" : "ArrowLeft";
        const fwd = this._vertical ? "ArrowDown" : "ArrowRight";
        if (key !== back && key !== fwd) return;
        e.preventDefault();
        const sizes = this._weights();
        const step = key === back ? -KEY_STEP : KEY_STEP;
        // No ``_announce`` here: ``_publish`` relaunches ``_apply``,
        // which sets every ``aria-valuenow`` back. Calling it IN
        // ADDITION would give the same value two authors.
        if (this._pair(sizes, i, sizes[i] + step)) this._publish(sizes);
      },

      // ── Imperative ───────────────────────────────────────────────
      set(v) {
        if (Array.isArray(v)) this._write(v);
      },
      // Back to the equal split. A method and not a "re-set of the
      // initial sizes": the server renders the component only once, so
      // "initial" has no stable meaning once the user has dragged a
      // handle — whereas "in equal shares" is true at any moment.
      reset() {
        const n = this._panels().length;
        if (!n) return;
        this._write(new Array(n).fill(Math.round((100 / n) * 100) / 100));
      },
    },
  };
})();

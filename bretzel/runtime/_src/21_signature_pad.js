/* 21_signature_pad.js — the SignaturePad component's shared scope.
 *
 * **The repository's first and only `<canvas>`** (checked: zero other
 * occurrence, the charts are SVG). Everything that follows comes from
 * two properties of the canvas the rest of the framework never had to
 * deal with: it has no intrinsic size, and **resizing it clears it**.
 *
 * ── The third member of the pointer-drag family ───────────────────────
 *   - `12_slider.js`      = pointer → a VALUE on a scale;
 *   - `20_resizable.js`   = pointer → a DIMENSION;
 *   - here                = pointer → a STROKE.
 * Nothing to do with `19_dnd.js`'s node-DnD. The pointer capture goes
 * through `$bz.helpers.capturePointer`, extracted on 2026-08-13 while
 * shipping `resizable` — this file is its first new caller.
 *
 *   bz-data="{...$bz.signaturePad.scope, value: '', _canvas: null,
 *             _strokes: [], _drawing: null, _base: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ── Why we keep the POINTS, when there is no undo ─────────────────────
 * It is not to undo — the API only exposes `.clear()`, a signature is
 * redone and not touched up. It is because a canvas **loses its content
 * at every size change**, and a pad in a responsive form really does
 * change: a phone you turn, a panel you open, a `resizable` you drag.
 * Without the points, the signature disappears on rotation. The
 * alternative — reading the bitmap back and redrawing it to scale —
 * degrades at every pass.
 *
 * ── The value is EMPTY as long as nothing is drawn ────────────────────
 * A fresh canvas returns a perfectly valid PNG: a white rectangle.
 * Publishing it would pass "not signed yet" off as "signed", on the
 * server side, with nothing looking wrong. Zero strokes ⇒ empty string.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  //: The stroke's thickness, in CSS pixels. A constant and not a prop:
  //: a signature has only one weight that works, and making it settable
  //: would add no power (memory `project_api_opinionation_thesis`).
  const LINE_WIDTH = 2;

  $bz.signaturePad = {
    scope: {
      // ── The canvas and its size ──────────────────────────────────
      // ⚠️ Resizing a canvas CLEARS it, and giving it a size in CSS
      // pixels is not enough: without the density factor, the stroke is
      // blurry on every retina screen — that is to say on every phone,
      // this repository's test environment.
      _resize() {
        const c = this._canvas;
        if (!c) return;
        const box = c.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const dpr = window.devicePixelRatio || 1;
        const w = Math.round(box.width * dpr);
        const h = Math.round(box.height * dpr);
        // Do nothing when nothing has moved: a write to
        // ``canvas.width`` clears the content EVEN if the value is
        // identical. The observer reports at the first wiring, so
        // without that guard the pad would clear at every rescan.
        if (c.width === w && c.height === h) return;
        c.width = w;
        c.height = h;
        const ctx = c.getContext("2d");
        ctx.scale(dpr, dpr);
        this._redraw();
      },

      // Re-wire the observer at every rescan rather than at the
      // ``bz-init``, and file it on the NODE: ``bz-init`` is one-shot
      // per node and idiomorph morphs in place, so an observer installed
      // there would never see a replaced canvas again. Same choice, same
      // reason as the Carousel's ``_observeGeom``.
      _observe() {
        const c = this._canvas;
        if (!c) return;
        if (c._bzPadRo) c._bzPadRo.disconnect();
        const self = this;
        const ro = new ResizeObserver(function () {
          self._resize();
        });
        ro.observe(c);
        c._bzPadRo = ro;
        this._resize();
        this._hydrate();
      },

      // ── The signature ALREADY THERE ──────────────────────────────
      // A reopened record returns its data URL at SSR. Without that
      // load, the frame showed EMPTY — and with no prompt, since the
      // server had already set ``data-empty="false"``. The component
      // therefore announced "there is a signature" while showing none.
      //
      // The loaded image becomes a BACKGROUND LAYER, distinct from the
      // points: ``_redraw`` paints it first, the strokes over it. It is
      // what makes it survive a resize like the rest — without that it
      // would disappear at the first size change, along with the canvas
      // we clear in order to resize it.
      //
      // Once per NODE only (``_bzHydrated``), and not in a reactive
      // effect: ``_publish`` writes into the same state, so an effect
      // that reads it would reload itself at every stroke. After the
      // boot, it is the canvas that is authoritative. A node property
      // and not a scope field, for the same reason as ``_bzPadRo`` — a
      // lifetime that is the canvas's.
      _hydrate() {
        const c = this._canvas;
        if (!c || c._bzHydrated) return;
        c._bzHydrated = true;
        const src = this._read();
        if (!src) return;
        const img = new Image();
        const self = this;
        img.onload = function () {
          self._base = img;
          self._redraw();
          self._empty(false);
        };
        img.src = src;
      },

      // ── The stroke ───────────────────────────────────────────────
      // The ink is READ on the element (the computed ``color``), never
      // configured: the theme decides, and the value follows dark mode
      // by itself. A ``pen_color`` prop would have frozen a colour that
      // becomes invisible on the other background.
      _ink() {
        return getComputedStyle(this._canvas).color || "#000";
      },
      _redraw() {
        const c = this._canvas;
        if (!c) return;
        const ctx = c.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        const w = c.width / dpr;
        const h = c.height / dpr;
        ctx.clearRect(0, 0, w, h);
        // The signature already there, under the new strokes. Stretched
        // to the current box: a raster image has no other option, and
        // the original frame is not known — it is the same compromise
        // as any resized raster render.
        if (this._base) {
          try {
            ctx.drawImage(this._base, 0, 0, w, h);
          } catch (err) {
            /* a broken / cross-origin image: we keep the strokes */
          }
        }
        ctx.lineWidth = LINE_WIDTH;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = this._ink();
        for (const stroke of this._strokes) {
          if (stroke.length < 2) {
            // A lone point: a tap with no movement must leave a mark,
            // otherwise signing with a dot produces nothing.
            if (stroke.length === 1) {
              ctx.beginPath();
              ctx.arc(
                stroke[0][0], stroke[0][1], LINE_WIDTH / 2, 0, Math.PI * 2
              );
              ctx.fillStyle = this._ink();
              ctx.fill();
            }
            continue;
          }
          ctx.beginPath();
          ctx.moveTo(stroke[0][0], stroke[0][1]);
          for (let i = 1; i < stroke.length; i++) {
            ctx.lineTo(stroke[i][0], stroke[i][1]);
          }
          ctx.stroke();
        }
      },

      _at(e) {
        const r = this._canvas.getBoundingClientRect();
        return [e.clientX - r.left, e.clientY - r.top];
      },

      _start(e) {
        if (this._locked()) return;
        // Stops the browser reading the gesture as a text selection or
        // a scroll. ``touch-none`` on the canvas covers the scroll; this
        // covers the rest.
        e.preventDefault();
        $bz.helpers.capturePointer(this._canvas, e);
        this._drawing = [this._at(e)];
        this._strokes.push(this._drawing);
        this._redraw();
        this._empty(false);
      },

      _draw(e) {
        if (!this._drawing) return;
        this._drawing.push(this._at(e));
        this._redraw();
      },

      _end(e) {
        if (!this._drawing) return;
        $bz.helpers.releasePointer(this._canvas, e);
        this._drawing = null;
        // Publish when the pen LIFTS, not at every point: a PNG is
        // tens of kilobytes, and emitting it per frame would send as
        // many POSTs if an ``on_change`` is wired. Same rule as the
        // Resizable's handle release.
        this._publish();
      },

      // ── The value ────────────────────────────────────────────────
      // Written into the STATE (``_write``), not onto the carrier: it is
      // the carrier's ``bz-attr:value`` that reports it into the DOM,
      // and its ``bz-effect`` that draws the ``change`` from it. A
      // single author, the same mechanics as Slider / Carousel /
      // Resizable — writing both would make the form field diverge from
      // the state as soon as an external writer goes through the
      // second.
      _publish() {
        // ``_base`` counts as much as the strokes: a reopened record
        // then submitted without being touched must not ERASE the
        // signature it carried.
        const inked = this._strokes.length || this._base;
        this._write(inked ? this._canvas.toDataURL("image/png") : "");
      },

      // The marker the theme reads to show / hide the prompt. An
      // attribute and not a class: ``data-[empty=true]:`` is the
      // Tailwind variant the rest of the repository uses for JS-driven
      // states.
      _empty(value) {
        if (this._canvas && this._canvas.parentElement) {
          this._canvas.parentElement.setAttribute(
            "data-empty", value ? "true" : "false"
          );
        }
      },

      _locked() {
        return !!(
          this._canvas && this._canvas.hasAttribute("data-bz-pad-locked")
        );
      },

      // ── Imperative ───────────────────────────────────────────────
      // ``.clear()`` and nothing else: a signature is redone, it is not
      // touched up. The points kept in memory serve the resize (cf. the
      // header), not an undo.
      clear() {
        this._strokes.length = 0;
        // The background layer goes WITH the strokes: "clear" means an
        // empty frame, not "go back to the previous signature".
        this._base = null;
        this._drawing = null;
        this._redraw();
        this._empty(true);
        this._publish();
      },
    },
  };
})();

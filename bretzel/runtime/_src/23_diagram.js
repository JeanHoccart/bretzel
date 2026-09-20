/* 23_diagram.js — the highlighting of neighbours, in `ui.diagram`.
 *
 * The graph is LAID OUT on the server: positions, layers, paths, it all
 * arrives computed. This file lays out nothing. It does one thing, and
 * it is purely local: when you designate a node, everything that is not
 * connected dims.
 *
 * Why it cannot be a round trip
 * ------------------------------
 * Lighting up does not change WHICH nodes exist, only which are in the
 * foreground. Going through the server for that would cost a request and
 * a morph per designation, for a result the browser already knows: the
 * adjacency is baked into the DOM at render.
 *
 * What the server does keep is the NARROWING (`focus=`) — there the
 * drawn nodes change, so the layout changes, so it has to re-render. The
 * two gestures look alike on screen and do not have the same cost; that
 * is the only reason they are separate.
 *
 * Why a slab rather than an expression per node
 * ----------------------------------------------
 * Same reason as 16_accordion: serialising these method bodies into
 * every node's `bz-data` would be 120 bytes × N. Here only the ADJACENCY
 * travels — an array of keys per node, the only thing that really
 * differs from one node to the next.
 *
 * ⚠️ METHODS, never getters: `scope.absorb` invokes each key at
 * registration and would freeze a getter on its first value (cf.
 * traps.md).
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  $bz.diagram = {
    scope: {
      /* The selection — READ AND WRITTEN by `_read` / `_write`.
       *
       * These two carry the indirection: the same methods serve the
       * local `value` field (no binding) and the store cell (a `value=`
       * bound to a `ClientState`). It is `tree`'s and `toggle_group`'s
       * idiom — without it, every method would have to test which mode
       * it is running in.
       *
       * No getter: `scope.absorb` invokes each key once at registration
       * and would freeze it on its first value.
       */
      _read() {
        return this.value;
      },
      _write(v) {
        this.value = v;
      },

      /* Designate `key`, whose neighbours `adj` lists (itself
       * included).
       *
       * Re-clicking the already designated node switches off. It is the
       * only way out from the keyboard and the finger — without it you
       * stay lit with no way of knowing how to come back, and there is
       * no hover to get out of it on a touch screen. */
      light(key) {
        this._write(
          String(this._read() || "") === String(key) ? "" : String(key)
        );
      },

      /* Must this node stay in the foreground?
       *
       * DERIVED from the selection, never stored. The first version kept
       * a `lit` array that `light()` filled — and that array did not
       * move when the selection changed from OUTSIDE (a `select` bound
       * to the same `ClientState`, a `state.node.set(...)`). The store
       * followed, the screen did not: measured at `dim = 0` where a
       * click gave 3.
       *
       * `adj` is the node's adjacency, baked by the server into its
       * `bz-class`. So we test "is the selected one MY neighbour" rather
       * than the other way round — it is the same predicate, and it
       * requires no state.
       */
      isLit(key, adj) {
        const sel = String(this._read() || "");
        if (!sel) return true;
        if (sel === String(key)) return true;
        return (adj || []).indexOf(sel) !== -1;
      },

      /* Tout rallumer. */
      reset() {
        this._write("");
      },

      /* Arm the click-outside-the-diagram, once only.
       *
       * Designating a node is a reading gesture: you must be able to get
       * out of it by clicking anywhere, not only by finding the node you
       * had designated. Without that you stay lit, and on a touch screen
       * there is not even a hover to suspect it.
       *
       * `$bz.helpers.clickOutside` rather than a home-made listener: it
       * is the one the overlays use, it is in the CAPTURE phase (so an
       * inner `stopPropagation` does not smother it) and it returns its
       * unsubscribe.
       *
       * Idempotent: `bz-effect` is re-evaluated after every morph, and
       * without the flag we would stack one listener per refresh.
       */
      arm(el) {
        if (!el || el._bzDiagramOff) return;
        const scope = this;
        el._bzDiagramOff = $bz.helpers.clickOutside(el, function () {
          scope.reset();
        });
      },

      /* An edge stays in the foreground if it TOUCHES the designated
       * node.
       *
       * "Incident", and not "both its ends are lit": two neighbours of
       * one node are both in the foreground, but the edge linking them
       * to each other says nothing about what was designated. Keeping it
       * lit filled the screen with what we were precisely trying to
       * remove. */
      isEdgeLit(a, b) {
        const sel = String(this._read() || "");
        return !sel || sel === a || sel === b;
      },
    },
  };
})();

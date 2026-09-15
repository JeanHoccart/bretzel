/* 09_notification.js — toast stack manager (bz-data scope factory). */
// ════════════════════════════════════════════════════════════════════════
// 09 NOTIFICATION — toast stack data manager.
//
// The user calls ``ui.notification("Saved!")`` from a handler ; the
// server rides the payload back in a ``<bz-patch>{"patches":
// {"_notifications":[…]}}`` block, the bridge forwards each to
// ``$bz.notify`` (→ a ``bz:notify`` DOM event), and the toaster
// container (pre-rendered in the shell) catches it and pushes the
// toast into its own ``bz-data`` scope.
//
// V3 vs V2 : no ``Alpine.store`` — the toaster owns its state in a
// bz-data scope (``stacks``, one bucket per position). The factory
// here builds that scope. Reassignment (not in-place push/splice) so
// the ``bz-for`` over each bucket re-renders (V3 signals are
// identity-compared). Enter animation is a CSS keyframe fired on mount ;
// leave is a two-phase dismiss (flip ``_leaving`` → wait ``LEAVE_MS`` →
// splice) so the ``bz-toast-leave`` keyframe can play before removal.
//
// Variant / icon / position normalisation reads the theme blob the
// shell injects on ``window.$bz_theme.notification``.
// ════════════════════════════════════════════════════════════════════════

(function () {
  "use strict";
  const $bz = window.$bz;
  if (!$bz) return;

  // Mirrors the ``bz-toast-out`` duration in the shell keyframes
  // (``_NOTIFICATION_ANIM_STYLE``). Keep them in sync.
  const LEAVE_MS = 200;

  // Shared with the bz-for FLIP reflow — see 06_helpers.js.
  const prefersReducedMotion = $bz.helpers.prefersReducedMotion;

  function genId() {
    return "bz-toast-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  }

  function makeScope() {
    const THEME = (window.$bz_theme && window.$bz_theme.notification) || {};
    const positions = Object.keys(THEME.positions || { "top-right": 1 });
    const variants = Object.keys(THEME.variants || { info: 1 });
    const icons = THEME.icons || {};

    function emptyStacks() {
      const out = {};
      for (const p of positions) out[p] = [];
      return out;
    }

    function normalise(opts) {
      opts = opts || {};
      const variant = variants.indexOf(opts.variant) >= 0 ? opts.variant : "info";
      let icon;
      if (opts.icon === "" || opts.icon === false) icon = null;
      else if (typeof opts.icon === "string" && opts.icon) icon = opts.icon;
      else icon = icons[variant] || null;
      return {
        id: opts.id || genId(),
        message: String(opts.message || ""),
        title: opts.title || null,
        variant: variant,
        position: positions.indexOf(opts.position) >= 0 ? opts.position : "top-right",
        duration_ms: typeof opts.duration_ms === "number" ? opts.duration_ms : 4000,
        dismissible: opts.dismissible !== false,
        icon: icon,
      };
    }

    return {
      stacks: emptyStacks(),

      show(opts) {
        const toast = normalise(opts);
        const pos = toast.position;
        const next = Object.assign({}, this.stacks);
        next[pos] = next[pos].concat([toast]);
        this.stacks = next;
        if (toast.duration_ms > 0) {
          const self = this;
          setTimeout(function () {
            self.dismiss(toast.id);
          }, toast.duration_ms);
        }
        return toast.id;
      },

      dismiss(id) {
        // No animation wanted : drop it now, skip the leave dance.
        if (prefersReducedMotion()) {
          this._remove(id);
          return;
        }
        // Phase 1 — mark the toast leaving so the ``bz-toast-leave``
        // keyframe plays (``bz-class`` reacts to ``_leaving``). Reassign a
        // fresh object under the same ``id`` so the keyed ``bz-for`` updates
        // the existing node in place instead of remounting it. Guard against
        // a double dismiss (manual click + auto-timeout) so we never restart
        // the animation or schedule a second removal.
        let found = false;
        const next = {};
        for (const p of Object.keys(this.stacks)) {
          next[p] = this.stacks[p].map(function (t) {
            if (t.id === id && !t._leaving) {
              found = true;
              return Object.assign({}, t, { _leaving: true });
            }
            return t;
          });
        }
        if (!found) return;
        this.stacks = next;
        // Phase 2 — actually splice once the leave animation has played.
        const self = this;
        setTimeout(function () {
          self._remove(id);
        }, LEAVE_MS);
      },

      _remove(id) {
        const next = {};
        let changed = false;
        for (const p of Object.keys(this.stacks)) {
          const before = this.stacks[p];
          next[p] = before.filter(function (t) {
            return t.id !== id;
          });
          if (next[p].length !== before.length) changed = true;
        }
        if (changed) this.stacks = next;
      },
    };
  }

  $bz.notification = { makeScope: makeScope };
})();

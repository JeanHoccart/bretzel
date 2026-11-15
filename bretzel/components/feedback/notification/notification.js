/* notification.js — toast stack manager (bz-data scope factory). */
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
// leave is a two-phase dismiss: flag ``_leaving`` (the ``bz-toast-leave``
// keyframe fades it in ``leave_ms``, the pointer already passes through),
// then splice. A toast floats over the page: it goes the way a dialog
// goes (rule 5 of the motion rule, ``components.md`` § motion).
// The neighbours glide into the freed slot (``:flip``).
//
// Variant / icon / position normalisation reads the theme blob the
// shell injects on ``window.$bz_theme.notification``.
// ════════════════════════════════════════════════════════════════════════

(function () {
  "use strict";
  const $bz = window.$bz;
  if (!$bz) return;


  function genId() {
    return "bz-toast-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
  }

  function makeScope() {
    const THEME = (window.$bz_theme && window.$bz_theme.notification) || {};
    const positions = Object.keys(THEME.positions || { "top-right": 1 });
    const variants = Object.keys(THEME.variants || { info: 1 });
    const icons = THEME.icons || {};
    // The fade-out of ``bz-toast-out``, from the same Python constant.
    const leaveMs = THEME.leave_ms || 0;

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
        // "Reduce motion": no fade to wait for, it goes at once.
        if ($bz.helpers.prefersReducedMotion()) {
          this._remove(id);
          return;
        }
        // Phase 1: flag it leaving, under the same ``id`` so the keyed
        // ``bz-for`` updates the node in place. A double dismiss (click +
        // auto-timeout) finds it already leaving and does nothing.
        let found = false;
        const next = {};
        for (const p of Object.keys(this.stacks)) {
          next[p] = this.stacks[p].map(function (t) {
            if (t.id !== id || t._leaving) return t;
            found = true;
            return Object.assign({}, t, { _leaving: true });
          });
        }
        if (!found) return;
        this.stacks = next;
        // Phase 2: splice once the fade has played.
        const self = this;
        setTimeout(function () {
          self._remove(id);
        }, leaveMs);
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

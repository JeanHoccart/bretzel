/* 22_verbs.js — the CLIENT half of `bretzel.runtime.verbs`.
 *
 * A verb is a BROWSER action triggered from an `on_*=`:
 *
 *     ui.button("Copy", on_click=bretzel.copy(state.api_key))
 *
 * It plugs into the slot that already accepts a client-source STRING —
 * the same as `dialog.open()` — so it adds no plumbing: no request, no
 * directive, no scope.
 *
 * Only `copy` needs this file. `print` and `fullscreen` fit in an
 * expression Python writes out in full; putting them here would have
 * added an indirection with nothing common kept.
 *
 * ⚠️ Why `copy` is NOT a bare `navigator.clipboard.writeText`
 * ---------------------------------------------------------------------
 * The Clipboard API requires a **secure context**. `https://` and
 * `http://localhost` are; `http://192.168.1.20:8000` is NOT. Yet that is
 * very exactly how an internal tool is used — the audience Bretzel aims
 * at. On that path `navigator.clipboard` is `undefined`, and a bare call
 * would raise a TypeError: the button would do nothing, without a word.
 *
 * Hence the fallback on `document.execCommand('copy')`. It is deprecated
 * and it works everywhere, including outside a secure context — it is
 * the only path that exists over there, so "deprecated" is not an
 * argument against it, it is an argument for not using it first.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  /* The fallback outside a secure context.
   *
   * The `<textarea>` is placed off screen rather than `display:none`: an
   * unrendered element is not selectable, so the copy would fail
   * silently. `readOnly` stops the virtual keyboard opening on mobile,
   * and `position:fixed` avoids scrolling the page to a field nobody
   * should see.
   */
  function viaTextarea(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0";
    document.body.appendChild(ta);
    const selection = document.getSelection();
    const previous = selection && selection.rangeCount > 0
      ? selection.getRangeAt(0) : null;
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    // Give the user's selection back: `select()` overwrote it, and
    // losing your highlight because something else was copied shows.
    if (previous && selection) {
      selection.removeAllRanges();
      selection.addRange(previous);
    }
    return ok;
  }

  $bz.verbs = {
    /* Share — the native sheet, or the clipboard.
     *
     * ⚠️ `navigator.share` is **undefined** on desktop Chromium
     * (measured on 2026-09-02: `typeof navigator.share === "undefined"`).
     * Its absence is therefore not an edge case, it is the NORMAL case
     * on the machine where Bretzel's users develop.
     *
     * Doing nothing in there would give an inert "Share" button to the
     * majority — exactly what this repository refuses elsewhere (cf. the
     * refusal of `tracks=` on `ui.audio`, which would have promised
     * subtitles and delivered an attribute). The fallback therefore
     * COPIES the URL: the button always does something useful, and it is
     * a contract, not an accident.
     */
    share(data) {
      const charge = data || {};
      if (!charge.url) charge.url = window.location.href;
      if (navigator.share) {
        // A refusal by the user (they close the sheet) rejects the
        // promise. It is not an app error: we do NOT fall back on the
        // copy, otherwise cancelling a share would copy behind their
        // back.
        return navigator.share(charge).then(
          function () { return "shared"; },
          function () { return "cancelled"; }
        );
      }
      return $bz.verbs.copy(charge.url).then(function (ok) {
        return ok ? "copied" : "failed";
      });
    },

    /* Vibrate. `navigator.vibrate` EXISTS everywhere (measured:
     * `function` on desktop Chromium) and does nothing with no hardware
     * — so there is no absence to handle, unlike `share`.
     */
    vibrate(motif) {
      return navigator.vibrate ? navigator.vibrate(motif) : false;
    },

    /* Copy `value` to the clipboard. Returns a promise of a boolean —
     * never an exception: a verb is called from an `on_*=`, where nobody
     * catches anything, so a rejection would surface as an
     * `unhandledrejection` in the app's console.
     */
    copy(value) {
      const text = value === null || value === undefined ? "" : String(value);
      if (window.isSecureContext && navigator.clipboard) {
        return navigator.clipboard.writeText(text).then(
          function () { return true; },
          // A refusal stays possible IN a secure context (permission
          // revoked, document without focus). The fallback is then the
          // last chance, not a dead path.
          function () { return viaTextarea(text); }
        );
      }
      return Promise.resolve(viaTextarea(text));
    },
  };
})();

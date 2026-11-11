/* message_input.js — what ``ui.message_input`` does in the browser.
 *
 * Document-level listeners, not a scope per box: a box swapped in by a
 * morph needs nothing re-wired. Every listener looks for the box it
 * concerns (``[data-bz-message-input]``, a ``<form>``) and does nothing
 * elsewhere. The behaviours follow those of chat libraries and their
 * tests (assistant-ui, Vercel AI Elements, Ant Design X, Streamlit,
 * Gradio, chatscope, Stream):
 *
 * - **Enter sends, Shift+Enter breaks the line** — never during an IME
 *   composition, nor on the Enter that ends one (Safari fires it after
 *   ``compositionend``, as keyCode 229). On a touch screen Enter breaks the
 *   line (the round button sends), as assistant-ui does. Sending is the
 *   form's own ``requestSubmit``: no request is built here.
 * - **Never empty, never twice.** A submit with neither text nor file, one
 *   while an answer is written (the round button hidden or absent), or one
 *   while the box's request is still in flight, is stopped before htmx
 *   sees it (capture phase). A box with no server action never leaves
 *   natively either — the browser would reload the page.
 * - **Emptied at once, given back on failure.** As the request leaves
 *   (``htmx:beforeSend``: the values are already taken), the text and the
 *   files go — what is typed while the server answers is kept — and come
 *   back if the request fails, unless something new was typed meanwhile.
 * - **Focus** returns to the text after a send by the round button.
 * - **Escape stops** the answer being written (the « Arrêter » button).
 * - **Backspace on an empty text** removes the last file joined.
 * - **The counter** of ``max_length`` follows what is typed.
 * - **The microphone** — the browser's dictation (Web Speech API), in the
 *   page's language, appended to what is written; ``data-listening`` while
 *   it listens. The page says the browser can dictate
 *   (``html[data-bz-can-dictate]``), so a morph re-rendering it changes
 *   nothing.
 * - **Files dropped on the box** join, as the clip's picker would; a box
 *   switched off, or taking no file, lets nothing through — and never lets
 *   the browser open the dropped file instead of the page.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});
  const BOX = "[data-bz-message-input]";
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const touch = window.matchMedia("(pointer: coarse)");
  const drafts = new WeakMap(); // form → {text, files} while its request is out
  let listening = null; // {rec, button}

  if (Recognition) document.documentElement.setAttribute("data-bz-can-dictate", "");

  function field(form) { return form.querySelector("[data-bz-message-field]"); }
  // The file picker's scope — its ``clear()``, ``handleFiles()``, ``files``.
  function uploader(form) {
    const el = form.querySelector(".bz-file-upload");
    return el && $bz._scopeFor ? $bz._scopeFor(el).proxy : null;
  }
  function off(form) { return form.matches("[data-disabled]"); }

  function busy(form) {
    const send = form.querySelector("[data-bz-message-send]");
    return !send || send.disabled || send.offsetParent === null;
  }

  function empty(form) {
    const text = field(form);
    const files = form.querySelector("input[type=file]");
    return !(text && text.value.trim()) && !(files && files.files && files.files.length);
  }

  function write(text, value) {
    text.value = value;
    text.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function count(form) {
    const text = field(form);
    const counter = form.querySelector("[data-bz-message-count]");
    if (text && counter) counter.textContent = text.value.length + " / " + text.maxLength;
  }

  function stopListening() {
    if (listening) listening.rec.stop();
  }

  document.addEventListener("keydown", function (e) {
    const text = e.target;
    if (!text.matches || !text.matches("[data-bz-message-field]")) return;
    const form = text.closest(BOX);
    if (!form) return;
    if (e.key === "Escape") {
      const stop = form.querySelector("[data-bz-message-stop]");
      if (stop && stop.offsetParent !== null && !e.isComposing) { e.preventDefault(); stop.click(); }
      return;
    }
    if (e.key === "Backspace" && !text.value) {
      const files = uploader(form);
      if (files && files.files && files.files.length) {
        e.preventDefault();
        files.removeFile(files.files[files.files.length - 1]);
      }
      return;
    }
    if (e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    if (touch.matches) return; // the line breaks; the round button sends
    e.preventDefault();
    if (!busy(form) && !empty(form)) {
      form.requestSubmit(form.querySelector("[data-bz-message-send]"));
    }
  });

  document.addEventListener("input", function (e) {
    const form = e.target.closest && e.target.closest(BOX);
    if (form && e.target.matches("[data-bz-message-field]")) count(form);
  });

  document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form.matches || !form.matches(BOX)) return;
    if (busy(form) || empty(form) || drafts.has(form) || form.classList.contains("htmx-request")) {
      e.preventDefault();
      e.stopImmediatePropagation();
      return;
    }
    if (!form.hasAttribute("hx-post")) e.preventDefault();
  }, true);

  document.addEventListener("htmx:beforeSend", function (e) {
    const form = e.detail && e.detail.elt;
    if (!form || !form.matches || !form.matches(BOX)) return;
    stopListening();
    const text = field(form);
    const files = uploader(form);
    drafts.set(form, { text: text ? text.value : "",
                       files: files && files.files ? files.files.map(function (f) { return f.file; }) : [] });
    if (text) write(text, "");
    if (files && files.clear) files.clear();
    if (text && document.activeElement && form.contains(document.activeElement)) text.focus();
  });

  document.addEventListener("htmx:afterRequest", function (e) {
    const form = e.detail && e.detail.elt;
    if (!form || !form.matches || !form.matches(BOX)) return;
    const draft = drafts.get(form);
    drafts.delete(form);
    if (!draft || e.detail.successful) return;
    const text = field(form);
    if (text && !text.value) write(text, draft.text);
    const files = uploader(form);
    if (files && draft.files.length && !(files.files && files.files.length)) {
      files.handleFiles(draft.files);
    }
  });

  document.addEventListener("click", function (e) {
    const button = e.target.closest && e.target.closest("[data-bz-voice]");
    if (!button || !Recognition) return;
    const form = button.closest(BOX);
    const text = form && field(form);
    if (!text) return;
    if (listening) { stopListening(); return; }
    const rec = new Recognition();
    rec.lang = document.documentElement.lang || navigator.language;
    rec.continuous = true;
    rec.interimResults = true;
    const before = text.value.replace(/\s+$/, "");
    rec.onresult = function (event) {
      let heard = "";
      for (let i = 0; i < event.results.length; i++) heard += event.results[i][0].transcript;
      heard = heard.trim();
      write(text, before && heard ? before + " " + heard : before || heard);
    };
    rec.onend = function () {
      button.removeAttribute("data-listening");
      button.setAttribute("aria-pressed", "false");
      listening = null;
    };
    listening = { rec: rec, button: button };
    button.setAttribute("data-listening", "true");
    button.setAttribute("aria-pressed", "true");
    rec.start();
  });

  document.addEventListener("dragover", function (e) {
    const form = e.target.closest && e.target.closest(BOX);
    if (form) e.preventDefault(); // a file dropped here never replaces the page
  });

  document.addEventListener("drop", function (e) {
    const form = e.target.closest && e.target.closest(BOX);
    if (!form) return;
    e.preventDefault();
    const files = uploader(form);
    if (!files || off(form) || !e.dataTransfer || !e.dataTransfer.files.length) return;
    files.handleFiles(e.dataTransfer.files);
  });
})();

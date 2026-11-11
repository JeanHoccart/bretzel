/* message_list.js — ``ui.message_list`` follows its newest message.
 *
 * The behaviour that chat libraries (assistant-ui, Vercel AI Elements,
 * Ant Design X, Gradio, chatscope) share, and test:
 *
 * - **at the bottom, it stays there** — a new message, an answer that
 *   grows word by word, a refresh of the thread: the list scrolls with it;
 * - **scrolled up, it stops following** — the reader is reading; nothing
 *   pulls them down, and « back to the latest message » appears
 *   (``data-away`` on the list, which its theme reads);
 * - **back at the bottom** — by hand or by that button — it follows again.
 *
 * What grows is watched by a ResizeObserver on the thread (a new node, a
 * longer text, an image that loads: all change its height). The state is
 * kept by the list's id (it always has one): a refresh that morphs it
 * strips ``data-away`` — the server never renders it —, one that replaces
 * the element loses its scroll; both are put back after each settle,
 * where the reader was. A list met for the first time starts at its
 * bottom.
 */
(function () {
  "use strict";
  const LIST = "[data-bz-message-list]";
  const NEAR = 48; // px from the bottom that still count as « at the bottom »
  // By the list's id, not its element: a refresh may replace the element,
  // and what the reader did (scrolled up, to where) must survive it.
  const states = new Map(); // id → {stuck, top}
  const watched = new WeakSet(); // elements already observed

  function smooth() {
    return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function toBottom(list, animated) {
    list.scrollTo({ top: list.scrollHeight, behavior: animated && smooth() ? "smooth" : "auto" });
  }

  function stateOf(list) {
    let state = states.get(list.id);
    if (!state) { state = { stuck: true, top: 0 }; states.set(list.id, state); }
    return state;
  }

  function mark(list) {
    list.toggleAttribute("data-away", !stateOf(list).stuck);
  }

  function adopt(list) {
    const known = states.has(list.id);
    const state = stateOf(list);
    if (!watched.has(list)) {
      watched.add(list);
      const thread = list.firstElementChild;
      if (thread && window.ResizeObserver) {
        new ResizeObserver(function () {
          if (stateOf(list).stuck) toBottom(list, false);
        }).observe(thread);
      }
      list.addEventListener("scroll", function () {
        const s = stateOf(list);
        s.stuck = list.scrollHeight - list.scrollTop - list.clientHeight < NEAR;
        s.top = list.scrollTop;
        mark(list);
      }, { passive: true });
      // A new element of a list met before: back where the reader was.
      if (known && !state.stuck) list.scrollTop = state.top;
    }
    if (state.stuck) toBottom(list, false);
    mark(list);
  }

  function scan(root) {
    (root && root.querySelectorAll ? root : document).querySelectorAll(LIST).forEach(adopt);
    if (root && root.matches && root.matches(LIST)) adopt(root);
  }

  document.addEventListener("DOMContentLoaded", function () { scan(document); });
  document.addEventListener("htmx:load", function (e) { scan(e.target); });
  document.addEventListener("htmx:afterSettle", function () {
    document.querySelectorAll(LIST).forEach(adopt);
  });

  document.addEventListener("click", function (e) {
    const button = e.target.closest && e.target.closest("[data-bz-message-list-bottom]");
    const list = button && button.closest(LIST);
    if (!list) return;
    stateOf(list).stuck = true;
    toBottom(list, true);
    mark(list);
  });
})();

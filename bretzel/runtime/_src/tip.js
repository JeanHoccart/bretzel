/* tip.js — the ONE tooltip panel of the page, and the service that shows it.
 *
 * A client scope, four listeners and a teleported panel with its arrow
 * for every `ui.tooltip` — and every universal `tooltip="…"`, which builds
 * one — would weigh far more than what the tooltip says. So the server
 * renders ONE panel per page (`#bz-tip`, with the app's merged tooltip
 * theme — `bretzel/components/overlay/tooltip`), and a trigger only
 * carries what it says:
 *
 *   data-bz-tip-root           the wrapper the pointer and the focus enter
 *   data-bz-tip="…"            its text (`bz-attr:` keeps a binding live)
 *   <template data-bz-tip-content>   rich content, cloned in at show time
 *   data-bz-tip-position / -color / -delay / -class   when not the default
 *   data-bz-tip-off="expr"     `disabled=`, evaluated at HOVER time with
 *                              `$el` = the trigger (never frozen at mount)
 *   data-bz-tip-beside="sel"   place the panel beside that ANCESTOR's edge,
 *                              centred on the trigger (the sidebar rail: a
 *                              collapsed entry is a square inside the rail)
 *
 * The rules are the ones the per-instance scope applied: the reveal delay;
 * no tooltip over a popup its trigger opened (`aria-expanded="true"`,
 * checked again after the delay); hidden on click and when an anchored
 * descendant dispatches `open`. Two are new: the focusable control is
 * described by the panel while it shows (`aria-describedby`) — unless its
 * accessible name already says the same words, as an icon-only button
 * named after its tooltip does — and a swap that removes the trigger hides
 * the panel instead of leaving it pointing at nothing.
 *
 * `$bz.tip.open(anchor, opts)` / `$bz.tip.close()` are the same panel for
 * code that positions it itself — the sidebar rail, the charts.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});
  const ROOT = "[data-bz-tip-root]";
  const BRIDGE = "bz-c-";

  let current = null; // the root shown, or waiting for its delay
  let timer = null;
  let detach = null; // floating's cleanup
  let watcher = null; // follows a live text while shown
  let described = null; // [element, previous aria-describedby]
  let extra = []; // per-instance panel classes applied on this show

  function panel() {
    return document.getElementById("bz-tip");
  }

  function bodyOf(p) {
    return p.querySelector("[data-bz-tip-body]");
  }

  function popupOpen(root) {
    return !!root.querySelector('[aria-expanded="true"]');
  }

  function switchedOff(root) {
    const expr = root.getAttribute("data-bz-tip-off");
    if (!expr) return false;
    try {
      return !!$bz._evaluate(root, expr);
    } catch (err) {
      return false;
    }
  }

  function anchorOf(root) {
    // Same probe as the anchored panels: a `display:contents` wrapper has
    // no box, its first child is the trigger's.
    return getComputedStyle(root).display === "contents"
      ? root.firstElementChild || root
      : root;
  }

  const FOCUSABLE = "a[href],button,input,select,textarea,[tabindex]";

  function controlOf(root) {
    return root.matches(FOCUSABLE) ? root : root.querySelector(FOCUSABLE) || root;
  }

  function nameOf(el) {
    return (el.getAttribute("aria-label") || el.textContent || "").trim();
  }

  // The extra gap that puts the panel beside an ancestor's edge rather
  // than the anchor's own.
  function besideGap(anchor, ancestor, placement) {
    const a = anchor.getBoundingClientRect();
    const b = ancestor.getBoundingClientRect();
    const side = placement.split("-")[0];
    if (side === "right") return b.right - a.right;
    if (side === "left") return a.left - b.left;
    if (side === "bottom") return b.bottom - a.bottom;
    if (side === "top") return a.top - b.top;
    return 0;
  }

  function delayOf(root) {
    const own = root.getAttribute("data-bz-tip-delay");
    const p = panel();
    return Number(own || (p && p.getAttribute("data-bz-tip-delay")) || 0);
  }

  function clearBody(p) {
    const body = bodyOf(p);
    if (!body) return null;
    for (const child of Array.from(body.children)) {
      if ($bz._disposeTree) $bz._disposeTree(child);
    }
    body.textContent = "";
    return body;
  }

  function paint(p, opts) {
    // The colour bridge: the panel carries exactly one.
    for (const cls of Array.from(p.classList)) {
      if (cls.indexOf(BRIDGE) === 0) p.classList.remove(cls);
    }
    p.classList.add(BRIDGE + (opts.color || "text"));
    for (const cls of extra) p.classList.remove(cls);
    extra = (opts.extraClass || "").split(/\s+/).filter(Boolean);
    for (const cls of extra) p.classList.add(cls);
  }

  function open(anchor, opts) {
    const p = panel();
    if (!p || !anchor) return;
    opts = opts || {};
    const body = clearBody(p);
    if (body) {
      if (opts.content) {
        body.appendChild(opts.content);
        if ($bz._scan) $bz._scan(body);
      } else {
        body.textContent = opts.text || "";
      }
    }
    paint(p, opts);
    const placement = opts.position || "auto";
    p.setAttribute("data-side", placement === "auto" ? "bottom" : placement);
    if (detach) detach();
    // Last in <body>: at the top rung (``z-50``) the tie goes to the last
    // painted, so the panel shows above an open dialog or picker.
    if (p.parentNode !== document.body || p.nextElementSibling) {
      document.body.appendChild(p);
    }
    p.style.display = "";
    const floatOpts = { placement: placement };
    if (opts.beside) floatOpts.offset = 6 + besideGap(anchor, opts.beside, placement);
    detach = $bz.helpers.floating(anchor, p, floatOpts);
    const control = opts.describes;
    if (control && nameOf(control) !== (opts.text || "").trim()) {
      described = [control, control.getAttribute("aria-describedby")];
      control.setAttribute("aria-describedby", "bz-tip");
    }
  }

  function close() {
    clearTimeout(timer);
    timer = null;
    if (watcher) watcher.disconnect();
    watcher = null;
    if (described) {
      const [el, previous] = described;
      if (previous === null) el.removeAttribute("aria-describedby");
      else el.setAttribute("aria-describedby", previous);
      described = null;
    }
    // The body is NOT emptied here. Emptying buys nothing; the next
    // `open` clears it.
    const p = panel();
    if (p) p.style.display = "none";
    if (detach) detach();
    detach = null;
    current = null;
  }

  function optionsOf(root) {
    const tpl = root.querySelector(":scope > template[data-bz-tip-content]");
    const beside = root.getAttribute("data-bz-tip-beside");
    return {
      beside: beside ? root.closest(beside) : null,
      describes: controlOf(root),
      text: root.getAttribute("data-bz-tip") || "",
      content: tpl ? tpl.content.cloneNode(true) : null,
      position: root.getAttribute("data-bz-tip-position") || "auto",
      color: root.getAttribute("data-bz-tip-color") || "text",
      extraClass: root.getAttribute("data-bz-tip-class") || "",
    };
  }

  function showRoot(root) {
    if (current !== root || !root.isConnected) return;
    if (popupOpen(root) || switchedOff(root)) return;
    open(anchorOf(root), optionsOf(root));
    // A bound text keeps changing while the panel shows.
    watcher = new MutationObserver(function () {
      const p = panel();
      const body = p && bodyOf(p);
      if (body && !root.querySelector(":scope > template[data-bz-tip-content]")) {
        body.textContent = root.getAttribute("data-bz-tip") || "";
      }
    });
    watcher.observe(root, { attributes: true, attributeFilter: ["data-bz-tip"] });
  }

  function enter(root) {
    if (root === current) return;
    close();
    if (popupOpen(root) || switchedOff(root)) return;
    current = root;
    timer = setTimeout(function () {
      showRoot(root);
    }, delayOf(root));
  }

  function rootOf(node) {
    return node && node.closest ? node.closest(ROOT) : null;
  }

  // A click hides the panel until the pointer MOVES. A click often redraws
  // what is under a pointer that has not moved — a button swapped for its
  // pressed twin, a row morphed — and the browser then sends `mouseover`
  // for the new element: the tooltip came back over what was just clicked.
  let clickedAt = null; // [x, y] of the click that closed the panel

  document.addEventListener("mouseover", function (e) {
    const root = rootOf(e.target);
    if (!root || root === current) return;
    if (e.relatedTarget && root.contains(e.relatedTarget)) return;
    if (clickedAt && e.clientX === clickedAt[0] && e.clientY === clickedAt[1]) return;
    clickedAt = null;
    enter(root);
  });
  document.addEventListener("mousemove", function (e) {
    if (!clickedAt || (e.clientX === clickedAt[0] && e.clientY === clickedAt[1])) return;
    clickedAt = null;
    const root = rootOf(e.target);
    if (root) enter(root);
  });
  document.addEventListener("mouseout", function (e) {
    if (!current || rootOf(e.target) !== current) return;
    if (e.relatedTarget && current.contains(e.relatedTarget)) return;
    close();
  });
  document.addEventListener("focusin", function (e) {
    const root = rootOf(e.target);
    // After a click, until the pointer moves, a focus that is not
    // ``:focus-visible`` was put there by a script — the clicked button
    // disappears and the runtime hands its focus to the neighbour, its
    // pressed twin, and the tooltip would come back over it. A Tab IS
    // focus-visible: the keyboard still opens it.
    if (clickedAt && !e.target.matches(":focus-visible")) return;
    if (root) enter(root);
  });
  document.addEventListener("focusout", function (e) {
    if (!current || !current.contains(e.target)) return;
    if (e.relatedTarget && current.contains(e.relatedTarget)) return;
    close();
  });
  document.addEventListener(
    "click",
    function (e) {
      if (!current || !current.contains(e.target)) return;
      close();
      clickedAt = [e.clientX, e.clientY];
    },
    true,
  );
  // An anchored descendant (a dropdown in the trigger) announces its panel.
  document.addEventListener(
    "open",
    function (e) {
      if (current && current.contains(e.target)) close();
    },
    true,
  );
  // A swap that removed the trigger must not leave the panel behind.
  for (const name of ["htmx:afterSwap", "htmx:oobAfterSwap"]) {
    document.addEventListener(name, function () {
      if (current && !current.isConnected) close();
    });
  }

  $bz.tip = { open: open, close: close };
})();

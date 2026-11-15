/* editor.js — the browser part of ``ui.editor``.
 *
 * The brick is ProseMirror, shipped as ``prosemirror.min.js`` (the
 * global ``BzProseMirror``) and loaded the first time an editor appears:
 * its URL is on the editor (``data-bz-editor-src``), never written here.
 * Everything that makes it Bretzel's editor is in this file — the schema,
 * the Markdown dialect, the keys, the paste — so the brick could change
 * without an app noticing.
 *
 *   bz-data="{...$bz.editor.scope, value: '…', _surface: null,
 *             _read(){…}, _write(v){…}}"
 *
 * ── Who writes what ────────────────────────────────────────────────────
 * The VALUE is Markdown, in the scope (``_read`` / ``_write``): the hidden
 * carrier reports it into the form, and draws the ``change`` from it.
 * The DOCUMENT is ProseMirror's, on the surface node (``_bzView``), which
 * a morph leaves whole (``data-bz-client-dom``, ``bridge.js``). Each edit
 * publishes the Markdown; ``_follow`` shows a value written from outside
 * and ignores what the editor published itself (``_bzShown``) — the same
 * pair as SignaturePad's ``_publish`` / ``_follow``.
 *
 * ── One format ─────────────────────────────────────────────────────────
 * Enter goes to the line (a hard break), Enter on an empty line starts a
 * paragraph, and Backspace at the start of a paragraph undoes exactly
 * that (the paragraph becomes a line again): a line and a paragraph are
 * the two steps of the Markdown, a paragraph 3/4 of a line apart.
 */
(function () {
  "use strict";
  const $bz = (window.$bz = window.$bz || {});

  // ── The brick, loaded once per page, and the kit built on it ──────────
  let loading = null;
  let built = null;
  function brick(src) {
    loading = loading || new Promise(function (resolve, reject) {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = function () {
        loading = null;
        reject(new Error("ui.editor: " + src + " did not load"));
      };
      document.head.appendChild(script);
    }).then(function () { return (built = kit(window.BzProseMirror)); });
    return loading;
  }

  // An address the browser would run, read as it reads a scheme: the
  // control characters and spaces it skips taken out (``java\tscript:``).
  function unsafe(href) {
    return /^(javascript|vbscript|data|file):/i.test(href.replace(/[\u0000- ]/g, ""));
  }

  // ── The kit: schema, Markdown both ways, keys, paste ──────────────────
  function kit(PM) {
    const schema = new PM.Schema({
      nodes: {
        doc: { content: "block+" },
        paragraph: {
          content: "inline*", group: "block",
          // A heading or a quote pasted in becomes a paragraph: the
          // editor has one format.
          parseDOM: [{ tag: "p" }, { tag: "h1" }, { tag: "h2" }, { tag: "h3" },
            { tag: "h4" }, { tag: "h5" }, { tag: "h6" }, { tag: "pre" }],
          toDOM: function () { return ["p", 0]; },
        },
        bullet_list: {
          content: "list_item+", group: "block", attrs: { tight: { default: true } },
          parseDOM: [{ tag: "ul" }],
          toDOM: function () { return ["ul", 0]; },
        },
        ordered_list: {
          content: "list_item+", group: "block",
          attrs: { order: { default: 1 }, tight: { default: true } },
          parseDOM: [{
            tag: "ol",
            getAttrs: function (dom) {
              const start = parseInt(dom.getAttribute("start") || "1", 10);
              return { order: isNaN(start) ? 1 : start };
            },
          }],
          toDOM: function (node) {
            return node.attrs.order === 1 ? ["ol", 0] : ["ol", { start: node.attrs.order }, 0];
          },
        },
        list_item: {
          content: "paragraph block*", defining: true,
          parseDOM: [{ tag: "li" }],
          toDOM: function () { return ["li", 0]; },
        },
        text: { group: "inline" },
        hard_break: {
          inline: true, group: "inline", selectable: false,
          parseDOM: [{ tag: "br" }],
          toDOM: function () { return ["br"]; },
        },
      },
      marks: {
        link: {
          attrs: { href: {}, title: { default: null } },
          inclusive: false,
          parseDOM: [{
            tag: "a[href]",
            getAttrs: function (dom) {
              const href = dom.getAttribute("href");
              if (!href || unsafe(href)) return false;
              return { href: href, title: dom.getAttribute("title") };
            },
          }],
          toDOM: function (mark) {
            return ["a", { href: mark.attrs.href, title: mark.attrs.title,
              rel: "noopener noreferrer nofollow", target: "_blank" }, 0];
          },
        },
        em: {
          parseDOM: [{ tag: "i" }, { tag: "em" }, { style: "font-style=italic" },
            { style: "font-style=normal", clearMark: function (m) { return m.type.name === "em"; } }],
          toDOM: function () { return ["em", 0]; },
        },
        strong: {
          parseDOM: [
            { tag: "strong" },
            // Google Docs wraps a whole paste in ``<b style="font-weight:normal">``.
            { tag: "b", getAttrs: function (n) { return n.style.fontWeight !== "normal" && null; } },
            { style: "font-weight=400", clearMark: function (m) { return m.type.name === "strong"; } },
            { style: "font-weight", getAttrs: function (v) { return /^(bold(er)?|[5-9]\d{2,})$/.test(v) && null; } },
          ],
          toDOM: function () { return ["strong", 0]; },
        },
      },
    });
    const N = schema.nodes;
    const M = schema.marks;

    // Markdown → document. CommonMark, reduced to what the editor shows:
    // the rest (a heading, a quote, code, an image) stays TEXT, so
    // nothing disappears in silence.
    const md = PM.MarkdownIt("commonmark", { html: false, linkify: false });
    md.disable(["heading", "lheading", "blockquote", "code", "fence", "hr",
      "html_block", "html_inline", "image", "backticks"]);
    function tight(tokens, i) {
      while (++i < tokens.length) if (tokens[i].type !== "list_item_open") return tokens[i].hidden;
      return false;
    }
    const parser = new PM.MarkdownParser(schema, md, {
      paragraph: { block: "paragraph" },
      list_item: { block: "list_item" },
      bullet_list: { block: "bullet_list", getAttrs: function (_, toks, i) { return { tight: tight(toks, i) }; } },
      ordered_list: {
        block: "ordered_list",
        getAttrs: function (tok, toks, i) {
          return { order: +tok.attrGet("start") || 1, tight: tight(toks, i) };
        },
      },
      hardbreak: { node: "hard_break" },
      em: { mark: "em" },
      strong: { mark: "strong" },
      link: {
        mark: "link",
        getAttrs: function (tok) { return { href: tok.attrGet("href"), title: tok.attrGet("title") || null }; },
      },
    });

    // Document → Markdown: ``**``, ``*``, ``- `` (two spaces a step),
    // ``1. ``, ``[text](url)``, a line break as ``\`` at the line's end.
    const base = PM.defaultMarkdownSerializer;
    const serializer = new PM.MarkdownSerializer({
      paragraph: base.nodes.paragraph,
      bullet_list: function (state, node) { state.renderList(node, "  ", function () { return "- "; }); },
      ordered_list: base.nodes.ordered_list,
      list_item: base.nodes.list_item,
      text: base.nodes.text,
      hard_break: base.nodes.hard_break,
    }, {
      em: { open: "*", close: "*", mixable: true, expelEnclosingWhitespace: true },
      strong: base.marks.strong,
      link: base.marks.link,
    });

    function parse(markdown) {
      return parser.parse(markdown || "") || schema.topNodeType.createAndFill();
    }
    function serialize(doc) {
      return isEmpty(doc) ? "" : serializer.serialize(doc);
    }
    function isEmpty(doc) {
      return doc.childCount === 1 && doc.firstChild.type === N.paragraph
        && doc.firstChild.content.size === 0;
    }

    // ── Where the cursor is ────────────────────────────────────────────
    function markActive(state, type) {
      const sel = state.selection;
      if (sel.empty) return !!type.isInSet(state.storedMarks || sel.$from.marks());
      return state.doc.rangeHasMark(sel.from, sel.to, type);
    }
    // The nearest list around the cursor: its node and its position.
    function nearestList(state) {
      const $from = state.selection.$from;
      for (let d = $from.depth; d > 0; d--) {
        const node = $from.node(d);
        if (node.type === N.bullet_list || node.type === N.ordered_list) {
          return { node: node, pos: $from.before(d) };
        }
      }
      return null;
    }
    function inItem(state) {
      const $from = state.selection.$from;
      return $from.depth >= 2 && $from.node(-1).type === N.list_item;
    }

    // ── Commands ───────────────────────────────────────────────────────
    function toggleList(type) {
      return function (state, dispatch) {
        const list = nearestList(state);
        if (list && list.node.type === type) return PM.liftListItem(N.list_item)(state, dispatch);
        if (list) {
          if (dispatch) dispatch(state.tr.setNodeMarkup(list.pos, type, { tight: list.node.attrs.tight }));
          return true;
        }
        return PM.wrapInList(type)(state, dispatch);
      };
    }
    const toggleBold = PM.toggleMark(M.strong);
    const toggleItalic = PM.toggleMark(M.em);

    // Enter goes to the line; on an empty line (just after a break) it
    // takes the break back and starts a paragraph. In a list, Enter is
    // the next item, and on an empty item it leaves the list.
    function enter(state, dispatch) {
      if (inItem(state)) {
        return PM.splitListItem(N.list_item)(state, dispatch)
          || PM.liftListItem(N.list_item)(state, dispatch);
      }
      if (!dispatch) return true;
      let tr = state.tr;
      if (!state.selection.empty) tr = tr.deleteSelection();
      const $pos = tr.selection.$from;
      const before = $pos.nodeBefore;
      if (before && before.type === N.hard_break) {
        tr = tr.delete($pos.pos - 1, $pos.pos);
        tr = tr.split(tr.mapping.map($pos.pos - 1));
      } else {
        tr = tr.replaceSelectionWith(N.hard_break.create());
      }
      dispatch(tr.scrollIntoView());
      return true;
    }
    function lineBreak(state, dispatch) {
      if (dispatch) dispatch(state.tr.replaceSelectionWith(N.hard_break.create()).scrollIntoView());
      return true;
    }
    // Backspace at the start of a paragraph that follows another one:
    // the paragraph's gap goes, the line break stays — Enter twice undone.
    function backspace(state, dispatch) {
      const sel = state.selection;
      const $from = sel.$from;
      if (!sel.empty || $from.parentOffset !== 0 || $from.parent.type !== N.paragraph
          || $from.parent.content.size === 0 || $from.index(-1) === 0) return false;
      const prev = $from.node(-1).child($from.index(-1) - 1);
      if (prev.type !== N.paragraph) return false;
      if (dispatch) {
        dispatch(state.tr.replaceWith($from.pos - 2, $from.pos, N.hard_break.create()).scrollIntoView());
      }
      return true;
    }
    // Tab and Shift+Tab nest in a list, and leave the field elsewhere.
    function onlyInItem(command) {
      return function (state, dispatch) { return inItem(state) ? command(state, dispatch) || true : false; };
    }

    // ── Links ──────────────────────────────────────────────────────────
    // The extent of the link around the cursor, or null.
    function linkAround(state) {
      const $from = state.selection.$from;
      const mark = M.link.isInSet($from.marks())
        || ($from.nodeAfter && M.link.isInSet($from.nodeAfter.marks));
      if (!mark) return null;
      const parent = $from.parent;
      const start = $from.start();
      let from = -1;
      let to = -1;
      parent.forEach(function (child, offset) {
        const has = mark.isInSet(child.marks);
        const a = start + offset;
        const b = a + child.nodeSize;
        if (has && from < 0 && b >= $from.pos) from = a;
        if (has && from >= 0 && to < 0 && a <= $from.pos) to = b;
        else if (has && from >= 0 && to === a) to = b;
      });
      return from >= 0 ? { from: from, to: to, href: mark.attrs.href } : null;
    }
    // What one types becomes an address: a domain gets ``https://``, an
    // e-mail ``mailto:``; a script address is refused.
    function address(raw) {
      const text = (raw || "").trim();
      if (!text || unsafe(text)) return "";
      if (/^[a-z][a-z0-9+.-]*:/i.test(text) || text.startsWith("/") || text.startsWith("#")) return text;
      if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) return "mailto:" + text;
      return "https://" + text;
    }
    function isAddress(text) {
      return /^(https?:\/\/|mailto:)\S+$/i.test(text) || /^www\.\S+\.\S+$/i.test(text);
    }
    // On the selection, else on the link around the cursor, else the
    // address typed becomes the link's text. An empty address unlinks.
    function setLink(view, raw) {
      const state = view.state;
      const href = address(raw);
      const sel = state.selection;
      const range = sel.empty ? linkAround(state) : sel;
      let tr = state.tr;
      if (range) {
        tr = tr.removeMark(range.from, range.to, M.link);
        if (href) tr = tr.addMark(range.from, range.to, M.link.create({ href: href }));
      } else if (href) {
        tr = tr.insert(sel.from, schema.text(raw.trim(), [M.link.create({ href: href })]));
      }
      view.dispatch(tr.scrollIntoView());
    }

    // ── Paste ──────────────────────────────────────────────────────────
    // Word (and Outlook, which writes with Word) pastes a list as
    // paragraphs ``mso-list:l0 level1``, the bullet in a span
    // ``mso-list:Ignore``. They become a real list, the bullet goes.
    function wordLists(html) {
      if (html.indexOf("mso-list") < 0) return html;
      const doc = new window.DOMParser().parseFromString(html, "text/html");
      const items = Array.from(doc.body.querySelectorAll("p")).filter(function (p) {
        return /mso-list:\s*l\d+/i.test(p.getAttribute("style") || "");
      });
      let run = [];
      const runs = [];
      items.forEach(function (p, i) {
        let prev = p.previousSibling;
        while (prev && (prev.nodeType === 8 || (prev.nodeType === 3 && !prev.textContent.trim()))) {
          prev = prev.previousSibling;
        }
        if (i > 0 && prev === items[i - 1]) run.push(p);
        else { if (run.length) runs.push(run); run = [p]; }
      });
      if (run.length) runs.push(run);
      runs.forEach(function (paras) {
        // ``stack``: the open lists, outermost first, each with its last item.
        const stack = [];
        let lastTop = null;
        paras.forEach(function (p) {
          const style = p.getAttribute("style") || "";
          const level = parseInt((style.match(/level(\d+)/i) || [0, 1])[1], 10);
          const ignore = p.querySelector("[style*='Ignore']");
          const marker = ignore ? ignore.textContent.trim() : "";
          if (ignore) ignore.remove();
          const ordered = /^\(?[0-9a-z]{1,4}[.)]$/i.test(marker);
          const li = doc.createElement("li");
          const para = doc.createElement("p");
          while (p.firstChild) para.appendChild(p.firstChild);
          li.appendChild(para);
          while (stack.length && stack[stack.length - 1].level > level) stack.pop();
          const open = stack[stack.length - 1];
          if (open && open.level === level && open.ordered === ordered) {
            open.list.appendChild(li);
            open.li = li;
            return;
          }
          const list = doc.createElement(ordered ? "ol" : "ul");
          list.appendChild(li);
          const entry = { level: level, ordered: ordered, list: list, li: li };
          if (open && open.level === level) {
            open.list.after(list);
            stack[stack.length - 1] = entry;
            if (stack.length === 1) lastTop = list;
            return;
          }
          if (open) open.li.appendChild(list);
          else {
            if (lastTop) lastTop.after(list);
            else paras[0].before(list);
            lastTop = list;
          }
          stack.push(entry);
        });
        paras.forEach(function (p) { p.remove(); });
      });
      return doc.body.innerHTML;
    }
    // Plain text: a line is a line, a blank line a paragraph — never
    // read as Markdown (``5*3`` stays ``5*3``).
    function plainText(text) {
      const paragraphs = text.replace(/\r\n?/g, "\n").split(/\n{2,}/).map(function (block) {
        const parts = [];
        block.split("\n").forEach(function (line, i) {
          if (i) parts.push(N.hard_break.create());
          if (line) parts.push(schema.text(line));
        });
        return N.paragraph.create(null, parts);
      });
      return new PM.Slice(PM.Fragment.fromArray(paragraphs), 1, 1);
    }

    // ``- `` or ``1. `` typed just after a line break (Enter, in a mail)
    // starts a list as at the start of a paragraph: the paragraph is cut
    // where the break was, and that line becomes the list's first item.
    // ProseMirror's own rule only looks at the start of a block, and with
    // Enter = line break, the start of a line is not one. The text before
    // the cursor reads a break as ``￼``.
    function listAfterBreak(pattern, type, attrsOf) {
      return new PM.InputRule(pattern, function (state, match, start, end) {
        const $start = state.doc.resolve(start);
        if ($start.parent.type !== N.paragraph || $start.depth !== 1) return null;
        const tr = state.tr.delete(start, end).split(start);
        const $line = tr.doc.resolve(start + 2);
        const range = $line.blockRange();
        const wrapping = range && PM.findWrapping(range, type, attrsOf(match));
        if (!wrapping) return null;
        return tr.wrap(range, wrapping);
      });
    }

    // Ctrl+K clicks the bar's own link button: one way in, one panel.
    function linkKey(state, dispatch, view) {
      const root = view && view.dom.closest("[data-bz-editor]");
      const link = root && root.querySelector("[data-bz-editor-command=link]");
      if (link && !link.disabled) link.click();
      return true;
    }
    // Built once: a plugin keeps its state in each editor's state, so
    // every editor of the page shares these instances.
    const plugins = [
      PM.inputRules({ rules: [
        PM.wrappingInputRule(/^\s*([-*])\s$/, N.bullet_list),
        PM.wrappingInputRule(/^(\d+)\.\s$/, N.ordered_list,
          function (m) { return { order: +m[1] }; },
          function (m, node) { return node.childCount + node.attrs.order === +m[1]; }),
        listAfterBreak(/￼\s*([-*])\s$/, N.bullet_list, function () { return null; }),
        listAfterBreak(/￼(\d+)\.\s$/, N.ordered_list, function (m) { return { order: +m[1] }; }),
      ] }),
      PM.keymap({
        "Enter": enter,
        "Shift-Enter": lineBreak,
        "Backspace": backspace,
        "Tab": onlyInItem(PM.sinkListItem(N.list_item)),
        "Shift-Tab": onlyInItem(PM.liftListItem(N.list_item)),
        "Mod-b": toggleBold,
        "Mod-i": toggleItalic,
        "Mod-k": linkKey,
        "Mod-z": PM.undo,
        "Mod-y": PM.redo,
        "Shift-Mod-z": PM.redo,
      }),
      PM.keymap(PM.baseKeymap),
      PM.history(),
    ];

    return {
      PM: PM, schema: schema, parse: parse, serialize: serialize, isEmpty: isEmpty,
      plugins: plugins, wordLists: wordLists, plainText: plainText, isAddress: isAddress,
      markActive: markActive, nearestList: nearestList, linkAround: linkAround, setLink: setLink,
      commands: {
        bold: toggleBold,
        italic: toggleItalic,
        bullet_list: toggleList(N.bullet_list),
        ordered_list: toggleList(N.ordered_list),
      },
    };
  }

  // ── The bar follows the cursor ────────────────────────────────────────
  function rootOf(view) { return view.dom.closest("[data-bz-editor]"); }
  function syncBar(view, k) {
    const root = rootOf(view);
    if (!root) return;
    const state = view.state;
    const list = k.nearestList(state);
    const active = {
      bold: k.markActive(state, k.schema.marks.strong),
      italic: k.markActive(state, k.schema.marks.em),
      bullet_list: !!list && list.node.type === k.schema.nodes.bullet_list,
      ordered_list: !!list && list.node.type === k.schema.nodes.ordered_list,
      link: k.markActive(state, k.schema.marks.link),
    };
    root.querySelectorAll("[data-bz-editor-command]").forEach(function (button) {
      const on = active[button.getAttribute("data-bz-editor-command")] ? "true" : "false";
      if (button.getAttribute("aria-pressed") !== on) button.setAttribute("aria-pressed", on);
    });
  }

  // ── The link panel ────────────────────────────────────────────────────
  // Its content goes to ``<body>`` with the popover; it names its editor.
  function viewFor(el) {
    const owner = el.closest("[data-bz-editor-for]");
    const root = owner ? document.getElementById(owner.getAttribute("data-bz-editor-for"))
      : el.closest("[data-bz-editor]");
    const surface = root && root.querySelector("[data-bz-client-dom]");
    return surface && surface._bzView ? surface._bzView : null;
  }
  function linkField(root) {
    return document.querySelector("[data-bz-editor-for='" + root.id + "'] [data-bz-editor-link-url]");
  }
  function closeLink(view) {
    const pop = rootOf(view).querySelector("[data-bz-editor-link]");
    if (pop) pop.dispatchEvent(new CustomEvent("bz-close", { bubbles: true }));
    view.focus();
  }
  // Filled before the popover opens; its ``autofocus`` puts the caret there.
  function openLink(view) {
    const field = linkField(rootOf(view));
    const around = built.linkAround(view.state);
    if (field) field.value = around ? around.href : "";
  }

  // ── The page's listeners, installed by its first editor ───────────────
  // Delegated from the document: a morph re-renders the bar freely, and a
  // page without an editor pays nothing.
  let listening = false;
  function listen() {
    if (listening) return;
    listening = true;
    // (The keyboard user's mark, ``data-bz-keyboard``, is the page's:
    // ``helpers.js``.)
    document.addEventListener("keydown", function (e) {
      // Enter in the link panel's address applies it.
      if (e.key !== "Enter" || !e.target.closest || !e.target.closest("[data-bz-editor-link-url]")) return;
      const view = viewFor(e.target);
      if (!view) return;
      e.preventDefault();
      built.setLink(view, e.target.value);
      closeLink(view);
    }, true);
    document.addEventListener("mousedown", function (e) {
      // The text keeps the focus and its selection.
      const button = e.target.closest && e.target.closest("[data-bz-editor-command]");
      if (button && button.getAttribute("data-bz-editor-command") !== "link") e.preventDefault();
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest) return;
      const button = e.target.closest("[data-bz-editor-command]");
      if (button) {
        const view = viewFor(button);
        if (!view || button.disabled) return;
        const name = button.getAttribute("data-bz-editor-command");
        if (name === "link") { openLink(view); return; }
        built.commands[name](view.state, view.dispatch);
        view.focus();
        return;
      }
      const apply = e.target.closest("[data-bz-editor-link-apply]");
      const remove = e.target.closest("[data-bz-editor-link-remove]");
      if (apply || remove) {
        const view = viewFor(apply || remove);
        if (!view) return;
        const field = linkField(rootOf(view));
        built.setLink(view, remove ? "" : (field ? field.value : ""));
        closeLink(view);
      }
    });
  }

  $bz.editor = {
    scope: {
      // At ``bz-init``: the view goes away with the editor, then the
      // brick loads (once per page) and the view mounts.
      _boot(root) {
        listen();
        const surface = this._surface;
        $bz._own(function () {
          if (surface && surface._bzView) { surface._bzView.destroy(); surface._bzView = null; }
        });
        const self = this;
        brick(root.getAttribute("data-bz-editor-src")).then(function (k) {
          self._mount(root, k);
        }, function (err) { console.error(err); });
      },

      _mount(root, k) {
        const surface = this._surface;
        if (!surface || surface._bzView || !surface.isConnected) return;
        const self = this;
        const shown = this._read() || "";
        surface._bzShown = shown;
        surface._bzOff = root.hasAttribute("data-disabled");
        // ProseMirror rewrites the node's class and attributes: they are
        // handed to it, read once from the server's paint.
        const own = {};
        ["class", "role", "aria-multiline", "aria-label", "data-bz-placeholder"].forEach(function (name) {
          if (surface.hasAttribute(name)) own[name] = surface.getAttribute(name);
        });
        surface.replaceChildren();
        const view = new k.PM.EditorView({ mount: surface }, {
          state: k.PM.EditorState.create({ doc: k.parse(shown), plugins: k.plugins }),
          editable: function () { return !root.hasAttribute("data-disabled"); },
          attributes: function (state) {
            const attrs = Object.assign({}, own);
            if (k.isEmpty(state.doc)) attrs["data-empty"] = "";
            return attrs;
          },
          transformPastedHTML: k.wordLists,
          clipboardTextParser: k.plainText,
          handlePaste: function (v, event) {
            // An address pasted over selected text makes it a link.
            const text = (event.clipboardData && event.clipboardData.getData("text/plain") || "").trim();
            if (v.state.selection.empty || !k.isAddress(text)) return false;
            k.setLink(v, text);
            return true;
          },
          // A click on a link follows it, in a new tab — what was clicked,
          // read on the page. A drag still selects (ProseMirror calls this
          // for a click only); to change a link, the caret goes in it by
          // the keyboard, then the bar's link button or Ctrl+K.
          handleClick: function (v, pos, event) {
            const a = event.target.closest && event.target.closest("a[href]");
            if (!a || !v.dom.contains(a)) return false;
            window.open(a.getAttribute("href"), "_blank", "noopener");
            return true;
          },
          dispatchTransaction: function (tr) {
            const state = view.state.apply(tr);
            view.updateState(state);
            if (tr.docChanged || tr.selectionSet || tr.storedMarksSet) syncBar(view, k);
            if (!tr.docChanged || tr.getMeta("bz-outside")) return;
            const markdown = k.serialize(state.doc);
            if (markdown === surface._bzShown) return;
            surface._bzShown = markdown;
            self._write(markdown);
          },
        });
        surface._bzView = view;
        syncBar(view, k);
      },

      // ``value`` is two-way: a value written from outside (a server
      // reset, ``.set()``, another control on the same ClientState) is
      // shown, as one undoable step. What the editor published itself is
      // not read back — re-parsing would move the cursor.
      _follow() {
        const value = this._read() || "";
        const surface = this._surface;
        const view = surface && surface._bzView;
        if (!view) return;
        // A morph may have switched the editor on or off.
        const off = surface.closest("[data-bz-editor]").hasAttribute("data-disabled");
        if (off !== surface._bzOff) { surface._bzOff = off; view.setProps({}); }
        if (value === surface._bzShown) return;
        surface._bzShown = value;
        const doc = built.parse(value);
        view.dispatch(view.state.tr.replaceWith(0, view.state.doc.content.size, doc.content)
          .setMeta("bz-outside", true));
      },

      // ``.insert(markdown)``: at the cursor, inline when it is one line.
      insert(markdown) {
        const surface = this._surface;
        const view = surface && surface._bzView;
        if (!view) {
          const now = this._read() || "";
          this._write(now ? now + "\n\n" + markdown : markdown);
          return;
        }
        const doc = built.parse(markdown);
        view.dispatch(view.state.tr.replaceSelection(built.PM.Slice.maxOpen(doc.content)).scrollIntoView());
      },
    },
  };
})();

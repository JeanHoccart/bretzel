/* file_upload.js — $bz.fileUpload.makeScope factory for ui.file_upload. */
// ════════════════════════════════════════════════════════════════════════
// 08 FILE UPLOAD — bz-data scope factory for <ui.file_upload>.
//
// Why a runtime slab
// ──────────────────
// The component carries enough JS for the inline-bz-data shape to bloat
// every instance. Externalising into one factory means each instance
// just drops ``bz-data="$bz.fileUpload.makeScope({el: $el, …})"``.
//
// Notes : (a) the scope captures its root element (``opts.el``,
// available in the ``bz-data`` expression) — scope methods get no
// ``$root`` / ``$refs`` / ``$dispatch`` magic. (b) signals compare
// by identity, so array mutations REASSIGN (``files = [...]``) and
// per-file updates replace the entry object (keyed by id) so the
// ``bz-for`` rows re-render.
//
// The factory owns :
//
//   1. Drag state (``isDragging``).
//   2. The file list (each entry carries the raw ``File`` + UI status :
//      progress / done / error).
//   3. Client-side validation : ``accept`` filter, ``max_size_mb``,
//      ``max_files``, single vs multi.
//   4. DataTransfer sync with the hidden native ``<input type="file">``
//      so a parent ``<form>`` submit ships exactly what's displayed.
//   5. Image-preview thumbnails via ``URL.createObjectURL`` (revoked on
//      remove to free memory).
//   6. Optional async upload mode (``uploadUrl`` opt-in) via per-file
//      XMLHttpRequest with progress events. ``upload_*`` Alpine events
//      dispatch with the raw ``File`` so a ClientBinding push or a
//      server callable receives identity.
//
// Public DOM event shape (what the framework hooks onto) :
//   change            — files added / removed
//   upload-start      — async POST started for one file
//   upload-progress   — per-file progress %, NOT bridged to the server
//                       (every-tick round-trip would melt the wire)
//   upload-complete   — async POST returned 2xx
//   upload-error      — async POST returned 4xx/5xx or threw
//
// Validation errors live in ``errors`` (array of strings) — rendered
// inline by the component. We don't dispatch them as events ; the panel
// is reactive on the array.
// ════════════════════════════════════════════════════════════════════════

(function () {
    'use strict';

    if (typeof window === 'undefined') return;
    if (!window.$bz) window.$bz = {};
    if (window.$bz.fileUpload) return;

    // A size in the page's language: « 1,5 Mo » in French, « 1.5 MB » in
    // English — ``Intl``'s units.
    function formatSize(bytes) {
        const lang = document.documentElement.lang || undefined;
        const unit = bytes >= 1048576 ? ['megabyte', bytes / 1048576, 1]
            : bytes >= 1024 ? ['kilobyte', bytes / 1024, 0] : ['byte', bytes, 0];
        return new Intl.NumberFormat(lang, {
            style: 'unit', unit: unit[0], unitDisplay: 'short',
            maximumFractionDigits: unit[2],
        }).format(unit[1]);
    }

    // Compare ``file`` against ``accept`` token (mirror of the HTML
    // accept-attribute matching, simplified) :
    //   ".pdf"      → extension match
    //   "image/*"   → MIME family match
    //   "image/png" → exact MIME match
    function matchesToken(file, token) {
        token = token.trim().toLowerCase();
        if (!token) return true;
        if (token.charAt(0) === '.') {
            const idx = file.name.lastIndexOf('.');
            if (idx < 0) return false;
            return file.name.slice(idx).toLowerCase() === token;
        }
        const type = (file.type || '').toLowerCase();
        if (token.endsWith('/*')) {
            return type.startsWith(token.slice(0, -1));
        }
        return type === token;
    }

    function matchesAccept(file, acceptList) {
        if (!acceptList || acceptList.length === 0) return true;
        for (let i = 0; i < acceptList.length; i++) {
            if (matchesToken(file, acceptList[i])) return true;
        }
        return false;
    }

    // Stable id per file entry so ``bz-for`` :key= stays consistent
    // through removals (browsers don't expose a native handle).
    let _uid = 0;
    function nextId() { _uid += 1; return _uid; }

    function isImage(file) {
        return (file.type || '').startsWith('image/');
    }

    // A pasted screenshot reaches the page as ``image.png`` — every one
    // of them: three captures pasted would be three files of the same
    // name. It is renamed after the moment it was pasted; a real file
    // copied from the file manager keeps its own name.
    const GENERIC_PASTE_NAME = /^image\.(\w+)$/i;

    function pad(n) { return String(n).padStart(2, '0'); }

    function pastedName(file, stamp, index) {
        const found = GENERIC_PASTE_NAME.exec(file.name || 'image.png');
        if (!found) return file.name;
        return 'pasted-' + stamp + (index ? '-' + (index + 1) : '') +
            '.' + found[1].toLowerCase();
    }

    // The files a paste carries, or none. ``text/plain`` among the types
    // means the paste is TEXT that happens to come with a picture — Excel
    // cells and Word paragraphs both put a rendering of themselves on the
    // clipboard: the text must land in the field, and nothing be joined.
    function filesOfPaste(data) {
        if (!data || !data.files || data.files.length === 0) return [];
        const types = Array.from(data.types || []);
        if (types.indexOf('text/plain') !== -1) return [];
        const now = new Date();
        const stamp = now.getFullYear() + pad(now.getMonth() + 1) +
            pad(now.getDate()) + '-' + pad(now.getHours()) +
            pad(now.getMinutes()) + pad(now.getSeconds());
        return Array.from(data.files).map((file, i) => {
            const name = pastedName(file, stamp, i);
            return name === file.name ? file : new File([file], name, {
                type: file.type, lastModified: file.lastModified,
            });
        });
    }

    function makeScope(opts) {
        const acceptList = opts.accept
            ? String(opts.accept).split(',').map((s) => s.trim()).filter(Boolean)
            : null;
        const maxSizeMB = opts.maxSizeMB || null;
        const maxFiles = opts.maxFiles || null;
        const multiple = !!opts.multiple;
        const showPreviews = opts.showPreviews !== false;  // default true
        const uploadUrl = opts.uploadUrl || null;
        // The app's texts (``render/texts.py``), English if absent.
        const texts = opts.texts || {};
        const say = (key, english, holes) => String(texts[key] || english)
            .replace(/\{(\w+)\}/g, (m, k) => (holes && k in holes ? holes[k] : m));

        return {
            // Root element captured from the bz-data expression — the
            // V3 replacement for Alpine's $root / $refs.
            _el: opts.el || null,
            // ── State ──────────────────────────────────────────────
            isDragging: false,
            // ``isGlobalDragActive`` flips true when the user is
            // dragging a file ANYWHERE on the page (from the OS).
            // Every dropzone subscribes via ``@dragenter.window`` so
            // the user can see the drop target highlight from any
            // scroll position. Tracked with a counter because
            // ``dragenter`` / ``dragleave`` fire one per element
            // boundary crossed ; the counter reaches 0 only when the
            // drag truly leaves the window.
            isGlobalDragActive: false,
            _globalDragCounter: 0,
            files: [],
            errors: [],

            // ⚠️ No ``destroy()``: the V3 scope engine has NO unmount
            // hook, so such a method would never run. The previews' blob
            // URLs are revoked in the three places that remove a file
            // (single-file replacement, removeFile, clear). Not handled:
            // the previews of a component removed from the DOM with
            // files still in it, which would take a real unmount hook on
            // the runtime side.

            // ── Validation + add ───────────────────────────────────
            handleFiles(fileList) {
                this.errors = [];
                let incoming = Array.from(fileList);
                let sizeRejected = 0;
                let formatRejected = 0;
                let firstReject = '';

                if (!multiple && incoming.length > 1) {
                    this.errors = this.errors.concat([say('only_one', 'Only one file allowed.')]);
                    incoming = [incoming[0]];
                }
                if (!multiple && this.files.length > 0) {
                    // Replace mode — drop the previous one (and its preview).
                    this.files.forEach((f) => {
                        if (f._preview) URL.revokeObjectURL(f._preview);
                    });
                    this.files = [];
                }
                if (multiple && maxFiles) {
                    const room = maxFiles - this.files.length;
                    if (room <= 0) {
                        this.errors = this.errors.concat(
                            [say('max_reached', 'Maximum {max} files reached.', { max: maxFiles })]);
                        return;
                    }
                    if (incoming.length > room) {
                        this.errors = this.errors.concat([
                            say('over_limit', '{count} files skipped — limit {max} reached.',
                                { count: incoming.length - room, max: maxFiles })
                        ]);
                        incoming = incoming.slice(0, room);
                    }
                }

                const accepted = [];
                for (let i = 0; i < incoming.length; i++) {
                    const f = incoming[i];
                    if (maxSizeMB && f.size > maxSizeMB * 1048576) {
                        sizeRejected += 1;
                        if (!firstReject) firstReject = f.name;
                        continue;
                    }
                    if (!matchesAccept(f, acceptList)) {
                        formatRejected += 1;
                        if (!firstReject) firstReject = f.name;
                        continue;
                    }
                    accepted.push(f);
                }

                if ((sizeRejected || formatRejected) && this.errors.length === 0) {
                    const rejected = sizeRejected + formatRejected;
                    let msg;
                    if (rejected === 1) {
                        msg = sizeRejected
                            ? say('too_large', '{name} — exceeds {size}',
                                  { name: firstReject, size: formatSize(maxSizeMB * 1048576) })
                            : say('wrong_format', '{name} — format not supported', { name: firstReject });
                    } else {
                        let reason;
                        if (sizeRejected && !formatRejected) reason = say('reason_too_large', 'too large');
                        else if (formatRejected && !sizeRejected) reason = say('reason_wrong_format', 'wrong format');
                        else reason = say('reason_size_or_format', 'size or format');
                        msg = say('skipped', '{count} files skipped ({reason}).',
                                  { count: rejected, reason: reason });
                    }
                    this.errors = this.errors.concat([msg]);
                }

                // Build the new entries then reassign ``files`` once (V3
                // signals are identity-compared — an in-place push won't
                // re-render the bz-for list).
                const newEntries = [];
                for (let i = 0; i < accepted.length; i++) {
                    const f = accepted[i];
                    newEntries.push({
                        id: nextId(),
                        file: f,
                        name: f.name,
                        size: f.size,
                        sizeLabel: formatSize(f.size),
                        type: f.type,
                        isImage: isImage(f),
                        _preview: (showPreviews && isImage(f))
                            ? URL.createObjectURL(f)
                            : null,
                        progress: 0,
                        status: 'idle',  // idle | uploading | done | error
                        error: '',
                    });
                }
                this.files = this.files.concat(newEntries);

                this.syncInput();
                this.dispatch('change', {
                    files: this.files.map((e) => e.file),
                    count: this.files.length,
                });

                if (uploadUrl) {
                    for (let i = 0; i < accepted.length; i++) {
                        // Find the entry we just pushed for this file.
                        const entry = this.files.find((e) => e.file === accepted[i]);
                        if (entry) this.uploadOne(entry.id);
                    }
                }
            },

            // Replace one entry (keyed by id) with a patched copy so the
            // keyed bz-for row re-renders (V3 entries aren't deep-reactive).
            _patchFile(id, patch) {
                this.files = this.files.map(
                    (e) => (e.id === id ? Object.assign({}, e, patch) : e),
                );
            },

            // ── Remove ─────────────────────────────────────────────
            removeFile(entry, evt) {
                if (evt) evt.preventDefault();
                if (entry._preview) URL.revokeObjectURL(entry._preview);
                if (entry._xhr) {
                    try { entry._xhr.abort(); } catch (e) {}
                }
                this.files = this.files.filter((e) => e.id !== entry.id);
                this.errors = [];
                this.syncInput();
                this.dispatch('change', {
                    files: this.files.map((e) => e.file),
                    count: this.files.length,
                });
            },

            // Every file out at once — ``ui.message_input`` empties its
            // box once the message has left (message_input.js).
            clear() {
                this.files.forEach((e) => {
                    if (e._preview) URL.revokeObjectURL(e._preview);
                });
                this.files = [];
                this.errors = [];
                this.syncInput();
                this.dispatch('change', { files: [], count: 0 });
            },

            // ── DataTransfer → native input ────────────────────────
            syncInput() {
                if (typeof DataTransfer === 'undefined') return;  // very old browsers
                const dt = new DataTransfer();
                this.files.forEach((entry) => dt.items.add(entry.file));
                const native = this._el && this._el.querySelector('input[type=file]');
                if (native) native.files = dt.files;
            },

            // ── Native input change passthrough ────────────────────
            onNativeChange(evt) {
                if (!evt.isTrusted) return;  // we set .files programmatically too
                if (evt.target.files && evt.target.files.length > 0) {
                    this.handleFiles(evt.target.files);
                }
            },

            // ── Drag-drop (instance-level) ─────────────────────────
            onDragEnter(evt) { evt.preventDefault(); this.isDragging = true; },
            onDragOver(evt)  { evt.preventDefault(); this.isDragging = true; },
            onDragLeave(evt) { evt.preventDefault(); this.isDragging = false; },
            onDrop(evt) {
                evt.preventDefault();
                this.isDragging = false;
                // Drop also tears down the global highlight on every
                // dropzone — the drag is over.
                this._globalDragCounter = 0;
                this.isGlobalDragActive = false;
                if (evt.dataTransfer && evt.dataTransfer.files) {
                    this.handleFiles(evt.dataTransfer.files);
                }
            },

            // ── Drag-drop (window-level, "page is the target") ─────
            // The handlers below subscribe to ``dragenter`` /
            // ``dragleave`` / ``drop`` on the window, so a drag from
            // the OS — anywhere on the page — surfaces this dropzone
            // as a candidate target. ``isGlobalDragActive`` flips
            // true while the drag is in flight ; the wrapper's
            // ``:class`` adds ``dropzone_global_drag`` (ring + glow)
            // so the user can see where to drop.
            //
            // ``dragenter`` / ``dragleave`` fire one PER element
            // boundary crossed (drag over a button → dragenter,
            // drag off it → dragleave). We use a counter to know
            // when the drag truly entered or left the window.
            onWindowDragEnter(evt) {
                if (!this._dragCarriesFiles(evt)) return;
                this._globalDragCounter += 1;
                this.isGlobalDragActive = true;
            },
            onWindowDragLeave(evt) {
                if (!this._dragCarriesFiles(evt)) return;
                this._globalDragCounter -= 1;
                if (this._globalDragCounter <= 0) {
                    this._globalDragCounter = 0;
                    this.isGlobalDragActive = false;
                }
            },
            onWindowDrop() {
                this._globalDragCounter = 0;
                this.isGlobalDragActive = false;
            },

            _dragCarriesFiles(evt) {
                // ``dataTransfer.types`` is a DOMStringList containing
                // 'Files' for OS-originated drags ; for in-page drags
                // it'll be 'text/plain' or similar. Filter so we don't
                // highlight on a Notion-style block drag.
                const types = evt.dataTransfer && evt.dataTransfer.types;
                if (!types) return false;
                for (let i = 0; i < types.length; i++) {
                    if (types[i] === 'Files') return true;
                }
                return false;
            },

            // ── Paste (``paste=True``) ─────────────────────────────
            // Called from the root's ``bz-init``, so ``this`` is the
            // reactive scope. The listener sits on the enclosing
            // ``<form>`` — a paste fires on the FOCUSED element, and the
            // one focused is the field the person writes in, not the
            // picker — or on the root when there is no form. A paste
            // that carries files adds them as a pick would; one that
            // carries text is left to the field (``filesOfPaste``).
            // No unmount hook in V3 (cf. above): a root that has left
            // the DOM — a zone redrawn — unsubscribes at its next paste.
            // The form around the field has sent its files: the list
            // empties. Otherwise a sent file would keep its pill under the
            // button, and a second send would ship it again. Only a
            // SUCCESSFUL send of that form: a refusal
            // (4xx, 5xx) keeps what was picked. Same unsubscribe as the
            // paste below, at the next send after the root has left.
            watchForm() {
                const self = this;
                const root = self._el;
                const form = root && root.closest('form');
                if (!form) return;
                function onSent(evt) {
                    if (!root.isConnected) {
                        form.removeEventListener('htmx:afterRequest', onSent);
                        return;
                    }
                    const d = evt.detail || {};
                    if (d.elt === form && d.successful && self.files.length) self.clear();
                }
                form.addEventListener('htmx:afterRequest', onSent);
            },

            watchPaste() {
                const self = this;
                const root = self._el;
                if (!root) return;
                const host = root.closest('form') || root;
                function onPaste(evt) {
                    if (!root.isConnected) {
                        host.removeEventListener('paste', onPaste);
                        return;
                    }
                    const native = root.querySelector('input[type=file]');
                    if (native && native.disabled) return;
                    const pasted = filesOfPaste(evt.clipboardData);
                    if (pasted.length === 0) return;
                    evt.preventDefault();
                    self.handleFiles(pasted);
                }
                host.addEventListener('paste', onPaste);
            },

            // ── Browse-trigger click (delegated to native input) ──
            openPicker() {
                const native = this._el && this._el.querySelector('input[type=file]');
                if (native) native.click();
            },

            // ── Async upload (one file, keyed by id) ───────────────
            uploadOne(id) {
                const entry0 = this.files.find((e) => e.id === id);
                if (!entry0) return;
                const file = entry0.file;
                this._patchFile(id, { status: 'uploading', progress: 0, error: '' });
                this.dispatch('upload-start', { file: file });

                const xhr = new XMLHttpRequest();
                this._patchFile(id, { _xhr: xhr });
                xhr.upload.addEventListener('progress', (e) => {
                    if (e.lengthComputable) {
                        const pct = Math.round((e.loaded / e.total) * 100);
                        this._patchFile(id, { progress: pct });
                        this.dispatch('upload-progress', { file: file, progress: pct });
                    }
                });
                xhr.addEventListener('load', () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        this._patchFile(id, { status: 'done', progress: 100 });
                        this.dispatch('upload-complete', {
                            file: file,
                            response: xhr.responseText,
                            status: xhr.status,
                        });
                    } else {
                        this._patchFile(id, { status: 'error', error: 'HTTP ' + xhr.status });
                        this.dispatch('upload-error', {
                            file: file,
                            error: 'HTTP ' + xhr.status,
                            status: xhr.status,
                        });
                    }
                });
                xhr.addEventListener('error', () => {
                    this._patchFile(id, { status: 'error', error: say('network_error', 'Network error') });
                    this.dispatch('upload-error', {
                        file: file,
                        error: say('network_error', 'Network error'),
                        status: 0,
                    });
                });
                const form = new FormData();
                form.append('file', file, entry0.name);
                xhr.open('POST', uploadUrl);
                // Bretzel's CSRF middleware is ALWAYS active and
                // protects every POST outside ``/_bretzel/action/*``.
                // Without this header, the async upload takes a 403 — so
                // ``upload_url=`` could work in NO app, the framework
                // rejecting its own component. Same source and same
                // header as the bridge (bridge.js).
                if ($bz._csrf) {
                    xhr.setRequestHeader('X-Bretzel-CSRF', $bz._csrf);
                }
                xhr.send(form);
            },

            // ── Dispatch helper — kebab DOM events on the root ─────
            dispatch(name, detail) {
                if (!this._el) return;
                this._el.dispatchEvent(new CustomEvent(name, {
                    detail: detail,
                    bubbles: true,
                }));
            },
        };
    }

    window.$bz.fileUpload = {
        makeScope: makeScope, formatSize: formatSize, filesOfPaste: filesOfPaste,
    };
})();

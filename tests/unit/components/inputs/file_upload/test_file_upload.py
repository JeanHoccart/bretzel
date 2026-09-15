"""Unit tests for :class:`bretzel.components.inputs.file_upload.FileUpload`."""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.inputs.file_upload import FileUpload
from bretzel.core.serialize import serialize
from bretzel.state import field


def _render(*args, **kwargs) -> str:
    with render_isolated():
        return serialize(FileUpload(*args, **kwargs).render())


# ───────────────────────────────────────────────────────────────────
# Structure
# ───────────────────────────────────────────────────────────────────


class TestStructure:
    def test_root_is_bz_file_upload_wrapper(self) -> None:
        html = _render()
        assert "bz-file-upload" in html

    def test_root_has_runtime_factory_scope(self) -> None:
        html = _render()
        # Component delegates state + behaviour to the runtime factory
        # (cf. bretzel/runtime/_src/08_file_upload.js) — keeps each
        # instance's bz-data short.
        assert "$bz.fileUpload.makeScope(" in html

    def test_scope_captures_root_via_el(self) -> None:
        # V3 scope methods have no $root / $refs — the factory captures
        # its root element from ``el: $el`` in the bz-data expression.
        html = _render()
        assert "el: $el" in html

    def test_hidden_native_file_input(self) -> None:
        html = _render()
        # The hidden ``<input type="file">`` is the form-data carrier ;
        # the dropzone / button is purely decorative and dispatches
        # ``input.click()`` via ``openPicker()``.
        assert '<input type="file"' in html
        assert 'bz-ref="nativeInput"' in html
        # sr-only keeps it in the tab order on screen readers but
        # invisible to sighted users.
        assert "sr-only" in html


# ───────────────────────────────────────────────────────────────────
# Variants
# ───────────────────────────────────────────────────────────────────


class TestVariants:
    def test_default_variant_is_dropzone(self) -> None:
        html = _render()
        # The dropzone wrapper carries the dashed border + drag
        # handlers ; the button variant lacks them.
        assert "border-dashed" in html
        assert "bz-on:dragenter=" in html
        assert "bz-on:drop=" in html

    def test_button_variant_skips_drop_handlers(self) -> None:
        html = _render(variant="button")
        assert "border-dashed" not in html
        assert "bz-on:dragenter" not in html
        assert "bz-on:drop" not in html

    def test_invalid_variant_raises(self) -> None:
        from bretzel.components.base import ComponentDefinitionError
        with pytest.raises(ComponentDefinitionError):
            FileUpload(variant="oops")

    def test_dropzone_keyboard_accessible(self) -> None:
        # Enter / Space open the file picker so keyboard users don't
        # need to tab through to the hidden native input. V3 has no
        # per-key modifier — one ``bz-on:keydown`` guards on $event.key.
        html = _render()
        assert "bz-on:keydown=" in html
        assert "openPicker()" in html
        # role=button + aria-label so screen readers announce the
        # control as activatable.
        assert 'role="button"' in html
        assert "aria-label=" in html

    def test_dropzone_default_label(self) -> None:
        html = _render()
        assert "Drop files here or click to browse" in html

    def test_button_default_label(self) -> None:
        html = _render(variant="button")
        assert "Upload file" in html

    def test_custom_label(self) -> None:
        html = _render(label="Attach a document")
        assert "Attach a document" in html


# ───────────────────────────────────────────────────────────────────
# Validation props (passed to the JS factory)
# ───────────────────────────────────────────────────────────────────


class TestValidationPropsForwarded:
    def test_accept_as_string_lands_on_native_input(self) -> None:
        html = _render(accept="image/*,.pdf")
        assert 'accept="image/*,.pdf"' in html

    def test_accept_as_list_normalised_to_comma_string(self) -> None:
        html = _render(accept=["image/*", ".pdf"])
        assert 'accept="image/*,.pdf"' in html

    def test_multiple_lands_on_native_input(self) -> None:
        html = _render(multiple=True)
        assert "multiple" in html

    def test_max_size_mb_passed_to_factory_opts(self) -> None:
        html = _render(max_size_mb=5)
        # opts blob is JSON-stringified into the bz-data factory call.
        assert "maxSizeMB" in html
        assert "5" in html

    def test_max_files_passed_to_factory_opts(self) -> None:
        html = _render(multiple=True, max_files=4)
        assert "maxFiles" in html

    def test_dropzone_shows_accept_hint(self) -> None:
        html = _render(accept="image/*")
        assert "Accepted: image/*" in html

    def test_dropzone_shows_max_size_hint(self) -> None:
        html = _render(max_size_mb=5)
        assert "Max size: 5 MB" in html

    def test_dropzone_shows_multiple_hint(self) -> None:
        html = _render(multiple=True)
        assert "Multiple files allowed" in html

    def test_dropzone_shows_max_files_cap_in_hint(self) -> None:
        html = _render(multiple=True, max_files=4)
        assert "up to 4" in html


# ───────────────────────────────────────────────────────────────────
# Upload mode (form vs async)
# ───────────────────────────────────────────────────────────────────


class TestUploadMode:
    def test_default_is_form_mode_no_upload_url(self) -> None:
        html = _render()
        assert "uploadUrl" not in html

    def test_async_mode_passes_upload_url_to_factory(self) -> None:
        html = _render(upload_url="/api/upload")
        assert "uploadUrl" in html
        assert "/api/upload" in html

    def test_per_file_progress_bar_template_present(self) -> None:
        html = _render(upload_url="/api/upload")
        # The per-file card carries a ``role="progressbar"`` div that
        # bz-show-s during ``uploading`` — present even when no file is
        # picked yet (it's the template).
        assert 'role="progressbar"' in html
        assert "entry.progress" in html


# ───────────────────────────────────────────────────────────────────
# Disabled / required
# ───────────────────────────────────────────────────────────────────


class TestDisabledRequired:
    def test_disabled_propagates_to_native_input(self) -> None:
        html = _render(disabled=True)
        # ``disabled`` lands on the native input AND drops the wrapper
        # from the tab order (tabindex="-1") with ``aria-disabled``.
        assert "disabled" in html
        assert 'tabindex="-1"' in html
        assert 'aria-disabled="true"' in html

    def test_required_propagates_to_native_input(self) -> None:
        html = _render(required=True)
        assert "required" in html

    def test_required_binding_is_refused(self) -> None:
        # ``required`` n'est plus bindable (règle « driver client, sinon
        # serveur » figée 2026-07-16 : la contrainte ne change qu'au
        # re-render serveur → @refreshable, pas de driver client). Un
        # binding y lève donc ComponentUsageError. La valeur littérale
        # reste supportée (cf. test_required_propagates_to_native_input).
        from bretzel.components.base.attrs import ComponentUsageError
        from bretzel.components.base.testing import render_isolated
        from bretzel.state.scopes.client import ClientState, rendering_scope

        class S(ClientState):
            req: bool = field(default=True)

        with render_isolated(), rendering_scope(), pytest.raises(ComponentUsageError):
            FileUpload(required=S().req)


# ───────────────────────────────────────────────────────────────────
# File-list rendering (template)
# ───────────────────────────────────────────────────────────────────


class TestFileListTemplate:
    def test_bzfor_iterates_file_entries_keyed(self) -> None:
        html = _render()
        # ``files`` is the array of entries managed by the factory ;
        # each entry has a stable ``id`` keyed inside the bz-for
        # attribute so removals don't shuffle the DOM. The serializer
        # HTML-escapes ``=`` to ``=`` inside attribute values.
        assert ("bz-for=" in html)
        assert ("entry in files" in html)
        assert (":key=entry.id" in html
                or ":key=entry.id" in html)

    def test_remove_button_per_file(self) -> None:
        html = _render()
        assert 'aria-label="Remove file"' in html
        assert "removeFile(entry, $event)" in html

    def test_image_preview_with_blob_url(self) -> None:
        html = _render()
        # The factory creates ``URL.createObjectURL(file)`` for
        # image/* entries — the <img> binds bz-attr:src to
        # entry._preview.
        assert "bz-attr:src=" in html
        assert "entry._preview" in html

    def test_show_previews_false_skipped_in_factory_opts(self) -> None:
        html = _render(show_previews=False)
        # show_previews=False sets ``showPreviews: false`` in the opts
        # blob ; the factory then skips ``URL.createObjectURL``.
        assert "showPreviews" in html
        assert "false" in html


# ───────────────────────────────────────────────────────────────────
# Bindable contract
# ───────────────────────────────────────────────────────────────────


class TestBindableContract:
    def test_bindable_props(self) -> None:
        # Surface resserrée 2026-07-16 (règle « driver client, sinon
        # serveur ») : seul ``disabled`` a un driver client (activer
        # l'upload après une checkbox). ``multiple`` / ``accept`` /
        # ``required`` sont de la config qui ne bouge qu'au re-render
        # serveur → @refreshable, donc ∅ (cf. client-reactive-surface.md).
        assert FileUpload.BINDABLE_PROPS == ("disabled",)
        # Invariant structurel : toute clé de carrier DOIT être bindable,
        # sinon elle est morte.
        assert set(FileUpload.BINDABLE_CARRIERS) <= set(
            FileUpload.BINDABLE_PROPS
        )

    def test_value_not_bindable(self) -> None:
        # File data cannot flow through ClientBinding (browser
        # restricts programmatic FileList writes outside DataTransfer).
        assert "value" not in FileUpload.BINDABLE_PROPS

    def test_events_listed(self) -> None:
        assert FileUpload.EVENTS == (
            "change",
            "upload_start", "upload_complete", "upload_error",
            "focus", "blur",
        )


# ───────────────────────────────────────────────────────────────────
# Size axis — each palier produces distinct classes
# ───────────────────────────────────────────────────────────────────


class TestSizeAxis:
    def test_each_palier_distinct(self) -> None:
        """Each ``size=`` palier must produce a different padding /
        icon / text class blob — otherwise the prop is API noise."""
        rendered = {sz: _render(size=sz) for sz in
                    ("xs", "sm", "md", "lg", "xl")}
        # Pull the dropzone wrapper class blobs out of each render
        # and check no two are identical (would mean the size= prop
        # collapses two paliers to the same visual).
        import re
        blobs = {}
        for sz, html in rendered.items():
            m = re.search(r'<div class="([^"]+rounded-box[^"]+)"', html)
            assert m, f"dropzone wrapper class not found in size={sz}"
            blobs[sz] = m.group(1)
        for a, b in (("xs", "sm"), ("sm", "md"), ("md", "lg"),
                     ("lg", "xl")):
            assert blobs[a] != blobs[b], (
                f"size={a} and size={b} produce identical classes — "
                f"the size axis is broken."
            )

    def test_dropzone_padding_scales_with_size(self) -> None:
        # Spot-check : xs has the smallest vertical padding, xl the
        # largest. ``py-3`` < ``py-16``.
        assert "py-3" in _render(size="xs")
        assert "py-16" in _render(size="xl")

    def test_button_padding_scales_with_size(self) -> None:
        assert "h-7" in _render(variant="button", size="xs")
        assert "h-14" in _render(variant="button", size="xl")


# ───────────────────────────────────────────────────────────────────
# Tab order
# ───────────────────────────────────────────────────────────────────


class TestTabOrder:
    def test_native_input_not_in_tab_order(self) -> None:
        """The native ``<input type="file">`` is sr-only — but sr-only
        alone does NOT remove it from the tab order. Without an
        explicit ``tabindex="-1"`` + ``aria-hidden="true"``, keyboard
        users tab to the wrapper AND to the input (two stops + a
        scroll jolt as the browser tries to scroll the off-screen
        input into view).
        """
        html = _render()
        # Find the native input opening tag.
        import re
        m = re.search(r'<input type="file"[^>]*>', html)
        assert m, "native file input not found"
        tag = m.group(0)
        assert 'tabindex="-1"' in tag
        assert 'aria-hidden="true"' in tag

    def test_wrapper_is_the_focus_host(self) -> None:
        # The wrapper is the canonical focus host with tabindex=0,
        # role=button, and aria-label. Enter / Space proxy to the
        # native input via openPicker().
        html = _render()
        assert 'tabindex="0"' in html
        assert 'role="button"' in html


# ───────────────────────────────────────────────────────────────────
# Compact mode (dropzone shrinks when files exist)
# ───────────────────────────────────────────────────────────────────


class TestCompactMode:
    def test_both_empty_states_rendered(self) -> None:
        # The dropzone renders TWO empty states, swapped via
        # ``bz-show`` based on ``files.length`` :
        #   - full when length === 0 (canonical hero state)
        #   - compact when length > 0 ("Drop more files" hint)
        # The serializer HTML-escapes ``===`` → ``===``
        # and ``>`` → ``&gt;`` ; check either form.
        html = _render()
        assert ("files.length === 0" in html
                or "files.length === 0" in html)
        assert ("files.length > 0" in html
                or "files.length &gt; 0" in html)

    def test_compact_label_for_multiple(self) -> None:
        html = _render(multiple=True)
        assert "Drop more files here" in html

    def test_compact_label_for_single(self) -> None:
        html = _render()
        assert "Drop a different file to replace" in html

    def test_wrapper_class_includes_files_swap(self) -> None:
        # The ``bz-class`` expression on the wrapper toggles between
        # full padding and compact padding based on files.length.
        # ``>`` HTML-escapes to ``&gt;`` in the attribute payload.
        html = _render()
        assert ("files.length > 0 ?" in html
                or "files.length &gt; 0 ?" in html)


# ───────────────────────────────────────────────────────────────────
# Global drag-over-page detection
# ───────────────────────────────────────────────────────────────────


class TestGlobalDragDetection:
    def test_window_drag_listeners_wired_via_onwindow(self) -> None:
        # Alpine's ``@dragenter.window`` / ``@dragleave.window`` /
        # ``@drop.window`` have no V3 directive equivalent — the three
        # window subscriptions are registered at ``bz-init`` through
        # ``$bz.helpers.onWindow`` so every dropzone learns that the
        # user is dragging a file ANYWHERE on the page.
        html = _render()
        assert "bz-init=" in html
        assert "$bz.helpers.onWindow(" in html
        assert "onWindowDragEnter" in html
        assert "onWindowDragLeave" in html
        assert "onWindowDrop" in html

    def test_global_drag_class_layered(self) -> None:
        # The wrapper's reactive ``bz-class`` adds the global highlight
        # ONLY when (a) the user is dragging files globally AND
        # (b) this dropzone isn't already the local target.
        html = _render()
        assert "isGlobalDragActive" in html
        assert "isDragging" in html

    def test_global_highlight_uses_bz_class_not_bz_attr_class(self) -> None:
        # ``bz-class`` MERGES onto the static class= (Alpine ``:class``
        # semantics) ; ``bz-attr:class`` would REPLACE the whole
        # attribute and wipe the dropzone's base classes. Regression
        # guard for the V3 ``:class`` → ``bz-class`` trap.
        html = _render()
        assert "bz-class=" in html
        assert "bz-attr:class=" not in html


# ───────────────────────────────────────────────────────────────────
# Remove button styling
# ───────────────────────────────────────────────────────────────────


class TestRemoveButtonStyling:
    def test_remove_button_floats_outside_card(self) -> None:
        # The ✕ button uses negative offsets so it floats OUTSIDE
        # the card corner — solid background, high contrast, never
        # overlaps the thumb (which was the V1 problem).
        html = _render()
        assert "-top-2" in html
        assert "-right-2" in html

    def test_remove_button_solid_not_transparent(self) -> None:
        # 2026 pattern : solid background (bg-text → opaque on any
        # background colour). Transparent + shadow was illegible on
        # photos.
        html = _render()
        # bg-text is fully opaque ; no /90 modifier.
        assert "bg-text " in html or 'bg-text\"' in html


# ───────────────────────────────────────────────────────────────────
# Strip scrollbar
# ───────────────────────────────────────────────────────────────────


class TestStripScrollbar:
    def test_strip_uses_custom_scrollbar(self) -> None:
        # We override the default browser scrollbar so we don't end
        # up with a double scrollbar inside Card. The strip uses a
        # thin themed bar that only shows on hover.
        html = _render()
        assert "::-webkit-scrollbar" in html

    def test_strip_overflow_y_hidden(self) -> None:
        # Without ``overflow-y: hidden`` the strip can grow a vertical
        # scrollbar of its own when a per-file card stretches — that
        # was the second bar in the "double scrollbar" report.
        html = _render()
        assert "overflow-y-hidden" in html


# ───────────────────────────────────────────────────────────────────
# FOUC pre-stamp (V3 bz-show branches that start hidden at SSR)
# ───────────────────────────────────────────────────────────────────


class TestFoucPrestamp:
    def test_file_list_strip_prestamped_hidden(self) -> None:
        # The file-list strip ``bz-show="files.length > 0"`` is falsy at
        # first paint — pre-stamp ``display:none`` so it doesn't flash
        # before the runtime's first effect.
        html = _render()
        # The strip carries the custom scrollbar classes ; its opening
        # div must include display:none in the style.
        assert "display:none" in html

    def test_full_empty_state_not_prestamped(self) -> None:
        # ``files.length === 0`` is truthy at SSR (no files) — the full
        # empty state must NOT be pre-stamped hidden, otherwise the
        # hero state flashes blank before the runtime boots.
        html = _render()
        import re
        # Locate the full empty-state div (carries
        # ``bz-show="files.length === 0"``, serializer-escaped) and
        # confirm its opening tag does NOT carry display:none.
        m = re.search(
            r'<div class="[^"]*"[^>]*bz-show="files\.length '
            r'(?:===|===) 0"[^>]*>',
            html,
        )
        assert m, "full empty-state div not found"
        assert "display:none" not in m.group(0)


# ───────────────────────────────────────────────────────────────────
# Routage des events serveur (forme callable)
# ───────────────────────────────────────────────────────────────────


class TestCallableEventRouting:
    """Un handler callable doit atterrir sur un élément qui FIRE l'event.

    Signalé par l'utilisateur : ``on_focus=`` / ``on_blur=`` callables ne
    partaient jamais, et ``on_change=`` partait DEUX fois.
    """

    @staticmethod
    def _handler(*args: object, **kwargs: object) -> None:
        return None

    def _attrs_of_tag_carrying(self, html: str, attr: str) -> dict[str, str]:
        for m in re.finditer(r"<(\w+)\b([^>]*)>", html):
            found = dict(re.findall(r'([\w:\-]+)="([^"]*)"', m.group(2)))
            if attr in found:
                return found
        return {}

    @pytest.mark.parametrize("event", ["focus", "blur"])
    def test_callable_focus_blur_ride_a_focusable_element(
        self, event: str,
    ) -> None:
        """``focus``/``blur`` ne BULLENT pas — la racine ne les verra jamais.

        La racine est un ``<div>`` sans ``tabindex``. Un
        ``hx-trigger="focus"`` posé dessus est du code mort silencieux :
        pas d'erreur, pas de log, le handler ne tourne simplement jamais.
        ``select.py`` avait déjà corrigé ce bug chez lui.
        """
        html = _render(**{f"on_{event}": self._handler})
        host = self._attrs_of_tag_carrying(html, "hx-trigger")
        assert host, f"aucun élément ne porte hx-trigger pour on_{event}"
        assert host.get("hx-trigger") == event
        assert host.get("tabindex") == "0", (
            f"le bundle HTMX de on_{event} est posé sur un élément non "
            f"focusable (tabindex={host.get('tabindex')!r}) — il ne peut "
            f"pas fire. Attributs : {host}"
        )

    def test_native_change_does_not_bubble_to_the_root(self) -> None:
        """Sinon : un POST pour le change natif + un pour celui du slab.

        La racine porte ``hx-trigger="change"`` et contient l'input
        natif. Le ``change`` de l'input bulle jusqu'à elle, PUIS le slab
        y dispatche le sien — deux events, deux POST pour une seule
        sélection de fichier.
        """
        html = _render(on_change=self._handler)
        native = self._attrs_of_tag_carrying(html, 'bz-ref')
        assert native.get("type") == "file", "input natif introuvable"
        assert "stopPropagation" in native.get("bz-on:change", ""), (
            "l'input natif ne stoppe pas son `change` : il bulle vers la "
            "racine qui écoute déjà celui du slab → double POST."
        )

    def test_callable_change_stays_on_the_root(self) -> None:
        """Le slab dispatche ``change`` sur la racine — le bundle y reste."""
        html = _render(on_change=self._handler)
        host = self._attrs_of_tag_carrying(html, "hx-trigger")
        assert host.get("hx-trigger") == "change"
        assert host.get("tabindex") is None, (
            "le bundle change a été relocalisé sur le wrapper focusable ; "
            "il doit rester sur la racine, où le slab dispatche."
        )


# ───────────────────────────────────────────────────────────────────
# list= — les deux présentations de la liste
# ───────────────────────────────────────────────────────────────────


class TestListPresentations:
    """``list=`` est un axe INDÉPENDANT de ``variant=`` : celui-ci habille
    le déclencheur, celui-là la liste des fichiers déposés.

    Les différences structurelles sont gatées catalogue-large par
    ``tests/consistency/test_list_presentations_restructure.py`` ; ici on
    épingle l'indépendance des deux axes et le défaut."""

    def test_tiles_is_the_default(self) -> None:
        assert _render() == _render(list="tiles")

    def test_chips_drop_the_thumbnail_node(self) -> None:
        """Pas masqué — non émis. Un nœud masqué coûterait quand même son
        ``URL.createObjectURL`` côté runtime."""
        assert "<img" in _render(list="tiles")
        assert "<img" not in _render(list="chips")

    def test_chips_remove_button_leaves_the_corner(self) -> None:
        """La raison d'être de la présentation : le × de la tuile est un
        badge de coin (``absolute -top-2 -right-2``) ; dans une puce il
        doit vivre dans le flux."""
        assert "-top-2" in _render(list="tiles")
        assert "-top-2" not in _render(list="chips")

    def test_the_two_axes_are_independent(self) -> None:
        """Les quatre combinaisons se construisent et se rendent — si
        ``list=`` n'était lu que dans la branche ``dropzone``, la moitié
        du tableau serait morte sans que rien ne le dise."""
        for variant in ("dropzone", "button"):
            for presentation in ("tiles", "chips"):
                out = _render(variant=variant, list=presentation)
                assert len(out) > 500, f"{variant}/{presentation} vide"
                has_corner = "-top-2" in out
                assert has_corner == (presentation == "tiles"), (
                    f"variant={variant} list={presentation} : le × de coin "
                    f"ne suit pas ``list=``, donc l'axe est mal câblé."
                )

    def test_an_unknown_presentation_raises(self) -> None:
        from bretzel.components.base import ComponentDefinitionError

        with pytest.raises(ComponentDefinitionError, match="zznope"):
            _render(list="zznope")

    def test_accept_still_takes_a_python_list(self) -> None:
        """⚠️ Le kwarg ``list=`` MASQUE le builtin ``list`` dans le corps
        d'``__init__``. Sans ``_SEQUENCE_TYPES``, ce cas levait
        ``isinstance() arg 2 must be a type`` — à trois cents lignes du
        nom fautif. Mesuré en écrivant la prop."""
        out = _render(accept=["image/*", ".pdf"], list="chips")
        assert 'accept="image/*,.pdf"' in out

"""``FileUpload`` — dropzone or compact-button file picker.

Deux axes INDÉPENDANTS : ``variant=`` habille le DÉCLENCHEUR,
``list=`` la liste des fichiers déposés.

- ``list="tiles"`` (défaut) — une tuile par fichier : vignette, nom,
  taille, et un × en badge de coin. La forme « pièces jointes ».
- ``list="chips"`` — une puce par fichier : icône, nom, × **inline**,
  qui s'enroulent sur plusieurs lignes. La forme « composer ».

Ce n'est pas un axe de style : les deux structures diffèrent dans le
DOM (la puce n'émet ni vignette ni taille, et son × est dans le flux).
Aucun override de ``slots=`` ne fait passer de l'un à l'autre.

Two trigger variants share the same file-management plumbing :

- ``variant="dropzone"`` (default) — large dashed area, drop OR click
  anywhere on the zone OR press Enter / Space when focused. Modern
  Drive / Notion / Linear shape.
- ``variant="button"`` — compact inline trigger that just opens the
  native file picker, no drop affordance. Use it when the page already
  has a primary call-to-action and you want a secondary attachment
  control.

State + behaviour live in a single runtime scope factory at
``bretzel/runtime/_src/08_file_upload.js`` ::

    bz-data="$bz.fileUpload.makeScope({el: $el, ...opts})"

The factory owns drag state, the file list (each entry carries the
raw ``File`` + UI status), validation (``accept`` / ``max_size_mb`` /
``max_files`` / ``multiple``), DataTransfer sync to the hidden native
input so parent ``<form>`` submits exactly what's displayed, image
preview thumbnails via ``URL.createObjectURL``, and the optional
async upload mode (XHR per file with progress events).

Two upload modes :

- **Form mode** (default) — files just accumulate in the hidden
  ``<input type="file">``. Submit the surrounding ``<form>`` and the
  browser sends each file as multipart. No JS upload, no progress.
- **Async mode** (set ``upload_url=``) — each accepted file is POSTed
  immediately via XHR. Per-file progress bar renders below the
  thumbnail ; ``upload_complete`` fires server-side per file.

Events emitted (the slab dispatches kebab-case DOM events that bubble
to the root) :

- ``change``           — file list changed (added / removed)
- ``upload_start``     — async mode : XHR sent for one file
- ``upload_complete``  — async mode : server returned 2xx
- ``upload_error``     — async mode : 4xx / 5xx or network error
- ``focus`` / ``blur`` — relayed from the focusable wrapper

Note : ``upload_progress`` exists as a DOM event but is NOT a declared
component event and is never bridged to the server — it would melt the
wire (one POST every tick). The fill bar reads the entry's reactive
``progress`` field directly.

Runtime notes :

- The opts blob passes ``el: $el`` so the scope captures its root
  (scope methods have no ``$root`` / ``$refs`` / ``$dispatch``) — the
  factory's ``querySelector`` + every ``dispatch()`` ride off it.
- ``bz-on`` carries no modifier grammar, so ``.prevent`` / ``.stop`` are
  inlined into the expression bodies.
- Window-level drag highlight has no per-element equivalent — the three
  window subscriptions are registered once at ``bz-init`` via
  ``$bz.helpers.onWindow`` (page-scoped, unsubscribe dropped).
- Reactive class uses ``bz-class`` (MERGE onto static ``class=``), never
  ``bz-attr:class`` (which REPLACES).
- FOUC ``display:none`` pre-stamps on branches hidden at SSR (error
  panel, compact empty state, file-list strip).
- Server-callable ``on_change`` / ``on_upload_*`` keep their HTMX bundle
  on the root — the slab dispatches on the root and events bubble. The
  ``upload_*`` names are renamed to kebab (the slab dispatches
  ``upload-start`` etc.). ``on_focus`` / ``on_blur`` relocate onto the
  focusable wrapper — **dans les deux formes** (string ET callable) :
  ``focus``/``blur`` ne bullent pas, donc un ``hx-trigger`` posé sur la
  racine ne partirait jamais.
- Le ``change`` NATIF de l'input caché est stoppé (``stopPropagation``) :
  il bulle sinon jusqu'à la racine, qui écoute déjà le ``change`` que le
  slab y dispatche — deux events, donc deux POST pour une sélection.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    reject_component,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    SERVER_ACTION_ATTRS,
    activate_keydown,
    dismiss_button,
    trigger_event,
)
from bretzel.components.inputs.file_upload.theme import FILE_UPLOAD_THEME
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as _TextNode
from bretzel.render import text

# Python event names use underscores ; the slab dispatches kebab-case
# DOM events. ``change`` / ``focus`` / ``blur`` are already kebab-safe ;
# only the ``upload_*`` family needs renaming (both the ``bz-on:`` string
# form and the server-callable ``hx-trigger`` value).
_KEBAB_EVENTS = {
    "upload_start": "upload-start",
    "upload_complete": "upload-complete",
    "upload_error": "upload-error",
}

# Enter / Space ouvrent le sélecteur. Le garde (trois noms de touche + la
# cible) vit dans ``_wiring.activate_keydown`` — ce fichier était le seul
# des trois sites à gérer le legacy ``Spacebar``, et le seul à NE PAS
# garder la cible.
_ACTIVATE_KEYDOWN = activate_keydown("openPicker();")

#: Les présentations de la liste de fichiers — ``list=``.
#:
#: Ce n'est PAS un axe de style : les deux structures diffèrent dans le
#: DOM. La tuile est une colonne avec vignette et un × en badge de coin
#: (``absolute -top-2 -right-2``) ; la puce est une ligne sans vignette,
#: dont le × est **inline**. Aucun override de ``slots=`` ne fait passer
#: de l'un à l'autre — mesuré le 2026-08-17 : +78 px après avoir réécrit
#: cinq slots, et le × flottait toujours. C'est la thèse « le thème
#: RESTYLE, il ne RESTRUCTURE pas ».
#:
#: Pourquoi deux présentations livrées plutôt qu'une échappatoire : la
#: liste est peuplée par le JS (``<template bz-for>`` cloné au dépôt de
#: fichier), donc ``COLLECTION_OWNER = "client"`` — ni des enfants Python
#: ni un rappel Python ne l'atteignent. Cf. ``Component.COLLECTION_OWNER``.
LIST_PRESENTATIONS: tuple[str, ...] = ("tiles", "chips")

#: ⚠️ Le kwarg public s'appelle ``list=``, donc il MASQUE le builtin
#: ``list`` dans le corps d'``__init__``. Les types séquence y sont donc
#: lus via cette constante — sinon ``isinstance(accept, (list, tuple))``
#: lève ``arg 2 must be a type`` sur la string ``"tiles"``, à trois cents
#: lignes du nom fautif. (Mesuré en écrivant la prop.)
_SEQUENCE_TYPES: tuple[type, ...] = (list, tuple)

#: Les slots que la présentation « chips » substitue à ceux des tuiles.
#: Table finie et littérale des DEUX côtés — jamais un nom assemblé :
#: une classe Tailwind que rien n'écrit en toutes lettres n'atteint pas
#: le CSS compilé (memory ``assembled_tailwind_class_dev_only``). Ici
#: c'est le NOM DE SLOT qu'on choisit, pas la classe, et les deux jeux
#: de classes sont écrits en entier dans le thème.
_CHIP_SLOTS: dict[str, str] = {
    "file_list": "chip_list",
    "file_item": "chip_item",
    "file_icon": "chip_icon",
    "file_name": "chip_name",
    "file_status_done": "chip_status_done",
    "file_status_error": "chip_status_error",
    "file_progress_bar": "chip_progress_bar",
    "remove_btn": "chip_remove_btn",
}


class FileUpload(Component):
    """Dropzone or compact-button file picker."""

    THEME: ClassVar[dict[str, Any]] = FILE_UPLOAD_THEME
    THEME_KEY: ClassVar[str] = "file_upload"
    IS_CONTAINER: ClassVar[bool] = False
    #: C'est le NAVIGATEUR qui possède la liste : elle est peuplée au
    #: dépôt de fichier, en clonant un ``<template bz-for>``. Ni des
    #: enfants Python ni un rappel ``render=`` ne l'atteignent — ils
    #: s'exécuteraient au rendu serveur, quand la liste est vide.
    #:
    #: Le mécanisme que l'auteur obtient à la place est donc
    #: ``list="tiles" | "chips"`` : deux présentations LIVRÉES, pas une
    #: échappatoire. Cf. ``Component.COLLECTION_OWNER`` et
    #: :data:`LIST_PRESENTATIONS`.
    COLLECTION_OWNER: ClassVar[str | None] = "client"
    # ``value`` is never bindable : browsers forbid programmatic
    # ``input.files`` assignment outside a DataTransfer, and the FileList
    # shape isn't serialisable for server-side state. Only ``disabled``
    # earns a client binding (flips live from client state) ; ``multiple``
    # / ``accept`` / ``required`` are config that only changes on a server
    # re-render (@refreshable), so they stay static per the
    # bindable-surface rule (cf. ``client-reactive-surface.md``).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)
    # The bindable ``disabled`` lives on the native ``<input type="file">``
    # (the wrapper ``<div>`` is just layout). The base walks the rendered
    # tree post-render and forwards the binding onto the element carrying
    # ``bz-ref="nativeInput"`` — no manual ``forward_binding`` needed.
    # Cf. ``traps.md`` § "wrapper-vs-carrier". Every carrier key MUST sit
    # in ``BINDABLE_PROPS`` (gate ``test_bindable_carriers_are_bindable_props``).
    BINDABLE_CARRIERS: ClassVar[dict[str, str]] = {
        "disabled": "nativeInput",
    }
    EVENTS: ClassVar[tuple[str, ...]] = (
        "change",
        "upload_start", "upload_complete", "upload_error",
        "focus", "blur",
    )

    name: str | None = reactive_prop(default=None, emit_attr=False)
    multiple: bool = reactive_prop(default=False, emit_attr=False)
    accept: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        *,
        variant: str = "dropzone",
        list: str = "tiles",
        label: str | None = None,
        multiple: bool | None = None,
        accept: str | list[str] | None = None,
        max_size_mb: float | None = None,
        max_files: int | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        upload_url: str | None = None,
        show_previews: bool = True,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_upload_start: Callable[..., Any] | str | None = None,
        on_upload_complete: Callable[..., Any] | str | None = None,
        on_upload_error: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        if variant not in ("dropzone", "button"):
            from bretzel.components.base import ComponentDefinitionError
            raise ComponentDefinitionError(
                f"FileUpload variant must be 'dropzone' or 'button', "
                f"got {variant!r}."
            )
        if list not in LIST_PRESENTATIONS:
            from bretzel.components.base import ComponentDefinitionError
            raise ComponentDefinitionError(
                f"FileUpload list must be one of "
                f"{' / '.join(map(repr, LIST_PRESENTATIONS))}, got {list!r}."
            )
        self._list = list
        reject_component(
            label,
            owner="FileUpload",
            prop="label",
            because=(
                "le label sert AUSSI d'``aria-label`` sur la dropzone et le "
                "bouton, et un attribut HTML ne peut porter qu'une string "
                "(le Component y était sérialisé en son repr Python, et "
                "annoncé tel quel au lecteur d'écran)."
            ),
            instead="Pour un contenu riche, compose autour du FileUpload.",
        )
        reject_component(
            accept,
            owner="FileUpload",
            prop="accept",
            because=(
                "``accept`` est un filtre MIME — il part dans l'attribut "
                "``accept`` de l'``<input type=file>`` ET dans le littéral "
                "JSON que lit le runtime, où un Component n'est même pas "
                "sérialisable (``Object of type TextNode is not JSON "
                "serializable``)."
            ),
            instead=(
                "Attendu : ``accept=\"image/*,.pdf\"`` ou "
                "``accept=[\"image/*\", \".pdf\"]``."
            ),
        )
        self._variant = variant
        self._label = label
        self._max_size_mb = max_size_mb
        self._max_files = max_files
        self._upload_url = upload_url
        self._show_previews = show_previews

        # ``accept=`` accepts either a comma string ("image/*,.pdf")
        # OR a list (["image/*", ".pdf"]) — normalise to the comma form
        # both for the HTML attribute and the JS factory.
        if isinstance(accept, _SEQUENCE_TYPES):
            accept = ",".join(accept)

        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            name=name,
            multiple=multiple,
            accept=accept,
            disabled=disabled,
            required=required,
            color=color, size=size,
            on_change=on_change,
            on_upload_start=on_upload_start,
            on_upload_complete=on_upload_complete,
            on_upload_error=on_upload_error,
            on_focus=on_focus,
            on_blur=on_blur,
            **kwargs,
        )

    # ── Render ────────────────────────────────────────────────────────

    def render(self) -> Element:
        # ``compose_class(slot)`` resolves ``{bg_color}`` / ``{fg_color}``
        # tokens from the theme — use it for every slot read so the
        # palette substitution lands. Falls back to the raw slot when
        # there's no token to substitute.
        def s(slot: str) -> str:
            return self.compose_class(
                slot, apply_variant_size_modifiers=False,
            )

        # Per-size lookup into ``THEME["sizes"]`` — same pattern as
        # other inputs that need different padding / font / icon
        # weights per palier (Input, NumberInput, …).
        theme = self._resolved_theme()
        size_map = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"

        def sz(group: str) -> str:
            """Return the class string for ``size_key`` in the
            ``sizes`` map's ``group`` (falls back to ``md`` then ``""``).
            """
            row = size_map.get(group, {})
            return row.get(size_key) or row.get("md") or ""

        multiple = bool(self._reactive_values.get("multiple") or False)
        accept = self._reactive_values.get("accept")
        disabled = bool(self._reactive_values.get("disabled") or False)
        required = bool(self._reactive_values.get("required") or False)

        # Pre-compute the scope's options blob — keeps the inline
        # ``bz-data`` short by passing one JSON object to the factory.
        opts: dict[str, Any] = {
            "multiple": multiple,
            "showPreviews": self._show_previews,
        }
        if accept:
            opts["accept"] = accept
        if self._max_size_mb is not None:
            opts["maxSizeMB"] = self._max_size_mb
        if self._max_files is not None:
            opts["maxFiles"] = self._max_files
        if self._upload_url:
            opts["uploadUrl"] = self._upload_url

        # ── Root attrs ─────────────────────────────────────────────
        root_attrs = self.emit_attrs()
        root_attrs["class"] = s("root")
        # ``el: $el`` captures the root in the scope (methods have no
        # $root) — the slab's ``querySelector`` + every ``dispatch()``
        # ride off it. Spliced after the leading brace because ``$el`` is
        # a runtime identifier, not a JSON-serialisable value. ``opts``
        # always carries ``multiple`` + ``showPreviews``, so the blob is
        # never ``"{}"``.
        scope_arg = "{el: $el, " + json.dumps(opts)[1:]
        root_attrs["bz-data"] = f"$bz.fileUpload.makeScope({scope_arg})"

        # ── Event relocation / normalisation ───────────────────────
        # The slab dispatches kebab-case events on the root and they
        # bubble, so the HTMX bundle / string handlers for change +
        # upload-* stay on the root. Only :
        #   1. the ``upload_*`` event names are renamed to kebab (both
        #      the ``bz-on:`` string form and the ``hx-trigger`` form) ;
        #   2. ``focus`` / ``blur`` relocate onto the focusable wrapper
        #      (the only element that fires them) — DANS LES DEUX FORMES.
        for under, kebab in _KEBAB_EVENTS.items():
            bz_key = f"bz-on:{under}"
            if bz_key in root_attrs:
                root_attrs[f"bz-on:{kebab}"] = root_attrs.pop(bz_key)
        if root_attrs.get("hx-trigger") in _KEBAB_EVENTS:
            root_attrs["hx-trigger"] = _KEBAB_EVENTS[root_attrs["hx-trigger"]]
        relocated_to_wrapper: dict[str, Any] = {}
        # Forme CALLABLE : le bundle HTMX est routé par l'event qu'il
        # écoute VRAIMENT. ``focus`` / ``blur`` ne BULLENT PAS (seuls
        # ``focusin`` / ``focusout`` le font) et la racine est un ``<div>``
        # sans ``tabindex`` — un ``hx-trigger="focus"`` posé là ne peut
        # donc jamais partir, en silence. Le wrapper ``role="button"
        # tabindex="0"`` est le seul hôte de focus. ``select.py`` avait
        # déjà corrigé exactement ça chez lui ; la leçon n'avait pas
        # circulé jusqu'ici. Les events ``change`` / ``upload-*`` restent
        # sur la racine : c'est le slab qui les y dispatche.
        # L'EVENT, pas la chaîne : un ``debounce=`` faisait échouer ce
        # test, le bundle restait sur la racine — un ``<div>`` sans
        # ``tabindex``, qui ne reçoit jamais ``focus``. Handler mort.
        if "hx-post" in root_attrs and trigger_event(root_attrs) in (
            "focus", "blur",
        ):
            relocated_to_wrapper.update({
                attr: root_attrs.pop(attr)
                for attr in SERVER_ACTION_ATTRS
                if attr in root_attrs
            })
        for ev_attr in ("bz-on:focus", "bz-on:blur"):
            if ev_attr in root_attrs:
                relocated_to_wrapper[ev_attr] = root_attrs.pop(ev_attr)

        # ── Form-data name (autoname-style for explicit name=) ────
        explicit_name = self._reactive_values.get("name")
        input_name = explicit_name or "files"

        # ── Hidden native file input ───────────────────────────────
        # ``tabindex="-1"`` + ``aria-hidden="true"`` remove it from
        # the tab order (sr-only alone does NOT, contrary to display:
        # none). Without this, keyboard users tab the wrapper AND the
        # native input — two stops + a scroll jolt when the browser
        # tries to scroll the off-screen input into view. The wrapper
        # is the canonical focus host ; the native input is a pure
        # form-data carrier. ``bz-ref="nativeInput"`` is the carrier
        # marker the base ``BINDABLE_CARRIERS`` walk forwards bindings
        # onto (and the slab queries ``input[type=file]`` directly, so
        # the ref is purely for binding forwarding).
        input_attrs: dict[str, Any] = {
            "type": "file",
            "bz-ref": "nativeInput",
            "class": s("input_native"),
            "name": str(input_name),
            "tabindex": "-1",
            "aria-hidden": "true",
            # ``stopPropagation`` : sans lui, le ``change`` NATIF de
            # l'input bulle jusqu'à la racine, qui porte déjà
            # ``hx-trigger="change"`` — et le slab y dispatche ENSUITE
            # son propre ``change``. Deux events sur la racine = DEUX
            # POST pour une seule sélection. On garde une seule source :
            # le dispatch du slab, qui couvre aussi le retrait de fichier
            # (l'input natif, lui, ne notifie rien quand on retire).
            "bz-on:change": (
                "$event.stopPropagation(); onNativeChange($event)"
            ),
        }
        if multiple:
            input_attrs["multiple"] = True
        if accept:
            input_attrs["accept"] = str(accept)
        if disabled:
            input_attrs["disabled"] = True
        if required:
            input_attrs["required"] = True
        # A ``disabled`` binding is auto-forwarded by the base post-render
        # walk onto the carrier with ``bz-ref="nativeInput"`` (driven by
        # ``BINDABLE_CARRIERS`` above). The wrapper ``<div>`` is just
        # layout ; without this forwarding the runtime would burn an
        # effect writing a no-op attribute onto the wrapper (cf.
        # ``traps.md`` § "wrapper-vs-carrier").
        native_input = Element(
            tag="input", attrs=input_attrs, children=(),
        )

        # ── Trigger (variant-dependent) ────────────────────────────
        if self._variant == "dropzone":
            trigger = self._render_dropzone(
                s, sz, native_input, relocated_to_wrapper,
            )
        else:
            trigger = self._render_button(
                s, sz, native_input, relocated_to_wrapper,
            )

        # ── Validation error panel ─────────────────────────────────
        # Hidden at SSR (no errors yet) → FOUC pre-stamp.
        error_panel_attrs: dict[str, Any] = {
            "class": s("error_panel"),
            "bz-show": "errors.length > 0",
            "role": "alert",
        }
        stamp_display_none(error_panel_attrs)
        error_panel = Element(
            tag="div",
            attrs=error_panel_attrs,
            children=(
                Element(
                    tag="span",
                    attrs={
                        "class": s("error_text"),
                        "bz-text": "errors[0]",
                    },
                    children=(),
                ),
            ),
        )

        # ── File-list strip (template bz-for) ──────────────────────
        file_list = self._render_file_list(s, sz)

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(trigger, error_panel, file_list),
        )

    # ── Trigger variants ─────────────────────────────────────────────

    def _render_dropzone(
        self, s, sz, native_input: Element,
        relocated_to_wrapper: dict[str, Any],
    ) -> Element:
        label = self._label or text("file_upload.dropzone")
        accept = self._reactive_values.get("accept")
        multiple = bool(self._reactive_values.get("multiple") or False)
        disabled = bool(self._reactive_values.get("disabled") or False)

        # Two empty states share the same DOM space, swapped via
        # ``bz-show`` based on files.length :
        #
        #  - **Full** : icon + label + hint lines. Renders when no
        #    files are picked yet (the canonical hero state).
        #  - **Compact** : tiny icon + "Drop more files" label.
        #    Renders when files are present so the dropzone doesn't
        #    steal vertical real-estate from the file strip.

        # Full empty state — visible when files.length === 0 (truthy at
        # SSR, so no FOUC pre-stamp).
        full_children: list[Node] = [
            Element(
                tag="iconify-icon",
                attrs={
                    "icon": "lucide:cloud-upload",
                    "class": " ".join(filter(None, [
                        s("dropzone_icon"),
                        sz("dropzone_icon_size"),
                        sz("dropzone_icon_margin"),
                    ])),
                },
                children=(),
            ),
            Element(
                tag="span",
                attrs={
                    "class": " ".join(filter(None, [
                        s("dropzone_title"),
                        sz("dropzone_title"),
                    ])),
                },
                children=(_TextNode(label),),
            ),
        ]
        if accept:
            full_children.append(Element(
                tag="span",
                attrs={
                    "class": " ".join(filter(None, [
                        s("dropzone_subtitle"),
                        sz("dropzone_subtitle"),
                    ])),
                },
                children=(_TextNode(text("file_upload.accepted", types=accept)),),
            ))
        if self._max_size_mb is not None:
            full_children.append(Element(
                tag="span",
                attrs={
                    "class": " ".join(filter(None, [
                        s("dropzone_subtitle"),
                        sz("dropzone_subtitle"),
                    ])),
                },
                children=(_TextNode(text(
                    "file_upload.max_size",
                    size=f"{self._max_size_mb} MB",
                )),),
            ))
        if multiple:
            # Deux phrases ENTIÈRES plutôt qu'un suffixe recollé : une
            # traduction ne met pas forcément le plafond à la fin.
            hint = (
                text("file_upload.multiple_capped", max=self._max_files)
                if self._max_files is not None
                else text("file_upload.multiple")
            )
            full_children.append(Element(
                tag="span",
                attrs={
                    "class": " ".join(filter(None, [
                        s("dropzone_subtitle"),
                        sz("dropzone_subtitle"),
                    ])),
                },
                children=(_TextNode(hint),),
            ))

        full_empty_state = Element(
            tag="div",
            attrs={
                "class": s("dropzone_empty_state"),
                "bz-show": "files.length === 0",
            },
            children=tuple(full_children),
        )

        # Compact empty state — visible when files.length > 0. Hidden at
        # SSR (no files yet) → FOUC pre-stamp.
        compact_label = text(
            "file_upload.drop_more" if multiple
            else "file_upload.drop_replace"
        )
        compact_attrs: dict[str, Any] = {
            "class": (
                s("dropzone_empty_state")
                + " flex-row gap-2"
            ),
            "bz-show": "files.length > 0",
        }
        stamp_display_none(compact_attrs)
        compact_empty_state = Element(
            tag="div",
            attrs=compact_attrs,
            children=(
                Element(
                    tag="iconify-icon",
                    attrs={
                        "icon": "lucide:cloud-upload",
                        "class": " ".join(filter(None, [
                            s("dropzone_icon"),
                            sz("dropzone_icon_size_with_files"),
                        ])),
                    },
                    children=(),
                ),
                Element(
                    tag="span",
                    attrs={
                        "class": " ".join(filter(None, [
                            s("dropzone_subtitle"),
                            sz("dropzone_subtitle"),
                        ])),
                    },
                    children=(_TextNode(compact_label),),
                ),
            ),
        )

        # Wrapper padding swaps between full / compact when files
        # exist — reactive class expression. ``bz-class`` MERGES the
        # dynamic toggles onto the static ``class=`` (``bz-attr:class``
        # would REPLACE it — cf. ``traps.md`` § ":class → bz-class").
        wrapper_base = s("dropzone_wrapper")
        # ⚠️ Le padding est coupé par AXE (cf. le thème) : l'horizontal est
        # statique, le vertical est EXCLUSIVEMENT dans le ``bz-class``.
        # Poser ``py-8`` en statique et ``py-3`` en dynamique ne marchait
        # pas — même spécificité, c'est la feuille Tailwind qui tranche, et
        # l'état compact ne s'appliquait jamais (mesuré : 32 px au lieu
        # de 12).
        pad_x = sz("dropzone_padding_x")
        pad_empty = sz("dropzone_padding_y")
        pad_compact = sz("dropzone_padding_with_files")
        active_cls = s("dropzone_active")
        global_drag_cls = s("dropzone_global_drag")

        wrapper_attrs: dict[str, Any] = {
            "class": f"{wrapper_base} {pad_x}",
            # Three layered class toggles : the VERTICAL padding, in its
            # two states ; ``dropzone_active`` when this dropzone is the
            # current drop target ; ``dropzone_global_drag`` when the
            # user is dragging files anywhere on the page. ``bz-class``
            # accepts an array natively (each entry split on whitespace).
            "bz-class": (
                "["
                f"files.length > 0 ? '{pad_compact}' : '{pad_empty}', "
                f"isDragging ? '{active_cls}' : '', "
                f"(isGlobalDragActive && !isDragging) "
                f"? '{global_drag_cls}' : ''"
                "]"
            ),
            "bz-on:click": "openPicker()",
            # ``.prevent`` inlined (``bz-on`` has no modifier grammar).
            "bz-on:dragenter": "$event.preventDefault(); onDragEnter($event)",
            "bz-on:dragover": "$event.preventDefault(); onDragOver($event)",
            "bz-on:dragleave": "$event.preventDefault(); onDragLeave($event)",
            "bz-on:drop": "$event.preventDefault(); onDrop($event)",
            # Window-level drag detection : ``bz-on:`` only listens on its
            # own element, so register the three window subscriptions once
            # at ``bz-init`` via ``$bz.helpers.onWindow``. Page-scoped :
            # the returned unsubscribe is dropped, the listeners live for
            # the page lifetime (a dropzone is never torn down mid-page).
            "bz-init": (
                "$bz.helpers.onWindow('dragenter', "
                "e => onWindowDragEnter(e)); "
                "$bz.helpers.onWindow('dragleave', "
                "e => onWindowDragLeave(e)); "
                "$bz.helpers.onWindow('drop', () => onWindowDrop()); "
                "$bz.helpers.onWindow('dragend', () => onWindowDrop())"
            ),
            "tabindex": "0" if not disabled else "-1",
            "bz-on:keydown": _ACTIVATE_KEYDOWN,
            "role": "button",
            "aria-label": label,
            **relocated_to_wrapper,
        }
        if disabled:
            wrapper_attrs["aria-disabled"] = "true"

        return Element(
            tag="div",
            attrs=wrapper_attrs,
            children=(
                native_input,
                full_empty_state,
                compact_empty_state,
            ),
        )

    def _render_button(
        self, s, sz, native_input: Element,
        relocated_to_wrapper: dict[str, Any],
    ) -> Element:
        label = self._label or text("file_upload.button")
        disabled = bool(self._reactive_values.get("disabled") or False)

        wrapper_attrs: dict[str, Any] = {
            "class": " ".join(filter(None, [
                s("button_wrapper"),
                sz("button_padding"),
            ])),
            "bz-on:click": "openPicker()",
            "tabindex": "0" if not disabled else "-1",
            "bz-on:keydown": _ACTIVATE_KEYDOWN,
            "role": "button",
            "aria-label": label,
            **relocated_to_wrapper,
        }
        if disabled:
            wrapper_attrs["aria-disabled"] = "true"

        return Element(
            tag="div",
            attrs=wrapper_attrs,
            children=(
                native_input,
                Element(
                    tag="iconify-icon",
                    attrs={
                        "icon": "lucide:upload",
                        "class": " ".join(filter(None, [
                            s("button_icon"),
                            sz("button_icon_size"),
                        ])),
                    },
                    children=(),
                ),
                Element(
                    tag="span",
                    attrs={},
                    children=(_TextNode(label),),
                ),
            ),
        )

    # ── File-list strip ──────────────────────────────────────────────

    def _render_file_list(self, s, sz) -> Element:
        """Build the ``<template bz-for>`` strip rendering one card per
        file. The cards display thumb-or-icon + name + size + remove
        button, with an optional progress bar overlay in async mode.

        The card lives inside a ``<template>``, so its ``bz-show`` /
        ``bz-attr`` branches don't need FOUC pre-stamps — the rows are
        cloned + bound fresh by ``bz-for`` (no SSR-rendered instance to
        flash)."""
        # ``slot`` substitue les noms de slot de la présentation choisie.
        # Le NOM est choisi ici ; les CLASSES sont écrites en entier dans
        # le thème des deux côtés — jamais assemblées, sinon elles
        # n'atteindraient pas le CSS compilé de prod.
        chips = self._list == "chips"

        def slot(name: str) -> str:
            return s(_CHIP_SLOTS[name] if chips and name in _CHIP_SLOTS else name)

        # Per-file item attrs : keyed by the entry's id (stable
        # through removals).
        thumb = Element(
            tag="img",
            attrs={
                "bz-attr:src": "entry._preview",
                "bz-attr:alt": "entry.name",
                "bz-show": "entry.isImage && entry._preview",
                "class": slot("file_thumb"),
                "loading": "lazy",
            },
            children=(),
        )
        icon_fallback = Element(
            tag="iconify-icon",
            attrs={
                "icon": "lucide:file",
                "class": slot("file_icon"),
                "bz-show": "!(entry.isImage && entry._preview)",
            },
            children=(),
        )

        # Status badges — uploading is implicit (progress bar shown),
        # done / error get a small badge over the thumbnail.
        status_done = Element(
            tag="span",
            attrs={
                "class": slot("file_status_done"),
                "bz-show": "entry.status === 'done'",
                "aria-label": text("file_upload.complete"),
            },
            children=(
                Element(
                    tag="iconify-icon",
                    attrs={
                        "icon": "lucide:check",
                        "class": slot("file_status_icon"),
                    },
                    children=(),
                ),
            ),
        )
        status_error = Element(
            tag="span",
            attrs={
                "class": slot("file_status_error"),
                "bz-show": "entry.status === 'error'",
                "bz-attr:title": "entry.error",
                "aria-label": text("file_upload.error"),
            },
            children=(
                Element(
                    tag="iconify-icon",
                    attrs={
                        "icon": "lucide:alert-triangle",
                        "class": slot("file_status_icon"),
                    },
                    children=(),
                ),
            ),
        )

        # Progress bar — only renders during ``uploading``.
        progress = Element(
            tag="div",
            attrs={
                "class": slot("file_progress_bar"),
                "bz-show": (
                    "entry.status === 'uploading' "
                    "|| (entry.status === 'done' && entry.progress < 100)"
                ),
                "role": "progressbar",
                "bz-attr:aria-valuenow": "entry.progress",
                "aria-valuemin": "0",
                "aria-valuemax": "100",
            },
            children=(
                Element(
                    tag="div",
                    attrs={
                        "class": slot("file_progress_fill"),
                        "bz-attr:style": "'width: ' + entry.progress + '%'",
                    },
                    children=(),
                ),
            ),
        )

        # Émission single-sourcée dans ``_wiring.dismiss_button`` (le même
        # x que Alert / Badge / Banner). Il apporte l'``Icon`` DÉTACHÉ — donc
        # le set d'icônes du thème et le traitement FOUC — là où ce fichier
        # écrivait un ``<iconify-icon icon="lucide:x">`` en dur. Seul le
        # geste diffère : ici on retire UNE entrée, pas le composant.
        # ``.stop`` inliné (``bz-on`` n'a pas de modificateurs).
        remove_btn = dismiss_button(
            button_class=" ".join(
                p for p in (slot("remove_btn"), sz("remove_btn")) if p
            ),
            aria_label=text("file_upload.remove"),
            icon_size=sz("remove_btn_icon_size") or "xs",
            on_click="$event.stopPropagation(); removeFile(entry, $event)",
        )

        item = Element(
            tag="div",
            attrs={
                "class": slot("file_item"),
                "bz-attr:title": "entry.name",
            },
            children=tuple(
                child for child in (
                # Une puce n'a pas de vignette (pas la place) ni de
                # taille (elle tiendrait sur deux lignes). Ce ne sont pas
                # des classes qu'on masque : les nœuds ne sont pas émis.
                None if chips else thumb,
                icon_fallback,
                status_done,
                status_error,
                Element(
                    tag="span",
                    attrs={
                        "class": slot("file_name"),
                        "bz-text": "entry.name",
                    },
                    children=(),
                ),
                None if chips else Element(
                    tag="span",
                    attrs={
                        "class": slot("file_size"),
                        "bz-text": "entry.sizeLabel",
                    },
                    children=(),
                ),
                progress,
                remove_btn,
                ) if child is not None
            ),
        )

        # ``bz-for`` lives on a ``<template>`` with a SINGLE root child ;
        # the key rides inside the attribute (``entry in files
        # :key=entry.id``) per the directive grammar.
        template = Element(
            tag="template",
            attrs={"bz-for": "entry in files :key=entry.id"},
            children=(item,),
        )

        # File-list strip — hidden at SSR (no files) → FOUC pre-stamp.
        list_attrs: dict[str, Any] = {
            "class": slot("file_list"),
            "bz-show": "files.length > 0",
        }
        stamp_display_none(list_attrs)
        return Element(
            tag="div",
            attrs=list_attrs,
            children=(template,),
        )

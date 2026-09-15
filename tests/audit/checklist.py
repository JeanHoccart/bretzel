"""Per-component audit checklist.

A :class:`ComponentSpec` describes everything the audit needs to know
about a single component : its playground URL, the CSS selector that
identifies its root in the DOM, which checks apply, and any
component-specific assertions (e.g. the variant Server-playground
input name).

Subagents (or the driver) consume specs from :func:`COMPONENT_SPECS`
to run a uniform audit pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ComponentSpec:
    name: str
    route: str
    root_selector: str                  # CSS ``.bz-<component>`` typically
    inner_role: str | None = "button"   # what to read computed style on
    # ── Feature flags : which probes apply ────────────────────────
    has_color_axis: bool = True
    # When True, the component MUST visually tint at rest (the
    # FileUpload / Button / Badge / Banner pattern : ``border-{color}``
    # + ``bg-{color}/[0.05]`` + ``text-{color}`` so the user sees
    # color= take effect without focusing).
    #
    # When False, the component is "input-like" — neutral at rest,
    # color only on focus / checked / drag (Input / Textarea / Select
    # / Combobox / Slider / Checkbox / Switch / DatePicker pattern,
    # mirror of Tailwind / Linear / Notion canonical inputs). The
    # ``color_distinctness`` probe is SKIPPED on these components by
    # design.
    #
    # If a component has ``has_color_axis=True`` and the probe returns
    # 1/7 distinct, the component is a candidate for moving to
    # ``color_at_rest=False`` — i.e. its design intent matches the
    # input-like family.
    color_at_rest: bool = True
    # Default palette count = 7 (primary/secondary/success/warning/
    # error/info/muted). Components like Alert (4 semantic colors :
    # info/success/warning/error) or Banner (6 colors : info/success/
    # warning/error/muted/primary) override this on their spec.
    expected_color_count: int = 7
    # Où lire la teinte, quand ce n'est PAS la racine. Un composant
    # composite teinte souvent une partie de lui-même : le datatable
    # colore son ``<thead>`` et l'accent de son pager, jamais son
    # conteneur. La sonde échantillonnait donc la racine, trouvait sept
    # fois le même gris et concluait « 1/7 distinct » — sur un composant
    # dont la teinte est parfaitement visible à l'écran.
    #
    # ⚠️ Ne PAS répondre à ça par ``color_at_rest=False`` : ce drapeau
    # dit « neutre au repos, coloré au focus » (la famille des champs de
    # saisie), et le datatable n'en est pas. Le déclarer reviendrait à
    # faire taire la sonde en lui mentant.
    color_sample_selector: str | None = None
    has_size_axis: bool = True
    # Default size paliers = 5 (xs/sm/md/lg/xl). Banner ships
    # 3 paliers (sm/md/lg) — override on its spec.
    expected_size_count: int = 5
    has_variant_axis: bool = False
    is_interactive: bool = True
    is_overlay: bool = False           # popover / dialog / drawer / dropdown
    has_text_input: bool = False
    # ── Component-specific selectors used by interaction probes ───
    trigger_selector: str | None = None
    panel_selector: str | None = None
    text_input_selector: str | None = None
    # ── Server-playground hooks for refreshable round-trip probes ─
    refreshable_inputs: dict[str, str] = field(default_factory=dict)
    # ── Dynamic probe skip list ───────────────────────────────────
    # Names of controls (Client or Server playground) the interaction
    # probes should NOT exercise. Use only when there's a structural
    # reason the probe can't oracle correctly :
    # - The bound prop drives a render branch that needs a non-empty
    #   initial value (avatar.src : ``<img>`` only emitted when SSR
    #   src is truthy, so a binding-driven change can't be observed
    #   on the missing element).
    # - The playground's ``server_changed`` handler does
    #   ``int(value)`` on a string-typed input where the probe's
    #   sentinel raises ValueError before reaching the binding.
    # - The bound prop only affects a teleported panel that's not a
    #   descendant of the spec selector's root (popovers / dropdowns
    #   when the spec anchors on the trigger, not the wrapper).
    #
    # Each entry SHOULD carry a one-line rationale via a comment so
    # future maintainers can re-evaluate when the underlying
    # constraint lifts.
    skip_dynamic_props: tuple[str, ...] = ()
    # ── Notes ─────────────────────────────────────────────────────
    notes: str = ""


# ─────────────────────────────────────────────────────────────────
# Component inventory — every shipped V2 component, by tier
# ─────────────────────────────────────────────────────────────────
#
# Subagents work through this list. Add / remove entries as components
# land or get retired. The route + root_selector pair MUST stay in sync
# with ``examples/playground/app/routes.py``.


TIER_1_PRIMITIVES_LAYOUT = [
    ComponentSpec(
        name="text",
        route="/text",
        # Text renders as ``<span class="leading-normal ...">`` — no
        # ``bz-text`` marker class exists in the component source.
        # Anchor on the ``leading-normal`` class which every Text instance
        # carries. The probe scopes the selector inside the Colors / Sizes
        # swatch container so unrelated leading-normal spans (descriptions)
        # outside the container don't pollute the sample.
        root_selector="span.leading-normal",
        # The selector matches the playground description span + the
        # ``control`` label spans + the demo, all of which are
        # outside any ``.bz-X`` and before the emitted-html boundary.
        # The probe's "last surviving match" heuristic doesn't reliably
        # land on the demo here ; the binding itself is verified by
        # ``tests/runtime_js/test_text_x_text_reactive.py``.
        skip_dynamic_props=("text",),
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="heading",
        route="/heading",
        # Heading renders as ``<hN class="font-sans tracking-tight ...">``
        # — no ``bz-heading`` marker class. Anchor on the
        # ``font-sans.tracking-tight`` pair which every Heading carries.
        root_selector=(
            "h1.font-sans, h2.font-sans, h3.font-sans, "
            "h4.font-sans, h5.font-sans, h6.font-sans"
        ),
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="icon",
        route="/icon",
        root_selector="iconify-icon",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="html",
        route="/html",
        # L'enveloppe porte ``bz-html``, une classe MARQUEUR posée pour
        # ça — le composant n'ayant aucune classe visuelle, il n'y a rien
        # d'autre sur quoi s'ancrer.
        root_selector=".bz-html",
        # Ni couleur ni taille : le composant n'impose aucun style à du
        # balisage qu'il n'a pas produit. C'est le point du composant.
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="iframe",
        route="/iframe",
        # La racine EST l'``<iframe>`` — on ancre sur ``iframe.block``,
        # le slot racine que toute instance porte.
        root_selector="iframe.block",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="audio",
        route="/audio",
        root_selector="audio.block",
        has_color_axis=False,
        has_size_axis=False,
        # La barre est dessinée par le navigateur — rien que la sonde
        # d'interaction Bretzel sache piloter.
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="video",
        route="/video",
        # La racine EST le ``<video>`` — pas de classe marqueur, on ancre
        # sur ``video.block``, le slot racine que toute instance porte.
        root_selector="video.block",
        # Ni couleur ni taille : ses axes à lui sont ratio et fit, que ces
        # sondes ne savent pas balayer.
        has_color_axis=False,
        has_size_axis=False,
        # Les contrôles sont ceux du navigateur — rien que la sonde
        # d'interaction Bretzel sache piloter.
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="image",
        route="/image",
        # Image renders as a bare ``<img>`` — no marker class. On ancre
        # sur ``img.block``, la seule classe que TOUTE instance porte
        # (le slot racine), ce qui exclut l'``<img>`` interne d'un avatar
        # (``h-full w-full``) si un jour la page en montrait un.
        root_selector="img.block",
        # Aucun axe couleur ni taille : une image n'a ni ``color=`` ni
        # ``size=``. Ses axes à elle sont ``ratio`` et ``fit``, qui ne
        # sont pas les axes standard que ces sondes savent balayer.
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="divider",
        route="/divider",
        # Divider renders as ``<div role="separator" aria-orientation=...>``
        # — no ``bz-divider`` marker class. Anchor on the ARIA role.
        root_selector='[role="separator"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="code",
        route="/code",
        root_selector="pre.bz-code",
        # ``text`` binding flows via ``x-text`` on the rendered
        # ``<pre>``. The probe's demo-finder picks the
        # ``emitted_html_block``'s code pre (which renders a
        # serialized snippet) over the live demo when both appear
        # before the show_html boundary — same shape as the text /
        # heading false positives. Binding itself is verified by
        # ``tests/runtime_js/test_code_text_reactive.py``.
        skip_dynamic_props=("text",),
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="markdown",
        route="/markdown",
        root_selector=".bz-markdown",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="link",
        route="/link",
        # Link renders as ``<a href class="group inline-flex ...">`` —
        # no ``bz-link`` marker class. Anchor on ``a.inline-flex`` which
        # every Link instance carries.
        root_selector="a.inline-flex",
        has_color_axis=True,
        has_size_axis=False,
        is_interactive=True,
        inner_role=None,
    ),
    ComponentSpec(
        name="button",
        route="/button",
        # Buttons don't carry a ``bz-button`` marker class — match by
        # tag inside the Reference card sections (color/size headings).
        root_selector="button",
        has_color_axis=True,
        has_size_axis=True,
        has_variant_axis=True,
        is_interactive=True,
        inner_role=None,
        refreshable_inputs={
            "variant": 'input[type="hidden"][name="sv_btn_variant"]',
            "color": 'input[type="hidden"][name="sv_btn_color"]',
        },
    ),
    ComponentSpec(
        name="icon_button",
        route="/icon-button",
        # IconButton renders as ``<button type="button" aria-label="..."
        # class="inline-flex items-center justify-center rounded-field
        # font-medium ...">`` — no ``bz-icon-button`` marker class.
        # Anchor on ``button[aria-label]`` which every IconButton instance
        # carries (it's required for a11y on icon-only buttons).
        root_selector="button[aria-label]",
        has_color_axis=True,
        has_size_axis=True,
        has_variant_axis=True,
        is_interactive=True,
        inner_role=None,
    ),
    ComponentSpec(
        name="card",
        route="/card",
        # Card renders as ``<div class="block w-full rounded-box
        # overflow-hidden bg-{color} border border-text/10 ...">`` — no
        # ``bz-card`` marker class. Anchor on the structural
        # ``rounded-box.overflow-hidden`` pair that identifies a Card
        # wrapper.
        #
        # ⚠️ ``shadow-sm`` était dans cette ancre jusqu'au 2026-09-13, où la
        # carte a perdu son ombre AU REPOS (elle est délimitée par son
        # filet ; l'ombre reste aux calques flottants et au survol). Le
        # sélecteur est alors devenu mort, et l'audit a rendu « no swatches
        # after color heading » — un message qui parle de couleurs pour un
        # défaut d'ancrage. C'est la deuxième fois : la migration des
        # rayons avait tué ``rounded-md`` et ``rounded-xl`` de la même
        # façon. **Une ancre ne doit nommer que ce qui tient à la
        # STRUCTURE** — une classe décorative y est une bombe à retardement.
        root_selector="div.rounded-box.overflow-hidden",
        has_color_axis=True,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="container",
        route="/container",
        # Container renders as ``<div class="mx-auto w-full px-6 py-8
        # max-w-...">`` — no ``bz-container`` marker class. Anchor on
        # the ``mx-auto`` + ``max-w-`` combination unique to Container.
        root_selector='div.mx-auto[class*="max-w-"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="flex",
        route="/flex",
        # Flex renders as ``<div class="flex flex-row|col ...">`` — no
        # ``bz-flex`` marker class. Anchor on ``div.flex`` with a gap
        # utility (excludes Card wrappers which don't carry gap-).
        root_selector='div.flex[class*="gap-"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="grid",
        route="/grid",
        # Grid renders as ``<div class="grid grid-cols-N gap-...">`` —
        # no ``bz-grid`` marker class. Anchor on the ``grid`` +
        # ``grid-cols-`` combination.
        root_selector='div.grid[class*="grid-cols-"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="stack",
        route="/stack",
        # VStack renders as ``<div class="flex flex-col ... gap-...">``
        # — a Flex shortcut (axis baked). No ``bz-stack`` marker class.
        root_selector='div.flex[class*="gap-"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
]

TIER_2_FORMS = [
    ComponentSpec(
        name="input",
        route="/input",
        root_selector="input.bz-input",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        has_text_input=True,
        inner_role=None,
        text_input_selector="input.bz-input",
        color_at_rest=False,
    ),
    ComponentSpec(
        name="number_input",
        route="/number_input",
        root_selector=".bz-number-input",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        has_text_input=True,
        inner_role=None,
        color_at_rest=False,
    ),
    ComponentSpec(
        name="textarea",
        route="/textarea",
        root_selector="textarea.bz-textarea",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        has_text_input=True,
        inner_role=None,
        color_at_rest=False,
    ),
    ComponentSpec(
        name="select",
        route="/select",
        root_selector=".bz-select",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        is_overlay=True,
        color_at_rest=False,
    ),
    ComponentSpec(
        name="combobox",
        route="/combobox",
        root_selector=".bz-combobox",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        is_overlay=True,
        has_text_input=True,
        color_at_rest=False,
    ),
    ComponentSpec(
        name="slider",
        route="/slider",
        root_selector=".bz-slider",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        color_at_rest=False,
    ),
    ComponentSpec(
        name="calendar",
        route="/calendar",
        root_selector="bz-calendar",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        notes="Calendar applies color only on data-[selected=true]:bg-{color} day cells. "
              "The wrapper-level color tint at rest is intentionally absent. "
              "Color distinctness probe will fail by design — accepted.",
        color_at_rest=False,
    ),
    ComponentSpec(
        name="date_picker",
        route="/date_picker",
        root_selector=".bz-date-picker",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        is_overlay=True,
        has_text_input=True,
        color_at_rest=False,
    ),
    ComponentSpec(
        name="date_range_picker",
        route="/date_range_picker",
        root_selector=".bz-date-range-picker",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        is_overlay=True,
        has_text_input=True,
        color_at_rest=False,
    ),
    ComponentSpec(
        name="file_upload",
        route="/file_upload",
        root_selector=".bz-file-upload",
        has_color_axis=True,
        # Input-like : the dropzone is neutral at rest and tints only on
        # hover / drag-enter (theme uses ``hover:border-{bg_color}`` +
        # ``hover:bg-{bg_color}/5`` — no at-rest tint). So the colour-
        # distinctness probe is skipped, same as Input/Select/Checkbox.
        # (The audit flagged 1/7 distinct at rest — a spec misconfig, not a
        # component bug : verified the dropzone genuinely colours on drag.)
        color_at_rest=False,
        has_size_axis=True,
        has_variant_axis=True,
        is_interactive=True,
    ),
    ComponentSpec(
        name="checkbox",
        route="/checkbox",
        root_selector=".bz-checkbox",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        inner_role=None,  # checkbox is a <label>, not a button,
        color_at_rest=False
    ),
    ComponentSpec(
        name="switch",
        route="/switch",
        root_selector=".bz-switch",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        inner_role=None,  # switch is a <label>, not a button,
        color_at_rest=False
    ),
    ComponentSpec(
        name="radio",
        route="/radio",
        # RadioGroup renders multiple <div role="radiogroup"> in the
        # Colors / Sizes sections (one group per color/size). Color
        # tints the CHECKED radio circle (not label at rest) →
        # color_at_rest=False, mirror of checkbox.
        #
        # has_size_axis=False : the aggregated probe samples the
        # first N <label>s across groups, but the LABEL element's
        # height is dominated by its flex/gap container, not by the
        # inner circle. Size paliers DO change visually (circle
        # diameter + label font-size) but the probe at the label
        # level reads near-identical heights. Probe limitation,
        # not a component bug — verified by inspecting the theme
        # ``sizes`` dict at radio/theme.py:66-71 (5 distinct
        # circle/dot/label triples).
        root_selector='[role="radiogroup"] label',
        has_color_axis=True,
        color_at_rest=False,
        has_size_axis=False,
        is_interactive=True,
        inner_role=None,
    ),
    ComponentSpec(
        name="toggle_group",
        route="/toggle_group",
        # Same selection-control pattern as Radio — color tints the
        # selected button. Probe samples the first N buttons across
        # variant/size groups, so same limitation applies.
        root_selector='[role="group"] button',
        has_color_axis=True,
        color_at_rest=False,
        has_size_axis=False,
        has_variant_axis=True,
        is_interactive=True,
        inner_role=None,
    ),
    ComponentSpec(
        name="form",
        route="/form",
        root_selector="form",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="form_field",
        route="/form_field",
        # FormField renders as ``<div ...>`` wrapping a <label>, the child
        # input, and a hint/error <span>. No marker class — anchor on the
        # <label> which every labelled field carries (the visual-layer
        # builder always renders FormField with a label).
        root_selector="div:has(> label)",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
        notes="Field wrapper : label on top + child input + hint/error "
              "span below. No visual axis (structure only).",
    ),
]

TIER_3_FEEDBACK = [
    ComponentSpec(
        name="alert",
        route="/alert",
        # Alert emits no marker class. Use direct children of the
        # swatch container. Color section ships ONLY 4 semantic
        # colors (info/success/warning/error) — override the
        # default expected_color_count=7.
        root_selector=":scope > div",
        has_color_axis=True,
        expected_color_count=4,
        has_size_axis=False,  # No "Sizes" heading in alert playground.
        is_interactive=False,
        inner_role=None,
        notes="4 semantic colors only (info/success/warning/error).",
    ),
    ComponentSpec(
        name="spinner",
        route="/spinner",
        # No marker class ; stable hook is role=status.
        root_selector='span[role="status"]',
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="progress",
        route="/progress",
        # The role=progressbar wrapper carries no color tokens — they
        # live on the inner ``bg-{color}/15`` track. Sample the track
        # directly. (selectors are relative to the swatch container.)
        root_selector='[role="progressbar"] > div',
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
        # ``value`` / ``label`` are int + str client-bound — the probe
        # types a string sentinel which (a) crashes int-coerced
        # server playgrounds, (b) renders ``width: NaN%`` so the fill
        # bar style stays unchanged. The probe's ``:style`` /
        # ``:aria-valuenow`` forwarding is verified via integration
        # tests with valid numeric values.
        skip_dynamic_props=("value", "label"),
        notes="Color tokens live on the inner track, not the role="
              "progressbar wrapper.",
    ),
    ComponentSpec(
        name="notification",
        route="/notification",
        # Notifications live in OOB portal #bz-notification-root and
        # mount only when toasted. At rest the playground shows
        # trigger buttons. Variant-based, not color=. Nothing to
        # probe statically.
        root_selector="#bz-notification-root",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
        notes="variant-based (info/success/warning/error/neutral), "
              "not color=. Toasts render on demand into a portal.",
    ),
    ComponentSpec(
        name="banner",
        route="/banner",
        # No marker class ; stable hook is role=status.
        # Banner ships 6 colors (info/success/warning/error/muted/
        # primary) and 3 sizes (sm/md/lg) — override defaults.
        root_selector='[role="status"]',
        has_color_axis=True,
        expected_color_count=6,
        has_size_axis=True,
        expected_size_count=3,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="empty_state",
        route="/empty_state",
        # No marker class ; stable hook is role=status + aria-live.
        # No "Colors" heading in the playground — color= defaults to
        # muted and is design-time only.
        root_selector='[role="status"][aria-live="polite"]',
        has_color_axis=False,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
        notes="color= defaults to muted ; playground has no Colors "
              "section. Size container wraps each empty_state in a card.",
    ),
]

TIER_4_OVERLAYS = [
    ComponentSpec(
        name="tooltip",
        route="/tooltip",
        # Tooltip emits no marker class. The Reference card's "Colors"
        # row shows one trigger BUTTON per color (the tooltip panel
        # itself is x-teleport'd to <body> and hidden at rest with
        # x-show=open). The trigger button carries the color tokens
        # (bg-primary/10, text-primary). Sample the button directly —
        # the wrapper div has no color tokens of its own.
        root_selector='div.inline-block.w-fit.h-fit > button',
        has_color_axis=True,
        has_size_axis=False,
        is_interactive=True,
        is_overlay=True,
        # ``text`` lands in a teleported panel that's a sibling of
        # the trigger ; the probe's snapshot anchors on the spec
        # selector (the button itself) and ``demo.parentElement``
        # picks up the wrapper, but the panel content only appears
        # AFTER hover (x-show=open is false at rest). Verified via
        # the dedicated tooltip integration tests.
        skip_dynamic_props=("text",),
        notes="Panel is x-teleport'd to <body> and hidden at rest. "
              "Color sampled on the trigger button.",
    ),
    ComponentSpec(
        name="popover",
        route="/popover",
        # ⚠️ ``data-bz-float-root`` n'existe PLUS — mesuré le
        # 2026-08-28 : zéro occurrence sur toute la page. Le crochet
        # était mort, donc la sonde de porteur ne trouvait aucune cible
        # et disait « preview introuvable », ce qui se lit comme un
        # défaut du composant.
        #
        # Le couple ``bz-id`` + ``bz-data`` est ce qui reste de stable :
        # la racine porte les deux (le scope ``{open: false}``), ses
        # enfants portent un ``bz-id`` mais pas de scope. Une classe
        # ``.bz-popover`` serait plus franche, mais le composant n'en
        # émet pas.
        #
        # No "Colors" heading in playground — the panel carries
        # surface tokens (bg-surface, border-text/10), no color= prop.
        root_selector='div[bz-id*="popover"][bz-data]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=True,
        is_overlay=True,
        notes="No color= prop. Panel teleported to body via portal. "
              "probe_click_opens would be the right axis to wire.",
    ),
    ComponentSpec(
        name="dialog",
        route="/dialog",
        # Dialog emits no marker class — the panel is portal-mounted
        # only when open. probe_no_clip is silently a no-op (selector
        # not found → empty suspect list → PASS by absence).
        root_selector='[role="dialog"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=True,
        is_overlay=True,
        notes="Panel portal-mounted only when open. Static probes "
              "are mostly no-ops ; needs probe_click_opens.",
    ),
    ComponentSpec(
        name="drawer",
        route="/drawer",
        # Same portal-on-open pattern as Dialog.
        root_selector='[role="dialog"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=True,
        is_overlay=True,
        notes="Panel portal-mounted only when open. Needs "
              "probe_click_opens for meaningful audit.",
    ),
    ComponentSpec(
        name="dropdown",
        route="/dropdown",
        # Dropdown does emit data-bz-float-root + inline classes.
        # No "Colors" heading — menu items carry color tokens not the
        # dropdown itself. No color= prop on the dropdown.
        root_selector='[data-bz-float-root], div[bz-id*="dropdown"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=True,
        is_overlay=True,
        notes="No color= prop. Menu panel is portaled.",
    ),
]

TIER_5_DATA = [
    ComponentSpec(
        name="badge",
        route="/badge",
        # Badges render as <span class="inline-flex … rounded-md …"> with
        # NO ``bz-badge`` marker class (same pattern as Button). Match
        # the soft-swatch span shape emitted by the theme.
        root_selector="span.inline-flex.rounded-selector",
        has_color_axis=True,
        has_size_axis=True,
        has_variant_axis=True,
        is_interactive=False,
        inner_role=None,
        notes="No marker class. Selector targets the theme's soft "
              "swatch shape (rounded-selector inline-flex span).",
    ),
    ComponentSpec(
        name="avatar",
        route="/avatar",
        # Avatars render as <span class="… inline-flex … rounded-full">.
        # The "Colors (initials fallback)" anchor still starts with
        # 'color' so the probe finds it.
        root_selector="span.inline-flex.rounded-full",
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
        # ``src`` only emits an ``<img>`` when the SSR src is truthy ;
        # the Client playground starts with empty src, so a
        # binding-driven src change has no element to attach to
        # (verified : the forwarded ``bz-attr:src`` lives on the
        # inner img which doesn't exist until SSR has a value).
        # ``status`` toggles a dot's visibility / color via the
        # existing reactive ``:class`` + ``x-show`` ; the bound dot
        # is at the wrapper level and was confirmed working by
        # the dedicated avatar tests.
        skip_dynamic_props=("src", "status"),
        notes="No marker class. Selector matches the rounded-full "
              "initials bubble.",
    ),
    ComponentSpec(
        name="skeleton",
        route="/skeleton",
        # Skeletons are neutral placeholders : no color, no size axes.
        # Match the shimmer animation class as a stable hook.
        root_selector="[class*='animate-pulse']",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
        notes="Neutral by design — no color / size axes. Selector "
              "targets the shimmer animation hook.",
    ),
    ComponentSpec(
        name="table",
        route="/table",
        # The root is the scroll-container <div> that wraps the <table> (it
        # owns the horizontal-scroll viewport + border/round, and carries
        # id / classes= / attrs=). Marked with the ``bz-table`` hook — a
        # stable audit anchor, not the cosmetic overflow utility.
        root_selector=".bz-table",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
    ),
    ComponentSpec(
        name="datatable",
        route="/datatable",
        # Root is the vertical stack (toolbar / table / footer), marked
        # with the ``bz-datatable`` hook. NOT ``.bz-table`` — that anchor
        # belongs to the composed table one level in, and matching it here
        # would make every datatable probe silently audit the Table.
        root_selector=".bz-datatable",
        # Both ladders live under their own h3 in Reference (size reaches
        # the cells AND the composed sort button / pager ; color tints the
        # header AND the pager accent).
        has_color_axis=True,
        has_size_axis=True,
        # La teinte vit dans l'en-tête, pas sur le conteneur.
        color_sample_selector=".bz-datatable thead",
        # TROIS paliers, pas cinq : le thème du datatable n'en déclare que
        # ``sm`` / ``md`` / ``lg`` (un tableau n'a pas de ``xs``, ses
        # cellules deviendraient illisibles). La sonde en cherchait cinq et
        # disait « only 3/5 swatches found » — elle décrivait le thème, pas
        # un défaut.
        expected_size_count=3,
        # Sort headers, search box and pager are all real controls.
        is_interactive=True,
        inner_role=None,
        notes="Assembles ui.table + ui.button + ui.input + ui.pagination. "
              "Every axis is server-driven (BINDABLE_PROPS = ()), so the "
              "client-switch probes have nothing to drive — the axes are "
              "exercised by the SSR ladders, not by a binding.",
    ),
    ComponentSpec(
        name="accordion",
        route="/accordion",
        # Le littéral de scope, PAS une méthode : les corps
        # (``isOpen`` / ``toggle`` / …) ont quitté chaque instance pour
        # ``$bz.accordion.single`` / ``.multi``, et ce sélecteur a suivi
        # deux jours après tout le monde — il ne matchait plus RIEN,
        # donc deux sondes rougissaient en accusant le composant.
        # ``$bz.accordion.`` couvre les deux modes.
        root_selector="div[bz-data*='$bz.accordion.']",
        # No "Colors" h3 in Reference — color= is driven only from the
        # Server playground select. Skip the color probe.
        has_color_axis=False,
        has_size_axis=True,
        has_variant_axis=True,
        is_interactive=True,
        inner_role=None,
        notes="No marker class. Hook on @bz-toggle attribute. No "
              "Colors Reference h3 (color= only via Server playground).",
    ),
    ComponentSpec(
        name="tree",
        route="/tree",
        # Tree root is <ul role="tree" bz-data="{open, isOpen, toggle, …}">.
        root_selector='[role="tree"]',
        # Color tints the SELECTED row (data-[selected=true]:bg-{color}),
        # not the <ul> root — sampling the root collapses to 1 distinct
        # (Bucket C, same as breadcrumb/tabs where color lives on inner
        # elements). Skip the color-distinctness probe.
        has_color_axis=True,
        color_at_rest=False,
        # Sizes (sm/md/lg) render as separate trees inside a grid
        # (flat-sibling, like tabs/pagination) — the height-distinctness
        # probe can't aggregate across grid cells. Skip.
        has_size_axis=False,
        is_interactive=True,
        inner_role=None,
        notes="Recursive disclosure. Chevron correctness (exactly one "
              "glyph per open/closed state) + per-depth label alignment "
              "are verified by a dedicated visual probe during rollout — "
              "the generic color/size probes are skipped (Bucket C : color "
              "on inner selected row, sizes as grid siblings).",
    ),
    ComponentSpec(
        name="diagram",
        route="/diagram",
        # `.bz-diagram`, la classe MARQUEUR de la racine — posée pour
        # ça, comme `bz-table`. Jamais une classe visuelle : le probe
        # cherchait `[class*="overflow-auto"]` et il est mort le jour où
        # la racine est passée à `overflow-x-auto`. C'est la même mort
        # que les deux sélecteurs de ce fichier emportés par la
        # migration des rayons.
        root_selector=".bz-diagram",
        # Le pont de couleur pose les paliers sur la RACINE, et un nœud
        # lit `--bz-border` / `--bz-bg` — donc la teinte descend, mais
        # elle est volontairement discrète (un graphe se lit par sa
        # structure, pas par sa couleur). Même famille que `tree` : la
        # sonde de distinction de couleur ne mord pas ici.
        has_color_axis=True,
        color_at_rest=False,
        # Les cinq paliers sont rendus comme des diagrammes FRÈRES dans
        # une pile — la sonde de hauteur ne sait pas agréger à travers
        # des conteneurs séparés (même cas que tabs / pagination). La
        # distinction est gatée par le test unitaire, qui compare les
        # styles inline des cinq paliers.
        has_size_axis=False,
        # Un nœud n'est cliquable que si `on_item_click=` est passé —
        # une seule des six cartes du banc le fait.
        is_interactive=False,
        inner_role=None,
        notes="Placement serveur. L'invariant qui compte — aucune arête "
              "ne traverse un nœud — se vérifie par le CALCUL dans "
              "tests/unit/components/data/test_diagram_layout.py (les "
              "Béziers y sont échantillonnées), pas par une capture : "
              "une capture ne garde pas cette propriété d'un run à "
              "l'autre. Ce qui reste au navigateur, c'est que le calque "
              "d'arêtes n'avale pas les clics et que rien ne déborde.",
    ),
]

TIER_6_NAV = [
    ComponentSpec(
        name="pagination",
        route="/pagination",
        # Pagination root is <nav role="navigation" aria-label="Pagination">.
        root_selector='nav[aria-label="Pagination"]',
        has_color_axis=True,
        # Pagination size section emits each pagination instance as its
        # own sibling div under the h3 ; the probe walks 3 next siblings
        # and needs ≥2 swatches in ONE of them. Flat-sibling layout
        # defeats that — Bucket C. Skip size probe until the probe is
        # extended to aggregate across siblings (or playground wraps
        # variants in a single container).
        has_size_axis=False,
        is_interactive=True,
        inner_role=None,
        color_at_rest=False,
        # ``value`` and ``total_pages`` are int-typed on PaginationClient
        # so the probe's string sentinels crash the playground's
        # ``int(value)`` coercion before reaching the binding. The
        # actual binding path is exercised by `tests/runtime_js/`
        # with numeric values.
        skip_dynamic_props=("value", "total_pages", "max_visible"),
        notes="No marker class. Color/Size sections lay each swatch in "
              "its own sibling wrapper (no single container with all N) "
              "— probe's next-sibling walk only sees 1 nav per sibling. "
              "Bucket C structural limitation. color_at_rest=False also "
              "reflects that color is applied to inner page buttons, not "
              "to the nav wrapper. has_size_axis=False to skip probe.",
    ),
    ComponentSpec(
        name="tabs",
        route="/tabs",
        # Tabs root is <div class="flex flex-col gap-3" bz-data="{active…,
        # setTab(v){…}}"> with no marker class. Hook on the V3 ``bz-data``
        # whose ``setTab`` method uniquely identifies a tabs root (V2 used
        # ``x-data``).
        root_selector="div[bz-data*='$bz.tabs.scope']",
        has_color_axis=True,
        # Tabs size section is flat-sibling like pagination — each tabs
        # widget is its own sibling div. Probe can't aggregate across.
        has_size_axis=False,
        # Single Crédit-Agricole style — no variant axis (dropped in the
        # tabs simplification).
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        color_at_rest=False,
        notes="No marker class. Each color/size swatch is a sibling — "
              "no wrapping container. Distinctness probe limited by "
              "flat-sibling layout (Bucket C). color_at_rest=False also "
              "reflects that color is applied to the active tab indicator "
              "and tab text, not to the root wrapper div.",
    ),
    ComponentSpec(
        name="month_picker",
        route="/month_picker",
        root_selector="div.bz-month-picker",
        has_color_axis=True,
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # Comme ses voisins de la famille : la couleur ne teinte rien au
        # repos, elle vit sur l'anneau de focus, l'icône du trigger et la
        # cellule sélectionnée du panneau — donc invisible panneau fermé.
        color_at_rest=False,
        notes="Enveloppe mince sur _picker_field + ui.calendar(mode="
              "\'month\'). color_at_rest=False : rien de teinté au repos.",
    ),
    ComponentSpec(
        name="week_picker",
        route="/week_picker",
        root_selector="div.bz-week-picker",
        has_color_axis=True,
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # Comme ses voisins de la famille : la couleur ne teinte rien au
        # repos, elle vit sur l'anneau de focus, l'icône du trigger et la
        # cellule sélectionnée du panneau — donc invisible panneau fermé.
        color_at_rest=False,
        notes="Enveloppe mince sur _picker_field + ui.calendar(mode="
              "\'week\'). color_at_rest=False : rien de teinté au repos.",
    ),
    ComponentSpec(
        name="time_picker",
        route="/time_picker",
        # Le root porte une classe marqueur, contrairement au carousel et
        # au stepper — même convention que ``bz-date-picker``.
        root_selector="div.bz-time-picker",
        has_color_axis=True,
        # La section Sizes met chaque palier dans sa propre cellule de
        # grille : la marche fratrie du probe n'en voit qu'un (Bucket C).
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # La couleur ne teinte rien au repos : elle vit sur l'anneau de
        # focus du cadre, l'icône du trigger et la cellule SÉLECTIONNÉE
        # du panneau — donc rien de visible tant qu'il est fermé.
        color_at_rest=False,
        notes="Panneau à deux colonnes, pas de calendrier. La couleur "
              "n'apparaît qu'au focus ou panneau ouvert, d'où "
              "color_at_rest=False. ⚠️ Les colonnes sont des conteneurs "
              "SCROLLABLES à dessein (24 heures) : un probe qui compte "
              "les scrollbars parasites doit regarder le BODY, pas les "
              "descendants.",
    ),
    ComponentSpec(
        name="color_picker",
        route="/color_picker",
        # Classe marqueur sur le root, même convention que
        # ``bz-date-picker`` et ``bz-time-picker``.
        root_selector="div.bz-color-picker",
        has_color_axis=True,
        # La section size met chaque palier dans sa propre cellule de
        # grille : la marche fratrie du probe n'en voit qu'un.
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # La couleur du composant (``color=``) ne teinte RIEN au repos :
        # elle vit sur l'anneau de focus du cadre. La pastille, elle,
        # rend la VALEUR — qui n'est pas ``color=``.
        color_at_rest=False,
        notes="Panneau de pastilles, pas de calendrier. ⚠️ Deux couleurs "
              "cohabitent et ne veulent pas dire la même chose : "
              "``color=`` habille le CHAMP (anneau de focus), ``value`` "
              "est la couleur ÉDITÉE. Un probe qui cherche la teinte du "
              "composant ne doit pas lire la pastille.",
    ),
    ComponentSpec(
        name="carousel",
        route="/carousel",
        # Root sans classe marqueur : on s'accroche au scope partagé,
        # qui ne peut appartenir qu'à un carousel.
        root_selector="div[bz-data*='$bz.carousel.scope']",
        has_color_axis=True,
        # Comme tabs / stepper : chaque swatch couleur ou taille est son
        # propre frère, sans conteneur qui les regroupe (Bucket C).
        has_size_axis=False,
        # ``per_view`` et ``gap`` sont des axes, mais PAS un ``variant=``
        # au sens du probe (il lit ``theme["variants"]``, absent ici).
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # La couleur ne teinte rien au repos : elle vit sur la puce
        # ACTIVE et sur les anneaux de focus.
        color_at_rest=False,
        notes="Pas de classe marqueur ; hook sur le scope partagé. "
              "color_at_rest=False parce que la couleur s'applique à la "
              "puce active et aux anneaux de focus, pas au wrapper. "
              "⚠️ La piste est un conteneur SCROLLABLE : un probe qui "
              "compte les scrollbars parasites doit regarder le BODY, "
              "pas les descendants — ici l'overflow-x est le mécanisme, "
              "pas un défaut.",
    ),
    ComponentSpec(
        name="signature_pad",
        route="/signature_pad",
        root_selector="div[bz-data*='$bz.signaturePad.scope']",
        has_color_axis=True,
        # Chaque pad de la page est son propre frère, sans conteneur qui
        # les regroupe (Bucket C).
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # La couleur ne teinte rien au repos : elle vit sur la bordure
        # du cadre focalisé et sur le bouton Effacer.
        color_at_rest=False,
        notes="⚠️ Le <canvas> est VIDE au chargement — un probe qui juge "
              "une surface blanche ne juge pas un bug mais l'état "
              "initial. Et il est `aria-hidden` à dessein : ce qui est "
              "annoncé et atteignable au clavier, c'est l'input caché "
              "(un vrai contrôle de formulaire) et le bouton Effacer, "
              "pas la surface de dessin.",
    ),
    ComponentSpec(
        name="resizable",
        route="/resizable",
        # Comme le carousel : pas de classe marqueur sur la racine, on
        # s'accroche au scope partagé, qui ne peut appartenir qu'à un
        # groupe redimensionnable.
        root_selector="div[bz-data*='$bz.resizable.scope']",
        has_color_axis=True,
        # Chaque groupe de la page est son propre frère, sans conteneur
        # qui les regroupe (Bucket C, comme tabs / stepper / carousel).
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # La couleur ne teinte rien au repos : elle vit sur le survol et
        # l'appui de la poignée, et sur son anneau de focus.
        color_at_rest=False,
        notes="Pas de classe marqueur ; hook sur le scope partagé. "
              "⚠️ Les panneaux sont des conteneurs ``overflow-hidden`` à "
              "dessein — c'est ce qui leur permet de RÉTRÉCIR sous la "
              "largeur de leur contenu. Un probe qui juge un contenu "
              "coupé doit regarder si le panneau a été tiré, pas "
              "conclure au clipping.",
    ),
    ComponentSpec(
        name="dropzone",
        route="/dnd",
        # Pas de scope partagé à quoi s'accrocher : le geste est délégué
        # au document, la zone n'émet qu'un contrat de data-attributes.
        # C'est donc CE contrat qui est le sélecteur.
        root_selector="div[data-bz-dropzone]",
        has_color_axis=True,
        # Chaque zone de la page est son propre frère (colonnes d'un
        # kanban, zones locked/libre) sans conteneur qui les regroupe.
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # Au repos la zone est INVISIBLE par construction : sa bordure est
        # `border-transparent`, et la couleur n'apparaît que pendant un
        # geste, sur `data-bz-drop-ok`. Un probe qui cherche une teinte au
        # repos ne trouvera rien, et c'est le comportement voulu.
        color_at_rest=False,
        notes="La couleur ne se voit QUE pendant un drag, via "
              "data-bz-drop-ok posé par le runtime — jamais au repos, et "
              "jamais sur :hover (le navigateur de référence n'a aucun "
              "pointeur fin). ⚠️ Un probe déterministe ne peut donc pas "
              "juger la couleur de ce composant sans piloter un geste : "
              "c'est test_dnd_end_to_end qui couvre le surlignage.",
    ),
    ComponentSpec(
        name="draggable",
        route="/dnd",
        root_selector="div[data-bz-draggable]",
        # Aucun axe : draggable n'est pas un composant visuel, c'est un
        # emballage de comportement. Ce qu'on VOIT est la carte qu'il
        # enveloppe. Sa seule surface propre est la poignée et l'état
        # `data-bz-dragging`, tous deux hors repos.
        has_color_axis=False,
        has_size_axis=False,
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        color_at_rest=False,
        notes="Emballage de comportement, pas de surface visuelle propre "
              "au repos : la carte visible est l'enfant. La poignée "
              "(handle=True) et l'opacité de drag sont ses deux seuls "
              "rendus, le second n'existant que pendant un geste.",
    ),
    ComponentSpec(
        name="stepper",
        route="/stepper",
        # Le root du stepper est <div class="flex flex-col gap-5"
        # bz-data="{...$bz.stepper.scope, current: …}"> sans classe
        # marqueur — on s'accroche au scope partagé, qui ne peut
        # appartenir qu'à un stepper.
        root_selector="div[bz-data*='$bz.stepper.scope']",
        has_color_axis=True,
        # Comme tabs / pagination : chaque swatch de couleur ou de taille
        # est son propre frère, sans conteneur qui les regroupe — la
        # marche fratrie du probe n'en voit qu'un à la fois (Bucket C).
        has_size_axis=False,
        # Deux orientations, mais ce n'est PAS un ``variant=`` : le probe
        # de variant lit ``theme["variants"]``, que le stepper n'a pas
        # (l'orientation vit dans sa propre table, lue par render()).
        has_variant_axis=False,
        is_interactive=True,
        inner_role=None,
        # La couleur ne teinte rien au repos sur le wrapper : elle vit
        # sur les pastilles franchie / courante et les connecteurs.
        color_at_rest=False,
        notes="Pas de classe marqueur ; hook sur le scope partagé. "
              "Chaque swatch couleur/taille est un frère isolé "
              "(Bucket C). color_at_rest=False parce que la couleur "
              "s'applique aux pastilles et connecteurs, pas au wrapper.",
    ),
    ComponentSpec(
        name="breadcrumb",
        route="/breadcrumb",
        # Breadcrumb root is <nav aria-label="Breadcrumb">. The Colors
        # section wraps all 7 in a vstack so the probe's first sibling
        # walk finds them all.
        root_selector='nav[aria-label="Breadcrumb"]',
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
        color_at_rest=False,
        notes="No marker class. Color/size sections wrap in vstack so "
              "the next-sibling walk finds all swatches. BUT color is "
              "applied to inner <a> links, not to the nav root → the "
              "computed-style sampling on the nav collapses to 1 distinct. "
              "Bucket C : probe samples wrong element. color_at_rest=False "
              "reflects design intent.",
    ),
    ComponentSpec(
        name="bottom_bar",
        route="/bottom-bar",
        # La barre rend un ``<nav class="group/bottombar …">`` sans classe
        # marqueur dédiée — on s'accroche au group name, qui ne peut
        # appartenir qu'à elle. Le ``/`` interdit le sélecteur de classe nu.
        root_selector="nav[class*='group/bottombar']",
        # Pas d'axe couleur/taille sur la BARRE (comme navbar/sidebar) : la
        # couleur vit sur l'item, la hauteur est fixe par design.
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
        notes="Tab bar bas d'écran (no color/size axis). Rendue AVEC ses "
              "BottomBarItem. Les barres des cartes sont en sticky=False "
              "(sinon elles s'épinglent toutes au même point) ; la barre "
              "collante réelle est la dernière de la page. css + context.",
    ),
    ComponentSpec(
        name="navbar",
        route="/navbar",
        # Navbar renders as ``<header role="banner" class="...">`` wrapping
        # an inner ``<nav>``. No marker class — anchor on the role.
        root_selector='header[role="banner"]',
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
        notes="Structural top bar (no color/size axis). Rendered WITH "
              "NavbarSection + NavbarItem children. css + context only.",
    ),
    ComponentSpec(
        name="sidebar",
        route="/sidebar",
        # Sidebar renders as ``<aside class="...">`` rail. No marker class —
        # anchor on the tag.
        root_selector="aside",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
        notes="Structural navigation rail (no color/size axis). Rendered "
              "WITH SidebarSection + SidebarItem children. css + context "
              "only.",
    ),
]

TIER_8_CHARTS = [
    ComponentSpec(
        name="sparkline",
        route="/sparkline",
        # Sparkline renders as ``<svg role="img" aria-label="Sparkline — …">``
        # — no ``bz-sparkline`` marker class. Match by aria-label prefix.
        root_selector='svg[aria-label^="Sparkline"]',
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=False,
        inner_role=None,
        color_at_rest=False,
        notes="No marker class. Playground COLORS list = 6 entries (no "
              "'secondary'), but probe expects 7 → mismatch (Bucket A on "
              "count). Color tint lives on inner <path stroke-{color}>, "
              "not on the <svg> wrapper → computed-style sampling on the svg "
              "root collapses to 1 distinct (Bucket C : probe should sample "
              "inner path[class*=stroke-] for SVG charts). Skip via "
              "color_at_rest=False until an SVG-aware probe lands.",
    ),
    ComponentSpec(
        name="bar_chart",
        route="/bar_chart",
        # BarChart renders as ``<svg role="img" aria-label="Bar chart — …">``.
        root_selector='svg[aria-label^="Bar chart"]',
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        inner_role=None,
        color_at_rest=False,
        notes="No marker class. Color on inner <rect fill-{color}>, not on "
              "svg root. Playground COLORS = 6 (probe expects 7 → Bucket A "
              "count mismatch). Bucket C : SVG charts need an inner-shape "
              "sampling probe. Skip via color_at_rest=False.",
    ),
    ComponentSpec(
        name="line_chart",
        route="/line_chart",
        root_selector='svg[aria-label^="Line chart"]',
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        inner_role=None,
        color_at_rest=False,
        notes="Same as bar_chart : color on inner <path stroke-{color}>. "
              "Playground COLORS = 6. Bucket A count + Bucket C inner-shape. "
              "Skip via color_at_rest=False.",
    ),
    ComponentSpec(
        name="pie_chart",
        route="/pie_chart",
        # PieChart renders as ``<svg role="img" aria-label="Pie chart — …">``.
        # No ``color=`` axis (palette cycles internally) → no "Colors" h3
        # in the playground Reference card.
        root_selector='svg[aria-label^="Pie chart"]',
        has_color_axis=False,
        has_size_axis=True,
        is_interactive=True,
        inner_role=None,
        notes="No marker class. No color= prop — palette cycles internally "
              "across slices. Hence no 'Colors' h3 in Reference (probe's "
              "anchor lookup fails by design — skip with has_color_axis=False).",
    ),
    ComponentSpec(
        name="scatter_chart",
        route="/scatter_chart",
        # ScatterChart renders as ``<svg role="img" aria-label="Scatter — …">``.
        root_selector='svg[aria-label^="Scatter"]',
        has_color_axis=True,
        has_size_axis=True,
        is_interactive=True,
        inner_role=None,
        color_at_rest=False,
        notes="No marker class. Same as line_chart : color on inner "
              "<circle class*=fill-{color}> dots, not on the svg root. "
              "Bucket C : SVG charts need an inner-shape sampling probe. "
              "Skip via color_at_rest=False.",
    ),
]

TIER_11_META = [
    ComponentSpec(
        name="meta",
        route="/meta",
        root_selector="body",
        has_color_axis=False,
        has_size_axis=False,
        is_interactive=False,
        inner_role=None,
        notes="Side-effect components (Title, MetaTag, Fragment) — "
              "only structural HTML checks apply.",
    ),
]


COMPONENT_SPECS: dict[str, list[ComponentSpec]] = {
    "tier_1": TIER_1_PRIMITIVES_LAYOUT,
    "tier_2": TIER_2_FORMS,
    "tier_3": TIER_3_FEEDBACK,
    "tier_4": TIER_4_OVERLAYS,
    "tier_5": TIER_5_DATA,
    "tier_6": TIER_6_NAV,
    "tier_8": TIER_8_CHARTS,
    "tier_11": TIER_11_META,
}


def all_specs() -> list[ComponentSpec]:
    out: list[ComponentSpec] = []
    for specs in COMPONENT_SPECS.values():
        out.extend(specs)
    return out

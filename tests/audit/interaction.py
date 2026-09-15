"""Interactive audit probes — drive playground controls + verify the
preview reacts as expected.

Three complementary classes of check :

1. **Carrier-landing** (static) — for every ``bz-attr:<attr>`` directive
   in the page, verify the host element is one where ``<attr>`` actually
   does work. ``disabled`` / ``multiple`` / ``checked`` etc. only act on
   form controls ; landing them on a ``<div>`` is a no-op. This catches
   the wrapper-vs-carrier trap (cf. ``traps.md``) without any clicks.
   The attribute→tags table lives in :mod:`tests.audit.carriers`, shared
   with the browser-free gate
   ``tests/consistency/test_binding_lands_on_carrier.py`` — run that one
   first, it's in the fast subset.

2. **Server-prop drives DOM** (interaction) — for every control in a
   Server playground panel, toggle it through each value and assert
   the preview DOM converges to the same structure the server would
   render fresh for that state. Catches idiomorph guard traps (cf. the
   ``:class`` dropped-binding trap) and variant-switch traps.

3. **Client-binding drives carrier** (interaction) — for every switch
   in a Client playground panel, toggle it and assert that
   ``$bz.state.<Class>.<key>.<field>`` flips AND the corresponding
   HTML attribute on the carrier reflects the new value within a
   reactive tick.

Each probe is callable from the main agent's CLI driver or a subagent's
parallel worker. Results are :class:`ProbeResult` so they slot into the
existing audit report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Page

from tests.audit.carriers import ATTR_CARRIERS, BZ_ATTR_PREFIX
from tests.audit.probes import ProbeResult


# ─────────────────────────────────────────────────────────────────
# Carrier-landing : which HTML attributes act on what kinds of element
# ─────────────────────────────────────────────────────────────────
#
# La table (et le préfixe de directive) vivent dans
# :mod:`tests.audit.carriers`, partagés avec la gate browser-free
# ``tests/consistency/test_binding_lands_on_carrier.py``. Recopier l'un
# ou l'autre ici est exactement ce qui a fait pourrir ce probe : il a
# cherché ``x-bz-prop:`` (Alpine-era) pendant des mois après le rebrand
# ``bz-``, sans jamais matcher un seul attribut — donc toujours vert.


def _attr_carrier_violations(
    page: Page,
) -> list[dict[str, str]]:
    """Walk every ``bz-attr:<attr>`` directive on the page ; return
    violations where the attr lives on an element where it's a no-op.

    Custom elements (``bz-calendar``, ``iconify-icon``, …) are valid
    carriers for any attribute — they handle reactivity through
    ``attributeChangedCallback``.
    """
    findings: list[dict[str, str]] = page.evaluate(
        """([carrierMap, prefix]) => {
            const findings = [];
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const tag = el.tagName.toLowerCase();
                // Custom elements own their attribute reactivity via
                // ``attributeChangedCallback`` : the runtime writes the
                // attribute, the element handles the rest.
                if (tag.includes('-')) continue;
                for (const a of el.attributes) {
                    if (!a.name.startsWith(prefix)) continue;
                    const attr = a.name.substring(prefix.length);
                    const carriers = carrierMap[attr];
                    // Absent from the map = universal (aria-*, data-*,
                    // class, style, hidden, …), never a violation.
                    if (carriers === undefined) continue;
                    if (!carriers.includes(tag)) {
                        findings.push({
                            attr,
                            tag,
                            allowed: carriers.join(','),
                            path: a.value,
                            outer: el.outerHTML.slice(0, 180),
                        });
                    }
                }
            }
            return findings;
        }""",
        [{k: sorted(v) for k, v in ATTR_CARRIERS.items()}, BZ_ATTR_PREFIX],
    )
    return findings


def probe_client_binding_lands_on_carrier(
    page: Page,
) -> ProbeResult:
    """Static check : every ``bz-attr:<attr>`` directive lives on an
    element where ``<attr>`` actually does something.

    The classic offender (file_upload pre-fix) emitted ``bz-attr:disabled``
    on the wrapper ``<div>`` — the runtime flipped the attribute on every
    state change, but ``disabled`` on a ``<div>`` is a no-op, so the
    picker stayed clickable. The probe catches that statically by
    reading the page once and consulting a tag whitelist per attribute.

    Le même contrat tourne sans navigateur (et bien plus tôt) dans
    ``tests/consistency/test_binding_lands_on_carrier.py``. Ce probe-ci
    garde une valeur propre : il lit le DOM **monté**, donc il verrait
    une directive posée par le runtime que le SSR n'a jamais émise.

    Verdict policy : zero violations = PASS. One or more = FAIL with
    the full violation list in ``detail`` (subagents log + the main
    agent triages).
    """
    findings = _attr_carrier_violations(page)
    if not findings:
        return ProbeResult(
            True, "carrier_landing",
            f"every {BZ_ATTR_PREFIX}<attr> lives on a tag where the "
            "attribute is meaningful",
        )
    # Compact one-line-per-finding output so subagent reports stay
    # readable when 20+ components fail at once.
    lines = []
    for f in findings[:12]:  # cap at 12 to keep detail bounded
        lines.append(
            f"{BZ_ATTR_PREFIX}{f['attr']} on <{f['tag']}> "
            f"(carrier must be one of : {f['allowed']}) — "
            f"path={f['path']!r}"
        )
    if len(findings) > 12:
        lines.append(f"... and {len(findings) - 12} more")
    return ProbeResult(
        False, "carrier_landing",
        f"{len(findings)} ClientBinding(s) emitted on the wrong tag : \n"
        + "\n".join(lines),
    )


# ─────────────────────────────────────────────────────────────────
# Playground enumerator — discover controls per page
# ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlaygroundControl:
    """One playground control bound to a state field."""
    panel: str               # "server" | "client"
    name: str                # the ``name=`` attribute → state field
    kind: str                # "checkbox" | "select" | "input" | "textarea" | "switch"
    current_value: str       # SSR snapshot
    candidates: tuple[str, ...] = ()   # values worth toggling through
    # Native ``<input type="...">`` value when the control is a plain
    # text-family input. Used by the probe driver to generate
    # type-appropriate sentinels — typing ``"AUDIT_VALUE_…"`` into an
    # ``<input type="number">`` is silently rejected by browsers AND
    # crashes any ``server_changed`` handler doing ``int(value)`` on
    # the bound state.
    input_type: str = "text"


def _enumerate_controls(page: Page) -> list[PlaygroundControl]:
    """Find every Server/Client playground control on the current page.

    The playground convention :
    - Server panel is a card whose h2 contains "Server playground" ;
      controls bound to a ``ServerState`` field via ``ui.select`` /
      ``ui.input`` / ``ui.textarea``.
    - Client panel is a card whose h2 contains "Client playground" ;
      controls bound to a ``ClientState`` field via ``ui.switch`` /
      ``ui.checkbox``.

    Each control has a ``name=<field>`` on its hidden / native form
    input. We scope the lookup to the panel card so unrelated inputs
    (Reference cards, Events panel) don't pollute the enumeration.
    """
    raw = page.evaluate(
        """() => {
            function panelFor(headingText) {
                const hs = [...document.querySelectorAll('h2')];
                const h = hs.find(h => h.textContent.includes(headingText));
                if (!h) return null;
                // Walk up to the card boundary (`.bz-card` or the
                // closest container whose direct sibling carries
                // another h2).
                return h.closest('.bz-card') || h.closest('div').parentElement;
            }
            function panelControls(panel, label) {
                if (!panel) return [];
                const out = [];
                const seen = new Set();
                const inputs = panel.querySelectorAll('input[name], select[name], textarea[name]');
                for (const inp of inputs) {
                    const name = inp.getAttribute('name');
                    if (!name) continue;
                    if (seen.has(name)) continue;
                    seen.add(name);
                    let kind = inp.tagName.toLowerCase();
                    let current = '';
                    let input_type = (inp.type || 'text').toLowerCase();
                    if (kind === 'input') {
                        const t = input_type;
                        if (t === 'checkbox') {
                            kind = 'checkbox';
                            // ``inp.value`` on a checkbox is the form-data
                            // payload ("on" by default), NOT the toggle
                            // state. Read ``inp.checked`` for truth.
                            current = inp.checked ? 'on' : 'off';
                        }
                        else if (t === 'hidden') {
                            // Hidden inputs often hide a bz-select or bz-switch.
                            const host = inp.closest('.bz-select') ||
                                         inp.closest('.bz-switch') ||
                                         inp.closest('.bz-combobox') ||
                                         inp.closest('.bz-toggle_group') ||
                                         inp.closest('.bz-tag_input');
                            if (host) {
                                kind = host.className.match(/bz-(\\w+)/)[1];
                            }
                            else if (!inp.hasAttribute('bz-model')) {
                                // Un porteur CACHE a sens unique n'est
                                // pas un controle : il porte
                                // ``bz-attr:value="String($bz.state…)"``,
                                // que l'etat ECRIT et que rien ne lit en
                                // retour. Y taper une valeur ne propage
                                // donc rien, et la sonde en concluait
                                // « le binding n'a jamais atteint le
                                // porteur » — sur un composant dont la
                                // demo et le reglage lisent pourtant le
                                // MEME champ. Mesure du 2026-08-28 sur
                                // ``/slider`` : les DEUX instances
                                // portent ``bz-attr:value`` sur
                                // ``SliderClient.playground.volume``, et
                                // aucune ne porte ``bz-model``.
                                //
                                // Le vrai reglage d'un slider est sa
                                // piste, qui se pilote au pointeur —
                                // hors de portee d'une sonde qui tape
                                // des valeurs. Mieux vaut n'en tester
                                // aucun que d'en inventer un.
                                continue;
                            }
                            current = inp.value || '';
                        } else {
                            kind = t;
                            current = inp.value || '';
                        }
                    } else {
                        current = inp.value || '';
                    }
                    // Collect candidate values.
                    let candidates = [];
                    if (kind === 'checkbox' || kind === 'switch') {
                        candidates = ['on', 'off'];
                    } else if (kind === 'select') {
                        const scope = inp.closest('.bz-select');
                        if (scope) {
                            // bz-select keeps options as a list of
                            // [role="option"] descendants. Read the
                            // ``data-value`` attribute — NOT the
                            // textContent which is the user-facing
                            // label. The bound state must receive
                            // the value, not the label, otherwise
                            // ``active === state`` comparisons stay
                            // false (the tabs probe report flagged
                            // exactly this when the probe sent "A"
                            // instead of "a").
                            const opts = [...scope.querySelectorAll('[role="option"]')];
                            // ``hasAttribute`` et non ``||`` : la chaine
                            // VIDE est une valeur legitime, et ``||`` la
                            // prenait pour une absence. Le repli rendait
                            // alors le LIBELLE — ``(aucun)`` — que la sonde
                            // envoyait ensuite au select comme cible. Le
                            // select ne peut pas la prendre, rien ne bouge,
                            // et la sonde concluait « le binding n'a pas
                            // atteint le porteur » sur un composant sain.
                            // Mesure du 2026-09-07 : c'etait le seul rouge
                            // de l'audit (``diagram``, dont l'option vide
                            // est la premiere ET la valeur courante).
                            candidates = opts.map(o => (
                                o.hasAttribute('data-value')
                                    ? o.getAttribute('data-value')
                                    : o.textContent.trim()
                            ));
                        }
                    }
                    out.push({
                        panel: label,
                        name,
                        kind,
                        current_value: current,
                        candidates,
                        input_type,
                    });
                }
                return out;
            }
            return [
                ...panelControls(panelFor('Server playground'), 'server'),
                ...panelControls(panelFor('Client playground'), 'client'),
            ];
        }"""
    )
    return [
        PlaygroundControl(
            panel=c["panel"],
            name=c["name"],
            kind=c["kind"],
            current_value=c["current_value"],
            candidates=tuple(c["candidates"]),
            input_type=c.get("input_type", "text"),
        )
        for c in raw
    ]


def _type_appropriate_sentinels(ctl: PlaygroundControl) -> tuple[str, str]:
    """Two distinct test values appropriate for the control's input
    type. Typing a string into ``<input type="number">`` is silently
    rejected by the browser AND crashes server-side ``int(value)``
    coercion in any ``server_changed`` handler, so we generate
    numeric / date / text sentinels per HTML5 input type.
    """
    t = ctl.input_type
    if t == "number":
        return ("42", "137")
    if t == "date":
        return ("2026-01-15", "2026-07-04")
    if t == "datetime-local":
        return ("2026-01-15T09:00", "2026-07-04T12:30")
    if t == "time":
        return ("09:30", "14:45")
    if t == "month":
        return ("2026-01", "2026-07")
    if t == "week":
        return ("2026-W03", "2026-W27")
    if t == "color":
        return ("#ff0000", "#00ff00")
    if t == "range":
        return ("25", "75")
    if t == "email":
        return ("alpha@audit.test", "beta@audit.test")
    if t == "url":
        return ("https://alpha.audit", "https://beta.audit")
    if t == "tel":
        return ("+15551234567", "+15559876543")
    return (_TEXT_PROBE_VALUE_A, _TEXT_PROBE_VALUE_B)


# ─────────────────────────────────────────────────────────────────
# Driver helpers — flip a control to a target value
# ─────────────────────────────────────────────────────────────────


def _flip_control(
    page: Page,
    control: PlaygroundControl,
    value: str,
    *,
    wait_ms: int = 1500,
) -> bool:
    """Set ``control`` to ``value`` and wait for any swap to settle.

    Returns True if the interaction was driven, False if the control
    couldn't be reached (e.g. selector race). Subagents log either way.

    Scopes the input lookup to the control's panel — when both Server
    and Client playgrounds expose a same-named control (``disabled``,
    ``multiple``, …) a global ``document.querySelector`` would pick
    the wrong one and the wrong panel's state mutates.
    """
    panel_heading = (
        "Server playground" if control.panel == "server"
        else "Client playground"
    )
    js = """
    async (args) => {
        // ── Attendre l'ETAT, pas une duree ────────────────────────
        // Ce helper a remplace un `setTimeout(1500)` inconditionnel le
        // 2026-08-31. Ce sommeil-la etait 88 a 92 % du temps de TOUT
        // l'audit visuel — mesure par composant : 46 s sur 52 pour
        // `button`, 30 s sur 33 pour `badge`, les sept autres probes
        // tenant ensemble en moins de 3 s. A ~2 000 manipulations sur
        // les 74 composants, la suite passait ~50 minutes a ne rien
        // faire, donc elle ne se lancait jamais.
        //
        // Deux phases, et la premiere n'est pas negociable : un
        // controle peut DEBOUNCER avant de poster, donc rendre la main
        // des que le DOM est calme lirait une signature perimee et
        // rapporterait « cette prop ne fait rien » sur une prop qui
        // marche. On laisse donc au coup de partir (`floor`), puis on
        // attend qu'il retombe.
        const settle = async () => {
            const t0 = Date.now();
            let last = 0;
            const obs = new MutationObserver(() => { last = Date.now(); });
            obs.observe(document.documentElement, {
                subtree: true, childList: true,
                attributes: true, characterData: true,
            });
            try {
                // Phase 1 — laisser le temps au depart : une requete en
                // vol, ou une mutation, ou l'expiration du plancher.
                while (Date.now() - t0 < args.floor) {
                    await new Promise(r => setTimeout(r, 20));
                    if (last || document.querySelector('.htmx-request')) break;
                }
                // Phase 2 — attendre le retour au calme, sous plafond.
                while (Date.now() - t0 < args.wait) {
                    await new Promise(r => setTimeout(r, 20));
                    if (document.querySelector('.htmx-request')) continue;
                    if (last && Date.now() - last >= args.quiet) return;
                    if (!last && Date.now() - t0 >= args.floor) return;
                }
            } finally {
                obs.disconnect();
            }
        };

        // Find the panel card by its h2 heading.
        const hs = [...document.querySelectorAll('h2')];
        const h = hs.find(h => h.textContent.includes(args.panelHeading));
        if (!h) return 'NO_PANEL';
        const card = h.closest('[class*="bg-surface"]') ||
                     (h.parentElement && h.parentElement.parentElement);
        if (!card) return 'NO_CARD';
        const inp = card.querySelector(
            `input[name="${args.name}"], select[name="${args.name}"], textarea[name="${args.name}"]`,
        );
        if (!inp) return 'NO_INPUT';
        if (args.kind === 'checkbox' || args.kind === 'switch') {
            // The visible toggle is a button next to the hidden checkbox.
            const want = args.value === 'on';
            if (!!inp.checked === want) return 'NO_CHANGE';
            const wrap = inp.closest('label, .bz-switch, .bz-checkbox')
                       || inp.parentElement;
            const btn = wrap.querySelector('[role="switch"], button, [role="button"]')
                       || inp;
            btn.click();
            await settle();
            return 'CLICKED';
        }
        if (args.kind === 'select') {
            // Open the bz-select trigger, click the matching option
            // FROM THIS SELECT'S PANEL — never from the global
            // ``[role="option"]`` pool. Reference cards on the same
            // page render multiple bz-selects with overlapping value
            // sets ; a global lookup would land on whichever was
            // first in DOM order and dispatch the click on the wrong
            // select's ``_pick`` handler (state never moves on the
            // bound select, audit reports a phantom binding bug).
            const scope = inp.closest('.bz-select');
            if (!scope) return 'NO_SCOPE';
            const trig = scope.querySelector('button, [role="combobox"], [role="button"]');
            trig.click();
            await new Promise(r => setTimeout(r, 250));
            const opts = [...scope.querySelectorAll('[role="option"]')];
            const hit = opts.find(o => (
                (o.getAttribute('data-value') || o.textContent.trim()) === args.value
            ));
            if (!hit) return 'NO_OPTION';
            hit.click();
            await settle();
            return 'CLICKED';
        }
        if (args.kind === 'text' || args.kind === 'input' || args.kind === 'textarea') {
            inp.value = args.value;
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            await settle();
            return 'TYPED';
        }
        return 'UNKNOWN_KIND';
    }
    """
    result = page.evaluate(
        js,
        {
            "name": control.name,
            "kind": control.kind,
            "value": value,
            "wait": wait_ms,
            # Le plancher couvre un debounce de 300 ms ; le silence de
            # 120 ms declare le swap retombe. Les deux sont sous le
            # plafond `wait`, qui reste le dernier mot.
            "floor": 320,
            "quiet": 120,
            "panelHeading": panel_heading,
        },
    )
    return result in ("CLICKED", "TYPED", "NO_CHANGE")


# ─────────────────────────────────────────────────────────────────
# Probe : server-playground prop drives the preview DOM
# ─────────────────────────────────────────────────────────────────


# Props that legitimately produce no observable DOM change at rest.
# A control whose toggle leaves the preview signature byte-equal is
# only reportable when its prop is NOT in this set.
#
# Rationale per entry :
# - ``visible`` removes the demo entirely — the signature lookup
#   doesn't find a node, can't compare.
# - ``classes`` adds user-defined classes — we can't predict the
#   expected suffix per candidate.
# - ``tooltip`` mounts an x-show panel that only appears on hover.
# - ``style`` lands as raw CSS we can't oracle.
# - ``extra_attrs`` is freeform key=value.
# - ``aria_label`` only mutates an ARIA attribute that some
#   components legitimately ignore (e.g. when there's a visible label).
# - ``custom_id`` / ``id`` / ``tag`` are framework chrome.
# - ``show_html`` / ``show_code`` / ``show_source`` are the per-card
#   ``emitted_html_block`` toggles, not the component being audited.
# - ``upload_url`` is a network endpoint, only takes effect on submit.
# - ``required`` legitimately adds ``required`` to a deeply-nested
#   ``<input>`` that some component-root signatures don't include
#   (the form-data-only props). Caught instead by the carrier-landing
#   probe + the per-component form unit tests.
_SERVER_PROP_DOM_IRRELEVANT: frozenset[str] = frozenset({
    "visible", "tooltip", "style", "extra_attrs", "aria_label",
    "custom_id", "id", "classes", "tag",
    "show_html", "show_code", "show_source",
    "upload_url",
    "required",
})


# Sentinel test values for free-form text fields. Two distinct values
# are enough — if the demo signature reflects neither, the prop is
# ignored. Numeric strings are used as the universal default because
# many playgrounds expose ``int`` / ``float`` state fields through a
# plain ``<input type="text">`` (the renderer doesn't promote the
# HTML5 type from the Python type) — typing ``"AUDIT_VALUE_…"`` into
# those crashed the playground's ``int(value)`` coercion before the
# binding ever ran. ``"42"`` / ``"137"`` parse cleanly as int, float,
# AND string, so the same sentinel pair survives every state-field
# type at the playground level. Type-aware overrides (date / email /
# color / range / etc.) still apply per `_type_appropriate_sentinels`.
_TEXT_PROBE_VALUE_A = "42"
_TEXT_PROBE_VALUE_B = "137"


def probe_server_props_drive_dom(
    page: Page,
    *,
    preview_selector: str,
    skip_props: tuple[str, ...] = (),
) -> ProbeResult:
    """For each Server playground control whose prop is in the
    DOM-affecting whitelist, cycle through its candidate values and
    verify the preview's DOM signature differs.

    Signature = ``outerHTML`` with ``bz-version="..."`` stripped (the
    framework's content hash recomputes on every render — keeping it
    in the diff would cause every snapshot to look different by
    accident). If the signature is byte-equal across all candidates,
    the prop is either : (a) wired to a render branch the server
    never takes, (b) suppressed by the morph guard, or (c) ignored
    silently.

    Caller passes ``preview_selector`` = the root selector AT THE
    SERVER PLAYGROUND CARD'S PREVIEW INSTANCE (not the global one ;
    the probe scopes the lookup to the Server playground card by
    walking from its h2). ``skip_props`` extends the built-in skip
    list with component-specific exceptions.
    """
    # Every server control whose prop is not in the known-irrelevant
    # list. Text / textarea / number inputs are tested by typing two
    # distinct sentinel values ; selects / switches by cycling through
    # their candidates ; anything else is skipped (no test plan).
    controls = [
        c for c in _enumerate_controls(page)
        if c.panel == "server"
        and c.name not in skip_props
        and c.name not in _SERVER_PROP_DOM_IRRELEVANT
        and (
            len(c.candidates) >= 2
            or c.kind in ("text", "input", "textarea", "number", "email",
                          "tel", "url", "search")
        )
    ]
    if not controls:
        return ProbeResult(
            True, "server_props_drive_dom",
            "no testable server props on this playground",
        )

    # When the audited component IS a form-input type
    # (``.bz-switch`` / ``.bz-checkbox`` / ``.bz-select`` / …), the
    # demo IS one of those classes — so we must NOT exclude it from
    # the search. Derive the component class from the preview selector
    # and drop it from the exclusion list.
    excluded_ctrls = [
        ".bz-switch", ".bz-checkbox", ".bz-select", ".bz-combobox",
        ".bz-toggle_group", ".bz-tag_input", ".bz-radio", ".bz-slider",
        ".bz-input", ".bz-textarea", ".bz-number_input",
    ]
    excluded_ctrls = [
        cls for cls in excluded_ctrls
        if cls.lstrip(".") not in preview_selector
    ]
    ctrl_sel = ", ".join(excluded_ctrls)

    def _signature() -> str | None:
        return page.evaluate(
            """(args) => {
                const hs = [...document.querySelectorAll('h2')];
                const h = hs.find(h => h.textContent.includes('Server playground'));
                if (!h) return null;
                const card = h.closest('[class*="bg-surface"]') ||
                             (h.parentElement && h.parentElement.parentElement);
                if (!card) return null;
                // Find the ``emitted_html_block`` boundary inside the
                // card : the hstack that hosts the
                // ``input[name="show_html"]`` switch and everything
                // that follows it (the label text + code block) are
                // playground chrome, NOT the demo. We detect the
                // boundary by walking up from the show_html switch
                // to the first direct child of the card.
                const showHtml = card.querySelector('input[name="show_html"]');
                let boundary = null;
                if (showHtml) {
                    let p = showHtml;
                    while (p && p.parentElement !== card) p = p.parentElement;
                    boundary = p;
                }
                // Filter out controls (other component types' driving
                // the demo props) and anything at-or-after the
                // emitted_html_block boundary.
                const ctrlSel = args.ctrlSel;
                const all = [...card.querySelectorAll(args.rootSel)];
                const candidates = all.filter(el => {
                    if (ctrlSel && el.closest(ctrlSel)) return false;
                    if (boundary) {
                        // Reject if ``el`` is the boundary itself
                        // OR sits inside it OR appears DOM-order
                        // after it among the card's children.
                        const within = boundary.contains(el);
                        if (within) return false;
                        // ``compareDocumentPosition`` returns
                        // ``DOCUMENT_POSITION_FOLLOWING`` (4) when el
                        // comes AFTER boundary, ``PRECEDING`` (2) when
                        // it comes BEFORE.
                        const pos = boundary.compareDocumentPosition(el);
                        if (pos & 4) return false;  // el is after boundary
                    }
                    return true;
                });
                const demo = candidates[candidates.length - 1];
                if (!demo) return null;
                // Strip framework-managed cache busters so identity
                // changes don't read as "the prop did something".
                return demo.outerHTML
                    .replace(/bz-version="[^"]+"/g, '')
                    .replace(/bz-id="[^"]+"/g, '')
                    .replace(/\\sid="[^"]+"/g, '');
            }""",
            {"rootSel": preview_selector, "ctrlSel": ctrl_sel},
        )

    findings: list[str] = []
    for ctl in controls:
        # Pick the values to try based on the control kind.
        if ctl.candidates:
            test_values = list(ctl.candidates[:4])
        else:
            a, b = _type_appropriate_sentinels(ctl)
            test_values = [a, b]
        captured: list[tuple[str, str]] = []
        for v in test_values:
            if not _flip_control(page, ctl, v):
                continue
            sig = _signature()
            if sig is not None:
                captured.append((v, sig))
        if len(captured) < 2:
            continue
        unique = {sig for _, sig in captured}
        if len(unique) == 1:
            findings.append(
                f"server prop {ctl.name!r} cycled through "
                f"{[v for v, _ in captured]} but preview DOM signature "
                f"stayed byte-equal"
            )
    if not findings:
        return ProbeResult(
            True, "server_props_drive_dom",
            f"all {len(controls)} tested server prop(s) visibly "
            f"change the preview when toggled",
        )
    return ProbeResult(
        False, "server_props_drive_dom",
        f"{len(findings)} server prop(s) did NOT visibly affect "
        f"preview :\n" + "\n".join(findings),
    )


# ─────────────────────────────────────────────────────────────────
# Probe : client-playground switch drives the carrier attribute
# ─────────────────────────────────────────────────────────────────


def probe_client_switches_drive_carrier(
    page: Page,
    *,
    component_root_selector: str,
    skip_props: tuple[str, ...] = (),
) -> ProbeResult:
    """Toggle each Client playground switch and verify :

    1. The bound ``$bz.state.<Class>.<key>.<field>`` flips.
    2. SOME attribute on or inside the rendered component root reflects
       the new value within ~500ms.

    If the state flips but no attribute on the component changes, the
    binding never reached the carrier — exactly the wrapper-vs-carrier
    bug class.

    The component root is looked up INSIDE the Client playground card
    — many pages render multiple instances (Reference / Examples cards)
    and ``document.querySelector`` would pick the wrong one.
    """
    # Every Client playground control — switches, selects, text
    # inputs, textareas, sliders. Skip pure code-display chrome and
    # any prop the spec marked as a structural probe-skip.
    controls = [
        c for c in _enumerate_controls(page)
        if c.panel == "client"
        and c.name not in ("show_html", "show_code", "show_source")
        and c.name not in skip_props
        and (
            len(c.candidates) >= 2
            or c.kind in ("text", "input", "textarea", "number", "email",
                          "tel", "url", "search")
        )
    ]
    if not controls:
        return ProbeResult(
            True, "client_switches_drive_carrier",
            "no client-playground bindings found (only code-display "
            "toggles) ; nothing to test",
        )

    # Building blocks of a playground control — when ``component_root_
    # selector`` is broad (``button``, ``div``, …), the first match
    # inside the Client playground card is often the switch / select
    # row above the demo. Skip elements whose ancestors are themselves
    # bz-input components and prefer the last matching element (demo
    # is always rendered AFTER the controls in the playground flow).
    CONTROL_HOSTS = (
        ".bz-switch, .bz-checkbox, .bz-select, .bz-combobox, "
        ".bz-toggle_group, .bz-tag_input, .bz-radio, .bz-slider, "
        ".bz-input, .bz-textarea, .bz-number_input"
    )

    def _snapshot(driven_name: str | None = None) -> str | None:
        return page.evaluate(
            """(args) => {
                const hs = [...document.querySelectorAll('h2')];
                const h = hs.find(h => h.textContent.includes('Client playground'));
                if (!h) return null;
                const card = h.closest('[class*="bg-surface"]') ||
                             (h.parentElement && h.parentElement.parentElement);
                // ── QUI regarder ────────────────────────────────
                // Plus de « trouver LA demo ». La question n'a pas de
                // reponse fiable par position, et deux heuristiques s'y
                // sont cassees le 2026-08-28 : la frontiere ``show_html``
                // avalait les QUATRE instances de ``/switch``, et le repli
                // ``all[last]`` ramassait alors le switch de l'inspecteur
                // du playground — lie a un tout autre etat, donc immobile.
                //
                // L'oracle est plus simple ET plus juste : on pilote UN
                // controle, et on exige que quelque chose d'AUTRE que lui
                // bouge dans la carte. C'est litteralement la question
                // posee — « le binding a-t-il atteint un porteur ? » — et
                // elle ne demande plus de designer lequel.
                //
                // Ca compte parce que sur ``/switch``, ``/slider``,
                // ``/toggle_group`` et les trois pickers, le composant
                // sous test EST la classe dont le playground fait ses
                // reglages : la demo et le controle sont des jumeaux que
                // rien dans le DOM ne distingue.
                // ETRE l'inspecteur, pas le CONTENIR. La premiere
                // version testait ``querySelector`` sur les descendants,
                // donc elle condamnait aussi le conteneur qui enveloppe
                // toute la carte — et sur un composant dont le selecteur
                // est ``:scope > div`` (alert), l'unique enfant direct
                // etait ce conteneur : plus aucune cible, et la sonde
                // disait « preview introuvable ». Mesure du 2026-08-28.
                //
                // Le bon test : l'element porte lui-meme la liaison, ou
                // il est l'HOTE DIRECT du controle qui la porte.
                const isChrome = (el) => {
                    const own = el.getAttribute && el.getAttribute('bz-model');
                    if (own && own.indexOf('PlaygroundInspector') !== -1) {
                        return true;
                    }
                    const inner = el.querySelector(
                        '[bz-model*="PlaygroundInspector"]');
                    return !!(inner && inner.closest(args.ctrlSel) === el);
                };
                // Le champ qu'on pilote : sa propre bascule n'est pas une
                // preuve, c'est la SOURCE. On le neutralise dans la
                // signature — et LUI SEUL, pas son hote.
                //
                // Retirer l'hote entier etait la version d'avant, et elle
                // se cassait sur l'autonommage : le champ cache d'une demo
                // porte le nom du champ d'etat qu'elle lie, donc il
                // s'appelle comme le controle. Sur ``/accordion``,
                // ``[name="expanded"]`` designait la DEMO, dont l'hote se
                // retrouvait exclu — plus une seule cible, « preview
                // introuvable ». Mesure du 2026-08-28.
                //
                // Meme selecteur que ``_flip_control`` : ce qu'on
                // neutralise doit etre exactement ce qui a ete pilote,
                // sinon les deux se decalent en silence.
                let drivenInput = null;
                if (args.drivenName) {
                    const n = args.drivenName;
                    drivenInput = card.querySelector(
                        'input[name="' + n + '"], select[name="' + n + '"], ' +
                        'textarea[name="' + n + '"]');
                }
                const usable = [...card.querySelectorAll(args.rootSel)]
                    .filter(el => !isChrome(el));
                // On PREFERE juger sur autre chose que l'hote du controle
                // pilote : si son enveloppe porte elle-meme un
                // ``data-state`` lie au meme modele, sa bascule prouverait
                // seulement que la source a bouge — un vert vide.
                //
                // Mais quand c'est le SEUL porteur de la page (une demo
                // dont le champ cache s'appelle comme le controle, cf.
                // l'autonommage), l'exclure ne laisserait rien : on le
                // garde alors, prive de son champ pilote, ce qui suffit —
                // le reste de ses attributs vient bien du binding.
                const host = drivenInput &&
                             (drivenInput.closest(args.ctrlSel) || drivenInput);
                const others = host
                    ? usable.filter(el => el !== host && !host.contains(el))
                    : usable;
                const targets = others.length ? others : usable;
                if (!targets.length) return null;
                const parts = [];
                function record(el) {
                    if (el === drivenInput) return;
                    for (const a of el.attributes) {
                        parts.push(el.tagName + ':' + a.name + '=' + a.value);
                    }
                    for (const n of el.querySelectorAll('*')) {
                        for (const a of n.attributes) {
                            parts.push(
                                n.tagName + ':' + a.name + '=' + a.value
                            );
                        }
                    }
                    // Les PROPRIETES des controles a valeur. Meme
                    // raison que le ``textContent`` juste en dessous, et
                    // c'est la moitie qui manquait : un ``bz-model`` sur
                    // un <input> ecrit ``el.value``, JAMAIS l'attribut
                    // homonyme. Mesure du 2026-08-28 sur ``/input`` :
                    // apres saisie, ``prop`` vaut '42' et ``attr`` vaut
                    // encore 'hello' — la sonde voyait donc « aucun
                    // attribut n'a suivi » sur un binding parfaitement
                    // sain, et le disait de TREIZE composants.
                    for (const f of [el, ...el.querySelectorAll(
                             'input, textarea, select')]) {
                        if (f === drivenInput) continue;
                        if (f.value !== undefined) {
                            parts.push(f.tagName + ':.value=' + f.value);
                        }
                        if (f.checked !== undefined) {
                            parts.push(f.tagName + ':.checked=' + f.checked);
                        }
                    }
                    // Text content too : ``x-text="..."`` bindings
                    // write to ``textContent`` (no attribute
                    // mutation), so label / content changes would
                    // not surface in an attribute-only signature.
                    parts.push('TEXT::' + el.textContent);
                }
                targets.forEach((t, i) => {
                    parts.push('#' + i);
                    record(t);
                });
                const demo = targets[targets.length - 1];
                // Teleported overlay panels (tooltip / popover /
                // dropdown content) live as ``<body>``'s direct
                // children after Alpine boots — the SSR ``<template
                // x-teleport>`` is moved out of the demo subtree at
                // init. Without including them in the signature, a
                // client-bound tooltip ``text`` change registers no
                // observable mutation under the trigger and the
                // probe wrongly reports the binding as dead.
                //
                // Templates may sit OUTSIDE the demo selector (for
                // tooltip the spec selector is ``... > button``
                // while the template is a sibling), so we also scan
                // the demo's immediate wrapper.
                const teleportRoots = [demo, demo.parentElement]
                    .filter(Boolean);
                const templates = new Set();
                for (const root of teleportRoots) {
                    for (const tpl of root.querySelectorAll(
                        'template[bz-teleport]'
                    )) templates.add(tpl);
                }
                for (const tpl of templates) {
                    const target = tpl.getAttribute('bz-teleport') || '';
                    let host = null;
                    try { host = document.querySelector(target); } catch (e) {}
                    if (!host) continue;
                    // The teleported subtree carries an
                    // ``x-bz-teleport-src`` marker we can grep, but
                    // an unmarked panel only exposes Alpine's
                    // ``_x_teleportBack`` internals. Best-effort :
                    // record every direct child of the teleport
                    // target ; cheap and inclusive.
                    for (const child of host.children) {
                        // Skip the demo itself (rare loopback).
                        if (demo.contains(child)) continue;
                        record(child);
                    }
                }
                return parts.join('|');
            }""",
            {
                "rootSel": component_root_selector,
                "ctrlSel": CONTROL_HOSTS,
                "drivenName": driven_name,
            },
        )

    findings: list[str] = []
    for ctl in controls:
        # Determine target value : flip toggles, type a sentinel for
        # text fields, pick a non-current candidate for selects.
        if ctl.kind in ("switch", "checkbox"):
            target = "on" if ctl.current_value != "on" else "off"
        elif ctl.candidates:
            target = next(
                (v for v in ctl.candidates if v != ctl.current_value),
                ctl.candidates[0],
            )
        else:
            a, b = _type_appropriate_sentinels(ctl)
            target = a if ctl.current_value != a else b
        before = _snapshot(ctl.name)
        if not _flip_control(page, ctl, target, wait_ms=500):
            continue
        after = _snapshot(ctl.name)
        if before is None or after is None:
            findings.append(
                f"client control {ctl.name!r} ({ctl.kind}) : preview "
                f"({component_root_selector!r}) not found in Client "
                f"playground card"
            )
            continue
        if before == after:
            findings.append(
                f"client control {ctl.name!r} ({ctl.kind}) changed to "
                f"{target!r} but NO attribute under "
                f"{component_root_selector!r} changed within the card — "
                f"binding never reached the carrier"
            )
        # Restore for next iteration so each control sees a known start.
        _flip_control(page, ctl, ctl.current_value or "off", wait_ms=300)
    if not findings:
        return ProbeResult(
            True, "client_switches_drive_carrier",
            f"all {len(controls)} client control(s) propagate to the "
            f"component subtree",
        )
    return ProbeResult(
        False, "client_switches_drive_carrier",
        f"{len(findings)} client control(s) changed but no DOM "
        f"attribute followed :\n" + "\n".join(findings),
    )


__all__ = [
    "PlaygroundControl",
    "probe_client_binding_lands_on_carrier",
    "probe_server_props_drive_dom",
    "probe_client_switches_drive_carrier",
    "_SERVER_PROP_DOM_AFFECTING",
    "_SERVER_PROP_DOM_IRRELEVANT",
]

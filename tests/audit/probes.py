"""Reusable Playwright probes — the building blocks of the audit.

Each probe is a callable ``(page, **kwargs) -> ProbeResult``. A
:class:`ProbeResult` is ``(passed: bool, name: str, detail: str)`` —
the truthy / falsy semantic matches pytest's assert style for easy
test wrapping.

Probes are intentionally minimal. They check ONE thing each ; the
caller composes them into a checklist (cf. :mod:`tests.audit.checklist`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from playwright.sync_api import Page


@dataclass(frozen=True)
class ProbeResult:
    passed: bool
    name: str
    detail: str = ""

    def __bool__(self) -> bool:
        return self.passed


# ─────────────────────────────────────────────────────────────────
# Visual — getComputedStyle distinctness
# ─────────────────────────────────────────────────────────────────


def probe_color_distinctness(
    page: Page,
    *,
    selector: str,
    expected_count: int = 7,
    inner_role: str | None = "button",
) -> ProbeResult:
    """Assert that ``expected_count`` distinct color variants of a
    component produce ``expected_count`` distinct computed styles.

    Anchors on the Reference card's ``color (...)`` heading (per
    playground-pattern convention) and reads the first N components
    that come after it. ``selector`` is matched RELATIVE to the
    container that follows the heading — so loose selectors like
    ``button`` work without picking up unrelated buttons elsewhere
    on the page.

    Samples ``borderColor`` + ``backgroundColor`` + ``color`` from
    ``getComputedStyle``. If two colors collapse to the same triple,
    the theme uses ``{color}`` only on transient states — cf.
    ``traps.md`` § "Theme utilise ``{bg_color}`` UNIQUEMENT sur états
    transitoires".
    """
    js = """
    (args) => {
        // Find the "color" h3. Match loosely : "color (7 paliers)",
        // "Colors (when selected)", etc.
        const h3s = document.querySelectorAll('h3');
        let anchor = null;
        for (const h of h3s) {
            const t = (h.textContent || '').toLowerCase();
            if (t.startsWith('color')) { anchor = h; break; }
        }
        if (!anchor) return {error: 'no color h3 anchor'};

        // Walk siblings AGGREGATING matches until we have
        // ``expected_count`` swatches OR we hit the NEXT h3 (which
        // means we crossed into a different section). This handles
        // the case where the playground renders N separate components
        // as N sibling divs (one per color) — flat sibling layout
        // — instead of grouping them in one wrapper.
        const samples = [];
        let cur = anchor.nextElementSibling;
        let walked = 0;
        const maxWalk = args.count * 2 + 4;  // safety bound
        while (cur && walked < maxWalk && samples.length < args.count) {
            // Stop at the next h3 (section boundary).
            if (cur.tagName === 'H3') break;
            const els = cur.querySelectorAll(args.selector);
            for (const el of els) {
                if (samples.length >= args.count) break;
                const target = args.role
                    ? (el.matches('[role="' + args.role + '"]')
                       ? el
                       : (el.querySelector('[role="' + args.role + '"]') || el))
                    : el;
                const cs = getComputedStyle(target);
                samples.push(
                    cs.borderColor + '|' + cs.backgroundColor + '|' + cs.color,
                );
            }
            cur = cur.nextElementSibling;
            walked += 1;
        }
        if (samples.length === 0) {
            // ⚠️ Distinguer « la section est vide » de « l'ancre est
            // MORTE » : les deux rendaient le même message, et le second
            // envoie chercher un défaut de couleur là où c'est le
            // sélecteur qui ne désigne plus rien. Mesuré deux fois — la
            // migration des rayons (``rounded-md``/``rounded-xl``) puis le
            // retrait de l'ombre au repos de la carte (``shadow-sm``), à
            // chaque fois une classe DÉCORATIVE nommée dans une ancre.
            if (document.querySelectorAll(args.selector).length === 0) {
                return {error: "ANCRE MORTE : `" + args.selector
                        + "` ne designe plus rien sur cette page. "
                        + "Ce nest pas un defaut de color : repare "
                        + "le root_selector dans "
                        + "tests/audit/checklist.py, et ny nomme que "
                        + "des classes STRUCTURELLES."};
            }
            return {error: 'no swatches after color heading'};
        }
        return {samples: samples};
    }
    """
    result = page.evaluate(js, {
        "selector": selector,
        "count": expected_count,
        "role": inner_role,
    })
    if "error" in result:
        return ProbeResult(
            False, "color_distinctness",
            f"{result['error']} for selector={selector!r}",
        )
    samples = result["samples"]
    if len(samples) < expected_count:
        return ProbeResult(
            False, "color_distinctness",
            f"only {len(samples)}/{expected_count} swatches found "
            f"(selector={selector!r} in color-heading container)",
        )
    distinct = len(set(samples))
    if distinct != expected_count:
        return ProbeResult(
            False, "color_distinctness",
            f"{distinct}/{expected_count} distinct computed styles "
            f"(theme likely tints only on transient states ; cf. "
            f"traps.md). First 3 samples : {samples[:3]}",
        )
    return ProbeResult(
        True, "color_distinctness",
        f"{expected_count} distinct computed styles ✓",
    )


def probe_size_distinctness(
    page: Page,
    *,
    selector: str,
    expected_count: int = 5,
    inner_role: str | None = "button",
) -> ProbeResult:
    """Same idea as :func:`probe_color_distinctness` but samples size
    paliers (xs/sm/md/lg/xl). Anchors on the Reference card's
    ``size (...)`` heading.

    Inspects ``padding`` + ``height`` + ``fontSize`` — the axes a
    size palier should shift.
    """
    js = """
    (args) => {
        const h3s = document.querySelectorAll('h3');
        let anchor = null;
        for (const h of h3s) {
            const t = (h.textContent || '').toLowerCase();
            if (t.startsWith('size')) { anchor = h; break; }
        }
        if (!anchor) return {error: 'no size h3 anchor'};

        // Aggregate across siblings, stopping at the next h3
        // (section boundary). Mirror of probe_color_distinctness so
        // flat-sibling playground layouts (each size as a separate
        // div) work.
        const samples = [];
        let cur = anchor.nextElementSibling;
        let walked = 0;
        const maxWalk = args.count * 2 + 4;
        while (cur && walked < maxWalk && samples.length < args.count) {
            if (cur.tagName === 'H3') break;
            const els = cur.querySelectorAll(args.selector);
            for (const el of els) {
                if (samples.length >= args.count) break;
                const target = args.role
                    ? (el.matches('[role="' + args.role + '"]')
                       ? el
                       : (el.querySelector('[role="' + args.role + '"]') || el))
                    : el;
                const cs = getComputedStyle(target);
                samples.push(cs.padding + '|' + cs.height + '|' + cs.fontSize);
            }
            cur = cur.nextElementSibling;
            walked += 1;
        }
        if (samples.length === 0) {
            // ⚠️ Distinguer « la section est vide » de « l'ancre est
            // MORTE » : les deux rendaient le même message, et le second
            // envoie chercher un défaut de couleur là où c'est le
            // sélecteur qui ne désigne plus rien. Mesuré deux fois — la
            // migration des rayons (``rounded-md``/``rounded-xl``) puis le
            // retrait de l'ombre au repos de la carte (``shadow-sm``), à
            // chaque fois une classe DÉCORATIVE nommée dans une ancre.
            if (document.querySelectorAll(args.selector).length === 0) {
                return {error: "ANCRE MORTE : `" + args.selector
                        + "` ne designe plus rien sur cette page. "
                        + "Ce nest pas un defaut de size : repare "
                        + "le root_selector dans "
                        + "tests/audit/checklist.py, et ny nomme que "
                        + "des classes STRUCTURELLES."};
            }
            return {error: 'no swatches after size heading'};
        }
        return {samples: samples};
    }
    """
    result = page.evaluate(js, {
        "selector": selector,
        "count": expected_count,
        "role": inner_role,
    })
    if "error" in result:
        return ProbeResult(
            False, "size_distinctness",
            f"{result['error']} for selector={selector!r}",
        )
    samples = result["samples"]
    if len(samples) < expected_count:
        return ProbeResult(
            False, "size_distinctness",
            f"only {len(samples)}/{expected_count} swatches found",
        )
    distinct = len(set(samples))
    if distinct < expected_count:
        return ProbeResult(
            False, "size_distinctness",
            f"{distinct}/{expected_count} distinct sizes — the size= "
            f"prop is partially or fully API noise. Samples : "
            f"{samples[:5]}",
        )
    return ProbeResult(
        True, "size_distinctness",
        f"{expected_count} distinct sizes ✓",
    )


# ─────────────────────────────────────────────────────────────────
# A11y — tab order
# ─────────────────────────────────────────────────────────────────


def probe_tab_order(
    page: Page,
    *,
    component_selector: str,
    max_stops_in_component: int = 3,
) -> ProbeResult:
    """Tab into the component and verify the focus host is correct.

    Catches the classic ``sr-only`` trap : a ``<input class="sr-only">``
    that should NOT be in the tab order but is, producing a phantom
    Tab stop with a scroll jolt. Cf. ``traps.md`` § "``sr-only`` ne
    retire PAS un élément du tab order".

    Walks Tab from inside the component, records each focused element's
    tag + visible flag, and asserts the sequence makes sense.
    """
    # First focus the component's wrapper to reset the cursor.
    page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (el) el.focus();
        }""",
        component_selector,
    )

    visited: list[dict] = []
    for _ in range(max_stops_in_component + 2):
        info = page.evaluate(
            """() => {
                const el = document.activeElement;
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    cls: (el.className && el.className.toString
                          ? el.className.toString().slice(0, 60) : ''),
                    visibleH: rect.height,
                    visibleW: rect.width,
                };
            }"""
        )
        visited.append(info)
        page.keyboard.press("Tab")

    # Flag stops on sr-only elements (visible height/width near 0).
    # EXCEPTION : checkbox / switch / radio canonically render a real
    # ``<input type="checkbox|radio">`` as ``sr-only`` AND keep it
    # focusable — the visible ``<label>`` provides the click area, the
    # input is the keyboard interaction surface. That's the standard
    # HTML pattern. We only flag sr-only Tab stops that are NOT on
    # such inputs.
    sr_only_stops = [
        v for v in visited
        if v and (v["visibleH"] < 5 or v["visibleW"] < 5)
        and "sr-only" in v["cls"]
        and v["tag"] != "input"
    ]
    if sr_only_stops:
        return ProbeResult(
            False, "tab_order",
            f"Tab stops on sr-only non-input elements (should be "
            f"tabindex=-1) : {sr_only_stops}",
        )
    return ProbeResult(True, "tab_order", "no phantom sr-only Tab stops ✓")


# ─────────────────────────────────────────────────────────────────
# Layout — scrollbar artefacts
# ─────────────────────────────────────────────────────────────────


def probe_no_body_overflow(page: Page) -> ProbeResult:
    """Detect parasite body / html scrollbars.

    The intended scrollbar on a Bretzel playground page is the right
    pane's ``overflow-y-auto``. If body or html ALSO overflow, the
    browser surfaces a second scrollbar — the classic shell layout
    bug fixed via ``fixed inset-0`` instead of ``h-screen``.
    Cf. ``traps.md`` § "Shell layout ``h-screen`` produit un double
    scrollbar viewport".
    """
    report = page.evaluate("""() => ({
        bodyOverflow: document.body.scrollHeight - document.body.clientHeight,
        htmlOverflow: document.documentElement.scrollHeight -
                      document.documentElement.clientHeight,
    })""")
    if report["bodyOverflow"] > 1:
        return ProbeResult(
            False, "no_body_overflow",
            f"body overflows by {report['bodyOverflow']}px → "
            f"double scrollbar viewport",
        )
    if report["htmlOverflow"] > 1:
        return ProbeResult(
            False, "no_body_overflow",
            f"html overflows by {report['htmlOverflow']}px → "
            f"viewport scrollbar in addition to the right pane's",
        )
    return ProbeResult(True, "no_body_overflow", "no parasite scrollbar ✓")


def probe_no_runaway_requests(page: Page, *, limit: int = 3) -> ProbeResult:
    """Detect a resource the page asks for over and over.

    The sixth minimal probe, added 2026-08-14 — and the only one that
    looks at the NETWORK. The five above read the DOM and the pixels, so
    none of them could see the bug that motivated it : ``ui.image`` and
    ``ui.video`` emitted ``src=""`` when given no source, an empty
    attribute resolves against the document URL, and the browser
    re-downloaded **the page itself** once per element. Nothing broke on
    screen ; it only showed up in uvicorn's log, where the user found it.

    The oracle is deliberately *repetition*, not a total : a page
    legitimately loads htmx, idiomorph, iconify, the runtime and its own
    document. What is never legitimate is the same URL fetched again and
    again — that is a loop, a retry storm, or an attribute pointing at
    something it shouldn't.

    Reloads the page to observe a full load from a clean slate, so it
    must run before any probe that mutates the DOM.
    """
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url))
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(800)

    tally: dict[str, int] = {}
    for url in seen:
        tally[url] = tally.get(url, 0) + 1
    if not tally:
        return ProbeResult(
            False, "no_runaway_requests",
            "aucune requête observée — le listener n'a rien capté, donc "
            "cette sonde ne vérifie rien (page déjà chargée ?)",
        )

    worst_url, worst_count = max(tally.items(), key=lambda kv: kv[1])
    if worst_count > limit:
        return ProbeResult(
            False, "no_runaway_requests",
            f"{worst_url.rsplit('/', 1)[-1] or worst_url} demandé "
            f"{worst_count}× sur un seul chargement (seuil {limit}) — "
            f"{len(seen)} requêtes au total. Une ressource répétée est une "
            f"boucle ou un attribut vide résolu contre l'URL du document.",
        )
    return ProbeResult(
        True, "no_runaway_requests",
        f"{len(seen)} requêtes, max {worst_count}× la même ✓",
    )


def probe_no_clip(
    page: Page, *, selector: str,
) -> ProbeResult:
    """Detect that absolutely-positioned children of the component
    aren't clipped by an ancestor's ``overflow-hidden``.

    Walks elements that have ``position: absolute`` AND negative
    top/left/right/bottom (i.e. floating outside their parent corner)
    and checks that ``getBoundingClientRect`` is non-zero — if zero,
    the element is rendered but clipped to invisibility. Cf.
    ``traps.md`` § "Bouton positionné ``-top-X -right-X`` clipé par
    ``overflow-hidden``".

    ⚠️ **Seuls les éléments AFFICHÉS sont jugés.** « Rendu puis clipé »
    n'a pas de sens pour un nœud que le CSS cache déjà : un panneau
    d'overlay fermé garde ses enfants dans le DOM, à des coordonnées qui
    n'ont pas encore été calculées, et la moitié d'entre eux tombent
    « hors » du premier conteneur défilant venu. Sans ce filtre la sonde
    accusait quatre composants d'un même nœud sain — la flèche d'un
    tooltip fermé.
    """
    suspects = page.evaluate("""(sel) => {
        const host = document.querySelector(sel);
        if (!host) return [];
        const out = [];
        for (const el of host.querySelectorAll('*')) {
            const cs = getComputedStyle(el);
            if (cs.position !== 'absolute') continue;
            // Un element qui n'est PAS AFFICHE ne peut pas etre « rendu
            // puis clipe jusqu'a l'invisibilite » : il est deja invisible,
            // et par dessein. Mesure du 2026-08-28 sur ``/flex`` : la
            // fleche d'un tooltip FERME (``visibility:hidden``,
            // ``opacity:0``) trainait a (-5.6, -5.6) — ses coordonnees
            // d'avant positionnement, floating-ui ne place le panneau qu'a
            // l'ouverture — et tombait donc « hors » du conteneur
            // defilant le plus proche. Quatre composants rouges pour un
            // seul noeud, parfaitement sain.
            if (el.checkVisibility &&
                !el.checkVisibility({
                    checkOpacity: true, checkVisibilityCSS: true,
                })) continue;
            const negTop = cs.top.startsWith('-');
            const negRight = cs.right.startsWith('-');
            const negBottom = cs.bottom.startsWith('-');
            const negLeft = cs.left.startsWith('-');
            if (!(negTop || negRight || negBottom || negLeft)) continue;
            const r = el.getBoundingClientRect();
            // Walk ancestors looking for overflow-hidden that might clip.
            let parent = el.parentElement, clipping = false;
            while (parent) {
                const pcs = getComputedStyle(parent);
                if (pcs.overflow === 'hidden' ||
                    pcs.overflowX === 'hidden' ||
                    pcs.overflowY === 'hidden') {
                    const pr = parent.getBoundingClientRect();
                    if (r.top < pr.top || r.right > pr.right ||
                        r.bottom > pr.bottom || r.left < pr.left) {
                        clipping = true;
                        break;
                    }
                }
                parent = parent.parentElement;
            }
            if (clipping) {
                out.push({
                    tag: el.tagName.toLowerCase(),
                    cls: el.className.toString().slice(0, 60),
                    top: cs.top, right: cs.right,
                });
            }
        }
        return out;
    }""", selector)
    if suspects:
        return ProbeResult(
            False, "no_clip",
            f"{len(suspects)} elements with negative position clipped "
            f"by ancestor overflow-hidden : {suspects[:3]}",
        )
    return ProbeResult(True, "no_clip", "no absolute children clipped ✓")


# ─────────────────────────────────────────────────────────────────
# Interaction — click / type / keyboard
# ─────────────────────────────────────────────────────────────────


def probe_click_opens(
    page: Page, *,
    trigger_selector: str,
    panel_selector: str,
    wait_ms: int = 400,
) -> ProbeResult:
    """Click ``trigger_selector`` and assert ``panel_selector`` becomes
    visible. Used for popovers / dropdowns / dialogs / drawers.
    """
    before = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            return getComputedStyle(el).display;
        }""",
        panel_selector,
    )
    page.locator(trigger_selector).first.click()
    page.wait_for_timeout(wait_ms)
    after = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            return getComputedStyle(el).display;
        }""",
        panel_selector,
    )
    if before == "none" and after != "none":
        return ProbeResult(
            True, "click_opens",
            f"click → display: {before} → {after} ✓",
        )
    return ProbeResult(
        False, "click_opens",
        f"click did not open : display {before} → {after}",
    )


def probe_type_updates_model(
    page: Page, *,
    input_selector: str,
    value: str,
    state_path_selector: str | None = None,
    wait_ms: int = 200,
) -> ProbeResult:
    """Type ``value`` into the input and assert Alpine ``x-model`` (or
    the equivalent) pushed it into reactive state. Confirms the
    ClientBinding two-way sync isn't broken.

    ``state_path_selector`` should be a CSS selector for a reactive
    element that echoes the value (e.g. ``[x-text="$bz.state.X.y"]``).
    If absent, only the input's own ``el.value`` is checked.
    """
    page.locator(input_selector).first.fill(value)
    page.wait_for_timeout(wait_ms)
    actual = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            return el ? el.value : null;
        }""",
        input_selector,
    )
    if actual != value:
        return ProbeResult(
            False, "type_updates_model",
            f"typed {value!r} but input.value = {actual!r}",
        )
    if state_path_selector:
        echoed = page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                return el ? el.textContent : null;
            }""",
            state_path_selector,
        )
        if echoed != value:
            return ProbeResult(
                False, "type_updates_model",
                f"typed {value!r} but reactive echo = {echoed!r} "
                f"— x-model push to state didn't propagate",
            )
    return ProbeResult(True, "type_updates_model", "ok ✓")


# ─────────────────────────────────────────────────────────────────
# State machinery — refreshable + htmx
# ─────────────────────────────────────────────────────────────────


def probe_refreshable_swap(
    page: Page, *,
    control_selector: str,
    new_value: str,
    target_selector: str,
    target_attribute: str,
    expected_pattern: str,
    wait_ms: int = 1200,
) -> ProbeResult:
    """Drive a refreshable round-trip via a control then assert the
    target attribute reflects the new state.

    Use case : Server playground select changes ``variant=button`` →
    the preview's wrapper class flips from ``border-dashed`` (dropzone)
    to ``inline-flex`` (button). Verifies the full htmx + Bretzel
    refreshable + idiomorph morph chain end-to-end.

    Parameters :
        control_selector : a hidden ``<input name="X">`` of the
            Server playground (set via Alpine ``x-model``).
        new_value : value to write into the input.
        target_selector : the element to inspect after the round-trip.
        target_attribute : ``class`` or ``aria-label`` etc.
        expected_pattern : substring expected in ``target_attribute``.
    """
    page.evaluate(
        """async (args) => {
            const inp = document.querySelector(args.sel);
            if (!inp) return;
            inp.value = args.val;
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            inp.dispatchEvent(new Event('input', {bubbles: true}));
        }""",
        {"sel": control_selector, "val": new_value},
    )
    page.wait_for_timeout(wait_ms)
    actual = page.evaluate(
        """(args) => {
            const el = document.querySelector(args.sel);
            return el ? el.getAttribute(args.attr) : null;
        }""",
        {"sel": target_selector, "attr": target_attribute},
    )
    if actual is None:
        return ProbeResult(
            False, "refreshable_swap",
            f"target {target_selector!r} not found after refresh",
        )
    if expected_pattern not in actual:
        return ProbeResult(
            False, "refreshable_swap",
            f"after refresh, {target_attribute}={actual!r} did not "
            f"contain {expected_pattern!r}",
        )
    return ProbeResult(
        True, "refreshable_swap",
        f"refresh propagated : {expected_pattern!r} in attribute ✓",
    )


# ─────────────────────────────────────────────────────────────────
# Theme convention — uses {color} at REST
# ─────────────────────────────────────────────────────────────────


def probe_theme_color_at_rest(
    page: Page, *,
    selector: str, color: str = "primary",
) -> ProbeResult:
    """Verify the theme exposes the ``color=`` prop visually at rest
    (not just on focus / hover / drag). This is a class-string check
    that complements ``probe_color_distinctness`` : we look for at
    least one ``-primary`` / ``-success`` / etc. token in the
    component root's class string that is NOT inside a
    ``focus-visible:`` / ``hover:`` / ``group-hover:`` modifier.
    """
    classes = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            return el ? el.className.toString() : '';
        }""",
        selector,
    )
    # Walk through tokens — skip those prefixed with a state modifier.
    tokens = classes.split()
    rest_tokens = [
        t for t in tokens
        if not (
            t.startswith("hover:") or t.startswith("focus:")
            or t.startswith("focus-visible:") or t.startswith("group-hover:")
            or t.startswith("group-focus:") or t.startswith("active:")
            or t.startswith("disabled:")
        )
    ]
    color_at_rest = any(f"-{color}" in t for t in rest_tokens)
    if not color_at_rest:
        return ProbeResult(
            False, "theme_color_at_rest",
            f"no {color}-tinted class at rest (only on transient "
            f"states). Rest tokens : {rest_tokens[:8]}",
        )
    return ProbeResult(
        True, "theme_color_at_rest",
        f"theme uses {color} at rest ✓",
    )


# ─────────────────────────────────────────────────────────────────
# State machinery — refresh + Alpine + idiomorph interactions
# ─────────────────────────────────────────────────────────────────
#
# These probes catch the class of bugs the user keeps reporting that
# the visual probes miss : "client state not reactive", "events don't
# work after refresh", "switching variant breaks behaviour".
#
# Common root cause : ``x-data="$bz.X.makeScope({opts})"`` is init-
# once. Server refresh emits a new ``x-data`` attribute string with
# new opts, idiomorph swaps it, BUT Alpine does NOT re-execute the
# factory. The scope keeps the old closure-captured opts. Visually
# the wrapper's static classes change ; behaviourally the JS is
# stale.


def _drive_server_playground_change(
    page: Page, *, input_name: str, new_value: str, wait_ms: int = 1200,
) -> bool:
    """Common helper : write ``new_value`` into the Server playground's
    hidden ``<input name="X">`` and dispatch the ``change`` event the
    Bretzel form dispatcher expects. Returns True if the input exists
    and the dispatch went through, False otherwise."""
    result = page.evaluate(
        """async (args) => {
            const inp = document.querySelector(
                'input[name="' + args.name + '"]'
            );
            if (!inp) return false;
            inp.value = args.val;
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            await new Promise(r => setTimeout(r, args.wait));
            return true;
        }""",
        {"name": input_name, "val": new_value, "wait": wait_ms},
    )
    return bool(result)


def probe_variant_roundtrip_consistent(
    page: Page, *,
    preview_selector: str,
    variant_input_name: str,
    variants: tuple[str, str],
    behaviour_check: str | None = None,
) -> ProbeResult:
    """A → B → A round-trip preserves behaviour.

    Switches the Server playground's ``variant`` (or any prop with
    two values) from A → B → A and asserts the final state matches
    a fresh A render. Specifically :

    1. Snapshot the preview wrapper's ``x-data`` attribute under A.
    2. Switch to B, wait for refresh.
    3. Switch back to A, wait for refresh.
    4. Compare current ``x-data`` to the snapshot. They must match
       byte-for-byte (modulo opts ordering).
    5. If ``behaviour_check`` is provided, evaluate it as JS expression
       on the preview element ; must return truthy.

    Catches the trap where switching prop X out and back leaves
    Alpine's scope desynchronised from the HTML attribute (the
    ``x-data init-once`` issue surfaces here as scope state still
    holding the B-state opts even though the attribute says A).
    """
    a, b = variants

    snapshot = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            return el ? {
                xdata: el.getAttribute('bz-data') || '',
                outer: el.outerHTML.length,
            } : null;
        }""",
        preview_selector,
    )
    if snapshot is None:
        return ProbeResult(
            False, "variant_roundtrip",
            f"preview {preview_selector!r} not found",
        )

    if not _drive_server_playground_change(
        page, input_name=variant_input_name, new_value=b,
    ):
        return ProbeResult(
            False, "variant_roundtrip",
            f"server playground input {variant_input_name!r} not found",
        )
    if not _drive_server_playground_change(
        page, input_name=variant_input_name, new_value=a,
    ):
        return ProbeResult(
            False, "variant_roundtrip",
            f"second dispatch to {variant_input_name!r} failed",
        )

    final = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            return el ? {
                xdata: el.getAttribute('bz-data') || '',
                outer: el.outerHTML.length,
            } : null;
        }""",
        preview_selector,
    )
    if final is None:
        return ProbeResult(
            False, "variant_roundtrip",
            "preview disappeared after round-trip",
        )

    # Allow ``bz-version`` to differ but the x-data string MUST match.
    if final["xdata"] != snapshot["xdata"]:
        return ProbeResult(
            False, "variant_roundtrip",
            f"x-data drifted across {a}→{b}→{a} round-trip. Before : "
            f"{snapshot['xdata'][:120]}... After : {final['xdata'][:120]}...",
        )

    if behaviour_check:
        ok = page.evaluate(
            """(args) => {
                const el = document.querySelector(args.sel);
                if (!el) return false;
                try { return !!eval(args.expr); } catch(e) { return false; }
            }""",
            {"sel": preview_selector, "expr": behaviour_check},
        )
        if not ok:
            return ProbeResult(
                False, "variant_roundtrip",
                f"behaviour check failed after round-trip : "
                f"{behaviour_check!r}",
            )

    return ProbeResult(
        True, "variant_roundtrip",
        f"{a}→{b}→{a} round-trip preserves x-data ✓",
    )


def probe_client_binding_reactive(
    page: Page, *,
    state_class: str, state_field: str,
    bound_selector: str,
    value_under_test: str,
    read_attribute: str = "value",
    wait_ms: int = 250,
) -> ProbeResult:
    """Mutating ``$bz.state.<class>.default.<field>`` from JS triggers
    a visible DOM update.

    Catches dead-watcher bugs where the bound DOM is rendered correctly
    at SSR but doesn't react to subsequent state mutations (e.g.
    because Alpine's ``$watch`` was attached to a now-detached scope
    after a morph).

    The probe writes a sentinel value into the state, waits a tick,
    reads ``bound_selector.{read_attribute}`` (default ``value`` —
    Alpine's ``x-model`` writes there). For ``x-text``-bound elements,
    pass ``read_attribute="textContent"``.
    """
    js_path = f"$bz.state.{state_class}.default.{state_field}"
    result = page.evaluate(
        """async (args) => {
            // Set the state.
            const expr = 'window.' + args.path + ' = ' + JSON.stringify(args.val);
            try { eval(expr); } catch(e) { return {error: String(e)}; }
            // Let Alpine settle.
            await new Promise(r => setTimeout(r, args.wait));
            const el = document.querySelector(args.sel);
            if (!el) return {error: 'bound element not found'};
            const actual = args.attr === 'textContent'
                ? el.textContent
                : (args.attr === 'value' ? el.value : el.getAttribute(args.attr));
            return {value: actual};
        }""",
        {
            "path": js_path,
            "val": value_under_test,
            "wait": wait_ms,
            "sel": bound_selector,
            "attr": read_attribute,
        },
    )
    if "error" in result:
        return ProbeResult(
            False, "client_binding_reactive",
            f"setup failed : {result['error']}",
        )
    actual = result.get("value", "")
    # Reactive sync should give us the new value (possibly trimmed
    # for textContent which can carry whitespace).
    if str(actual).strip() != str(value_under_test).strip():
        return ProbeResult(
            False, "client_binding_reactive",
            f"mutated {js_path} = {value_under_test!r} but "
            f"{bound_selector}.{read_attribute} = {actual!r} "
            f"(reactivity broken — likely dead watcher after morph)",
        )
    return ProbeResult(
        True, "client_binding_reactive",
        f"state mutation propagates to {bound_selector} ✓",
    )


def probe_event_survives_refresh(
    page: Page, *,
    trigger_selector: str,
    expected_side_effect: str,
    side_effect_kind: str = "alpine_data",
    refreshable_input_name: str | None = None,
    refreshable_value: str | None = None,
    wait_ms: int = 800,
) -> ProbeResult:
    """Click handler still fires after an intervening server refresh.

    Steps :
        1. Click the trigger. Verify expected side effect happens.
        2. Trigger a server refresh on the Server playground (any prop
           change works — we just want the wrapper to morph).
        3. Click the trigger again. Verify side effect happens AGAIN.

    Side effect kinds :
        - ``alpine_data`` : ``expected_side_effect`` is a JS expression
          read against the trigger's enclosing Alpine scope. Should
          flip true.
        - ``dom_class`` : ``expected_side_effect`` is a class name
          that should be ADDED to a sibling element.
    """
    # Step 1 : initial click.
    page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (el) el.click();
        }""",
        trigger_selector,
    )
    page.wait_for_timeout(200)
    initial_ok = _check_side_effect(
        page, trigger_selector, expected_side_effect, side_effect_kind,
    )
    if not initial_ok:
        return ProbeResult(
            False, "event_survives_refresh",
            f"initial click failed — handler not wired at SSR. "
            f"trigger={trigger_selector} expected={expected_side_effect}",
        )

    # Step 2 : trigger a refresh.
    if refreshable_input_name and refreshable_value:
        if not _drive_server_playground_change(
            page, input_name=refreshable_input_name,
            new_value=refreshable_value, wait_ms=wait_ms,
        ):
            return ProbeResult(
                False, "event_survives_refresh",
                f"intermediate refresh failed (input "
                f"{refreshable_input_name!r} not found)",
            )
    else:
        return ProbeResult(
            False, "event_survives_refresh",
            "spec missing refreshable_input_name / refreshable_value",
        )

    # Step 3 : click again, verify still works.
    page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (el) el.click();
        }""",
        trigger_selector,
    )
    page.wait_for_timeout(200)
    final_ok = _check_side_effect(
        page, trigger_selector, expected_side_effect, side_effect_kind,
    )
    if not final_ok:
        return ProbeResult(
            False, "event_survives_refresh",
            f"click stopped working after server refresh — handler "
            f"binding killed by idiomorph + Alpine init-once. "
            f"trigger={trigger_selector}",
        )
    return ProbeResult(
        True, "event_survives_refresh",
        "click works before and after refresh ✓",
    )


def _check_side_effect(
    page: Page, trigger_sel: str, expected: str, kind: str,
) -> bool:
    if kind == "alpine_data":
        return bool(page.evaluate(
            """(args) => {
                const el = document.querySelector(args.sel);
                if (!el) return false;
                try {
                    const scope = window.Alpine && window.Alpine.$data(el);
                    if (!scope) return false;
                    return !!eval('scope.' + args.expr);
                } catch(e) { return false; }
            }""",
            {"sel": trigger_sel, "expr": expected},
        ))
    if kind == "dom_class":
        return bool(page.evaluate(
            """(args) => {
                const el = document.querySelector(args.sel);
                if (!el) return false;
                let p = el.parentElement;
                while (p) {
                    if (p.classList && p.classList.contains(args.cls))
                        return true;
                    p = p.parentElement;
                }
                return false;
            }""",
            {"sel": trigger_sel, "cls": expected},
        ))
    return False


def probe_xdata_attribute_reflects_refresh(
    page: Page, *,
    preview_selector: str,
    input_name: str,
    new_value: str,
    expected_substring_in_xdata: str,
    wait_ms: int = 1200,
) -> ProbeResult:
    """After a Server playground refresh, the preview wrapper's
    ``x-data`` attribute should contain ``expected_substring_in_xdata``.

    Confirms the SERVER side of the refresh works (the new HTML reaches
    the DOM). Pair with :func:`probe_variant_roundtrip_consistent` to
    catch the Alpine-scope-stale follow-up trap : attribute updates but
    JS scope doesn't.
    """
    if not _drive_server_playground_change(
        page, input_name=input_name, new_value=new_value, wait_ms=wait_ms,
    ):
        return ProbeResult(
            False, "xdata_reflects_refresh",
            f"input {input_name!r} not found",
        )
    xdata = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            return el ? (el.getAttribute('bz-data') || '') : null;
        }""",
        preview_selector,
    )
    if xdata is None:
        return ProbeResult(
            False, "xdata_reflects_refresh",
            f"preview {preview_selector!r} not found after refresh",
        )
    if expected_substring_in_xdata not in xdata:
        return ProbeResult(
            False, "xdata_reflects_refresh",
            f"after setting {input_name}={new_value!r}, expected "
            f"{expected_substring_in_xdata!r} in x-data, got : "
            f"{xdata[:200]}",
        )
    return ProbeResult(
        True, "xdata_reflects_refresh",
        f"x-data reflects {input_name}={new_value} ✓",
    )


__all__ = [
    "ProbeResult",
    "probe_color_distinctness",
    "probe_size_distinctness",
    "probe_tab_order",
    "probe_no_body_overflow",
    "probe_no_runaway_requests",
    "probe_no_clip",
    "probe_click_opens",
    "probe_type_updates_model",
    "probe_refreshable_swap",
    "probe_theme_color_at_rest",
    # State machinery
    "probe_variant_roundtrip_consistent",
    "probe_client_binding_reactive",
    "probe_event_survives_refresh",
    "probe_xdata_attribute_reflects_refresh",
]

"""Gate : every visual component is enrolled in the browser audit.

The browser audit (``tests/runtime_js/test_component_audit.py`` driving
``tests/audit/checklist.py``) is the only thing that catches the class of
bug SSR / ``TestClient`` cannot see — a CSS class that loses to a web
component's baked-in ``display``, a ``group-*`` selector that leaks across
a recursive tree, an icon whose font-size width doesn't match a fixed
spacer. All three shipped in ``ui.tree`` because enrollment in the audit
was **manual and unchecked** : the component had a route, a nav entry and
a ``ui.tree`` binding, but no ``ComponentSpec`` — so Chromium never ran on
it.

This gate closes that hole. It fails the moment a new ``ui.foo = Foo``
component exists without either an audit ``ComponentSpec`` or an explicit
:data:`EXEMPT` entry justifying why it has no standalone visual audit.
"Please remember to add a spec" becomes "the suite is red until you do".
"""

from __future__ import annotations

import re

from tests.audit.checklist import all_specs
from tests.consistency._discovery import public_component_names

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "compare deux ENSEMBLES (composants visuels / composants enrôlés dans l'audit) ; sa non-vacuité est gardée par `test_coverage_is_non_trivial`, pas par un motif"
)


def _snake(name: str) -> str:
    """``IconButton`` → ``icon_button`` (the ``ComponentSpec.name`` form)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


# Components on the ``ui`` namespace that legitimately have NO standalone
# browser audit. Each MUST carry a reason — a future maintainer re-reads
# this when the constraint lifts. A NEW primary component is deliberately
# NOT here, so it trips the gate until it is audited or explicitly exempted.
EXEMPT: dict[str, str] = {
    # ── Sub-components : exercised inside their parent's bench, no route ──
    "accordion_item": "rendered inside the /accordion bench",
    "breadcrumb_item": "rendered inside the /breadcrumb bench",
    "dropdown_item": "rendered inside the /dropdown bench",
    "bottom_bar_item": "rendered inside the /bottom-bar bench",
    "navbar_item": "rendered inside the /navbar bench",
    "navbar_section": "rendered inside the /navbar bench",
    "radio_group": "container audited via the /radio bench",
    "resizable_panel": "rendu dans le banc /resizable — et il ne rend "
                       "AUCUNE classe à lui : sa boîte est composée par "
                       "le groupe, donc l'auditer seul jugerait un div nu",
    "sidebar_footer": "rendered inside the /sidebar bench",
    "sidebar_footer_item": "rendered inside the /sidebar bench",
    "sidebar_item": "rendered inside the /sidebar bench",
    "sidebar_section": "rendered inside the /sidebar bench",
    "sidebar_title": "rendered inside the /sidebar bench",
    # Il rend un ``ui.icon_button`` et RIEN d'autre — pas une classe a
    # lui : l'auditer seul jugerait le bouton, qui a deja son banc. Ce
    # qui lui est propre n'est pas une apparence mais un COMPORTEMENT
    # (le clic ramene la barre a l'ecran), et ca se mesure en pixels :
    # tests/probes/probe_sidebar_trigger.py, x = -256 -> 0.
    "sidebar_trigger": "rend un ui.icon_button nu — son propre contrat "
                       "est un comportement, mesure par "
                       "tests/probes/probe_sidebar_trigger.py",
    "step": "rendered inside the /stepper bench",
    "step_panel": "rendered inside the /stepper bench",
    "tab": "rendered inside the /tabs bench",
    "tab_panel": "rendered inside the /tabs bench",
    "toggle_button": "rendered inside the /toggle_group bench",
    "tree_node": "rendered inside the /tree bench",
    # ── Layout shortcuts : HStack / VStack are Flex shortcuts ────────────
    "h_stack": "Flex shortcut — audited via the /stack bench",
    "v_stack": "Flex shortcut — audited via the /stack bench",
    # ── Les deux régions de l'écran gelé ────────────────────────────────
    # Aucune couleur, aucune taille, aucun chrome : ce qu'elles font est
    # un COMPORTEMENT de disposition, que l'audit visuel par composant ne
    # sait pas juger (il compare des captures d'un composant monté seul,
    # et un `fixed inset-0` monté seul est un rectangle vide). Elles sont
    # mesurées au navigateur, en pixels, par
    # `tests/runtime_js/test_a_frozen_screen_scrolls_only_its_panes.py`.
    "viewport": "disposition pure — mesuré en pixels par "
                "tests/runtime_js/test_a_frozen_screen_scrolls_only_its_panes.py",
    "pane": "disposition pure — mesuré en pixels par "
            "tests/runtime_js/test_a_frozen_screen_scrolls_only_its_panes.py",
    # ── Side-effect / structural : no visual surface to audit ────────────
    "fragment": "structural grouping — no rendered chrome",
    "interval": "side-effect polling marker — no visual",
    "outlet": "layout slot marker — no visual of its own",
    "title": "document <title> side-effect — audited via /meta",
    "meta_tag": "document <meta> side-effect — audited via /meta",
}


def test_every_visual_component_is_audited() -> None:
    components = {_snake(n) for n in public_component_names()}
    audited = {spec.name for spec in all_specs()}
    uncovered = sorted(components - audited - set(EXEMPT))
    assert not uncovered, (
        "These components are on the `ui` namespace but have NO browser "
        f"audit and are not exempt : {uncovered}.\n"
        "Either add a ComponentSpec to tests/audit/checklist.py (so "
        "`test_component_audit` runs Chromium on it — the only gate that "
        "catches SSR-invisible visual bugs), or add the name to EXEMPT in "
        "this file with a one-line reason. A new component must not ship "
        "un-audited (this is exactly how ui.tree shipped with two broken "
        "chevrons)."
    )


def test_exempt_entries_are_not_secretly_audited() -> None:
    # Hygiene : if an EXEMPT component later gets its own spec, drop it
    # from EXEMPT so the list doesn't rot into a stale rubber stamp.
    audited = {spec.name for spec in all_specs()}
    redundant = sorted(set(EXEMPT) & audited)
    assert not redundant, (
        f"These names are BOTH audited and in EXEMPT : {redundant}. "
        "Remove them from EXEMPT — they no longer need the exemption."
    )


def test_coverage_is_non_trivial() -> None:
    # A refactor that hid the component registry or the specs would make
    # the gate pass vacuously — pin a floor on both sides.
    assert len(public_component_names()) >= 50
    assert len({spec.name for spec in all_specs()}) >= 50

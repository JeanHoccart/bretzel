"""Gate : a disabled control exposes its disabled state — to assistive tech
AND to the pointer (the not-allowed cursor).

**Machine-readable (AT).** Native controls (``<button disabled>`` /
``<input disabled>``) announce themselves for free. Role-based /
``<div>``-based items (``role="treeitem"``, a link with a stripped ``href``,
a custom select trigger) do NOT — a screen reader sees a normal, focusable
element unless the render emits ``aria-disabled="true"``. The visual dim +
``tabindex=-1`` are invisible to AT. The tree shipped disabled nodes WITHOUT
``aria-disabled`` (fixed in ``716bd4a``).

**Cursor affordance.** A disabled control must also show ``cursor-not-allowed``
on hover — AND that cursor must actually render. The trap : putting
``pointer-events-none`` on the SAME element as ``cursor-not-allowed`` silently
CANCELS the cursor (an element that receives no pointer events never paints a
cursor), so the user sees the default arrow. The tree's disabled row shipped
exactly that combo (``pointer-events-none cursor-not-allowed`` together) — the
class was present but invisible. The standard is the Link pattern : keep
pointer events, neutralise hover by ``aria-disabled:`` specificity. This gate
locks BOTH invariants across every disable-able component so the next
role-based control can't regress either way.
"""

from __future__ import annotations

import re

import pytest

from bretzel import ui
from bretzel.components.base.testing import render_isolated
from bretzel.components.data.tree import Tree, TreeNode
from bretzel.core.serialize import serialize

# A native boolean ``disabled`` ATTRIBUTE : serialised bare (``disabled>``),
# empty (``disabled=""``), or LAST in a self-closing tag (``disabled/>``).
# The lookbehind rejects ``aria-disabled`` (preceded by ``-``) and the
# lookahead rejects the Tailwind ``disabled:`` variant (followed by ``:``),
# so only the real attribute matches.
#
# ⚠️ Le ``/`` de la classe de caractères a été ajouté le 2026-08-13, en
# soldant ``_UNAUDITED``. Sans lui, ``ui.radio(disabled=True)`` — dont
# l'``<input disabled/>`` n'a rien après l'attribut — était déclaré NON
# annoncé alors qu'il l'est parfaitement. ``checkbox`` et ``switch``
# passaient seulement parce qu'un ``id`` suit leur ``disabled``. Une gate
# qui accuse à tort coûte autant qu'une gate qui laisse passer : les deux
# fois, on corrige la mauvaise chose.
_NATIVE_DISABLED = re.compile(r'(?<![-\w])disabled(?=[\s/>=])')


def _disabled_resizable():
    # Deux panneaux minimum : la poignée — le seul élément que
    # ``disabled=`` concerne — est DÉRIVÉE, donc un groupe à un panneau
    # n'en rend aucune et le cas serait vide.
    with ui.resizable(disabled=True) as group:
        with ui.resizable_panel():
            ui.text("a")
        with ui.resizable_panel():
            ui.text("b")
    return group.render()


def _tree_with_disabled_node():
    with Tree() as t:
        TreeNode("a", label="Enabled")
        TreeNode("b", label="Disabled", disabled=True)
    return t.render()


# ── Les sous-composants : un état disabled n'existe QUE dans son parent ──
# C'est la raison pour laquelle ``_CASES`` est écrite à la main plutôt que
# dérivée : aucune introspection ne devine qu'un ``ui.step`` doit naître
# dans un ``ui.stepper`` pour rendre autre chose qu'un ``<span>`` inerte.


def _accordion_with_disabled_item():
    with ui.accordion() as a:
        ui.accordion_item("v1", label="Open")
        ui.accordion_item("v2", label="Locked", disabled=True)
    return a.render()


def _stepper_with_disabled_step(clickable: bool = True):
    with ui.stepper(clickable=clickable) as s:
        ui.step("One")
        ui.step("Locked", disabled=True)
    return s.render()


def _stepper_indicator_with_disabled_step():
    """⚠️ Le mode NON cliquable est un cas à part entière, pas un doublon.

    En cliquable, la pastille est un ``<button disabled>`` : l'invariant
    « machine-readable » est satisfait par l'attribut NATIF, donc ce cas
    ne prouve rien sur l'``aria-disabled`` que le composant émet. Mesuré
    en mutation-testant : retirer cet ``aria-disabled`` laissait la gate
    VERTE tant que seul le mode cliquable était couvert.

    En indicateur, la pastille est un ``<span>`` — aucun filet natif,
    donc c'est ce cas, et lui seul, qui garde le fix du 2026-08-13.
    """
    return _stepper_with_disabled_step(clickable=False)


def _tabs_with_disabled_tab():
    with ui.tabs() as t:
        ui.tab("a", label="One")
        ui.tab("b", label="Locked", disabled=True)
    return t.render()


def _toggle_group_with_disabled_button():
    with ui.toggle_group() as g:
        ui.toggle_button("a", label="One")
        ui.toggle_button("b", label="Locked", disabled=True)
    return g.render()


def _sidebar_with_disabled_footer_item():
    with ui.sidebar() as s, ui.sidebar_footer(name="Jean"):
        ui.sidebar_footer_item(label="Locked", href="/x", disabled=True)
    return s.render()


# A single element carrying BOTH ``pointer-events-none`` and
# ``cursor-not-allowed`` : the cursor never paints (no pointer events → no
# cursor). The exact tree bug. We scan per class-attribute so a decorative
# child with ``pointer-events-none`` (but no cursor) stays legal.
_CLASS_ATTR = re.compile(r'class="([^"]*)"')


# (label, factory) — each renders the component in its DISABLED state.
# A new disable-able component joins this table.
_CASES = [
    ("tree", _tree_with_disabled_node),
    ("link", lambda: ui.link("x", href="/y", disabled=True).render()),
    ("select", lambda: ui.select(["a", "b"], disabled=True).render()),
    ("combobox", lambda: ui.combobox(["a", "b"], disabled=True).render()),
    ("slider", lambda: ui.slider(disabled=True).render()),
    ("calendar", lambda: ui.calendar(disabled=True).render()),
    ("file_upload", lambda: ui.file_upload(disabled=True).render()),
    ("button", lambda: ui.button("x", disabled=True).render()),
    ("icon_button", lambda: ui.icon_button("x", disabled=True).render()),
    ("checkbox", lambda: ui.checkbox(disabled=True).render()),
    ("switch", lambda: ui.switch(disabled=True).render()),
    ("input", lambda: ui.input(disabled=True).render()),
    ("textarea", lambda: ui.textarea(disabled=True).render()),
    ("number_input", lambda: ui.number_input(disabled=True).render()),
    ("draggable", lambda: ui.draggable(key="k", disabled=True).render()),
    ("resizable", _disabled_resizable),
    ("signature_pad", lambda: ui.signature_pad(disabled=True).render()),
    # Les trois items de nav, sortis de ``_UNAUDITED`` le 2026-08-13. Ils
    # portaient bien le défaut que la dette annonçait comme possible :
    # ``cursor-not-allowed`` et ``pointer-events-none`` sur la MÊME chaîne
    # de classes, donc un curseur qui ne peut pas peindre. ``href=`` est
    # passé exprès — c'est le cas où l'inertie compte vraiment.
    ("navbar_item", lambda: ui.navbar_item("x", href="/y", disabled=True).render()),
    ("sidebar_item", lambda: ui.sidebar_item("x", href="/y", disabled=True).render()),
    (
        "bottom_bar_item",
        lambda: ui.bottom_bar_item("x", href="/y", disabled=True).render(),
    ),
    # ── Les 14 derniers de ``_UNAUDITED``, soldés le 2026-08-13 ────────
    # Deux défauts sur quatorze, et aucun des deux n'était celui qu'on
    # cherchait (cf. le commentaire de ``_UNAUDITED``, désormais vide).
    ("accordion_item", _accordion_with_disabled_item),
    ("step", _stepper_with_disabled_step),
    ("step_indicator", _stepper_indicator_with_disabled_step),
    ("tab", _tabs_with_disabled_tab),
    ("tree_node", _tree_with_disabled_node),
    ("toggle_button", _toggle_group_with_disabled_button),
    ("sidebar_footer_item", _sidebar_with_disabled_footer_item),
    (
        "dropdown_item",
        lambda: ui.dropdown_item(label="x", href="/y", disabled=True).render(),
    ),
    ("radio", lambda: ui.radio(value="a", label="x", disabled=True).render()),
    ("pagination", lambda: ui.pagination(total_pages=3, disabled=True).render()),
    ("date_picker", lambda: ui.date_picker(disabled=True).render()),
    (
        "date_range_picker",
        lambda: ui.date_range_picker(disabled=True).render(),
    ),
    ("month_picker", lambda: ui.month_picker(disabled=True).render()),
    ("week_picker", lambda: ui.week_picker(disabled=True).render()),
    ("time_picker", lambda: ui.time_picker(disabled=True).render()),
    ("color_picker", lambda: ui.color_picker(disabled=True).render()),
]

# ── Complétude : la liste ci-dessus est ÉCRITE À LA MAIN ──────────────
# C'est son angle mort, et il a mordu : ``ui.draggable`` a shippé le
# 2026-08-10 avec un ``disabled=`` sans ``aria-disabled`` ET avec le
# combo ``pointer-events-none`` + curseur que cette gate documente — en
# restant verte, parce que personne ne l'avait ajouté à ``_CASES``.
# On ne remplace pas la liste (chaque entrée porte la façon de construire
# un cas disabled, que l'introspection ne devine pas) : on garde qu'aucun
# composant acceptant ``disabled=`` n'en soit absent.
_COVERED = {label for label, _ in _CASES}

#: Composants qui acceptent ``disabled=`` sans être des contrôles au sens
#: de cette gate. Chacun porte sa raison.
_NOT_A_CONTROL: dict[str, str] = {
    "radio_group": "délègue à ses ``radio``, qui sont couverts",
    "toggle_group": "délègue à ses ``toggle_button``",
    "form": "propage à ses champs, ne rend aucun contrôle propre",
}

#: ✅ **VIDE depuis le 2026-08-13.** C'était la dette ouverte le
#: 2026-08-10 : 17 composants qui acceptaient ``disabled=`` sans avoir
#: jamais été confrontés aux deux invariants. Tous soldés, en deux
#: passes, et le bilan mérite d'être gardé parce qu'il contredit ce qu'on
#: en attendait.
#:
#: **Passe 1 (3 composants)** — les items de nav : les trois portaient le
#: défaut annoncé, le combo curseur / ``pointer-events-none``.
#: **Passe 2 (14 composants)** — DEUX défauts seulement, et aucun des
#: deux n'était celui qu'on cherchait :
#:
#: - ``radio`` était **conforme**, et c'est la GATE qui l'accusait à
#:   tort : son ``<input disabled/>`` n'a rien après l'attribut, et le
#:   lookahead ne connaissait pas le ``/``. ``checkbox`` et ``switch``
#:   n'échappaient au faux positif que parce qu'un ``id`` suit le leur ;
#: - ``step`` avait un vrai trou, mais dans le mode NON cliquable
#:   seulement : sa pastille est un ``<span>``, où ``:disabled`` ne
#:   matche jamais, donc ``disabled=True`` n'y ternissait rien et
#:   n'annonçait rien. Corrigé en ``aria-disabled``.
#:
#: La leçon, pour la prochaine dette datée : après trois défauts sur
#: trois, on prédisait « ~14 suspects ». Le taux réel est **2 sur 14**,
#: dont un imputable à l'instrument. Un aveu daté dit « personne n'a
#: vérifié », pas « c'est probablement cassé » — et extrapoler un petit
#: échantillon coûte, dans les deux sens.
#:
#: ⚠️ La liste ne peut que rétrécir : on n'y ajoute pas une entrée, on
#: écrit son cas dans ``_CASES``. ``test_the_unaudited_list_only_shrinks``
#: le tient.
_UNAUDITED: frozenset[str] = frozenset()


def _accepts_disabled(name: str) -> bool:
    import inspect

    component = getattr(ui, name, None)
    if not isinstance(component, type):
        return False
    try:
        return "disabled" in inspect.signature(component.__init__).parameters
    except (TypeError, ValueError):
        return False


def test_no_disable_able_component_is_missing_from_the_cases() -> None:
    from bretzel.components.base import Component

    public = [
        name for name in dir(ui)
        if not name.startswith("_")
        and isinstance(getattr(ui, name, None), type)
        and issubclass(getattr(ui, name), Component)
    ]
    missing = sorted(
        name for name in public
        if _accepts_disabled(name)
        and name not in _COVERED
        and name not in _NOT_A_CONTROL
        and name not in _UNAUDITED
    )
    assert not missing, (
        f"ces composants acceptent ``disabled=`` mais ne sont pas dans "
        f"_CASES : {missing}.\n"
        f"  Tant qu'ils n'y sont pas, ils peuvent shipper sans "
        f"``aria-disabled`` et avec le combo pointer-events/curseur que "
        f"cette gate existe pour interdire — c'est exactement ce qui est "
        f"arrivé à ``draggable``.\n"
        f"  Ajoute une entrée, ou déclare la raison dans _NOT_A_CONTROL."
    )


def test_the_unaudited_list_only_shrinks() -> None:
    """Une dette qui survit à la disparition de son composant est du bruit
    que la prochaine lecture prendra pour une décision — et une dette qui
    reste listée alors qu'elle est PAYÉE cache le progrès."""
    stale = sorted(name for name in _UNAUDITED if not _accepts_disabled(name))
    assert not stale, (
        f"_UNAUDITED garde {stale}, qui n'acceptent plus ``disabled=`` — "
        f"retire les lignes."
    )
    paid = sorted(_UNAUDITED & _COVERED)
    assert not paid, (
        f"{paid} sont maintenant dans _CASES : retire-les de _UNAUDITED "
        f"pour que la dette restante soit juste."
    )


@pytest.mark.parametrize("label,factory", _CASES, ids=[c[0] for c in _CASES])
def test_disabled_state_is_machine_readable(label, factory) -> None:
    with render_isolated():
        out = serialize(factory())
    has_aria = 'aria-disabled="true"' in out
    has_native = bool(_NATIVE_DISABLED.search(out))
    assert has_aria or has_native, (
        f"{label}: a disabled render must expose the disabled state to assistive "
        f"tech — emit aria-disabled=\"true\" (role/div-based control) or a native "
        f"`disabled` attribute. Neither was found (screen readers see it as a "
        f"normal, focusable element — the tree bug fixed in 716bd4a)."
    )


@pytest.mark.parametrize("label,factory", _CASES, ids=[c[0] for c in _CASES])
def test_disabled_cursor_affordance(label, factory) -> None:
    """A disabled render shows ``cursor-not-allowed`` AND it actually paints —
    i.e. no element cancels it with ``pointer-events-none`` on the same class."""
    with render_isolated():
        out = serialize(factory())

    assert "cursor-not-allowed" in out, (
        f"{label}: a disabled render must show `cursor-not-allowed` on hover — "
        f"none found. Native controls get it via `disabled:cursor-not-allowed`; "
        f"role/div-based ones via `aria-disabled:cursor-not-allowed` (the Link "
        f"pattern)."
    )

    conflicts = [
        cls for cls in _CLASS_ATTR.findall(out)
        if "cursor-not-allowed" in cls and "pointer-events-none" in cls
    ]
    assert not conflicts, (
        f"{label}: an element carries BOTH `pointer-events-none` and "
        f"`cursor-not-allowed` — the pointer-events rule cancels the cursor "
        f"(no pointer events → no cursor paints), so the user sees the default "
        f"arrow. Drop `pointer-events-none` and neutralise hover via "
        f"`aria-disabled:` specificity (the Link/tree fix). Offending class: "
        f"{conflicts[0]!r}"
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : les cas d'affordance couverts sont toujours là."""
    assert len(_CASES) >= 30, (
        f"seulement {len(_CASES)} cas d'affordance désactivée (35 le "
        f"2026-08-19) — la table a rétréci, la gate juge moins de composants."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : l'attribut natif ``disabled`` est encore reconnu.

    La gate exige que l'état désactivé soit lisible par une machine. Si
    la regex cessait de matcher, elle ne verrait plus l'attribut natif
    et accuserait des composants corrects — ou pire, en absoudrait.
    """
    for offending in ('<button disabled>', '<input disabled="">', "<button disabled/>"):
        assert _NATIVE_DISABLED.search(offending), f"{offending!r} devrait mordre"
    for licit in ('<div data-disabled="true">', '<div class="is-disabled">'):
        assert not _NATIVE_DISABLED.search(licit), f"{licit!r} : faux positif"

"""Source unique : quel attribut HTML agit sur quel tag.

Le piège wrapper-vs-carrier (cf. ``traps.md``) : ``emit_attrs`` pose
``bz-attr:<prop>`` sur la RACINE du composant, mais ``disabled`` /
``checked`` / ``src`` … n'ont d'effet que sur un tag précis. Sur le
``<div>`` wrapper d'un composite, le runtime réécrit l'attribut à chaque
tick réactif et le DOM ne bouge pas.

Deux consommateurs, **une seule table** :

- ``tests/consistency/test_binding_lands_on_carrier.py`` — la gate
  (statique, sans navigateur, dans le sous-ensemble rapide) ;
- ``tests/audit/interaction.py`` ``probe_client_binding_lands_on_carrier``
  — le probe DOM équivalent, qui voit en plus ce que le runtime a
  réellement monté.

⚠️ Le préfixe vient de ``protocol.BZ_ATTR_PREFIX``, JAMAIS d'un littéral
recopié. Le probe cherchait ``x-bz-prop:`` (Alpine-era) longtemps après
le rebrand ``bz-`` : il ne matchait plus aucun attribut et passait au
vert sur des composants cassés (F01–F04 de l'audit 2026-07-18).
"""

from __future__ import annotations

from html.parser import HTMLParser

from bretzel.runtime.protocol import BZ_ATTR_PREFIX

# Attribut → tags où il agit réellement (MDN, restreint aux attributs
# que les composants Bretzel bindent). Un attribut ABSENT de la table est
# universel (``aria-*``, ``data-*``, ``class``, ``style``, ``hidden``,
# ``title``, ``id``, ``tabindex``, ``role``…) et n'est jamais une
# violation — mieux vaut ne pas lister que lister sans contrainte.
ATTR_CARRIERS: dict[str, frozenset[str]] = {
    "disabled": frozenset({"input", "select", "textarea", "button",
                           "fieldset", "optgroup", "option"}),
    "readonly": frozenset({"input", "textarea"}),
    "required": frozenset({"input", "select", "textarea"}),
    "multiple": frozenset({"input", "select"}),
    "checked": frozenset({"input"}),
    "selected": frozenset({"option"}),
    "value": frozenset({"input", "select", "textarea", "option",
                        "button", "li", "meter", "progress", "param"}),
    "min": frozenset({"input", "meter", "progress"}),
    "max": frozenset({"input", "meter", "progress"}),
    "step": frozenset({"input"}),
    "pattern": frozenset({"input"}),
    "placeholder": frozenset({"input", "textarea"}),
    "accept": frozenset({"input"}),
    "maxlength": frozenset({"input", "textarea"}),
    "minlength": frozenset({"input", "textarea"}),
    "autofocus": frozenset({"input", "select", "textarea", "button"}),
    "autocomplete": frozenset({"input", "select", "textarea", "form"}),
    # ⚠️ L'attribut HTML ``size`` (largeur en caractères), pas le token
    # de design ``size=`` des composants — celui-là est ``emit_attr=False``
    # partout et ne devrait jamais atterrir comme attribut HTML.
    "size": frozenset({"input", "select"}),
    "src": frozenset({"img", "iframe", "audio", "video", "source",
                      "track", "input", "script", "embed"}),
    "href": frozenset({"a", "area", "link", "base"}),
    "for": frozenset({"label", "output"}),
    "open": frozenset({"details", "dialog"}),
}


def is_valid_carrier(tag: str, attr: str) -> bool:
    """``attr`` fait-il quelque chose sur ``<tag>`` ?

    Un **custom element** (tag contenant un ``-`` : ``bz-calendar``,
    ``iconify-icon``) est valide pour n'importe quel attribut : il gère
    sa propre réactivité via ``attributeChangedCallback``.
    """
    if "-" in tag:
        return True
    carriers = ATTR_CARRIERS.get(attr)
    return carriers is None or tag in carriers


class _DirectiveCollector(HTMLParser):
    """Collecte ``(tag, attr, expr)`` pour chaque ``bz-attr:<attr>``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.startswith(BZ_ATTR_PREFIX):
                self.found.append((tag, name[len(BZ_ATTR_PREFIX):], value or ""))

    handle_startendtag = handle_starttag


def carrier_violations(html: str) -> list[tuple[str, str, str]]:
    """``(tag, attr, expr)`` pour chaque directive posée sur un tag inerte."""
    collector = _DirectiveCollector()
    collector.feed(html)
    return [f for f in collector.found if not is_valid_carrier(f[0], f[1])]


__all__ = [
    "ATTR_CARRIERS",
    "BZ_ATTR_PREFIX",
    "carrier_violations",
    "is_valid_carrier",
]

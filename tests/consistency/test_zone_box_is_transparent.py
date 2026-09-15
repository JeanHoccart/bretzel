"""Gate : une zone de rafraîchissement n'a pas de boîte, et n'en donne pas.

Un ``@refreshable`` est une frontière de **transport** : HTMX vise son
``id`` pour ses swaps, idiomorph la retrouve par son ``bz-id``. Rien de
tout ça ne demande une boîte — et tant qu'elle en avait une, elle
**cassait la disposition du parent** ::

    with ui.vstack():          # gap-4
        ui.heading("Reference")
        reference_panel()      # ← ses N enfants comptaient pour UN

L'auteur lit trois enfants espacés ; le navigateur en voit deux et colle
le contenu de la zone. Mesuré avant le fix : parent ``gap:16px``,
éléments de 20 px → 36 px avant la zone, **20 px dedans**. Après :
36 px partout.

Ce n'était pas une inattention isolée — **100 des 201 zones du
playground** posaient leurs enfants à même la zone. Quand la moitié des
exemples du framework tombe dans le piège, c'est le défaut de l'API qui
est mal placé, pas l'auteur qui se trompe.

Deux invariants, et le second est celui qui peut faire mal :

1. **La branche WRAP porte ``contents``.** Sans elle, le piège revient.
2. **La branche SPLICE ne le porte JAMAIS.** Elle fusionne les attrs de
   la zone DANS l'élément unique de l'appelant : y poser ``contents``
   supprimerait la boîte de sa ``ui.card`` ou de son ``ui.datatable`` —
   un fond, une bordure et un rembourrage qui s'évaporent, en silence,
   sur le composant de quelqu'un d'autre. C'est la régression coûteuse,
   et c'est celle qu'un « ajoute la classe aux attrs communs » produit
   naturellement.

⚠️ Ce que la gate NE dit pas : que la disposition est correcte à
l'écran. ``display:contents`` est une propriété calculée, invisible au
SSR — la preuve géométrique vit dans
``tests/probes/probe_datatable_filter.py``. Ici on protège la FORME, qui
est décidable.
"""

from __future__ import annotations

from bretzel.core.tree import Element, TextNode
from bretzel.render.fusion import BZ_ID_ATTR, fuse_or_wrap

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "rend des zones et lit les attributs produits ; chaque test porte "
    "son cas et son contre-cas, sans motif à reconnaître"
)


def _classes(node: Element) -> set[str]:
    return set(str(node.attrs.get("class", "")).split())


# ── 1. La zone qui ENVELOPPE est transparente ─────────────────────────


def test_wrapping_zone_has_no_box() -> None:
    out = fuse_or_wrap(
        [Element("p", {}, (TextNode("un"),)), Element("p", {}, (TextNode("deux"),))],
        bz_id="zone",
    )
    assert "contents" in _classes(out), (
        "l'enveloppe de zone a repris une boîte : elle redevient un "
        "élément flex à elle seule, donc le `gap` du parent s'arrête à "
        "elle et son contenu se colle. C'est ce que 100 zones du "
        "playground sur 201 subissaient."
    )


def test_wrapping_zone_keeps_its_swap_identity() -> None:
    """La boîte disparaît, l'ÉLÉMENT reste — sinon HTMX n'a plus de cible."""
    out = fuse_or_wrap([TextNode("a"), TextNode("b")], bz_id="zone")
    assert out.attrs[BZ_ID_ATTR] == "zone"
    assert out.attrs["id"] == "zone"


# ── 2. La zone qui FUSIONNE n'en donne pas ────────────────────────────


def test_spliced_zone_never_receives_contents() -> None:
    """L'invariant coûteux.

    Quand la zone n'a qu'un enfant Element, elle ne l'enveloppe pas :
    elle fusionne ses attrs DEDANS. Un ``contents`` qui suivrait
    supprimerait la boîte du composant de l'appelant.
    """
    card = Element("div", {"class": "rounded-xl border bg-surface p-4"}, ())
    out = fuse_or_wrap([card], bz_id="zone")
    assert "contents" not in _classes(out), (
        "`contents` a atterri sur l'élément de l'APPELANT : sa bordure, "
        "son fond et son rembourrage ne peignent plus rien. La classe "
        "n'appartient qu'à la branche wrap — pas aux attrs communs."
    )
    # Et ce qu'il avait est intact.
    assert _classes(out) == {"rounded-xl", "border", "bg-surface", "p-4"}


def test_spliced_zone_with_no_class_stays_classless() -> None:
    """Même sans classe à préserver, on n'en invente pas une."""
    out = fuse_or_wrap([Element("section", {}, ())], bz_id="zone")
    assert "class" not in out.attrs, out.attrs


# ── 3. L'appelant garde la main ───────────────────────────────────────


def test_caller_class_wins_over_contents() -> None:
    """``setdefault``, pas écrasement : si un jour un ``extra_attrs``
    apporte sa classe, c'est la sienne qui vaut."""
    out = fuse_or_wrap(
        [TextNode("a"), TextNode("b")],
        bz_id="zone",
        extra_attrs={"class": "grid gap-2"},
    )
    assert _classes(out) == {"grid", "gap-2"}

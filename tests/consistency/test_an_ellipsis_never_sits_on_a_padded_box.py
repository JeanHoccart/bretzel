"""Gate : l'ellipse vit sur un élément SANS marge intérieure horizontale.

Le défaut, livré puis rattrapé le 2026-08-25
----------------------------------------------
En réparant le débordement de `ui.toggle_group`, j'ai posé `truncate` sur
le **bouton** — l'élément qui porte `px-4`. Rendu dans une cellule de
240 px : les trois options se touchaient, « CompacteNormale » se lisait en
un mot, et **aucune ellipse n'apparaissait**. Rapporté par l'utilisateur
en dix secondes sur une capture, après qu'une sonde eut déclaré le rendu
correct — elle mesurait des boîtes, pas de la lisibilité.

**Le mécanisme.** `truncate` vaut `overflow-hidden` + `text-ellipsis` +
`whitespace-nowrap`, et `overflow-hidden` rogne au bord de la boîte de
**padding**, pas de la boîte de contenu. Un texte plus large que son
contenu peint donc PAR-DESSUS les marges intérieures de son propre
élément : la respiration disparaît, les libellés voisins se touchent, et
l'ellipse — qui se calcule sur la boîte de contenu — ne s'affiche jamais
parce que le texte a de la place au-delà.

La correction est structurelle, pas cosmétique : l'ellipse a besoin d'un
élément **à elle**, à l'intérieur de la boîte padée. `ui.toggle_group`
enveloppe donc son étiquette dans un `<span>` qui porte `truncate`, et le
bouton garde ses marges.

Ce que la gate garde
---------------------
La convention existait déjà partout — 23 slots tronquent dans le
catalogue, et **les 23 sont des slots d'étiquette** (`label`, `name`,
`title_text`, `description`, `chip_name`…), jamais la coquille padée qui
les contient. Zéro violation au moment de l'écriture : ma version cassée
était la première. C'est donc un cliquet, et il est à zéro.

⚠️ Ce qu'elle ne peut PAS attraper : que l'ellipse soit posée au bon
NIVEAU. Un `truncate` sur un élément sans padding mais qui n'est pas le
porteur du texte reste inutile — la gate le laisse passer. Ce qu'elle
ferme, c'est la composition qui rend un HTML parfait et un écran
illisible.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import public_component_classes, ui_name_of

#: L'ellipse, sous ses deux écritures Tailwind.
_ELLIPSIS = re.compile(r"(?:^|\s)(?:truncate|text-ellipsis)(?:\s|$)")

#: Les marges intérieures HORIZONTALES — les seules qui comptent ici : le
#: rognage se fait sur l'axe du texte. Un ``py-2`` sur un élément qui
#: tronque est sans conséquence.
_PADDING_X = re.compile(r"(?:^|\s)(p|px|ps|pe|pl|pr)-\S+")

#: 23 slots tronquent, mesurés le 2026-08-25. Le seuil laisse de la marge
#: sans laisser passer une découverte cassée.
_TRUNCATING_FLOOR = 20


def classes_per_slot(cls: type) -> dict[str, str]:
    """``clé de slot`` → **toutes** les classes qui atterrissent dessus.

    ⚠️ La première version de cette gate lisait les chaînes du thème une
    par une — et elle NE MORDAIT PAS sur le défaut qui l'a fait écrire.
    La faute livrée mettait ``truncate`` dans ``slots["item"]`` pendant
    que le ``px-4`` venait de ``sizes["md"]["item"]`` : deux chaînes, UN
    seul élément. Une gate qui les juge séparément déclare donc correct
    un composant dont le rendu est cassé.

    C'est le test de mutation qui l'a montré, pas la relecture — et c'est
    exactement ce que la gardienne des gates existe pour forcer.
    """
    from bretzel.components.base.sizes import is_size_keyed

    theme = getattr(cls, "THEME", None)
    if not isinstance(theme, dict):
        return {}
    parts: dict[str, list[str]] = {}
    slots = theme.get("slots")
    if isinstance(slots, dict):
        for key, value in slots.items():
            if isinstance(value, str):
                parts.setdefault(str(key), []).append(value)
    sizes = theme.get("sizes")
    # ``is_size_keyed`` départage les deux imbrications opposées des
    # tables ``sizes`` (clés = tailles, ou clés = slots). Sans lui, un
    # thème indexé par slot ferait passer des noms de palier pour des
    # noms de slot.
    if isinstance(sizes, dict) and is_size_keyed(sizes):
        for step in sizes.values():
            if isinstance(step, dict):
                for key, value in step.items():
                    if isinstance(value, str):
                        parts.setdefault(str(key), []).append(value)
    return {key: " ".join(chunks) for key, chunks in parts.items()}


def truncating_slots() -> list[tuple[str, str, str]]:
    """``(composant, clé de slot, classes réunies)`` pour tout ce qui
    tronque."""
    out: list[tuple[str, str, str]] = []
    for cls in public_component_classes():
        for key, classes in classes_per_slot(cls).items():
            if _ELLIPSIS.search(classes):
                out.append((ui_name_of(cls), key, classes))
    return sorted(set(out))


def horizontal_padding(classes: str) -> list[str]:
    """Les marges intérieures horizontales d'une chaîne de classes.

    Le DÉTECTEUR, isolé pour que la preuve de morsure l'attaque sur des
    chaînes fabriquées plutôt que sur un faux thème.
    """
    return [match.group(0).strip() for match in _PADDING_X.finditer(classes)]


_POPULATION = truncating_slots()


# ── Plancher ──────────────────────────────────────────────────────────

def test_the_sweep_finds_the_truncating_slots() -> None:
    assert len(_POPULATION) >= _TRUNCATING_FLOOR, (
        f"seulement {len(_POPULATION)} slots tronquants trouvés "
        f"(23 mesurés le 2026-08-25) — vérifie la découverte avant de "
        f"croire que cette gate passe."
    )


# ── L'interdiction ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name,key,classes",
    _POPULATION,
    ids=[f"{n}.{k}" for n, k, _ in _POPULATION],
)
def test_no_ellipsis_on_a_padded_box(name: str, key: str, classes: str) -> None:
    pads = horizontal_padding(classes)
    assert not pads, (
        f"ui.{name} → slot `{key}` tronque ET porte {pads}.\n"
        f"`overflow-hidden` rogne au bord de la boîte de PADDING : le "
        f"texte peint par-dessus ses propres marges, la respiration "
        f"disparaît, les voisins se touchent, et l'ellipse ne s'affiche "
        f"jamais. Mesuré sur ui.toggle_group le 2026-08-25 — trois "
        f"options collées, « CompacteNormale » en un mot.\n"
        f"L'ellipse a besoin d'un élément à ELLE, à l'intérieur de la "
        f"boîte padée : enveloppe le texte dans un slot dédié."
    )


# ── Preuve que le détecteur mord, dans les DEUX sens ──────────────────

def test_the_detector_bites_on_the_shape_that_shipped() -> None:
    """Le versant ILLICITE — l'écriture exacte qui a été livrée."""
    fautif = "inline-flex items-center justify-center gap-1.5 min-w-0 truncate"
    assert _ELLIPSIS.search(fautif)
    # Le padding vient de la table ``sizes`` sur le même élément.
    assert horizontal_padding("h-full px-4 text-sm") == ["px-4"]


def test_the_detector_stays_quiet_on_the_licit_forms() -> None:
    """Le versant LICITE, et c'est lui qui a trouvé les deux seuls bugs
    de gate du dépôt.

    Quatre écritures correctes : l'étiquette nue qui tronque, la même
    avec une marge VERTICALE (sans conséquence sur l'axe du texte), une
    coquille padée qui ne tronque pas, et un slot qui ne fait ni l'un ni
    l'autre.
    """
    assert horizontal_padding("truncate") == []
    assert horizontal_padding("truncate py-2") == []
    assert not _ELLIPSIS.search("inline-flex items-center px-4 h-full")
    assert not _ELLIPSIS.search("flex gap-2")


def test_the_detector_does_not_confuse_other_p_classes() -> None:
    """``pointer-events-none``, ``place-items-center``, ``pb-1`` : trois
    classes qui commencent par ``p`` et ne sont pas une marge
    horizontale. Une expression trop large les prendrait pour telles et
    ferait rougir du correct."""
    assert horizontal_padding("truncate pointer-events-none") == []
    assert horizontal_padding("truncate place-items-center") == []
    assert horizontal_padding("truncate pb-1 pt-2") == []

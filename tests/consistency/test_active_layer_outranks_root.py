"""Une couche d'ÉTAT qui recouvre une couleur du ``root`` porte une variante.

Deux utilitaires Tailwind qui posent la MÊME propriété CSS ont la MÊME
spécificité (0,1,0). Le vainqueur est alors le dernier des deux **dans la
feuille générée** — et l'ordre des tokens dans l'attribut ``class=`` n'y
change **rien**. Un thème qui écrit ``text-muted`` sur son slot ``root`` et
``text-{bg_color}`` nu sur son slot ``active`` ne décide donc pas de la
couleur qu'il rend : c'est Tailwind qui la décide, à sa place.

Mesuré (2026-08-08, navigateur) sur ``bottom_bar``, qui portait cette forme :
``color=error`` et ``color=info`` rendaient **gris**, les quatre autres
passaient. Le partage n'est pas une règle — en dev, Tailwind tourne dans le
navigateur et émet ses règles dans l'ordre où il rencontre les classes du DOM,
donc le camp des perdants dépend de la page. Le seul ordre stable est celui du
``@theme`` généré (``bretzel/theme/tailwind.py``), où ``muted`` sort **en
dernier** des onze couleurs sémantiques : dans un build compilé, la forme nue
perdrait vraisemblablement pour les SIX couleurs.

**Le correctif est une variante d'état** — ``data-[active=true]:text-…``,
``group-data-[selected=true]:text-…``, ``aria-current:text-…`` — qui monte la
spécificité à (0,2,0). Le verdict cesse de dépendre d'un ordre, en dev comme
en build.

⚠️ Cette gate LIT les thèmes, elle n'en unifie aucun : chaque composant garde
ses propres chaînes de classes (memory ``feedback_no_shared_style_tokens``).
"""

from __future__ import annotations

import ast
import re

import pytest

from tests.consistency._discovery import ParsedSource, theme_sources

#: Preuve de morsure : contrôle POSITIF — le détecteur trouve encore des couches d'état
#: à surveiller sur le corpus réel.
MUTATION_PROOF = "test_the_gate_finds_layers_to_watch"

_THEMES = theme_sources()

# Les slots qui se composent PAR-DESSUS ``root`` : le composant émet
# ``class="<root> <state>"`` (ou pousse ``<state>`` via ``bz-class``), donc
# leurs utilitaires entrent en concurrence directe avec ceux du root.
_STATE_SLOTS = ("active", "selected", "checked", "current")

# Un utilitaire de couleur de texte NU : pas de variante devant (``foo:``),
# pas de crochet arbitraire (``text-[11px]`` est une TAILLE, pas une couleur).
_BARE_TEXT = re.compile(r"^text-(?!\[)[a-z{][\w{}-]*(?:/\d+)?$")


def _slot_strings(theme: ParsedSource) -> dict[str, list[str]]:
    """Les chaînes de classes par nom de slot, sur tous les dicts du thème.

    Un thème porte plusieurs tables (``slots`` de plusieurs sous-composants,
    ``sizes``, ``variants``) ; on ratisse tous les dicts et on regroupe par
    clé, ce qui suffit ici : on ne compare que ``root`` à ``active`` &co.
    """
    out: dict[str, list[str]] = {}
    for node in ast.walk(theme.tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if not (isinstance(key, ast.Constant)
                    and isinstance(key.value, str)):
                continue
            parts = [
                n.value for n in ast.walk(value)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            if parts:
                out.setdefault(key.value, []).append(" ".join(parts))
    return out


def _bare_text_tokens(chunks: list[str]) -> list[str]:
    return [t for chunk in chunks for t in chunk.split() if _BARE_TEXT.match(t)]


def _offenders(theme: ParsedSource) -> list[tuple[str, list[str], list[str]]]:
    slots = _slot_strings(theme)
    root = _bare_text_tokens(slots.get("root", []))
    if not root:
        return []
    found = []
    for state in _STATE_SLOTS:
        bare = _bare_text_tokens(slots.get(state, []))
        if bare:
            found.append((state, root, bare))
    return found


def test_the_gate_finds_layers_to_watch() -> None:
    """Plancher de non-vacuité. Le test ci-dessous est une INTERDICTION : il
    passerait tout aussi bien si plus AUCUN thème ne composait une couche
    d'état par-dessus une couleur de root — ni le ``rglob``, ni l'extraction
    AST, ni la regex ne signalent leur propre panne. On vérifie donc qu'il
    reste des couches à surveiller : un thème qui a un slot d'état porteur
    d'un ``text-*`` (nu OU sous variante) ET un ``text-*`` nu sur son root.
    """
    watched = []
    for theme in _THEMES:
        slots = _slot_strings(theme)
        if not _bare_text_tokens(slots.get("root", [])):
            continue
        for state in _STATE_SLOTS:
            chunks = slots.get(state, [])
            if any("text-" in c for c in chunks):
                watched.append(f"{theme.path.parent.name}.{state}")
                break
    assert len(watched) >= 3, (
        f"Seulement {len(watched)} couche(s) d'état surveillée(s) : "
        f"{watched}. Sous ce seuil, la gate ci-dessous ne prouve plus rien — "
        f"vérifie que l'extraction AST et la regex marchent encore avant de "
        f"baisser le plancher."
    )


@pytest.mark.parametrize("theme", _THEMES, ids=lambda s: s.path.parent.name)
def test_state_layer_carries_a_variant(theme: ParsedSource) -> None:
    offenders = _offenders(theme)
    assert not offenders, "\n".join(
        f"{theme.path.parent.name} : le slot `{state}` pose {bare} SANS "
        f"variante "
        f"d'état, alors que `root` pose déjà {root}.\n"
        f"  Même propriété, même spécificité (0,1,0) → c'est l'ordre de la "
        f"feuille Tailwind qui tranche, PAS l'ordre du `class=`. La couleur "
        f"rendue n'est donc pas celle que le thème croit choisir.\n"
        f"  Fix : préfixe la classe recouvrante par sa variante d'état — "
        f"`data-[active=true]:text-…` (spécificité 0,2,0). Le verdict cesse "
        f"de dépendre d'un ordre."
        for state, root, bare in offenders
    )

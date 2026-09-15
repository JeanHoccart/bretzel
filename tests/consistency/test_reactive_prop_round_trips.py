"""Gate de convergence : chaque ``reactive_prop`` passée explicitement PREND
EFFET (le composant la forwarde bien à ``super().__init__``).

Le mécanisme. Un composant déclare ses props via `reactive_prop`, expose des
kwargs typés dans son ``__init__``, et doit les forwarder au socle. Le socle
(`Component.__init__`) drope les kwargs `None` (garde le défaut) — donc
l'ancienne garde manuelle `forwarded`/`if x is not None` est inutile, et
chaque `__init__` doit désormais forwarder ses props DIRECTEMENT
(`super().__init__(size=size, …, **kwargs)`).

Le risque de la conversion (2026-07-16) : en retirant le dict `forwarded`,
OUBLIER un param dans l'appel `super()` direct → la prop n'est plus
forwardée, sa valeur passée par l'appelant est silencieusement ignorée, le
défaut s'applique toujours. Aucune erreur — juste une prop morte.

Cette gate ferme ça, et force la convergence pour l'avenir : pour chaque
prop, on construit le composant en passant une valeur SENTINELLE ≠ défaut, et
on vérifie que `_reactive_values[prop]` a bougé du défaut. Si le param est
oublié dans le forward, la valeur stockée reste le défaut → rouge. Un
composant transformant sa valeur à la construction passe quand même (la
valeur stockée diffère du défaut) — on teste « la prop est forwardée », pas
« stockée verbatim ».

Self-evolving : piloté par `public_component_classes()` x `__reactive_props__`
— un nouveau composant, ou une nouvelle prop, est couvert sans toucher ce
fichier. Le prochain `__init__` qui oublie de forwarder une prop rougit.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from tests.consistency._discovery import public_component_classes

#: Preuve de morsure : re-mesure chaque exemption plutôt que de la croire — le mécanisme
#: existe pour qu'une entrée réparée ne dorme pas dans la table.
MUTATION_PROOF = "test_known_unreachable_is_still_unreachable"

# Args requis NON-parent pour construire seul (options, max…). On évite
# délibérément les builders `CONSTRUCT` qui enveloppent l'enfant dans un
# parent (ToggleButton→ToggleGroup, NavbarItem→Navbar…) : ils retournent le
# PARENT, donc inspecter `_reactive_values` viserait la mauvaise instance
# (faux positif). Ces enfants compound sont skippés (TypeError → skip).
_EXTRA: dict[str, dict[str, object]] = {
    "Select": {"options": [("a", "A"), ("b", "B")]},
    "Combobox": {"options": [("a", "A"), ("b", "B")]},
    "ToggleGroup": {"options": [("a", "A"), ("b", "B")]},
    "RadioGroup": {"options": [("a", "A"), ("b", "B")]},
    "Progress": {"max": 100},
    "Pagination": {"total_pages": 10},
}

# Props exclues avec RAISON — pas des oublis de forward, des collisions de
# nommage pré-existantes (hors périmètre du sweep forward-guard 2026-07-16).
#
# VIDE depuis le 2026-07-29. L'unique entrée était ``("Icon", "style")`` : la
# prop reactive ``style`` d'Icon était masquée par le modifier universel
# ``style=`` (inline CSS), popé avant le split des kwargs. Son commentaire
# proposait le fix — « à renommer, ex. ``icon_style`` » — et ce renommage a
# été livré (`75e934b1`). Mesuré : ``Icon.__reactive_props__`` porte
# désormais ``icon_style`` et plus ``style``, donc l'entrée n'excluait plus
# rien et achetait un faux sentiment de couverture.
#
# ⚠️ Si tu ajoutes une entrée ici, ajoute AUSSI sa vérification dans
# ``test_known_unreachable_is_still_unreachable`` — une allowlist qu'on ne
# re-mesure pas est une gate qui a déjà perdu (audit du socle, § pathologies
# de gate : c'est exactement comme ça que celle-ci a pourri).
_KNOWN_UNREACHABLE: frozenset[tuple[str, str]] = frozenset()


def _sentinel(default: object) -> object | None:
    """Une valeur ≠ ``default``, de type plausible. ``None`` = on ne sait pas
    fabriquer de sentinelle sûre (list/dict/objets) → prop skippée."""
    if isinstance(default, bool):
        return not default
    if isinstance(default, str):
        return "zzq_sentinel" if default != "zzq_sentinel" else "other"
    if isinstance(default, int):
        return default + 7
    if isinstance(default, float):
        return default + 1.5
    if default is None:
        # défaut None → n'importe quelle valeur non-None prend effet. Une
        # string couvre les props ``str | None`` (les plus courantes) ; les
        # props ``… | None`` non-str stockent quand même la string verbatim
        # (le socle ne coerce pas), donc ``!= None`` tient.
        return "zzq_sentinel"
    return None  # list / dict / date / objet → skip (sentinelle non triviale)


def _construct(cls: type, prop: str, value: object):
    """Construit ``cls`` SEUL avec ``prop=value`` (+ args requis non-parent).
    Lève TypeError si un contexte parent est requis → la prop est skippée."""
    return cls(**{prop: value}, **_EXTRA.get(cls.__name__, {}))


_CASES: list[tuple[type, str]] = [
    (cls, prop)
    for cls in public_component_classes()
    for prop in getattr(cls, "__reactive_props__", {})
    if (cls.__name__, prop) not in _KNOWN_UNREACHABLE
]


def test_known_unreachable_is_still_unreachable() -> None:
    """Re-mesure chaque exemption. Vide aujourd'hui — donc no-op — mais le
    mécanisme existe pour que le commentaire de ``_KNOWN_UNREACHABLE`` ne
    soit pas une promesse creuse : la précédente entrée y a dormi des mois
    après que le bug qu'elle documentait avait été réparé."""
    for cls_name, prop in sorted(_KNOWN_UNREACHABLE):
        cls = next(
            (c for c in public_component_classes() if c.__name__ == cls_name),
            None,
        )
        assert cls is not None, (
            f"_KNOWN_UNREACHABLE exempte {cls_name}.{prop}, mais {cls_name} "
            f"n'est plus un composant public — retire l'entrée."
        )
        assert prop in getattr(cls, "__reactive_props__", {}), (
            f"_KNOWN_UNREACHABLE exempte {cls_name}.{prop}, mais {prop!r} "
            f"n'est plus une prop reactive de {cls_name} (renommée ? "
            f"supprimée ?) — l'entrée n'exclut plus rien, retire-la. C'est "
            f"exactement comme ça que ('Icon', 'style') a pourri."
        )


@pytest.mark.parametrize(
    "cls,prop", _CASES, ids=[f"{c.__name__}.{p}" for c, p in _CASES]
)
def test_reactive_prop_is_forwarded(cls: type, prop: str) -> None:
    descriptor = cls.__reactive_props__[prop]
    default = descriptor.resolve_default()
    sentinel = _sentinel(default)
    if sentinel is None:
        pytest.skip(f"pas de sentinelle triviale pour default={default!r}")

    with render_isolated():
        try:
            instance = _construct(cls, prop, sentinel)
        except TypeError as exc:
            pytest.skip(f"contexte parent / args requis non câblés : {exc}")
        stored = instance._reactive_values.get(prop)

    # Un builder CONSTRUCT peut rebinder la valeur (dates) — dans ce cas
    # ``stored`` != ``sentinel`` mais reste != ``default``, ce qui suffit :
    # on prouve que la prop est FORWARDÉE (a pris effet), pas qu'elle est
    # stockée verbatim.
    assert stored != default, (
        f"{cls.__name__}.{prop} : passé {sentinel!r} mais `_reactive_values["
        f"{prop!r}]` vaut toujours le défaut {default!r} → la prop N'EST PAS "
        f"forwardée à `super().__init__`. Le forward direct a-t-il oublié "
        f"`{prop}={prop}` ? (cf. la conversion des gardes `forwarded`)."
    )


def test_gate_is_not_vacuous() -> None:
    # Assez de props réellement exercées (non skippées) pour que la gate morde.
    exercised = 0
    for cls, prop in _CASES:
        descriptor = cls.__reactive_props__[prop]
        if _sentinel(descriptor.resolve_default()) is not None:
            exercised += 1
    assert exercised >= 100, (
        f"seulement {exercised} props avec sentinelle — la découverte "
        f"`__reactive_props__` a-t-elle cassé ?"
    )

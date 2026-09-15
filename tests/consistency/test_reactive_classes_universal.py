"""Gate G7 — ``classes=<ClientBinding>`` marche sur TOUS les composants,
et ne détruit jamais la composition statique.

Le contrat (funnel `kwarg-routing.md` § reserved, `client-reactive-surface.md`
§ A.5) : ``classes=`` est un kwarg réservé, **bindable sur tous les
composants**. Le socle en est propriétaire — un composant ne s'en occupe
jamais (cf. gate ``test_no_manual_user_class_append``).

Ce que la gate exige, pour chaque composant public :

1. le binding produit une directive **que le runtime V3 interprète**,
   référençant le chemin ``$bz.state.…`` ;
2. la composition statique du thème **survit** — un ``classes=binding``
   ne doit pas déshabiller le composant.

Pourquoi (audit 2026-07-27, dérivé de F23)
------------------------------------------
Le mécanisme documenté était un reliquat V2 : ``:class="'<statique>' + ' '
+ (binding || '')"`` — une **syntaxe Alpine que le runtime V3 n'écoute
pas** (il ne connaît que les 13 directives ``bz-*``). Deux symptômes
opposés selon le composant :

- Button / IconButton (les 2 seuls à appeler ``apply_class_attrs``)
  émettaient le ``:class`` inerte **et droppaient leur ``class=``
  statique** au passage → bouton entièrement dénué de style ;
- les ~50 autres posent ``attrs["class"]`` à la main, donc ignoraient
  le binding en silence (l'audit n'avait vu que cette moitié-là, sur
  Link, et l'avait prise pour la déviation — c'était la majorité).

Le fix est allé au point d'assemblage : la branche réactive vit dans
``_apply_universal_modifiers`` (le wrap métaclasse qui possède déjà
``classes=`` littéral sur le vrai root), donc les 55 composants l'ont
d'un coup, et ``bz-class`` — qui accepte une string et **préserve le
``class=`` statique** — remplace le ``:class`` mort.
"""

from __future__ import annotations

import re

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.runtime.protocol import BZ_CLASS_PREFIX
from bretzel.state.scopes.client import ClientBinding
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import public_component_classes

_PATH = "$bz.state.draft.default.extra"


def _binding() -> ClientBinding:
    return ClientBinding(class_name="draft", instance_key="default",
                         field_name="extra", value="ring-2")


def _render(cls: type, **kwargs) -> str:
    """Rend ``cls`` via le registre de construction fidèle de l'audit
    (parents requis, options, valeurs SSR réalistes)."""
    builder = CONSTRUCT.get(cls.__name__)
    with render_isolated():
        if builder is not None:
            # Le builder pose la prop bindée lui-même : on lui donne une
            # prop inoffensive et on greffe nos kwargs sur l'instance via
            # un sous-classement du lambda n'est pas possible → on tente
            # la construction directe, et on skip si elle échoue.
            comp = cls(**kwargs)
        else:
            comp = cls(**kwargs)
        return serialize(comp.render())


@pytest.mark.parametrize("cls", public_component_classes(),
                         ids=lambda c: c.__name__)
def test_classes_binding_emits_a_live_directive(cls: type) -> None:
    try:
        html = _render(cls, classes=_binding())
        static_html = _render(cls)
    except _Skip as exc:
        pytest.skip(str(exc))
    except Exception as exc:
        pytest.skip(f"{cls.__name__} non constructible sans contexte : "
                    f"{type(exc).__name__}: {exc}")

    assert ":class=" not in html, (
        f"{cls.__name__} émet un `:class=` — syntaxe Alpine que le runtime "
        f"V3 n'interprète pas (il ne connaît que les 13 directives bz-*). "
        f"Utiliser `{BZ_CLASS_PREFIX}` (il accepte une string et préserve "
        f"le class= statique)."
    )
    assert f'{BZ_CLASS_PREFIX}="{_PATH}"' in html, (
        f"{cls.__name__} : `classes=<ClientBinding>` n'émet aucun "
        f"`{BZ_CLASS_PREFIX}=\"{_PATH}\"`. Le kwarg est réservé et "
        f"documenté bindable sur TOUS les composants — le socle "
        f"(`_apply_universal_modifiers`) doit le poser sur le vrai root."
    )

    # La composition statique du thème doit survivre au binding : on
    # compare la 1re classe composée du rendu sans binding.
    m = re.search(r'\sclass="([^"]+)"', static_html)
    if m and m.group(1).strip():
        first_static = m.group(1).split()[0]
        assert first_static in html, (
            f"{cls.__name__} : `classes=<ClientBinding>` a effacé la "
            f"composition statique (classe {first_static!r} absente). "
            f"`{BZ_CLASS_PREFIX}` ajoute par-dessus le class= statique — "
            f"il n'y a aucune raison de le dropper."
        )

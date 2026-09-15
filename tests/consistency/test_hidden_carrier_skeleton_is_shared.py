"""Le squelette du porteur caché sort d'un seul endroit.

Un ``<div>`` ne porte ni ``name``/``value`` ni ``change`` natif. Les
composants dont la racine n'est pas un contrôle de formulaire posent donc un
``<input type="hidden">`` qui fait les deux — 12 sites dans 11 fichiers.

Cinq attributs y sont **invariants**, et c'est eux que
:func:`hidden_carrier_attrs` rend : ``type``, ``bz-ref``, la ``value`` SSR
(pour que le premier POST parte juste avant même que le runtime ait booté),
``bz-attr:value`` (la liaison qui la tient à jour) et ``bz-effect`` (le
dispatcher de ``change``, sans lequel tout le reste est muet).

⚠️ Le ``bz-effect`` est entré dans la primitive le 2026-08-21
--------------------------------------------------------------
Il en était exclu, au nom d'un argument qui s'est révélé **vide sur la
population concernée** : « le dispatch diffère réellement — une méthode de
scope pour Slider ». Or Slider n'appelle pas la primitive ; il est déclaré
ici même dans ``_SKELETON_DEBT``, comme Calendar et Dropzone, les deux
autres qui dispatchent depuis le runtime. Sur les **dix** appelants réels,
dix posaient ``change_emit_effect``, et neuf sur la même expression.

Ce que l'opt-in coûtait : un porteur sans dispatcher relocalise un
``hx-post`` que **rien ne déclenchera jamais** — contrôle inerte, sans
erreur ni avertissement. Les cinq pickers de date l'avaient oublié.
``dispatch=None`` refuse le dispatcher, ``dispatch=<expr>`` le pose sur
une autre expression (ToggleGroup). Cf.
``test_a_relocated_change_reaches_its_carrier.py``, qui garde la propriété
côté RENDU — y compris sur les quatre porteurs écrits à la main.

⚠️ Ce que la primitive NE factorise toujours PAS, et pourquoi
--------------------------------------------------------------
``name`` et ``required`` restent à l'appelant.

``name`` est le cas important. Coller un ``name="value"`` par défaut à un
``Tabs`` ou un ``Accordion`` **injecterait un champ parasite dans chaque
formulaire englobant**. Un Tabs n'est pas un contrôle de formulaire : il n'a
un ``name`` que si l'appelant en veut un. C'est une variance **légitime**,
et un ``hidden_carrier_input`` complet — que le recensement des affordances
du 2026-07-28 proposait — aurait uniformisé un bug.

⚠️ **Correction d'une affirmation de l'audit**, vérifiée à la main : il
annonçait que accordion / tree / tabs / pagination / toggle_group émettent
un input **sans** ``name``, donc une FormData amputée. **C'est faux** — les
cinq posent ``hidden_attrs["name"]``. Il n'y a pas de bug de FormData.

Ce qui reste dehors (``name``, ``required``) y reste pour une variance
qu'on peut NOMMER et qui se vérifie sur les appelants réels. C'est la
correction apportée le 2026-08-21 au raisonnement d'origine : « la
primitive factorise le facile et laisse le difficile » est juste tant que
le difficile est vraiment différent — et il faut le REVÉRIFIER sur la
population, pas sur un exemple qui n'en fait pas partie.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    COMPONENTS_DIR,
    assert_sweep_is_not_vacuous,
    component_sources,
)

_HAND_WRITTEN = re.compile(r'"type":\s*"hidden"')

# Sites qui posent encore le squelette à la main, avec la raison de leur
# forme. Égalité stricte : une entrée dont la dette est payée rougit.
_SKELETON_DEBT: dict[str, str] = {
    "components/inputs/calendar/calendar.py":
        "l'input est piloté par le custom element, pas par un bz-effect",
    "components/inputs/combobox/combobox.py":
        "deux porteurs (single + multi), refs distinctes",
    "components/inputs/select/select.py":
        "deux porteurs (single + multi), refs distinctes",
    "components/layout/dropzone/dropzone.py":
        "porteur écrit IMPÉRATIVEMENT par 19_dnd.js, pas lié : la zone n'a "
        "aucun scope (le geste est délégué au document), donc le `bz-ref` et "
        "le `bz-attr:value` de la primitive ne désigneraient rien",
}


def _rel(path) -> str:
    return f"components/{path.relative_to(COMPONENTS_DIR).as_posix()}"


def test_the_sweep_visits_the_components() -> None:
    assert_sweep_is_not_vacuous()


@pytest.mark.parametrize("path", component_sources(), ids=lambda p: p.name)
def test_no_new_hand_written_skeleton(path) -> None:
    if path.parts[-2] == "base" or path.name == "_wiring.py":
        pytest.skip("le socle possède la primitive")

    text = path.read_text(encoding="utf8")
    hits = [
        i for i, line in enumerate(text.splitlines(), 1)
        if not line.strip().startswith("#") and _HAND_WRITTEN.search(line)
    ]
    rel = _rel(path)
    owed = rel in _SKELETON_DEBT

    if hits and not owed:
        pytest.fail(
            f"{path.name} écrit le squelette du porteur caché à la main "
            f"(ligne(s) {hits}).\n"
            f"  Passe par `**hidden_carrier_attrs(<value_expr>, "
            f"initial=<ssr>)`, puis ajoute `name` / `required` toi-même — "
            f"ces deux-là sont VOLONTAIREMENT hors de la primitive. Le "
            f"dispatcher de `change`, lui, est ACQUIS : refuse-le avec "
            f"`dispatch=None`, redirige-le avec `dispatch=<expr>`.\n"
            f"  Si ta forme diverge pour une vraie raison, déclare-la dans "
            f"_SKELETON_DEBT avec cette raison."
        )
    if owed and not hits:
        pytest.fail(
            f"{rel} est déclaré en dette de squelette manuel "
            f"({_SKELETON_DEBT[rel]}) mais n'en porte plus — retire la ligne."
        )


def test_the_primitive_renders_the_five_invariants() -> None:
    from bretzel.components.base._wiring import (
        change_emit_effect,
        hidden_carrier_attrs,
    )

    got = hidden_carrier_attrs("active", initial="a")
    assert got == {
        "type": "hidden",
        "bz-ref": "bzhidden",
        "value": "a",
        "bz-attr:value": "active",
        "bz-effect": change_emit_effect("active"),
    }
    # Et surtout : elle ne pose NI name NI required.
    for forbidden in ("name", "required"):
        assert forbidden not in got, (
            f"`hidden_carrier_attrs` ne doit PAS poser `{forbidden}` — "
            f"c'est la décision de l'appelant. Un `name` par défaut "
            f"injecterait un champ parasite dans tout formulaire "
            f"englobant un Tabs."
        )


def test_the_dispatcher_can_be_refused_or_redirected() -> None:
    """Les deux sorties de l'opt-out, et ce qu'elles valent.

    ``None`` sert les porteurs dont le dispatch vit dans le runtime ;
    l'expression sert ToggleGroup, dont la valeur POSTÉE et la valeur
    OBSERVÉE ne sont pas la même chose. Sans ce second cas, la primitive
    aurait câblé le dispatcher en dur et ToggleGroup aurait dû rester
    dehors — c'est-à-dire redevenir le prochain à l'oublier.
    """
    from bretzel.components.base._wiring import (
        change_emit_effect,
        hidden_carrier_attrs,
    )

    assert "bz-effect" not in hidden_carrier_attrs("v", dispatch=None)

    redirected = hidden_carrier_attrs("json(v)", dispatch="picked")
    assert redirected["bz-attr:value"] == "json(v)"
    assert redirected["bz-effect"] == change_emit_effect("picked"), (
        "`dispatch=<expr>` doit observer l'expression DONNÉE, pas celle "
        "de la valeur — sinon ToggleGroup dispatche sur la mauvaise."
    )


def test_the_form_bound_carriers_do_name_themselves() -> None:
    """Le contre-point : les composants qui DOIVENT nommer le font.

    Fige la correction d'une affirmation fausse de l'audit — il annonçait
    une FormData amputée sur ces cinq-là."""
    import re as _re

    from tests.consistency._discovery import (
        public_component_classes,
        rendered_html_of,
    )

    by_name = {c.__name__: c for c in public_component_classes()}
    for name in ("Accordion", "Tree", "Tabs", "Pagination", "ToggleGroup"):
        cls = by_name.get(name)
        if cls is None:
            continue
        html = rendered_html_of(cls)
        if html is None:
            continue
        hidden = _re.findall(r'<input[^>]*type="hidden"[^>]*>', html)
        for tag in hidden:
            assert "name=" in tag, (
                f"{name} émet un <input type=hidden> SANS name — la "
                f"FormData ne porterait pas la valeur.\n  {tag[:120]}"
            )

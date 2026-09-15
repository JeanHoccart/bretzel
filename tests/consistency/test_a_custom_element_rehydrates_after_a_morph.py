"""Gate — un custom element rendu par un composant sait se repeindre.

Le défaut qu'elle ferme (finding [25], mesuré le 2026-08-21)
------------------------------------------------------------
Un custom element est le seul nœud du catalogue dont le DOM interne
n'appartient PAS au serveur : le SSR émet une coquille, et le JS la
remplit au ``connectedCallback``. C'est un choix assumé — l'élément
survit à idiomorph « pour rien », ses attributs observés étant morphables
librement.

Ce que le choix ne disait pas, c'est que ça ne vaut **que pour les
attributs**. Sur un morph, idiomorph remet les ENFANTS à la version
serveur — donc à la coquille vide — et aucun callback ne se réveille :

- ``connectedCallback`` ne re-tourne pas, le nœud a survécu ;
- ``attributeChangedCallback`` non plus, rien n'a changé ;
- ``bz-init`` non plus, il est **one-shot par nœud** (``_bzInitDone``,
  qui survit explicitement au rebind).

Résultat mesuré sur ``ui.calendar`` dans une zone ``@refreshable`` : 42
cellules au premier rendu, **0** après un refresh, définitivement. Le
symptôme rapporté était « cliquer sur une date fait planter le composant
des dates ».

Ce que la gate exige
---------------------
Que tout custom element émis par un composant porte un ``bz-effect`` —
le SEUL hook du framework qui re-tourne à chaque rescan, parce que
``bindEl`` le dispose et le refait — et que la méthode qu'il nomme
**existe vraiment dans le runtime**. Les deux moitiés comptent : un hook
qui appelle une méthode disparue est exactement aussi muet que pas de
hook, et la garde ``&&`` de l'expression le rendrait silencieux.

Ce qu'elle n'affirme pas
-------------------------
Que le repaint soit correct — ça, c'est
``tests/runtime_js/test_calendar_survives_its_zone_refresh.py``, qui fait
un vrai aller-retour HTTP et compte les cellules dans Chromium. Ici on
garde la classe : *un custom element sans personne pour le rehydrater*.

Pourquoi une gate pour UN élément
----------------------------------
Le catalogue n'en définit qu'un aujourd'hui (``<bz-calendar>``). La gate
n'est pas là pour lui — il est réparé — mais pour le **deuxième**, qui
héritera du même piège sans que rien ne le lui dise : il sera écrit à
partir de celui-ci, et le hook a l'air décoratif.
"""

from __future__ import annotations

import functools
import html as _html
import re

import pytest

from tests.consistency._discovery import (
    public_component_classes,
    rendered_html_of,
    runtime_slabs,
    strip_js_comments,
    ui_name_of,
)

#: Un custom element au sens du DOM : un tag avec un tiret. Le préfixe
#: ``bz-`` est celui du framework, et le tag qu'on cherche est CELUI DU
#: RENDU d'un composant — les balises de transport (``<bz-patch>``,
#: ``<bz-envelope>``) ne passent jamais par un ``render()``.
_CUSTOM_TAG = re.compile(r"<(bz-[a-z][a-z-]*)\b([^>]*)>")

#: L'appel que le hook doit faire : ``$el.<méthode> && $el.<méthode>()``.
_HOOK_CALL = re.compile(r"\$el\.(\w+)\s*&&\s*\$el\.\1\s*\(\s*\)")

#: Le plancher : le catalogue rend au moins un custom element. Sans lui,
#: un ``render`` qui cesserait d'en émettre laisserait la gate verte —
#: sur rien.
_TAGS_FLOOR = 1


@functools.cache
def custom_element_sites() -> tuple[tuple[str, str, str], ...]:
    """``(nom ui, tag, attributs bruts)`` de chaque custom element rendu.

    Découvert en rendant les composants publics, jamais listé : un
    deuxième custom element rejoint la population tout seul, et c'est
    précisément le cas que cette gate existe pour servir.
    """
    found: list[tuple[str, str, str]] = []
    for cls in public_component_classes():
        html = rendered_html_of(cls)
        if not html:
            continue
        for match in _CUSTOM_TAG.finditer(html):
            # DÉSÉCHAPPÉ : le sérialiseur écrit `&amp;&amp;`, et un
            # détecteur qui chercherait `&&` dans le HTML brut ne
            # trouverait JAMAIS le hook — vert sur rien.
            found.append((
                ui_name_of(cls),
                match.group(1),
                _html.unescape(match.group(2)),
            ))
    return tuple(found)


@functools.cache
def _runtime_code() -> str:
    return "\n".join(
        strip_js_comments(path.read_text(encoding="utf8"))
        for path in runtime_slabs()
    )


def test_the_sweep_finds_custom_elements() -> None:
    sites = custom_element_sites()
    tags = {tag for _, tag, _ in sites}
    assert len(tags) >= _TAGS_FLOOR, (
        "aucun custom element trouvé dans le rendu des composants "
        "publics (`<bz-calendar>` en était un le 2026-08-21). Soit ils "
        "ont disparu, soit le motif ne les reconnaît plus — et la gate "
        "ne garde alors plus rien."
    )


@pytest.mark.parametrize(
    "site", custom_element_sites(), ids=lambda s: f"{s[0]}:{s[1]}"
)
def test_a_custom_element_carries_a_rehydration_hook(
    site: tuple[str, str, str],
) -> None:
    name, tag, attrs = site
    assert _HOOK_CALL.search(attrs), (
        f"ui.{name} rend un <{tag}> SANS hook de re-hydratation.\n"
        f"  Un morph remet les enfants d'un custom element à la version "
        f"serveur — c'est-à-dire à la coquille vide que le SSR émet — et "
        f"AUCUN callback ne se réveille : le nœud a survécu, aucun "
        f"attribut n'a changé, et `bz-init` est one-shot par nœud.\n"
        f"  Pose `bz-effect=\"$el.<méthode> && $el.<méthode>()\"` sur la "
        f"racine : `bz-effect` est le seul hook que `bindEl` refait à "
        f"chaque rescan. La méthode doit être idempotente — ne repeindre "
        f"que si le corps a vraiment été effacé."
    )


@pytest.mark.parametrize(
    "site", custom_element_sites(), ids=lambda s: f"{s[0]}:{s[1]}"
)
def test_the_hook_names_a_method_the_runtime_defines(
    site: tuple[str, str, str],
) -> None:
    """L'autre moitié : la garde ``&&`` rend un nom mort SILENCIEUX.

    ``$el.rehydrate && $el.rehydrate()`` sur un élément qui n'a plus de
    ``rehydrate`` ne lève pas, ne prévient pas, et ne fait rien — la
    panne d'origine, avec un hook qui a l'air branché.
    """
    name, tag, attrs = site
    match = _HOOK_CALL.search(attrs)
    if not match:
        pytest.skip("pas de hook — c'est l'autre test qui le dit")
    method = match.group(1)
    assert re.search(rf"\b{re.escape(method)}\s*\(", _runtime_code()), (
        f"ui.{name} appelle `$el.{method}()` sur son <{tag}>, mais aucun "
        f"slab de `bretzel/runtime/_src/` ne définit ce nom (commentaires "
        f"retirés). La garde `&&` avale l'absence en silence : le hook a "
        f"l'air branché et ne fait rien."
    )


def test_the_detector_still_bites() -> None:
    """Trois cas fabriqués — le vrai hook, l'absence, et le faux ami."""
    assert _HOOK_CALL.search(' bz-effect="$el.rehydrate && $el.rehydrate()"'), (
        "le détecteur ne reconnaît plus la forme réelle du hook."
    )
    assert not _HOOK_CALL.search(' mode="picker" weekstart="1"')
    # Le faux ami : un ``bz-effect`` qui existe mais n'appelle rien sur
    # ``$el`` — la forme qu'aurait un effet de miroir ou de calcul.
    assert not _HOOK_CALL.search(' bz-effect="year = $event.detail.year"'), (
        "le détecteur accepte un `bz-effect` qui ne rehydrate rien — il "
        "vérifie la présence d'un effet au lieu de ce qu'il appelle."
    )


def test_the_runtime_reader_is_not_blind() -> None:
    """Le contrôle positif du second bras : il TROUVE une méthode réelle."""
    code = _runtime_code()
    assert re.search(r"\brehydrate\s*\(", code), (
        "`rehydrate` n'est plus défini nulle part dans `_src/` — soit le "
        "hook du calendrier est mort, soit le lecteur l'est."
    )
    assert not re.search(r"\bmethodeQuiNExistePas\s*\(", code)

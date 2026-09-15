"""Les sélecteurs de l'audit visent encore quelque chose.

Le fait gardé
--------------
``tests/audit/checklist.py`` décrit chaque composant à auditer par un
``root_selector`` — souvent un crochet sur son littéral de scope,
``div[bz-data*='…']``. Ces sélecteurs sont écrits à la main, dans un
fichier que personne n'ouvre en refactorant un composant.

Quand le composant change de scope, le sélecteur ne matche plus rien.
Et l'audit ne dit **pas** « je ne trouve pas » : ses sondes disent « pas
de swatch après le titre size », « le preview n'a pas été trouvé dans la
carte Client » — c'est-à-dire qu'elles accusent le COMPOSANT d'un défaut
qui n'existe pas. Un audit qui tourne 42 s par composant devient une
liste de faux coupables.

Mesuré le 2026-08-28 : deux sélecteurs sur six étaient morts.
``accordion`` cherchait ``isOpen`` et ``tabs`` cherchait ``setTab`` —
deux méthodes qui ont quitté chaque instance pour vivre une seule fois
dans ``$bz.accordion.*`` / ``$bz.tabs.scope``. Le commentaire du
checklist expliquait même pourquoi ``isOpen`` avait été choisi : « unique
à la racine de l'accordéon ». Il l'était, jusqu'au refactor. Quatre
rouges d'audit, deux composants, zéro bug.

Pourquoi ici et pas dans l'audit
---------------------------------
L'audit coûte 15 à 30 minutes et un navigateur par composant, donc il ne
tourne pas souvent — c'est précisément ce qui laisse un sélecteur mort
vivre des semaines. Cette gate pose la même question en quelques
secondes et **sans navigateur** : le HTML servi suffit à savoir si un
crochet a encore une prise.

Ce que la gate n'affirme PAS
-----------------------------
Que le sélecteur vise le BON élément — ``div[bz-data*='$bz.tabs.scope']``
matcherait encore si le scope des tabs migrait sur un autre composant.
Elle ferme la disparition pure, qui est la forme observée, pas la
confusion d'identité.

Elle ne regarde que les sélecteurs à crochet ``bz-data``. Les autres
(``.bz-datatable``, ``button``…) sont des classes de composant, gardées
par ailleurs et beaucoup plus stables.
"""

from __future__ import annotations

import html as _html
import re

from fastapi.testclient import TestClient

from tests.audit.checklist import all_specs

#: Preuve de morsure : le contrôle NÉGATIF vit dans
#: ``test_the_detector_still_bites``.
MUTATION_PROOF = "test_the_detector_still_bites"

#: ``[<attribut>*='fragment']`` — n'importe quel crochet de
#: sous-chaîne, pas seulement ``bz-data``. La première version ne lisait
#: que celui-là, et elle a laissé passer ``[data-bz-float-root]`` du
#: popover : un attribut qui n'existait plus NULLE PART sur la page
#: (mesuré le 2026-08-28, zéro occurrence), donc une sonde sans cible et
#: un « preview introuvable » qui accusait le composant.
_HOOK = re.compile(r"""\[([a-z-]+)\*=['"]([^'"]+)['"]\]""")
#: Les sélecteurs d'ATTRIBUT nu — ``[data-bz-float-root]`` — n'ont pas de
#: fragment : on vérifie alors la seule présence de l'attribut.
_BARE_ATTR = re.compile(r"""\[([a-z][a-z0-9-]*)\](?!\s*\*=)""")


def hook_of(selector: str) -> tuple[str, str | None] | None:
    """``(attribut, fragment)`` cherché par ce sélecteur, ou ``None``.

    ``fragment`` vaut ``None`` pour un sélecteur d'attribut NU, où la
    question est « cet attribut existe-t-il encore ? ».

    Extrait plutôt qu'inline pour être MUTABLE : c'est ce détecteur que
    ``test_the_detector_still_bites`` nourrit de sélecteurs fabriqués.
    """
    match = _HOOK.search(selector or "")
    if match:
        return match.group(1), match.group(2)
    bare = _BARE_ATTR.search(selector or "")
    return (bare.group(1), None) if bare else None


def hook_matches(page_html: str, attr: str, needle: str | None) -> bool:
    """Ce crochet a-t-il encore une prise sur cette page ?

    ``needle=None`` pour un sélecteur d'ATTRIBUT NU : la question est
    alors « cet attribut existe-t-il encore ? », et un attribut sans
    valeur (``<div data-bz-overlay>``) compte.

    ``unescape`` d'abord : une valeur d'attribut traverse l'échappement
    HTML — ``&quot;`` pour les guillemets, ``&amp;`` pour l'esperluette —
    donc une recherche sur le texte brut raterait tout crochet qui en
    contient. (L'apostrophe, elle, n'est plus échappée depuis le
    2026-08-28 ; ``unescape`` la laisse passer sans rien faire.)
    """
    values = re.findall(rf'{re.escape(attr)}="([^"]*)"', page_html)
    if needle is None:
        return bool(values) or f"{attr}>" in page_html or f"{attr} " in page_html
    return any(needle in _html.unescape(value) for value in values)


def _hooked_specs() -> list[tuple[str, str, str, str | None]]:
    """``(composant, route, attribut, fragment)`` par sélecteur à crochet."""
    out = []
    for spec in all_specs():
        hook = hook_of(getattr(spec, "root_selector", "") or "")
        if hook is not None:
            out.append((spec.name, spec.route, hook[0], hook[1]))
    return out


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher ancré sur la DÉCOUVERTE : des crochets sont trouvés.

    Si le checklist cessait d'utiliser cette forme — ou si l'expression
    régulière cessait de la reconnaître — la gate passerait au vert en
    ne vérifiant rien. C'est le détecteur qu'on ancre, pas la population.
    """
    hooked = _hooked_specs()
    assert len(hooked) >= 4, (
        f"seulement {len(hooked)} sélecteur(s) à crochet ``bz-data`` trouvé(s) "
        f"dans le checklist (>= 4 attendus, 6 le 2026-08-28). Soit la "
        f"convention a changé, soit ``hook_of`` ne la reconnaît plus — dans "
        f"les deux cas cette gate ne garde plus rien."
    )


def test_every_audit_hook_still_matches() -> None:
    from examples.playground.main import app

    dead: list[str] = []
    with TestClient(app) as client:
        pages: dict[str, str] = {}
        for name, route, attr, needle in _hooked_specs():
            if route not in pages:
                pages[route] = client.get(route).text
            if not hook_matches(pages[route], attr, needle):
                looked = f"{attr}*={needle!r}" if needle else attr
                dead.append(f"{name} ({route}) cherche {looked}")

    assert not dead, (
        "Des sélecteurs de l'audit ne visent plus rien :\n  "
        + "\n  ".join(dead)
        + "\n\nL'audit ne dira pas « introuvable » : ses sondes accuseront "
        "le COMPOSANT (« pas de swatch après le titre size », « preview "
        "non trouvé »). Répare le sélecteur — le littéral de scope actuel "
        "se lit dans le ``bz-data`` de la racine rendue."
    )


def test_the_detector_still_bites() -> None:
    """Les deux versants, sur des sources FABRIQUÉES."""
    # ── Le lecteur de sélecteur ───────────────────────────────────────
    assert hook_of("div[bz-data*='$bz.tabs.scope']") == ("bz-data", "$bz.tabs.scope")
    assert hook_of('div[bz-data*="isOpen"]') == ("bz-data", "isOpen")
    # Le sélecteur d'ATTRIBUT NU — la forme qui a échappé à la première
    # version, et qui a coûté un rouge de plus (``data-bz-float-root``
    # du popover, disparu sans que rien ne le dise).
    assert hook_of("[data-bz-float-root]") == ("data-bz-float-root", None)
    assert hook_of(".bz-datatable") is None, (
        "un sélecteur de CLASSE est pris pour un crochet, donc la gate "
        "exigerait qu'il apparaisse dans un attribut"
    )

    # ── Versant ILLICITE : les crochets morts sont vus ────────────────
    page = '<div bz-data="{...$bz.tabs.scope,active: 1}"></div>'
    assert not hook_matches(page, "bz-data", "setTab")
    assert not hook_matches(page, "data-bz-float-root", None)

    # ── Versant LICITE : et les vivants passent ───────────────────────
    assert hook_matches(page, "bz-data", "$bz.tabs.scope")
    assert hook_matches('<div data-bz-overlay></div>', "data-bz-overlay", None), (
        "un attribut SANS valeur est déclaré mort — or c'est une forme "
        "courante, et la gate rougirait sur un checklist juste"
    )

    # ── Le versant qui compte : l'ÉCHAPPEMENT HTML ────────────────────
    # Une valeur d'attribut voyage échappée. Sans ``unescape``, tout
    # crochet portant un guillemet serait déclaré mort.
    escaped = '<div bz-data="{...$bz.accordion.single,expanded: &quot;a&quot;}"></div>'
    assert hook_matches(escaped, "bz-data", "$bz.accordion.")
    assert hook_matches(escaped, "bz-data", 'expanded: "a"')

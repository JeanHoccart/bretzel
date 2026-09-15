"""Gate : ce que ``Theme`` déclare atteint la feuille servie, et en dernier.

Le problème que cette gate ferme
--------------------------------

``Theme(fonts=…)`` et ``Theme(css=…)`` sont les deux seules sections dont
la valeur ne se *voit* nulle part avant le navigateur. Une couleur ratée
saute aux yeux ; une fonte qui n'arrive pas laisse la pile système, qui
est exactement ce à quoi ressemble une page qui n'a jamais eu de fonte.
Le mode de défaillance est donc « rien ne change », c'est-à-dire le pire
de tous — celui qu'on attribue à son propre `@font-face`, à son cache
navigateur, à tout sauf au framework.

Trois chemins mènent à ce silence, tous déjà empruntés par ce dépôt sous
d'autres formes :

1. **Une section qu'on oublie de faire suivre.**
   ``generate_theme_css_full`` reçoit ses entrées en paramètres nommés et
   les recompose ; ajouter une section au-dessus sans threader ``fonts``
   ou ``extra_css`` les laisse tomber sans que rien ne casse. C'est le
   pendant exact de ``generate_envelope_dict`` (retirée le 2026-08-01),
   dont la moitié ``icons`` était calculée puis jetée parce que le
   pipeline n'extrayait que ``palette``.

2. **``extra_css`` qui cesse d'être la DERNIÈRE section.**
   Toute la valeur de la porte est là : à spécificité égale, l'ordre de
   la feuille tranche. Mesuré le 2026-08-16 sur ``classes=`` —
   ``bg-black`` perd contre le ``bg-surface`` d'un thème parce que
   Tailwind ordonne ses utilitaires lui-même. Une échappatoire qui perd
   contre ce qu'elle vient corriger n'échappe à rien, et elle perd en
   silence.

3. **L'empreinte qui cesse de les voir.**
   ``build.get_or_build_css`` ne recompile que si le sha256 du
   ``theme_css`` a changé. Si les fontes n'entrent pas dans la chaîne
   empreintée, changer de fonte sert le ``style.css`` d'avant, pour
   toujours. Ce bug a déjà eu lieu ici en grand : le cache était validé
   sur la seule EXISTENCE du fichier, donc plus rien ne se reconstruisait
   après le premier build (cf. le commentaire de ``get_or_build_css``).

4. **Les deux réécritures du chemin DEV.** En ``css="browser"``, la
   feuille ne part pas en ``<link>`` : elle est inlinée dans un
   ``<style type="text/tailwindcss">`` après être passée par
   ``strip_safelist`` puis ``_strip_tailwind_import`` — deux regex qui
   opèrent désormais sur une chaîne contenant du CSS utilisateur
   arbitraire. Une régression y serait invisible en prod et casserait
   uniquement le mode dans lequel on développe. D'où un aller-retour HTTP
   réel plutôt qu'un appel aux fonctions : le harnais doit copier le
   timing du rendu, sinon il ne prouve pas ce qu'il croit.

Ce que la gate n'est pas
------------------------

Ce n'est pas une interdiction balayant une population — donc pas de
plancher de non-vacuité à déclarer : chaque test construit son propre
sujet et affirme une présence. Si la construction cassait, les tests
rougiraient au lieu de se vider — à condition qu'aucun ``Theme`` ne soit
construit à la COLLECTE (un ``parametrize`` qui instancie ferait
disparaître le module entier sur une erreur de construction, ce qui est
exactement la forme qu'on prétend exclure). D'où des kwargs paramétrés,
jamais des objets.

Elle ne prouve pas que la fonte s'AFFICHE : ça, seul un navigateur avec
le fichier ``.woff2`` le dit. Elle prouve que la déclaration traverse la
couche Python jusqu'à la chaîne compilable et jusqu'au document servi.

⚠️ Elle ne dit **rien** des sections voisines. ``semantic``, ``palette``
et ``components`` avalent toujours une clé inconnue en silence (mesuré le
2026-08-16 : ``Theme(semantic={"primry": …})`` est accepté, la clé est
filtrée par compréhension dans ``palette.py`` et n'atteint aucun CSS).
Ne pas lire le vert d'ici comme « la couche thème valide ses entrées » :
seule ``fonts`` est fermée.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, page, ui
from bretzel.theme import Theme, ThemeError
from bretzel.theme.build import _theme_digest
from bretzel.theme.tokens import FONT_SLOT_NAMES

#: Preuve de morsure : contrôle NÉGATIF — un slot de fonte inconnu doit LEVER au lieu de
#: disparaître, ce qui prouve que le vocabulaire est bien lu.
MUTATION_PROOF = "test_unknown_font_slot_raises_instead_of_vanishing"

_FAMILY = "Inter, ui-sans-serif, system-ui, sans-serif"
_RULE = "@keyframes bz-gate-probe{50%{opacity:.4}}"

#: Un thème qui porte TOUTES les autres sections. Le scrollbar est la seule
#: section conditionnelle de l'assembleur et il s'ajoute après le corps :
#: c'est la forme de code qui laisse une section suivante s'insérer au
#: mauvais endroit, donc l'ordre se vérifie aussi sur ce cas-là.
_FULL_KWARGS: dict[str, Any] = {
    "semantic": {"primary": "#123456"},
    "fonts": {"mono": "JetBrains Mono, monospace"},
    "components": {"card": {"slots": {"root": "block w-full"}}},
    "scrollbar": {"width": "9px"},
    "css": _RULE,
}


def test_every_font_slot_reaches_the_theme_block() -> None:
    """Les trois slots, pas seulement celui qu'on utilise en démo.

    Itérer sur ``FONT_SLOT_NAMES`` plutôt que d'écrire trois assertions :
    un quatrième slot ajouté un jour arrive ici sans qu'on y pense, et
    l'oubli de son émission rougit tout de suite.
    """
    theme = Theme(fonts={slot: f"Probe{slot}, sans-serif" for slot in FONT_SLOT_NAMES})
    css = theme.generate_css()

    for slot in FONT_SLOT_NAMES:
        token = f"--font-{slot}: Probe{slot}, sans-serif;"
        assert token in css, (
            f"slot `{slot}` déclaré mais absent du CSS de thème. "
            f"Vérifie que `generate_theme_css_full` fait suivre `fonts=` "
            f"jusqu'à `generate_theme_css`."
        )


def test_font_token_lands_inside_the_theme_block() -> None:
    """Dans ``@theme {}``, pas à côté.

    Hors du bloc, la custom property existerait toujours — mais Tailwind
    ne la lirait pas, donc ni l'utilitaire ``font-sans`` ni le
    ``--default-font-family`` du preflight ne suivraient. Le CSS serait
    valide et la page inchangée : le silence, encore.
    """
    css = Theme(fonts={"sans": _FAMILY}).generate_css()

    start = css.index("@theme {")
    end = css.index("}", start)
    assert "--font-sans:" in css[start:end], (
        "`--font-sans` est émis hors du bloc `@theme {}` — Tailwind ne le "
        "lira pas et la page gardera la pile système."
    )


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("thème nu", {"css": _RULE}),
        ("toutes sections", _FULL_KWARGS),
    ],
)
def test_app_css_is_the_last_section(label: str, kwargs: dict[str, Any]) -> None:
    """La porte de sortie a le dernier mot, littéralement.

    On compare des POSITIONS et non un ``endswith`` : une section ajoutée
    après elle un jour (une règle de debug, un reset) passerait un
    ``endswith`` assoupli, pas cette comparaison.
    """
    css = Theme(**kwargs).generate_css()

    assert _RULE in css, f"[{label}] `Theme(css=…)` n'atteint pas le CSS."
    where = css.index(_RULE)
    for section in ("@theme {", "@import", "::selection", "scrollbar"):
        if section in css:
            assert css.index(section) < where, (
                f"[{label}] `{section}` est émis APRÈS `Theme(css=…)`. La "
                f"porte de sortie doit rester la dernière section, sinon "
                f"l'app perd la cascade à spécificité égale contre le "
                f"framework."
            )


def test_base_theme_css_is_inherited_not_dropped() -> None:
    """Hériter d'un thème ne doit pas amputer sa moitié CSS.

    Le cas réel : une marque déclare ``fonts`` ET le ``@font-face`` qui
    rend la fonte chargeable. Un thème dérivé qui ajoute trois règles
    gardait le token (les sections dict se mergent) et perdait le
    ``@font-face`` — donc la pile système, sans un mot. C'est la forme
    même de silence que cette section existe pour fermer, et elle était
    née avec.
    """
    brand = Theme(fonts={"sans": _FAMILY}, css="@font-face{font-family:Probe}")
    child = Theme(base=brand, css=".child{color:red}")
    css = child.generate_css()

    assert "@font-face{font-family:Probe}" in css, (
        "le CSS de la base a disparu quand l'enfant a déclaré le sien — "
        "asymétrie avec `fonts`, qui lui est bien hérité."
    )
    assert ".child{color:red}" in css
    assert css.index("@font-face") < css.index(".child"), (
        "le morceau de l'enfant doit venir APRÈS celui de la base, sinon "
        "il ne peut plus rien surcharger."
    )
    assert ".child" not in Theme(base=brand, css="").generate_css(), (
        "`css=\"\"` doit remettre la section à zéro — c'est la seule "
        "sortie explicite, comme `scrollbar=None`."
    )


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        ("fonte", {"fonts": {"sans": _FAMILY}}),
        ("css", {"css": _RULE}),
    ],
)
def test_digest_sees_the_declaration(label: str, kwargs: dict[str, Any]) -> None:
    """Changer de fonte doit invalider le ``style.css`` en cache.

    On empreinte par la fonction que ``get_or_build_css`` utilise
    réellement, pas par une recopie : une gate qui recalcule depuis sa
    propre source reste verte quand le mécanisme se débranche (cf.
    ``test_prohibition_gates_declare_a_floor`` et la mémoire
    « un plancher doit lire la source de LA gate »).
    """
    baseline = _theme_digest(Theme().generate_css())
    changed = _theme_digest(Theme(**kwargs).generate_css())

    assert baseline != changed, (
        f"un thème qui ne diffère que par sa {label} produit la MÊME "
        f"empreinte : `.bretzel/style.css` ne sera jamais recompilé et "
        f"l'app servira le CSS d'avant, indéfiniment."
    )


def test_unknown_font_slot_raises_instead_of_vanishing() -> None:
    """Le mode de défaillance refusé, énoncé comme test.

    C'est la raison d'être de la section : la couche thème acceptait
    jusqu'ici un composant inconnu, un slot mal orthographié et une
    variante inexistante sans rien dire (mesuré le 2026-08-16). Celle-ci
    naît fermée.
    """
    with pytest.raises(ThemeError, match="slot"):
        Theme(fonts={"body": _FAMILY})

    with pytest.raises(ThemeError):
        Theme(fonts={"sans": "   "})


def test_declaration_survives_the_dev_inlining() -> None:
    """Le chemin DEV, par un vrai aller-retour HTTP.

    En ``css="browser"`` la feuille n'est pas servie en ``<link>`` : elle
    traverse ``strip_safelist`` puis ``_strip_tailwind_import`` — deux
    substitutions par regex — avant d'être inlinée dans la page. Les trois
    tests d'au-dessus s'arrêtent à ``generate_css()`` et ne verraient rien
    si l'une des deux se mettait à mordre sur du CSS utilisateur.

    L'aller-retour est monté plutôt que simulé parce qu'un appel direct aux
    deux fonctions ne prouverait que ce qu'on aurait pensé à appeler, dans
    l'ordre qu'on aurait supposé — c'est le harnais qui doit copier le
    timing du rendu, pas l'inverse.
    """

    @page("/")
    def _home() -> None:
        ui.text("gate")

    theme = Theme(
        fonts={"sans": "ProbeSans, sans-serif"},
        css="@font-face{font-family:ProbeSans;src:url('/static/p.woff2')}",
    )
    app = Bretzel(secret_key="gate-secret-key-1234567890", mode="dev", theme=theme)
    app.include(_home)

    with TestClient(app) as client:
        html = client.get("/").text

    assert 'type="text/tailwindcss"' in html, (
        "le mode dev ne passe plus par le compilateur navigateur — ce test "
        "ne vérifie plus le chemin qu'il prétend couvrir."
    )
    assert "--font-sans: ProbeSans, sans-serif;" in html, (
        "le token de fonte n'atteint pas la page en dev : une des deux "
        "réécritures de la feuille inline l'a mangé."
    )
    assert "@font-face{font-family:ProbeSans" in html, (
        "`Theme(css=…)` n'atteint pas la page en dev — la fonte serait "
        "déclarée mais jamais chargeable, et uniquement dans le mode où "
        "on développe."
    )

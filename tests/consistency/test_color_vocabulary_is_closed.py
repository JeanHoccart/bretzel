"""Ce que la safelist développe est exactement ce que le rendu accepte.

Le bug que cette gate ferme, mesuré le 2026-08-18 sur
``ui.badge(color="neutral")`` :

- ça **se construit** — aucune validation sur ``color=`` ;
- ça **se rend** — la classe sort dans le HTML ;
- ``bretzel check`` répond « aucun constat » — sa règle
  ``value-outside-the-table`` lit les tables du THÈME (``variants``,
  ``sizes``), or ``color`` n'a pas de table par composant : il puise
  dans la palette. La règle n'a rien à comparer ;
- et l'élément sort **sans style en production**.

Pourquoi la production seulement
--------------------------------

⚠️ **Le mécanisme a changé le 2026-08-30, le mode d'échec non.** Le thème
écrivait ``bg-{bg_color}/15`` : le trou n'était comblé qu'au rendu, donc
la classe finale ``bg-neutral/15`` n'apparaissait **littéralement dans
aucune source**. Aujourd'hui le thème écrit ``bg-(--bz-bg)``, une classe
complète — mais ``bz-c-neutral`` est une classe **sans règle**, donc les
douze paliers sont indéfinis, donc toute déclaration qui les lit est
invalide. Le composant rend nu.

Dans les deux cas : le compilateur de PROD ne génère que ce qu'il trouve
écrit dans les sources, le mode DEV compile depuis le DOM **vivant**.

D'où la forme du bug : **correct en dev, mort en prod, HTML identique des
deux côtés, aucune erreur**. Invisible avant déploiement — c'est la
classe de défaut la plus coûteuse de ce dépôt (memory
``assembled_tailwind_class_dev_only``).

Le correctif, et ce que cette gate protège
------------------------------------------

Deux endroits savaient ce qu'est une couleur valide, et ne se parlaient
pas : le générateur de safelist (qui décide quelles classes **existent**
en CSS) et le rendu (qui décidait n'importe quoi). Ils lisent désormais
la même chose :

- les couleurs de la palette — dynamiques, une app peut en ajouter via
  ``Theme(palette={...})``, donc aucune liste statique ne convient ;
- plus :data:`~bretzel.theme.slots.COLOR_KEYWORDS`, l'ensemble FERMÉ des
  noms qui ne sont pas des couleurs de palette mais de vraies couleurs
  CSS (aujourd'hui ``current`` → ``currentColor``).

Tout le reste **lève**. La propriété gardée ici est l'égalité des deux
ensembles : une couleur que la safelist ne développe pas ne peut pas être
émise, et une couleur émissible est forcément développée.

Ce que la mesure a dit avant de fermer
--------------------------------------

2 495 appels ``color="…"`` littéraux dans ``bretzel/`` et ``examples/``,
**2 495 dans le vocabulaire**. Fermer était donc gratuit : aucun site
d'appel existant ne casse. C'est ``test_no_call_site_is_outside`` qui
re-mesure ça à chaque run — le jour où quelqu'un écrit une couleur
inventée, il l'apprend ici et pas en production.
"""

from __future__ import annotations

import ast

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.theme import SEMANTIC_COLOR_NAMES, Theme
from bretzel.components.base._wiring import _refuse_unknown_color
from bretzel.theme.slots import COLOR_KEYWORDS
from tests.consistency._discovery import (
    render_isolated,
    EXAMPLES_FLOOR,
    PACKAGE_FLOOR,
    REPO_ROOT,
    parsed_sources,
)

#: Preuve de morsure : contre-cas — une couleur hors vocabulaire doit LEVER, ce qui prouve
#: que le vocabulaire ferme est bien consulte a la resolution.
MUTATION_PROOF = "test_anything_else_raises"


def _palette():
    return Theme().get_palette()


class _Probe:
    """Un composant de façade — ``_refuse_unknown_color`` n'en lit que le
    nom de classe, pour le message d'erreur."""


def _refuse(color: str) -> None:
    _refuse_unknown_color(_Probe(), color)


def test_a_keyword_is_accepted() -> None:
    """Un mot-clé passe, et c'est correct : ``bz-c-current`` fait partir
    ``--bz-text`` de ``currentColor``. Sept composants en dépendent, dont
    toute la barre du datatable — et c'est le DÉFAUT d'``ui.icon``."""
    with render_isolated(theme=Theme()):
        for keyword in COLOR_KEYWORDS:
            _refuse(keyword)          # ne lève pas


def test_a_palette_color_is_accepted() -> None:
    """Le cas nominal — et le cas DYNAMIQUE : une couleur de marque
    déclarée par l'app doit passer, sinon la fermeture casserait tout
    thème personnalisé."""
    with render_isolated(theme=Theme()):
        _refuse("primary")

    with render_isolated(theme=Theme(palette={"zzbrand": "#ff00aa"})):
        _refuse("zzbrand")


def test_anything_else_raises() -> None:
    """Le cœur de la gate. Sans cette levée, la classe part dans le HTML
    et meurt en silence à la compilation de prod.

    ⚠️ Le refus a DÉMÉNAGÉ le 2026-08-30 : il vivait dans
    ``resolve_slot_or_keyword``, déposé avec le mécanisme de gabarits. Il
    est maintenant dans ``_wiring.color_bridge_class``, à l'endroit où le
    nom de couleur est consommé — c'est-à-dire là où le pont se pose. La
    règle est la même, et le mode d'échec qu'elle ferme aussi.
    """
    with render_isolated(theme=Theme()):
        with pytest.raises(ComponentUsageError) as exc:
            _refuse("zznotacolor")

    msg = str(exc.value)
    assert "zznotacolor" in msg, "le message doit nommer la fautive"
    assert "primary" in msg, "et lister ce qui est accepté"
    assert "prod" in msg.lower(), (
        "et dire la CONSÉQUENCE — sans elle, l'auteur lit « couleur "
        "inconnue » comme un détail cosmétique alors que c'est une "
        "feature morte en production."
    )


def test_it_stays_quiet_without_a_render_context() -> None:
    """Hors contexte on ne peut pas lire la palette : se taire plutôt que
    refuser à tort.

    Sans ce repli, tout banc qui construit un composant nu — et il y en a
    dans quatre gates — lèverait sur des couleurs parfaitement valides.
    """
    _refuse("zznotacolor")            # aucun contexte : silence


def test_the_bridges_and_the_renderer_read_the_same_keywords() -> None:
    """La propriété entière de ce chantier, en un test.

    Le générateur de PONTS itère les couleurs de la palette **plus**
    ``COLOR_KEYWORDS``. Si quelqu'un remettait un littéral à cet
    endroit-là — ce qu'il y avait avant (``"current"`` écrit en dur) —
    les deux ensembles pourraient diverger : un pont existerait pour un
    nom que le rendu refuse, ou le rendu accepterait un nom sans pont, et
    le composant rendrait nu.

    ⚠️ Ce test lisait ``theme/tailwind.py`` jusqu'au 2026-08-30, quand la
    safelist développait les couleurs. Elle ne développe plus rien : ce
    sont les ponts qui portent la fermeture.
    """
    src = (REPO_ROOT / "bretzel" / "theme" / "bridges.py").read_text(
        encoding="utf-8"
    )
    assert "CURRENT_COLOR_NAME" in src, (
        "le générateur de ponts ne nomme plus le mot-clé — s'il recopie "
        "la liste, elle peut diverger de celle que le rendu accepte, et "
        "une couleur redevient acceptable sans pont."
    )


def _literal_color_calls() -> list[tuple[str, int, str]]:
    """Tous les ``color="…"`` littéraux du dépôt, avec leur site."""
    out: list[tuple[str, int, str]] = []
    for root, floor in (
        (REPO_ROOT / "bretzel", PACKAGE_FLOOR),
        (REPO_ROOT / "examples", EXAMPLES_FLOOR),
    ):
        for src in parsed_sources(root, floor=floor):
            for node in ast.walk(src.tree):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg != "color":
                        continue
                    if not isinstance(kw.value, ast.Constant):
                        continue
                    if isinstance(kw.value.value, str):
                        rel = src.path.relative_to(REPO_ROOT)
                        out.append((str(rel), node.lineno, kw.value.value))
    return out


def test_no_call_site_is_outside_the_vocabulary() -> None:
    """Aucun ``color="…"`` du dépôt n'est hors vocabulaire.

    Mesuré à la fermeture : 2 495 appels, 2 495 dedans — c'est ce qui a
    rendu la levée gratuite. Ce test garde la propriété, et surtout il
    fait apprendre la faute ICI plutôt qu'en production.

    ⚠️ Le vocabulaire de référence est celui du thème par DÉFAUT. Une app
    qui déclare une couleur de marque dans son propre ``Theme(palette=…)``
    la verrait signalée ici à tort — si ça arrive, la bonne réponse est
    d'élargir ce test à la palette de l'app concernée, PAS de le
    supprimer.
    """
    palette = _palette()
    known = {*SEMANTIC_COLOR_NAMES, *COLOR_KEYWORDS}
    known |= set(palette.envelope_dict())

    offenders = [
        (f, n, v) for f, n, v in _literal_color_calls() if v not in known
    ]
    assert not offenders, (
        "Des appels utilisent une couleur hors vocabulaire. Leur classe "
        "est assemblée au rendu, donc absente du CSS compilé : correct en "
        "dev, SANS STYLE en prod.\n  "
        + "\n  ".join(f"{f}:{n}  color={v!r}" for f, n, v in offenders[:20])
    )


def test_the_call_site_sweep_is_not_vacuous() -> None:
    """Le plancher de ``test_no_call_site_is_outside_the_vocabulary``.

    Cette gate affirme « zéro contrevenant » — et elle l'affirmerait tout
    aussi bien si le balayage AST ne trouvait plus aucun appel (mot-clé
    renommé, racine déplacée, parse cassé). Verte, sur rien.

    2 495 appels ``color="…"`` littéraux mesurés le 2026-08-18 dans
    ``bretzel/`` + ``examples/``. Le seuil laisse de la marge pour une
    réorganisation sans laisser passer un balayage amputé.
    """
    calls = _literal_color_calls()
    assert len(calls) >= 1500, (
        f"le balayage ne trouve plus que {len(calls)} appels ``color=`` "
        f"(2 495 mesurés le 2026-08-18) — vérifie-le avant de croire que "
        f"la gate passe. Ne baisse pas le plancher."
    )

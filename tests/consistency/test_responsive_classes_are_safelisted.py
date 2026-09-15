"""Gate : une classe préfixée par un breakpoint existe dans le CSS de prod.

Même classe de bug que ``test_emitted_classes_exist_in_source``, un cran
plus loin — et c'est ce cran qui manquait.

Un prop **gradué** prend un dict de breakpoints
(``gap={"base": "sm", "md": "lg"}``) et :func:`responsive_classes` ressort
``gap-2 md:gap-6``. Le token ``gap-6`` existe littéralement dans le thème,
donc le scanner le voit ; ``md:gap-6``, lui, n'existe **nulle part** — il
n'est assemblé qu'au render. En dev ça marche (le compilateur navigateur
scanne le DOM vivant), en prod la règle n'est jamais générée. Le HTML est
identique des deux côtés : seule la feuille diffère.

Mesuré le 2026-08-08, avant correctif ::

    ui.flex(direction={'base':'col','md':'row'})  → md:flex-row   ABSENT
    ui.grid(gap={'base':'sm','md':'lg'})          → md:gap-6      ABSENT
    ui.carousel(per_view={'base':1,'lg':3})       → lg:hidden     ABSENT

Autrement dit ``direction=`` gradué — la feature entière du commit
096ecbba — ne changeait pas d'axe en mode compilé.

**Pourquoi la gate d'à côté ne l'a pas vu.**
``test_emitted_classes_exist_in_source`` balaie les pages du playground,
et aucune n'utilise un ``gap=`` / ``direction=`` responsive. Pire :
``md:hidden`` y passait, parce que la chaîne apparaît par hasard dans une
**docstring** de ``carousel.py``. Une gate qui dépend de ce qu'une page de
démo se trouve exercer n'est pas une clôture — d'où celle-ci, qui
DÉCOUVRE les props gradués au lieu d'attendre qu'on les mette en vitrine.

**La découverte.** Un prop gradué se reconnaît à ce qu'il accepte un dict
sans lever : les non-gradués passent par ``reject_responsive``. On teste
donc chaque prop réactif de chaque composant public avec un dict, et on
rend ceux qui l'acceptent. Aucune liste à tenir à jour : un futur prop
gradué est couvert le jour où il est écrit.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.theme import Theme
from bretzel.theme.tokens import BREAKPOINTS
from tests.consistency._discovery import (
    public_component_classes,
    tailwind_corpus,
)

#: Le préfixe de breakpoint dans une classe émise.
_PREFIXED = re.compile(rf"^(?:{'|'.join(BREAKPOINTS)}):")

#: Planchers de non-vacuité. Une gate d'interdiction verte sur zéro
#: échantillon est pire que pas de gate (cf.
#: ``test_prohibition_gates_declare_a_floor``). Au 2026-08-08 : trois
#: composants gradués (Flex + ses deux raccourcis VStack / HStack, Grid,
#: Carousel) pour cinq props (direction, gap ×3, cols, per_view).
_MIN_GRADED_PROPS = 5
_MIN_PREFIXED_CLASSES = 5

#: Le breakpoint de sonde. N'importe lequel ferait l'affaire — la
#: safelist clôture sur les cinq ou sur aucun.
_PROBE_BP = "md"


def _graded_probes() -> list[tuple[type, str, object]]:
    """``(classe, prop, valeur)`` pour chaque prop qui ACCEPTE un dict.

    La valeur du dict est le défaut du prop : on ne cherche pas à
    couvrir tout le domaine (les autres entrées de la table sont
    clôturées par construction, la safelist les prend en bloc), mais à
    exercer le CHEMIN de préfixage.
    """
    probes: list[tuple[type, str, object]] = []
    for cls in public_component_classes():
        for prop, descriptor in (
            getattr(cls, "__reactive_props__", None) or {}
        ).items():
            default = descriptor.default
            if default is None or isinstance(default, (dict, bool)):
                # ``None`` ne produit aucune classe (le resolve rend ""),
                # un dict n'est pas un scalaire, un bool n'est jamais gradué.
                continue
            probe = {"base": default, _PROBE_BP: default}
            try:
                with render_isolated():
                    serialize(cls(**{prop: probe}).render())
            except ComponentUsageError:
                continue  # reject_responsive : prop non gradué, attendu
            except Exception:
                # Le dict traverse la construction puis casse au render
                # (typiquement ``unhashable type: 'dict'`` sur un lookup
                # de table). C'est le cas que ``reject_responsive`` existe
                # pour transformer en message utile, et il n'est câblé que
                # sur Flex et Carousel — dette suivie dans
                # ``.claude/work/todo.md``.
                #
                # ⚠️ Ce n'est PAS un saut de confort : chacun de ces
                # couples sort de la population que la gate juge, et
                # ``_NOT_GRADED`` les nomme un par un pour qu'un nouveau
                # se voie (cf. ``test_the_abstentions_are_declared``).
                continue
            probes.append((cls, prop, probe))
    return probes


#: Les couples ``Classe.prop`` qui CASSENT au render sous un dict gradué,
#: figés au 2026-08-19. Une seule cause pour les 127 : ``reject_responsive``
#: n'est câblé que sur Flex et Carousel (cf. le fichier pour le détail).
_NOT_GRADED: frozenset[str] = frozenset(
    line.strip()
    for line in (
        pathlib.Path(__file__).with_name("_not_graded.txt")
    ).read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
)


def graded_abstentions() -> set[str]:
    """``Classe.prop`` pour ce qui casse au lieu d'être refusé proprement.

    ⚠️ **Deux corrections le 2026-09-04**, sans quoi la table restait
    peuplée de neuf noms qui n'avaient rien à y faire :

    1. la sonde construisait le composant NU (``cls(**{prop: probe})``),
       donc ``Datatable`` / ``Image`` / ``ToggleButton`` levaient sur un
       argument requis manquant et se lisaient comme « casse sous un
       dict ». On passe par ``bare_kwargs``, la table PARTAGÉE — c'est
       la règle de ``gates.md`` : on ne redevine jamais comment
       construire un composant ;
    2. un refus NOMMÉ n'est pas un défaut. ``Calendar(mode={...})``
       répond « not in ('picker', 'range', 'week', 'month') » et
       ``VStack(direction=…)`` répond « has a fixed axis » — les deux
       nomment le composant, le prop et la sortie. Les compter comme
       « casse » revenait à exiger UNE seule classe d'exception là où
       trois disent la bonne chose.
    """
    from bretzel.components.base.attrs import ComponentDefinitionError
    from tests.consistency._discovery import bare_kwargs, rendered_node_of

    #: Les refus qui DISENT quelque chose d'actionnable. ``TypeError``
    #: nu n'y est pas : c'est la forme que prend précisément l'accident
    #: qu'on traque (``unhashable type: 'dict'``).
    PROPRES = (ComponentUsageError, ComponentDefinitionError)

    out: set[str] = set()
    for cls in public_component_classes():
        # Un prop que la table FOURNIT déjà ne peut pas être sondé : le
        # passer une seconde fois lève « got multiple values », qui se
        # lirait comme « casse sous un dict ». Six composants — les
        # obligatoires (``Image.alt``, ``Iframe.title``, un libellé de
        # nav) — tombaient là-dedans.
        fournis = bare_kwargs(cls)
        # Un prop SCELLÉ ne se passe pas du tout — dict ou scalaire, il
        # lève. Le sonder ne mesure donc pas le sujet de cette gate
        # (``Radio.option_value`` / ``ToggleButton.option_value`` sont
        # alimentés par le ``value`` positionnel). La qualité de CE
        # refus-là est un item à part dans ``work/todo.md``.
        scelles = frozenset(getattr(cls, "SEALED_PROPS", ()) or ())
        for prop, descriptor in (
            getattr(cls, "__reactive_props__", None) or {}
        ).items():
            default = descriptor.default
            if default is None or isinstance(default, (dict, bool)):
                continue
            if prop in fournis or prop in scelles:
                continue
            probe = {"base": default, _PROBE_BP: default}
            try:
                # ``rendered_node_of`` porte la table PARTAGÉE
                # (``CONSTRUCT`` + ``_BARE_ARGS``) et le même protocole
                # ``(classe, prop, valeur)`` que cette sonde. ``None``
                # veut dire « la table déclare qu'il faut un contexte
                # qu'un banc ne peut pas fabriquer ».
                if rendered_node_of(cls, prop=prop, value=probe) is None:
                    continue
            except PROPRES:
                continue
            except TypeError as exc:
                if "multiple values" not in str(exc):
                    out.add(f"{cls.__name__}.{prop}")
                    continue
                # Le bâtisseur partagé FOURNIT déjà ce prop, donc la
                # sonde le passe deux fois. Ce n'est pas le composant
                # qui casse — cinq couples tombaient là-dedans et se
                # lisaient comme une dette (``Progress.max``,
                # ``SidebarItem.label``…). On re-sonde NU : le refus
                # d'un dict de paliers se décide dans ``__init__``,
                # avant tout rendu, donc une construction minimale
                # mesure exactement la bonne chose.
                try:
                    with render_isolated():
                        cls(**{prop: probe})
                except PROPRES:
                    continue
                except Exception:
                    out.add(f"{cls.__name__}.{prop}")
                else:
                    continue
            except Exception:
                out.add(f"{cls.__name__}.{prop}")
    return out


def test_the_abstentions_are_declared() -> None:
    """Ce qui casse sous un dict gradué est NOMMÉ, pas compté.

    Le commentaire de ``_graded_probes`` disait déjà pourquoi — il ne le
    vérifiait pas. Un composant NEUF qui casse tomberait dans la même
    branche et passerait pour une dette connue.

    Le jour où ``reject_responsive`` est câblé ailleurs, les entrées
    concernées doivent SORTIR du fichier : un plafond chiffré laisserait
    passer « un qui sort, un qui rentre ».
    """
    measured = graded_abstentions()
    surprise = sorted(measured - _NOT_GRADED)
    assert not surprise, (
        f"{surprise} casse(nt) sous un dict gradué sans être déclaré(s). "
        f"Soit c'est un composant neuf — ajoute-le à `_not_graded.txt` en "
        f"sachant qu'il hérite de la dette `reject_responsive` — soit une "
        f"prop a changé de forme."
    )
    fixed = sorted(_NOT_GRADED - measured)
    assert not fixed, (
        f"{fixed} ne casse(nt) plus : retire les entrées de "
        f"`_not_graded.txt`. Une table qui garde des noms réparés autorise "
        f"la régression en silence."
    )


@pytest.fixture(scope="module")
def corpus() -> str:
    """Le corpus de PROD : sources + safelist.

    Pas la safelist seule. Une classe préfixée peut être parfaitement
    légitime en littéral — le rail replié de la sidebar écrit
    ``md:group-data-[open=false]/sidebar:hidden`` en toutes lettres dans
    son thème, donc le scanner la voit et elle n'a rien à faire dans la
    safelist. Ce que la gate refuse, c'est une classe qu'AUCUN des deux
    canaux ne porte.
    """
    return tailwind_corpus()


@pytest.fixture(scope="module")
def safelist() -> str:
    """La directive ``@source inline(...)`` SEULE — sans les sources.

    Le contrat de la déclaration se vérifie ici et pas contre le corpus
    complet, parce que le corpus contient de la **prose**. Mesuré en
    mutation-testant cette gate : retirer ``"directions"`` du
    ``RESPONSIVE_THEME_KEYS`` de Flex la laissait VERTE, ``md:flex-row``
    se trouvant écrit dans un commentaire de ``flex.py``. C'est
    exactement la faiblesse relevée sur la gate d'à côté (``md:hidden``
    présent par hasard dans une docstring de ``carousel.py``) — une
    phrase devenue load-bearing sans que personne le sache.
    """
    from bretzel.components import (
        dynamic_responsive_classes,
    )

    return Theme().generate_css(
        responsive_classes=dynamic_responsive_classes(),
    )


@pytest.fixture(scope="module")
def graded() -> list[tuple[type, str, object]]:
    return _graded_probes()


def test_the_sweep_is_not_vacuous(graded) -> None:
    assert len(graded) >= _MIN_GRADED_PROPS, (
        f"{len(graded)} prop(s) gradué(s) découvert(s), plancher "
        f"{_MIN_GRADED_PROPS}. Soit la découverte est cassée (un "
        f"``reject_responsive`` posé trop large avale tout), soit des "
        f"props gradués ont disparu — dans les deux cas cette gate ne "
        f"garde plus rien."
    )


def test_declared_responsive_tables_exist(graded) -> None:
    """Une clé déclarée mais absente du thème = clôture silencieusement vide.

    ``dynamic_responsive_classes`` ignore une clé inconnue (elle tourne au
    démarrage du serveur, ce n'est pas l'endroit pour lever). Le refus vit
    donc ici : renommer une table de thème sans toucher la déclaration
    doit rougir, pas amputer la safelist en silence.
    """
    for cls in public_component_classes():
        for key in getattr(cls, "RESPONSIVE_THEME_KEYS", ()) or ():
            table = (cls.THEME or {}).get(key)
            assert isinstance(table, dict) and table, (
                f"{cls.__name__}.RESPONSIVE_THEME_KEYS déclare {key!r}, "
                f"qui n'est pas une table non-vide de son THEME. La "
                f"safelist ne clôturerait rien pour cette table, et les "
                f"classes ``{_PROBE_BP}:…`` correspondantes manqueraient "
                f"du CSS de prod sans la moindre erreur."
            )


def test_declared_tables_are_closed_over_breakpoints(safelist) -> None:
    """Chaque token déclaré × chaque breakpoint est DANS la safelist.

    L'assertion stricte, et la seule que la prose ne peut pas satisfaire
    : elle ne regarde ni le rendu ni les sources, juste la déclaration
    face à la directive générée. C'est celle qui rougit si quelqu'un
    retire une table de ``RESPONSIVE_THEME_KEYS`` ou casse le bridge
    ``components → theme``.

    Sa jumelle ``test_every_prefixed_class_is_safelisted`` couvre le sens
    inverse — une classe préfixée émise SANS être déclarée. Il faut les
    deux : la première ne voit pas ce qui n'est pas déclaré, la seconde
    se laisse berner par un littéral de commentaire.
    """
    checked = 0
    for cls in public_component_classes():
        for key in getattr(cls, "RESPONSIVE_THEME_KEYS", ()) or ():
            table = (cls.THEME or {}).get(key) or {}
            for value in table.values():
                for token in str(value).split():
                    for bp in BREAKPOINTS:
                        checked += 1
                        assert f"{bp}:{token}" in safelist, (
                            f"{cls.__name__} déclare la table {key!r}, mais "
                            f"`{bp}:{token}` n'est pas dans la safelist "
                            f"générée. Le bridge components → theme est "
                            f"cassé (cf. `dynamic_responsive_classes` et "
                            f"`generate_safelist_comment`) : la classe sera "
                            f"émise sans règle, donc sans effet en prod."
                        )
    assert checked >= len(BREAKPOINTS) * _MIN_PREFIXED_CLASSES, (
        f"{checked} combinaison(s) vérifiée(s) — plus aucune table "
        f"déclarée, la gate ne garde rien."
    )


def _explicit_cases() -> list[tuple[str, object]]:
    """Les appels gradués RÉELS, écrits à la main — et pourquoi.

    Le balayage automatique sonde chaque prop avec son **défaut**, ce qui
    suffit à découvrir qu'il est gradué mais pas toujours à exercer le
    chemin : ``per_view`` vaut 1 par défaut, or les puces ne se masquent
    qu'à partir de 2. Mutation-testé — la gate restait verte alors que
    Carousel ne déclarait plus rien, précisément le bug d'origine.

    Ces quatre cas ferment le trou. Ils sont écrits en dur parce qu'ils
    encodent une INTENTION (« la valeur au breakpoint doit différer de
    celle de base ») qu'aucune introspection ne devine.
    """
    from bretzel.components.layout.carousel import Carousel
    from bretzel.components.layout.flex import Flex
    from bretzel.components.layout.grid import Grid
    from bretzel.components.primitives.text import Text

    def carousel() -> object:
        with Carousel(per_view={"base": 1, _PROBE_BP: 3}) as node:
            for index in range(6):
                Text(f"s{index}")
        return node

    return [
        ("ui.flex(direction=…)",
         lambda: Flex(direction={"base": "col", _PROBE_BP: "row"})),
        ("ui.flex(gap=…)", lambda: Flex(gap={"base": "sm", _PROBE_BP: "xl"})),
        ("ui.grid(cols=…, gap=…)",
         lambda: Grid(cols={"base": 1, _PROBE_BP: 3},
                      gap={"base": "sm", _PROBE_BP: "xl"})),
        ("ui.carousel(per_view=…)", carousel),
    ]


def test_real_graded_call_sites_reach_the_safelist(safelist) -> None:
    """Le cas d'usage entier, de l'appel Python à la règle CSS.

    Contre la **safelist** et non le corpus : c'est ce qui rend cette
    assertion imperméable à un littéral de commentaire (cf. la fixture).
    Et chaque cas doit émettre AU MOINS une classe préfixée — sans quoi
    un composant qui cesse de graduer passerait inaperçu.
    """
    for label, build in _explicit_cases():
        with render_isolated():
            html = serialize(build().render())
        prefixed = {
            token
            for match in re.finditer(r'(?<![\w:-])class="([^"]*)"', html)
            for token in match.group(1).split()
            if _PREFIXED.match(token)
        }
        assert prefixed, (
            f"{label} n'émet plus AUCUNE classe préfixée. Soit le prop a "
            f"cessé d'être gradué, soit la table qui le porte est vide — "
            f"dans les deux cas le responsive de ce composant est mort."
        )
        missing = sorted(c for c in prefixed if c not in safelist)
        assert not missing, (
            f"{label} émet {missing}, absent(s) de la safelist : la règle "
            f"ne sera pas dans le `style.css` compilé, donc le composant "
            f"ignorera son breakpoint en PROD tout en marchant en dev. "
            f"Déclare la table d'origine dans le `RESPONSIVE_THEME_KEYS` "
            f"du composant."
        )


def test_every_prefixed_class_is_safelisted(graded, corpus) -> None:
    """Le cœur : rendre chaque prop gradué, et exiger la règle en prod."""
    missing: list[str] = []
    seen = 0
    for cls, prop, probe in graded:
        with render_isolated():
            html = serialize(cls(**{prop: probe}).render())
        for match in re.finditer(r'(?<![\w:-])class="([^"]*)"', html):
            for token in match.group(1).split():
                if not _PREFIXED.match(token):
                    continue
                seen += 1
                if token not in corpus:
                    missing.append(f"{token} ({cls.__name__}.{prop})")

    assert seen >= _MIN_PREFIXED_CLASSES, (
        f"{seen} classe(s) préfixée(s) observée(s), plancher "
        f"{_MIN_PREFIXED_CLASSES} — les props gradués sont découverts "
        f"mais n'émettent plus rien : la gate est devenue aveugle."
    )
    assert not missing, (
        "ces classes sont émises mais absentes de la safelist, donc "
        "sans règle dans le `style.css` compilé — elles marchent en dev "
        "et ne font RIEN en prod : "
        + ", ".join(sorted(set(missing)))
        + ". Le remède : déclarer la table de thème d'où sort le token "
        "dans le `RESPONSIVE_THEME_KEYS` du composant (elle sera "
        "clôturée sur les cinq breakpoints), ou l'ajouter à "
        "`_LAYOUT_CLASSES` si la classe est assemblée depuis un scalaire."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : une classe préfixée par un breakpoint est reconnue.

    Une classe ``md:gap-6`` n'existe littéralement dans aucun fichier —
    elle est assemblée au render. Si le préfixe cessait d'être reconnu,
    la gate ne chercherait plus rien dans la safelist et le gap
    disparaîtrait en PROD tout en étant juste en dev.
    """
    for offending in ("md:gap-6", "sm:w-64", "2xl:grid-cols-4"):
        assert _PREFIXED.match(offending), f"{offending!r} devrait être vu préfixé"
    for licit in ("gap-6", "group-hover:opacity-100", "data-[open=true]:flex"):
        assert not _PREFIXED.match(licit), f"{licit!r} : faux positif"

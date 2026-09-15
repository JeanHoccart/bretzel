"""Un slot textuel accepte un Component — ou le REFUSE en le disant.

Le socle porte le contrat noir sur blanc (``component.py``,
``emit_text_slot``) : *« Universal contract says every slot accepts
``str | ClientBinding | Component`` »*. Cette gate le fait tenir, et
surtout elle interdit le troisième état — celui qui n'est écrit nulle
part et que 27 paramètres pratiquaient : **casser sans le dire**.

Les trois états, dont DEUX sont légitimes
-----------------------------------------

1. **Accepte** — ``adopt_slot`` à la construction, ``emit_text_slot`` au
   rendu. Le balisage arrive dans le DOM. C'est le défaut.
2. **Refuse fort** — ``ComponentUsageError`` à la CONSTRUCTION, avec la
   raison. Légitime quand la valeur n'est pas un slot : une source à
   parser (``markdown.text``), une chaîne de balisage (``html.content``),
   une donnée sérialisée en JSON (``file_upload.accept``), ou un texte
   qui **double en attribut** — un ``aria-label`` ne porte qu'une string
   (``file_upload.label``, les quatre ``empty_text`` de chart).
3. ~~Avale ou plante~~ — **interdit**. C'est ce que la gate ferme.

Ce que le troisième état donnait, mesuré le 2026-08-17 sur les 63
paramètres textuels du catalogue :

- **14 plantaient** sur ``AttributeError: 'Text' object has no attribute
  'replace'``, levé au fond de ``escape_html`` — aucun rapport visible
  avec ce que l'auteur a écrit. Un ``ui.dialog(title=…)`` avec un badge
  dedans est banal ; il cassait.
- **13 expédiaient le ``__repr__`` Python au navigateur** —
  ``<bretzel…object at 0x…>`` affiché dans la page.

Pourquoi une gate et pas 27 correctifs
--------------------------------------

C'est la **quatrième** gate de kwarg universel, sœur de
``test_root_slot_override_universal`` (``slots=``),
``test_reactive_classes_universal`` (``classes=``) et de celle de
``style=``. Même forme, même maladie : un contrat que le socle porte et
qu'un composant sur deux oublie de lire. Réparer les 27 sans la gate les
laisse redériver au prochain composant écrit (règle 8 du CLAUDE.md).

⚠️ Le point aveugle que cette gate a dû corriger dans son PROPRE harnais
-----------------------------------------------------------------------

``tab``, ``step``, ``tree_node`` et ``accordion_item`` rendent **vide**
montés seuls : c'est leur parent qui lit leur ``label``. Un balayage qui
les construit isolément conclut donc « pas un slot textuel » et les sort
de la population **sans un mot** — la première version de cette mesure a
raté sept composants comme ça. D'où :data:`MOUNT`. C'est la même
pathologie que celle notée en tête de
``test_root_slot_override_universal`` (« un composant dont le bug
n'existe qu'en composition est invisible à un harnais qui le monte
isolément »), rencontrée une deuxième fois.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bretzel import ui
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.core.serialize import serialize
from bretzel.introspect import describe_component
from tests.audit.test_binding_completeness import CONSTRUCT, _Skip
from tests.consistency._discovery import (
    in_text_content,
    public_component_classes,
    ui_name_of,
)

#: Preuve de morsure : garde la table MOUNT vivante — sans elle la population rétrécit de
#: sept composants-enfants en restant au-dessus du plancher.
MUTATION_PROOF = "test_the_sweep_sees_a_component_mounted_under_its_parent"

#: Une chaîne qu'aucun thème ni aucun défaut ne peut produire.
SENTINEL = "ZZTEXTSLOT"

#: Planchers de non-vacuité. Mesurés le 2026-08-17 : 63 paramètres
#: textuels sur 45 composants. Sous ces seuils, la gate n'exerce plus
#: assez pour affirmer quoi que ce soit — un ``describe_component`` cassé
#: ou un ``MOUNT`` périmé videraient la population en silence, et la gate
#: resterait verte sur rien. À relever quand la couverture monte, jamais
#: à baisser sans écrire pourquoi.
_PARAM_FLOOR = 55
_COMPONENT_FLOOR = 40


# ── Construction sous parent ──────────────────────────────────────────


def _under(*make_parents, **fixed):
    """Un builder qui bâtit l'enfant DANS la pile de parents donnée.

    ``make_parents`` sont des **fabriques**, du plus externe au plus
    interne, et chacune est appelée DANS le contexte de la précédente.
    Ce n'est pas un détail de style : un ``Component`` s'enregistre
    auprès du parent actif dès son ``__init__``, donc construire toute la
    pile d'avance détache la section de sa sidebar — mesuré, la
    population passait de 63 à 59 paramètres.

    ``fixed`` porte les arguments que l'enfant exige par ailleurs (son
    identifiant, son ``href``) — en **kwargs**, jamais en positionnels,
    sinon ils entrent en collision avec le paramètre sous test.
    """

    def build(Cls, prop, value):
        import contextlib

        with contextlib.ExitStack() as stack:
            root = stack.enter_context(make_parents[0]())
            for make in make_parents[1:]:
                stack.enter_context(make())
            Cls(**{**fixed, prop: value})
        return root

    return build


#: Les composants qu'il faut bâtir DANS leur parent — cf. le point aveugle
#: en tête de module. Les parents sont construits paresseusement (lambda)
#: parce qu'un ``Component`` s'enregistre auprès du parent actif dès son
#: ``__init__`` : les bâtir à l'import de ce module les attacherait à la
#: racine de rendu de qui importe en premier.
#:
#: ``CONSTRUCT`` (partagé avec l'audit) couvre les autres besoins de
#: construction fidèle ; il est consulté en second parce que ses builders
#: posent des positionnels qui entrent en collision avec le paramètre sous
#: test (``ToggleButton("a", "A", label=…)`` → *got multiple values for
#: argument 'label'*).
def _mount_table():
    from bretzel.components import Accordion, Stepper, Tabs, ToggleGroup, Tree
    from bretzel.components.navigation.navbar.navbar import Navbar, NavbarSection
    from bretzel.components.navigation.sidebar.sidebar import Sidebar, SidebarSection

    return {
        "Tab": _under(lambda: Tabs(value="a"), tab_id="a"),
        "Step": _under(lambda: Stepper(value=0)),
        "TreeNode": _under(Tree),
        "AccordionItem": _under(Accordion),
        "ToggleButton": _under(ToggleGroup, value="a"),
        # Les deux items de nav veulent la vraie chrome : le conteneur
        # possède la portée ``current_path`` que lit le mode auto-actif,
        # la section groupe les lignes.
        "SidebarItem": _under(
            Sidebar, lambda: SidebarSection(label="MENU"), href="/"
        ),
        "NavbarItem": _under(
            Navbar, lambda: NavbarSection(side="center"), href="/"
        ),
    }


MOUNT = _mount_table()


def _build(cls: type, prop: str, value):
    builder = MOUNT.get(cls.__name__) or CONSTRUCT.get(cls.__name__)
    if builder is not None:
        return builder(cls, prop, value)
    return cls(**{prop: value})


def _in_text_content(html: str) -> bool:
    """La sentinelle est-elle du CONTENU, pas une valeur d'attribut ?"""
    return in_text_content(html, SENTINEL)


# ── Découverte de la population ───────────────────────────────────────


def _textual_params(cls: type) -> list[str]:
    """Les paramètres dont une STRING ressort en contenu du DOM.

    Empirique exprès. Une heuristique sur le nom (``label``, ``title``…)
    raterait ``table.empty_text`` et prendrait ``input.placeholder``, qui
    n'est qu'un attribut.

    L'annotation ne sert que de pré-filtre, et il faut ``str`` **ou**
    ``Any`` : quatre slots bien réels du catalogue (``step.label``,
    ``step.description``, ``tree_node.label``, ``accordion_item.label``)
    sont annotés ``Any``. Et le pré-filtre reste nécessaire dans l'autre
    sens — sans lui, ``heading.level`` (un ``int`` qui devient un nom de
    balise) et ``file_upload.max_size_mb`` entrent dans la population, où
    une string ressort « en contenu » sans qu'il s'agisse d'un slot.
    """
    info = describe_component(ui_name_of(cls), cls)
    out: list[str] = []
    for p in info.params:
        if p.kind in ("**kwargs", "*args") or p.name.startswith("on_"):
            continue
        if "str" not in p.type_label and p.type_label != "Any":
            continue
        try:
            with render_isolated():
                html = serialize(_build(cls, p.name, SENTINEL).render())
        except Exception:
            # Un paramètre qu'une string ne peut pas traverser (une
            # énumération, un `int`, un couple d'arguments requis) n'est
            # pas un slot textuel — il sort de la population par
            # DÉFINITION, pas par accident de balayage.
            #
            # ⚠️ « Par définition » était une AFFIRMATION, jamais
            # vérifiée : un composant qui cesse de se construire tombe
            # dans la même branche et passe pour un refus de principe.
            # ``_not_a_text_slot.txt`` nomme les 35 d'aujourd'hui, donc
            # le 36ᵉ se voit (cf. ``test_the_abstentions_are_declared``).
            continue
        if _in_text_content(html):
            out.append(p.name)
    return out


def _population() -> list[tuple[type, str]]:
    return [
        (cls, prop)
        for cls in public_component_classes()
        for prop in _textual_params(cls)
    ]


_POPULATION = _population()


# ── Le contrat ────────────────────────────────────────────────────────

#: Les deux moitiés du contrat balaient la MÊME population. Écrit une
#: fois : le jour où l'``ids=`` change, il ne peut pas ne changer que
#: d'un côté et rendre les deux rapports d'échec incomparables.
_over_population = pytest.mark.parametrize(
    ("cls", "prop"),
    _POPULATION,
    ids=lambda v: v if isinstance(v, str) else v.__name__,
)


@_over_population
def test_text_slot_accepts_a_component_or_refuses_loudly(
    cls: type, prop: str
) -> None:
    name = f"{ui_name_of(cls)}.{prop}"

    try:
        with render_isolated():
            built = _build(cls, prop, ui.text(SENTINEL))
    except _Skip as exc:
        pytest.skip(str(exc))
    except ComponentUsageError as exc:
        # État 2 — refus légitime. On exige que le message DISE pourquoi :
        # un refus qui ne se justifie pas se lit comme un bug.
        msg = str(exc)
        assert prop in msg, (
            f"{name} refuse un Component, mais son message ne nomme pas le "
            f"paramètre fautif — l'auteur ne saura pas quoi corriger.\n{msg}"
        )
        assert len(msg) > 80, (
            f"{name} refuse un Component sans dire POURQUOI. Un refus est "
            f"un état légitime du contrat, mais il doit expliquer ce que le "
            f"paramètre est vraiment (une source à parser ? une donnée qui "
            f"double en attribut ?) et par quoi composer à la place — cf. "
            f"``markdown.text`` et ``file_upload.label``.\n{msg}"
        )
        return
    except Exception as exc:
        raise AssertionError(
            f"{name} : passer un Component PLANTE sur "
            f"{type(exc).__name__}: {exc}\n\n"
            f"C'est le troisième état, celui que le contrat n'autorise pas. "
            f"Deux issues, au choix :\n"
            f"  • si c'est un slot de contenu → ``Component.adopt_slot(v)`` "
            f"dans ``__init__`` puis ``self.emit_text_slot(v)`` au rendu, "
            f"comme ``button.label`` et ses 31 frères ;\n"
            f"  • si ce n'en est pas un (source à parser, donnée JSON, texte "
            f"qui double en ``aria-label``) → lève un ``ComponentUsageError`` "
            f"à la construction en disant pourquoi, comme ``markdown.text``.\n"
            f"Ce qui est interdit, c'est de casser au fond de la pile : "
            f"l'erreur ci-dessus n'a aucun rapport visible avec ce que "
            f"l'auteur a écrit."
        ) from exc

    with render_isolated():
        html = serialize(built.render())

    assert "object at 0x" not in html, (
        f"{name} : le ``__repr__`` Python part au navigateur "
        f"(``<bretzel…object at 0x…>`` s'affiche dans la page).\n\n"
        f"Le Component tombe dans un ``str(value)``. Même correctif que "
        f"ci-dessus : ``adopt_slot`` + ``emit_text_slot`` si c'est un slot, "
        f"``ComponentUsageError`` si ce n'en est pas un."
    )
    assert _in_text_content(html), (
        f"{name} : le Component est AVALÉ — ni rendu, ni refusé, aucune "
        f"trace dans le DOM. Le contrat n'a que deux issues : honorer ou "
        f"refuser en le disant."
    )


@_over_population
def test_an_empty_text_slot_renders_nothing_instead_of_crashing(
    cls: type, prop: str
) -> None:
    """L'autre moitié du contrat : ``emit_text_slot`` renvoie ``None``
    pour un slot vide, et le sérialiseur **lève** sur un ``None`` dans
    ``children`` (« Cannot serialize unknown Node type : NoneType »).

    Un appelant qui écrit ``children=(self.emit_text_slot(x),)`` sans
    garder l'appel par un ``if x:`` transforme donc « slot vide » — un cas
    parfaitement légal — en plantage. C'est exactement ce que la migration
    des 20 slots de contenu a introduit dans ``sidebar_footer`` : le span
    du nom était le seul des six slots du fichier à n'être gardé par aucun
    ``if``, donc ``ui.sidebar_footer()`` sans nom levait.

    **Les 14 956 tests de la suite rapide ne l'ont pas vu** — aucun ne
    construit ce composant sans nom. Un piège que le contrat lui-même
    fabrique mérite sa moitié de gate, pas une relecture attentive.
    """
    try:
        with render_isolated():
            built = _build(cls, prop, "")
    except _Skip as exc:
        pytest.skip(str(exc))
    except ComponentUsageError:
        # Ce paramètre refuse déjà (état 2) : rien à vérifier ici.
        return
    with render_isolated():
        serialize(built.render())


def test_population_is_not_vacuous() -> None:
    """Sans plancher, un ``describe_component`` cassé ou un ``MOUNT``
    périmé viderait la population et cette gate resterait verte en
    n'ayant rien vérifié — la pathologie relevée sur quatre gates par
    l'audit du socle."""
    components = {cls.__name__ for cls, _ in _POPULATION}
    assert len(_POPULATION) >= _PARAM_FLOOR, (
        f"la gate n'exerce plus que {len(_POPULATION)} paramètres textuels "
        f"(plancher {_PARAM_FLOOR}, 63 mesurés le 2026-08-17). Vérifie la "
        f"découverte avant de croire que la gate passe — ne baisse pas le "
        f"plancher."
    )
    assert len(components) >= _COMPONENT_FLOOR, (
        f"la gate n'exerce plus que {len(components)} composants (plancher "
        f"{_COMPONENT_FLOOR}, 45 mesurés le 2026-08-17)."
    )


def test_the_sweep_sees_a_component_mounted_under_its_parent() -> None:
    """La découverte doit voir ``tab.label`` — le cas qui a fait rater
    sept composants à la première version de cette mesure.

    Ce test garde :data:`MOUNT` vivant. Sans lui, quelqu'un peut retirer
    une entrée de ``MOUNT`` : la population rétrécit de sept, reste
    au-dessus du plancher, et la gate continue de passer en ayant cessé
    de regarder les composants-enfants — exactement le mode de panne que
    le plancher NE couvre pas (cf. la memory sur les planchers qui
    doivent lire la DÉCOUVERTE, pas la population)."""
    from bretzel.components import (
        AccordionItem,
        NavbarItem,
        SidebarItem,
        Step,
        Tab,
        ToggleButton,
        TreeNode,
    )

    # ⚠️ TOUTES les entrées de MOUNT, pas un échantillon. Mesuré le
    # 2026-08-17 en refactorant la table : construire la pile de parents
    # d'avance (au lieu de chaque parent DANS le contexte du précédent)
    # détachait la section de sa sidebar, et la population tombait de 63 à
    # 59. Ni le plancher (55) ni un échantillon Tab/Step/TreeNode/
    # AccordionItem ne l'ont vu — c'est SidebarItem et NavbarItem qui
    # étaient tombés. Seul le nombre de tests collectés l'a révélé, ce qui
    # n'est pas une gate.
    for cls, prop in (
        (Tab, "label"),
        (Step, "label"),
        (TreeNode, "label"),
        (AccordionItem, "label"),
        (SidebarItem, "label"),
        (NavbarItem, "label"),
        (ToggleButton, "label"),
    ):
        assert prop in _textual_params(cls), (
            f"{cls.__name__}.{prop} est sorti de la population. Ce composant "
            f"a besoin de son parent — soit il rend VIDE monté seul (c'est le "
            f"parent qui lit son label), soit son parent porte la portée qu'il "
            f"lit. Il faut donc le bâtir sous ce parent (MOUNT) pour que la "
            f"découverte le voie. Sans ça il quitte le balayage sans un mot."
        )


#: Les couples ``Classe.param`` qu'une sentinelle de chaîne ne traverse
#: pas, figés au 2026-08-19 (35 sur 430 candidats). Le fichier porte la
#: raison ; elle est la même pour tous.
_NOT_A_TEXT_SLOT: frozenset[str] = frozenset(
    line.strip()
    for line in (
        Path(__file__).with_name("_not_a_text_slot.txt")
    ).read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
)


def sentinel_abstentions() -> set[str]:
    """``Classe.param`` que la sentinelle de chaîne ne construit pas."""
    out: set[str] = set()
    for cls in public_component_classes():
        info = describe_component(ui_name_of(cls), cls)
        for p in info.params:
            if p.kind in ("**kwargs", "*args") or p.name.startswith("on_"):
                continue
            if "str" not in p.type_label and p.type_label != "Any":
                continue
            try:
                with render_isolated():
                    serialize(_build(cls, p.name, SENTINEL).render())
            except Exception:
                out.add(f"{cls.__name__}.{p.name}")
    return out


def test_the_abstentions_are_declared() -> None:
    """Ce que la sentinelle ne traverse pas est NOMMÉ, pas compté.

    Les planchers du fichier comptent la population RETENUE ; ils ne
    disent rien de ce qui en sort. Un composant qui cesse de se
    construire ferait donc baisser le compte sans être nommé — et les
    planchers ont de la marge, donc rien ne rougirait.
    """
    measured = sentinel_abstentions()
    surprise = sorted(measured - _NOT_A_TEXT_SLOT)
    assert not surprise, (
        f"{surprise} ne traverse(nt) plus la sentinelle sans être "
        f"déclaré(s). Soit c'est un paramètre neuf qui n'est pas un slot "
        f"textuel — ajoute-le au fichier — soit un composant a cessé de se "
        f"construire, et il sort du contrat EN SILENCE."
    )
    fixed = sorted(_NOT_A_TEXT_SLOT - measured)
    assert not fixed, (
        f"{fixed} traverse(nt) de nouveau : retire les entrées de "
        f"`_not_a_text_slot.txt` — le contrat les juge désormais."
    )

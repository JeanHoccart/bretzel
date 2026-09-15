"""Câblage partagé du socle — deux métiers, pas un.

⚠️ Ce module s'est longtemps annoncé « Shared V3 client wiring for
**overlay** components », et ça n'a plus été vrai à partir du
2026-08-23 : il a pris +518 lignes qui ne parlent pas d'overlays du tout.
Un lecteur cherchant « où vit la vérification de placement d'une barre
sticky » n'avait aucune raison d'ouvrir un fichier qui se présente comme
la colle des popovers.

**1. Le câblage client des surfaces ancrées et modales** — le métier
d'origine, décrit en détail ci-dessous.

**2. Les questions de PLACEMENT, arbitrées quand l'arbre est complet.**
Elles ne peuvent PAS se répondre à la construction : une barre ``sticky``
ne sait pas qu'un ``ui.viewport`` va venir, ni quel est son vrai parent de
disposition. Le pipeline les appelle depuis un seul point, une fois la
page bâtie (cf. ``render/pipeline.py``) :

- :func:`register_sticky_bar` / :func:`check_sticky_bar_placement` — une
  barre ``sticky`` est-elle dans un cadre gelé où elle a un sens ?
- :func:`wire_sidebar_triggers` / :func:`check_sidebars_are_reachable` —
  à quelle barre ce déclencheur parle-t-il, et cette barre a-t-elle un
  moyen de revenir ?
- :func:`unwrap_transparent` — un conteneur qui trie ses enfants doit
  voir à travers une zone ``@refreshable``, qui est transparente à la
  disposition sans être une instance de ce qu'elle porte.
- :func:`drop_tag_bound_attrs` — ce qu'un changement de balise ne peut
  plus porter.

Les deux métiers cohabitent ici parce qu'ils partagent la même raison
d'être au niveau ``base/`` : être importables par tous les groupes sans
créer de cycle. S'ils divergent encore, c'est le second qui part.

---

Two families share the anchored/modal wiring so it can't drift :

**Modal overlays** (Dialog, Drawer) :
- :func:`show_attrs` — ``data-open`` + ``bz-attr:data-open`` +
  ``data-bz-overlay``. L'élément reste **MONTÉ** (pas de ``bz-show``, pas de
  prestamp ``display:none`` : c'est le sélecteur
  ``[data-bz-overlay][data-open="false"]`` du shell qui fait l'anti-flash,
  et une transition CSS a besoin que le nœud existe). Cette ligne annonçait
  l'ancien mécanisme jusqu'au 2026-08-01, en contredisant la docstring de la
  fonction elle-même 90 lignes plus bas.
- :func:`focus_trap_effect` — panel ``bz-effect`` engaging
  ``$bz.helpers.focusTrap`` while open (dispose on close).
- :func:`modal_root_effect` — root ``bz-effect`` : scroll lock via
  ``$bz.helpers.scrollLock`` + ``open``/``close`` event dispatch.
- :func:`escape_init` — ``bz-init`` Escape-to-close.

**Anchored overlays** (Popover, Dropdown, Tooltip) :
- :func:`anchored_panel_effect` — panel ``bz-effect`` : display toggle
  + attach / detach ``$bz.helpers.floating`` against the trigger.
- :func:`dispatch_root_effect` — root ``bz-effect`` : open/close
  dispatch only (no scroll lock — an anchored panel doesn't trap the
  page).
- :func:`anchored_dismiss_init` — ``bz-init`` : Escape + click-outside
  via ``$bz.helpers``.

**Both** :
- :func:`imperative_listeners` — ``bz-on:bz-open/close/toggle``
  catching the DOM commands fired by ``.open()``/``.close()``/
  ``.toggle()`` from external triggers.

Base-level shared primitive (juin 2026 — promoted from ``overlay/`` per
its own guidance). The same anchored/modal wiring is needed by overlays
(Dialog/Drawer/Dropdown/Popover/Tooltip), inputs (Select/Combobox/the
date pickers/Calendar) AND navigation (SidebarFooter) — i.e. across
groups — so it belongs in ``base/``, importable by anyone, instead of
forcing every consumer to reach into the ``overlay/`` group (anti-règle 5).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.core.tree import Element, Node
from bretzel.runtime import (
    BZ_ATTR_PREFIX,
    BZ_ON_PREFIX,
    DATA_BZ_SIG,
    DATA_BZ_TS,
    SERVERSYNC_KEY,
)
from bretzel.runtime.protocol import outlet_id_for

# Tokens qui déclarent une largeur INTRINSÈQUE — la boîte se dimensionne
# à son contenu. Tout le reste, en flux normal, remplit son parent.
# Même vocabulaire que ``test_inline_root_hugs_content``, qui classe les
# racines sur exactement cet axe.
#: Les attributs HTML dont le SENS est lié à une balise précise, avec la
#: liste des balises où ils en ont un. Fermée et courte exprès : on n'y
#: met que ce qui change de signification (ou n'en a plus) ailleurs, pas
#: tout ce qui est « inhabituel ».
#: Le drapeau qu'un composant pose pour dire « je ne suis pas là ».
#: Deux le portent : la section d'une zone ``@refreshable`` et
#: ``ui.fragment``. Cf. :func:`unwrap_transparent`.
TRANSPARENT_WRAPPER_FLAG = "IS_TRANSPARENT_WRAPPER"


#: Le drapeau qu'un cadre « document gelé » pose pour dire « l'écran,
#: c'est moi ». Un seul le porte :
#: :class:`~bretzel.components.layout.viewport.Viewport`.
FROZEN_FRAME_FLAG = "IS_FROZEN_FRAME"

#: Les directions de flex qui font d'une barre pleine largeur une COLONNE
#: du cadre au lieu d'une rangée du bas.
_ROW_DIRECTIONS = frozenset({"row", "row-reverse"})


def register_sticky_bar(component: Any, call: str) -> None:
    """Inscrire une barre ``sticky`` pour la passe de placement.

    Appelée par ``ui.bottom_bar`` (toujours collée) et par
    ``ui.navbar(sticky=True)``. Une navbar ordinaire défile avec le
    document : elle n'a rien à voir avec le modèle gelé, et ne s'inscrit
    pas.

    Le site d'appel est capturé ICI, pendant que la pile le porte encore
    — la passe, elle, tourne dans le pipeline et ne saurait plus dire
    quelle ligne a écrit la barre. C'est ce qui permet au message de
    nommer ``fichier:ligne`` au lieu de laisser le lecteur chercher.
    """
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    if ctx is None:
        return
    ctx.sticky_bars.append((component, call, _user_call_site()))


def _user_call_site() -> str:
    """``fichier:ligne`` du premier cadre HORS du framework, ou ``""``.

    On remonte jusqu'à sortir de ``bretzel/`` : entre l'appelant et ici
    il y a le ``__init__`` du composant et celui du socle, et parfois
    une fabrique. Compter les cadres serait juste jusqu'au premier
    composant qui en ajoute un.
    """
    frame = sys._getframe(1) if hasattr(sys, "_getframe") else None
    root = str(Path(__file__).parents[2])
    while frame is not None:
        name = frame.f_code.co_filename
        if not name.startswith(root):
            return f"{Path(name).name}:{frame.f_lineno}"
        frame = frame.f_back
    return ""


def check_sticky_bar_placement(roots: Iterable[Any], bars: Iterable[Any]) -> None:
    """Juger la place des barres ``sticky`` une fois l'arbre bâti.

    Ne fait **rien** tant qu'aucun cadre gelé (``ui.viewport``) n'est
    dans l'arbre : le modèle par défaut — le document qui défile, dix
    apps du dépôt sur dix-huit — n'est pas concerné.

    Les deux placements refusés ont été mesurés en Chromium (375×667,
    ``tests/probes/probe_bottom_bar_placement.py``) ; ils rendent tous
    les deux une page qui a l'air construite :

    - **hors du cadre** — un ``ui.viewport`` est ``fixed inset-0``, donc
      il quitte le flux. Une barre restée dehors n'a plus de document à
      quoi se coller : mesuré **y = 0**, et le cadre la recouvre.
    - **dans une RANGÉE** — la barre est pleine largeur, donc elle prend
      toute la rangée : mesuré, le ``ui.pane`` voisin tombe à **0 px de
      large** et son contenu disparaît, sans erreur ni trace. C'est le
      cas le plus traître des deux, parce que la barre, elle, atterrit
      au bon endroit.

    Pourquoi ici et pas à la construction de la barre
    --------------------------------------------------
    Parce que c'est une question d'ARBRE. Une barre écrite AVANT le
    ``ui.viewport`` ne peut pas savoir qu'un cadre va venir — et pour
    une navbar, « la barre du haut d'abord » est l'ordre naturel. Et le
    parent de DISPOSITION n'est pas le parent de construction : un
    ``ui.fragment`` ou une zone ``@refreshable`` est transparent au CSS
    et opaque à ``parent_stack``, donc la barre était jugée sur son
    enveloppe. Les deux cas ont été **mesurés cassés**, et tous deux
    passaient une garde posée à la construction (2026-08-24).
    """
    bars = list(bars)
    if not bars:
        return
    frames: list[Any] = []
    paths: dict[int, list[Any]] = {}
    _index_tree(roots, [], frames, paths, {id(bar) for bar, _, _ in bars})
    if not frames:
        return

    for bar, call, site in bars:
        path = paths.get(id(bar))
        if path is None:
            # La barre n'est pas dans l'arbre rendu : adoptée par un slot,
            # ou bâtie dans un ``serialize_html`` d'inspection. Rien à
            # juger — on ne sait pas où elle atterrira.
            continue
        where = f" ({site})" if site else ""
        if not any(getattr(type(a), FROZEN_FRAME_FLAG, False) for a in path):
            raise ComponentUsageError(
                f"{call}{where} est posée HORS du `ui.viewport` de la "
                f"page. Un `ui.viewport` est `fixed inset-0` : il quitte "
                f"le flux du document, donc une barre restée dehors se "
                f"rend à y=0 et le cadre la recouvre (mesuré en "
                f"Chromium). Écris-la DANS le cadre — dernier enfant du "
                f"`ui.pane` qui défile, ou enfant direct d'un "
                f'`ui.viewport(direction="col")`.'
            )
        parent = _layout_parent(path)
        if _is_a_row(parent):
            raise ComponentUsageError(
                f"{call}{where} est dans une RANGÉE "
                f"(`{_call_name(parent)}`). La barre est pleine largeur : "
                f"elle prend toute la rangée et écrase ses voisins — "
                f"mesuré, le `ui.pane` d'à côté tombe à 0 px de large et "
                f"son contenu disparaît sans erreur. Mets-la dans la "
                f"colonne : dans le `ui.pane`, ou dans un "
                f'`ui.viewport(direction="col")`.'
            )


#: Les modes de repli qui peuvent faire DISPARAITRE la barre — ni bande
#: d'icones, ni largeur residuelle. Une barre dans un de ces deux modes
#: emporte hors de l'ecran TOUTES les affordances qu'elle rend
#: (le chevron du titre, l'arete de repli), donc son moyen de revenir ne
#: peut etre que dehors.
_VANISHING_MODES = frozenset({"overlay", "offcanvas"})


#: Le repli d'un declencheur qui n'a trouve aucune barre dans SON rendu
#: — le cas d'un rafraichissement de zone, ou la coque n'est pas rejouee.
#: On vise alors le marqueur stable pose par ``Sidebar.render``, resolu
#: au CLIC et non a la construction. Le ``?.`` evite de lever si la page
#: n'en a effectivement aucune.
TOGGLE_NEAREST_SIDEBAR = (
    "document.querySelector('[data-bz-sidebar]')?.dispatchEvent("
    "new CustomEvent('bz-toggle', {bubbles: true}))"
)


def wire_sidebar_triggers(triggers: Iterable[Any], sidebars: list[Any]) -> None:
    """Donner a chaque ``ui.sidebar_trigger`` la barre qu'il pilote.

    Resolu ici, sur l'arbre bati, et pas a la construction du
    declencheur : une coque qui ecrit sa barre du haut AVANT son
    ``<aside>`` est parfaitement normale, et l'ordre d'ecriture ne doit
    pas decider si le bouton marche. C'est la lecon des barres
    ``sticky``, appliquee au premier composant suivant qui pose une
    question d'arbre.

    Une seule barre dans la page : le declencheur la trouve tout seul —
    c'est le tier 1, et c'est le cas de toutes les coques du depot.
    Plusieurs barres : on refuse de deviner, parce qu'un mauvais choix
    ferait un bouton qui a l'air de marcher et ouvre la mauvaise chose.
    """
    for trigger in triggers:
        if trigger._sidebar is not None:      # ``sidebar=`` explicite
            continue
        if len(sidebars) == 1:
            trigger.bind_sidebar(sidebars[0])
        elif len(sidebars) > 1:
            raise ComponentUsageError(
                f"ui.sidebar_trigger() ne peut pas deviner quelle barre "
                f"il pilote : cette page en monte {len(sidebars)}. "
                f"Passe-la en argument — garde la barre dans une "
                f"variable (`sb = ui.sidebar(...)`) puis ecris "
                f"`ui.sidebar_trigger(sb)`."
            )
        # Zero barre dans CE rendu (un rafraichissement de zone qui ne
        # rejoue pas la coque) : le declencheur garde son repli par
        # selecteur, qui resout au clic. Il marche, il n'annonce juste
        # pas d'``aria-controls``.


def check_sidebars_are_reachable(sidebars: Iterable[Any]) -> None:
    """Une barre qui peut disparaitre doit avoir un moyen de revenir.

    Mesure du 2026-08-24, banc neuf en 375x667 : un
    ``ui.sidebar(collapsible="overlay", open=False)`` sans declencheur
    rend un ``<aside>`` a **x = -256** et **zero element cliquable a
    l'ecran**. La page repond 200, rien n'est journalise, et la
    navigation est simplement injoignable — c'est ce qui avait rendu six
    des onze routes d'``examples/crm`` inatteignables sur telephone.

    Ce n'est pas un oubli du composant, c'est le revers d'une bonne
    decision : le chevron flottant auto-rendu a ete retire le
    2026-08-21 parce que « c'etait le composant qui decidait de la place
    d'une affordance de l'app ». Ce qui manquait ensuite, c'etait une
    piece a POSER — d'ou ``ui.sidebar_trigger``, et d'ou ce controle.

    Trois facons d'etre atteignable, et la garde se tait si l'une tient :

    - un ``ui.sidebar_trigger`` la vise (tier 1) ;
    - une commande a ete emise contre elle — ``on_click=sb.toggle()`` sur
      n'importe quel bouton (tier 2, l'echappatoire) ;
    - son ``open=`` est pilote par un :class:`ClientBinding` : l'etat
      appartient alors a l'app, qui peut le lever d'ou elle veut, et le
      framework n'a aucun moyen de le savoir. On ne juge pas.
    """
    for sidebar in sidebars:
        mode = getattr(sidebar, "_reactive_values", {}).get("collapsible")
        if mode not in _VANISHING_MODES:
            continue
        if getattr(sidebar, "_commanded", False):
            continue
        if sidebar._binding_metadata.get("open") is not None:
            continue
        raise ComponentUsageError(
            f'ui.sidebar(collapsible="{mode}") n\'a aucun moyen d\'etre '
            f"rouverte. Dans ce mode la barre quitte l'ecran, et elle "
            f"emporte avec elle le chevron de son titre et son arete de "
            f"repli — mesure : aside a x=-256, zero element cliquable a "
            f"l'ecran, page a 200. Pose un `ui.sidebar_trigger()` la ou "
            f"tu veux le bouton (dans ta barre du haut, typiquement), ou "
            f"appelle `sb.toggle()` depuis le tien. Si c'est ton app qui "
            f"tient l'etat, passe `open=` un ClientState : la garde se "
            f"tait."
        )


def _index_tree(
    children: Iterable[Any],
    path: list[Any],
    frames: list[Any],
    paths: dict[int, list[Any]],
    wanted: set[int],
) -> None:
    """Descendre l'arbre en notant les cadres et le chemin des barres.

    Une seule descente pour les deux questions, et on ne garde le chemin
    que des barres inscrites : une page fait des milliers de nœuds, en
    garder un chemin par nœud coûterait plus que la passe.
    """
    for child in children:
        if getattr(type(child), FROZEN_FRAME_FLAG, False):
            frames.append(child)
        if id(child) in wanted:
            paths[id(child)] = list(path)
        kids = getattr(child, "_children", None)
        if kids:
            path.append(child)
            _index_tree(kids, path, frames, paths, wanted)
            path.pop()


def _layout_parent(path: list[Any]) -> Any:
    """Le premier ancêtre qui compte pour le CSS, enveloppes sautées.

    Un ``ui.fragment`` et la section d'une zone ``@refreshable`` sont
    transparents à la DISPOSITION (``display:contents``, ou fusion dans
    leur enfant unique — cf. ``render/fusion.py``). Le parent flex réel
    est donc au-dessus d'eux, et c'est lui qui décide si la barre est
    dans une rangée.
    """
    for ancestor in reversed(path):
        if not getattr(type(ancestor), TRANSPARENT_WRAPPER_FLAG, False):
            return ancestor
    return None


def _is_a_row(component: Any) -> bool:
    """La ``direction`` du composant, y compris graduée par breakpoint.

    ``direction`` est une prop RESPONSIVE (``Flex.RESPONSIVE_PROPS``) :
    ``{"base": "col", "md": "row"}`` est un appel légal, et la lire comme
    un scalaire laisserait passer un cadre qui EST une rangée à partir de
    ``md``. Un seul cran en rangée suffit à écraser le voisin.
    """
    values = getattr(component, "_reactive_values", None)
    if not values:
        return False
    direction = values.get("direction")
    if isinstance(direction, dict):
        return any(step in _ROW_DIRECTIONS for step in direction.values())
    return direction in _ROW_DIRECTIONS


def _call_name(component: Any) -> str:
    key = getattr(type(component), "THEME_KEY", None)
    return f"ui.{key}" if key else type(component).__name__



# ── Le pont de couleur ──────────────────────────────────────────────────


#: Ce qu'un thème écrit quand il lit un PALIER plutôt qu'un gabarit.
_READS_A_STEP = "(--bz-"


def refuse_a_value_off_the_table(component: Any) -> None:
    """``size=`` / ``variant=`` hors table : lever, au lieu de se taire.

    **Le silence était le comportement du catalogue, et il coûtait.**
    Mesuré le 2026-09-06 : sur les 57 couples (composant, axe) portant
    ``size`` ou ``variant``, **56 rendaient quand même** une valeur
    inventée, et pas de la même façon —

        ui.button(size="zzz")  → perd h-10, px-4, gap-2, text-sm
                                  (le bouton rend SANS AUCUNE taille)
        ui.badge(size="zzz")   → retombe sur `sm`, une taille plus bas

    Une faute de frappe ne levait pas, ne s'affichait pas, et ne se
    voyait pas en revue.

    Le dépôt applique pourtant déjà cette règle et l'écrit :
    ``bretzel describe`` dit du ``grow=`` de ``ui.flex`` « table FERMÉE, et
    une valeur hors table LÈVE : elle rendrait la chaîne vide, donc un
    kwarg mort ». C'est la même phrase, appliquée aux deux props les
    plus fréquentes du catalogue.

    Deux abstentions, chacune volontaire : on ne lève que si les valeurs
    légales sont CONNAISSABLES (cf. ci-dessous), et une valeur non-``str``
    — un dict gradué, un binding — sort d'ici sans bruit : ce n'est pas
    cette fonction qui arbitre ce cas.

    **``reactive_prop(steps=)`` passe avant la table**, et c'est ce qui a
    fermé les quatre derniers muets le 2026-09-07. La table du thème ne
    peut pas répondre pour tout le monde : ``bar_chart.variant`` et
    ``pie_chart.variant`` nomment un mode de tracé (aucune table),
    ``radio_group.size`` transmet aux enfants (table vide), et
    ``radio.size`` a bien une table mais un défaut ``None`` — or c'est le
    défaut qui sert d'ancre pour lire une table imbriquée. Les quatre
    rendaient donc n'importe quoi en silence, et l'ancienne liste
    d'abstentions de la gate décrivait cette limite du DÉTECTEUR comme
    si c'était une propriété des composants.
    """
    theme = component._resolved_theme()
    descriptors = type(component).__reactive_props__
    for prop, table_key in (("size", "sizes"), ("variant", "variants")):
        value = component._reactive_values.get(prop)
        descriptor = descriptors.get(prop)
        declared = getattr(descriptor, "steps", None)
        if declared:
            steps = frozenset(declared)
        else:
            anchor = getattr(descriptor, "default", None)
            steps = declared_steps(theme.get(table_key, {}), anchor=anchor)
        if not steps or not isinstance(value, str) or value in steps:
            continue
        raise ComponentUsageError(
            f"ui.{_ui_name_for_error(component)}: {prop}={value!r} n'est "
            f"pas dans la table du thème. Valeurs connues : "
            f"{', '.join(sorted(steps))}.\n"
            f"  Une valeur hors table ne lèverait pas d'elle-même : elle "
            f"rendrait la chaîne vide, donc un kwarg mort — le composant "
            f"perdrait ce palier sans un mot. Pour un habillage qu'aucun "
            f"palier ne couvre, c'est `classes=`."
        )


def declared_steps(
    table: Mapping[str, Any], *, anchor: str | None
) -> frozenset[str]:
    """Les paliers d'une table ``sizes`` / ``variants``, TROIS formes.

    Le catalogue imbrique la table **dans les deux sens**, et rien dans
    sa structure ne dit lequel — mesuré le 2026-09-06 : 17 tables
    plates, 37 imbriquées, et les imbriquées se partagent les deux
    ordres ::

        sizes = {"sm": "h-8", "md": "h-10"}                    # plate
        sizes = {"input_frame": {"md": "h-10"}}                # date_picker
        sizes = {"md": {"root": "h-10", "close": "size-4"}}    # badge

    D'où l'ancre : le palier par DÉFAUT du composant, lu sur son
    descripteur. Il est valide par construction, donc le niveau qui le
    contient est le niveau des paliers. Pas de vocabulaire en dur —
    sans quoi un composant qui inventerait un palier ferait mentir la
    liste.

    Deviner l'ordre coûte cher : le premier jet lisait la table plate
    partout, et la suite est passée de verte à **198 rouges** parce que
    je n'avais mesuré le refus que sur le versant illicite (cf.
    règle 8 : prouver la morsure dans les deux sens).

    Sans ancre lisible — pas de défaut déclaré, ou un défaut qu'aucun
    des deux niveaux ne porte — on rend l'ensemble vide, et le refus
    s'abstient : mieux vaut ne rien dire que refuser une valeur juste.
    """
    if not table:
        return frozenset()
    outer = frozenset(table)
    inner = frozenset(
        step
        for slot in table.values()
        if isinstance(slot, Mapping)
        for step in slot
    )
    if not inner or anchor in outer:
        return outer
    return inner if anchor in inner else frozenset()


def _ui_name_for_error(component: Any) -> str:
    """Le nom ``ui.*`` du composant, ou sa classe à défaut."""
    key = getattr(type(component), "THEME_KEY", "") or ""
    return key or type(component).__name__


def theme_context(
component: Any, *, size_default: str = "md", color_default: str = "primary"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    """``(theme, slots, sizes, size, color)`` — le préambule de render().

Une FONCTION et pas une méthode du socle : `component.py` est le
point de passage de 96 composants, et `test_the_choke_point_only_shrinks`
refuse qu'il grossisse sans décision. Sa place est ici, à côté des
autres primitives de rendu partagées.

    **Vingt-six composants ouvraient leur ``render()`` sur les mêmes
    quatre à cinq lignes**, et ils se partageaient 13 contre 11 sur
    l'ORDRE de deux d'entre elles (``size`` avant ``color``, ou
    l'inverse). Ce partage est la preuve que c'était du
    copier-coller : personne n'écrit sciemment le même bloc dans
    deux ordres. Et c'est ce qui rendait la duplication invisible —
    deux blocs qui ne diffèrent que par l'ordre ne se ressemblent
    pour aucun outil.

    Le dépôt avait déjà traité cette pathologie une fois, mais par
    FAMILLE (``overlay/_modal``, ``inputs/_picker_field``…). Ce
    préambule-là est universel, donc aucune famille ne le couvrait.

    Les défauts sont paramétrés parce qu'ils diffèrent pour de vrai :
    ``ui.icon`` part sur ``color="current"``, quelques composants sur
    une autre taille de base. Les passer explicitement garde le
    comportement identique à l'octet près.
    """
    theme = component._resolved_theme()
    return (
        theme,
        theme.get("slots", {}),
        theme.get("sizes", {}),
        component._reactive_values.get("size") or size_default,
        component._reactive_values.get("color") or color_default,
    )


def color_bridge_class(component: Any, node: Node) -> str | None:
    """La classe-pont à poser sur la racine, ou ``None``.

    Un composant coloré porte ``bz-c-<couleur>``, qui installe les onze
    paliers sur son sous-arbre (cf. :mod:`bretzel.theme.bridges`). C'est
    ce qui remplace la substitution ``{bg_color}`` : le thème écrit
    ``bg-(--bz-bg)``, une classe COMPLÈTE que le compilateur voit, et le
    pont dit de quelle couleur il s'agit.

    Trois refus, chacun pour une raison :

    1. **Une classe-pont déjà posée par l'utilisateur.** Deux ``bz-c-*``
       sur le même élément se départagent par l'ordre de la FEUILLE et
       non par celui des classes, donc l'échappatoire
       ``classes="bz-c-error"`` gagnerait ou perdrait au hasard. On lui
       laisse la place.
    2. **Une couleur qui n'est pas une chaîne** — un dict gradué, un
       binding. Sans ce refus le socle stringifie et pose
       ``bz-c-{'md': 'primary'}`` dans le DOM (mesuré le 2026-08-30).
    3. **Pas de couleur du tout** — le composant n'est pas coloré.

    ⚠️ Le cas 2 **lève** quand le thème lit un palier. Ne pas poser le
    pont y rendrait le composant SANS style — paliers indéfinis, donc
    propriétés invalides — sans une erreur ni une trace. Le dict gradué
    sur ``color`` cassait déjà au render avant la migration (cf.
    ``tests/consistency/_not_graded.txt``) : lever garde le bruit à
    l'endroit où il était, au lieu de le troquer contre du silence.
    """
    if not isinstance(node, Element):
        return None
    color = component._reactive_values.get("color")
    if color is None:
        return None

    from bretzel.theme.bridges import BRIDGE_CLASS_PREFIX, bridge_class

    root_class = str(node.attrs.get("class", ""))
    user_written = component._user_classes_str() + " " + component._raw_class_str
    if BRIDGE_CLASS_PREFIX in root_class + " " + user_written:
        return None

    if isinstance(color, str):
        _refuse_unknown_color(component, color)

    if not isinstance(color, str):
        if _READS_A_STEP in root_class:
            raise ComponentUsageError(
                f"{type(component).__name__}(color={color!r}) : la couleur "
                "doit être un nom, pas un "
                f"{type(color).__name__}.\n"
                "  Ce composant se peint avec des PALIERS "
                "(``bg-(--bz-bg)``…), qui sont posés par la classe-pont de "
                "sa couleur. Sans nom de couleur il n'y a pas de pont, "
                "donc pas de paliers, donc un composant rendu SANS style.\n"
                "  ``color=`` ne se gradue pas : une couleur par "
                "breakpoint n'a pas de sens ici."
            )
        return None
    return bridge_class(color)

def unwrap_transparent(child: Any) -> tuple[Any, Any]:
    """``(l'enfant réel, de quoi lui rendre son enveloppe)``.

    Le problème qu'elle résout, mesuré le 2026-08-23
    -------------------------------------------------
    Plusieurs conteneurs traitent leurs enfants **selon leur type** :
    ``ui.tabs`` cherche des ``Tab``, ``ui.stepper`` des ``Step``,
    ``ui.accordion`` des ``AccordionItem``, ``ui.sidebar`` son titre et
    son pied. Or un enfant est très souvent ENVELOPPÉ — dans une zone
    ``@refreshable`` (pour se rafraîchir tout seul) ou dans un
    ``ui.fragment``. L'enveloppe n'est pas une instance de ce qu'elle
    contient, donc le tri la rate.

    L'enveloppe est déjà transparente à la DISPOSITION (la zone se
    fusionne dans son enfant unique, ou se rend en ``display:contents`` —
    cf. ``render/fusion.py``). Elle ne l'était pas à l'IDENTITÉ, et ça
    coûtait cher, en silence :

    ==================  ==========================================
    ``ui.tabs``         l'onglet enveloppé **disparaît** de la barre
    ``ui.stepper``      l'étape **disparaît**
    ``ui.accordion``    l'item perd son **en-tête** et son libellé
    ``ui.sidebar``      le pied tombait **dans la zone qui défile**
    ``ui.toggle_group`` **lève** — le seul à être bruyant
    ==================  ==========================================

    Pourquoi rendre AUSSI une fonction de ré-enveloppement
    -------------------------------------------------------
    On ne peut pas simplement jeter l'enveloppe : celle d'une zone porte
    son ``bz-id``, la cible que HTMX vise pour la rafraîchir. Un parent
    qui rendrait l'enfant nu produirait un onglet correct… qui ne se
    rafraîchirait plus jamais. Le parent compose donc l'enfant comme
    avant, puis rend son identité au nœud produit ::

        real, rewrap = unwrap_transparent(child)
        node = real._render_in_tabs(...)   # le parent compose
        node = rewrap(node)                # la zone se rhabille

    Sur un enfant nu, ``rewrap`` est l'identité — l'appelant n'a pas de
    branche à écrire.

    ⚠️ **Une enveloppe à plusieurs enfants n'est PAS traversée.** Elle
    est rendue telle quelle, comme avant. Un parent qui trie ne peut pas
    couper un nœud en deux, et deviner lequel des trois enfants est « le
    vrai » serait décider à la place de l'appelant. Une zone qui contient
    un onglet ET autre chose doit être scindée par celui qui l'écrit.
    """
    if not getattr(type(child), TRANSPARENT_WRAPPER_FLAG, False):
        return child, _identity
    kids = list(getattr(child, "_children", ()) or ())
    if len(kids) != 1:
        return child, _identity
    return kids[0], getattr(child, "_rewrap", _identity)


def _identity(node: Any) -> Any:
    return node


TAG_BOUND_ATTRS: dict[str, frozenset[str]] = {
    # Sur un ``<a>``, ``type`` est un indice de type MIME de la cible —
    # pas la nature d'un bouton.
    "type": frozenset({"button", "input", "ol", "link", "script", "style"}),
    "href": frozenset({"a", "link", "area", "base"}),
    "src": frozenset({
        "img", "script", "iframe", "video", "audio", "source",
        "embed", "track", "input",
    }),
    "alt": frozenset({"img", "area", "input"}),
    "for": frozenset({"label", "output"}),
    "target": frozenset({"a", "area", "form", "base"}),
}


def drop_tag_bound_attrs(
    tag: str, attrs: dict[str, Any], *, spare: Iterable[str] = ()
) -> None:
    """Retire d'``attrs`` ce qui n'a plus de sens sous ``tag``.

    Un composant déclare ses props contre sa ``DEFAULT_TAG``, et
    plusieurs ont un défaut non-``None`` qui sort donc toujours :
    ``Button.type`` vaut ``"button"``, ``Image.alt`` est obligatoire.
    Quand la balise change — par le kwarg universel ``tag=``, ou parce
    qu'une prop l'implique (``ui.button(href=…)`` et ``ui.card(href=…)``
    rendent un ``<a>``) — ces attributs restaient là. Mesuré le
    2026-08-23 : **quatre** composants rendaient un attribut lié à une
    autre balise, dont trois un ``type="button"`` sur ce qui n'en était
    plus un.

    Appelé en fin de ``Component.emit_attrs`` — le seul endroit où la
    balise et le sac d'attributs se rencontrent pour tout le catalogue.
    Ici et pas là-bas parce que le point d'étranglement est sous
    ratchet : ce qui est une primitive partagée vit dans ce fichier.

    ``spare`` liste ce que l'appelant a écrit LUI-MÊME —
    ``attrs={"type": "text/html"}`` sur un ``<a>`` est un vrai type MIME,
    et l'échappatoire brute a le dernier mot partout ailleurs (cf. le
    contrat de précédence de ``merge_attr``). On ne retire que ce que le
    composant a produit tout seul.

    ⚠️ Deux composants posent leur attribut **après** ``emit_attrs``
    (``menu_item`` son ``type``, ``image`` son ``alt``), donc hors de
    portée d'ici : ils portent leur propre garde. C'est pourquoi la gate
    ``test_a_changed_tag_drops_what_it_cannot_carry`` lit le RENDU et
    pas cette table.
    """
    spared = set(spare)
    for name, tags in TAG_BOUND_ATTRS.items():
        if name in attrs and name not in spared and tag not in tags:
            del attrs[name]


_SHRINK_TOKENS = ("inline-block", "inline-flex", "inline-grid", "inline-table")
#: Balises inline PAR NATURE : elles se dimensionnent à leur contenu sans
#: qu'aucune classe ne le déclare. Une racine <span> sans token de
#: display hugge, un <div> identique remplit — la classe seule ne peut
#: pas les distinguer.
_INLINE_TAGS = frozenset({"span", "a", "label", "em", "strong", "code",
                          "abbr", "small", "b", "i", "button"})

_SHRINK_WIDTH_RE = re.compile(r"(?:^|\s)(?:w-fit|w-max|w-min|w-auto|w-\d|w-\[)")

#: ⚠️ Un MOT, pas une sous-chaîne. ``"w-full" in cls`` était vrai pour
#: ``max-w-full`` — qui déclare l'inverse : un PLAFOND, pas une largeur.
#: Trouvé le 2026-08-25 en posant ``max-w-full`` sur la racine du
#: calendrier : son enveloppe de tooltip s'est mise à s'étendre sur toute
#: la ligne, donc le panneau s'ancrait sur la rangée et non sur le
#: composant. Le piège vaut pour ``sm:w-full``, ``group-hover:w-full``,
#: n'importe quel préfixe — et il ne se voit qu'au navigateur.
_FILL_WIDTH_RE = re.compile(r"(?:^|\s)w-full(?:\s|$)")


def _class_decides_width(root_cls: str) -> bool | None:
    """La CLASSE tranche-t-elle, et dans quel sens ?

    ``True`` = hugge, ``False`` = remplit, ``None`` = la classe ne dit
    rien et c'est à la balise de répondre.

    L'ordre compte, et c'est le défaut que la gate a trouvé le jour même :
    une déclaration explicite doit battre l'heuristique de balise. Un
    ``dropdown_item`` est un ``<button class="… w-full">`` — inline par
    balise, remplissant par déclaration — et un ``skeleton`` est un
    ``<span class="block">``. Interroger la balise en premier les classait
    tous les deux à l'envers.
    """
    if _FILL_WIDTH_RE.search(root_cls):
        return False
    if any(token in root_cls for token in _SHRINK_TOKENS):
        return True
    if _SHRINK_WIDTH_RE.search(root_cls):
        return True
    if re.search(r"(?:^|\s)block(?:\s|$)", root_cls):
        return False
    return None


def trigger_hugs_its_content(root_cls: str) -> bool:
    """La racine se dimensionne-t-elle à son contenu ?

    ⚠️ **Ne PAS répondre par « contient ``w-full`` »**, et c'est la
    correction du 2026-08-10 : un ``div`` en bloc sans largeur déclarée
    remplit son parent **sans le dire**. Le dépôt le savait déjà ailleurs —
    ``test_input_root_fills_width`` écrit noir sur blanc « radio_group /
    form fill without a literal ``w-full``, so we forbid the shrink tokens
    rather than require ``w-full`` » — mais cette fonction-ci utilisait
    quand même le signal que cette gate déclare non fiable.

    Mesuré avant correction : **huit composants livrés** rendaient un
    tooltip qui les rétrécissait à la largeur de leur contenu — ``grid``,
    ``vstack``, ``hstack``, ``flex``, ``form``, ``radio_group``, ``tabs``
    (et ``dropzone``, qui l'a fait remonter). Dont *les deux* que la gate
    citait en exemple.
    """
    return bool(_class_decides_width(root_cls))


def trigger_is_full_width(triggers: Iterable[Any]) -> bool:
    """True if any trigger fills its row.

    An anchored overlay (Tooltip / Popover / Dropdown) wraps its trigger in
    a ``w-fit`` root. When the trigger fills its parent, that root must
    expand (see :func:`expand_fit_wrapper`) or the trigger collapses to
    content width — a tooltip'd full-width button comes out narrower than
    its plain siblings, and a tooltip'd ``vstack`` collapses onto its
    longest child.

    The question is asked of the trigger's built-in THEME root, of a
    user-passed ``classes=``, and of a rendered :class:`Element`'s class
    (the universal-modifier path). Cf. :func:`trigger_hugs_its_content`
    for why « does it say ``w-full`` » is the wrong question.
    """
    from bretzel.components.base.component import Component  # deferred : cycle

    for trigger in triggers:
        if trigger is None:
            continue
        if isinstance(trigger, Component):
            theme = getattr(trigger, "THEME", {}) or {}
            root_cls = theme.get("slots", {}).get("root", "") or ""
            # Les classes de l'appelant peuvent rétrécir une racine qui
            # remplissait, et inversement — on juge donc les deux ensemble.
            verdict = _class_decides_width(f"{root_cls} {trigger._user_classes_str()}")
            if verdict is None:
                # ⚠️ La classe ne dit rien : c'est la BALISE qui décide.
                # ``ui.text`` rend un ``<span>`` sans token de display — il
                # hugge parce qu'il est inline PAR NATURE. Sans ce repli, un
                # tooltip sur un mot s'ancrerait sur la ligne entière.
                verdict = getattr(trigger, "_tag", "div") in _INLINE_TAGS
            if not verdict:
                return True
        elif isinstance(trigger, Element):
            # Même règle, et il FAUT la répéter ici : c'est par cette
            # branche que passe le modificateur universel ``tooltip=``,
            # qui reçoit le nœud déjà rendu et non le composant. Ne juger
            # que la classe y classait ``ui.text`` (un ``<span>``) comme
            # remplissant, et son tooltip s'ancrait sur la ligne entière.
            cls = trigger.attrs.get("class", "")
            verdict = _class_decides_width(cls if isinstance(cls, str) else "")
            if verdict is None:
                verdict = trigger.tag in _INLINE_TAGS
            if not verdict:
                return True
    return False


def expand_fit_wrapper(root_cls: str) -> str:
    """Collapse an anchored overlay's ``inline-* w-fit h-fit`` default to
    ``block w-full``. Strip the fit tokens too : Tailwind's ``w-full w-fit``
    ordering is non-deterministic, so leaving ``w-fit`` in can still win and
    the full-width trigger collapses."""
    return (
        root_cls
        .replace("inline-block", "block w-full")
        .replace("inline-flex", "block w-full")
        .replace("w-fit", "")
        .replace("h-fit", "")
    )


def shrink_fit_wrapper(root_cls: str) -> str:
    """The other direction : a ``w-full`` root that must hug its trigger.

    :func:`expand_fit_wrapper` serves the overlays, whose root defaults to
    ``w-fit`` and must GROW for a full-width trigger. A form control
    defaults to ``w-full`` (a field fills its row) and has the symmetric
    problem the day it stops being a field : ``ui.combobox(trigger=…)``
    wraps the caller's « Status » button, and ``w-full`` stretches it
    across the toolbar.

    SUBSTITUTED, never appended, for the same reason the sibling strips :
    ``w-full w-fit`` resolves in an order Tailwind does not promise, so
    the loser is decided by stylesheet position rather than by intent.

    Lives here, next to its twin, so the pair is read together — the
    inline ``.replace()`` this replaces restated the ordering rationale a
    second time, three lines below a comment citing the first.
    """
    return root_cls.replace("w-full", "w-fit")


def trigger_asks_full_width(component: Any, triggers: Iterable[Any]) -> bool:
    """Does anything ask this wrapper to fill its row ?

    Two sources, and BOTH matter — that is the whole point of the helper.
    :func:`trigger_is_full_width` reads the trigger ; a caller can also
    ask on the wrapper itself, and does so through two different doors :
    ``classes="w-full"`` (``_user_classes_str``) and ``class_=`` /
    ``attrs={"class": …}`` (``_raw_class_str``, appended after render by
    the universal-modifier pass). Checking only the first silently shrank
    a combobox whose caller had used the second.
    """
    for source in (component._user_classes_str(), component._raw_class_str):
        # Même mot, même piège : un appelant qui écrit
        # ``classes="max-w-full"`` demande un PLAFOND, pas une largeur.
        if _FILL_WIDTH_RE.search(source or ""):
            return True
    return trigger_is_full_width(triggers)


def show_attrs(open_expr: str, initial_open: bool) -> dict[str, Any]:
    """``data-open`` state for CSS-driven enter/leave animations.

    The overlay element stays MOUNTED (no ``display`` toggle — ``display``
    can't be transitioned, which is why the old ``bz-show`` made the modal
    overlays pop in/out brutally). The theme animates opacity / scale /
    translate / **visibility** off ``data-[open=true|false]`` instead.

    Stringified ternary so the runtime always writes ``"true"``/``"false"``
    (a bare boolean ``false`` makes ``bz-attr`` DROP the attribute, which
    would break the CSS selector).

    ``data-bz-overlay`` est le marqueur que lit la règle anti-flash du
    shell. Le garde-fou ``html:not(.bz-ready) [bz-data]
    {visibility:hidden}`` ne suffit PAS ici : ``visibility`` est
    écrasable par un descendant, et pendant sa transition le backdrop
    calcule explicitement ``visible``, donc il gagne contre le ``hidden``
    de son ancêtre.

    Ce que ça évite. Le CSS Tailwind arrive APRÈS le premier paint (dev :
    compilé dans le navigateur ; prod : après un morph de nav partielle,
    le temps que le sous-arbre inséré soit stylé). À cet instant le
    backdrop passe d'un état non-stylé (``static``, ``opacity:1``,
    ``visible``) à ``fixed inset-0 bg-black/50 backdrop-blur-sm`` +
    ``opacity:0``. Le décor s'applique d'un coup, mais ``opacity`` et
    ``visibility`` sont dans un ``transition ... 200ms`` : elles ANIMENT
    depuis leur valeur non-stylée. Résultat : un voile flouté plein écran
    qui s'efface en 200 ms sur toute page portant un dialog / drawer. Le
    marqueur permet au shell de déclarer l'état fermé AVANT le premier
    paint : les valeurs ne bougent plus quand la feuille arrive, donc
    aucune transition ne démarre.
    """
    return {
        "data-open": "true" if initial_open else "false",
        "bz-attr:data-open": bool_attr(open_expr),
        "data-bz-overlay": "",
    }


def focus_trap_effect(open_expr: str) -> str:
    """Panel ``bz-effect`` : trap focus while open, restore on close."""
    return (
        f"((v) => {{ "
        f"if (v && !$el._bzTrap) {{ "
        f"$el._bzTrap = $bz.helpers.focusTrap($el); }} "
        f"else if (!v && $el._bzTrap) {{ "
        f"$el._bzTrap(); $el._bzTrap = null; }} "
        f"}})(!!({open_expr}))"
    )


def _dispatch_arm(open_expr: str) -> str:
    """The open/close ``$dispatch`` arm, shared by every overlay root.

    Bootstraps quietly so the initial state never fires a phantom
    event ; subsequent transitions emit ``open`` / ``close`` on the
    root, where the ``hx-trigger="open"`` / ``"close"`` listeners
    installed from ``on_open=`` / ``on_close=`` catch them.
    """
    return (
        "if ($el._bzLastOpen === undefined) { $el._bzLastOpen = v; } "
        "else if (v !== $el._bzLastOpen) { "
        "$el._bzLastOpen = v; "
        "$dispatch(v ? 'open' : 'close'); }"
    )


def modal_root_effect(open_expr: str) -> str:
    """Root ``bz-effect`` (modal overlays) : scroll lock + dispatch."""
    return (
        f"((v) => {{ "
        f"if (v && !$el._bzLock) {{ "
        f"$el._bzLock = $bz.helpers.scrollLock(); }} "
        f"else if (!v && $el._bzLock) {{ "
        f"$el._bzLock(); $el._bzLock = null; }} "
        f"{_dispatch_arm(open_expr)} "
        f"}})(!!({open_expr}))"
    )


def dispatch_root_effect(open_expr: str) -> str:
    """Root ``bz-effect`` (anchored overlays) : open/close dispatch only.

    No scroll lock — a popover / dropdown doesn't trap the page.
    """
    return (
        f"((v) => {{ {_dispatch_arm(open_expr)} }})(!!({open_expr}))"
    )


#: Le drapeau que :func:`changed_since_open_effect` pose sur la racine, et
#: que le filtre d'événement HTMX relit. Écrit à UN endroit : le poseur et
#: le liseur sont dans deux langages et deux fichiers, donc un littéral
#: recopié se désynchroniserait en silence — le handler ne partirait plus
#: JAMAIS, ce qui ressemble exactement au comportement voulu.
CHANGED_FLAG = "_bzChanged"


def changed_since_open_effect(open_expr: str, picked_js: str) -> str:
    """``bz-effect`` : la valeur a-t-elle bougé depuis l'ouverture ?

    Un panneau qu'on ouvre puis qu'on referme sans rien toucher ne doit
    RIEN envoyer. C'est le geste normal — on clique un filtre pour voir
    ce qu'il propose, on le referme — et il coûtait un aller-retour plus
    un re-rendu de zone à chaque fois.

    Le drapeau vit sur l'élément (pas dans le scope) parce que c'est le
    filtre d'événement HTMX qui le relit, et celui-ci s'évalue avec
    ``this`` = l'élément, hors de toute portée de signal.

    ⚠️ L'instantané se prend à la TRANSITION, pas à chaque tick : cet
    effet dépend de la valeur, donc il re-tourne à chaque coche. Le
    re-prendre alors le rendrait toujours égal au courant — le panneau ne
    serait jamais sale, et le handler ne partirait plus jamais. Le garde
    ``_bzOpenWas`` est ce qui distingue « on vient d'ouvrir » de « on est
    ouvert et ça bouge ».

    Les valeurs sont TRIÉES avant comparaison : décocher puis recocher
    la même valeur la remet en fin de tableau, et un ordre différent
    n'est pas un changement de sélection.
    """
    return (
        f"((v) => {{ "
        f"if ($el._bzOpenWas === v) return; "
        f"$el._bzOpenWas = v; "
        f"const s = JSON.stringify([...({picked_js})].map(String).sort()); "
        f"if (v) {{ $el._bzOpenSnap = s; }} "
        f"else {{ $el.{CHANGED_FLAG} = s !== $el._bzOpenSnap; }} "
        f"}})(!!({open_expr}))"
    )


#: The events :func:`_dispatch_arm` fires ON THE ROOT. A server handler
#: wired to one of them must keep its HTMX bundle THERE — relocating it
#: onto a value carrier or a focusable child points the listener at an
#: element that never sees the event, and the handler dies silently (no
#: error, no POST : the ``EVENTS`` + ``on_X=`` dead-letter shape of
#: ``traps.md``).
#:
#: Declared here, next to the effect that dispatches them, rather than as
#: each component's private list of what DOES relocate : that inverted
#: form is a whitelist you have to remember to extend, and forgetting is
#: the silent failure it was meant to prevent.
ROOT_DISPATCHED_EVENTS = frozenset({"open", "close"})


def floating_placement(position: str, align: str) -> str:
    """Theme ``position`` + ``align`` → a ``$bz.helpers.floating`` placement.

    The floating helper takes ``"<side>"`` or ``"<side>-<align>"`` ;
    ``center`` is its default so we drop it to keep the string tidy.

    Lives here, next to :func:`anchored_panel_effect` which consumes its
    output, because Popover and Dropdown each carried a private copy
    (audit F58) — the same converter feeding the same helper, maintained
    twice.
    """
    return position if align in ("center", "") else f"{position}-{align}"


def anchored_panel_effect(
    open_expr: str,
    placement: str,
    *,
    trigger_ref: str = "bztrigger",
    match_width: bool = False,
) -> str:
    """Panel ``bz-effect`` for anchored overlays.

    Toggles the panel's ``display`` AND attaches / detaches
    ``$bz.helpers.floating`` against the trigger. Display is set
    BEFORE floating measures (so ``offsetWidth`` is correct in the
    same synchronous run — no flash, no zero-size measure).

    Anchor resolution adapts to the trigger shape. Popover / Dropdown /
    Tooltip wrap their trigger in a ``display:contents`` span (no box of
    its own) so we anchor on its ``firstElementChild`` — the real
    trigger box. Select / Combobox put ``bz-ref="bztrigger"`` directly
    on the trigger ``<button>`` / ``<div>`` (a real box), so we anchor
    on the ref itself ; using ``firstElementChild`` there would anchor
    on an inner label span / pills row and mis-align the panel. The
    ``display:contents`` probe picks the right one at runtime without a
    per-component flag. Falls back to the panel's previous sibling if
    the ref is missing.

    ``match_width=True`` pins the panel's width to the trigger's — min
    AND max, so a long option wraps inside the trigger's box instead of
    growing the panel toward the viewport edge (native ``<select>``
    look). Used by Select / Combobox, and by personne d'autre : Dropdown,
    Popover, Tooltip et les pickers laissent leur panneau à sa largeur
    naturelle.

    ⚠️ **Le pincement a un plancher**, posé dans ``floating()``
    (``MIN_MATCHED_WIDTH``, 192 px) : sous une gâchette plus étroite que
    ça — un ``ui.select`` dans une sidebar repliée en ``rail``, mesuré à
    31 px — le panneau rendait la largeur de la gâchette et enroulait ses
    libellés lettre par lettre. Au-dessus du plancher le comportement est
    inchangé, à l'identique.

    The floating instance is re-attached (detach + fresh attach, which
    re-resolves the anchor and re-pins the panel) in TWO cases while the
    panel stays open :

    - **placement CHANGED** : a server refresh rewrote ``position`` /
      ``align`` on an open popover, re-running this effect with a new
      placement literal. Without re-attaching, the already-attached
      instance (pinned to the old placement) would never update — the
      panel would stay put (cf. the popover server playground).
    - **inline position WIPED** (``$el.style.position !== 'fixed'``) : a
      morph of the panel's own @refreshable zone re-stamps the SSR
      ``style`` attribute (``display:none``), clobbering the inline
      ``position:fixed; top; left`` that ``floating`` had set. The
      ``_bzFloat`` guard alone would see the instance still "attached"
      and skip re-positioning, so the panel falls back to its themed
      ``position:absolute`` with no offsets and paints ON TOP of the
      trigger. Re-attaching restores the fixed coordinates. (This is the
      "popover covers the button after an on_open refresh" bug —
      reproduced in ``experiments/v3/runtime/probe_overlay_refresh.py``.)
    """
    opts = (
        "{placement: __p, matchWidth: true}"
        if match_width
        else "{placement: __p}"
    )
    return (
        f"((v) => {{ "
        f"$el.style.display = v ? '' : 'none'; "
        f"const __p = '{placement}'; "
        f"if (v) {{ "
        # Re-attach when the placement changed (server rewrote
        # position/align) OR the inline position was wiped by a morph
        # (re-stamped SSR style) — either way we detach so the block
        # below re-attaches, re-resolving the anchor and re-pinning.
        f"if ($el._bzFloat && "
        f"($el._bzFloatP !== __p || $el.style.position !== 'fixed')) {{ "
        f"$el._bzFloat(); $el._bzFloat = null; }} "
        f"if (!$el._bzFloat) {{ "
        f"const __t = $refs.{trigger_ref}; "
        f"const __a = __t "
        f"? (getComputedStyle(__t).display === 'contents' "
        f"? (__t.firstElementChild || __t) : __t) "
        f": $el.previousElementSibling; "
        f"$el._bzFloat = $bz.helpers.floating(__a, $el, {opts}); "
        f"$el._bzFloatP = __p; }} "
        f"}} else if ($el._bzFloat) {{ "
        f"$el._bzFloat(); $el._bzFloat = null; }} "
        f"}})(!!({open_expr}))"
    )


def anchored_trigger_wrapper(
    node: Any,
    *,
    open_expr: str,
    haspopup: str,
    on_click: str | None = None,
) -> Element:
    """Wrap a caller-supplied trigger for an anchored overlay.

    The ``display:contents`` box is not cosmetic and not optional :
    :func:`anchored_panel_effect` probes ``getComputedStyle(ref).display
    === 'contents'`` to decide whether to anchor on the ref or on its
    ``firstElementChild``. A wrapper that loses ``class="contents"`` or
    ``bz-ref="bztrigger"`` makes the panel anchor on a zero-size box —
    off-screen, silently.

    Popover, Dropdown and Combobox each wrote this by hand, differing
    only in ``aria-haspopup`` (``dialog`` / ``menu`` / ``listbox``) and,
    for Combobox, in the click body (it also hands the keyboard to the
    search field). Three copies of a contract no test covers is the
    repo's own threshold for extracting a primitive.

    ``on_click`` defaults to the plain toggle ; pass one when the trigger
    has to do more than flip the flag.
    """
    return Element(
        tag="div",
        attrs={
            "class": "contents",
            "bz-ref": "bztrigger",
            "bz-on:click": on_click or f"{open_expr} = !{open_expr}",
            "aria-haspopup": haspopup,
            "bz-attr:aria-expanded": bool_attr(f"{open_expr}"),
        },
        children=(node,),
    )


def anchored_dismiss_init(open_expr: str) -> str:
    """Root ``bz-init`` for anchored overlays : Escape + click-outside.

    Both registered once at mount. ``clickOutside`` targets the ROOT
    (which contains the trigger) AND is handed ``() => $refs.bzpanel`` as
    the "also inside" element : every anchored overlay teleports its panel
    to ``<body>`` (out of the root's subtree), so without this a click
    ANYWHERE in the panel counts as outside and dismisses. That's mostly
    masked for menus (an enabled item dispatches its own close first, so
    the deferred dismiss is a no-op) — but a click that dispatches NOTHING
    (a disabled row, the panel's own padding, rich Popover content) would
    close the overlay. The guard resolves the ref on EACH click (the
    teleported panel registers its ref after this handler is wired, so it
    can't be captured up front) and every overlay names its panel
    ``bz-ref="bzpanel"``.

    The click-outside dismiss is DEFERRED (``setTimeout 0``) with a
    double guard so an EXTERNAL control handling the SAME click wins the
    race. ``clickOutside`` fires in the CAPTURE phase — BEFORE a sibling
    button's bubble-phase ``bz-on:click`` runs the command it carries
    (``.toggle()`` / ``.open()`` from ``_dispatch_command``). A
    synchronous ``open = false`` here would land first, then the
    command's ``open = !open`` would read ``false`` and RE-OPEN — the
    overlay could never be closed by an outside toggle (the ".toggle()
    only opens" bug). So : snapshot ``open`` at click time (``__w``) and
    only dismiss if it was open THEN **and** is still open after the
    click's handlers ran. A toggle that CLOSED it leaves ``open=false``
    → skip ; a toggle that OPENED it had ``__w=false`` → skip ; a genuine
    outside click leaves ``open`` unchanged (true) → dismiss.

    Why ``setTimeout`` and NOT ``queueMicrotask`` : for a TRUSTED click
    the browser runs a microtask checkpoint BETWEEN each event listener
    (the JS stack empties between the capture and bubble listeners of a
    user click), so a microtask scheduled in the capture phase runs
    BEFORE the bubble-phase toggle — the exact race we're trying to
    escape (it fired ``open=false`` first, then the toggle re-opened).
    A macrotask (``setTimeout``) is the earliest defer that is
    GUARANTEED to run only after the WHOLE click event finished both
    phases. A naive defer WITHOUT ``__w`` also breaks the open direction
    (open→callback sees true→re-closes). Cf. ``traps.md`` § *anchored
    overlay .toggle() only opens (microtask-between-listeners)*.
    """
    return (
        f"$bz.helpers.escapeKey(() => {{ "
        f"if ($el.isConnected && ({open_expr})) {{ {open_expr} = false; }} }}); "
        f"$bz.helpers.clickOutside($el, () => {{ "
        f"const __w = ({open_expr}); "
        f"setTimeout(() => {{ "
        f"if ($el.isConnected && __w && ({open_expr})) {{ {open_expr} = false; }} "
        f"}}, 0); }}, () => $refs.bzpanel)"
    )


def imperative_listeners(open_expr: str) -> dict[str, str]:
    """``bz-on:bz-open/close/toggle`` — the imperative-API receivers.

    Harmless when ``open=`` is bound (the binding's own setter writes
    the path directly, the event never fires) ; uniform for both cases
    keeps the contract simple. Cf. ``.claude/bretzel/imperative-api.md``.
    """
    return {
        "bz-on:bz-open": f"{open_expr} = true",
        "bz-on:bz-close": f"{open_expr} = false",
        "bz-on:bz-toggle": f"{open_expr} = !{open_expr}",
    }


def install_open_close_toggle(component: Any, prop: str = "open") -> None:
    """Installe l'API impérative write-only ``.open()`` / ``.close()`` /
    ``.toggle()`` en ATTRIBUTS D'INSTANCE sur ``component``.

    Byte-identique sur tout overlay open-driven (Dialog / Drawer / Dropdown /
    Popover) : chaque méthode write-through le binding ``prop`` s'il a été
    passé à la construction, sinon dispatch une commande DOM que le root
    (via :func:`imperative_listeners`) rattrape. L'assignation est
    per-instance À DESSEIN — elle SHADOW le descripteur ``reactive_prop``
    ``open`` (non-data-descriptor, pas de ``__set__``) : ``dialog.open``
    renvoie le callable, le descripteur reste dans le class-dict pour la
    collecte ``__reactive_props__`` + le routage kwarg. Doit tourner dans
    ``__init__`` APRÈS ``super().__init__`` (a besoin de ``_binding_metadata``
    peuplé). Retire les 3 ``def _imperative_*`` + 3 assignations recopiés
    dans chaque overlay. Cf. imperative-api.md ; gardé par
    ``test_imperative_classvar`` (les noms sont callables sur l'instance).
    """
    # ``_commanded`` : « quelqu'un a demandé une commande sur moi ».
    # C'est ce qui distingue un composant qu'on peut piloter d'un
    # composant que rien n'atteint — la question que pose
    # :func:`check_sidebars_are_reachable`. Posé ici plutôt que chez
    # l'appelant parce que les deux tiers de l'API passent par là : le
    # composant tier 1 (``ui.sidebar_trigger``) comme l'échappatoire
    # tier 2 (``on_click=sb.toggle()``).
    def _open() -> str:
        component._commanded = True
        binding = component._binding_metadata.get(prop)
        if binding is not None:
            return binding.set(True)
        return component._dispatch_command("bz-open")

    def _close() -> str:
        component._commanded = True
        binding = component._binding_metadata.get(prop)
        if binding is not None:
            return binding.set(False)
        return component._dispatch_command("bz-close")

    def _toggle() -> str:
        component._commanded = True
        binding = component._binding_metadata.get(prop)
        if binding is not None:
            return binding.toggle()
        return component._dispatch_command("bz-toggle")

    component.open = _open
    component.close = _close
    component.toggle = _toggle


def install_value_commands(
    component: Any,
    *,
    empty: Any = "",
    focus_selector: str | None = None,
) -> None:
    """Installe ``.set()`` / ``.clear()`` / ``.focus()`` / ``.blur()``.

    Le jumeau de :func:`install_open_close_toggle`, pour l'autre moitié
    de l'API impérative : celle des composants qui portent une VALEUR.

    Pourquoi une fabrique ici plutôt que quatre méthodes par classe
    ---------------------------------------------------------------
    Parce que les six pickers sont arrivés SANS aucune surface
    impérative — le seul groupe entier du catalogue dans ce cas
    (mesuré le 2026-09-02 : 22 composants en avaient une, eux zéro) —
    et que les leur écrire à la main aurait recopié le même bloc six
    fois. C'est exactement la forme de dette que ce module existe pour
    éviter.

    ``Input``, ``Select`` et ``Combobox`` gardent leurs propres méthodes,
    et ce n'est pas une deuxième convention : leurs ``focus`` visent des
    éléments RÉELLEMENT différents (la racine, un ``[role=combobox]``,
    un ``input[type=text]``), et leur ``clear`` dépend d'un mode
    ``multiple``. Ce qu'ils partagent — ``set`` = ``_value_command`` —
    tient en une ligne.

    ``focus_selector`` désigne l'élément à viser DANS le composant ;
    ``None`` vise la racine. Les six pickers rendent tous un ``<input>``
    en premier élément focusable (vérifié sur le HTML rendu des six),
    d'où leur ``"input"`` commun.
    """

    def _set(value: Any) -> str:
        return component._value_command(value)

    def _clear() -> str:
        return component._value_command(empty)

    def _cible() -> str:
        racine = f"document.getElementById('{component.id}')"
        return racine if focus_selector is None else (
            f"{racine}.querySelector('{focus_selector}')"
        )

    def _focus() -> str:
        return f"{_cible()}.focus()"

    def _blur() -> str:
        return f"{_cible()}.blur()"

    component.set = _set
    component.clear = _clear
    component.focus = _focus
    component.blur = _blur


# ── Dismiss client-local (Alert / Badge / Banner) ────────────────────────
#
# Le dismiss « pur client » partagé par la famille feedback dismissible :
# un flag ``bz-data="{open: true}"`` + ``bz-show="open"`` sur le root, et un
# × qui fait ``open = false`` (cache) + ``$dispatch('close')`` (remonte
# l'event que ``on_close=`` écoute). Recopié à l'identique 3× — extrait ici.

#: Le handler du bouton × : cache le composant en client ET redispatche
#: ``close`` pour que le ``on_close=`` serveur/client se déclenche.
DISMISS_TOGGLE_CLICK = "open = false; $dispatch('close')"


def close_handler_wired(attrs: dict[str, Any]) -> bool:
    """True si un handler ``close`` est câblé sur ``attrs`` — server
    (``hx-trigger="close"``) ou client (``bz-on:close``).

    Encode la règle « déclarer un ``on_close=`` DOIT faire apparaître
    l'affordance × qui le déclenche » : sans elle, le handler était un
    dead-letter silencieux (aucun × ne dispatchait jamais ``close``). Le
    peek recopié à l'identique dans Alert / Badge / Banner.
    """
    return attrs.get("hx-trigger") == "close" or "bz-on:close" in attrs


def dismiss_local_scope() -> dict[str, str]:
    """Le scope client-local du dismiss : ``bz-data="{open: true}"`` +
    ``bz-show="open"`` à poser sur le root. Keyé par ``bz-id`` (survit aux
    morphs) ; pas de FOUC pre-stamp (l'éval initiale ``open: true`` est
    truthy). Recopié à l'identique dans Alert / Badge / Banner."""
    return {"bz-data": "{open: true}", "bz-show": "open"}


def dismiss_button(
    *,
    button_class: str,
    aria_label: str,
    icon_size: str = "sm",
    on_click: str = DISMISS_TOGGLE_CLICK,
    extra_attrs: dict[str, Any] | None = None,
) -> Element:
    """Le bouton x — UNE émission pour tout le framework.

    ``on_click`` par défaut = le toggle local du dismiss (famille feedback :
    Alert / Badge / Banner). FileUpload le surcharge : son x retire UNE
    entrée d'une liste, pas le composant entier. Le geste diffère, la
    CONSTRUCTION est la même — c'est elle que ce helper single-source, et
    c'était le dernier x fait à la main (il émettait un ``<iconify-icon>``
    brut avec ``lucide:`` en dur, donc sans le FOUC ni le set d'icônes du
    thème — finding #2 de l'audit de composition).

    Avant : le *wiring* (``DISMISS_TOGGLE_CLICK`` / ``dismiss_local_scope``
    / ``close_handler_wired``) était single-sourcé ici, mais la
    **construction du bouton** avait dérivé en 3 formes — Alert via
    ``IconButton`` (detach ✓), Badge/Banner en ``<button>`` brut + Icon
    (Banner avait oublié le detach → le × fuyait à la racine via
    ``serialize_html``). Ce helper referme l'axe *construction* comme le
    wiring l'était déjà :

    - **detach baked-in** : l'Icon est construit puis
      :meth:`Component.render_detached` — impossible de refaire fuir un ×.
    - **gating bz-show/FOUC single-sourcé** : ``(path) && open`` +
      pre-stamp ``display:none`` quand le snapshot SSR est falsy. (Alert
      omettait le ``&& open`` — drift harmonisé ; sans effet observable,
      le × vit dans un root déjà masqué par ``bz-show="open"``.)

    Les **strings de style restent par-thème** : ``button_class`` est
    composé par l'appelant depuis SON thème (cf.
    ``feedback_no_shared_style_tokens`` — on factorise la logique, pas les
    tokens visuels).

    ⚠️ Le × n'a plus de gating ``bz-show`` : il vivait pour un
    ``dismissible=<ClientBinding>`` que les trois constructeurs REFUSENT
    depuis la coupe du 2026-07-16 (``dismissible`` n'est dans aucun
    ``BINDABLE_PROPS``). Les paramètres ``show_path`` / ``hidden_ssr``
    étaient donc toujours à leur défaut — retirés (audit F05/F06/F07).
    Le × vit de toute façon dans une root déjà masquée par
    ``bz-show="open"``.
    """
    # Deferred : base.component dépend de base._wiring, top-level = cycle.
    from bretzel.components.base.component import (
        Component,
    )
    from bretzel.components.primitives.icon import Icon

    attrs: dict[str, Any] = {
        "type": "button",
        "class": button_class,
        "aria-label": aria_label,
        f"{BZ_ON_PREFIX}click": on_click,
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    return Element(
        tag="button",
        attrs=attrs,
        children=(Component.render_detached(Icon("x", size=icon_size)),),
    )


def teleport_to_body(panel: Node, owner: Any = None) -> Node:
    """Wrap an overlay ``panel`` in a ``<template bz-teleport="body">`` so the
    runtime projects it under ``<body>`` at init.

    **Périmètre réel : les overlays ANCRÉS seulement** — Tooltip, Popover,
    Dropdown, et le popover de `SidebarFooter`. Ils sont ``position: fixed``
    et flottent contre leur trigger, donc n'importe quel ancêtre à
    ``overflow`` (un conteneur scrollable, l'``overflow-hidden`` d'une
    ``Card``) ou à contexte d'empilement / ``transform`` les clipperait ou
    les mal-superposerait.

    ⚠️ **Dialog et Drawer ne passent PAS par ici**, contrairement à ce que
    cette docstring annonçait jusqu'au 2026-08-01 en disant couvrir les
    panneaux « modal ». C'est une abstention, pas un oubli constaté : leur
    backdrop plein écran les rend moins sensibles au clipping, et aucun
    ancêtre ``transform`` n'a été trouvé dans le shell actuel. Le risque
    reste **latent** — un layout applicatif qui poserait un ``transform``
    au-dessus d'un Dialog en ferait le containing block. À trancher :
    téléporter les modaux aussi, ou garder l'abstention (cf. `todo.md`).
    Teleporting to ``<body>`` frees the panel from those traps ; the runtime
    keeps the projected clone bound to THIS component's ORIGIN scope
    (``node._bzScopeHost = template`` — bare signal names and ``$refs`` still
    resolve here, and morphs re-project on content change). Cf.
    ``runtime/_src/02_directives.js::bindTeleport`` + traps.md.

    ``bz-teleport`` is a STRUCTURAL directive on a ``<template>`` : the runtime
    moves the template's *content* (the panel) to the target, not the template
    element itself. So the panel becomes the template's single child.

    ``owner`` — LE PONT DE COULEUR VOYAGE AVEC LE PANNEAU
    ------------------------------------------------------

    Les paliers (``--bz-bg``, ``--bz-text``…) sont des propriétés
    héritées, posées par la classe-pont sur la racine du composant. Un
    panneau téléporté sous ``<body>`` **n'est plus un descendant de cette
    racine** : il perd donc les onze paliers d'un coup, et rend sans
    couleur — sans erreur et sans trace, puisqu'une propriété custom
    indéfinie rend simplement la déclaration invalide.

    Passer ``owner`` recopie le pont sur le panneau lui-même. C'est fait
    ICI, au point d'assemblage, et pas dans chaque composant : le
    Tooltip est le seul concerné aujourd'hui (le Dropdown, le Popover et
    le pied de Sidebar n'écrivent aucune couleur dans leur panneau), mais
    le prochain overlay coloré n'aurait aucune raison d'y penser.
    """
    if owner is not None:
        bridge = color_bridge_class(owner, panel)
        if bridge is not None:
            panel = _append_class(panel, bridge)
    return Element(
        tag="template",
        attrs={"bz-teleport": "body"},
        children=(panel,),
    )



def _refuse_unknown_color(component: Any, color: str) -> None:
    """Lever si ``color`` n'a pas de pont — donc pas de paliers.

    ⚠️ **Ce refus est la moitié qui reste d'une gate**, et il a failli
    disparaître avec la dépose du 2026-08-30.

    ``resolve_slot_or_keyword`` levait sur une couleur inconnue depuis le
    2026-08-18, après le bug mesuré sur ``ui.badge(color="neutral")`` :
    ça se construisait, ça se rendait, ``bretzel check`` ne disait rien,
    et l'élément sortait **sans style en production** — parce que la
    classe résolue n'existait dans aucune source, donc dans aucun CSS
    compilé. Correct en dev (le compilateur navigateur scanne le DOM
    vivant), mort en prod, HTML identique des deux côtés.

    Les paliers ont changé le mécanisme et **pas** le mode d'échec :
    ``bz-c-neutral`` est une classe sans règle, donc les douze paliers
    sont indéfinis, donc toute déclaration qui les lit est invalide. Le
    composant rend nu, sans erreur. Il fallait donc redéposer le refus
    ici, à l'endroit où le nom de couleur est maintenant consommé.

    Hors contexte de rendu (un banc, un test unitaire) on ne peut pas
    lire la palette : on se tait plutôt que de refuser à tort.
    """
    from bretzel.render.context import maybe_current_context

    ctx = maybe_current_context()
    theme = getattr(getattr(ctx, "app", None), "theme", None)
    getter = getattr(theme, "get_palette", None)
    if not callable(getter):
        return

    from bretzel.theme.bridges import bridged_color_names

    known = bridged_color_names(getter())
    if color in known:
        return
    raise ComponentUsageError(
        f"{type(component).__name__}(color={color!r}) : couleur inconnue.\n"
        f"  Les couleurs disponibles sont {sorted(known)}.\n"
        "  Une couleur hors de cette liste n'a pas de classe-pont, donc "
        "aucun palier : le composant rendrait SANS style, sans erreur et "
        "sans trace — et seulement en production, parce que le "
        "compilateur de dev scanne le DOM vivant.\n"
        "  Pour ajouter une couleur de marque : "
        '``Theme(palette={"brand": "#..."})``.'
    )


def _append_class(node: Node, extra: str) -> Node:
    """``node`` avec ``extra`` ajouté à sa ``class``."""
    if not isinstance(node, Element):
        return node
    current = str(node.attrs.get("class", "")).strip()
    return Element(
        tag=node.tag,
        attrs={**node.attrs, "class": f"{current} {extra}".strip()},
        children=node.children,
    )


#: Le motif d'une valeur COMPLÈTE, par granularité de picker.
#:
#: C'est la seule chose qui distinguait le miroir de MonthPicker de celui
#: de ses trois voisins — et c'est pour cet écart d'un caractère qu'il en
#: portait une quatrième copie écrite à la main. Le garde qu'ils
#: encodent est le même partout : n'écrire QUE ce qui est complet, sinon
#: une frappe en cours (« 2026-0 ») effacerait la sélection du
#: calendrier.
_COMPLETE_VALUE_RE: dict[str, str] = {
    "day": "/^\\d{4}-\\d{2}-\\d{2}$/",
    "month": "/^\\d{4}-\\d{2}$/",
}


def calendar_value_mirror(
    value_expr: str, *, is_range: bool, granularity: str = "day"
) -> str:
    """``bz-effect`` body mirroring ``value_expr`` onto a child
    ``<bz-calendar>``'s observed ``value`` ATTRIBUTE.

    V3 ``bz-attr:value`` on a custom element writes the JS *property*,
    which skips ``attributeChangedCallback`` — so the date pickers do
    an explicit ``setAttribute`` from the wrapper instead (cf.
    ``traps.md`` § *bz-attr value on a custom element*). The body :

    - captures ``value_expr`` ONCE (so a bound store path is read a
      single time per tick, not 2-3×) ;
    - pushes the empty string to clear, a clean value (single) / JSON
      pair (range) to set, and ``null`` (no write) while the user is
      mid-typing a partial one ;
    - only ``setAttribute`` when the attribute actually differs.

    Shared by DatePicker and WeekPicker (``is_range=False``, scalar
    ISO), MonthPicker (``granularity="month"``, ``"YYYY-MM"``) and
    DateRangePicker (``is_range=True``, the body's caller prepends its
    own store-push fragment before this in the same single
    ``bz-effect``). Returns the inner statements — the caller wraps
    them in its ``(() => { … })()`` effect shell.

    ``granularity`` existe parce que MonthPicker en tenait une copie
    manuscrite : le helper codait ``YYYY-MM-DD`` en dur, donc le seul
    picker à valeur ``YYYY-MM`` ne pouvait pas s'en servir. Un paramètre
    plutôt qu'une divergence — c'était la 4ᵉ copie d'un piège qui a sa
    propre entrée dans ``traps.md``, la pire catégorie à laisser
    dupliquée.
    """
    iso_re = _COMPLETE_VALUE_RE[granularity]
    if is_range:
        # ``value_expr`` is a ``[start, end]`` pair expression ; the
        # caller addresses ``vstart`` / ``vend`` locals, so the mirror
        # reads them directly rather than re-capturing.
        return (
            "const cal = $el.querySelector('bz-calendar'); "
            "if (!cal) return; "
            "let _v = null; "
            "if (!vstart && !vend) _v = ''; "
            f"else if ({iso_re}.test(vstart) && {iso_re}.test(vend)) "
            "_v = JSON.stringify([vstart, vend]); "
            "if (_v !== null && cal.getAttribute('value') !== _v) "
            "cal.setAttribute('value', _v); "
        )
    return (
        "const cal = $el.querySelector('bz-calendar'); "
        "if (!cal) return; "
        f"const _val = ({value_expr}); "
        f"const _v = !_val ? '' : ({iso_re}.test(_val) ? _val : null); "
        "if (_v !== null && cal.getAttribute('value') !== _v) "
        "cal.setAttribute('value', _v); "
    )


def change_emit_effect(value_expr: str) -> str:
    """``bz-effect`` body that fires ``change`` on a hidden input.

    Runs in directive context (``$el`` / ``$nextTick`` injected, unlike a
    bz-data method body), re-evaluating ``value_expr`` on every state tick.
    Bootstraps quietly — the first run only records the baseline, so the
    SSR→hydration handoff never fires a phantom change ; a genuine change
    dispatches a bubbling ``change`` so the relocated ``hx-post`` /
    ``bz-on:change`` handler on the same input fires with a populated
    FormData. ``$nextTick`` lets the runtime flush ``bz-attr:value`` onto
    the DOM input BEFORE HTMX serialises it.

    Shared by every value-holding control that relocates its change wiring
    onto a hidden input. La population n'est PAS recopiée ici — elle l'était
    (six noms pour dix appelants, dérivé au 2026-08-21) ; elle se lit dans
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``,
    qui la DÉCOUVRE. Promoted to ``base/`` (2026-06-23) — it used to be copied
    byte-for-byte into all six because the old anti-règle 5 banned the
    cross-group import ; the rule is now "no cycles", and ``base/`` is
    importable by all, so the single source lives here.
    """
    return (
        f"((v) => {{ "
        f"if ($el._bzLast === undefined) {{ $el._bzLast = v; }} "
        f"else if (v !== $el._bzLast) {{ $el._bzLast = v; "
        f"$nextTick(() => $el.dispatchEvent("
        f"new Event('change', {{bubbles: true}}))); }} "
        f"}})({value_expr})"
    )


# ── Server-action wire attrs — the ONE definition ────────────────────
# The native-HTMX bundle ``emit_attrs`` stamps on a component root for a
# callable ``on_change=`` handler : ``hx-post`` + ``hx-trigger`` +
# ``hx-target`` + ``hx-swap`` + optional ``hx-vals`` + the HMAC stamps
# ``data-bz-sig`` / ``data-bz-ts``. Value-holding controls whose root
# carries no ``name`` / ``value`` (Accordion, Pagination, Tree, Tabs,
# Select, Combobox, ToggleGroup, Slider, NumberInput, Calendar) relocate
# this bundle onto a hidden ``<input>`` so the dispatched FormData is
# non-empty (cf. traps.md § "bz-event:change sur un div").
#
# ``DATA_BZ_TS`` MUST travel with ``DATA_BZ_SIG`` : the HMAC v2 signature
# is computed over ``action_id|args|render_ts`` and the bridge reads the
# ts off ``closest("[data-bz-sig]")`` — i.e. the SAME element as the sig.
# Relocating the sig without the ts leaves the ts on the (now
# handler-less) root, so the bridge forwards an empty ``X-Bz-Ts`` and
# every POST 403s. This bit the framework once already : at the HMAC-v2
# rollout four component-LOCAL copies of this tuple missed ``data-bz-ts``
# (cf. traps.md § "data-bz-ts oublié au relocate"). There are now NO
# component-local copies — every value-holding control imports
# ``SERVER_ACTION_ATTRS`` from here, so the sig+ts couple can only change
# in one place. Guarded by ``tests/consistency/test_action_wire_attrs.py``.
SERVER_ACTION_ATTRS: tuple[str, ...] = (
    "hx-post",
    "hx-trigger",
    "hx-target",
    "hx-swap",
    "hx-vals",
    DATA_BZ_SIG,
    DATA_BZ_TS,
)

# ``SERVER_ACTION_ATTRS`` plus the string-handler shape ``bz-on:change``.
# Controls that relocate BOTH handler shapes off the root (Accordion,
# Pagination, Tree, Tabs) pop this superset ; the rich inputs route the
# string handler per-event separately and relocate only
# ``SERVER_ACTION_ATTRS``.
CHANGE_HANDLER_KEYS: tuple[str, ...] = (
    *SERVER_ACTION_ATTRS,
    f"{BZ_ON_PREFIX}change",
)


def trigger_event(attrs: Mapping[str, Any]) -> str:
    """L'EVENT que sert ``hx-trigger``, sans ses modificateurs.

    ``action_attrs`` écrit ``hx-trigger`` sous la forme
    ``"<event> [modificateur] [from:#id]"`` — le modificateur venant d'un
    ``debounce=`` (``delay:300ms``) ou d'un ``throttle=``. **L'event est
    le premier mot, jamais la chaîne entière.**

    Pourquoi ce lecteur existe (mesuré le 2026-08-19)
    -------------------------------------------------
    Sept sites de relocation comparaient la CHAÎNE ENTIÈRE au nom d'un
    event (``== "change"``, ``in ("focus", "blur")``) ou, pire, y
    cherchaient une sous-chaîne (``"change" in trigger``). Poser un
    ``debounce=`` faisait donc échouer la comparaison — et chaque site
    échouait DIFFÉREMMENT :

    ===================================  ==================================
    ``ui.combobox(on_change=, debounce=)``   le bundle popé n'était re-posé
                                             nulle part → ``hx-post``
                                             **disparu**, handler mort
    ``ui.toggle_group(…)`` idem              bundle laissé sur la racine,
                                             qui ne fire pas ``change`` →
                                             handler mort
    ``ui.file_upload(on_focus=, …)``         idem sur le wrapper focusable
    Select / Slider / les 4 pickers          modificateur écrasé → le
                                             ``debounce=`` demandé
                                             **silencieusement perdu**
    ===================================  ==================================

    Et le test par sous-chaîne était faux dans l'autre sens aussi :
    ``"change" in "month_change"`` est vrai, donc le jour où Calendar
    adopterait :func:`relocate_server_action`, son ``on_month_change``
    partirait sur le porteur de valeur avec un trigger réécrit en
    ``change``.

    Gaté par ``tests/consistency/test_trigger_modifiers_survive.py``.
    """
    return str(attrs.get("hx-trigger", "")).split(" ", 1)[0]


def retrigger(trigger: str, event: str) -> str:
    """Renommer l'event d'un ``hx-trigger`` en GARDANT ses modificateurs.

    Calendar rebaptise ``month_change`` en la CustomEvent kebab
    ``month-change`` ; réécrire la chaîne entière jetterait le
    ``delay:`` que ``debounce=`` y avait mis.
    """
    _, separator, modifiers = str(trigger).partition(" ")
    return event + separator + modifiers


def pop_change_handler(attrs: dict[str, Any]) -> dict[str, Any]:
    """Pop every change-handler attribute out of ``attrs`` (in place).

    Returns the popped subset — empty when no ``on_change`` was wired.
    The caller stamps the result onto its hidden form input.

    ⚠️ **Ne convient qu'aux composants MONO-CIBLE** — ceux dont
    ``EVENTS`` ne contient que ``("change",)``, donc pour qui « le seul
    bundle serveur est le change » est un invariant vrai (Tabs, Pagination,
    Tree, Accordion). Un composant qui expose aussi ``focus`` / ``blur``
    doit passer par :func:`relocate_server_action`, qui ROUTE au lieu de
    tout déplacer vers une cible unique.
    """
    return {key: attrs.pop(key) for key in CHANGE_HANDLER_KEYS if key in attrs}


#: ``dispatch=`` par défaut : « la même expression que la valeur ». Une
#: chaîne impossible à écrire par accident, plutôt qu'un ``None`` qui
#: voudrait dire deux choses (« par défaut » et « surtout pas »).
_SAME_AS_VALUE = "\x00same-as-value"


def hidden_carrier_attrs(
    value_expr: str,
    *,
    initial: Any = "",
    ref: str = "bzhidden",
    dispatch: str | None = _SAME_AS_VALUE,
) -> dict[str, Any]:
    """Le SQUELETTE d'un ``<input type="hidden">`` porteur de valeur.

    Un ``<div>`` ne porte ni ``name``/``value`` ni ``change`` natif. Les
    composants dont la racine n'est pas un contrôle de formulaire posent
    donc un input caché qui fait les deux — 12 sites dans 11 fichiers.

    Ce helper rend les **cinq attributs invariants** :

    - ``type="hidden"`` ;
    - ``bz-ref`` — comment le scope retrouve le porteur ;
    - ``value`` — la valeur SSR, pour que le premier POST parte juste même
      avant que le runtime ait booté ;
    - ``bz-attr:value`` — la liaison réactive qui la tient à jour ;
    - ``bz-effect`` — :func:`change_emit_effect`, **le dispatcher sans
      lequel tout ce qui précède est muet**.

    Le dispatcher est entré ici le 2026-08-21, et c'est une INVERSION
    -------------------------------------------------------------------
    Il était laissé à l'appelant, au nom d'un argument écrit noir sur
    blanc : « le dispatch de ``change`` diffère réellement
    (``change_emit_effect`` pour la plupart, une méthode de scope pour
    Slider) ». **Slider n'est pas un appelant** — il écrit son squelette à
    la main (déclaré dans ``_SKELETON_DEBT``), comme Calendar et Dropzone,
    les deux autres qui dispatchent depuis le runtime. Le contre-exemple
    qui justifiait la variance ne vivait donc pas dans la population
    concernée : sur les **dix** appelants réels, dix posent
    ``change_emit_effect``, et **neuf** sur la même expression que celle
    qu'ils viennent de passer ici.

    Ce que ça coûtait : le porteur relocalise le bundle ``hx-post`` d'un
    ``on_change=`` serveur — mais un input caché ne fire jamais ``change``
    tout seul, et une écriture programmatique de ``.value`` n'émet aucun
    événement. Oublier le ``bz-effect``, c'est donc un contrôle INERTE,
    sans erreur ni avertissement. Les cinq pickers de date l'ont oublié,
    et personne ne l'a vu avant qu'un humain se serve de l'app.

    D'où l'inversion : le dispatch est **acquis**, et on le refuse
    explicitement (``dispatch=None``) ou on le pose sur une autre
    expression (``dispatch=<expr>``, le cas de ToggleGroup dont la valeur
    postée et la valeur observée diffèrent). Un opt-out se relit ; un
    opt-in s'oublie.

    ⚠️ **``name`` et ``required``, eux, restent à l'appelant.**

    ``name`` est le cas important : coller un ``name="value"`` par défaut à
    un ``Tabs`` ou un ``Accordion`` injecterait un **champ parasite dans
    chaque formulaire englobant**. Un Tabs n'est pas un contrôle de
    formulaire — il n'a un ``name`` que si l'appelant en veut un. C'est une
    variance LÉGITIME, et un ``hidden_carrier_input`` qui l'uniformiserait
    uniformiserait un bug. ``required`` ne concerne, lui, que les contrôles
    de formulaire.

    Gaté par ``tests/consistency/test_hidden_carrier_skeleton_is_shared.py``
    (le squelette sort d'ici) et
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``
    (aucun porteur muet ne reçoit d'action serveur) — la seconde couvre
    aussi les quatre porteurs écrits à la main, hors de portée de ce
    défaut.
    """
    attrs: dict[str, Any] = {
        "type": "hidden",
        "bz-ref": ref,
        "value": initial,
        f"{BZ_ATTR_PREFIX}value": value_expr,
    }
    if dispatch is not None:
        attrs["bz-effect"] = change_emit_effect(
            value_expr if dispatch == _SAME_AS_VALUE else dispatch
        )
    return attrs


def relocate_server_action(
    root_attrs: dict[str, Any],
    *,
    value_carrier: dict[str, Any],
    focusable: dict[str, Any],
) -> None:
    """Router le bundle d'action serveur vers la bonne cible, **en place**.

    Un composant riche a deux porteurs et ils ne sont pas interchangeables :

    - le **porteur de valeur** — un ``<input type="hidden">`` qui porte
      ``name`` + ``value`` et dispatche un ``change`` synthétique ; c'est
      lui que la FormData doit trouver ;
    - l'**élément focusable** — le trigger, le seul à recevoir nativement
      ``focus`` / ``blur``.

    Le choix se lit dans ``hx-trigger``, que ``action_attrs`` a déjà posé
    d'après l'event que le handler écoute VRAIMENT. C'est la décision que
    cette fonction retire à l'appelant.

    Pourquoi elle existe (audit du socle, item 10)
    ----------------------------------------------
    ``pop_change_handler`` ne factorisait que le **pop** — le facile — et
    laissait le **routage** — le difficile — à l'appelant. Résultat mesuré :
    4 adopteurs, tous les 4 étant justement les composants mono-cible, face
    à 8 boucles manuelles chez les composants riches.

    Et le défaut avait un coût. ``slider.py`` déplaçait le bundle vers
    l'input caché *sans regarder* ``hx-trigger``, puis forçait
    ``hx-trigger="change"`` : un ``on_focus=`` callable partait donc sur
    l'input caché, qui ne fire jamais ``focus``, et se déclenchait au
    ``change``. Pas mort — **pire que mort** : le handler s'exécutait au
    mauvais moment (un ``on_focus`` d'analytics à chaque drag).

    Le fix a été propagé À LA MAIN sur les 8 sites : les bugs sont morts,
    mais aucune primitive n'a été extraite, donc **le 9ᵉ composant
    re-déciderait seul**. C'est une réparation, pas un mécanisme — et
    c'est exactement ce que cette fonction transforme.
    """
    if "hx-post" not in root_attrs:
        return
    # ``hx-trigger`` dit sur quel event le handler serveur écoute. Un
    # bundle ``change`` rejoint le porteur de valeur — l'input caché ne
    # fire pas ``change`` tout seul, c'est ``change_emit_effect`` qui l'y
    # dispatche, et le trigger voyage avec le bundle. Tout le reste —
    # focus, blur — ne peut vivre que sur l'élément focusable.
    # ``open`` / ``close`` are dispatched ON the root by
    # ``dispatch_root_effect`` : moving their bundle anywhere else points
    # the listener at an element that never fires them. Leave it put.
    event = trigger_event(root_attrs)
    if event in ROOT_DISPATCHED_EVENTS:
        return
    bundle = {a: root_attrs.pop(a) for a in SERVER_ACTION_ATTRS if a in root_attrs}
    # ÉGALITÉ sur l'event, jamais une sous-chaîne du trigger : ``"change"
    # in "month_change"`` est vrai, et ``"change" in "input changed
    # delay:200ms"`` aussi. Cf. :func:`trigger_event`.
    if event == "change":
        # ``hx-trigger`` voyage DANS le bundle (il est dans
        # ``SERVER_ACTION_ATTRS``), donc il arrive intact sur le porteur —
        # modificateurs compris. L'ancienne ligne le réécrivait en
        # ``"change"`` nu et jetait le ``debounce=`` de l'appelant.
        value_carrier.update(bundle)
    else:
        focusable.update(bundle)


def activate_keydown(action_js: str) -> str:
    """Enter / Espace activent un élément NON natif.

    Un ``<button>`` reçoit l'activation clavier gratuitement du
    navigateur. Un ``<div role="button">`` / ``<tr role="button">`` /
    ``<div role="treeitem">`` ne reçoit **rien** : sans ce handler,
    l'élément est atteignable au Tab et totalement inerte au clavier.

    Trois modules écrivaient ce même garde de trois façons (recensement
    des affordances, 2026-07-28) — et deux des écarts étaient
    FONCTIONNELS, pas cosmétiques :

    - ``'Spacebar'``, l'ancien nom de touche (IE, vieux Firefox), n'était
      géré que par la dropzone : l'un s'activait à l'Espace, l'autre pas ;
    - la **garde de cible** ``$event.target === $el`` n'existait que dans
      Table. Sans elle, une frappe sur un contrôle ENFANT bulle jusqu'au
      parent et l'active aussi — un Espace sur un bouton imbriqué dans un
      nœud d'arbre déclenchait le nœud.

    Le helper prend le sur-ensemble correct : les trois noms de touche et
    la garde. ``action_js`` est le geste du composant — ``$el.click()``
    pour déléguer à son propre ``hx-trigger``, un appel de scope, ou du JS
    inliné.
    """
    return (
        "if ($event.target === $el && ($event.key === 'Enter' "
        "|| $event.key === ' ' || $event.key === 'Spacebar')) "
        f"{{ $event.preventDefault(); {action_js} }}"
    )


def reject_sealed(kwargs: dict[str, Any], cls: type) -> None:
    """Un prop SCELLÉ passé à l'appel : on le dit, avec une phrase.

    Un prop scellé est déclaré sur la classe et volontairement REFUSÉ à
    l'appel — l'axe d'une ``VStack`` est son identité, et le
    ``option_value`` d'un ``Radio`` est alimenté par son ``value``
    positionnel. ``bretzel.introspect`` les soustrait de la fiche, donc
    ils ne sont annoncés nulle part ; ce qui restait, c'est de bien
    répondre à qui les écrit quand même.

    ⚠️ **Promu de ``layout/stack.py`` le 2026-09-04, parce que la
    moitié de la famille n'y avait pas accès.** Les piles appelaient ce
    garde et répondaient « HStack has a fixed axis — pass no
    ``direction`` ». ``Radio`` et ``ToggleButton``, eux, laissaient la
    collision arriver jusqu'au ``super().__init__`` et rendaient ::

        TypeError: Component.__init__() got multiple values for
        keyword argument 'option_value'

    — qui ne nomme pas le composant, ne dit pas que le prop est scellé,
    et se lit comme un bug du framework. Leur commentaire assumait même
    ce message (« la passer explicitement produit un multiple
    values »), donc rien n'aurait rappelé de le réparer.

    Le refus doit rester DANS le sous-classe, avant son
    ``super().__init__`` : la collision est levée par Python au moment
    de construire l'appel, donc le socle ne la voit jamais.

    ``SEALED_REASONS`` permet à une sous-classe de scelller autre chose
    que l'axe (``Pane`` scelle ``wrap``) sans hériter d'un message faux.
    """
    reasons = getattr(cls, "SEALED_REASONS", {})
    for name in getattr(cls, "SEALED_PROPS", ()):
        if name in kwargs:
            raise ComponentUsageError(
                reasons.get(name)
                or f"{cls.__name__} has a fixed axis — pass no ``{name}``. "
                f"Use the other shortcut, or ``ui.flex(direction=…)`` for "
                f"a runtime-chosen axis."
            )


def coerce_index(
    value: Any, *, default: int = 0, minimum: int | None = None
) -> int:
    """La valeur SSR d'un index piloté — best-effort, jamais une exception.

    Trois composants portent le même archétype « index borné » —
    ``Pagination``, ``Stepper``, ``Carousel``, tous trois
    ``IMPERATIVE = ("set", "next", "prev")`` — et chacun avait sa copie
    de cette conversion, sous deux noms (``_coerce_int`` /
    ``_coerce_index``). Le seuil du dépôt (« deux fois c'est une
    coïncidence, trois fois c'est un pattern ») a été franchi le
    2026-08-02, quand Pagination a gagné le trio impératif.

    Pourquoi une conversion tolérante et pas un cast : **la valeur
    traverse une form data**. L'input caché la sérialise, donc elle
    revient en CHAÎNE (``"2"``), et un carousel piloté par un binding
    peut la recevoir vide. Le bornage FIN, lui, n'est pas ici : il vit
    dans les méthodes de scope, seul endroit qui connaisse la valeur
    vivante et la vraie borne (le nombre de pages, la géométrie de la
    piste). Ici on ne produit qu'un point de départ SSR raisonnable.

    - ``default`` : ce que vaut une valeur absente ou illisible — ``0``
      pour un index 0-based, ``1`` pour une pagination.
    - ``minimum`` : plancher optionnel, pour les index 0-based qui ne
      doivent jamais partir en négatif. ``None`` = pas de plancher (la
      pagination laisse son ``setActive`` borner).
    """
    if value is None:
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if minimum is None else max(minimum, result)


def bool_attr(expr: str) -> str:
    """Un attribut réactif qui doit porter la CHAÎNE ``"true"``/``"false"``.

    ``bz-attr`` traite un booléen comme HTML le veut : ``true`` → attribut
    **vide**, ``false`` → attribut **retiré**. C'est la bonne sémantique
    pour ``disabled`` / ``checked`` / ``required``, où la PRÉSENCE de
    l'attribut est l'information.

    Deux familles ont besoin du contraire — de la valeur littérale :

    - **ARIA** (``aria-disabled``, ``aria-expanded``, ``aria-pressed``,
      ``aria-selected``) : un lecteur d'écran lit la valeur, et la variante
      Tailwind ``aria-disabled:`` compile vers ``[aria-disabled="true"]``,
      qu'un attribut vide ne matche pas ;
    - **les ``data-*`` pilotant un style** (``data-open``, ``data-active``,
      ``data-menu-open``) : ``data-[open=true]:`` matche le littéral.

    Dans les deux cas, oublier le ternaire ne casse RIEN de visible — ni le
    style ni l'annonce ne s'appliquent, en silence. La règle était écrite en
    commentaire à trois endroits ; **dix-neuf sites la ré-implémentaient à
    la main, dont dix sans parenthéser leur opérande** (recensement des
    affordances, 2026-07-28). Elle vit ici désormais.

    Les parenthèses ne sont pas cosmétiques : ``a || b ? 'true' : 'false'``
    se lit ``(a || b) ? …`` par chance, mais toute expression plus lâche
    re-associerait. Même classe que le parenthésage de l'algèbre de
    bindings (cf. ``tests/consistency/test_client_expression_atomic.py``).
    """
    return f"({expr}) ? 'true' : 'false'"


def server_sync_marker(*props: str, enabled: bool) -> str:
    """``_serverSync`` fragment for a component's ``bz-data`` object literal.

    ``" _serverSync: ['<prop>', …],"`` when ``enabled`` (the value(s) are
    server-backed → a ``@refreshable`` morph re-adopts them from the freshly
    rendered attr, server wins) ; ``""`` otherwise (a client-owned value
    keeps its state through the morph). Accepts one OR several keys — a
    control whose scope holds several server-driven signals (calendar's
    ``year``+``month``, the range picker's ``vstart``+``vend``) lists them
    all in one marker. The ``_serverSync`` key is single-sourced from
    :data:`protocol.SERVERSYNC_KEY` and mirrored into the JS scope reader, so
    a rename can't silently strand one control. The leading space + trailing
    comma suit emission after a leading field in a ``{...}`` literal.
    """
    if not enabled:
        return ""
    keys = ", ".join(f"'{p}'" for p in props)
    return f" {SERVERSYNC_KEY}: [{keys}],"


def escape_init(open_expr: str) -> str:
    """``bz-init`` : global Escape-to-close while the overlay is open."""
    return (
        f"$bz.helpers.escapeKey(() => {{ "
        f"if ($el.isConnected && ({open_expr})) "
        f"{{ {open_expr} = false; }} }})"
    )


def outlet_target_attrs(nom_composant: str, outlet: Any) -> dict[str, str]:
    """``{"hx-target": "#outlet_<coque>"}`` pour un lien qui nomme sa région.

    Sans ``outlet=``, la coque booste tous les liens internes vers
    ``[data-bz-outlet]`` (``render/shell.py``) et htmx retient le PREMIER
    outlet du document. Avec des coques imbriquées c'est toujours le plus
    extérieur : le serveur re-rend donc la coque intérieure EN PLUS de la
    page, alors que le lien ne change que la page.

    Mesuré en A/B alterné dans le même processus le 2026-09-08, vingt
    clics par variante : **1 204 octets et 10 ms** en visant l'extérieur,
    **569 octets et 3 ms** en visant l'intérieur.

    ⚠️ **On prend la FONCTION de coque, jamais son id**, et c'est ce qui
    rend la faute impossible. L'id s'écrit ``outlet_<nom>`` ; l'écrire à
    la main donne un sélecteur qui ne matche rien, et htmx n'envoie alors
    AUCUNE requête — sans erreur, sans trace. C'est exactement ce qui est
    arrivé au banc qui a produit la mesure ci-dessus.
    """
    if outlet is None:
        return {}
    if not callable(outlet) or not hasattr(outlet, "_bz_layout"):
        raise ComponentUsageError(
            f"{nom_composant}: ``outlet=`` prend une fonction décorée "
            f"``@layout``, pas {type(outlet).__name__}. C'est la coque "
            f"dont la région doit être remplacée."
        )
    return {"hx-target": "#" + outlet_id_for(outlet.__name__)}

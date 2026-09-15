"""``Stepper`` / ``Step`` / ``StepPanel`` — progression en étapes ordonnées.

Usage ::

    with ui.stepper(value=state.step, on_change=goto):
        ui.step("Compte", description="Email et mot de passe", icon="user")
        ui.step("Adresse", description="Livraison")
        ui.step("Paiement", status="error")

        with ui.step_panel():          # panneau 0
            ui.input("Email", value=state.email)
        with ui.step_panel():          # panneau 1
            ui.input("Ville", value=state.city)

**L'étape courante est un INDEX entier, 0-based** (``value`` en JS),
comme Ant ``Steps.current`` / MUI ``activeStep`` / Mantine ``active``. Le
statut de chaque étape s'en DÉDUIT — ``index < current`` = franchie,
``== current`` = courante, ``> current`` = à venir — donc il n'y a rien à
déclarer, et la comparaison est un entier côté client. Un id par étape
aurait obligé chaque pastille à faire un ``indexOf`` dans une liste bakée
pour la même information.

``status="error"`` est le SEUL statut explicite : il fige l'étape (attribut
statique, pas de ``bz-attr``), le triptyque dérivé couvrant tout le reste.

Les panneaux sont appariés par **ordre de déclaration** — le n-ième
``ui.step_panel()`` s'affiche quand ``current == n``. Un panneau de plus
que d'étapes est légitime et c'est le point : il devient l'écran
« terminé », atteint par un dernier ``.next()`` (idiome
``Stepper.Completed`` de Mantine, sans le quatrième composant). C'est
pourquoi la borne de ``next()`` est ``max(len(steps), len(panels)) - 1``
et non ``len(steps) - 1``.

En orientation ``vertical`` les panneaux restent SOUS la liste, ils ne
s'intercalent pas entre les étapes (ce que fait MUI). C'est une
abstention, pas un oubli : intercaler dédouble la structure de rendu pour
un gain qui ne concerne que le wizard-de-formulaire vertical.

Form integration : ``names_field=True`` sur ``value`` dérive le ``name``
HTML depuis le champ lié — un ``<input type="hidden">`` porte l'index dans
la form data, et le listener de ``change`` y est relocalisé (une ``<ol>``
n'a ni ``name``/``value`` ni ``change`` natif). Idiome partagé avec Tabs /
Pagination / Accordion.

Imperative API : ``.set(i)`` / ``.next()`` / ``.prev()``. ``.set`` écrit
directement dans la binding quand il y en a une (write-through) ; ``.next``
/ ``.prev`` dispatchent TOUJOURS une commande DOM, binding ou pas — leur
résultat dépend de la valeur VIVANTE et de la borne, que le serveur ne
connaît pas au moment du rendu. Cf. ``imperative-api.md``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    reactive_prop,
    stamp_display_none,
)
from bretzel.components.base._wiring import (
    coerce_index,
    hidden_carrier_attrs,
    server_sync_marker,
    unwrap_transparent,
)
from bretzel.components.base._wiring import (
    pop_change_handler as _pop_change_handler,
)
from bretzel.components.navigation.stepper.theme import STEPPER_THEME
from bretzel.components.primitives.icon import Icon
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode


def _build_bz_data(
    *,
    scope_key: str,
    has_local_value: bool,
    initial_value: int,
    binding_path: str | None,
    max_index: int,
    server_synced: bool,
) -> str:
    """Le ``bz-data`` de l'instance : **des données, pas du code**.

    Les méthodes (``_status`` / ``goTo`` / ``next`` / ``prev``) vivent une
    seule fois dans ``$bz.stepper.scope``
    (``bretzel/runtime/_src/16_accordion.js``). Ne partent d'ici que
    l'état, l'indirection lecture/écriture, et la borne ``_max``.

    Deux modes, comme Tabs :

    - **local** : un signal ``value``. Quand la valeur vient du serveur
      (``value=state.step``), il porte ``_serverSync`` pour que le morph
      d'un ``@refreshable`` la ré-adopte — le serveur fait foi. Un
      littéral (``value=1``) s'en abstient, sinon un refresh voisin
      écraserait la navigation du client.
    - **binding** : PAS de signal local et surtout pas de getter —
      ``scope.absorb`` évalue chaque clé une fois et figerait un getter
      sur sa première valeur. Les directives et ``_read``/``_write``
      adressent directement la cellule ``$bz.state.<path>``.
    """
    # ``_max`` est de la CONFIG : le nombre d'étapes vient du serveur, le
    # client ne l'écrit jamais → re-semé sans condition. ``absorb`` ne
    # réécrit jamais un signal existant, donc sans ça un stepper qui gagne
    # ou perd une étape gardait son ancienne borne (``next()`` bloquait sur
    # l'ancien maximum). Même racine que ``_total`` de Pagination.
    config_sync = ["_max"]
    if has_local_value:
        # La VALEUR reste gatée : sans propriété serveur, un refresh voisin
        # écraserait l'étape que le client vient d'atteindre.
        keys = [scope_key, *config_sync] if server_synced else config_sync
        sync = server_sync_marker(*keys, enabled=True)
        state = f"{scope_key}: {json.dumps(initial_value)},{sync} "
        target = f"this.{scope_key}"
    else:
        assert binding_path is not None
        state = f"{server_sync_marker(*config_sync, enabled=True).lstrip()} "
        target = binding_path

    return (
        "{...$bz.stepper.scope,"
        + state
        + f"_read() {{ return {target}; }},"
        + f"_write(v) {{ {target} = v; }},"
        + f"_max: {max_index}"
        + "}"
    )


class Stepper(Component):
    """Liste ordonnée d'étapes + panneaux de contenu appariés."""

    THEME: ClassVar[dict[str, Any]] = STEPPER_THEME
    THEME_KEY: ClassVar[str] = "stepper"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "next", "prev")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    # ``writes=True`` → la métaclasse dérive ``TWO_WAY_PROPS``.
    # La clé de scope vaut le nom de la prop — ``value`` — dans le
    # ``bz-data`` (≠ le nom de la prop) — déclaré ici, pas hardcodé dans
    # le builder ni dans ``server_sync_marker``.
    value: Any = reactive_prop(
        default=0,
        emit_attr=False,
        writes=True,
        names_field=True,
    )
    orientation: str = reactive_prop(default="horizontal", emit_attr=False)
    clickable: bool = reactive_prop(default=False, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    # Comme Tabs / Pagination : l'autoname couvre le cas lié, ``name=``
    # reste là pour un stepper à valeur littérale qui veut quand même
    # poster son index.
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: Any = None,
        orientation: str | None = None,
        clickable: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(
            value=value,
            orientation=orientation,
            clickable=clickable,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )

    # ── API impérative ─────────────────────────────────────────────────
    #
    # Des méthodes de CLASSE ordinaires, pas des attributs d'instance :
    # le trick non-data-descriptor des overlays n'existe que pour ne pas
    # shadow une ``reactive_prop`` homonyme (``open``), et aucun de ces
    # trois noms n'en est une. Le prendre quand même coûterait
    # doublement — la gate ``test_imperative_classvar_is_complete`` ne
    # lit que les méthodes PUBLIQUES d'une ClassDef, donc des
    # ``_imperative_*`` assignés lui seraient invisibles.

    def set(self, index: int) -> str:
        """Aller à ``index``. Write-through binding s'il y en a une."""
        return self._value_command(coerce_index(index, minimum=0))

    def next(self) -> str:
        # Toujours le dispatch, binding ou pas : « l'étape suivante » se
        # calcule depuis la valeur VIVANTE et s'arrête à ``_max``. Le
        # serveur ne connaît ni l'une ni l'autre au moment du rendu — un
        # write-through devrait baker ``index + 1`` et déborderait.
        return self._dispatch_command("bz-next")

    def prev(self) -> str:
        return self._dispatch_command("bz-prev")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        orientations = theme.get("orientations", {})

        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        orientation = self._reactive_values.get("orientation") or "horizontal"
        axis = orientations.get(orientation) or orientations["horizontal"]
        clickable = bool(self._reactive_values.get("clickable"))

        # ── Binding de ``value`` ─────────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        initial_index = coerce_index(self._reactive_values.get("value"), minimum=0)
        value_server_backed = self._value_server_backed("value")
        scope_key = self._scope_keys("value")[0]
        binding_path = (
            self.path_of(value_binding) if value_binding is not None else None
        )
        # L'expression que lisent les directives : le signal local, ou la
        # cellule de store trackée en mode binding (JAMAIS un getter de
        # scope, que ``absorb`` figerait — cf. ``_build_bz_data``).
        active_expr = binding_path or scope_key

        # ── Walk des enfants ─────────────────────────────────────────
        # Les couples ``(enfant, rehabillage)`` : une étape est souvent
        # ENVELOPPÉE — zone ``@refreshable`` pour se rafraîchir seule,
        # ``ui.fragment``. L'enveloppe n'est pas une instance de ``Step``,
        # donc le tri par type la ratait et l'étape **disparaissait**,
        # sans une erreur (mesuré le 2026-08-23 : 4 022 → 2 185
        # caractères). Le rehabillage voyage AVEC l'enfant parce que le
        # rendu a lieu plus bas, une fois les index connus.
        steps: list[tuple[Step, Any]] = []
        panels: list[tuple[StepPanel, Any]] = []
        passthrough: list[Element] = []
        for raw in self._children:
            child, rewrap = unwrap_transparent(raw)
            if isinstance(child, Step):
                steps.append((child, rewrap))
            elif isinstance(child, StepPanel):
                panels.append((child, rewrap))
            else:
                rendered = self._render_one(raw)
                if isinstance(rendered, Element):
                    passthrough.append(rendered)

        # Le plus grand index atteignable : un panneau de plus que
        # d'étapes est l'écran « terminé », et ``next()`` doit pouvoir
        # l'atteindre.
        max_index = max(max(len(steps), len(panels)) - 1, 0)

        # ── Le décor, calculé UNE fois pour toutes les étapes ─────────
        # Neuf valeurs identiques d'une étape à l'autre : les passer une
        # par une ferait une signature à treize mots-clés dont quatre
        # seulement varient. Le contexte les regroupe ; ``step_class`` et
        # ``body_class`` restent des paramètres parce qu'ils dépendent du
        # rang (la dernière étape ne revendique pas de part et ne pousse
        # plus rien sous elle).
        chrome: dict[str, Any] = {
            "clickable": clickable,
            "rail_class": self.slot_class("rail", axis.get("rail", "")),
            "bullet_class": self.slot_class("bullet", size_cfg.get("bullet", "")),
            "connector_class": self.slot_class("connector", axis.get("connector", "")
            ),
            "label_class": self.slot_class("label", size_cfg.get("label", "")),
            "description_class": self.slot_class("description", size_cfg.get("description", "")
            ),
            "icon_size": size_cfg.get("icon_size", "sm"),
            "active_expr": active_expr,
            "initial_index": initial_index,
        }

        last_index = len(steps) - 1
        step_nodes = [
            rewrap(step._render_in_stepper(
                index=index,
                is_last=index == last_index,
                step_class=self.slot_class("step", axis.get(
                        "step_last" if index == last_index else "step", ""
                    ),
                ),
                body_class=self.slot_class("body", axis.get("body", ""),
                    axis.get("body_last", "") if index == last_index else "",
                ),
                chrome=chrome,
            ))
            for index, (step, rewrap) in enumerate(steps)
        ]

        panel_class = self.slot_class("panel")
        panel_nodes = [
            rewrap(panel._render_panel(
                index=index,
                panel_class=panel_class,
                active_expr=active_expr,
                initial_index=initial_index,
            ))
            for index, (panel, rewrap) in enumerate(panels)
        ]

        # ── Input caché — form data + source du ``change`` ───────────
        # Une ``<ol>`` n'a ni ``name``/``value`` ni ``change`` natif : on
        # relocalise tout listener de change (client ``bz-on:change`` ou
        # le bundle serveur ``hx-*``) sur l'input, dont le ``bz-effect``
        # re-fire un ``change`` à chaque mouvement de l'index.
        root_attrs = self.emit_attrs()
        relocated = _pop_change_handler(root_attrs)
        name = self._reactive_values.get("name") or self._derive_field_name()

        hidden_node: Element | None = None
        if name or relocated:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(active_expr, initial=initial_index),
            }
            if name:
                hidden_attrs["name"] = str(name)
            hidden_attrs.update(relocated)
            hidden_node = Element(tag="input", attrs=hidden_attrs, children=())

        # ── Assemblage ───────────────────────────────────────────────
        # Le scope + les listeners impératifs vivent sur le WRAPPER, pas
        # sur la ``<ol>`` : les panneaux et l'input caché sont hors de la
        # liste (une ``<ol>`` n'accepte que des ``<li>``) et doivent
        # pourtant lire le même signal. Le wrapper est aussi la vraie
        # root — c'est là qu'atterrissent ``classes=`` et un éventuel
        # ``slots={"root": …}``.
        ordered_list = Element(
            tag="ol",
            attrs={"class": self.slot_class("list", axis.get("list", ""))},
            children=tuple(step_nodes),
        )
        wrapper_children: list[Node] = [ordered_list]
        if hidden_node is not None:
            wrapper_children.append(hidden_node)
        if panel_nodes:
            wrapper_children.append(
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("panels")},
                    children=tuple(panel_nodes),
                )
            )
        # Un enfant étranger (texte, divider injecté) atterrit sur le
        # WRAPPER, pas dans la ``<ol>`` — pour la raison qui a fait
        # exister ce wrapper : une liste ordonnée n'accepte que des
        # ``<li>``, et l'y glisser produirait du HTML invalide.
        wrapper_children.extend(passthrough)

        root_attrs["class"] = self.slot_class("root")
        root_attrs["bz-data"] = _build_bz_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial_value=initial_index,
            binding_path=binding_path,
            max_index=max_index,
            server_synced=value_server_backed,
        )
        # Réception des commandes impératives émises par un trigger
        # externe (``wizard.next()`` sur un bouton ailleurs dans la page).
        root_attrs["bz-on:bz-set"] = "goTo($event.detail.value)"
        root_attrs["bz-on:bz-next"] = "next()"
        root_attrs["bz-on:bz-prev"] = "prev()"

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(wrapper_children)
        )


class Step(Component):
    """Une étape dans un :class:`Stepper`.

    Porte des métadonnées : ``Stepper.render()`` walk ses enfants et
    construit le ``<li>`` réel. Hors d'un ``with ui.stepper(...)``, le
    rendu par défaut est un ``<span>`` inerte — un ``ui.step(...)`` égaré
    au scope page ne fait pas exploser le renderer.
    """

    THEME_KEY: ClassVar[str] = "step"
    IS_CONTAINER: ClassVar[bool] = False
    # L'index courant vit chez le parent : une binding par étape voudrait
    # dire N bindings pour la même information.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    NAMED_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)
    ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon",)

    label: Any = reactive_prop(default="", emit_attr=False)
    description: Any = reactive_prop(default="", emit_attr=False)
    status: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        label: Any = "",
        *,
        description: Any = None,
        icon: Any = None,
        status: str | None = None,
        disabled: bool | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(
            label=label,
            description=description,
            status=status,
            disabled=disabled,
            icon=icon,
            **kwargs,
        )

    # ── Rendu interne — appelé par Stepper ────────────────────────────

    def _render_in_stepper(
        self,
        *,
        index: int,
        is_last: bool,
        step_class: str,
        body_class: str,
        chrome: dict[str, Any],
    ) -> Element:
        """``chrome`` = le décor identique pour toutes les étapes, calculé
        une fois par ``Stepper.render()`` (classes composées, taille
        d'icône, expression d'index, drapeau cliquable)."""
        clickable: bool = chrome["clickable"]
        icon_size: str = chrome["icon_size"]
        initial_index: int = chrome["initial_index"]

        label = self._reactive_values.get("label")
        description = self._reactive_values.get("description")
        frozen_status = self._reactive_values.get("status")
        disabled = bool(self._reactive_values.get("disabled"))
        status_expr = f"_status({index})"

        # ── Le driver d'état ─────────────────────────────────────────
        # Un statut explicite est figé : il ne dépend pas de l'index
        # courant, donc aucune raison de le recalculer côté client.
        step_attrs: dict[str, Any] = {"class": step_class}
        if frozen_status:
            step_attrs["data-status"] = str(frozen_status)
        else:
            initial_status = (
                "done"
                if index < initial_index
                else ("current" if index == initial_index else "upcoming")
            )
            # SSR statique pour que le premier paint soit juste, puis
            # réactif. La chaîne littérale est obligatoire : un booléen nu
            # ferait DROPPER l'attribut à false et ``data-[status=…]`` ne
            # matcherait jamais (cf. ``bool_attr``, même classe de piège).
            step_attrs["data-status"] = initial_status
            step_attrs["bz-attr:data-status"] = status_expr
            step_attrs["bz-attr:aria-current"] = (
                f"({status_expr} === 'current') ? 'step' : false"
            )
            if initial_status == "current":
                step_attrs["aria-current"] = "step"

        # ── La pastille ──────────────────────────────────────────────
        bullet_children: list[Node] = []
        icon = self._slot_components.get("icon")
        if isinstance(icon, Component):
            # Icône explicite : elle remplace numéro ET check, dans les
            # quatre statuts.
            bullet_children.append(Component.render_detached(icon))
        elif frozen_status == "error":
            bullet_children.append(
                Component.render_detached(Icon("triangle-alert", size=icon_size))
            )
        else:
            # Deux glyphes montés, un seul visible : le numéro tant que
            # l'étape n'est pas franchie, le check ensuite. Deux nœuds
            # plutôt qu'un contenu réécrit — le runtime ne remplace pas du
            # texte, il bascule un ``display``.
            #
            # Le pré-tampon suit l'INDEX, pas ``frozen_status`` : le seul
            # statut explicite est ``error``, traité au-dessus. Accepter
            # ici un ``status="done"`` ne marcherait qu'à moitié — le
            # ``data-status`` serait figé mais les deux ``bz-show``
            # continueraient de lire ``_status(index)``, donc le runtime
            # inverserait le pré-tampon dès l'hydratation.
            is_done = index < initial_index
            number = Element(
                tag="span",
                attrs={"bz-show": f"{status_expr} !== 'done'"},
                children=(TextNode(str(index + 1)),),
            )
            if is_done:
                stamp_display_none(number.attrs)
            check = Icon("check", size=icon_size)
            check_node = Component.render_detached(check)
            if isinstance(check_node, Element):
                check_node.attrs["bz-show"] = f"{status_expr} === 'done'"
                if not is_done:
                    stamp_display_none(check_node.attrs)
            bullet_children.extend((number, check_node))

        bullet_attrs: dict[str, Any] = {"class": chrome["bullet_class"]}
        if disabled:
            # Dans les DEUX modes. En cliquable le ``<button disabled>``
            # ci-dessous suffirait à l'a11y, mais c'est ``aria-disabled``
            # que le thème lit pour ternir — et en NON cliquable la
            # pastille est un ``<span>``, où ``:disabled`` ne matche
            # jamais : ``disabled=True`` n'y avait donc AUCUN effet, ni
            # visuel ni annoncé (mesuré le 2026-08-13, en soldant
            # ``_UNAUDITED``).
            bullet_attrs["aria-disabled"] = "true"
        if clickable and not disabled:
            bullet_tag = "button"
            bullet_attrs["type"] = "button"
            bullet_attrs["bz-on:click"] = f"goTo({index})"
        elif clickable:
            bullet_tag = "button"
            bullet_attrs["type"] = "button"
            bullet_attrs["disabled"] = True
        else:
            # Non cliquable = pas de ``<button>`` du tout : rien dans le
            # tab order, rien à annoncer comme actionnable.
            bullet_tag = "span"
        bullet = Element(
            tag=bullet_tag, attrs=bullet_attrs, children=tuple(bullet_children)
        )

        rail_children: list[Node] = [bullet]
        if not is_last:
            rail_children.append(
                Element(
                    tag="span",
                    attrs={"class": chrome["connector_class"], "aria-hidden": "true"},
                    children=(),
                )
            )

        # ── Le corps ─────────────────────────────────────────────────
        body_children: list[Node] = []
        if label is not None and label != "":
            body_children.append(
                Element(
                    tag="span",
                    attrs={"class": chrome["label_class"]},
                    children=(_text_or_component(label),),
                )
            )
        if description is not None and description != "":
            body_children.append(
                Element(
                    tag="span",
                    attrs={"class": chrome["description_class"]},
                    children=(_text_or_component(description),),
                )
            )

        children: list[Node] = [
            Element(
                tag="div", attrs={"class": chrome["rail_class"]},
                children=tuple(rail_children),
            )
        ]
        if body_children:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": body_class},
                    children=tuple(body_children),
                )
            )

        return Element(tag="li", attrs=step_attrs, children=tuple(children))

    def render(self) -> Element:
        # Hors d'un Stepper, une étape n'a pas de contexte de statut.
        return Element(tag="span", attrs={}, children=())


class StepPanel(Component):
    """Contenu affiché quand son rang égale l'index courant.

    Aucun paramètre : le rang vient de l'ORDRE de déclaration parmi les
    panneaux. Un ``index=`` explicite aurait été une seconde manière de
    dire la même chose (charter, principe 4) et l'occasion d'un décalage
    silencieux entre la valeur écrite et la position réelle.
    """

    THEME_KEY: ClassVar[str] = "step_panel"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    def __init__(self, **kwargs: Any) -> None:
        # Signature explicite bien qu'elle n'ajoute aucun paramètre :
        # sans elle, l'introspection publique remonte le ``*_args`` du
        # socle comme s'il était une surface du composant.
        super().__init__(**kwargs)

    def _render_panel(
        self,
        *,
        index: int,
        panel_class: str,
        active_expr: str,
        initial_index: int,
    ) -> Element:
        # ``Number(...)`` : la valeur peut revenir d'une form data en
        # chaîne (l'input caché la sérialise), et ``"1" === 1`` est faux.
        # Pas de ``role`` : un panneau d'étape n'est pas un ``tabpanel``
        # (il n'y a pas de ``tablist``, et le lier à une pastille
        # ``aria-controls`` mentirait sur la nature du contrôle). Le
        # panneau caché l'est par ``display:none``, ce que les lecteurs
        # d'écran respectent déjà.
        attrs: dict[str, Any] = {
            "class": panel_class,
            "bz-show": f"Number({active_expr}) === {index}",
        }
        if index != initial_index:
            # Anti-FOUC : pré-tamponné caché, sinon le panneau clignote
            # avant le premier effet ``bz-show``.
            stamp_display_none(attrs)
        return Element(
            tag="div", attrs=attrs, children=tuple(self._render_children())
        )

    def render(self) -> Element:
        # Usage isolé — le contenu apparaît, sans le câblage de bascule.
        return Element(
            tag="div",
            attrs={"class": "outline-none"},
            children=tuple(self._render_children()),
        )


def _text_or_component(value: Any) -> Node:
    """Le contenu d'un slot textuel : un Component rendu, sinon du texte.

    Pas de branche ClientBinding — ``label`` / ``description`` ne sont pas
    bindables, et une binding vit dans ``_binding_metadata``, jamais dans
    ``_reactive_values`` (cf. traps.md § « Lire un binding via
    _reactive_values + isinstance »).
    """
    if isinstance(value, Component):
        return Component.render_detached(value)
    return TextNode(str(value))


__all__ = ["Step", "StepPanel", "Stepper"]

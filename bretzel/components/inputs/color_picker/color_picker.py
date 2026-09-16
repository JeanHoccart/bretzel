"""``ColorPicker`` — champ de couleur avec panneau de pastilles.

Usage ::

    ui.color_picker(value=state.brand)

**La valeur est une chaîne hexadécimale** — ``"#2f5fd0"``. C'est ce
qu'attend un ``Theme(semantic=…)``, ce qu'une form data transporte tel
quel, et ce qui se relit dans le champ. Une chaîne vide veut dire « pas
de couleur », comme partout ailleurs dans la famille input.

Pourquoi pas ``<input type="color">``
--------------------------------------

``ui.input`` le REFUSE, et ce composant est ce que son message
recommande. Un sélecteur natif n'est pas thématisable et change d'allure
entre Chrome, Safari et Android — c'est la même leçon que la scrollbar
du Carousel et que ``<input type="time">``. S'y ajoute ici une raison
propre à Bretzel : le natif ne peut pas proposer **la palette du thème**,
qui est précisément ce qu'on veut choisir neuf fois sur dix.

Ce que le panneau propose
--------------------------

Les couleurs NOMMÉES du thème actif, résolues en hexadécimal (les 31 de
la palette livrée par défaut). Pas les onze slots sémantiques : eux sont
la structure qu'on est en train d'éditer, les proposer comme valeur
serait circulaire.

⚠️ **Il n'y a pas de ``swatches=``**, et c'est délibéré. Une app qui veut
sa charte la déclare une fois — ``Theme(palette={"brand": "#..."})`` — et
TOUS ses pickers la proposent. Un paramètre par instance serait une
seconde manière de faire la même chose, et il ferait diverger deux
pickers de la même app sans que rien ne le dise. Il rendrait aussi ce
composant « propriétaire d'une collection » sans avoir de balisage à
déléguer, ce qui n'est aucun des trois cas de ``COLLECTION_OWNER``.

Le champ reste libre : n'importe quel hexadécimal se tape à la main, et
c'est ce qui évite qu'une grille de pastilles devienne une prison.

Form integration : ``names_field=True`` sur ``value`` dérive le ``name``
HTML ; un ``<input type="hidden">`` porte la couleur dans la form data.
Idiome partagé avec DatePicker / TimePicker / Calendar.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
    bool_attr,
    imperative_listeners,
    install_open_close_toggle,
    install_value_commands,
    server_sync_marker,
)
from bretzel.components.inputs._picker_field import (
    anchored_panel,
    clear_button,
    detach_wrapper_carriers,
    hidden_carrier,
    relocate_field_events,
    trigger_button,
    value_expr,
)
from bretzel.components.inputs.color_picker.theme import COLOR_PICKER_THEME
from bretzel.core.escape import RawAttrValue
from bretzel.core.tree import Element, Node
from bretzel.render import text

#: Le repli quand aucun contexte de rendu n'est actif (un banc, un test
#: unitaire) : on ne peut pas lire la palette de l'app, et un panneau vide
#: serait pire qu'une liste courte.
_FALLBACK_SWATCHES: tuple[str, ...] = (
    "#8b8d98", "#e54d2e", "#e5484d", "#e93d82", "#d6409f",
    "#8e4ec6", "#6e56cf", "#3e63dd", "#0090ff", "#00a2c7",
    "#12a594", "#30a46c", "#46a758", "#ffe629", "#ffc53d",
    "#f76b15", "#ad7f58", "#8d8d8d",
)


def hex_or_empty(value: Any, *, owner: str = "ColorPicker") -> str:
    """Coercer une valeur de couleur vers ``"#rrggbb"`` ou ``""``.

    ``None`` → ``""`` (champ vide) ; une chaîne passe. Tout le reste est
    une erreur d'usage, levée avec ``owner`` dans le message pour que
    l'auteur voie QUI a refusé — **même contrat que ``time_to_hhmm`` et
    ``date_to_iso``**, délibérément.

    ⚠️ Une chaîne non hexadécimale n'est PAS refusée, et c'est un choix.
    Le champ est éditable : l'utilisateur tape forcément des états
    intermédiaires (``"#2f"``), et la graine SSR d'un appelant peut être
    n'importe quoi. Refuser à la construction déplacerait l'erreur au
    mauvais endroit — c'est le rendu qui montre une pastille vide, et ça
    se lit. Les trois pickers de date raisonnent pareil.
    """
    from bretzel.components.base.attrs import ComponentDefinitionError

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ComponentDefinitionError(
        f"{owner}(value={value!r}) : type {type(value).__name__} non "
        "supporté. Attendu une chaîne hexadécimale ou None."
    )


class ColorPicker(Component):
    """Render a color field with a swatch selection panel."""

    THEME: ClassVar[dict[str, Any]] = COLOR_PICKER_THEME
    THEME_KEY: ClassVar[str] = "color_picker"
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value", "disabled")
    #: Un picker est les DEUX natures à la fois : un panneau ancré
    #: (comme `dialog`) et un champ qui porte une valeur (comme
    #: `input`). Sa surface est donc l'union des deux vocabulaires
    #: déjà fixés par ses voisins — rien d'inventé ici.
    IMPERATIVE: ClassVar[tuple[str, ...]] = (
        "open", "close", "toggle", "set", "clear", "focus", "blur",
    )
    EVENTS: ClassVar[tuple[str, ...]] = ("change", "focus", "blur")

    name: str | None = reactive_prop(default=None, emit_attr=False)
    value: Any = reactive_prop(
        default=None, writes=True, names_field=True
    )
    # ``emit_attr=False`` : la racine est un ``<div>`` wrapper, où
    # ``disabled`` ne fait RIEN. Le binding est forwardé à la main sur les
    # trois porteurs réels (champ, ×, déclencheur) — même raison et même
    # gate que TimePicker (``test_binding_lands_on_carrier``).
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        name: str | None = None,
        placeholder: str | None = None,
        clearable: bool = False,
        disabled: bool | None = None,
        required: bool | None = None,
        color: str | None = None,
        size: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        self._placeholder = placeholder or "#rrggbb"
        self._clearable = clearable
        super().__init__(
            value=value, name=name, disabled=disabled, required=required,
            color=color, size=size,
            on_change=on_change, on_focus=on_focus, on_blur=on_blur,
            **kwargs,
        )
        # APRÈS `super().__init__` : les deux installeurs lisent
        # `_binding_metadata`, qui n'est peuplé qu'à ce moment-là.
        install_open_close_toggle(self)
        # ⚠️ PAS `"input"` : le premier `<input>` d'un picker est le
        # porteur CACHÉ (`hidden_carrier`), qui ne prend pas le
        # focus. Mesuré — `.focus()` ne faisait rien sur les six.
        install_value_commands(
            self, focus_selector="input:not([type=hidden])"
        )

    # ── Les deux formes de l'expression de valeur ────────────────────

    def _palette_swatches(self) -> tuple[str, ...]:
        """Les couleurs proposées — celles du THÈME, et rien d'autre.

        Hors contexte de rendu on ne peut pas lire la palette : on rend le
        repli plutôt qu'un panneau vide. Un banc qui construit le composant
        nu voit donc quand même des pastilles.
        """
        from bretzel.render.context import maybe_current_context
        from bretzel.theme.tokens import SEMANTIC_COLOR_NAMES

        ctx = maybe_current_context()
        theme = getattr(getattr(ctx, "app", None), "theme", None)
        getter = getattr(theme, "get_palette", None)
        if not callable(getter):
            return _FALLBACK_SWATCHES
        palette = getter()
        semantic = set(SEMANTIC_COLOR_NAMES)
        return tuple(
            palette.resolve(name, "light").bg_hex
            for name in palette.envelope_dict()
            if name not in semantic
        )

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"

        size_cfg = sizes.get(size_key, sizes.get("md", {}))

        def sized(slot: str) -> str:
            return self.slot_class(slot, size_cfg.get(slot, ""))

        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))
        initial = hex_or_empty(self._reactive_values.get("value"))
        val = value_expr(self)

        # ── Racine : attrs, relocations, scope ───────────────────────
        root_attrs = self.emit_attrs()
        hidden_extra: dict[str, Any] = {}
        relocated: dict[str, Any] = {}
        relocate_field_events(
            root_attrs, value_carrier=hidden_extra, focusable=relocated
        )
        name = detach_wrapper_carriers(self, root_attrs)
        root_attrs["class"] = self.compose_class("root")
        # ``_serverSync`` : sans lui, une mutation serveur suivie d'un
        # rafraîchissement ne changerait RIEN à l'écran — idiomorph
        # préserve le signal client, donc l'ancienne valeur gagne. Le
        # marqueur dit au runtime de ré-adopter la valeur rendue.
        # ⚠️ ``server_sync_marker`` rend un fragment qui commence par une
        # ESPACE et finit par une VIRGULE : il est fait pour se glisser
        # ENTRE deux champs, donc la virgule qui le précède est à la
        # charge de l'appelant. L'oublier produit
        # ``val: "#2f5fd0" _serverSync: [...]`` — une erreur de syntaxe
        # qui tue le SCAN du runtime pour la page entière (28 scopes, 0
        # initialisé) sans un mot dans la console. Mesuré ici même.
        local = ""
        if self._binding_metadata.get("value") is None:
            (key,) = self._scope_keys("value")
            sync = server_sync_marker(
                key, enabled=self._value_server_backed("value")
            )
            local = f",{key}: {json.dumps(initial)},{sync}"
        root_attrs["bz-data"] = "{open: false" + local + "}"
        # ── Les récepteurs de l'API impérative ───────────────────
        #
        # En mode LIÉ, `.open()` / `.set()` écrivent directement dans le
        # store et ces écouteurs ne se déclenchent jamais ; on les pose
        # quand même pour que le contrat soit le même dans les deux
        # modes — le choix déjà fait par Sidebar, Dialog et Select.
        for _ev, _handler in imperative_listeners("open").items():
            root_attrs.setdefault(_ev, _handler)
        root_attrs.setdefault(
            "bz-on:bz-set", f"{val} = $event.detail.value"
        )
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        hidden_input = hidden_carrier(
            value_expr=val, initial=initial, name=name,
            required=required, extra=hidden_extra,
        )

        # ── La pastille de tête ──────────────────────────────────────
        # Le damier du thème transparaît quand la valeur est vide : une
        # pastille blanche et une pastille SANS couleur se confondraient.
        swatch = Element(
            tag="span",
            attrs={
                "class": sized("swatch"),
                "aria-hidden": "true",
                # ``background-color`` et pas ``background`` : la classe
                # pose le gris de repos, et un raccourci ``background``
                # l'effacerait même vide. Ici, valeur absente = pas de
                # style inline = le gris se voit.
                "bz-attr:style": RawAttrValue(
                    f"{val} ? 'background-color:' + {val} : ''"
                ),
                **({"style": f"background-color:{initial}"} if initial else {}),
            },
            children=(),
        )

        field_attrs: dict[str, Any] = {
            "type": "text",
            "placeholder": self._placeholder,
            "class": sized("input_field"),
            "value": initial,
            "bz-model": val,
            "autocomplete": "off",
            "spellcheck": "false",
            "aria-label": self._placeholder,
        }
        if disabled:
            field_attrs["disabled"] = True
        if required:
            field_attrs["aria-required"] = "true"
        field_attrs.update(relocated)
        self.forward_binding("disabled", field_attrs)

        frame_children: list[Node] = [
            swatch,
            Element(tag="input", attrs=field_attrs, children=()),
        ]

        if self._clearable:
            cross = clear_button(
                css=sized("clear_button"),
                icon_css=self.slot_class(
                    "button_icon", size_cfg.get("button_icon", "")
                ),
                aria_label=text("color_picker.clear"),
                clear_js=f"{val} = ''",
                show_when=val,
                has_value_at_ssr=bool(initial),
                disabled=disabled,
            )
            self.forward_binding("disabled", cross.attrs)
            frame_children.append(cross)

        opener = trigger_button(
            icon="palette",
            css=sized("trigger_button"),
            icon_css=self.slot_class(
                "button_icon", size_cfg.get("button_icon", "")
            ),
            aria_label=text("color_picker.open"),
            disabled=disabled,
        )
        self.forward_binding("disabled", opener.attrs)
        frame_children.append(opener)

        frame = Element(
            tag="div",
            attrs={"class": sized("input_frame"), "bz-ref": "bztrigger"},
            children=tuple(frame_children),
        )

        panel = anchored_panel(
            css=self.slot_class("panel"),
            children=(
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("panel_label")},
                    children=(Element(
                        tag="span", attrs={}, children=()),),
                ),
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("grid")},
                    children=tuple(
                        self._cell(hexa, val, initial, disabled)
                        for hexa in self._palette_swatches()
                    ),
                ),
            ),
        )

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(hidden_input, frame, panel),
        )

    def _cell(
        self, hexa: str, val: str, initial: str, disabled: bool
    ) -> Element:
        """Une pastille du panneau.

        Le clic écrit la valeur ET referme : contrairement au TimePicker,
        où l'heure précède la minute, il n'y a rien à choisir après une
        couleur.
        """
        attrs: dict[str, Any] = {
            "type": "button",
            "class": self.slot_class("swatch_cell"),
            "style": f"background:{hexa}",
            "title": hexa,
            "aria-label": hexa,
            # ``bool_attr`` et pas un ternaire à la main : ``bz-attr``
            # traite un booléen comme HTML le veut (attribut vide, ou
            # retiré), or ``data-[selected=true]:`` matche le LITTÉRAL.
            # Oublier le ternaire ne casse rien de visible — le style ne
            # s'applique pas, en silence.
            "data-selected": (
                "true" if initial.lower() == hexa.lower() else "false"
            ),
            "bz-attr:data-selected": RawAttrValue(
                bool_attr(f"({val} || '').toLowerCase() === '{hexa.lower()}'")
            ),
            # ⚠️ ``value`` et ``open`` NUS, pas ``this.value`` : un
            # ``bz-on:`` est une DIRECTIVE, évaluée dans un
            # ``with($scope)`` — l'identifiant nu y résout, ``this`` non.
            # C'est ``this`` qu'il faut dans un CORPS DE MÉTHODE du
            # ``bz-data``, l'exact inverse. Écrit à l'envers ici, la
            # levée tuait le scan du runtime pour la PAGE ENTIÈRE : plus
            # aucun scope initialisé, et aucune erreur visible.
            "bz-on:click": RawAttrValue(
                f"{val} = '{hexa}'; open = false"
            ),
        }
        if disabled:
            attrs["disabled"] = True
        self.forward_binding("disabled", attrs)
        return Element(tag="button", attrs=attrs, children=())

"""``TimePicker`` — champ d'heure avec panneau à deux colonnes.

Usage ::

    ui.time_picker(value=state.start)                 # :00 :15 :30 :45
    ui.time_picker(value=state.start, step=30)        # demi-heures
    ui.time_picker(value=state.start, min="09:00", max="18:00")

**La valeur est une chaîne ``"HH:MM"``** — même forme que l'ISO des
pickers de date : triable, comparable, sérialisable telle quelle dans une
form data, et lisible dans le champ éditable. Python accepte en plus un
``datetime.time``, converti au rendu.

Silhouette identique à :class:`DatePicker` (champ éditable + bouton icône
dans le même anneau de focus, popover ancré), mais le panneau n'est pas
une grille : **deux colonnes aimantées**, heures et minutes.

Pourquoi des colonnes maison et pas ``<input type="time">`` : un widget
natif n'est pas thématisable et change d'allure entre Chrome, Safari et
Android. C'est la leçon payée sur la scrollbar du Carousel, en plus
visible — et ici s'y ajoute le fait qu'un ``min``/``max`` natif
s'applique sans qu'on puisse MONTRER les créneaux permis.

``step`` (défaut 15) est de la **donnée métier**, pas du goût : un
créneau de rendez-vous. Il décide quelles minutes existent —
``step=15`` → :00 :15 :30 :45, ``step=1`` → les soixante. Le défaut évite
la colonne de 60 lignes que personne ne veut faire défiler.

``min`` / ``max`` bornent les cellules PROPOSÉES (une heure hors bornes
est rendue ``disabled``). Ils ne sont **pas** bindables, contrairement à
la famille date : la règle (`client-reactive-surface.md`) ne les y admet
que pour la contrainte croisée client-side d'un range (``fin.min =
début``), qui n'existe pas ici. Cf. `kwarg-routing.md`.

Le clic sur une MINUTE referme le panneau, celui sur une heure non :
l'ordre de lecture est heure puis minute, donc refermer à l'heure
couperait la main de l'utilisateur au milieu de son geste.

Form integration : ``names_field=True`` sur ``value`` dérive le ``name``
HTML du champ lié ; un ``<input type="hidden">`` porte l'heure dans la
form data. Idiome partagé avec DatePicker / Calendar.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, reject_component
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
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
from bretzel.components.inputs.time_picker.theme import TIME_PICKER_THEME
from bretzel.core.tree import Element, Node
from bretzel.core.tree import TextNode as TextNode
from bretzel.render import text

#: Les deux parties, dans l'ordre où on les lit. Les indices sont ceux
#: du tuple rendu par ``_parts()`` dans ``$bz.time.scope`` — un seul
#: endroit les nomme de chaque côté.
HOUR, MINUTE = 0, 1


def time_to_hhmm(value: Any, *, owner: str = "TimePicker") -> str:
    """Coercer une valeur d'heure vers ``"HH:MM"``.

    ``None`` → ``""`` (champ vide) ; un ``datetime.time`` → sa forme
    ``HH:MM`` ; une chaîne passe (déjà normalisée, ou la graine SSR de
    l'appelant). Tout le reste est une erreur d'usage, levée avec
    ``owner`` dans le message pour que l'auteur voie QUI a refusé.

    Même contrat que ``inputs/_wiring.date_to_iso`` pour la famille date
    — volontairement, les deux familles se lisent pareil.
    """
    from bretzel.components.base.attrs import ComponentDefinitionError

    if value is None:
        return ""
    if isinstance(value, _dt.time):
        return f"{value.hour:02d}:{value.minute:02d}"
    if isinstance(value, str):
        return value
    raise ComponentDefinitionError(
        f"{owner} value must be time / None / str, "
        f"got {type(value).__name__}: {value!r}"
    )


#: Normalisation au blur : la saisie libre devient ``HH:MM``, ou se vide.
#: Templatée sur ``{V}`` (l'expression de valeur) pour que le mode lié
#: (``$bz.state.X.y``) et le mode littéral (``value``) partagent le MÊME
#: parseur — exactement comme ``NORMALISE_TO_ISO_TEMPLATE`` chez
#: DatePicker.
NORMALISE_TO_HHMM_TEMPLATE = (
    "(() => {{ const raw = String({V} || '').trim(); "
    "if (!raw) {{ {V} = ''; return; }} "
    # ``9h30`` / ``9:30`` / ``9.30`` / ``930`` / ``9`` — un seul motif
    # couvre les cinq façons dont les gens tapent une heure.
    "const m = raw.match(/^(\\d{{1,2}})[^\\d]?(\\d{{2}})?$/); "
    "if (!m) {{ {V} = ''; return; }} "
    "const h = Number(m[1]), mi = Number(m[2] || 0); "
    "if (h > 23 || mi > 59) {{ {V} = ''; return; }} "
    "const pad = n => String(n).padStart(2, '0'); "
    "{V} = pad(h) + ':' + pad(mi); }})()"
)


def normalise_to_hhmm_js(value_expr: str) -> str:
    """Le normaliseur saisie-libre → ``HH:MM`` pour ``value_expr``."""
    return NORMALISE_TO_HHMM_TEMPLATE.format(V=value_expr)


def _in_bounds(candidate: str, low: str, high: str) -> bool:
    """``candidate`` tient-il dans ``[low, high]`` ?

    Comparaison de CHAÎNES, et c'est correct : ``"HH:MM"`` zéro-paddé se
    trie lexicographiquement comme il se trie chronologiquement. C'est la
    raison d'être du format, la même qui fait choisir l'ISO pour les
    dates.
    """
    if low and candidate < low:
        return False
    return not (high and candidate > high)


class TimePicker(Component):
    """Render a time field with hour and minute panels."""

    THEME: ClassVar[dict[str, Any]] = TIME_PICKER_THEME
    THEME_KEY: ClassVar[str] = "time_picker"
    IS_CONTAINER: ClassVar[bool] = False
    # ``min`` / ``max`` restent statiques : la règle ne les admet en
    # one-way que pour la contrainte croisée d'un range de dates, qui
    # n'existe pas ici (cf. client-reactive-surface.md § La règle).
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
    min: Any = reactive_prop(default=None, emit_attr=False)
    max: Any = reactive_prop(default=None, emit_attr=False)
    # ``emit_attr=False`` : la racine est un ``<div>`` wrapper, où
    # ``disabled`` ne fait RIEN. Le binding est forwardé à la main sur
    # les trois porteurs réels (champ, ×, trigger) — même raison et même
    # gate que DatePicker (``test_binding_lands_on_carrier``).
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    required: bool = reactive_prop(default=False, emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)

    def __init__(
        self,
        value: Any = None,
        *,
        placeholder: str = "HH:MM",
        step: int = 15,
        min: Any = None,
        max: Any = None,
        color: str | None = None,
        size: str | None = None,
        disabled: bool | None = None,
        required: bool | None = None,
        clearable: bool = True,
        close_on_pick: bool = True,
        hour_label: str = "H",
        minute_label: str = "M",
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        on_focus: Callable[..., Any] | str | None = None,
        on_blur: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        if not 1 <= int(step) <= 60:
            from bretzel.components.base.attrs import ComponentUsageError

            raise ComponentUsageError(
                f"TimePicker(step={step!r}) — un pas de minutes doit tenir "
                f"dans 1..60. Sans cette garde, step=0 boucle à l'infini "
                f"et step=90 rend une colonne vide, toutes deux en silence."
            )
        self._placeholder = placeholder
        self._step = int(step)
        self._clearable = clearable
        self._close_on_pick = close_on_pick
        for _prop, _value in (("hour_label", hour_label),
                              ("minute_label", minute_label)):
            reject_component(
                _value,
                owner="TimePicker",
                prop=_prop,
                because=(
                    "l'en-tête de colonne sert AUSSI de nom accessible — il "
                    "part dans l'``aria-label`` de la colonne ET dans celui de "
                    "chacune de ses 24 (ou 60) cellules (``f\"{label} {v}\"``), "
                    "et un attribut HTML ne peut porter qu'une string."
                ),
                instead=(
                    "Attendu : une abréviation d'un ou deux caractères, "
                    "``hour_label=\"H\"`` / ``minute_label=\"Min\"``."
                ),
            )
        self._hour_label = hour_label
        self._minute_label = minute_label
        # Forward direct : le socle drope les kwargs reactive None (garde le défaut).
        super().__init__(
            name=name,
            value=value,
            min=min,
            max=max,
            color=color,
            size=size,
            disabled=disabled,
            required=required,
            on_change=on_change,
            on_focus=on_focus,
            on_blur=on_blur,
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


    def _value_target(self) -> str:
        """La même valeur, telle qu'un CORPS DE MÉTHODE doit l'adresser.

        Un corps de méthode n'est PAS enveloppé dans ``with($scope)`` :
        l'identifiant nu ``value`` y lève ``value is not defined``, et
        le panneau entier devient inerte — les clics n'écrivent rien, en
        silence côté serveur. Il faut ``this.value``.

        Le chemin de store, lui, est global : il s'écrit pareil des deux
        côtés. C'est ce qui rend le bug INVISIBLE en mode binding et
        présent seulement en mode littéral — donc absent de la moitié des
        tests si on n'y prend pas garde.

        (Le piège est documenté depuis Pagination : « dans un corps de
        méthode, un identifiant nu ne voit pas le scope ». Je l'ai repris
        en copiant l'expression de DatePicker, qui ne s'en sert QUE dans
        des directives.)
        """
        binding = self._binding_metadata.get("value")
        if binding is not None:
            return self.path_of(binding)
        # La clé vient de la DÉCLARATION, jamais d'un littéral. Elle a été
        # écrite ``"this.val"`` en dur ici jusqu'au 2026-09-07, et c'est le
        # seul site que la normalisation des clés de scope a raté : le
        # panneau entier est devenu inerte en mode littéral, sans erreur
        # JS et sans un test rouge — seul ``probe_time_picker_cells`` l'a
        # dit. Exactement le mode d'échec que ce helper documente
        # au-dessus, appliqué à lui-même.
        return f"this.{self._scope_keys('value')[0]}"

    def render(self) -> Element:
        theme = self._resolved_theme()
        sizes = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = sizes.get(size_key, sizes.get("md", {}))
        disabled = bool(self._reactive_values.get("disabled"))
        required = bool(self._reactive_values.get("required"))

        initial = time_to_hhmm(self._reactive_values.get("value"))
        low = time_to_hhmm(self._reactive_values.get("min"))
        high = time_to_hhmm(self._reactive_values.get("max"))
        val = value_expr(self)

        # ── Racine : attrs, relocations, scope ────────────────────────
        # Les deux appels ci-dessous sont la mécanique commune aux trois
        # pickers (``inputs/_picker_field.py``) : vider la racine de ce
        # qu'elle ne peut pas porter, et router chaque handler vers le
        # porteur capable de le tirer.
        root_attrs = self.emit_attrs()
        hidden_extra: dict[str, Any] = {}
        relocated: dict[str, Any] = {}
        relocate_field_events(
            root_attrs, value_carrier=hidden_extra, focusable=relocated
        )
        name = detach_wrapper_carriers(self, root_attrs)
        root_attrs["class"] = self.slot_class("root")
        root_attrs["bz-data"] = self._scope_literal(
            initial, self._value_target()
        )
        # ── Les récepteurs de l'API impérative ───────────────────
        #
        # En mode LIÉ, `.open()` / `.set()` écrivent directement dans le
        # store et ces écouteurs ne se déclenchent jamais ; on les pose
        # quand même pour que le contrat soit le même dans les deux
        # modes — le choix déjà fait par Sidebar, Dialog et Select.
        for _ev, _handler in imperative_listeners("open").items():
            root_attrs.setdefault(_ev, _handler)
        # ⚠️ `value_expr()` et PAS `_value_target()`. Un `bz-on:` est
        # une DIRECTIVE, donc évaluée dans un `with($scope)` où
        # l'identifiant nu `value` résout ; `this.value` n'y désigne rien.
        # C'est l'exact miroir du piège que `_value_target` documente,
        # et il ne se voit qu'en mode LITTÉRAL : en mode lié les deux
        # rendent le même chemin de store. Mesuré — `.set()` ne posait
        # rien sur le time_picker, et sur lui seul.
        root_attrs.setdefault(
            "bz-on:bz-set", f"{value_expr(self)} = $event.detail.value"
        )
        # Escape + clic-dehors : le helper partagé enregistre les deux sur
        # ``$el`` (``bz-on`` n'a ni ``.outside`` ni ``.escape`` — il n'a
        # AUCUN modificateur, cf. traps.md).
        root_attrs["bz-init"] = anchored_dismiss_init("open")

        hidden_input = hidden_carrier(
            value_expr=val,
            initial=initial,
            name=name,
            required=required,
            extra=hidden_extra,
        )

        # ── Champ éditable ───────────────────────────────────────────
        field_attrs: dict[str, Any] = {
            "type": "text",
            "placeholder": self._placeholder,
            "class": self.slot_class("input_field", size_cfg.get("input_field", "")),
            "value": initial,
            "bz-model": val,
            "bz-on:blur": normalise_to_hhmm_js(val),
            "autocomplete": "off",
            "inputmode": "numeric",
            "spellcheck": "false",
            "aria-label": self._placeholder,
        }
        if disabled:
            field_attrs["disabled"] = True
        if required:
            # Repère visuel seulement — le vrai ``required`` de la
            # validation vit sur l'input caché.
            field_attrs["aria-required"] = "true"
        if "bz-on:blur" in relocated:
            # Enchaîner plutôt qu'écraser : la normalisation interne et le
            # ``on_blur=`` de l'utilisateur doivent tourner tous les deux.
            relocated["bz-on:blur"] = (
                f"{field_attrs['bz-on:blur']}; {relocated['bz-on:blur']}"
            )
        field_attrs.update(relocated)
        self.forward_binding("disabled", field_attrs)

        frame_children: list[Node] = [
            Element(tag="input", attrs=field_attrs, children=())
        ]

        if self._clearable:
            cross = clear_button(
                css=self.slot_class("clear_button", size_cfg.get("clear_button", "")),
                icon_css=self.slot_class("button_icon", size_cfg.get("button_icon", "")),
                aria_label=text("time_picker.clear"),
                clear_js=f"{val} = ''",
                show_when=val,
                has_value_at_ssr=bool(initial),
                disabled=disabled,
            )
            self.forward_binding("disabled", cross.attrs)
            frame_children.append(cross)

        opener = trigger_button(
            icon="clock",
            css=self.slot_class("trigger_button", size_cfg.get("trigger_button", "")),
            icon_css=self.slot_class("button_icon", size_cfg.get("button_icon", "")),
            aria_label=text("time_picker.open"),
            disabled=disabled,
        )
        self.forward_binding("disabled", opener.attrs)
        frame_children.append(opener)

        # ``bz-ref="bztrigger"`` : l'ancre contre laquelle le panneau se
        # positionne (même idiome que Select / Combobox / DatePicker).
        frame = Element(
            tag="div",
            # La hauteur du palier est sur le CADRE, qui porte la
            # bordure (cf. la note du thème) — sinon 2 px de trop.
            attrs={
                "class": self.slot_class(
                    "input_frame", size_cfg.get("input_frame", "")),
                "bz-ref": "bztrigger",
            },
            children=tuple(frame_children),
        )

        # La classe d'une cellule voyage UNE fois, sur le conteneur.
        # Avant le 2026-09-01 elle était recopiée sur chacune des 28 ou
        # 84 cellules : 452 caractères × 84 = 38 Ko d'une seule chaîne
        # identique, dans une page qui en pesait 54.
        cell_base = " ".join(
            p
            for p in (
                self.compose_class("cell", apply_variant_size_modifiers=False),
                size_cfg.get("cell", ""),
            )
            if p
        )

        # ── Panneau : deux colonnes aimantées ────────────────────────
        panel = anchored_panel(
            css=self.slot_class("panel"),
            # À l'ouverture, amener la valeur courante sous les yeux : sur
            # 24 heures, ouvrir à 14:00 en montrant 00-06 obligerait à
            # chercher. C'est une ACTION déclenchée par le signal ``open``,
            # pas une valeur calculée — donc immunisée au piège « une
            # mesure n'est pas un signal » qui a mordu le Carousel.
            extra_effect=(
                "if (open) $el.querySelectorAll('[data-selected=true]')"
                ".forEach(c => c.scrollIntoView({block: 'center'}))"
            ),
            children=(
                Element(
                    tag="div",
                    attrs={
                        "class": self.slot_class("columns"),
                        # ── Les cellules naissent ICI, côté client ───
                        # ``bz-effect`` et PAS ``bz-init`` : ce dernier
                        # est one-shot par NŒUD et survit au rebind, or
                        # idiomorph morphe EN PLACE — un ``bz-init`` ne
                        # re-tournerait donc jamais après un swap. Même
                        # choix et même raison que ``<bz-calendar>``,
                        # qui a payé la leçon.
                        #
                        # L'effet fait DEUX choses, et la seconde est
                        # celle qui justifie qu'il soit un effet :
                        # peindre les cellules une fois, puis
                        # re-marquer la sélection à CHAQUE changement de
                        # la valeur. C'est ce qui remplace les 84
                        # ``bz-attr:data-selected`` d'avant — un effet
                        # par instance au lieu d'un par cellule.
                        # ``_parts()`` est LU ici, et c'est ce qui abonne
                        # l'effet : sans cette lecture il ne
                        # re-tournerait jamais et la sélection
                        # resterait celle du premier paint. Le
                        # ``pick`` voyage en flèche — une méthode
                        # passée par son nom perdrait son ``this``,
                        # et le scope n'est PAS ``this`` dans une
                        # expression de directive (mesuré : « scope.
                        # _parts is not a function », le runtime ne
                        # démarrait plus du tout).
                        "bz-effect": (
                            "$bz.time.fill($el, _parts(), (p, v) => pick(p, v))"
                        ),
                        "data-bz-cell-class": cell_base,
                        **({"data-bz-cells-disabled": "true"}
                           if disabled else {}),
                    },
                    children=(
                        self._column(
                            HOUR, self._hour_label,
                            [f"{h:02d}" for h in range(24)],
                            low, high, size_cfg, disabled, part_is_hour=True,
                        ),
                        self._column(
                            MINUTE, self._minute_label,
                            [f"{m:02d}" for m in range(0, 60, self._step)],
                            low, high, size_cfg, disabled, part_is_hour=False,
                        ),
                    ),
                ),
            ),
        )

        return Element(
            tag=self._tag,
            attrs=root_attrs,
            children=(
                hidden_input,
                frame,
                panel,
            ),
        )

    # ── Fabrique de pièces ──────────────────────────────────────────

    def _scope_literal(self, initial: str, target: str) -> str:
        """Le ``bz-data`` de l'instance : **des données, pas du code**.

        Les méthodes (``_parts`` / ``_is`` / ``pick``) vivent une seule
        fois dans ``$bz.time.scope`` — un panneau fait 28 boutons, écrire
        le pick en toutes lettres sur chacun sérialiserait le même
        algorithme 28 fois par instance.

        ``_read`` / ``_write`` couvrent les deux modes de valeur avec les
        mêmes méthodes. Ce n'est pas une élégance : une expression liée
        DOIT vivre dans un corps de méthode, seul endroit relu à chaque
        appel donc tracé. En champ, elle serait figée au montage (cf.
        traps.md § « un champ de bz-data n'est pas réactif »).

        ⚠️ ``target`` vient de :meth:`_value_target`, PAS de
        :func:`~bretzel.components.inputs._picker_field.value_expr` : ici on est dans un corps de méthode, où
        l'identifiant nu ne résout pas. Payé une fois — le panneau
        entier était inerte en mode littéral, et seul le navigateur le
        disait (« val is not defined »).
        """
        local = ""
        if self._binding_metadata.get("value") is None:
            (key,) = self._scope_keys("value")
            sync = server_sync_marker(
                key, enabled=self._value_server_backed("value")
            )
            local = f"{key}: {json.dumps(initial)},{sync} "
        return (
            "{...$bz.time.scope,open: false,"
            + local
            + f"_closeOnPick: {'true' if self._close_on_pick else 'false'},"
            + f"_read() {{ return {target}; }},"
            + f"_write(v) {{ {target} = v; }}"
            + "}"
        )

    def _icon(self, name: str, size_cfg: dict[str, Any]) -> Element:
        return Element(
            tag="iconify-icon",
            attrs={
                "icon": f"lucide:{name}",
                "class": " ".join(
                    p
                    for p in (
                        self.compose_class(
                            "button_icon", apply_variant_size_modifiers=False
                        ),
                        size_cfg.get("button_icon", ""),
                    )
                    if p
                ),
            },
            children=(),
        )

    def _column(
        self,
        part: int,
        label: str,
        values: list[str],
        low: str,
        high: str,
        size_cfg: dict[str, Any],
        disabled: bool,
        *,
        part_is_hour: bool,
    ) -> Element:
        """Une colonne aimantée — ses cellules, et lesquelles sont hors
        bornes.

        Le bornage d'une HEURE regarde la fin de l'heure (``09:59``) pour
        le plancher et son début (``09:00``) pour le plafond : une heure
        n'est exclue que si AUCUNE de ses minutes ne tient dans
        ``[min, max]``. Sans cette nuance, ``min="09:30"`` griserait
        l'heure 09 entière et 09:45 deviendrait inatteignable.
        """
        off = [
            v
            for v in values
            # Une minute ne se borne que s'il n'y a qu'une heure
            # possible ; sinon ``:45`` serait grisé parce qu'il sort
            # à la dernière heure, alors qu'il est valide à toutes
            # les autres. On laisse donc passer, la saisie clavier
            # étant de toute façon la porte d'entrée précise.
            if part_is_hour
            and not (
                _in_bounds(f"{v}:59", low, "")
                and _in_bounds(f"{v}:00", "", high)
            )
        ]

        header = Element(
            tag="div",
            attrs={
                "class": " ".join(
                    p
                    for p in (
                        self.compose_class(
                            "column_label", apply_variant_size_modifiers=False
                        ),
                        size_cfg.get("column_label", ""),
                    )
                    if p
                )
            },
            children=(TextNode(label),),
        )
        return Element(
            tag="div",
            attrs={
                "class": " ".join(
                    p
                    for p in (
                        self.compose_class(
                            "column", apply_variant_size_modifiers=False
                        ),
                        size_cfg.get("column", ""),
                    )
                    if p
                ),
                "role": "listbox",
                "aria-label": label,
                # ── La colonne se DÉCRIT, elle ne s'écrit pas ────────
                # Ses cellules sont peintes par ``$bz.time.fill``. Ce
                # qui voyage ici, c'est la donnée dont elle est faite :
                # les valeurs, celles qui sont hors bornes, et le mot
                # qui préfixe l'``aria-label`` de chacune.
                "data-bz-part": str(part),
                "data-bz-values": ",".join(values),
                "data-bz-off": ",".join(off),
                "data-bz-cell-label": label,
            },
            children=(header,),
        )


__all__ = ["TimePicker", "normalise_to_hhmm_js", "time_to_hhmm"]

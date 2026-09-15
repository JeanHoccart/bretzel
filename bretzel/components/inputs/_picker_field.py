"""La mécanique commune des *picker fields* — champ éditable + popover.

Trois composants ont exactement la même silhouette : un ``<div>`` wrapper
qui porte le scope, un cadre à un seul anneau de focus contenant un
``<input>`` typable et un ou deux boutons icône, un ``<input
type=hidden>`` porteur de form data, et un panneau ancré. Seuls changent
le **codec de valeur**, le **normaliseur au blur** et le **contenu du
panneau**.

  DatePicker · DateRangePicker · TimePicker

Ce module extrait ce qui est identique — et rien d'autre. En
particulier il ne touche **pas** aux chaînes de classes : elles restent
par composant (`feedback_no_shared_style_tokens`), et les trois n'ont
même pas la même forme de table de tailles (les deux pickers de date
indexent `sizes[slot][size]`, la forme inversée encore en dette dans
``test_size_reaches_slots._INVERTED_SHAPE`` ; TimePicker utilise la forme
canonique). Les fabriques ci-dessous prennent donc des classes **déjà
composées**, jamais un thème.

Pourquoi extraire maintenant : le seuil du dépôt (« deux fois c'est une
coïncidence, trois fois c'est un pattern ») a été franchi le 2026-08-02
avec TimePicker. Et le prochain arrivant compte — trois pickers restent
à écrire (month / week / date_time), qui hériteraient sinon des mêmes
blocs recopiés.

⚠️ **La leçon qui a motivé le découpage.** En écrivant TimePicker j'ai
pris DatePicker comme gabarit et recopié à la main deux blocs que le
socle avait DÉJÀ extraits depuis (``hidden_carrier_attrs``,
``relocate_server_action``) — parce que DatePicker est antérieur à ces
primitives et que personne ne l'a migré. Deux gates l'ont refusé. C'est
exactement ce que ce module empêche de recommencer : le gabarit et le
code partagé sont désormais le même objet.
"""

from __future__ import annotations

import json
from typing import Any

from bretzel.components.base import Component, stamp_display_none
from bretzel.components.base._wiring import (
    anchored_dismiss_init,
    anchored_panel_effect,
    bool_attr,
    calendar_value_mirror,
    hidden_carrier_attrs,
    imperative_listeners,
    relocate_server_action,
    server_sync_marker,
)
from bretzel.core.tree import Element, Node

#: Les deux events déclarés par les trois pickers qui NE BULLENT PAS.
#: C'est toute la raison de :func:`relocate_field_events`.
_NON_BUBBLING = ("focus", "blur")


def value_expr(component: Any, *, local: str | None = None) -> str:
    """L'expression que lisent les DIRECTIVES pour la valeur du champ.

    Liée (``value=state.x``) → le chemin du magasin. Littérale → le nom
    NU du champ de scope : une directive tourne dans un ``with($scope)``,
    donc l'identifiant y résout.

    ``local`` par défaut = la clé DÉCLARÉE sur la prop
    (``reactive_prop(scope_keys=)``, lue par ``_scope_keys``). Elle
    valait ``"val"`` en dur, ce qui faisait de ce helper une SECONDE
    source pour un fait déjà déclaré : un picker qui aurait changé de
    clé aurait émis un littéral sous un nom et des directives sous
    l'autre — silencieusement, puisque les deux existent. Le paramètre
    reste, pour un appelant qui adresse une variable de scope qui n'est
    PAS la valeur de la prop.

    ⚠️ Ces deux lignes étaient écrites **cinq fois**, une par picker, et
    ce qui différait n'était pas le code — c'étaient les docstrings :
    quatre explications du même mécanisme, une absence. C'est exactement
    ce que `creating-a-component.md` reproche aux rendus non factorisés,
    « ce qui empêchait de savoir si les deux se comportaient pareil sans
    relire les deux ». Les cinq appelaient DÉJÀ les helpers de cette
    famille : elle était factorisée à 90 %, ces deux lignes étaient
    restées derrière.
    """
    binding = component._binding_metadata.get("value")
    if binding is not None:
        return component.path_of(binding)
    return local if local is not None else component._scope_keys("value")[0]


def relocate_field_events(
    root_attrs: dict[str, Any],
    *,
    value_carrier: dict[str, Any],
    focusable: dict[str, Any],
) -> None:
    """Vider la racine de ses handlers, vers le porteur qui peut les tirer.

    Un picker a une racine ``<div>`` : **non focusable, et sans ``name``
    ni ``value``**. Trois choses en découlent, et chacune est un bug
    silencieux si on l'oublie :

    - ``focus`` / ``blur`` ne **bullent pas**. Un handler laissé sur la
      racine ne peut structurellement JAMAIS partir — il n'y a pas de
      chemin par lequel l'event y arriverait. (``change``, lui, bulle
      nativement depuis l'input, d'où le traitement différent.)
    - le bundle d'action SERVEUR doit être routé selon ce que le handler
      écoute vraiment : un ``change`` vers le porteur de valeur (sinon la
      FormData part vide), un ``focus`` vers l'élément focusable. C'est
      ``relocate_server_action`` qui décide, en lisant ``hx-trigger`` —
      écrit à la main, c'est le bug Slider qui revient (un ``on_focus``
      callable posé sur un input caché, qui se déclenche au change).
    - la version STRING de ces handlers (``bz-on:focus``) doit suivre le
      même chemin que la version callable, sinon les deux formes du même
      prop se comportent différemment.

    Les deux dictionnaires sont remplis EN PLACE ; l'appelant les verse
    sur ses éléments. ``root_attrs`` est vidé des clés déplacées.
    """
    for event in _NON_BUBBLING:
        key = f"bz-on:{event}"
        if key in root_attrs:
            focusable[key] = root_attrs.pop(key)
    relocate_server_action(
        root_attrs, value_carrier=value_carrier, focusable=focusable
    )


def detach_wrapper_carriers(component: Any, root_attrs: dict[str, Any]) -> str:
    """Retirer de la racine ce qui n'y a aucun sens, et rendre le ``name``.

    ``value`` : le picker adresse sa valeur par une EXPRESSION (le chemin
    de store, ou une variable de scope). La directive auto-émise par le
    socle réécrirait un ``value=""`` inutile sur un ``<div>`` à chaque
    tick réactif — et l'audit de landing des porteurs le signale.

    ``name`` : l'autoname l'injecte sur la racine, mais le porteur de
    form data est l'``<input type=hidden>``, qui se le pose lui-même. Le
    relâcher garantit que le nom vit à **exactement un endroit**.

    Retourne le nom de champ résolu — explicite, puis autoname, puis le
    repli ``"value"`` qui garde un picker non lié présent dans le
    formulaire. Les trois pickers avaient la même chaîne.
    """
    component.release_root_attr("value", root_attrs)
    component.release_root_attr("name", root_attrs)
    return str(
        component._reactive_values.get("name")
        or component._derive_field_name()
        or "value"
    )


def hidden_carrier(
    *,
    value_expr: str,
    initial: Any,
    name: str,
    required: bool,
    extra: dict[str, Any] | None = None,
) -> Element:
    """L'``<input type=hidden>`` qui porte la valeur dans la form data.

    Le squelette vient de ``hidden_carrier_attrs`` (type / bz-ref /
    value SSR / bz-attr:value) ; ``name`` et ``required`` restent posés
    ici parce que la primitive les laisse VOLONTAIREMENT à l'appelant —
    un ``name`` par défaut injecterait un champ parasite dans tout
    formulaire englobant, ce qui n'est pas le cas d'un picker mais l'est
    d'un Tabs ou d'un Accordion.

    ``required`` vit sur ce porteur et **pas** sur le champ visible : la
    validation HTML doit regarder la valeur réelle, pas le texte en cours
    de frappe. Le champ visible ne reçoit qu'un ``aria-required``.

    ⚠️ **``change_emit_effect`` n'est pas décoratif — sans lui le picker
    est INERTE.** ``relocate_server_action`` route le bundle ``on_change=``
    ICI, parce que c'est ce porteur que la FormData doit trouver ; or un
    input caché ne fire jamais ``change`` tout seul, et le
    ``<bz-calendar>`` du panneau écrit la valeur **par programme** — une
    écriture de ``.value`` n'émet aucun événement. Les cinq pickers ont
    donc vécu sans qu'aucun ``on_change`` serveur ne parte, sans une
    erreur ni un avertissement (mesuré le 2026-08-21 : « la période ne
    filtre pas »). C'est le MÊME dispatcher que les onze autres porteurs
    cachés du catalogue, et la classe est gatée par
    ``tests/consistency/test_a_relocated_change_reaches_its_carrier.py``.
    """
    attrs: dict[str, Any] = {
        **hidden_carrier_attrs(value_expr, initial=initial),
        "name": name,
    }
    if required:
        attrs["required"] = True
    if extra:
        attrs.update(extra)
    return Element(tag="input", attrs=attrs, children=())


def calendar_picker_scope(
    component: Any, *, value_expr: str, initial: str
) -> str:
    """Le ``bz-data`` d'un picker dont le panneau est un ``<bz-calendar>``.

    Deux modes, et c'est toute la logique :

    - **lié** — la valeur vit dans le store, donc le scope ne porte que
      le drapeau ``open``. Aucune synchro à maintenir : chaque directive
      adresse ``$bz.state.<path>`` directement.
    - **littéral** — une variable locale, nommée par la clé de scope
      DÉCLARÉE sur la prop, sème la valeur SSR.
      ``scope.absorb`` la PRÉSERVE à travers un morph, ce qui est
      exactement ce qu'on veut pour l'édition d'un utilisateur — mais
      qui ferait ignorer un changement SERVEUR sur un ``value=state.x``.
      D'où ``_serverSync``, émis UNIQUEMENT quand la valeur est
      server-backed (un littéral pur garde sa valeur client).

    Utilisé par :func:`render_calendar_field` pour MonthPicker et
    WeekPicker. DatePicker construit encore son scope séparément ;
    DateRangePicker porte deux variables (``vstart`` / ``vend``).
    """
    if component._binding_metadata.get("value") is not None:
        return "{open: false}"
    (key,) = component._scope_keys("value")
    sync = server_sync_marker(
        key, enabled=component._value_server_backed("value")
    )
    return (
        f"{{open: false, {key}: {json.dumps(initial)}"
        + (f",{sync}" if sync else "")
        + "}"
    )


def panel_calendar(owner: Any, cal_kwargs: dict[str, Any]) -> Element:
    """Le ``<bz-calendar>`` du panneau — détaché, mais ADRESSÉ par son picker.

    Les quatre pickers de date construisaient ces trois lignes à
    l'identique. Elles vivent ici pour l'``id``, qui est load-bearing et
    ne se devine pas.

    ⚠️ **Pourquoi un ``id`` explicite.** Un composant construit pendant le
    ``render()`` d'un autre n'a pas son constructeur sur la
    ``parent_stack`` — le picker n'est pas un conteneur, il ne s'y empile
    jamais. Son ``id`` se dérive donc de ``"root"`` et vaut
    ``root_calendar_0``, ``root_calendar_1``… **sur toutes les pages**.

    Or le ``bz-id`` indexe le magasin de scopes du runtime, une ``Map``
    qui SURVIT à une navigation ``hx-boost`` (le runtime n'est pas
    rechargé). Deux pages de picker différentes revendiquaient donc le
    même scope : après un clic dans la sidebar, le calendrier de la
    nouvelle page retrouvait le scope de l'ancienne, dont le parent est
    le picker de la page PRÉCÉDENTE. Le handler ``on_change`` écrivait
    alors sa valeur dans un scope mort — grille surlignée, champ vide, et
    un F5 pour s'en sortir. Le ``year`` / ``month`` de l'ancienne page
    fuyait par le même chemin, ce qui faisait apparaître le calendrier sur
    une année qu'on n'avait pas choisie.

    Dériver l'``id`` du picker le rend unique par page, donc les deux
    scopes ne se confondent plus. ``setdefault`` : un appelant qui passe
    son propre ``id=`` reste maître.

    Le durcissement complémentaire est côté runtime — ``ensureScope``
    re-résout le parent d'un scope retrouvé, pour que la CLASSE ne
    revienne pas par une autre collision d'id.
    """
    import datetime as _dt

    from bretzel.components.inputs.calendar import Calendar

    cal_kwargs.setdefault("id", f"{owner.id}_calendar")
    # ── Le mois affiché suit la VALEUR, pas la date du jour ──────────
    # ``Calendar`` sait déjà dériver son mois initial de ``value``
    # (``calendar.py`` : ``month=`` explicite, sinon le mois de la valeur,
    # sinon aujourd'hui). Encore faut-il qu'il REÇOIVE la valeur : les
    # quatre pickers ne la lui passaient pas, donc un
    # ``ui.date_picker(value=date(2026, 6, 15))`` s'ouvrait sur le mois
    # COURANT, avec le jour sélectionné invisible parce que hors grille.
    # Mesuré le 2026-08-19 sur les quatre : ``month="2026-08-01"`` pour
    # une valeur de juin, et aucun attribut ``value`` sur le
    # ``<bz-calendar>``.
    #
    # Seule une valeur LITTÉRALE est transmise : une ``ClientBinding`` n'a
    # pas de valeur au SSR, et c'est le ``bz-effect`` de miroir qui la
    # posera côté client (cf. ``calendar_value_mirror``).
    # ⚠️ La graine est DÉSTAMPÉE avant d'être passée. Une valeur adossée à
    # un ``ServerState`` n'est pas une ``date`` nue : c'est un ``_BoundDate``
    # (sous-classe de ``date``) qui porte le nom de son champ, et de là le
    # calendrier imbriqué DÉRIVAIT son propre ``name=`` — deux
    # ``name="appointment"`` dans la même page, donc un champ parasite dans
    # la FormData. Attrapé par ``test_autoname_from_server_state_field``.
    def _plain(v: object) -> object:
        if isinstance(v, _dt.date):
            return _dt.date(v.year, v.month, v.day)
        return str(v)

    if "value" not in cal_kwargs:
        seed = getattr(owner, "_reactive_values", {}).get("value")
        literal = (_dt.date, str)
        if isinstance(seed, literal) and seed:
            cal_kwargs["value"] = _plain(seed)
        elif isinstance(seed, (list, tuple)) and seed and all(
            isinstance(v, literal) and v for v in seed
        ):
            cal_kwargs["value"] = [_plain(v) for v in seed]
    inner = Calendar(**cal_kwargs)
    # Le calendrier est un enfant de RENDU, pas un enfant d'arbre : sans
    # ce détachement il resterait dans ``root_children`` et se rendrait
    # une seconde fois en orphelin.
    Component._detach_from_parent(inner)
    return inner.render()


def icon_button(
    *,
    icon: str,
    css: str,
    icon_css: str,
    aria_label: str,
    on_click: str,
    disabled: bool,
    show_when: str | None = None,
    hidden_at_ssr: bool = False,
    extra: dict[str, Any] | None = None,
) -> Element:
    """Un des deux boutons du cadre : le ``×`` ou l'ouvre-panneau.

    ``show_when`` (le ``×``) le fait apparaître seulement quand il y a
    quelque chose à effacer ; ``hidden_at_ssr`` pré-tamponne
    ``display:none`` pour qu'il ne clignote pas avant que le runtime
    prenne la main.

    L'appelant passe des classes **déjà composées** : les trois pickers
    n'ont pas la même forme de table de tailles, et les chaînes de style
    restent par composant de toute façon.
    """
    attrs: dict[str, Any] = {
        "type": "button",
        "class": css,
        "aria-label": aria_label,
        "bz-on:click": on_click,
    }
    if show_when is not None:
        attrs["bz-show"] = show_when
        if hidden_at_ssr:
            stamp_display_none(attrs)
    if disabled:
        attrs["disabled"] = True
    if extra:
        attrs.update(extra)
    return Element(
        tag="button",
        attrs=attrs,
        children=(
            Element(
                tag="iconify-icon",
                attrs={"icon": f"lucide:{icon}", "class": icon_css},
                children=(),
            ),
        ),
    )


def trigger_button(
    *,
    icon: str,
    css: str,
    icon_css: str,
    aria_label: str,
    disabled: bool,
    open_expr: str = "open",
) -> Element:
    """Le bouton qui bascule le panneau.

    ``$event.stopPropagation()`` est load-bearing : sans lui le clic
    remonte jusqu'au ``clickOutside`` posé sur la racine, qui referme
    aussitôt ce que le toggle vient d'ouvrir.

    ``aria-expanded`` est rendu STATIQUE puis gardé réactif — et via
    ``bool_attr``, parce qu'un booléen nu ferait DROPPER l'attribut à
    false, alors qu'un lecteur d'écran doit entendre « replié ».
    """
    return icon_button(
        icon=icon,
        css=css,
        icon_css=icon_css,
        aria_label=aria_label,
        on_click=f"$event.stopPropagation(); {open_expr} = !{open_expr}",
        disabled=disabled,
        extra={
            "aria-expanded": "false",
            "bz-attr:aria-expanded": bool_attr(open_expr),
        },
    )


def clear_button(
    *,
    css: str,
    icon_css: str,
    aria_label: str,
    clear_js: str,
    show_when: str,
    has_value_at_ssr: bool,
    disabled: bool,
) -> Element:
    """Le ``×`` — visible seulement quand il y a une valeur à effacer."""
    return icon_button(
        icon="x",
        css=css,
        icon_css=icon_css,
        aria_label=aria_label,
        on_click=f"$event.stopPropagation(); {clear_js}",
        disabled=disabled,
        show_when=show_when,
        hidden_at_ssr=not has_value_at_ssr,
    )


def anchored_panel(
    *,
    css: str,
    children: tuple[Node, ...],
    placement: str = "bottom-start",
    open_expr: str = "open",
    extra_effect: str = "",
) -> Element:
    """Le popover : ancré par ``$bz.helpers.floating``, fermé au SSR.

    ``bz-ref="bzpanel"`` n'est pas décoratif — le ``clickOutside`` de la
    racine le résout à CHAQUE clic pour savoir ce qui compte comme
    « dedans ». Sans lui, un clic sur le rembourrage du panneau (ou sur
    une cellule désactivée, qui ne dispatche rien) refermerait le
    popover. Gardé par ``test_dismiss_scope_owns_its_panel``.

    Le pré-tampon ``display:none`` est l'anti-FOUC : le panneau part
    fermé, et sans lui il apparaît le temps d'une frame avant que le
    premier effet ne tourne.
    """
    effect = anchored_panel_effect(open_expr, placement)
    if extra_effect:
        effect = f"{effect}; {extra_effect}"
    attrs: dict[str, Any] = {
        "class": css,
        "bz-ref": "bzpanel",
        "bz-effect": effect,
    }
    stamp_display_none(attrs)
    return Element(tag="div", attrs=attrs, children=children)


def render_calendar_field(
    component: Any,
    *,
    initial: str,
    value_expr: str,
    blur_js: str,
    mirror_granularity: str | None,
    clearable: bool,
    clear_label: str,
    trigger_icon: str,
    trigger_label: str,
    calendar_kwargs: dict[str, Any],
    root_css: str,
    frame_css: str,
    panel_css: str,
    field_css: str,
    clear_css: str,
    trigger_css: str,
    icon_css: str,
) -> Element:
    """Le rendu ENTIER d'un picker à panneau ``<bz-calendar>``.

    Mesuré le 2026-08-19 : ``MonthPicker.render`` et ``WeekPicker.render``
    faisaient 130 et 125 lignes, dont **107 identiques** — 82 %. Ce ne
    sont pas deux composants qui se ressemblent, c'est un composant écrit
    deux fois, dont les différences tiennent en sept valeurs : le format
    de la valeur initiale, la granularité du miroir, le JS de
    normalisation au blur, deux libellés, une icône, et les kwargs du
    calendrier.

    Les fabriques de ce module (``hidden_carrier``, ``trigger_button``…)
    couvraient déjà les MORCEAUX ; ce qui restait recopié, c'était leur
    ORCHESTRATION — l'ordre des appels, le routage des handlers vers le
    bon porteur, le chaînage du blur. C'est là que les divergences font
    mal : un picker qui oublie de chaîner le ``on_blur=`` de
    l'utilisateur perd son rappel sans rien casser de visible.

    ⚠️ **Les classes arrivent COMPOSÉES, jamais un thème** — la règle de
    ce module (`feedback_no_shared_style_tokens`), et une nécessité
    technique : les deux pickers de date indexent leur table de tailles
    dans la forme inversée (``sizes[slot][size]``), les autres dans la
    forme canonique. Une fonction qui lirait le thème elle-même devrait
    connaître les deux, et se tromperait sur l'un des deux.
    """
    root_attrs = component.emit_attrs()
    hidden_extra: dict[str, Any] = {}
    relocated: dict[str, Any] = {}
    relocate_field_events(
        root_attrs, value_carrier=hidden_extra, focusable=relocated
    )
    name = detach_wrapper_carriers(component, root_attrs)
    root_attrs["class"] = root_css
    root_attrs["bz-data"] = calendar_picker_scope(
        component, value_expr=value_expr, initial=initial
    )
    # ── Les récepteurs de l'API impérative ───────────────────────────
    #
    # Sans eux, `.open()` et `.set()` dispatchent un événement que
    # PERSONNE n'écoute : les méthodes existent, elles émettent du JS
    # valide, et il ne se passe rien. C'est le mode d'échec le plus
    # coûteux — il ne lève pas et ne se voit pas en revue.
    #
    # En mode LIÉ, la méthode écrit directement dans le store et ces
    # écouteurs ne se déclenchent jamais ; on les pose quand même, pour
    # que le contrat soit le même dans les deux modes. C'est le choix
    # déjà fait par Sidebar, Dialog et Select.
    for _ev, _handler in imperative_listeners("open").items():
        root_attrs.setdefault(_ev, _handler)
    root_attrs.setdefault(
        "bz-on:bz-set", f"{value_expr} = $event.detail.value"
    )
    # Miroir vers l'attribut ``value`` OBSERVÉ du ``<bz-calendar>``.
    # ``bz-attr:value`` sur un custom element écrit la PROPRIÉTÉ, pas
    # l'attribut, donc il court-circuiterait ``attributeChangedCallback``
    # — d'où le ``setAttribute`` explicite (cf. traps.md).
    mirror = (
        calendar_value_mirror(value_expr, is_range=False)
        if mirror_granularity is None
        else calendar_value_mirror(
            value_expr, is_range=False, granularity=mirror_granularity
        )
    )
    root_attrs["bz-effect"] = "(() => { " + mirror + "})()"
    root_attrs["bz-init"] = anchored_dismiss_init("open")

    disabled = bool(component._reactive_values.get("disabled"))
    required = bool(component._reactive_values.get("required"))

    hidden_input = hidden_carrier(
        value_expr=value_expr, initial=initial, name=name,
        required=required, extra=hidden_extra,
    )

    field_attrs: dict[str, Any] = {
        "type": "text",
        "placeholder": component._placeholder,
        "class": field_css,
        "value": initial,
        "bz-model": value_expr,
        "bz-on:blur": blur_js,
        "autocomplete": "off",
        "inputmode": "numeric",
        "spellcheck": "false",
        "aria-label": component._placeholder,
    }
    if disabled:
        field_attrs["disabled"] = True
    if required:
        field_attrs["aria-required"] = "true"
    if "bz-on:blur" in relocated:
        # Enchaîner : la normalisation interne ET le ``on_blur=`` de
        # l'utilisateur doivent tourner tous les deux.
        relocated["bz-on:blur"] = (
            f"{field_attrs['bz-on:blur']}; {relocated['bz-on:blur']}"
        )
    field_attrs.update(relocated)
    component.forward_binding("disabled", field_attrs)

    frame_children: list[Node] = [
        Element(tag="input", attrs=field_attrs, children=())
    ]
    if clearable:
        cross = clear_button(
            css=clear_css, icon_css=icon_css,
            aria_label=clear_label, clear_js=f"{value_expr} = ''",
            show_when=value_expr, has_value_at_ssr=bool(initial),
            disabled=disabled,
        )
        component.forward_binding("disabled", cross.attrs)
        frame_children.append(cross)
    opener = trigger_button(
        icon=trigger_icon, css=trigger_css, icon_css=icon_css,
        aria_label=trigger_label, disabled=disabled,
    )
    component.forward_binding("disabled", opener.attrs)
    frame_children.append(opener)

    frame = Element(
        tag="div",
        attrs={"class": frame_css, "bz-ref": "bztrigger"},
        children=tuple(frame_children),
    )

    if disabled:
        calendar_kwargs["disabled"] = True

    return Element(
        tag=component._tag,
        attrs=root_attrs,
        children=(
            hidden_input,
            frame,
            anchored_panel(
                css=panel_css,
                children=(panel_calendar(component, calendar_kwargs),),
            ),
        ),
    )


__all__ = [
    "anchored_panel",
    "clear_button",
    "detach_wrapper_carriers",
    "hidden_carrier",
    "icon_button",
    "panel_calendar",
    "relocate_field_events",
    "render_calendar_field",
    "trigger_button",
]

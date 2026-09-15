"""``SignaturePad`` — signer au doigt ou à la souris, dans un formulaire.

Usage ::

    class Contract(PageState):
        signature: str = field(default="")

    with ui.form(on_submit=sign):
        ui.signature_pad(value=contract.signature)
        ui.button("Signer", type="submit")

    def sign(doc: Contract) -> None:
        doc.signature      # "data:image/png;base64,iVBORw0KG…"

**La valeur est un PNG en data-URL**, et elle vit dans ton `ServerState`.
``AUTONAME_FROM = "value"`` dérive le ``name`` de l'input caché depuis le
champ que tu lui passes, et
:func:`~bretzel.server.routing.actions._hydrate_state` le réécrit dans
l'instance à la soumission — comme n'importe quel champ de formulaire. Ni
endpoint, ni encodage à écrire.

Le PNG plutôt que les points ou du SVG : le consommateur d'une signature
veut une IMAGE (l'embarquer dans un PDF, l'afficher dans un dossier, la
stocker). Rendre les points obligerait chaque appelant à réécrire le
rasteur.

⚠️ **``value`` est bindable, mais y lier un ``ClientState`` se paie.**
Le socle l'exige (``TWO_WAY_PROPS ⊆ BINDABLE_PROPS`` : un champ que le
client écrit ne peut pas être form-bound sans être bindable), et en mode
LOCAL — le cas normal, ``value=doc.signature`` sur un ServerState — la
data-URL vit dans le scope JS et ne coûte rien sur le fil. En revanche
le snapshot ``ClientState`` part **entier à chaque POST d'action**
(``runtime/_src/05_bridge.js``), donc un pad lié à un ``ClientState``
renverrait ses dizaines de kilo-octets à chaque clic de la page. Il n'y
a pas de mode « delta » pour l'éviter — il a été retiré le 2026-08-14,
sa sémantique étant fausse (cf. le docstring de ``ClientState``). Le
seul levier est ``send_to_server=False``, qui ne s'applique PAS ici :
une signature est écrite par le client, elle doit remonter. À ne faire que si un autre composant doit lire la
signature côté client.

**Rien n'est publié pendant le geste** : la data-URL est écrite au LEVER
du stylo. Un ``on_change`` câblé fait donc un POST par trait — c'est
supportable et c'est explicite, là où publier par frame ne le serait pas.

**Le pad est VIDE, pas blanc, tant que rien n'est tracé.** Un canvas neuf
rend un PNG parfaitement valide — un rectangle blanc — et le publier
ferait passer « pas encore signé » pour « signé » côté serveur, sans que
rien ne semble faux. Zéro trait ⇒ chaîne vide.

**Une signature déjà là est REPEINTE.** Passer une data-URL existante
(un dossier rouvert) la charge à l'hydratation et la peint comme couche
de fond, sous les traits neufs — donc elle survit au redimensionnement
comme le reste, et resoumettre sans y toucher ne l'efface pas.
``.clear()`` l'emporte avec les traits : « effacer » veut dire un cadre
vide, pas « revenir à la signature d'avant ». *(La première version ne
la chargeait pas : le cadre s'affichait vide ET sans invite, puisque le
SSR avait déjà posé ``data-empty="false"`` — le composant annonçait une
signature en n'en montrant aucune.)*

Le trait est encré avec la couleur de texte LUE sur le canvas, jamais
configurée : elle suit le mode sombre toute seule. Il n'y a donc pas de
``pen_color=`` — il aurait figé une encre invisible sur l'autre fond.

Imperative API : ``.clear()``. Une signature se refait, elle ne se
retouche pas — pas d'``undo()``. (Le runtime garde bien les points, mais
pour redessiner après un changement de taille : un canvas s'efface quand
on le redimensionne, et un téléphone qu'on tourne le redimensionne.)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.actions.button import Button
from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    hidden_carrier_attrs,
    pop_change_handler,
    server_sync_marker,
)
from bretzel.components.inputs.signature_pad.theme import SIGNATURE_PAD_THEME
from bretzel.core.tree import Element, Node
from bretzel.render import text


class SignaturePad(Component):
    """Surface de signature — pointeur / doigt → PNG en data-URL."""

    THEME: ClassVar[dict[str, Any]] = SIGNATURE_PAD_THEME
    THEME_KEY: ClassVar[str] = "signature_pad"
    # ``value`` EST bindable, et l'invariant du socle l'exige :
    # ``TWO_WAY_PROPS ⊆ BINDABLE_PROPS`` (``test_two_way_props``). Un
    # champ que le client écrit — et il l'écrit, l'utilisateur dessine —
    # ne peut pas être form-bound sans être bindable. La réserve sur le
    # poids reste vraie et vit dans la docstring du module : elle ne
    # concerne QUE le cas où l'appelant lie à un ``ClientState``.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("value",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("clear",)
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    # ``names_field=True`` : c'est CETTE prop qui donne son ``name`` HTML
    # au porteur caché, donc le champ ServerState qu'on lui passe. Le
    # ClassVar ``AUTONAME_FROM`` en est DÉRIVÉ — le déclarer à la main
    # est refusé au chargement (deux endroits pour un seul fait).
    # ``writes=True`` est exigé par ``names_field`` et c'est juste : le
    # CLIENT écrit bien cette valeur (il dessine) — et c'est précisément
    # ce qui force ``value`` dans ``BINDABLE_PROPS`` ci-dessus. Ce qui ne
    # remonte JAMAIS dans un signal, c'est le tracé lui-même : les points
    # vivent dans le canvas, seule la data-URL atterrit sur le porteur.
    # ``never_code`` : cette valeur est une **data-URL**, et son padding
    # base64 s'écrit ``=`` ou ``==`` — donc un tracé sur quatre environ
    # sortait classé « expression client » de l'heuristique, partait en
    # ``bz-attr:value=`` et faisait planter le boot du runtime (mesuré le
    # 2026-08-13). Ça avait été réparé par une exclusion ``data:`` DANS
    # l'heuristique ; elle est retirée depuis le 2026-08-26 au profit de
    # cette déclaration, qui dit le fait là où il est vrai. C'est le seul
    # porteur d'URI dont le nom de prop ne l'annonce pas — d'où son entrée
    # nominative dans ``test_a_url_prop_is_never_read_as_code``.
    value: str | None = reactive_prop(
        default=None, emit_attr=False, writes=True, names_field=True,
        never_code=True,
    )
    # ``None`` : un défaut de ``reactive_prop`` est résolu à l'import,
    # donc figerait l'anglais quelle que soit la langue de l'app.
    placeholder: str | None = reactive_prop(default=None, emit_attr=False)
    clear_label: str | None = reactive_prop(default=None, emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        value: str | None = None,
        placeholder: str | None = None,
        clear_label: str | None = None,
        disabled: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None.
        super().__init__(
            value=value,
            placeholder=placeholder,
            clear_label=clear_label,
            disabled=disabled,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )

    # ── API impérative ─────────────────────────────────────────────────

    def clear(self) -> str:
        """Effacer le tracé. Toujours un dispatch DOM.

        **Y compris quand ``value`` porte une binding**, et c'est la
        seule raison qui tienne : effacer n'est pas « écrire la chaîne
        vide ». Il faut aussi jeter ``_strokes``, oublier le ``_base``
        d'une signature rouverte et repeindre le canvas — trois choses
        que seul le runtime sait faire. Un write-through
        (:meth:`Component._value_command`, le patron des onze ``.set()``)
        laisserait le cadre montrer un tracé que l'état dit absent.
        """
        return self._dispatch_command("bz-clear")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        size_table = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = size_table.get(size_key, size_table.get("md", {}))
        disabled = bool(self._reactive_values.get("disabled"))
        initial = self._reactive_values.get("value") or ""
        # ``is None`` et pas ``or`` : ``placeholder=""`` est un opt-out
        # explicite qui doit rester silencieux, et un ``or`` lui
        # redonnerait le défaut.
        placeholder = self._reactive_values.get("placeholder")
        if placeholder is None:
            placeholder = text("signature_pad.placeholder")

        # ── Binding de ``value`` ─────────────────────────────────────
        value_binding = self._binding_metadata.get("value")
        scope_key = self._scope_keys("value")[0]
        binding_path = (
            self.path_of(value_binding) if value_binding is not None else None
        )
        value_expr = binding_path or scope_key

        canvas_attrs: dict[str, Any] = {
            "class": self.slot_class("canvas"),
            "bz-ref": "bzcanvas",
            # Le canvas n'est PAS focusable et ne porte aucun rôle : ce
            # qui est annoncé et atteignable au clavier, c'est l'input
            # caché (un vrai contrôle de formulaire, avec son ``name``)
            # et le bouton Effacer. Poser un ``role`` sur une surface de
            # dessin annoncerait un contrôle qu'aucune touche ne pilote.
            "aria-hidden": "true",
        }
        if disabled:
            # Lu par ``_locked()`` côté runtime. Un attribut plutôt qu'un
            # champ de scope : ``disabled`` n'est pas bindable, donc la
            # valeur est figée au rendu et n'a rien à faire dans un
            # signal.
            canvas_attrs["data-bz-pad-locked"] = ""
        else:
            canvas_attrs["bz-on:pointerdown"] = "_start($event)"
            canvas_attrs["bz-on:pointermove"] = "_draw($event)"
            canvas_attrs["bz-on:pointerup"] = "_end($event)"
            canvas_attrs["bz-on:pointercancel"] = "_end($event)"
            # Rebranché à chaque rescan, pas au ``bz-init`` : celui-ci
            # est one-shot par nœud, or un canvas remplacé par un morph
            # ne serait alors jamais observé (même raison, même remède
            # que ``_observeGeom`` du Carousel).
            canvas_attrs["bz-effect"] = "_observe()"

        pad_children: list[Node] = [
            Element(tag="canvas", attrs=canvas_attrs, children=()),
            Element(
                tag="div",
                attrs={"class": self.slot_class("baseline")},
                children=(),
            ),
        ]
        if placeholder:
            pad_children.append(
                Element(
                    tag="div",
                    attrs={
                        "class": self.slot_class(
                            "hint", size_cfg.get("hint", "")
                        ),
                        # Le même ``data-empty`` que le cadre porte : le
                        # variant Tailwind de l'invite le lit sur
                        # elle-même, donc il doit y être aussi.
                        "data-empty": "false" if initial else "true",
                    },
                    children=(self.emit_text_slot(placeholder),),
                )
            )

        pad = Element(
            tag="div",
            attrs={
                "class": self.slot_class("pad", size_cfg.get("pad", "")),
                # SSR : vide sauf si une signature est déjà là (un
                # dossier rouvert). Le runtime prend le relais au
                # premier trait.
                "data-empty": "false" if initial else "true",
                "data-locked": "true" if disabled else "false",
            },
            children=tuple(pad_children),
        )

        # ── Input caché — form data + source du ``change`` ───────────
        # Le porteur standard : ``bz-attr:value`` reporte l'état dans le
        # DOM, ``change_emit_effect`` en tire le ``change``. Le runtime
        # n'écrit donc QUE l'état, jamais l'input — un seul auteur.
        root_attrs = self.emit_attrs()
        relocated = pop_change_handler(root_attrs)
        field_name = (
            self._reactive_values.get("name") or self._derive_field_name()
        )
        hidden_attrs: dict[str, Any] = {
            **hidden_carrier_attrs(value_expr, initial=initial, ref="bzpad"),
        }
        if field_name:
            hidden_attrs["name"] = str(field_name)
        if disabled:
            hidden_attrs["disabled"] = True
        hidden_attrs.update(relocated)
        children: list[Node] = [
            pad,
            Element(tag="input", attrs=hidden_attrs, children=()),
        ]

        # ── La barre d'actions ───────────────────────────────────────
        # Le bouton EST un ``ui.button``, pas une imitation : c'est la
        # règle de dogfooding du dépôt, et il apporte gratuitement le
        # focus ring, l'état disabled et l'échelle de tailles.
        clear_label = self._reactive_values.get("clear_label")
        if clear_label is None:
            clear_label = text("signature_pad.clear")
        if clear_label:
            children.append(
                Element(
                    tag="div",
                    attrs={"class": self.slot_class("actions")},
                    children=(
                        Component.render_detached(
                            Button(
                                clear_label,
                                variant="ghost",
                                size=size_cfg.get("button", "sm"),
                                color=self._reactive_values.get("color")
                                or "primary",
                                icon_left="eraser",
                                disabled=disabled,
                                on_click=self.clear(),
                            )
                        ),
                    ),
                )
            )

        # ── Assemblage ───────────────────────────────────────────────
        root_attrs["class"] = self.slot_class("root")
        root_attrs["bz-data"] = self._build_bz_data(
            scope_key=scope_key,
            has_local_value=value_binding is None,
            initial=initial,
            binding_path=binding_path,
            server_synced=self._value_server_backed("value"),
        )
        # Une méthode de scope n'a pas ``$refs`` — c'est ici, en contexte
        # de directive, qu'on capture le canvas dans le scope.
        root_attrs["bz-init"] = "_canvas = $refs.bzcanvas"
        root_attrs["bz-on:bz-clear"] = "clear()"

        return Element(
            tag=self._tag, attrs=root_attrs, children=tuple(children)
        )

    @staticmethod
    def _build_bz_data(
        *,
        scope_key: str,
        has_local_value: bool,
        initial: str,
        binding_path: str | None,
        server_synced: bool,
    ) -> str:
        """Le ``bz-data`` de l'instance : **des données, pas du code**.

        Le tracé (pointeur, redimensionnement, rendu, publication) vit
        une seule fois dans ``$bz.signaturePad.scope``.

        ``_canvas`` est déclaré ``null`` puis rempli par le ``bz-init``
        du root : une méthode de scope n'a pas accès à ``$refs``, seules
        les directives en ont (même contrainte et même remède que
        Slider, Carousel et Resizable).

        ``_strokes`` vit ICI plutôt que sur le nœud parce qu'il doit
        survivre au rescan sans survivre au canvas — un scope est
        réapparié par ``bz-id``, exactement comme la signature qu'il
        porte.
        """
        if has_local_value:
            sync = server_sync_marker(scope_key, enabled=server_synced)
            state = f"{scope_key}: {json.dumps(initial)},{sync} "
            target = f"this.{scope_key}"
        else:
            assert binding_path is not None
            state = ""
            target = binding_path

        return (
            "{...$bz.signaturePad.scope,"
            + state
            + "_canvas: null,"
            + "_strokes: [],"
            + "_drawing: null,"
            # La signature DÉJÀ LÀ, chargée une fois à l'hydratation et
            # peinte SOUS les traits neufs. Déclarée ici plutôt que
            # posée à la volée côté JS : un champ non déclaré devient un
            # signal à sa première écriture, donc l'assigner depuis le
            # ``onload`` de l'image réveillerait les effets du scope
            # pour rien.
            + "_base: null,"
            + f"_read() {{ return {target}; }},"
            + f"_write(v) {{ {target} = v; }}"
            + "}"
        )


__all__ = ["SignaturePad"]

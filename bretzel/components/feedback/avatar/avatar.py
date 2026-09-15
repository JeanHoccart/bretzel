"""``Avatar`` — round / square user image with initials fallback.

**``name=`` est la façon recommandée d'appeler ce composant** : il en
dérive les initiales ET l'``alt`` de l'image, donc l'appelant n'a rien
à oublier. ``ui.avatar(name="Jean Hoccart", src="/photo.png")`` rend
``<img alt="Jean Hoccart">`` ; sans ``src``, la pastille affiche ``JH``.

Trois modes de rendu :

- ``src=`` : une ``<img>`` couvre la pastille. Son ``alt`` vient de
  ``alt=`` s'il est donné, sinon de ``name=``. ⚠️ Ni l'un ni l'autre
  laisse ``alt=""``, qui déclare une image DÉCORATIVE — légitime à côté
  d'un nom déjà écrit en toutes lettres, silencieux et faux ailleurs.
- ``initials=`` ou ``name=`` (sans ``src``) : un carré teinté affiche
  les lettres dans la ``color`` choisie. ``initials=`` l'emporte quand
  les deux sont donnés.
- Aucun des trois : une pastille vide dans la couleur choisie.

Optional ``status=`` overlays a small dot in the bottom-right corner
(``online`` / ``offline`` / ``busy`` / ``away``).

``shape=`` picks ``circle`` (default) or ``square``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop, stamp_display_none
from bretzel.components.base._wiring import theme_context
from bretzel.components.feedback.avatar.theme import AVATAR_THEME
from bretzel.core.tree import Element, Node


def initials_of(name: str) -> str:
    """Les initiales d'un nom — ``"Jean Hoccart"`` → ``"JH"``.

    Première lettre du premier mot, première du DERNIER : c'est ce que
    les quatre exemples du dépôt recopiaient chacun de leur côté, à la
    lettre près. Un seul mot ne donne qu'une initiale, plutôt que ses
    deux premières lettres — ``"Jean"`` → ``"J"``, pas ``"JE"``.

    Rend ``""`` pour un nom vide ou blanc, et l'appelant décide : le
    composant n'affiche alors aucune pastille de lettres, ce qui est
    plus honnête qu'un ``"?"`` qui ressemble à une donnée.
    """
    parts = name.split()
    if not parts:
        return ""
    return (parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")).upper()


class Avatar(Component):
    """Round / square user chip with image or initials fallback."""

    THEME: ClassVar[dict[str, Any]] = AVATAR_THEME
    THEME_KEY: ClassVar[str] = "avatar"
    DEFAULT_TAG: ClassVar[str] = "span"
    IS_CONTAINER: ClassVar[bool] = False
    # Only ``status`` earns a client binding — presence flips live from a
    # client driver (SSE / polling) via ``bz-attr:class`` + ``bz-show``.
    # ``src`` / ``initials`` change only on a server re-render (new user
    # data → ``@refreshable``), so they stay design-time.
    # Cf. .claude/bretzel/client-reactive-surface.md.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("status",)

    src: str | None = reactive_prop(default=None, emit_attr=False, never_code=True)
    alt: str = reactive_prop(default="", emit_attr=False)
    #: Le nom de la personne. **La façon recommandée d'appeler ce
    #: composant** : il en dérive les initiales ET l'``alt`` de l'image.
    #:
    #: Le défaut que ça ferme : ``ui.avatar(src="/photo.png")`` émettait
    #: ``alt=""``, ce qui ne veut pas dire « pas d'alternative » mais
    #: **« image décorative, ignore-moi »** — la photo d'un utilisateur
    #: devenait invisible au lecteur d'écran, en silence. ``ui.image``
    #: exige son ``alt`` pour exactement cette raison, mais l'exiger ici
    #: casserait tous les appels existants.
    #:
    #: Dériver plutôt qu'exiger est la voie qu'``ui.file_upload`` emprunte
    #: déjà (sa vignette porte le nom du fichier) : l'appelant n'a rien à
    #: savoir, donc rien à oublier. Et les call-sites y gagnent — ils
    #: calculaient tous leurs initiales à la main.
    name: str | None = reactive_prop(default=None, emit_attr=False)
    initials: str | None = reactive_prop(default=None, emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    shape: str = reactive_prop(default="circle", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    status: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        src: str | None = None,
        alt: str | None = None,
        name: str | None = None,
        initials: str | None = None,
        size: str | None = None,
        shape: str | None = None,
        color: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None (garde le defaut).
        super().__init__(
            src=src, alt=alt, name=name, initials=initials,
            size=size, shape=shape, color=color,
            status=status,
            **kwargs,
        )

    def render(self) -> Element:
        theme, slots, sizes, size_key, _color = theme_context(self)
        shapes = theme.get("shapes", {})
        statuses = theme.get("statuses", {})

        shape = self._reactive_values.get("shape") or "circle"
        src = self._reactive_values.get("src")
        nom = self._reactive_values.get("name")
        # ``alt`` explicite > nom > vide. Le vide reste possible et il est
        # LICITE : un avatar purement decoratif a cote d'un nom deja ecrit
        # en toutes lettres ne doit pas etre annonce deux fois.
        alt = self._reactive_values.get("alt") or (str(nom) if nom else "")
        # Idem pour les initiales : explicites > derivees du nom.
        initials = self._reactive_values.get("initials") or (
            initials_of(str(nom)) or None if nom else None
        )
        status = self._reactive_values.get("status")
        size_map = sizes.get(size_key, sizes.get("md", {}))

        children: list[Node] = []

        if src:
            # Image carries rounded-{shape} so IT clips itself : the root
            # has no ``overflow-hidden`` (see theme) so the status dot's
            # ring can extend outside the box.
            image_class = " ".join(
                p
                for p in (
                    slots.get("image", ""),
                    shapes.get(shape, shapes.get("circle", "")),
                )
                if p
            )
            img_attrs: dict[str, Any] = {
                "src": src,
                "alt": alt,
                "class": image_class,
                # ``loading="lazy"`` saves bandwidth in avatar lists
                # (table rows, contributor strips).
                "loading": "lazy",
                # ``src`` n'est pas bindable : l'``<img>`` reflète son
                # attribut ``src`` statique, aucun carrier à câbler.
            }
            children.append(
                Element(tag="img", attrs=img_attrs, children=())
            )
        else:
            # ``initials`` est design-time : ``BINDABLE_PROPS = ("status",)``,
            # donc le socle LÈVE sur une ClientBinding avant d'arriver ici.
            # La branche ``_binding_metadata.get("initials")`` qui vivait
            # ici était inatteignable — retirée le 2026-08-01. Si la
            # réactivité des initiales devient un besoin, il faut d'abord
            # ajouter la prop à ``BINDABLE_PROPS``.
            # Troncature à 3 caractères : un avatar est dimensionné pour
            # 1-3 lettres par convention.
            if isinstance(initials, str) and len(initials) > 3:
                initials = initials[:3]
            initials_node = self.emit_text_slot(initials)
            if initials_node is not None:
                children.append(
                    Element(
                        tag="span",
                        attrs={"class": slots.get("initials", "")},
                        children=(initials_node,),
                    )
                )

        # Status dot — overlaid bottom-right. Two paths :
        # 1. literal string → bake the bg-color class statically.
        # 2. ClientBinding → render unconditionally with reactive
        #    ``bz-attr:class`` + ``bz-show`` so the colour flips live.
        # The class = slot (positioning + ring) + colour entry (bg-…) +
        # per-size dimensions ; only the colour is reactive.
        status_binding = self._binding_metadata.get("status")
        status_base_class = " ".join(
            p
            for p in (
                slots.get("status", ""),
                size_map.get("status", ""),
            )
            if p
        )
        if status_binding is not None:
            # Reactive : ``bz-attr:class`` is the single writer that
            # rebuilds the class ; the static ``class`` carries the SSR
            # snapshot for first paint. FOUC : pre-stamp ``display:none``
            # when the SSR value resolves to no visible dot.
            path = status_binding.binding_path()
            color_lookup_js = (
                "{"
                + ", ".join(
                    f"'{name}': '{cls}'" for name, cls in statuses.items()
                )
                + "}"
            )
            ssr_color = statuses.get(status, "") if status else ""
            initial_visible = bool(status and status in statuses)
            status_attrs: dict[str, Any] = {
                "class": " ".join(
                    p for p in (status_base_class, ssr_color) if p
                ),
                "bz-attr:class": (
                    f"'{status_base_class} ' + "
                    f"(({color_lookup_js})[{path}] || '')"
                ),
                "bz-show": f"!!{path} && !!(({color_lookup_js})[{path}])",
                "bz-attr:aria-label": path,
                "role": "status",
            }
            if status:
                status_attrs["aria-label"] = status
            if not initial_visible:
                stamp_display_none(status_attrs)
            children.append(
                Element(
                    tag="span",
                    attrs=status_attrs,
                    children=(),
                )
            )
        elif status and status in statuses:
            status_class = " ".join(
                p
                for p in (
                    status_base_class,
                    statuses.get(status, ""),
                )
                if p
            )
            children.append(
                Element(
                    tag="span",
                    attrs={
                        "class": status_class,
                        "aria-label": status,
                        "role": "status",
                    },
                    children=(),
                )
            )

        attrs = self.emit_attrs()
        attrs["class"] = " ".join(
            p
            for p in (
                self.compose_class(
                    "root",
                    apply_variant_size_modifiers=False,
                ),
                shapes.get(shape, shapes.get("circle", "")),
                size_map.get("root", ""),
            )
            if p
        )
        return Element(tag=self._tag, attrs=attrs, children=tuple(children))

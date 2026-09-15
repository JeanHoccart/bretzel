"""``Link`` — anchor with three visual variants and a11y disabled state.

External links get ``target="_blank"`` + the ``rel="noopener noreferrer"``
safety pair. Disabled links suppress the ``href``, set ``aria-disabled``
and ``tabindex="-1"`` so keyboard users can't navigate.

The ``group`` class on the root carries ``group-hover:`` /
``group-focus-visible:`` reactivity to children (e.g. trailing chevrons
that should follow the link's state).
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.actions.link.theme import LINK_THEME
from bretzel.components.base import Component, reactive_prop
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding


class Link(Component):
    """Anchor element with semantic colour, three variants
    (``hover`` / ``underline`` / ``text``), and a11y-correct disabled
    state."""

    THEME: ClassVar[dict[str, Any]] = LINK_THEME
    THEME_KEY: ClassVar[str] = "link"
    DEFAULT_TAG: ClassVar[str] = "a"
    # with status (counter, dynamic string). href changes when the
    # target depends on state. variant/color are design-time.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("label", "href")

    variant: str = reactive_prop(default="hover", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    href: str | None = reactive_prop(default=None, never_code=True)

    def __init__(
        self,
        label: str | ClientBinding | None = None,
        *,
        href: str | ClientBinding | None = None,
        variant: str | None = None,
        color: str | None = None,
        external: bool = False,
        download: bool = False,
        disabled: bool = False,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive ``None``.
        # ``external`` / ``download`` / ``disabled`` sont des booléens
        # design-time → à part.
        super().__init__(href=href, variant=variant, color=color, **kwargs)
        # ``adopt_slot`` détache un Component passé en slot (sinon il rend
        # deux fois) ; string / ClientBinding traversent intacts. Cf.
        # traps.md § « Slot Component stocké sans adopt_slot ».
        self._label = Component.adopt_slot(label)
        self._external = external
        self._download = download
        self._disabled = disabled

    def render(self) -> Element:
        # ``compose_class`` reads slots + variant. On ajoute la couleur
        # du texte ici pour ne pas polluer les gabarits de variante — et
        # c'est le PALIER qu'on écrit, pas un nom de couleur : le pont
        # que le socle pose sur cette même racine dit lequel.
        cls_string = f'{self.compose_class("root")} text-(--bz-text)'.strip()

        attrs = self.emit_attrs()
        attrs["class"] = cls_string

        # External : open in a new tab + neuter the opener for security.
        if self._external:
            attrs.setdefault("target", "_blank")
            attrs.setdefault("rel", "noopener noreferrer")

        # ── Download : ce lien porte un FICHIER, pas une navigation ──
        #
        # ⚠️ ``hx-boost="false"`` n'est pas une option : la coque pose
        # ``hx-boost`` sur la page, donc htmx intercepte TOUT ``<a>``,
        # va chercher la cible en XHR et l'injecte dans le document.
        # Sur un CSV, ça ne télécharge rien et ça remplace la page par
        # du texte brut — sans erreur, sans requête échouée, rien à
        # voir côté serveur.
        #
        # Mesuré le 2026-09-02 sur `/meta` du playground, avant ce
        # correctif : ``resource_type: 'xhr'`` et l'URL passée à
        # ``/meta-demo.csv``. C'est le mécanisme que l'export du
        # datatable neutralisait déjà à la main (`datatable.py:745`) ;
        # ceci le rend disponible à tout le monde plutôt que de le
        # laisser se redécouvrir.
        #
        # L'attribut HTML ``download`` en plus : il dit au navigateur de
        # ne PAS afficher le fichier même s'il sait le rendre (un SVG,
        # un PDF), et il laisse le serveur nommer via
        # ``Content-Disposition``.
        if self._download:
            attrs.setdefault("hx-boost", "false")
            attrs.setdefault("download", True)

        # Disabled : suppress ``href`` so keyboard nav can't follow it, mark
        # ``aria-disabled`` (screen readers + the theme's ``aria-disabled:*``
        # CSS) and ``tabindex="-1"`` to skip it in keyboard order.
        if self._disabled:
            self.release_root_attr("href", attrs)
            attrs["aria-disabled"] = "true"
            attrs["tabindex"] = "-1"

        children = list(self._render_children())
        # Inline-text shortcut takes precedence over child nodes if the
        # user passed both — same as Button.label. ``emit_text_slot``
        # handles the static-vs-ClientBinding split (raw text node vs
        # ``<span bz-text="...">``).
        label_node = self.emit_text_slot(self._label)
        if label_node is not None:
            children = [label_node, *children]

        return Element(tag=self._tag, attrs=attrs, children=tuple(children))

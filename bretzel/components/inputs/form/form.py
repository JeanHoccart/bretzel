"""``Form`` — wraps children in a ``<form>`` tag with submit handling.

Used as a context manager ::

    with ui.form(on_submit=save_handler):
        ui.input(name="label", placeholder="…")
        ui.button("Save", type="submit")

The dispatcher (runtime/_src/05_dispatcher.js) walks up to the
nearest ``<form>`` ancestor on submit and ships the FormData
verbatim — every named child input shows up in
``current_context().form_data`` on the server.

**Un formulaire qui contient un fichier s'encode en multipart, tout seul.**
htmx ne construit un corps ``FormData`` que si le formulaire le lui dit
(``hx-encoding``) ; sinon il URL-encode, et un ``File`` n'y survit pas — il
part comme le NOM du fichier, ou rien. Le formulaire n'a pas de prop pour
le déclarer : il rend ses enfants avant de composer ses attributs, donc il
SAIT ce qu'il contient (:func:`contains_file_input`). Une prop aurait été
une deuxième façon de dire ce que l'arbre dit déjà — et une occasion de
l'oublier, ce qui rendait le mode formulaire de ``ui.file_upload``
entièrement muet (mesuré le 2026-08-19 sur l'écran Import du CRM).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.components.inputs.form.theme import FORM_THEME
from bretzel.core.tree import Element, Node

#: ``type=file`` dans du HTML BRUT, quelle que soit la façon de le citer.
#: C'est la seule branche qui lit du markup que le framework n'a pas
#: produit : y exiger des guillemets doubles serait supposer une
#: convention sur ce qu'on ne contrôle justement pas.
_RAW_FILE_INPUT = re.compile(r"""type\s*=\s*["']?file\b""", re.IGNORECASE)


def contains_file_input(nodes: tuple[Node, ...] | list[Node]) -> bool:
    """Y a-t-il un ``<input type="file">`` quelque part sous ces nœuds ?

    Extraite pour être testable seule : c'est elle qui décide de l'encodage
    du formulaire, et une descente qui raterait un niveau redonnerait
    silencieusement un formulaire URL-encodé.

    Les quatre formes de :class:`~bretzel.core.tree.Node` sont couvertes :
    ``Element`` (tag + attrs + enfants), ``Fragment`` (enfants sans
    enveloppe), ``Text`` (rien à voir) et ``Html`` — dont le contenu est du
    HTML brut que le framework n'a pas produit, donc inspecté à la chaîne.
    L'erreur y est ASYMÉTRIQUE et c'est ce qui décide : un faux positif
    encode un formulaire en multipart pour rien, un faux négatif perd un
    fichier en silence.
    """
    for node in nodes:
        attrs = getattr(node, "attrs", None) or {}
        if getattr(node, "tag", None) == "input" and attrs.get("type") == "file":
            return True
        raw = getattr(node, "html", None)
        if isinstance(raw, str) and _RAW_FILE_INPUT.search(raw):
            return True
        children = getattr(node, "children", None) or ()
        if children and contains_file_input(children):
            return True
    return False


class Form(Component):
    """HTML form wrapper. Children are added via ``with`` block."""

    THEME: ClassVar[dict[str, Any]] = FORM_THEME
    THEME_KEY: ClassVar[str] = "form"
    DEFAULT_TAG: ClassVar[str] = "form"
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("submit",)

    def __init__(
        self,
        *,
        on_submit: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(on_submit=on_submit, **kwargs)

    def render(self) -> Element:
        children_nodes = self._render_children()
        attrs = self.emit_attrs()
        cls_string = self.compose_class("root")
        if cls_string:
            attrs = {**attrs, "class": cls_string}
        # Opt out of the document-level ``hx-boost`` (shell.py) : a form's
        # submit must keep its native / explicit semantics, not get
        # AJAX-swapped into the page outlet.
        attrs.setdefault("hx-boost", "false")
        if contains_file_input(children_nodes):
            # ``hx-encoding`` est ce que lit htmx ; ``enctype`` est ce que
            # lit le navigateur si la soumission part nativement. Les deux
            # disent la même chose à deux lecteurs différents — ce n'est
            # pas la même mécanique écrite deux fois.
            attrs.setdefault("hx-encoding", "multipart/form-data")
            attrs.setdefault("enctype", "multipart/form-data")
        return Element(tag=self._tag, attrs=attrs, children=children_nodes)

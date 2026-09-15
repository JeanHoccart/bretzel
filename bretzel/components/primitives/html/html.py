"""``Html`` — la porte de sortie : injecter du balisage verbatim.

Le nœud d'échappement existait depuis le début —
:class:`bretzel.core.tree.Html`, dont le docstring dit qu'il est « the
only legitimate way to inject markup that the framework did not produce ».
Quatre composants s'en servent (``code``, ``markdown``, le SVG de
``draggable``, le SSR du calendrier). Il n'était simplement **pas ouvert
au code applicatif** : une app avec un embed tiers, du contenu CMS déjà
assaini ou un ``<iframe>`` de carte n'avait aucun chemin, sinon écrire un
composant.

Pourquoi ``ui.html`` et pas ``ui.raw_html`` : le nom rejoint la famille
des primitives de contenu — ``ui.text``, ``ui.markdown``, ``ui.code``,
toutes nommées d'après ce qu'elles affichent. Le nommer d'après son
risque en ferait la seule exception, et surtout un nom effrayant
n'avertit qu'une personne, une fois, au moment où elle l'écrit. Ce qui
avertit à chaque ajout, pour toujours, c'est la gate
``tests/consistency/test_ui_html_call_sites_are_listed.py``, qui fige
les appels du dépôt : en ajouter un la fait rougir.

⚠️ **C'est un puits à XSS.** Tout ce qui entre sort verbatim dans la
page. La règle est simple : le contenu doit être **soit un littéral que
tu as écrit**, soit une valeur passée par un assainisseur (bleach,
nh3, …) juste avant. Jamais une chaîne venue de l'utilisateur telle
quelle. Si tu hésites, c'est ``ui.markdown`` qu'il te faut : il échappe
le HTML embarqué et réécrit les URLs dangereuses.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reject_component,
)
from bretzel.components.primitives.html.theme import HTML_THEME
from bretzel.core.tree import Element, HtmlNode
from bretzel.state.scopes.client import ClientBinding


class Html(Component):
    """Injecte du HTML verbatim. Server-only, et jamais échappé."""

    THEME: ClassVar[dict[str, Any]] = HTML_THEME
    THEME_KEY: ClassVar[str] = "html"
    IS_CONTAINER: ClassVar[bool] = False
    # Aucune surface réactive, et ce n'est pas un oubli : une binding path
    # sur du HTML brut voudrait dire « le runtime écrit du balisage depuis
    # l'état client », donc un puits à XSS piloté par le client. Le
    # constructeur REJETTE, il ne dégrade pas silencieusement.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        text: str | None = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(text, ClientBinding):
            raise ComponentUsageError(
                "ui.html n'accepte pas de ClientBinding pour ``text=`` — "
                "faire écrire du balisage brut au runtime depuis l'état "
                "client est un puits à XSS piloté par le client, et le "
                "serveur ne peut plus rien garantir de ce qui atterrit dans "
                "la page. Pour du HTML qui change, garde la source dans un "
                "PageState et re-rends la zone (@refreshable + refresh) : le "
                "serveur reste l'auteur du balisage."
            )
        reject_component(
            text,
            owner="ui.html",
            prop="text",
            because=(
                "``text`` est une STRING de balisage. Un Component y "
                "serait stringifié en son repr Python et injecté tel quel."
            ),
            instead=(
                "Pour composer, mets les composants AUTOUR : "
                "``with ui.vstack(): ui.html(src) ; ui.badge(…)``."
            ),
        )
        super().__init__(**kwargs)
        self._text = "" if text is None else str(text)

    def render(self) -> Element:
        cls = self.compose_class("root", apply_variant_size_modifiers=False)
        attrs = self.emit_attrs()
        if cls:
            attrs = {**attrs, "class": cls}
        if not self._text:
            return Element(tag=self._tag, attrs=attrs, children=())
        # L'enveloppe existe pour que les kwargs universels (``classes``,
        # ``id``, ``attrs``, ``visible``, ``tooltip``) aient où atterrir —
        # même raison que chez ``markdown`` et ``code``. ``tag=`` la change
        # (``span`` en contexte inline) ; rien ne la supprime, et c'est
        # assumé : sans porteur, la moitié de l'API universelle tomberait
        # dans le vide sans le dire.
        return Element(
            tag=self._tag, attrs=attrs, children=(HtmlNode(self._text),)
        )

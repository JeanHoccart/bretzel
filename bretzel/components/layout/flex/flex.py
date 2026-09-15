"""``Flex`` — generic CSS-flex container (Archetype 2).

The component is intentionally light : it owns the *axis-agnostic* API
(direction / align / justify / gap / wrap / grow) ; the convenience subclasses
(:class:`VStack`, :class:`HStack`) bake one direction in and expose a
smaller surface for the most common cases.

``direction`` and ``gap`` are **graded** props, so they take the same
``{breakpoint: value}`` dict as :class:`Grid`'s ``cols`` ::

    ui.flex(direction={"base": "col", "md": "row"}, gap={"base": "sm", "md": "lg"})

which is THE canonical "side by side on desktop, stacked on mobile".
``align`` / ``justify`` / ``wrap`` stay scalar — they are not graded, and
a second way to express a binary choice would duplicate ``Screen``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import (
    Component,
    ComponentUsageError,
    reactive_prop,
    responsive_classes,
)
from bretzel.components.layout.flex.theme import FLEX_THEME
from bretzel.core.tree import Element

# Props whose value may be a ``{breakpoint: value}`` dict. Graded only :
# more than two useful steps. Cf. ``base/responsive.py``.
RESPONSIVE_PROPS = frozenset({"direction", "gap"})



class Flex(Component):
    """A flex container with the full Tailwind axis API exposed.

    Children are added via the ordinary ``with`` block ; layout props
    map 1-to-1 onto Tailwind utilities through the theme dict.
    """

    THEME: ClassVar[dict[str, Any]] = FLEX_THEME
    THEME_KEY: ClassVar[str] = "flex"
    # Inherited by VStack / HStack via MRO.
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    #: Prop → groupe de thème, pour les six props de la famille.
    #:
    #: Écrit une fois et LU par le rendu, plutôt que redit à chaque
    #: endroit qui en a besoin. Ce qui l'a rendu nécessaire : ``ui.pane``
    #: et ``ui.viewport`` ont chacun leur ``THEME``, auto-suffisant par
    #: convention du dépôt — donc un groupe oublié dans l'une des copies
    #: rend la chaîne vide, et la prop devient un kwarg MORT sur ce
    #: composant-là seulement. Aucune erreur, aucune trace : c'est
    #: exactement le mode d'échec dominant du dépôt.
    #:
    #: La gate ``test_a_flex_family_declares_every_table`` lit cette table
    #: et exige le groupe dans chaque thème de la famille, sauf si la prop
    #: est dans ``SEALED_PROPS`` (``ui.pane`` scelle ``wrap``).
    THEME_TABLES: ClassVar[dict[str, str]] = {
        "direction": "directions",
        "align": "alignments",
        "justify": "justifies",
        "gap": "gaps",
        "wrap": "wrap",
        "grow": "grows",
    }

    #: Les tables que ``RESPONSIVE_PROPS`` traverse — donc celles dont les
    #: classes peuvent ressortir préfixées (``md:flex-row``, ``md:gap-6``),
    #: ce que la safelist doit couvrir.
    #:
    #: DÉRIVÉE depuis le 2026-08-25. Elle était écrite à la main, avec pour
    #: raison que « la correspondance prop → table vit dans le tuple de
    #: ``_compose_classes``, qui n'est pas lisible depuis la safelist » —
    #: ce tuple n'existe plus, c'est ``THEME_TABLES``, et il est lisible.
    #: Trié pour que l'ordre ne dépende pas de celui d'un ``frozenset``.
    #: ⚠️ ``map`` et pas une génératrice : dans un CORPS DE CLASSE, une
    #: compréhension ouvre sa propre portée et n'y voit pas les noms de la
    #: classe — ``THEME_TABLES`` y lèverait un ``NameError``. Les arguments
    #: de ``map`` sont évalués dans la portée de la classe, eux.
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = tuple(
        sorted(map(THEME_TABLES.__getitem__, RESPONSIVE_PROPS))
    )
    #: La MEME liste, vue comme des noms de props — c'est elle que le
    #: socle lit pour refuser un dict de paliers ailleurs. Le module la
    #: possede (le rendu s'en sert ligne 308) ; la classe l'expose.
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = RESPONSIVE_PROPS

    # Pure layout cosmetic props — kept off the DOM via emit_attr=False.
    # ``direction`` / ``gap`` are ``Any`` because they also take a
    # breakpoint dict ; the scalar-only ones keep their narrow annotation.
    direction: Any = reactive_prop(default="row", emit_attr=False)
    align: str = reactive_prop(default="stretch", emit_attr=False)
    justify: str = reactive_prop(default="start", emit_attr=False)
    gap: Any = reactive_prop(default="md", emit_attr=False)
    wrap: bool = reactive_prop(default=False, emit_attr=False)
    #: Comment les enfants directs se partagent l'axe PRINCIPAL — la
    #: largeur dans une rangée, la hauteur dans une colonne. ``None`` par
    #: défaut, et c'est load-bearing : une pile qui ne demande rien
    #: n'émet aucune classe de plus.
    #:
    #: Le manque qu'elle ferme (finding [30]) : la racine de tous les
    #: contrôles porte ``w-full``, et c'est la bonne convention — un champ
    #: remplit sa colonne. Mais dans un ``wrap=True``, un item dont la
    #: base vaut 100 % ne peut **jamais** partager sa ligne, donc la barre
    #: devient une PILE. Mesuré en Chromium le 2026-08-25, deux champs
    #: dans 860 px : 860 px chacun et une barre de 148 px, contre 422 px
    #: chacun et 66 px avec ``grow="16rem"``. Trois apps portaient la
    #: même rustine à l'appel (``BAR_FIELD = "basis-64 grow"``).
    #:
    #: C'est le PARENT qui distribue, par le variant ``*:`` (« enfants
    #: directs ») : aucun des 99 composants n'a besoin de savoir qu'il est
    #: dedans, donc ça marche avec les 46 qui ne déclarent aucune largeur.
    #:
    #: ``*:`` et non la forme entre crochets qu'écrit ``ui.pane``
    #: (``[&>*]:shrink-0``) : les deux disent la même chose, mais celle-ci
    #: s'échappe dans le HTML (``[&amp;&gt;*]:``), donc 18 caractères sur
    #: le fil au lieu de 10 — et c'est un variant NOMMÉ de Tailwind, pas
    #: un variant arbitraire, donc le cas le plus simple pour le scanner.
    #: Le pane garde l'autre orthographe pour l'instant : elle est citée
    #: par une gate de doc et par trois bancs (cf. ``work/todo.md``).
    grow: Any = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        direction: str | dict | None = None,
        align: str | None = None,
        justify: str | None = None,
        gap: str | dict | None = None,
        wrap: bool | None = None,
        grow: bool | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive ``None``
        # (garde le défaut du descripteur). Cas load-bearing préservé :
        # VStack/HStack ne passent PAS ``direction`` → il arrive ``None``
        # ici → le socle le drope → leur défaut de CLASSE (``col`` / ``row``)
        # gagne, exactement ce que l'ancienne garde ``if direction is not
        # None`` protégeait.
        super().__init__(
            direction=direction,
            align=align,
            justify=justify,
            gap=gap,
            wrap=wrap,
            grow=grow,
            **kwargs,
        )
        # ``grow=`` est validé ICI, pas au rendu, et c'est mesurable : une
        # levée depuis ``_compose_classes`` remonte une pile sans AUCUNE
        # frame de l'appelant (``wrapped_render → render →
        # _compose_classes``), donc elle nomme les valeurs acceptées sans
        # dire lequel des N ``grow=`` de la page est fautif. Le socle le
        # dit noir sur blanc (``ComponentUsageError`` : *raised at
        # instantiation time*), 18 refus du catalogue le font, et
        # ``_reject_unknown_slot_keys`` résout le même problème de la même
        # façon — ``_resolved_theme()`` est lisible depuis ``__init__``.
        #
        # Après ``super()`` obligatoirement : c'est lui qui remplit
        # ``_reactive_values``. Même contrainte, même commentaire, que
        # ``Resizable.__init__`` pour son ``orientation``.
        resolved = self._reactive_values.get("grow")
        if resolved:
            # Résultat jeté : on ne veut que la levée. Le rendu refera la
            # recherche — un dict `.get`, et il ne peut plus échouer.
            self._grow_class(resolved, self._grow_table())

        # ⚠️ Les CINQ SŒURS de ``grow``, alignées le 2026-08-29.
        #
        # Elles faisaient ``table.get(value, "")`` : ``align="stretchy"``
        # rendait une classe VIDE, sans erreur, sans warning, avec un HTML
        # parfaitement valide. C'est le kwarg mort, le mode d'échec
        # dominant de ce dépôt — et ``grow`` refusait déjà, ce qui laissait
        # DEUX mécanismes pour une même classe d'erreur dans une seule
        # méthode (principe 4 du charter).
        #
        # Balayage préalable, 2026-08-29 : **2 366 passages littéraux** dans
        # `bretzel/`, `examples/` et `tests/`, et **2 valeurs hors table**,
        # les deux ``gap="2xs"`` d'``examples/playground/features/dnd.py``
        # — un palier qui n'a jamais existé, donc deux piles sans gouttière
        # depuis le premier jour. Corrigées dans le même commit. Le
        # changement de comportement ne casse rien d'autre.
        for prop in ("direction", "align", "justify", "gap"):
            value = self._reactive_values.get(prop)
            if value:
                self._table_class(prop, value, self._table_of(prop))

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        cls_string = self._compose_classes()
        attrs = self.emit_attrs()
        if cls_string:
            attrs = {**attrs, "class": cls_string}
        return Element(
            tag=self._tag,
            attrs=attrs,
            children=self._render_children(),
        )

    # ── Class composition ──────────────────────────────────────────────

    def _table_of(self, prop: str) -> dict[str, str]:
        """La table de thème de ``prop``, override utilisateur compris.

        Même raison que :meth:`_grow_table` : ``__init__`` valide et
        ``_compose_classes`` résout, et les deux doivent regarder
        exactement la même table — sinon un ``Theme(components=…)`` ferait
        passer la validation et rendre autre chose.
        """
        return self._resolved_theme().get(self.THEME_TABLES[prop], {})

    @staticmethod
    def _table_class(prop: str, value: Any, table: dict[str, str]) -> str:
        """La classe de ``prop``, ou une levée qui NOMME les valeurs.

        Un dict de points de rupture est validé palier par palier : c'est
        la VALEUR de chaque entrée qui doit être dans la table, pas la
        clé (qui est un nom de breakpoint, la responsabilité de
        ``responsive_classes``).
        """
        if isinstance(value, dict):
            for breakpoint_value in value.values():
                Flex._table_class(prop, breakpoint_value, table)
            return ""
        entry = table.get(value)
        if entry is None:
            accepted = ", ".join(repr(k) for k in table)
            raise ComponentUsageError(
                f"{prop}={value!r} n'est pas une valeur connue. Valeurs "
                f"acceptées : {accepted}.\n"
                f"  Sans ce refus, l'appel rendrait une classe VIDE — un "
                f"HTML valide, aucune erreur, et la propriété simplement "
                f"absente. Pour une valeur hors table, écris-la à l'appel "
                f"avec ``classes=``."
            )
        return entry

    def _grow_table(self) -> dict[str, str]:
        """La table ``grows`` de CE composant, override utilisateur compris.

        Une méthode et pas deux lectures : ``__init__`` valide et
        ``_compose_classes`` résout, et les deux doivent regarder
        exactement la même table — sinon un ``Theme(components=…)`` ferait
        passer la validation et rendre autre chose.
        """
        return self._resolved_theme().get(self.THEME_TABLES["grow"], {})

    @staticmethod
    def _grow_class(grow: Any, table: dict[str, str]) -> str:
        """La classe de ``grow=``, ou une levée qui NOMME les valeurs.

        Une valeur hors table rendrait la chaîne vide — donc un appel qui
        ne fait rien, avec un HTML valide et une barre qui reste empilée.
        C'est le mode d'échec dominant du dépôt (le kwarg mort), et il n'a
        aucune raison d'être reconduit sur une prop neuve.

        ``True`` est un alias de ``"equal"`` et pas une cinquième clé : la
        table serait sinon indexée par des types mêlés, et
        ``bretzel describe flex`` afficherait ``True`` au milieu de trois
        longueurs.
        """
        # Pas de refus du dict ici : le socle l'a fait a la
        # construction (``reject_stray_breakpoints``), et son
        # message nomme le composant en plus du prop.
        key = "equal" if grow is True else grow
        entry = table.get(key)
        if entry is None:
            accepted = ", ".join(repr(k) for k in table)
            raise ComponentUsageError(
                f"grow={key!r} n'est pas une base connue. Valeurs acceptées : "
                f"{accepted} (``grow=True`` vaut 'equal'). La table est fermée "
                f"pour que chaque classe soit ENTIÈRE, donc visible au "
                f"compilateur Tailwind de prod ; pour une autre base, écris-la "
                f"à l'appel avec classes=."
            )
        return entry

    def _compose_classes(self) -> str:
        """Six props, six groupes de thème (``THEME_TABLES``) — tous trop
        spécifiques à l'axe pour le chemin variant/size du socle. On tire
        le thème et les classes utilisateur par les helpers du socle, et
        on applique les recherches propres à Flex entre les deux.

        Quatre passent par la boucle. ``wrap`` est un booléen (son groupe
        est une chaîne, pas une table) et ``grow`` refuse une valeur hors
        table au lieu de rendre la chaîne vide : deux branches à part,
        pour deux raisons différentes.
        """
        theme = self._resolved_theme()
        parts: list[str] = []

        root = theme.get("slots", {}).get("root")
        if root:
            parts.append(root)

        for prop in ("direction", "align", "justify", "gap"):
            table_key = self.THEME_TABLES[prop]
            value = self._reactive_values.get(prop)
            if not value:
                continue
            table = theme.get(table_key, {})
            if prop in RESPONSIVE_PROPS:
                # ``_t=table`` binds this iteration's table — a bare closure
                # would read the loop variable after it moved on.
                entry = responsive_classes(value, lambda v, _t=table: _t.get(v, ""))
            else:
                # Pas de refus ici : le socle l'a deja fait a la
                # construction, avec le nom du composant en plus.
                entry = table.get(value, "")
            if entry:
                parts.append(entry)

        if self._reactive_values.get("wrap"):
            wrap_class = theme.get(self.THEME_TABLES["wrap"])
            if wrap_class:
                parts.append(wrap_class)

        grow = self._reactive_values.get("grow")
        if grow:
            # Ne peut plus lever : ``__init__`` a déjà refusé l'inconnu.
            parts.append(self._grow_class(grow, self._grow_table()))

        # Classes user posées par le wrap ``_apply_universal_modifiers`` sur
        # le vrai root — ne pas ré-append ici (doublon « X X », héritté par
        # VStack/HStack). Gardé par test_no_manual_user_class_append.py.

        return " ".join(p for p in parts if p).strip()

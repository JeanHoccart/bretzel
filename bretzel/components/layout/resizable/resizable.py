"""``Resizable`` — panneaux séparés par des poignées qu'on tire.

Usage ::

    with ui.resizable():
        with ui.resizable_panel(min_size=15):
            ui.sidebar_nav()
        with ui.resizable_panel():
            ui.datatable(...)

    # Les tailles vivent où l'app veut qu'elles vivent :
    class Layout(ClientState, persist="local"):
        split: list = field(default_factory=lambda: [25, 75])

    with ui.resizable(sizes=layout.split, orientation="vertical"):
        ...

**Un seul composant sous ce nom, et c'est le split pane.** L'autre
« resizable » de l'écosystème — une boîte à poignée de coin, librement
redimensionnée en pixels — n'est pas ici : le navigateur la fait
nativement avec ``resize: both``, donc un composant n'y ajouterait rien
qu'une API à maintenir (arbitrage 2026-08-13, cf. la roadmap).

**Chaque enfant direct EST un panneau**, comme chaque enfant direct d'un
:class:`Carousel` est une slide. ``ui.resizable_panel`` n'est pas un
péage : c'est l'opt-in qui permet d'en contraindre un par ``min_size``.
Un enfant nu reçoit la même boîte, avec un minimum de zéro — donc un
``@refreshable`` ou un ``ui.fragment`` composent sans cérémonie.

**Le partage vit dans ``sizes``, une liste de poids.** Un poids par
panneau, dans l'ordre du rendu ; le navigateur répartit au prorata, donc
``[1, 3]`` et ``[25, 75]`` donnent la même chose. La liste est
**normalisée à 100 des deux côtés** — et ce n'est pas cosmétique :
``min_size`` est en points de pourcentage, donc des poids bruts d'un
côté et des minimums en pourcents de l'autre figent la poignée sans rien
signaler. Les deux normalisations sont gatées l'une contre l'autre par
``tests/runtime_js/test_resizable_mirrors_python.py``.

**Il n'y a pas de ``default_size=`` sur le panneau**, et c'est un choix :
``sizes=`` sur le groupe dit déjà le partage initial, et deux façons de
l'énoncer se contrediraient dès qu'on écrit les deux (principe 4 du
charter). Le panneau porte des **CONTRAINTES**, pas une valeur —
``min_size``, ``max_size``, ``collapsible`` : un axe orthogonal, donc
aucun recouvrement.

**``gap=`` appartient au GROUPE**, et c'est le seul endroit possible.
Un padding posé sur un ancêtre atteint bien le groupe — mesuré le
2026-08-23 sur la coque du CRM, parent en ``p-8`` : le panneau commençait
à x=32, pas à 0. Mais aucun padding d'ancêtre ne peut créer d'espace **à
l'intérieur**, entre un panneau et la poignée ; seul le parent des
panneaux sait où elle est. L'échelle est celle de ``ui.flex`` /
``ui.hstack`` / ``ui.grid``, cran pour cran, et l'accord des tables est
gaté par ``test_a_flex_container_spaces_its_children``.

La gouttière est **transparente au geste** : la conversion pixel → poids
somme les largeurs de PANNEAUX (``totalPx``) et n'a jamais supposé
qu'elles remplissaient le conteneur. Mesuré : +100 px de souris donnent
+100 px de panneau, avec gouttière et sans.

**Persistance : rien à déclarer ici.** ``sizes`` accepte une
:class:`ClientBinding`, donc un ``ClientState(persist="local")`` fait
survivre le partage au F5 sans un prop de plus. Et il n'y a **pas de
flash** à corriger : la racine porte un ``bz-data``, donc elle reste
``visibility:hidden`` jusqu'à ``html.bz-ready`` (``render/shell.py``
§ ``_ANTI_FLASH_STYLE``), et le boot du runtime hydrate le store depuis
localStorage AVANT le scan qui pose les tailles — mesuré dans
``00_index.js`` (register → scan → ``.bz-ready``). Un script pré-paint
comme celui de ``ColorScheme`` serait un second mécanisme pour un
problème que le premier résout déjà.

**Le geste** est du Pointer Events avec capture, comme :class:`Slider` —
famille *pointer-drag*, pas node-DnD (la roadmap insiste : les deux se
confondent et ça coûte cher). Il ne redistribue que la PAIRE encadrant la
poignée tirée, donc les autres panneaux ne bougent pas. Le clavier fait
le même travail par pas de 2 points (motif ARIA *window splitter*) : une
poignée qui n'obéit qu'au pointeur est inutilisable sans souris.

Rien n'est publié pendant le geste — seulement au relâchement. Publier
chaque frame enverrait un ``change`` par pixel au serveur et écrirait
localStorage cent fois par seconde.

**Replier un panneau** : ``ui.resizable_panel(collapsible=True)``, puis
double-clic sur la poignée — ou ``Entrée`` quand elle a le focus, parce
qu'un geste souris sans jumeau clavier n'existe pas pour la moitié des
gens. Le repli **passe outre ``min_size``** : le minimum dit « ne me
réduis pas en tirant », le repli dit « range-le ». Sans cette sortie, un
minimum rendrait le repli impossible et il faudrait un second
vocabulaire pour la même intention. Re-jouer le geste restaure la taille
d'avant.

C'est déclaratif et non impératif, contrairement aux overlays : replier
revient à écrire ``sizes``, donc ça passe par le canal qui porte déjà la
valeur. Un ``.collapse()`` aurait été une seconde façon de changer la
même chose (principe 4).

Imperative API : ``.set([30, 70])`` / ``.reset()`` (retour au partage
égal).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from bretzel.components.base import Component, reactive_prop
from bretzel.components.base._wiring import (
    hidden_carrier_attrs,
    pop_change_handler,
    server_sync_marker,
    unwrap_transparent,
)
from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.responsive import responsive_classes
from bretzel.components.layout.resizable.theme import (
    RESIZABLE_PANEL_THEME,
    RESIZABLE_THEME,
)
from bretzel.core.tree import Element, Node
from bretzel.render import text

#: Les deux axes d'un groupe. ``horizontal`` = panneaux côte à côte.
ORIENTATIONS: tuple[str, ...] = ("horizontal", "vertical")


def normalize_weights(raw: Any, count: int) -> list[float]:
    """``sizes`` brut → ``count`` pourcentages qui somment à 100.

    ⚠️ **Le miroir de ``_weights()`` dans ``_src/20_resizable.js``**, et
    les deux doivent s'accorder : le serveur pose les styles du premier
    paint, le runtime les repose à chaque tick. Une divergence se
    verrait comme un saut de mise en page à l'hydratation, sans qu'aucun
    test de rendu n'échoue.

    Une liste de la MAUVAISE longueur ne lève pas, elle est complétée à
    parts égales. C'est délibéré : quand les panneaux viennent des
    données (``for x in items:``), leur nombre change sans que la valeur
    persistée dans localStorage l'ait su — lever ferait planter la page
    sur un état vieux de trois jours.

    Une entrée absurde (négative, ``None``, non numérique) tombe elle
    aussi à part égale, panneau par panneau : c'est ce qui garantit
    qu'un panneau ne DISPARAÎT jamais à cause d'une valeur cassée.
    """
    if count <= 0:
        return []
    share = 100.0 / count
    # Le test de forme est hissé HORS de la boucle : il ne dépend pas de
    # l'index, et une chaîne est une ``Sequence`` — d'où l'exclusion
    # explicite, sans quoi ``sizes="50,50"`` se lirait caractère par
    # caractère au lieu d'être rejeté vers le repli.
    seq: Sequence[Any] = (
        raw
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
        else ()
    )
    values: list[float] = []
    for index in range(count):
        candidate: Any = seq[index] if index < len(seq) else None
        try:
            weight = float(candidate)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            weight = share
        values.append(weight if weight >= 0 else share)

    total = sum(values)
    if total <= 0:
        return [round(share, 2) for _ in range(count)]
    return [round(value * 100.0 / total, 2) for value in values]


def _num(value: float) -> str:
    """Un poids → sa forme la plus courte (``25`` et non ``25.0``).

    ``json.dumps`` rend ``25.0`` pour tout float entier, et ce ``.0``
    part dans le ``bz-data`` ET dans le ``style`` de CHAQUE panneau. Ce
    n'est pas faux — juste illisible dans l'inspecteur, là où on va
    justement lire ces valeurs quand quelque chose cloche.
    """
    return str(int(value)) if float(value).is_integer() else str(value)


def _num_list(values: Sequence[float]) -> str:
    """La liste JSON des poids, sans les ``.0``."""
    return "[" + ", ".join(_num(v) for v in values) + "]"


class ResizablePanel(Component):
    """Un panneau du groupe — conteneur, ouvert par ``with``.

    Il ne rend AUCUNE classe à lui : sa boîte (base nulle, plancher flex
    désactivé, débordement coupé) est composée par le groupe, seul à
    savoir sur quel axe il vit. Le composant existe pour marquer qu'un
    enfant est un panneau, et pour porter ses trois **contraintes** —
    ``min_size``, ``max_size``, ``collapsible``.

    Les trois sont en **points de pourcentage**, la même échelle que
    ``sizes`` sur le groupe. ``max_size`` a été ajouté le 2026-08-23 :
    ``min_size`` vivait seul, ce qui était une asymétrie et non une
    décision — un panneau de navigation qu'on veut borner à 40 % n'avait
    aucun moyen de le dire.

    ⚠️ **``collapsible`` PASSE OUTRE ``min_size``, et c'est le but.** Un
    panneau replié tombe à 0, donc sous son minimum. Le minimum dit « ne
    me réduis pas par accident en tirant » ; le repli est un geste
    explicite (double-clic sur la poignée, ou ``Entrée`` quand elle a le
    focus) qui dit « range-le ». Sans cette sortie, `min_size=20` rendrait
    le repli impossible et il faudrait un second vocabulaire pour dire la
    même chose. C'est le comportement de VS Code et de shadcn.

    Le repli se **souvient** de la taille d'avant : re-double-cliquer la
    restaure. Si le souvenir a été perdu (un morph a changé le nombre de
    panneaux), le panneau revient à son ``min_size``, ou à part égale.
    """

    THEME: ClassVar[dict[str, Any]] = RESIZABLE_PANEL_THEME
    THEME_KEY: ClassVar[str] = "resizable_panel"
    # ``min_size`` est une contrainte de conception : elle ne change
    # qu'au re-render serveur, donc aucun driver côté client (cf.
    # client-reactive-surface.md § La règle).
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()

    min_size: float = reactive_prop(default=0.0, emit_attr=False)
    #: ``100`` veut dire « aucun plafond » — la valeur neutre, pas une
    #: sentinelle : un panneau qui peut prendre 100 % n'est pas borné.
    max_size: float = reactive_prop(default=100.0, emit_attr=False)
    collapsible: bool = reactive_prop(default=False, emit_attr=False)

    def __init__(
        self,
        *,
        min_size: float | None = None,
        max_size: float | None = None,
        collapsible: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            min_size=min_size,
            max_size=max_size,
            collapsible=collapsible,
            **kwargs,
        )

    def render(self) -> Element:
        attrs = self.emit_attrs()
        return Element(
            tag=self._tag, attrs=attrs, children=tuple(self._render_children())
        )

    def _render_in_group(self, chrome: dict[str, Any]) -> Element:
        """Se rendre AVEC la boîte que le groupe lui impose.

        C'est le panneau qui compose son propre nœud, pas le groupe qui
        réécrit après coup celui qu'il vient de recevoir. Cinq
        précédents dans le dépôt (``Step._render_in_stepper``,
        ``StepPanel._render_panel``, ``Tab._render_button``,
        ``TabPanel._render_panel``, ``ToggleButton._render_button``) :
        le parent compose les classes, l'enfant construit l'Element.

        La chirurgie post-rendu qui était écrite ici avant portait un
        vrai défaut, pas seulement un défaut de goût : elle indexait une
        liste d'``id`` par le rang de boucle tout en ne l'alimentant que
        pour les enfants effectivement rendus, donc un enfant sauté
        décalait tous les ``aria-controls`` suivants.
        """
        attrs = self.emit_attrs()
        own_class = attrs.get("class")
        own_id = attrs.get("id")
        attrs.update(chrome)
        # Un ``id=`` explicite de l'appelant gagne sur celui que le
        # groupe propose : c'est SON identifiant, il l'a peut-être écrit
        # pour l'adresser d'ailleurs.
        if own_id:
            attrs["id"] = own_id
        # La classe du GROUPE d'abord, celle de l'utilisateur ensuite —
        # non pas parce que l'ordre de la chaîne déciderait quoi que ce
        # soit (Tailwind ordonne canoniquement dans la feuille, cf.
        # components.md), mais pour lire dans le sens où on l'écrit :
        # la boîte imposée, puis ce que l'appelant a ajouté.
        if own_class:
            attrs["class"] = f"{chrome['class']} {own_class}"
        return Element(
            tag=self._tag, attrs=attrs, children=tuple(self._render_children())
        )


class Resizable(Component):
    """Groupe de panneaux redimensionnables par des poignées dérivées."""

    THEME: ClassVar[dict[str, Any]] = RESIZABLE_THEME
    THEME_KEY: ClassVar[str] = "resizable"
    #: La seule prop graduée du groupe, et la table qu'elle traverse —
    #: donc la seule dont les classes peuvent ressortir en ``md:gap-6``.
    #: Écrit et non déduit : la correspondance prop → table est ce que la
    #: safelist de prod doit connaître.
    RESPONSIVE_PROPS: ClassVar[frozenset[str]] = frozenset({"gap"})
    RESPONSIVE_THEME_KEYS: ClassVar[tuple[str, ...]] = ("gaps",)
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("sizes",)
    IMPERATIVE: ClassVar[tuple[str, ...]] = ("set", "reset")
    EVENTS: ClassVar[tuple[str, ...]] = ("change",)

    sizes: Any = reactive_prop(
        default=None,
        emit_attr=False,
        writes=True,
        names_field=True,
    )
    orientation: str = reactive_prop(default="horizontal", emit_attr=False)
    disabled: bool = reactive_prop(default=False, emit_attr=False)
    #: ``Any`` et non ``str`` : comme chez :class:`~bretzel.components.layout.flex.Flex`,
    #: la valeur accepte un dict de points de rupture
    #: (``gap={"base": "sm", "md": "lg"}``). Un ``gap`` qui ressemblerait
    #: aux autres sans en avoir la forme graduée serait un citoyen de
    #: seconde zone — exactement l'incohérence que la prop supprime.
    gap: Any = reactive_prop(default="none", emit_attr=False)
    size: str = reactive_prop(default="md", emit_attr=False)
    color: str = reactive_prop(default="primary", emit_attr=False)
    name: str | None = reactive_prop(default=None, emit_attr=False)

    def __init__(
        self,
        *,
        sizes: Any = None,
        orientation: str | None = None,
        gap: str | dict | None = None,
        disabled: bool | None = None,
        size: str | None = None,
        color: str | None = None,
        name: str | None = None,
        on_change: Callable[..., Any] | str | None = None,
        **kwargs: Any,
    ) -> None:
        # Forward direct : le socle drope les kwargs reactive None.
        super().__init__(
            sizes=sizes,
            orientation=orientation,
            gap=gap,
            disabled=disabled,
            size=size,
            color=color,
            name=name,
            on_change=on_change,
            **kwargs,
        )
        # ⚠️ APRÈS ``super()``, jamais avant. Tester ``orientation not in
        # ORIENTATIONS`` sur le kwarg BRUT évalue un ``ClientBinding`` en
        # contexte booléen si l'appelant en passe un — et ça lève une
        # ``ReactivityError`` sur la réactivité au lieu du
        # ``ComponentUsageError`` « prop non bindable » que le contrat
        # universel promet. Le socle fait ce contrôle-là ; on lit ensuite
        # la valeur qu'il a résolue, qui est forcément un littéral.
        resolved = self._reactive_values.get("orientation")
        if resolved not in ORIENTATIONS:
            raise ComponentUsageError(
                f"ui.resizable(orientation={resolved!r}) — attendu "
                f"{' ou '.join(repr(o) for o in ORIENTATIONS)}."
            )

    # ── API impérative ─────────────────────────────────────────────────

    def set(self, sizes: Sequence[float]) -> str:
        """Imposer un partage. Write-through binding s'il y en a une."""
        return self._value_command(
            [float(w) for w in sizes], prop="sizes", event="bz-set"
        )

    def reset(self) -> str:
        """Revenir au partage égal.

        Toujours le dispatch, binding ou pas : la part égale dépend du
        NOMBRE de panneaux vivants, que le serveur ne connaît plus après
        un morph qui en a ajouté (même raison que ``Carousel.next()``,
        dont la destination dépend de la géométrie du moment).
        """
        return self._dispatch_command("bz-reset")

    # ── Render ─────────────────────────────────────────────────────────

    def render(self) -> Element:
        theme = self._resolved_theme()
        size_table = theme.get("sizes", {})
        size_key = self._reactive_values.get("size") or "md"
        size_cfg = size_table.get(size_key, size_table.get("md", {}))
        orientation = self._reactive_values.get("orientation") or "horizontal"
        vertical = orientation == "vertical"
        axis = "v" if vertical else "h"
        disabled = bool(self._reactive_values.get("disabled"))

        # ── Binding de ``sizes`` ─────────────────────────────────────
        sizes_binding = self._binding_metadata.get("sizes")
        scope_key = self._scope_keys("sizes")[0]
        binding_path = (
            self.path_of(sizes_binding) if sizes_binding is not None else None
        )
        sizes_expr = binding_path or scope_key

        # ── Les panneaux ─────────────────────────────────────────────
        # **Chaque enfant direct EST un panneau**, comme chaque enfant
        # direct d'un Carousel est une slide. ``ui.resizable_panel`` n'est
        # pas un péage : c'est l'opt-in qui permet de donner un
        # ``min_size`` à l'un d'eux. Un enfant nu reçoit la même boîte,
        # avec un minimum de zéro.
        #
        # La version qui LEVAIT sur un enfant étranger a été retirée le
        # jour même, mesurée : elle rendait ``ui.resizable``
        # incompatible avec ``@refreshable`` et ``ui.fragment``, dont les
        # nœuds s'attachent au parent courant comme n'importe quel
        # composant. Le message d'erreur citait alors
        # ``_RefreshableSection``, une classe interne que l'appelant n'a
        # jamais tapée. Aucun autre conteneur du dépôt ne refuse ses
        # enfants (Tabs, Stepper, Accordion, ToggleGroup, Sidebar les
        # laissent tous passer) — et une fois la boîte posée par le
        # groupe, l'objection tombe d'elle-même : un enfant enveloppé
        # EST un ``basis-0``.
        # ``unwrap_transparent`` : un panneau ENVELOPPÉ — zone
        # ``@refreshable``, ``ui.fragment`` — n'est pas une instance de
        # ``ResizablePanel``, donc il perdait ses TROIS contraintes en
        # silence. Mesuré le 2026-08-23 : ``_mins`` passait de ``[25, 0]``
        # à ``[0, 0]``, et ``max_size`` / ``collapsible`` avec.
        unwrapped = [unwrap_transparent(c) for c in self._children]
        panels = [c for c, _ in unwrapped]
        rewraps = [r for _, r in unwrapped]
        weights = normalize_weights(
            self._reactive_values.get("sizes"), len(panels)
        )
        # Les trois contraintes, lues panneau par panneau. Un enfant nu
        # (pas un ``ResizablePanel``) reçoit les valeurs neutres : c'est
        # ce qui permet à un ``@refreshable`` ou un ``ui.fragment`` de
        # composer sans cérémonie, cf. la docstring du groupe.
        mins = [
            max(0.0, float(p._reactive_values.get("min_size") or 0.0))
            if isinstance(p, ResizablePanel)
            else 0.0
            for p in panels
        ]
        maxs = [
            min(100.0, float(p._reactive_values.get("max_size") or 100.0))
            if isinstance(p, ResizablePanel)
            else 100.0
            for p in panels
        ]
        foldable = [
            bool(p._reactive_values.get("collapsible"))
            if isinstance(p, ResizablePanel)
            else False
            for p in panels
        ]
        for index, (lo, hi) in enumerate(zip(mins, maxs, strict=True)):
            if lo > hi:
                raise ComponentUsageError(
                    f"ui.resizable_panel n°{index + 1} : min_size={lo} > "
                    f"max_size={hi}. Le panneau ne pourrait prendre aucune "
                    f"taille, et la poignée se figerait sans rien signaler."
                )

        # Les trois chaînes de classes sont composées UNE fois : rien
        # dans ``handle``/``grip`` ne dépend de l'index, et chaque
        # ``slot_class`` est une résolution de thème complète (contextvar
        # + substitution de palette). Composées dans la boucle, un groupe
        # à cinq panneaux en résolvait seize là où quatre suffisent —
        # c'est le même hoist que ``panel_class``, qui l'avait déjà.
        panel_class = self.slot_class("panel")
        handle_class = self.slot_class(
            "handle",
            self.slot_class(f"handle_{axis}"),
            self.slot_class(
                "handle_locked" if disabled else "handle_active"
            ),
            size_cfg.get(f"bar_{axis}", ""),
        )
        grip_class = self.slot_class("grip", size_cfg.get(f"grip_{axis}", ""))
        children: list[Node] = []

        for index, panel in enumerate(panels):
            # Le motif ARIA « window splitter » veut que la poignée
            # DÉSIGNE le panneau qu'elle redimensionne. Un panneau
            # n'émet d'``id`` que s'il en a besoin par ailleurs, donc le
            # groupe lui en propose un — dérivé du sien, donc stable
            # d'un rendu à l'autre et unique par construction. Un ``id=``
            # explicite de l'appelant gagne (``setdefault`` côté panneau).
            panel_id = f"{self.id}_panel_{index}"
            # LA boîte, composée une fois et servie aux deux chemins :
            # un ``resizable_panel`` la reçoit et se rend AVEC (il peut y
            # ajouter ses propres attributs), un enfant étranger est
            # ENVELOPPÉ dedans. Un seul dict, donc les deux chemins ne
            # peuvent pas diverger.
            chrome: dict[str, Any] = {
                "class": panel_class,
                "data-bz-rz-panel": "",
                "id": panel_id,
                # Le poids en style inline, dès le SSR : la mise en page
                # est juste au premier paint, avant que le runtime ne
                # reprenne la main. Une valeur continue ne peut pas
                # passer par une classe (aucune n'existerait dans le CSS
                # compilé — memory
                # ``project_assembled_tailwind_class_dev_only``).
                "style": f"flex-grow:{_num(weights[index])}",
            }
            if isinstance(panel, ResizablePanel):
                node = panel._render_in_group(chrome)
            else:
                node = Element(
                    tag="div",
                    attrs=chrome,
                    children=(self._render_one(panel),),
                )
            # La zone reprend son ``bz-id`` sur le nœud composé : sans ça
            # le panneau s'afficherait et ne se rafraîchirait jamais.
            node = rewraps[index](node)
            children.append(node)
            # L'``id`` est RELU sur le nœud rendu, pas supposé : un
            # panneau à qui l'appelant a passé ``id=`` garde le sien, et
            # ``aria-controls`` doit désigner celui qui existe. Le
            # déduire des deux côtés, c'est la paire qui se désaccorde.
            panel_id = str(node.attrs.get("id") or panel_id)

            if index < len(panels) - 1:
                children.append(
                    self._handle(
                        index=index,
                        handle_class=handle_class,
                        grip_class=grip_class,
                        disabled=disabled,
                        value=weights[index],
                        controls=panel_id,
                        vertical=vertical,
                        # La poignée range le panneau repliable qu'elle
                        # touche. Celui de GAUCHE gagne quand les deux le
                        # sont : c'est celui que son ``aria-controls``
                        # désigne déjà, donc le geste et l'annonce parlent
                        # du même panneau.
                        fold_target=(
                            index
                            if foldable[index]
                            else index + 1
                            if foldable[index + 1]
                            else None
                        ),
                    )
                )

        # ── Input caché — form data + source du ``change`` ───────────
        root_attrs = self.emit_attrs()
        relocated = pop_change_handler(root_attrs)
        # ``JSON.stringify`` et pas la liste nue : la valeur d'un input
        # est une chaîne, et c'est aussi ce que ``change_emit_effect``
        # compare pour décider qu'il y a eu changement (idiome
        # ``Accordion`` multiple).
        carrier_expr = f"JSON.stringify({sizes_expr} || [])"
        field_name = self._reactive_values.get("name") or self._derive_field_name()
        if field_name or relocated:
            hidden_attrs: dict[str, Any] = {
                **hidden_carrier_attrs(carrier_expr, initial=_num_list(weights)),
            }
            if field_name:
                hidden_attrs["name"] = str(field_name)
            hidden_attrs.update(relocated)
            children.append(Element(tag="input", attrs=hidden_attrs, children=()))

        # ── Assemblage ───────────────────────────────────────────────
        # La GOUTTIERE, entre chaque panneau et sa poignee. C'est un
        # ``gap`` flex ordinaire, donc le geste y est insensible : la math
        # du glissement somme les LARGEURS DE PANNEAUX (``totalPx``) et
        # n'a jamais suppose qu'elles remplissaient le conteneur. Mesure
        # du 2026-08-23 : +100 px de souris => +100 px de panneau, avec
        # gouttiere et sans, a l'unite pres.
        gap_table = theme.get("gaps", {})
        gap_class = responsive_classes(
            self._reactive_values.get("gap") or "none",
            lambda v, _t=gap_table: _t.get(v, ""),
        )
        root_attrs["class"] = self.slot_class(
            "root",
            self.slot_class("vertical" if vertical else "horizontal"),
            gap_class,
        )
        root_attrs["bz-data"] = self._build_bz_data(
            scope_key=scope_key,
            has_local_value=sizes_binding is None,
            weights=weights,
            mins=mins,
            maxs=maxs,
            foldable=foldable,
            binding_path=binding_path,
            server_synced=self._value_server_backed("sizes"),
            vertical=vertical,
        )
        # Une méthode de scope n'a pas ``$el`` — c'est ici, en contexte de
        # directive, qu'on capture le groupe dans le scope.
        root_attrs["bz-init"] = "_group = $el"
        root_attrs["bz-effect"] = "_apply()"
        root_attrs["bz-on:bz-set"] = "set($event.detail.value)"
        root_attrs["bz-on:bz-reset"] = "reset()"

        return Element(tag=self._tag, attrs=root_attrs, children=tuple(children))

    # ── Morceaux ───────────────────────────────────────────────────────

    @staticmethod
    def _handle(
        *,
        index: int,
        handle_class: str,
        grip_class: str,
        disabled: bool,
        value: float,
        controls: str,
        vertical: bool,
        fold_target: int | None,
    ) -> Element:
        """La poignée entre le panneau ``index`` et le suivant.

        Elle est DÉRIVÉE, jamais déclarée : il y en a exactement une de
        moins que de panneaux, donc la faire écrire à l'appelant
        n'ajouterait qu'une occasion de se tromper (même raisonnement que
        les contrôles du Carousel).

        Les deux chaînes de classes arrivent COMPOSÉES : rien dedans ne
        dépend de l'index, donc les recomposer ici referait N fois une
        résolution de thème identique.
        """
        attrs: dict[str, Any] = {
            "class": handle_class,
            "data-bz-rz-handle": "",
            # ``separator`` avec ``aria-valuenow`` = le motif ARIA
            # « window splitter ». L'orientation déclarée est celle de la
            # BARRE, donc l'INVERSE de celle du groupe : des panneaux
            # côte à côte sont séparés par une barre verticale. C'est la
            # confusion classique du motif, d'où la ligne.
            "role": "separator",
            "aria-orientation": "horizontal" if vertical else "vertical",
            "aria-valuemin": "0",
            "aria-valuemax": "100",
            "aria-valuenow": str(round(value)),
            "aria-label": text("resizable.resize_panel", n=index + 1),
        }
        # Toujours posé : le groupe garantit un ``id`` au panneau qui
        # précède, donc la branche « pas d'id » n'existe pas.
        attrs["aria-controls"] = controls
        if disabled:
            attrs["aria-disabled"] = "true"
        else:
            # Focusable : c'est ce qui rend le clavier possible, et le
            # clavier est la seule voie sans pointeur.
            attrs["tabindex"] = "0"
            attrs["bz-on:pointerdown"] = f"_start($event, {index})"
            attrs["bz-on:pointermove"] = "_move($event)"
            attrs["bz-on:pointerup"] = "_end($event)"
            attrs["bz-on:pointercancel"] = "_end($event)"
            # Le repli, s'il y a un panneau repliable de part et d'autre.
            # Double-clic ET ``Entrée`` : un geste souris qui n'a pas de
            # jumeau clavier n'existe pas pour la moitié des gens, et la
            # poignée est déjà focusable pour les flèches.
            #
            # La PAIRE voyage, pas seulement la cible : replier, c'est
            # donner sa place au voisin d'en face, et lequel c'est dépend
            # de quel côté de la poignée le panneau repliable se trouve.
            if fold_target is None:
                fold = "null"
            else:
                partner = index + 1 if fold_target == index else index
                fold = f"[{fold_target}, {partner}]"
                attrs["bz-on:dblclick"] = f"_fold({fold_target}, {partner})"
            attrs["bz-on:keydown"] = f"_key($event, {index}, {fold})"

        grip = Element(
            tag="div",
            attrs={"class": grip_class, "aria-hidden": "true"},
            children=(),
        )
        return Element(tag="div", attrs=attrs, children=(grip,))

    @staticmethod
    def _build_bz_data(
        *,
        scope_key: str,
        has_local_value: bool,
        weights: list[float],
        mins: list[float],
        maxs: list[float],
        foldable: list[bool],
        binding_path: str | None,
        server_synced: bool,
        vertical: bool,
    ) -> str:
        """Le ``bz-data`` de l'instance : **des données, pas du code**.

        Les méthodes (géométrie, geste, clavier, impératif) vivent une
        seule fois dans ``$bz.resizable.scope``.

        ``_group`` est déclaré ``null`` puis rempli par le ``bz-init`` du
        root : une méthode de scope n'a pas accès à ``$el``, seules les
        directives en ont (même contrainte et même remède que Slider et
        Carousel).

        ``_mins`` / ``_maxs`` / ``_foldable`` voyagent en donnée plutôt
        que d'être relus du DOM : ce sont des contraintes de conception,
        elles ne changent qu'au re-render, et les écrire sur chaque
        panneau obligerait le runtime à les reparser à chaque frame du
        geste.

        ``_folded`` part vide et vit côté client : c'est la mémoire de
        « quelle taille avait ce panneau avant qu'on le range ». Elle
        n'a pas de sens côté serveur, qui ne sait pas ce que
        l'utilisateur a replié il y a trois secondes.
        """
        if has_local_value:
            sync = server_sync_marker(scope_key, enabled=server_synced)
            state = f"{scope_key}: {_num_list(weights)},{sync} "
            target = f"this.{scope_key}"
        else:
            assert binding_path is not None
            state = ""
            target = binding_path

        return (
            "{...$bz.resizable.scope,"
            + state
            + f"_mins: {_num_list(mins)},"
            + f"_maxs: {_num_list(maxs)},"
            + f"_foldable: {json.dumps(foldable)},"
            + "_folded: {},"
            + f"_vertical: {json.dumps(vertical)},"
            + "_group: null,"
            + "_drag: null,"
            + f"_read() {{ return {target}; }},"
            + f"_write(v) {{ {target} = v; }}"
            + "}"
        )


__all__ = ["Resizable", "ResizablePanel", "normalize_weights"]

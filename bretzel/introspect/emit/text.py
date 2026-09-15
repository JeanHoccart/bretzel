"""L'émetteur texte — deux granularités, et c'est le point du design.

Une fiche complète × 104 composants ne tient pas en contexte et ne se lit
pas. D'où :

- :func:`render_index` — **une ligne par symbole**, toute la surface.
  C'est ce qui reste chargé en permanence : il répond à « est-ce que
  ``justify`` existe sur ``hstack`` ? », qui est la question dont la
  mauvaise réponse produit un contournement (``classes="justify-between"``).
- :func:`render_detail` — la fiche entière d'UN symbole, à la demande.

L'index bon marché toujours présent, le détail à une commande.
"""

from __future__ import annotations

from bretzel.introspect.components import RESERVED_KWARGS, describe_components
from bretzel.introspect.model import (
    SOURCE_REACTIVE_PROP,
    AlgebraOp,
    ComponentInfo,
    HelperInfo,
    MethodInfo,
    ModuleSection,
    ParamInfo,
    StateInfo,
    SymbolDetail,
)

_INDENT = " " * 4

#: Au-delà, une ligne de doc cesse de tenir sur une ligne d'index.
_DOC_CLIP = 62


def _names(params: tuple[ParamInfo, ...]) -> str:
    return " ".join(p.name for p in params)


def render_index() -> str:
    """Une ligne par symbole ``ui.*`` — plus une ligne de contrats quand
    le composant en porte."""
    catalogue = describe_components()
    components = [i for i in catalogue if isinstance(i, ComponentInfo)]
    helpers = [i for i in catalogue if isinstance(i, HelperInfo)]

    width = max((len(i.ui_name) for i in catalogue), default=0) + 3

    out: list[str] = [
        f"# Surface ui.* — {len(components)} composants, {len(helpers)} helpers",
        "",
        "Lu vivant depuis le code : cet index ne peut pas mentir sur ce qui existe.",
        "Lu à la demande depuis le code avec `bretzel describe`.",
        "",
        "Tout composant accepte EN PLUS ces kwargs universels, jamais répétés",
        f"ci-dessous : {', '.join(RESERVED_KWARGS)}.",
        "",
        "Un event `click` s'écrit `on_click=`. Un slot se passe par son nom.",
        "Detail complet d'une entree : `describe <nom>`.",
        "",
    ]

    for info in components:
        head = f"ui.{info.ui_name}".ljust(width)
        props = _names(tuple(p for p in info.params if not p.name.startswith("on_")))
        out.append(f"{head}{info.family:<12} <{info.tag}>  {props}")
        contracts: list[str] = []
        if info.handler_kwargs:
            contracts.append(" ".join(info.handler_kwargs))
        if info.named_slots:
            contracts.append("slots: " + " ".join(info.named_slots))
        if info.imperative:
            contracts.append("impératif: " + " ".join(info.imperative))
        if contracts:
            out.append(f"{' ' * width}{' · '.join(contracts)}")

    if helpers:
        out.extend(["", "## Helpers (pas des composants)", ""])
        for helper in helpers:
            head = f"ui.{helper.ui_name}".ljust(width)
            out.append(f"{head}{helper.kind:<18} {_names(helper.params)}")

    out.append(render_modules())
    out.append(render_kwarg_routing())
    out.append(render_bindable_matrix())
    return "\n".join(out)


def render_detail(info: ComponentInfo | HelperInfo) -> str:
    """La fiche complète d'un symbole."""
    if isinstance(info, HelperInfo):
        return _render_helper(info)
    return _render_component(info)


def _prologue(title: str, doc: str | None, params: tuple[ParamInfo, ...]) -> list[str]:
    """Le haut de fiche, commun aux composants et aux helpers.

    Les deux moitiés divergeaient d'une ligne vide finale — un oubli, pas
    une décision, et tout ce qui suivait dans la fiche composant supposait
    la ligne présente."""
    out = [title, ""]
    if doc:
        out.extend([doc, ""])
    if params:
        out.append("Paramètres")
        out.extend(_param_lines(params))
        out.append("")
    return out


def _row(label: str, values: tuple[str, ...], suffix: str = "") -> str:
    """Une ligne de contrat. L'alignement vit ICI et non dans quatre
    littéraux comptés à l'œil — renommer « Impératif » ne peut plus
    décaler la colonne en silence."""
    return f"{label:<12}" + (", ".join(values) + suffix if values else "—")


def _render_helper(info: HelperInfo) -> str:
    return "\n".join(
        _prologue(f"ui.{info.ui_name}   ({info.kind})", info.doc, info.params)
    ).rstrip()


def _render_component(info: ComponentInfo) -> str:
    shape = "conteneur" if info.is_container else "feuille"
    title = f"ui.{info.ui_name} → {info.class_name}   ({info.family}, <{info.tag}>, {shape})"
    out = _prologue(title, info.doc, info.params)

    audited = "" if info.bindable_audited else "   ⚠ non audité (BINDABLE_PROPS absent)"
    out.append(
        _row("Bindable", info.bindable, audited)
        if info.bindable
        else "Bindable    — (aucune prop ne se lie côté client)"
    )
    out.append(_row("Events", info.handler_kwargs))
    out.append(_row("Slots", info.named_slots))
    out.append(_row("Impératif", info.imperative))
    if info.autoname_from:
        out.append(_row("Autoname", (f"depuis {info.autoname_from}",)))
    out.extend(_theme_lines(info))

    out.extend(["", f"Kwargs universels acceptés : {', '.join(RESERVED_KWARGS)}"])
    return "\n".join(out)


def render_symbol(detail: SymbolDetail) -> str:
    """La fiche d'un symbole hors ``ui.*``.

    Même forme que la fiche composant — titre, docstring, paramètres,
    puis les contrats en lignes ``label / valeurs`` — pour qu'un lecteur
    qui a vu l'une sache lire l'autre. Ce qui change est ce que la nature
    du symbole permet de dire : une constante n'a qu'une valeur, une
    classe a des méthodes, ``ClientBinding`` a son algèbre.
    """
    title = f"{detail.name} → {detail.module}   ({detail.kind}, {detail.category})"
    out = _prologue(title, detail.doc, detail.signature.params if detail.signature else ())

    if detail.value_repr is not None:
        out.append(_row("Valeur", (detail.value_repr,)))
    if detail.state is not None:
        out.append(_row("Portée", (detail.state.scope,)))
        out.extend(_state_url_lines(detail.state))
        out.extend(_state_field_lines(detail.state))
    if len(detail.exported_by) > 1:
        others = tuple(m for m in detail.exported_by if m != detail.module)
        out.append(_row("Aussi dans", others, "   (le même objet, ré-exporté)"))
    if detail.also_known_as:
        out.append(_row("Homonyme", detail.also_known_as, "   (une AUTRE chose)"))

    out.extend(_method_lines(detail.methods))
    out.extend(_algebra_lines(detail.algebra))
    return "\n".join(out).rstrip()


def _state_url_lines(state: StateInfo) -> list[str]:
    """Ce que l'état publie dans l'ADRESSE, et sous quel nom.

    La question qu'aucune fiche ne savait répondre. Un lecteur qui écrit
    ``class Issues(DatatableState, addressable=True)`` ne peut pas
    deviner ``?tri=&sens=&p=`` : les noms sont écrits sur les champs du
    PARENT, un fichier qu'il n'a aucune raison d'ouvrir. Mesuré le
    2026-09-06 — la question a été posée, et la réponse a demandé de
    lire ``state/datatable/state.py``.

    Trois états, et les distinguer EST l'information :

    - publié — la ligne nomme les paramètres, et dit que le reste ne
      part pas (c'est la garantie qui tient ``filters`` hors de l'URL) ;
    - nommé mais **éteint** — il ne manque qu'``addressable=True``, ce
      qu'aucune autre lecture ne dirait ;
    - rien du tout — le défaut de tout le framework, où on n'écrit pas
      de ligne plutôt qu'un « Adressable — » qui se lirait comme une
      lecture ratée.
    """
    if state.url_error:
        return [_row("Adressable", (f"⚠ déclaration refusée — {state.url_error}",))]
    if state.url_params:
        return [_row(
            "Adressable",
            tuple(f"{champ}→{param}" for champ, param in state.url_params),
            "   (un champ absent de cette ligne ne part JAMAIS dans l'URL)",
        )]
    if state.url_named:
        nommes = ", ".join(f"{champ}→{param}" for champ, param in state.url_named)
        return [_row(
            "Adressable",
            ("— éteint",),
            f"   (`addressable=True` publierait {nommes})",
        )]
    return []


def _state_field_lines(state: StateInfo) -> list[str]:
    """Les champs d'une classe d'état.

    Les cinq classes de BASE n'en ont aucun, et c'est l'attendu — leur
    fiche s'arrête à la portée. Ne rien écrire dans ce cas plutôt qu'un
    « Champs — » qui se lirait comme une lecture ratée."""
    if not state.fields:
        return []
    out = ["Champs"]
    out.extend(
        _param_lines(
            tuple(
                ParamInfo(
                    name=f.name,
                    kind="keyword-only",
                    type_label=f.type_label,
                    default_label=f.default_label,
                )
                for f in state.fields
            )
        )
    )
    if state.computed:
        out.append(_row("Computed", state.computed))
    return out


def _method_lines(methods: tuple[MethodInfo, ...]) -> list[str]:
    """Les méthodes publiques, une par ligne, avec leur signature.

    Le nom seul ne suffit pas : ``Language.set`` et ``auth.login`` se
    lisent à leurs arguments, et c'est précisément ce qu'aucune ligne
    d'index ne pouvait porter."""
    if not methods:
        return []
    out = ["", "Méthodes"]
    width = max(len(m.name) for m in methods) + 2
    for method in methods:
        call = f"{method.name}({_names(method.params)})"
        out.append(f"{_INDENT}{call:<{width + 14}}-> {method.returns_label}")
        if method.doc:
            out.append(f"{_INDENT}{_INDENT}{method.doc.splitlines()[0]}")
    return out


def _algebra_lines(ops: tuple[AlgebraOp, ...]) -> list[str]:
    """L'algèbre Python→JS, groupée par catégorie.

    Le JS montré est **capturé à l'exécution** par la sonde
    d':mod:`~bretzel.introspect.algebra`, pas recopié : ce qui s'affiche
    est ce que le composant émettra."""
    if not ops:
        return []
    out = ["", "Algèbre Python → JS (le JS est capturé à l'exécution)"]
    current = ""
    width = max(len(op.python) for op in ops) + 3
    for op in ops:
        if op.category != current:
            current = op.category
            out.append(f"  {current}")
        out.append(f"{_INDENT}{op.python:<{width}}{op.js or '—'}")
    return out


def _theme_lines(info: ComponentInfo) -> list[str]:
    """Le vocabulaire de thème — une ligne par groupe.

    Les VALEURS ne sont pas montrées : 70 855 caractères de classes
    Tailwind sur l'ensemble du catalogue, que le code dit déjà mieux. Ce
    qu'on ne pouvait lire nulle part, c'est la liste des noms qu'on a le
    droit d'écrire dans ``Theme(components=…)``.

    La clé est rappelée quand elle diffère du nom ``ui.*`` : trois
    composants écrivent sous le thème d'un AUTRE (``sidebar_section`` →
    ``sidebar``), et personne ne devine ça.
    """
    if not info.theme:
        return []
    head = "Thème"
    if info.theme_key and info.theme_key != info.ui_name:
        head = f"Thème (clé : {info.theme_key})"
    out = ["", f"{head} — Theme(components={{{info.theme_key!r}: {{…}}}})"]
    for group, keys in info.theme:
        out.append(f"  {group:<14}" + (", ".join(keys) if keys else "— (valeur unique)"))
    # Les clés de ``sizes`` ne sont PAS les valeurs de ``size=`` : sur 33
    # des 44 tables du catalogue elles nomment des SLOTS (``date_picker``
    # affiche ``input_field, clear_button…``), et lire la ligne brute fait
    # écrire ``size="input_field"``. C'est l'erreur exacte qu'une première
    # version de la règle ``valeur-hors-table`` a commise en la lisant.
    # La ligne résolue coupe court, et elle porte aussi les échelles
    # étendues (``heading`` jusqu'à ``8xl``, ``avatar`` jusqu'à ``2xl``).
    if info.size_values and tuple(info.size_values) != tuple(dict(info.theme).get("sizes", ())):
        out.append(f"  {'size= vaut':<14}" + ", ".join(info.size_values))
    return out


def _param_lines(params: tuple[ParamInfo, ...]) -> list[str]:
    """Les paramètres alignés. Une prop réactive est marquée : son absence
    de l'``__init__`` est une décision d'API, pas un accident, et le
    lecteur doit savoir qu'elle passe par ``**kwargs``."""
    if not params:
        return []
    name_w = max(len(p.name) for p in params) + 2
    type_w = max(len(p.type_label) for p in params) + 2
    return [
        f"{_INDENT}{p.name:<{name_w}}{p.type_label:<{type_w}}"
        f"{f'= {p.default_label}' if p.default_label else ''}"
        f"{'   (prop réactive)' if p.source == SOURCE_REACTIVE_PROP else ''}"
        for p in params
    ]


def render_module(section: ModuleSection) -> str:
    """Une section de module, groupée par besoin.

    Chaque symbole tient sur une ligne avec sa première ligne de
    docstring, tronquée : l'index répond à « qu'est-ce qui existe et à
    quoi ça sert », pas à « quelle est la signature exacte ».
    """
    out: list[str] = [f"## {section.name}", ""]
    if not section.covered:
        out.extend(["(section non couverte — aucun classement écrit)", ""])
        return "\n".join(out)

    current = ""
    width = max((len(s.name) for s in section.symbols), default=0) + 2
    for symbol in section.symbols:
        if symbol.category != current:
            current = symbol.category
            out.append(f"  {current}")
        doc = (symbol.summary or "").strip()
        if len(doc) > _DOC_CLIP:
            doc = doc[: _DOC_CLIP - 1].rstrip() + "…"
        out.append(f"    {symbol.name:<{width}}{symbol.kind:<11} {doc}")
    out.append("")
    return "\n".join(out)


def render_modules() -> str:
    """Toutes les sections de modules, dans l'ordre de lecture."""
    from bretzel.introspect.modules import describe_modules

    out = ["", "# Surface des modules", ""]
    out.extend(render_module(section) for section in describe_modules())
    return "\n".join(out).rstrip()


def render_kwarg_routing() -> str:
    """Le routage des kwargs, DÉRIVÉ des constantes du socle.

    Cette table était écrite à la main dans ``kwarg-routing.md`` et y a
    porté trois affirmations fausses simultanément. Générée, elle ne
    peut plus en porter aucune — c'est le seul remède qui a survécu à la
    mesure (trois candidats de gate sur la prose ont été écartés, cf.
    :mod:`bretzel.introspect.routing`).
    """
    from bretzel.introspect.routing import describe_kwarg_routing

    buckets = describe_kwarg_routing()
    width = max(len(b.name) for b in buckets) + 2
    out = [
        "",
        "# Routage des kwargs — les seaux de `split_kwargs`",
        "",
        "GÉNÉRÉ depuis les constantes du socle : cette table ne peut pas",
        "mentir sur ce que le framework accepte ou refuse.",
        "",
    ]
    for bucket in buckets:
        accepts = " ".join(bucket.accepts)
        if len(accepts) > 78:
            accepts = accepts[:77] + "…"
        out.append(f"{bucket.rank}. {bucket.name:<{width}} → {bucket.outcome}")
        out.append(f"{' ' * (width + 5)}{accepts}")
    return "\n".join(out)


def render_bindable_matrix() -> str:
    """La surface bindable de chaque composant, DÉRIVÉE.

    Cette matrice était écrite à la main dans ``kwarg-routing.md`` — 70
    lignes, un composant par ligne, avec le sens du binding noté ``⇄`` /
    ``→`` / ``∅``. ``test_bindable_surface`` la gardait indirectement : il
    rougit quand le code change, ce qui **force à mettre à jour le
    funnel** — il ne vérifie pas que la mise à jour a été faite juste.

    Dérivée, l'étape manuelle disparaît. ``⇄`` = le client écrit
    (``TWO_WAY_PROPS``), ``→`` = lecture seule, absent = statique.
    """
    from bretzel.introspect.components import describe_components
    from bretzel.introspect.model import ComponentInfo

    infos = [i for i in describe_components() if isinstance(i, ComponentInfo)]
    bindables = [i for i in infos if i.bindable]
    out = [
        "",
        f"# Surface bindable — {len(bindables)} composants sur {len(infos)}",
        "",
        "GÉNÉRÉ. `⇄` = le client ÉCRIT la valeur (`TWO_WAY_PROPS`), `→` = lecture",
        "seule. Un composant absent d'ici n'a AUCUNE prop bindable : tout binding",
        "y lève `ComponentUsageError`, ce n'est pas un oubli.",
        "",
    ]
    width = max((len(i.ui_name) for i in bindables), default=0) + 3
    for info in sorted(bindables, key=lambda i: (i.family, i.ui_name)):
        props = " ".join(f"{p}{'⇄' if p in info.two_way else '→'}" for p in info.bindable)
        audited = "" if info.bindable_audited else "   ⚠ non audité"
        out.append(f"ui.{info.ui_name:<{width}}{info.family:<12} {props}{audited}")
    return "\n".join(out)

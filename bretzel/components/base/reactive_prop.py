"""Reactive props — the bridge between component kwargs and runtime attrs.

A *reactive prop* is a class attribute on a :class:`Component` subclass
declared like ::

    class Button(Component):
        color: str = reactive_prop(default="primary")
        disabled: bool = reactive_prop(default=False)

The descriptor itself is mostly a marker : the real work happens at
:py:meth:`Component.__init__` time, where the metaclass walks the
class body and the constructor inspects the kwargs to decide which
storage path each value takes (cf. ``.claude/bretzel/components.md`` § *How
emit_attrs handles the 3 cases*) :

- **Python literal** (``True``, ``"primary"``, ``42``) → static HTML
  attribute, baked at render time.
- **ClientBinding** (``state.X`` from a ``ClientState``) → emitted as
  ``bz-attr:X="<binding-path>"`` ; the runtime binds it reactively.
  (The old ``bz-prop:`` prefix was split into ``BZ_MODEL_PREFIX`` +
  ``BZ_ATTR_PREFIX`` — cf. ``runtime/protocol.py``.)
- **client expression string** (``"$bz.state.X.y"``, ``"a <= 1"``, …) →
  emitted as a raw ``bz-attr:X="..."`` directive too.

This module owns the descriptor + factory + the heuristic that tells
"is this string a client expression or a literal?".
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Final


class _Missing:
    """Sentinel for "no default" — kept distinct from ``None`` which
    is itself a perfectly valid default value."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final[Any] = _Missing()


# ───────────────────────────────────────────────────────────────────────────
# Descriptor
# ───────────────────────────────────────────────────────────────────────────


class ReactivePropDescriptor:
    """Class-level descriptor for a reactive prop.

    Stores the default value at class build time ; the actual value
    lives in ``instance._reactive_values[name]`` after
    :py:meth:`Component.__init__` runs.

    Class-level access (``Button.color``) yields the descriptor itself
    so the metaclass / introspection code can read its config.
    Instance-level access (``my_btn.color``) yields the stored value.
    """

    __slots__ = (
        "declared_type",
        "default",
        "default_factory",
        "emit_attr",
        "name",
        "names_field",
        "never_code",
        "scope_keys",
        "steps",
        "writes",
    )

    def __init__(
        self,
        *,
        default: Any = MISSING,
        default_factory: Callable[[], Any] | None = None,
        emit_attr: bool = True,
        writes: bool = False,
        scope_keys: tuple[str, ...] | None = None,
        steps: tuple[str, ...] | None = None,
        names_field: bool = False,
        never_code: bool = False,
    ) -> None:
        if default is not MISSING and default_factory is not None:
            raise ValueError(
                "reactive_prop cannot specify both ``default`` and ``default_factory``."
            )
        if scope_keys is not None and len(scope_keys) < 2:
            # ⚠️ Une clé UNIQUE ne se déclare pas : le défaut est le nom
            # de la prop, donc ``scope_keys=("value",)`` est redondant et
            # ``scope_keys=("val",)`` est un SYNONYME. Le dépôt en portait
            # treize — ``val``, ``active``, ``current``, ``sel``,
            # ``expanded``, ``picked`` — soit huit orthographes pour la
            # même notion, et il sait ce qu'elles ont coûté : « c'est la
            # divergence de nommage (value/picked/active/sel) qui a causé
            # 5 des 8 oublis de ``_serverSync`` ».
            #
            # Ce qui reste légitime est la forme que le défaut ne peut PAS
            # exprimer : une valeur qui vit sous PLUSIEURS clés
            # (``Calendar.month`` → ``year`` + ``month``,
            # ``DateRangePicker.value`` → ``vstart`` + ``vend``). D'où le
            # seuil à deux — il ne mesure pas une quantité, il désigne la
            # seule raison d'exister du paramètre.
            #
            # Levée à la CRÉATION DE CLASSE, donc à l'import : ce n'est
            # pas un test qu'on peut oublier de lancer.
            raise ValueError(
                f"reactive_prop(scope_keys={scope_keys!r}) : une clé de "
                f"scope UNIQUE ne se déclare pas — elle vaut le nom de la "
                f"prop par défaut. Retire le paramètre et nomme la clé "
                f"comme la prop. ``scope_keys=`` n'existe que pour une "
                f"valeur qui vit sous PLUSIEURS clés (year+month, "
                f"vstart+vend)."
            )
        self.name: str = ""
        self.default = default
        self.default_factory = default_factory
        # When ``False``, the prop's value is consumed internally by
        # the component (typically to compose theme classes) but never
        # ends up as a raw HTML attribute. Use for purely-cosmetic
        # props like ``variant`` / ``size`` / ``color`` / ``weight``
        # that would otherwise pollute the DOM with framework noise.
        # Reactive bindings (ClientBinding / client expressions) are
        # still emitted as ``bz-attr:`` / ``bz-model`` because the
        # runtime has to track them.
        self.emit_attr = emit_attr
        # ``writes`` : le CLIENT écrit dans cette prop (value / checked /
        # open). Le chemin client sert de CIBLE D'ASSIGNATION dans le JS
        # émis → une ClientExpression y est refusée, et ``_serverSync``
        # s'émet en mode server-backed. La métaclasse en dérive le ClassVar
        # ``TWO_WAY_PROPS`` (co-localisé avec la prop plutôt que déclaré 30
        # lignes plus bas — c'est le ``reflect`` de Lit / ``bindings=`` de
        # Textual). Ce n'est PAS ``AUTONAME_FROM`` (« d'où vient mon name=
        # HTML »). Cf. ``Component._value_server_backed`` + todo.md § A3.
        self.writes = writes
        # ``scope_keys`` : sous quelle(s) clé(s) la valeur vit dans le
        # ``bz-data`` du composant. **Défaut : le nom de la prop**, et
        # c'est le cas de 31 des 33 props écrivantes. Les deux qui
        # déclarent sont celles que le défaut ne peut pas exprimer :
        # ``Calendar.month`` → ``("year", "month")``,
        # ``DateRangePicker.value`` → ``("vstart", "vend")``.
        #
        # ⚠️ Une clé UNIQUE est REFUSÉE (cf. ``__init__``). Le paramètre a
        # porté treize synonymes — ``val``, ``active``, ``current``,
        # ``sel``, ``expanded``, ``picked`` — soit huit orthographes pour
        # « la valeur choisie ». Le coût est constaté : « c'est la
        # divergence de nommage (value/picked/active/sel) qui a causé 5
        # des 8 oublis ``_serverSync`` ». La clé était en plus hardcodée
        # dans chaque ``server_sync_marker(...)`` — deux sources pour un
        # fait ; l'émission la lit désormais via
        # ``Component._scope_keys(prop)``.
        self.scope_keys = scope_keys
        # ``steps`` : les valeurs LÉGALES de cette prop, quand le thème
        # ne peut pas les dire. ``refuse_a_value_off_the_table`` lit
        # normalement la table ``sizes`` / ``variants`` ; quatre props du
        # catalogue lui échappaient et rendaient donc n'importe quoi en
        # silence (mesuré le 2026-09-06, puis le 2026-09-07) :
        #
        #   - ``bar_chart.variant`` / ``pie_chart.variant`` — leur valeur
        #     nomme un MODE DE TRACÉ, pas un palier de thème, donc il n'y
        #     a aucune table à lire. ``variant="zzz"`` rendait à
        #     l'identique du défaut ;
        #   - ``radio.size`` — la table existe mais son défaut vaut
        #     ``None`` (« hériter du groupe »), et c'est le défaut qui
        #     sert d'ancre pour savoir lequel des deux niveaux d'une
        #     table imbriquée porte les paliers. Sans ancre lisible, le
        #     refus s'abstenait, et ``size="zzz"`` rendait SANS taille ;
        #   - ``radio_group.size`` — le groupe n'a pas de table à lui, il
        #     transmet aux enfants.
        #
        # ⚠️ **Ne PAS retaper une liste que le thème porte déjà.** Trois
        # des quatre lisent leur propre table (``tuple(RADIO_THEME
        # ["sizes"])``) : c'est le même geste que ``scope_keys``, une
        # déclaration qui DÉSIGNE une source plutôt que d'en devenir une
        # seconde. Un ensemble recopié dériverait de la table le jour où
        # elle gagne un palier.
        self.steps = steps
        # ``names_field`` : c'est CETTE prop qui donne son ``name=`` HTML au
        # composant, donc le champ que la FormData portera. La métaclasse en
        # dérive le ClassVar ``AUTONAME_FROM``.
        #
        # Troisième fait co-localisé sur la prop, après ``writes`` et
        # ``scope_keys`` — et le dernier des trois à avoir migré (l'audit du
        # socle 2026-07-29 le classait « la dernière déclaration de style
        # pré-migration »). Il répond à une question DIFFÉRENTE de
        # ``writes`` : « d'où vient mon name= » contre « qu'est-ce que le
        # client écrit ». Les deux coïncident sur les 15 inputs de
        # formulaire mais divergent — 6 composants écrivent sans nommer (les
        # 5 overlays sur ``open``, ``FormField`` sur ``error``). Confondre
        # les deux est précisément ce qui avait couplé le server-sync au
        # form-naming.
        #
        # ⚠️ ``names_field=True`` implique ``writes=True`` : un champ de
        # formulaire dont le client n'écrirait pas la valeur n'a pas de
        # ``name=`` à dériver. La métaclasse le vérifie.
        self.names_field = names_field
        # ``never_code`` : la valeur de cette prop est une DONNÉE, jamais
        # du code client — donc ``looks_like_client_expr`` ne tourne pas
        # dessus. Quatrième fait co-localisé sur la prop, même patron que
        # ``writes`` / ``scope_keys`` / ``names_field``.
        #
        # Le cas qui l'a fait naître, et pourquoi c'est une DÉCLARATION et
        # pas un marqueur de plus dans l'heuristique : une prop qui porte
        # une URL (``href`` / ``src`` / ``poster``) reçoit régulièrement du
        # base64, dont le padding s'écrit ``=`` ou ``==``. Or ``==`` est un
        # marqueur fort. La valeur partait donc en ``bz-attr:href``, le
        # runtime tentait de compiler ``/_bretzel/datatable.csv?q=…`` comme
        # du JS — ``/…/`` est un littéral regex — et jetait « Invalid
        # regular expression flags ». Mesuré le 2026-08-26 : l'export CSV du
        # datatable perdait son ``href`` après toute recherche, selon que le
        # blob tombait ou non sur le padding.
        #
        # C'était la TROISIÈME occurrence de cette classe (``--w: 200px``,
        # la data-URI de ``signature_pad``, celle-ci), et les deux premières
        # avaient été réparées par une exclusion de FORME dans l'heuristique
        # — dont ``value.startswith("data:")``, retiré ici : il visait les
        # mêmes props, en devinant sur la valeur ce que la prop peut dire.
        # Une exclusion de forme ne ferme jamais que l'occurrence qu'elle a
        # vue ; la déclaration ferme la classe.
        #
        # L'échappatoire reste : ``**{"bz-attr:href": "…"}`` force
        # l'expression, comme sur n'importe quelle prop.
        self.never_code = never_code
        # Populated by ``_ComponentMeta.__new__`` once it can read the
        # owner class's ``__annotations__``. ``None`` means "unannotated"
        # — discipline checks fall back to permissive behaviour.
        self.declared_type: Any = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any | None, owner: type | None = None) -> Any:
        if instance is None:
            return self
        # Stored values live on a per-instance dict populated by the
        # Component constructor. Falling back to the descriptor's own
        # default keeps simple instantiations working before the
        # storage dict is wired (helps tests and class introspection).
        values = getattr(instance, "_reactive_values", None)
        if values is None:
            return self.resolve_default()
        return values.get(self.name, self.resolve_default())

    def resolve_default(self) -> Any:
        if self.default_factory is not None:
            return self.default_factory()
        if self.default is not MISSING:
            return self.default
        return None

    def has_default(self) -> bool:
        return self.default is not MISSING or self.default_factory is not None

    def __repr__(self) -> str:
        parts = [f"name={self.name!r}"]
        if self.default is not MISSING:
            parts.append(f"default={self.default!r}")
        if self.default_factory is not None:
            parts.append(f"default_factory={self.default_factory!r}")
        return f"reactive_prop({', '.join(parts)})"


# ───────────────────────────────────────────────────────────────────────────
# Public sugar
# ───────────────────────────────────────────────────────────────────────────


def reactive_prop(
    *,
    default: Any = MISSING,
    default_factory: Callable[[], Any] | None = None,
    emit_attr: bool = True,
    writes: bool = False,
    scope_keys: tuple[str, ...] | None = None,
    steps: tuple[str, ...] | None = None,
    names_field: bool = False,
    never_code: bool = False,
) -> Any:
    """Declare a reactive prop on a :class:`Component` subclass.

    Pass ``emit_attr=False`` for cosmetic props consumed only by the
    component's class composition (variant / size / color / weight …)
    so they don't leak into the DOM as raw attributes. Reactive
    bindings still flow through (``bz-attr:`` / ``bz-model`` directives) —
    the runtime needs them.

    Pass ``writes=True`` when the CLIENT writes into this prop (a
    value-holding input : ``value`` / ``checked`` / ``open``). The
    metaclass derives ``TWO_WAY_PROPS`` from these — no separate ClassVar
    to keep in sync. La clé de scope vaut alors le NOM DE LA PROP, et
    ``scope_keys=(...)`` ne se pose que pour une valeur qui vit sous
    PLUSIEURS clés (``Calendar.month`` → ``("year", "month")``,
    ``DateRangePicker.value`` → ``("vstart", "vend")``) — une clé unique
    est refusée à la création de classe. Cf.
    :class:`ReactivePropDescriptor`.

    Pass ``names_field=True`` sur la prop qui donne son ``name=`` HTML au
    composant — la métaclasse en dérive ``AUTONAME_FROM``. Implique
    ``writes=True`` (vérifié) : un champ de formulaire dont le client
    n'écrit pas la valeur n'a pas de ``name=`` à dériver.

    Pass ``never_code=True`` quand la valeur est une DONNÉE et jamais du
    code client — une URL (``href`` / ``src`` / ``poster``), typiquement.
    :func:`looks_like_client_expr` ne tourne alors pas dessus, ce qui la
    met hors d'atteinte de ses faux positifs : un padding base64 (``==``)
    dans une URL suffisait à la faire partir en ``bz-attr:``, et le runtime
    jetait alors une erreur de syntaxe au lieu de poser l'attribut. Cf.
    :class:`ReactivePropDescriptor`.

    Return type is ``Any`` so static checkers see the field's
    annotated type on the class (``color: str = reactive_prop(...)``
    type-checks as ``str``).
    """
    return ReactivePropDescriptor(
        default=default,
        default_factory=default_factory,
        emit_attr=emit_attr,
        writes=writes,
        scope_keys=scope_keys,
        steps=steps,
        names_field=names_field,
        never_code=never_code,
    )


# ───────────────────────────────────────────────────────────────────────────
# client-expression heuristic
# ───────────────────────────────────────────────────────────────────────────


# Conservative markers — every one of these is a *strong* signal that
# the string is JS code, not a value. We default to "literal" when in
# doubt so harmless strings like ``color="primary"`` never accidentally
# get evaluated as JS.
_CLIENT_EXPR_MARKERS: tuple[str, ...] = (
    "==", "!=", "===", "!==",
    "<=", ">=",
    "&&", "||",
    # NOTE : ``++`` / ``--`` removed mai 2026.
    # - ``--`` collides with EVERY CSS custom property name
    #   (``--w``, ``--bg-color``, ``--bz-overlay-z``) and is far
    #   more commonly typed as a value than as a JS decrement.
    #   Regression : a placeholder ``"--w: 200px"`` mistagged as
    #   the runtime emitted ``:placeholder="--w: 200px"`` → the runtime
    #   parse error → page crash.
    # - ``++`` shows up in prose too (``"C++ developer"``,
    #   ``"version 2++"``) and the JS decrement / increment forms
    #   always come WITH an identifier (``i++``, ``++count``)
    #   which is already caught by the function-call /
    #   member-access heuristics elsewhere.
    # A user who really wants to fire a JS ``i--`` expression as a
    # prop value forces it with ``attrs={"bz-attr:x": …}``. (Le
    # ``:attr`` d'antan était un préfixe Alpine inerte, et il LÈVE
    # depuis le 2026-07-30.)
    # Les magies du runtime V3. ``$store`` a été retiré le 2026-08-01 :
    # c'était une magie Alpine, absente de ``runtime/_src`` (les vraies
    # sont $bz / $dispatch / $el / $event / $refs / $root). Une entrée
    # d'allowlist qui n'exclut plus rien est la pathologie que l'audit
    # du socle a nommée.
    "$dispatch", "$bz.", "$el", "$refs", "$event", "$root",
)  # fmt: skip


# Ternary requires ``<expr> ? <a> : <b>`` ; we look for ``\s\?\s`` plus
# a colon later in the string. This is intentionally strict — a bare
# ``?`` in human text (``"What needs to be done ?"`` placeholder) used
# to be classified as a client expr and the value got emitted as ``:placeholder``,
# making the runtime try to evaluate the sentence as JS at runtime.
_TERNARY_RE = re.compile(r"\s\?\s.*:")
# Arrow function : ``)`` immediately before ``=>`` (catches both
# ``() => x`` and ``(a, b) => a + b``). Naked ``=>`` is not enough —
# CSS selectors and other strings can include it.
_ARROW_FN_RE = re.compile(r"\)\s*=>")
# No ``\s*`` between the identifier and ``(`` : real function calls
# never have a space there (``foo()`` / ``state.toggle()``), but
# prose does (``Sign up (free)`` / ``Email (work)``). The trailing
# whitespace allowance used to misclassify text as JS.
_FUNCTION_CALL_RE = re.compile(r"\b[a-zA-Z_$][a-zA-Z0-9_$]*\(")


def reads_as_client_expr(value: Any, owner: type, name: str) -> bool:
    """La question complète : ``value``, posée sur CETTE prop, est-elle du code ?

    Deux moitiés, et l'ordre compte :

    1. la **déclaration** — ``reactive_prop(never_code=True)`` dit que
       cette prop transporte une donnée. On ne devine pas ;
    2. l'**heuristique** — pour tout le reste, :func:`looks_like_client_expr`
       renifle la valeur.

    Elle vit ici plutôt qu'en ligne dans ``Component.__init__`` parce que
    c'est UNE question, pas deux : séparer la déclaration de l'heuristique
    laissait un appelant lire la seconde sans la première — ce qui est
    exactement l'état d'avant le 2026-08-26, où l'export CSV du datatable
    perdait son ``href``.

    Elle prend ``(owner, name)`` plutôt que le descripteur déjà résolu
    pour tenir en UN appel chez l'appelant : ``Component.__init__`` est
    sous plafond de lignes (``test_the_choke_point_only_shrinks``), et
    une question qui déménage ne doit pas laisser sa résolution derrière
    elle.
    """
    if not isinstance(value, str):
        return False
    descriptor = getattr(owner, "__reactive_props__", {}).get(name)
    if descriptor is not None and descriptor.never_code:
        return False
    return looks_like_client_expr(value)


def looks_like_client_expr(value: str) -> bool:
    """Heuristic : does ``value`` look like an client / JS expression ?

    Returns ``True`` if it carries one of :
    - A leading ``$`` (runtime magics : ``$bz``, ``$dispatch``, ``$el``…).
    - A standalone ``<`` or ``>`` (comparison) — but never ``<=``/``>=`` only,
      we check the wider list above.
    - One of the client / JS markers in :data:`_CLIENT_EXPR_MARKERS`.
    - A function call : ``foo()`` or ``method()``.

    Returns ``False`` for plain identifiers (``primary``), CSS class
    strings, etc.

    ⚠️ **Elle ne protège PAS les URLs**, contrairement à ce que cette
    ligne a promis jusqu'au 2026-08-26 (« Returns False for … URLs
    (``/users/42``) »). C'est vrai de ``/users/42``, qui ne porte aucun
    marqueur — et faux dès qu'une URL en porte un : un padding base64
    (``==``), un ``&&`` dans une query string. La promesse tenait par
    l'exemple choisi, pas par le code, et trois régressions sont passées
    par là.

    Une prop qui porte une URL se déclare
    ``reactive_prop(never_code=True)`` : l'heuristique ne tourne alors
    pas dessus du tout. C'est le seul mécanisme — les exclusions de forme
    (``data:``…) ont été retirées avec lui.

    **L'échappatoire, quand l'heuristique se trompe** — dans les deux sens :

    - *elle voit du code là où tu voulais du texte* (``placeholder="a && b"``)
      → passe par ``attrs={"placeholder": "a && b"}``. Le bucket ``attrs=``
      court-circuite l'heuristique et gagne la précédence sur le kwarg nommé.
    - *tu veux forcer une expression client* → écris la directive toi-même :
      ``**{"bz-attr:placeholder": "a && b"}``.

    ⚠️ Cette docstring a longtemps annoncé « force client binding via the
    explicit ``:attr_name="expr"`` » — or ``:`` est un préfixe **Alpine**,
    mort depuis V3. L'échappatoire documentée ne faisait donc rien du tout,
    et depuis le 2026-07-29 elle lève (``reject_dead_alpine_attr``). Il n'y
    avait plus d'opt-out fonctionnel documenté ; ce sont les deux ci-dessus.
    """
    if not isinstance(value, str) or not value:
        return False

    # Leading ``$`` — only when followed by an JS identifier
    # (letter / underscore / dot). Lone ``$`` (currency prefix) and
    # ``$<digit>`` (regex backref-like, ``$1.50``) are text, not
    # the runtime. Regression : the playground's ``prefix="$"`` control
    # used to emit ``:prefix="$"`` and the runtime crashed with
    # ``$ is not defined``.
    if value.startswith("$"):
        if len(value) > 1 and (
            value[1].isalpha() or value[1] == "_" or value[1] == "."
        ):
            return True
        return False

    # Strong markers : comparisons, logical ops, ternary, arrow fn.
    for marker in _CLIENT_EXPR_MARKERS:
        if marker in value:
            return True

    # Bare ``<`` or ``>`` as comparison — but skip cases where they're
    # part of HTML / templates passed verbatim. Conservative : only
    # treat as expression when surrounded by spaces (``a > 1``).
    if " < " in value or " > " in value:
        return True

    # Ternary : strict pattern with surrounding spaces + a colon later.
    if _TERNARY_RE.search(value):
        return True

    # Arrow function : the ``=>`` must come right after a ``)``.
    if _ARROW_FN_RE.search(value):
        return True

    # Function call. Catches ``foo()``, ``$bz._resolveIcon(…)``,
    # ``state.toggle()``. **Tightened (mai 2026)** : the match must sit
    # at the start of the string, optionally preceded ONLY by
    # identifier-chain chars (letters / digits / underscore / dot /
    # dollar). Without this, text content containing a parenthesised
    # aside (``Sign up (free)``) or HTML embedded JS
    # (``<script>alert(1)</script>``) was misclassified as a client expr
    # and the runtime crashed trying to evaluate it. Regression
    # reported via the Input playground Edge cases card.
    match = _FUNCTION_CALL_RE.search(value)
    if not match:
        return False
    prefix = value[: match.start()]
    if not prefix:
        return True
    return all(c.isalnum() or c in "_.$" for c in prefix)

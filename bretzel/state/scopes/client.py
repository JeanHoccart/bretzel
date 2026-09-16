"""``ClientState`` — typed state living in the browser.

The schema, the operator-overloaded :class:`ClientBinding` returned at
render time, and the mutation-helper sugar are all defined here.

How field access is resolved depends on the **render flag** held on a
context-local. When the render layer enters its scope ::

    with rendering_scope():
        # accessing my_state.field returns ClientBinding(...)
        ...

field access on a :class:`ClientState` instance produces a
:class:`ClientBinding` wrapper — components detect it and emit the right
``bz-attr:`` / ``bz-model`` attributes. Outside of that scope (typical
inside an action handler), the same access returns the raw value, so
server code can read what the client most-recently sent.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, ClassVar, Final, Literal, NoReturn

from bretzel.state.base import State
from bretzel.state.fields.descriptor import Field

# ───────────────────────────────────────────────────────────────────────────
# Persist modes — un seul axe : combien de temps la valeur survit.
#
#   "memory" (défaut) : RAM JS. Perdue au reload (F5) et à la fermeture.
#   "session"         : sessionStorage. Survit au reload, perdue à la fermeture.
#   "local"           : localStorage. Survit à tout.
#
# Le runtime (04_persistence.js) n'attache aucun adaptateur de stockage
# pour "memory" : la valeur reste en RAM JS (comportement volatile),
# perdue au reload. Les modes "page" et le TTL ont été retirés (côté
# runtime ET API) — c'étaient des reliquats V2 sans effet.
# ───────────────────────────────────────────────────────────────────────────

PERSISTS: Final[tuple[str, ...]] = ("memory", "session", "local")
ClientPersist = Literal["memory", "session", "local"]


# ───────────────────────────────────────────────────────────────────────────
# Render-flag — when True, attribute access wraps in ClientBinding
# ───────────────────────────────────────────────────────────────────────────

_RENDERING: ContextVar[bool] = ContextVar(
    "bretzel_client_rendering", default=False
)


@contextmanager
def rendering_scope() -> Iterator[None]:
    """Mark the active task as 'rendering'.

    Within this scope, :class:`ClientState` field reads return a
    :class:`ClientBinding`. The render layer enters this scope around
    every page / partial render so components see bindings, while action
    handlers run with the flag unset and see raw values.
    """
    token = _RENDERING.set(True)
    try:
        yield
    finally:
        _RENDERING.reset(token)


# ───────────────────────────────────────────────────────────────────────────
# Errors
# ───────────────────────────────────────────────────────────────────────────


class ReactivityError(RuntimeError):
    """Raised when a :class:`ClientBinding` is misused server-side.

    The classic case is ``if state.is_open: ...`` during render — the
    Python ``__bool__`` would freeze the value at server time and break
    client-side reactivity. We refuse it loudly with a clear hint.
    """


# ───────────────────────────────────────────────────────────────────────────
# JS literal serialisation
# ───────────────────────────────────────────────────────────────────────────


def _to_js(value: Any) -> str:
    """Convert a Python value to its JS-literal source form.

    Used everywhere a binding builds a ``bz-*`` client expression that
    mixes bindings and Python literals. ``ClientBinding`` operands serialise
    to their ``$bz.state.…`` path ; primitives go through ``json.dumps``
    so quoting and escaping are correct.
    """
    if isinstance(value, ClientBinding):
        return value.binding_path()
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str | list | tuple | dict):
        return json.dumps(value)
    raise TypeError(
        f"Cannot embed {type(value).__name__} in a client expression. "
        "Allowed types : bool, int, float, str, list, tuple, dict, None, "
        "ClientBinding."
    )


# ───────────────────────────────────────────────────────────────────────────
# ClientBinding — the wrapper returned by ClientState attribute access
# ───────────────────────────────────────────────────────────────────────────


class ClientBinding:
    """Wrapper carrying field metadata + the current server-side value."""

    __slots__ = (
        "class_name",
        "field_name",
        "instance_key",
        "sends_to_server",
        "value",
    )

    def __init__(
        self,
        *,
        class_name: str,
        instance_key: str,
        field_name: str,
        value: Any,
        sends_to_server: bool = True,
    ) -> None:
        self.class_name = class_name
        self.instance_key = instance_key
        self.field_name = field_name
        self.value = value
        #: Recopié de ``ClientState.__send_to_server__`` à la construction.
        #: Le binding porte le NOM de sa classe, pas la classe — donc sans
        #: cette copie, un consommateur ne peut pas savoir si le champ
        #: remonte. Le seul qui en a besoin est la garde two-way de
        #: ``Component.__init__`` : lier un champ que le CLIENT écrit à un
        #: état qui ne remonte pas le perd en silence. Défaut ``True`` —
        #: le cas de très loin majoritaire, et la valeur sûre.
        self.sends_to_server = sends_to_server

    # ── Path serialisation ──────────────────────────────────────────────

    def serialize_path(self) -> str:
        """Short form for ``bz-attr:`` / ``bz-model`` HTML attributes.

        Format : ``ClassName.key.field``. The runtime prepends
        ``$bz.state.`` itself when interpreting these attributes.
        """
        return f"{self.class_name}.{self.instance_key}.{self.field_name}"

    def binding_path(self) -> str:
        """Full form for inline ``bz-*`` expressions (``bz-attr:disabled="…"``).

        Format : ``$bz.state.ClassName.key.field``. Use this whenever
        interpolating into a string passed as ``on_click="…"`` or other
        raw ``bz-*`` attributes.
        """
        return f"$bz.state.{self.serialize_path()}"

    # ── Bool trap ──────────────────────────────────────────────────────

    def __bool__(self) -> bool:
        raise ReactivityError(
            "ClientBinding cannot be used in a Python boolean context. "
            f"You evaluated {self.binding_path()!r} in an `if`/`and`/`or` "
            "expression — this would freeze the value at server render "
            "time and break client-side reactivity. Use Tailwind data "
            "variants (e.g. `data-[active=true]:ring-primary`) and pass "
            "the binding through `data_active=state.field`, or hand the "
            "binding directly to a reactive_prop."
        )

    # ── F-string / str() trap ─────────────────────────────────────────
    #
    # The same footgun as ``__bool__`` : ``f"count : {state.count}"``
    # would freeze the binding's repr into a static string at server
    # render time. We refuse loudly with a clear hint so the dev sees
    # the right pattern instead of a silent Bretzel-internals leak.

    def __format__(self, format_spec: str) -> str:
        raise ReactivityError(
            f"ClientBinding cannot be interpolated into an f-string : "
            f"``f'… {{state.field}} …'`` would freeze the rendered text "
            f"at server-render time, breaking client-side reactivity. "
            f"Either : (a) pass the binding directly — ``ui.text(state.field)`` "
            f"— so the runtime emits ``bz-text=…``, OR (b) compose adjacent "
            f"text fragments — ``ui.text('count : '); ui.text(state.field)``. "
            f"Path : {self.binding_path()}"
        )

    def __str__(self) -> str:
        # ``str(binding)`` is just as broken — same fix as f-string.
        raise ReactivityError(
            "ClientBinding cannot be coerced to str — use the binding "
            "directly in a component (``ui.text(state.field)``). "
            f"Path : {self.binding_path()}"
        )

    # ── Comparison operators → ClientExpression ────────────────────────
    #
    # ⚠️ INVARIANT — tout opérateur de cette algèbre rend une source
    # ATOMIQUE : interpolable dans une expression plus large sans
    # re-associer. Un opérateur lâche parenthèse son résultat ; un accès
    # membre ou un appel (``x.length``) l'est déjà. Le pourquoi en détail
    # et la gate : ``tests/consistency/test_client_expression_atomic.py``.
    #
    # Périmètre : cette algèbre. Une ``ClientExpression`` bâtie à la main
    # (``meta/iteration/*``) sert de valeur TERMINALE à ``visible=`` et
    # n'est jamais opérande — la parenthéser coûterait des octets par
    # ligne rendue sans rien garantir de plus.

    def __eq__(self, other: object) -> ClientExpression:  # type: ignore[override]
        return ClientExpression(f"({self.binding_path()} === {_to_js(other)})")

    def __ne__(self, other: object) -> ClientExpression:  # type: ignore[override]
        return ClientExpression(f"({self.binding_path()} !== {_to_js(other)})")

    def __lt__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} < {_to_js(other)})")

    def __le__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} <= {_to_js(other)})")

    def __gt__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} > {_to_js(other)})")

    def __ge__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} >= {_to_js(other)})")

    # ── Arithmetic operators ──────────────────────────────────────────

    def __add__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} + {_to_js(other)})")

    def __radd__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({_to_js(other)} + {self.binding_path()})")

    def __sub__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} - {_to_js(other)})")

    def __rsub__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({_to_js(other)} - {self.binding_path()})")

    def __mul__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} * {_to_js(other)})")

    def __rmul__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({_to_js(other)} * {self.binding_path()})")

    def __truediv__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} / {_to_js(other)})")

    def __floordiv__(self, other: Any) -> ClientExpression:
        return ClientExpression(
            f"Math.floor({self.binding_path()} / {_to_js(other)})"
        )

    def __mod__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} % {_to_js(other)})")

    def __neg__(self) -> ClientExpression:
        return ClientExpression(f"(-{self.binding_path()})")

    def __abs__(self) -> ClientExpression:
        return ClientExpression(f"Math.abs({self.binding_path()})")

    def __round__(self, ndigits: int | None = None) -> ClientExpression:
        path = self.binding_path()
        if not ndigits:
            return ClientExpression(f"Math.round({path})")
        factor = 10 ** int(ndigits)
        return ClientExpression(f"(Math.round({path} * {factor}) / {factor})")

    # ── Logical operators ─────────────────────────────────────────────

    def __invert__(self) -> ClientExpression:
        # Parenthésé aussi : ``!x.length`` lie le ``.length`` avant le
        # ``!``, donc un ``!x`` nu se fait manger par un accès membre.
        return ClientExpression(f"(!{self.binding_path()})")

    def __and__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} && {_to_js(other)})")

    def __or__(self, other: Any) -> ClientExpression:
        return ClientExpression(f"({self.binding_path()} || {_to_js(other)})")

    # ── Named accessors (alternative to operators, for clarity) ───────

    def eq(self, other: Any) -> ClientExpression:
        return self.__eq__(other)

    def ne(self, other: Any) -> ClientExpression:
        return self.__ne__(other)

    def lt(self, other: Any) -> ClientExpression:
        return self.__lt__(other)

    def le(self, other: Any) -> ClientExpression:
        return self.__le__(other)

    def gt(self, other: Any) -> ClientExpression:
        return self.__gt__(other)

    def ge(self, other: Any) -> ClientExpression:
        return self.__ge__(other)

    def not_(self) -> ClientExpression:
        return self.__invert__()

    def between(self, low: Any, high: Any) -> ClientExpression:
        path = self.binding_path()
        return ClientExpression(
            f"({path} >= {_to_js(low)} && {path} <= {_to_js(high)})"
        )

    def length(self) -> ClientExpression:
        return ClientExpression(f"{self.binding_path()}.length")

    def contains(self, item: Any) -> ClientExpression:
        return ClientExpression(
            f"{self.binding_path()}.includes({_to_js(item)})"
        )

    def then_else(self, then: Any, otherwise: Any) -> ClientExpression:
        """Client-side ternary : ``cond ? then : otherwise``. Python can't
        overload ``a if cond else b``, so this is the way to derive a value
        from a condition without a raw ``ClientExpression`` ::

            ui.text((cart.count > 0).then_else("In cart", "Empty"))
        """
        return ClientExpression(
            f"({self.binding_path()} ? {_to_js(then)} : {_to_js(otherwise)})"
        )

    def to_fixed(self, digits: int = 2) -> ClientExpression:
        """Format a numeric binding with a fixed number of decimals
        (JS ``Number(x).toFixed(n)``) — for money / rounded display ::

            ui.text(price.to_fixed(2))      # "19.90"
        """
        return ClientExpression(
            f"Number({self.binding_path()}).toFixed({int(digits)})"
        )

    def join(self, sep: str = ", ", *, empty: str = "") -> ClientExpression:
        """Render a list binding as a ``sep``-joined string, falling back
        to ``empty`` when the list is empty / undefined.

        The Pythonic way to *display* a client list as text — no raw
        ``ClientExpression`` needed at the call site :

            ui.text(events.log.join("\\n", empty="(none yet)"))

        Null-guards the path (``|| []``) so it works before the store is
        first written.
        """
        path = self.binding_path()
        return ClientExpression(
            f"((({path} || []).join({_to_js(sep)})) || {_to_js(empty)})"
        )

    # ── Mutation helpers — return V3 client source ready for on_*=... ─
    #
    # Every helper REASSIGNS the path (``x = …``) rather than mutating in
    # place : V3 signals are identity-compared (Object.is), so an
    # in-place ``arr.push(x)`` keeps the same array reference and the
    # signal never fires — the bound view wouldn't update. Cf. traps.md
    # § "array mutations MUST reassign".

    def toggle(self) -> str:
        path = self.binding_path()
        return f"{path} = !{path}"

    def increment(self, by: float = 1) -> str:
        return f"{self.binding_path()} += {_to_js(by)}"

    def decrement(self, by: float = 1) -> str:
        return f"{self.binding_path()} -= {_to_js(by)}"

    def set(self, value: Any) -> str:
        return f"{self.binding_path()} = {_to_js(value)}"

    def push(self, item: Any) -> str:
        # Reassign with a fresh array (spread + append) so the signal's
        # identity check sees a new reference and re-renders. ``|| []``
        # guards a null/undefined initial list.
        path = self.binding_path()
        return f"{path} = [...({path} || []), {_to_js(item)}]"

    def clear(self) -> str:
        return f"{self.binding_path()} = []"

    # ── Identity / repr ────────────────────────────────────────────────

    def __hash__(self) -> int:
        return hash(self.serialize_path())

    def __repr__(self) -> str:
        return f"ClientBinding({self.binding_path()})"


# ───────────────────────────────────────────────────────────────────────────
# ClientExpression — composable expression carrying only its JS source
# ───────────────────────────────────────────────────────────────────────────


class ClientExpression(ClientBinding):
    """Build a browser-side expression from one or more client bindings."""

    __slots__ = ("_expr",)

    #: Sentinelle « pas de valeur serveur » — distincte de ``None``, qui
    #: est une valeur JS légitime (et falsy, donc pré-poser
    #: ``display:none`` dessus serait juste, pas neutre).
    _NO_SSR_VALUE: ClassVar[object] = object()

    def __init__(self, expr: str, *, ssr_value: Any = _NO_SSR_VALUE) -> None:
        # Bypass ClientBinding.__init__ — no field metadata for raw expressions.
        self._expr = expr
        if ssr_value is not ClientExpression._NO_SSR_VALUE:
            self.value = ssr_value

    def serialize_path(self) -> str:
        return self._expr

    def binding_path(self) -> str:
        return self._expr

    # ── Les mutateurs, refusés ────────────────────────────────────────
    #
    # ⚠️ Hérités de :class:`ClientBinding`, ils produisaient du JS INVALIDE
    # en silence : ``(state.a | state.b).set(3)`` émettait ``(…||…) = 3``,
    # une ``SyntaxError`` au bind navigateur, et zéro signal côté Python.
    # Une expression est une LECTURE — il n'existe aucune cible à laquelle
    # assigner.
    #
    # ``Component`` gardait déjà l'autre porte (le passage d'une expression
    # à une prop à double sens, ``component.py``) ; la même erreur entrait
    # par celle-ci. Le refus ne coûte rien au rendu : il ne se déclenche
    # qu'en cas de mésusage.
    def _refuse_mutation(self, verbe: str) -> NoReturn:
        raise ReactivityError(
            f"``.{verbe}()`` sur une ClientExpression — une expression est "
            f"une LECTURE, il n'y a pas de cible à laquelle assigner. "
            f"L'appel émettrait du JS invalide (``{self._expr} = …``), qui "
            f"ne se verrait qu'au bind navigateur.\n"
            f"  Appelle le mutateur sur le CHAMP : ``state.champ.{verbe}(…)``."
        )

    def toggle(self) -> NoReturn:
        self._refuse_mutation("toggle")

    def increment(self, by: float = 1) -> NoReturn:
        self._refuse_mutation("increment")

    def decrement(self, by: float = 1) -> NoReturn:
        self._refuse_mutation("decrement")

    def set(self, value: Any) -> NoReturn:
        self._refuse_mutation("set")

    def push(self, item: Any) -> NoReturn:
        self._refuse_mutation("push")

    def clear(self) -> NoReturn:
        self._refuse_mutation("clear")

    def __repr__(self) -> str:
        return f"ClientExpression({self._expr!r})"


# ───────────────────────────────────────────────────────────────────────────
# ClientState
# ───────────────────────────────────────────────────────────────────────────


class ClientState(State):
    """Typed state mirrored into the browser by the runtime."""

    __persist__: ClassVar[ClientPersist] = "memory"
    __send_to_server__: ClassVar[bool] = True

    def __init_subclass__(
        cls,
        *,
        persist: ClientPersist | None = None,
        send_to_server: bool | None = None,
        **kwargs: object,
    ) -> None:
        super().__init_subclass__(**kwargs)

        if persist is not None:
            if persist not in PERSISTS:
                raise ValueError(
                    f"Invalid persist {persist!r} on {cls.__name__} : "
                    f"expected one of {PERSISTS}."
                )
            cls.__persist__ = persist

        if send_to_server is not None:
            # ``isinstance`` et non un test de vérité : ``send_to_server=""``
            # ou ``="false"`` sont les fautes de frappe plausibles, et la
            # seconde est TRUTHY — elle ferait exactement l'inverse de ce
            # qu'on lit, sans rien signaler. Le seul réglage dont la
            # mauvaise valeur est muette mérite sa garde.
            if not isinstance(send_to_server, bool):
                raise ValueError(
                    f"Invalid send_to_server {send_to_server!r} on "
                    f"{cls.__name__} : expected True or False."
                )
            cls.__send_to_server__ = send_to_server

    # ── Render-flag-aware attribute access ─────────────────────────────

    def __getattribute__(self, name: str) -> Any:
        # Dunder / private attributes always pass through unchanged. This
        # also short-circuits ``self._key`` etc. used internally by the
        # binding constructor below.
        if name.startswith("_"):
            return object.__getattribute__(self, name)

        # When NOT rendering, behave like a regular State — handlers see
        # raw Python values.
        if not _RENDERING.get():
            return object.__getattribute__(self, name)

        # Inside a render : only Field accesses get wrapped. Methods,
        # computed properties, validators stay normal.
        descriptor = inspect.getattr_static(type(self), name, None)
        if not isinstance(descriptor, Field):
            return object.__getattribute__(self, name)

        # Resolve the raw value via the descriptor with rendering OFF, so
        # we don't recurse forever when ``Field.__get__`` reads internal
        # state (and so factory defaults still get cached on the instance).
        token = _RENDERING.set(False)
        try:
            raw_value = object.__getattribute__(self, name)
        finally:
            _RENDERING.reset(token)

        return ClientBinding(
            class_name=type(self).__name__,
            instance_key=object.__getattribute__(self, "_key"),
            field_name=name,
            value=raw_value,
            sends_to_server=type(self).__send_to_server__,
        )

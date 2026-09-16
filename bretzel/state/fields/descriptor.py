"""``Field`` descriptor — the storage / access primitive for typed state.

Every typed attribute on a :class:`~bretzel.state.base.State` subclass is
backed by a :class:`Field` instance. The descriptor's two jobs :

1. Read / write the value on the host instance, with no extra ceremony at
   the call site (``cart.coupon`` reads, ``cart.coupon = "X"`` writes).
2. Hook the framework's :class:`~bretzel.core.tracking.DependencyTracker`
   into every read and write, so ``@computed`` / re-render observers see
   the right dependency graph.

The metaclass in :mod:`bretzel.state.base` is responsible for detecting
plain class-level annotations and wrapping them in ``Field`` automatically.
Users only need :func:`field` for non-trivial defaults (``default_factory``
mainly).
"""

from __future__ import annotations

import json
import types
from collections.abc import Callable
from typing import Any, Final, Union, get_args, get_origin

from bretzel.core.tracking import TRACKER
from bretzel.state.types import decode_value

# ───────────────────────────────────────────────────────────────────────────
# Sentinel — distinguishable from any real ``default`` (including ``None``)
# ───────────────────────────────────────────────────────────────────────────


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final[Any] = _Missing()


# ───────────────────────────────────────────────────────────────────────────
# Form-data coercion
# ───────────────────────────────────────────────────────────────────────────

# Strings the dispatcher + plain HTML forms can plausibly send for a
# bool field. Anything outside this set raises so we don't silently
# turn "maybe" into True/False.
_TRUE_STRINGS = frozenset({"true", "1", "on", "yes"})
_FALSE_STRINGS = frozenset({"false", "0", "off", "no", ""})
_BOOL_STRINGS_HINT = repr(sorted(_TRUE_STRINGS | _FALSE_STRINGS))

_SCALAR_TYPES: Final[tuple[type, ...]] = (bool, int, float)

#: Les types déclarés qui n'ont RIEN à décoder — ni codec métier, ni
#: énumération. Ils couvrent la quasi-totalité des champs, d'où la sortie
#: rapide de :meth:`Field.__set__`.
_NOTHING_TO_DECODE: Final[frozenset[Any]] = frozenset(
    {str, int, float, bool, None}
)

#: Les conteneurs qu'un champ peut déclarer et qu'un contrôle sérialise en
#: JSON. ``tuple`` n'y est PAS : ``json.loads`` ne produit jamais de tuple,
#: donc l'annoncer ferait lever tout ce qui arrive du formulaire.
_COMPOSITE_TYPES: Final[tuple[type, ...]] = (list, dict)

#: Les façons dont deux écritures concurrentes se combinent. ``None`` —
#: absent d'ici — veut dire « remplacer », et c'est le défaut : pour un
#: CHOIX (une page, un tri), le dernier qui écrit a raison.
MERGES: Final[tuple[str, ...]] = ("add",)


def _resolve_scalar_target(type_: Any) -> type | None:
    """Return the scalar type to coerce *into*, or ``None`` if N/A.

    Only two annotation shapes coerce :

    - Plain scalar : ``flag: bool`` → ``bool``.
    - Nullable scalar : ``flag: bool | None`` / ``Optional[bool]`` →
      ``bool``. We unwrap only when ``None`` is the *only* extra arg so
      ambiguous unions like ``int | str`` stay untouched (the form
      string is a legitimate value for the ``str`` branch).
    """
    if type_ in _SCALAR_TYPES:
        return type_  # type: ignore[no-any-return]
    origin = get_origin(type_)
    if origin is Union or origin is types.UnionType:
        args = get_args(type_)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and non_none[0] in _SCALAR_TYPES:
            return non_none[0]  # type: ignore[no-any-return]
    return None


class _SkipAssignment:
    """Sentinel returned by :func:`_coerce_scalar` to tell
    :meth:`Field.__set__` to no-op on this write. Used when a form
    sends an empty string for a typed-non-str field — semantically,
    "the user didn't enter a value", which should leave the current
    state field untouched rather than blowing up with a coercion
    error or silently storing garbage."""


_SKIP_ASSIGNMENT: _SkipAssignment = _SkipAssignment()


def _resolve_container_target(type_: Any) -> type | None:
    """``list`` / ``dict``, y compris PARAMÉTRÉS et nullables. Sinon ``None``.

    ``list[str]`` n'est pas ``list`` : ``type_ in (list, dict)`` est faux, et
    c'est pourtant l'annotation la plus courante — celle que ``state.md``
    donne en exemple (``tags: list[str] = field(default_factory=list)``).
    Sans cette résolution, le décodage ne s'appliquait qu'aux annotations
    nues et laissait passer la forme que tout le monde écrit. Trouvé en
    relisant le correctif, pas en l'écrivant.

    Même prudence que :func:`_resolve_scalar_target` sur les unions : on ne
    déballe que si ``None`` est le seul autre membre.
    """
    if type_ in _COMPOSITE_TYPES:
        return type_  # type: ignore[no-any-return]
    origin = get_origin(type_)
    if origin in _COMPOSITE_TYPES:
        return origin  # type: ignore[no-any-return]
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in get_args(type_) if a is not type(None)]
        if len(non_none) == 1:
            return _resolve_container_target(non_none[0])
    return None


def _coerce_composite(value: Any, type_: Any) -> Any:
    """Décoder le JSON qu'un contrôle à valeur COMPOSITE dépose dans le form.

    Six composants portent une valeur qui n'est pas un scalaire — une
    sélection multiple (``toggle_group`` / ``select`` / ``combobox``), deux
    bornes (``date_range_picker``, ``slider(range=True)``), une répartition
    (``resizable``). Aucun `<input>` ne transporte autre chose qu'une chaîne,
    donc tous sérialisent en ``JSON.stringify`` dans un champ caché.

    Sans ce décodage, un champ ``list`` recevait la CHAÎNE ``'["a","b"]'`` et
    la rangeait telle quelle. Le rendu suivant faisait ``list(...)`` dessus et
    affichait quatorze caractères ; la bouillie était repostée, et elle
    **survivait au rechargement**. Aucune erreur nulle part — c'est exactement
    le mode d'échec que la coercition scalaire existe pour supprimer sur les
    ``bool``/``int``, appliqué un cran plus haut.

    Mesuré le 2026-08-19 sur l'écran Paramètres du CRM.

    Règles :

    - chaîne vide → conteneur vide. « Rien de sélectionné » est une valeur
      que l'utilisateur a choisie, pas une absence de saisie — la sauter
      (comme le fait ``""`` sur un ``int``) rendrait un multi-select
      impossible à VIDER, le jumeau exact du bug de la case décochée ;
    - une chaîne qui **ressemble** à un conteneur (``[…]`` / ``{…}``) est
      décodée, et un JSON malformé y ``ValueError`` — donc un message de
      champ, pas un silence ;
    - **tout le reste passe INCHANGÉ**, et cette clause est la plus
      importante des trois. Le magasin ``ClientState`` ne voyage pas en
      JSON : htmx sérialise un tableau **élément par élément**
      (``formDataFromObject`` : ``obj[key].forEach(v => append(key, v))``),
      donc un champ ``list`` d'un ``ClientState`` reçoit ``"change"``, pas
      ``'["change"]'``. Une première version de ce décodage levait dessus,
      et comme ``State._apply_fields`` n'a pas de garde, **toute action
      d'une page portant un tel état rendait 500**. Six états du playground
      étaient concernés, et la suite complète était verte : aucune gate ne
      poste un magasin client. Trouvé en relecture, pas par un test.
    """
    container = _resolve_container_target(type_)
    if not isinstance(value, str) or container is None:
        return value
    type_ = container
    text = value.strip()
    if not text:
        return type_()
    if not text.startswith(("[", "{")):
        # Pas un conteneur sérialisé — cf. la clause 3 de la docstring.
        return value
    try:
        decoded = json.loads(text)
    except ValueError as exc:
        raise ValueError(
            f"Impossible de lire {value!r} comme du JSON pour un champ "
            f"{type_.__name__} : {exc}."
        ) from exc
    if not isinstance(decoded, type_):
        raise ValueError(
            f"{value!r} décode en {type(decoded).__name__}, pas en "
            f"{type_.__name__}."
        )
    return decoded


def _coerce_scalar(value: Any, type_: Any) -> Any:
    """Coerce string form-data values to a field's declared scalar type.

    Form submissions arrive as strings ; without this, handlers would
    need per-field ``if value in ("true", "false")`` ladders before
    ``setattr(state, key, value)``. Only ``str → bool|int|float`` is
    performed — non-string values and non-scalar fields pass through.

    Empty string for a typed (non-str) field returns the
    :data:`_SKIP_ASSIGNMENT` sentinel : an HTML form sends ``""`` for
    an unfilled ``type="number"`` input (or similar), which the
    handler should treat as "no value provided" rather than a
    coercion error. The descriptor catches the sentinel and skips
    the assignment, leaving the field at its current value.

    Raises :class:`ValueError` on malformed *non-empty* input so bad
    data still surfaces loudly instead of landing a nonsensical
    value in state.
    """
    if not isinstance(value, str) or type_ is None:
        return value
    target = _resolve_scalar_target(type_)
    # ``int`` / ``float`` fields : empty form value (typical HTML
    # ``type="number"`` input erased by the user) → tell the
    # descriptor to skip the assignment. Without this the dispatch
    # would 500 on ``float("")`` / ``int("")``. ``str`` and ``bool``
    # keep their existing handling : "" is a valid str, and bool's
    # legacy ``_FALSE_STRINGS`` includes "" → False.
    if value == "" and target in (int, float):
        return _SKIP_ASSIGNMENT
    if target is bool:
        v = value.strip().lower()
        if v in _TRUE_STRINGS:
            return True
        if v in _FALSE_STRINGS:
            return False
        raise ValueError(
            f"Cannot coerce {value!r} to bool — expected one of "
            f"{_BOOL_STRINGS_HINT}."
        )
    if target is int:
        return int(value)  # int() already strips whitespace ; ValueError on garbage
    if target is float:
        return float(value)
    return value


# ───────────────────────────────────────────────────────────────────────────
# Descriptor
# ───────────────────────────────────────────────────────────────────────────


class Field:
    """Per-attribute descriptor.

    Instances are configured with a default (value or factory) and an
    optional ``type_`` annotation captured at class-build time. The actual
    name is filled in by :py:meth:`__set_name__` when the descriptor is
    assigned to a class attribute.

    Storage layout : the value is kept on the host instance under the
    private key ``f"_field_{name}"``. We avoid name mangling and never
    shadow the public attribute (which is the descriptor itself).
    """

    __slots__ = (
        "_storage_key", "default", "default_factory", "merge", "name",
        "type_", "url",
    )

    def __init__(
        self,
        *,
        default: Any = MISSING,
        default_factory: Callable[[], Any] | None = None,
        type_: type | None = None,
        url: str | None = None,
        merge: str | None = None,
    ) -> None:
        if default is not MISSING and default_factory is not None:
            raise ValueError(
                "Field cannot have both a 'default' and a 'default_factory'."
            )
        self.default = default
        self.default_factory = default_factory
        self.type_: type | None = type_
        #: Le nom que ce champ porte dans l'URL — ``field(url="tri")``.
        #: DÉCLARE le nom ; il ne suffit pas à rendre le champ adressable
        #: (c'est ``addressable=True`` sur la classe qui l'allume), parce
        #: que ce qui est dans une URL est PUBLIC et ne doit jamais
        #: s'obtenir par accident. Cf. :mod:`bretzel.state.url`.
        self.url: str | None = url
        #: Comment deux écritures concurrentes se combinent. ``None``
        #: remplace — le dernier qui écrit gagne. ``"add"`` additionne :
        #: le commit envoie l'ÉCART, et le magasin l'applique sans lire,
        #: donc deux requêtes concurrentes comptent toutes les deux.
        self.merge: str | None = merge
        self.name: str = ""  # populated by __set_name__
        self._storage_key: str = ""

    # ── Descriptor protocol ─────────────────────────────────────────────

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self._storage_key = f"_field_{name}"

    def __get__(self, instance: object | None, owner: type | None = None) -> Any:
        if instance is None:
            return self  # class-level access returns the descriptor itself
        TRACKER.track_access(instance, self.name)
        try:
            return instance.__dict__[self._storage_key]
        except KeyError:
            return self._resolve_default(instance)

    def __set__(self, instance: object, value: Any) -> None:
        cls = type(instance)
        validators_map: dict[str | None, list[Any]] = getattr(cls, "__validators__", {})

        # Coerce form-data strings before anything else sees them, so
        # validators receive the declared type and handlers can write
        # ``setattr(state, key, value)`` for bool/int/float fields
        # without per-field ladders.
        value = _coerce_scalar(value, self.type_)
        # …puis les conteneurs : une sélection multiple, une plage de dates,
        # une répartition de panneaux arrivent en JSON dans un champ caché.
        value = _coerce_composite(value, self.type_)
        # …puis les types métier. Un seul geste pour DEUX chemins : la
        # relecture depuis le magasin (où une ``date`` est revenue en
        # ``"2026-03-04"``) et l'écriture d'un formulaire (où elle arrive
        # en chaîne aussi). Les traiter séparément aurait laissé le
        # second silencieux — c'était le cas : le champ typé ``date``
        # gardait la ``str`` sans que rien ne le dise.
        # Sortie rapide : 99 % des champs sont ``str``/``int``/``bool``,
        # et ``decode_value`` leur coûtait quatre appels pour ne rien
        # faire — mesuré le 2026-09-06, +16 % sur chaque écriture de
        # champ. Le type déclaré ne change jamais après la construction
        # de la classe, donc ce test est le même à chaque écriture.
        if self.type_ not in _NOTHING_TO_DECODE:
            value = decode_value(self.type_, value)

        # ``_SKIP_ASSIGNMENT`` sentinel : the coercer detected an
        # empty form-data value targeting a typed-non-str field
        # (e.g. ``type="number"`` input erased by the user). Skip
        # the write entirely so the current value is preserved and
        # no validator runs on a placeholder. This is what every
        # form handler ``server_changed(**kwargs)`` expects when
        # a numeric input is emptied — without this, the dispatch
        # would 500 on a ``float("")`` ValueError.
        if isinstance(value, _SkipAssignment):
            return

        # 1. Single-field validators in declaration order. Each may transform
        #    or reject ; the chained return value is what gets stored.
        for v in validators_map.get(self.name, ()):
            value = v.fn(instance, value)

        # 2. Capture previous state for rollback if a whole-instance
        #    validator rejects after we've written.
        had_previous = self._storage_key in instance.__dict__
        previous: Any = instance.__dict__.get(self._storage_key)

        instance.__dict__[self._storage_key] = value
        if hasattr(instance, "_dirty"):
            instance._dirty = True  # type: ignore[attr-defined]

        # 3. Whole-instance validators (multi-field invariants).
        try:
            for v in validators_map.get(None, ()):
                v.fn(instance)
        except Exception:
            # Rollback — restore prior storage exactly as it was.
            if had_previous:
                instance.__dict__[self._storage_key] = previous
            else:
                instance.__dict__.pop(self._storage_key, None)
            raise

        # 4. Notify only after the mutation has been validated end-to-end.
        TRACKER.notify_change(instance, self.name)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _resolve_default(self, instance: object) -> Any:
        """Return the field's default for ``instance``.

        With ``default_factory`` we materialise the value once and cache
        it on the instance, so each instance gets its own object — the
        mutable-default trap that plain Python defaults are subject to.
        """
        if self.default_factory is not None:
            value = self.default_factory()
            instance.__dict__[self._storage_key] = value
            return value
        if self.default is not MISSING:
            return self.default
        raise AttributeError(
            f"Field {self.name!r} has no value and no default."
        )

    def has_value(self, instance: object) -> bool:
        """``True`` iff ``instance`` has an explicitly stored value for this
        field (defaults aren't materialised by this check)."""
        return self._storage_key in instance.__dict__

    def __repr__(self) -> str:
        parts = [f"name={self.name!r}"]
        if self.default is not MISSING:
            parts.append(f"default={self.default!r}")
        if self.default_factory is not None:
            parts.append(f"default_factory={self.default_factory!r}")
        if self.type_ is not None:
            parts.append(f"type_={self.type_!r}")
        return f"Field({', '.join(parts)})"


# ───────────────────────────────────────────────────────────────────────────
# Public sugar
# ───────────────────────────────────────────────────────────────────────────


def field(
    *,
    default: Any = MISSING,
    default_factory: Callable[[], Any] | None = None,
    url: str | None = None,
    merge: str | None = None,
) -> Any:
    """Declare a typed state field."""
    if isinstance(default, list | dict | set):
        # La garde a DÉMÉNAGÉ ici le 2026-09-05, avec l'obligation de
        # passer par ``field()`` : elle vivait dans la métaclasse, sur le
        # chemin des défauts nus, qui n'existe plus. Sans ce déplacement
        # ``field(default=[])`` passait — le littéral est alors PARTAGÉ
        # par toutes les instances, et muter l'une mute les autres.
        raise ValueError(
            f"field(default={default!r}) : un littéral mutable serait "
            f"partagé par toutes les instances de l'état. Écris "
            f"`field(default_factory={type(default).__name__})`, qui en "
            f"construit un par instance."
        )
    if default is not MISSING and default_factory is not None:
        raise ValueError(
            "field() prend `default` OU `default_factory`, pas les deux."
        )
    if merge is not None and merge not in MERGES:
        raise ValueError(
            f"field(merge={merge!r}) : valeurs acceptées {MERGES}, ou "
            f"``None`` pour remplacer (le défaut)."
        )
    return Field(
        default=default,
        default_factory=default_factory,
        url=url,
        merge=merge,
    )

"""Abstract :class:`State` + the ``_StateMeta`` metaclass.

The metaclass is the magic that lets users write idiomatic Python ::

    class CartState(ServerState, scope="session"):
        items: list[Item] = field(default_factory=list)
        coupon: str = field(default="")

        @computed
        def total(self) -> float:
            return ...

        @validator("coupon")
        def normalize_coupon(self, v: str) -> str:
            return v.strip().upper()

…and have it transparently turned into a typed, tracked, serialisable
state class. La métaclasse parcourt le corps de classe, REFUSE toute
déclaration qui ne passe pas par :func:`~bretzel.state.fields.descriptor.field`
— une seule forme, décidé le 2026-09-05 — et collecte les
:class:`~bretzel.state.fields.computed.ComputedProperty` et
:class:`~bretzel.state.fields.validator.Validator` dans des registres de
classe que les couches descripteur et registre relisent.

Concrete scopes (``ServerState`` / ``ClientState``) live in
``bretzel.state.scopes`` and add the persistence-side configuration on
top of this skeleton.
"""

from __future__ import annotations

import re
import typing
from collections.abc import Iterator
from typing import Any, ClassVar, Final

from bretzel.state.fields.computed import ComputedProperty
from bretzel.state.fields.descriptor import MISSING, Field
from bretzel.state.fields.validator import Validator
from bretzel.state.types import is_storable

# Sentinel returned by ``namespace.get`` so we can tell "no entry" apart
# from "entry is ``None``" (a valid default).
_NOT_PROVIDED: Final[Any] = object()

#: ``ClassVar[…]`` en tête d'annotation, avec ou sans préfixe de module.
#: Les annotations arrivent en TEXTE, d'où la reconnaissance textuelle.
_CLASS_VAR_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:\w+\.)?ClassVar\b"
)

#: Les types qu'un champ ``merge="add"`` peut porter. Le magasin
#: additionne des NOMBRES : ``HINCRBY`` sur une chaîne rend
#: « hash value is not an integer », donc au déploiement.
_ADDABLE_TYPES: Final[tuple[type, ...]] = (int, float)


# ───────────────────────────────────────────────────────────────────────────
# Metaclass
# ───────────────────────────────────────────────────────────────────────────


def _is_class_var(annotation: Any) -> bool:
    """L'annotation dit-elle ``ClassVar`` ?

    Elle arrive en TEXTE la plupart du temps (le ``__future__``, ou le
    format demandé à PEP 649), donc la reconnaissance est textuelle — avec
    le préfixe de module optionnel, ``typing.ClassVar`` étant aussi
    courant que ``ClassVar``. Sur 3.12/3.13 sans le ``__future__``, elle
    arrive en objet, d'où le second test.
    """
    if isinstance(annotation, str):
        return _CLASS_VAR_RE.match(annotation) is not None
    return annotation is ClassVar or typing.get_origin(annotation) is ClassVar


def _refuse_a_bare_declaration(cls_name: str, attr_name: str, valeur: Any) -> None:
    """Un champ se déclare par ``field(...)``, et par rien d'autre.

    **Une seule façon d'écrire une chose.** Une option de champ
    n'a nulle part où se poser sur la forme courte, donc chaque
    déclaration nouvelle devait s'inventer un TYPE (``Counter``,
    ``Amount``…) et grossir la surface publique. Avec un appel, elles
    s'ajoutent en paramètres.

    L'annotation, elle, reste obligatoire : c'est la seule position où
    Python lit une *expression* de type, donc la seule qui sache dire
    ``int | None``.
    """
    if isinstance(valeur, list | dict | set):
        # Le cas le plus piégeux garde son message : un littéral mutable
        # partagé entre instances est une faute en soi, pas seulement une
        # question d'orthographe.
        raise TypeError(
            f"Mutable default for {attr_name!r} on {cls_name!r} : "
            "use 'field(default_factory=...)' instead of a "
            "literal list/dict/set."
        )
    if valeur is _NOT_PROVIDED:
        écrire = "field()"
        constat = "n'a pas de valeur"
    else:
        écrire = f"field(default={valeur!r})"
        constat = f"vaut {valeur!r}"
    raise TypeError(
        f"{cls_name}.{attr_name} {constat} : écris "
        f"`{attr_name}: … = {écrire}`. "
        f"Un champ se déclare par UN appel, et c'est là que vivent "
        f"`default_factory`, `url` et `merge` — il n'y a pas de seconde "
        f"façon de le faire. L'annotation de type, elle, reste : c'est "
        f"elle qui donne le type."
    )


def _refuse_an_unstorable_type(cls_name: str, attr_name: str, fld: Field) -> None:
    """Un champ doit pouvoir ARRIVER jusqu'au magasin, et on le dit tôt.

    Sans ce refus, ``jour: date`` était accepté, le magasin mémoire
    gardait l'objet Python tel quel, et la faute attendait le
    branchement de Redis : ça marchait en dev et cassait au déploiement.
    Lever à l'import déplace la panne là où elle se voit — au démarrage,
    sur la machine de celui qui écrit le champ.

    Même geste que les deux refus voisins : on interdit la forme
    ambiguë plutôt que de la laisser mordre plus tard.
    """
    if is_storable(fld.type_):
        return
    # ⚠️ Une référence AVANT non résolue reste une chaîne (cf. le
    # ``except (NameError, TypeError)`` de la métaclasse, qui laisse
    # ``type_`` tel quel). On ne peut pas juger ce qu'on n'a pas su
    # résoudre : refuser ici casserait un motif que le framework
    # tolère exprès. C'est alors le magasin qui refusera à l'écriture,
    # en nommant le champ.
    if isinstance(fld.type_, str):
        return
    nom = getattr(fld.type_, "__name__", None) or repr(fld.type_)
    raise TypeError(
        f"{cls_name}.{attr_name} est déclaré {nom!r}, que le magasin ne "
        f"sait pas écrire. Un état se persiste en JSON — Bretzel ne "
        f"retombe PAS sur pickle (risque d'exécution de code).\n"
        f"  • si c'est une de tes classes : "
        f"`register_type({nom}, encode=…, decode=…)` une fois, au "
        f"chargement de l'app, et l'annotation suffit ensuite ;\n"
        f"  • si tu sais ce que tu fais : annote `Any`, et c'est le "
        f"magasin qui refusera à l'écriture, en nommant le champ.\n"
        f"Sont connus d'origine : str, int, float, bool, list, dict, "
        f"date, datetime, time, Decimal, UUID et toute énumération."
    )


def _refuse_an_impossible_sum(cls_name: str, attr_name: str, fld: Field) -> None:
    """``merge="add"`` demande un nombre, et un nombre qui part de zéro.

    Les deux refus viennent du magasin, pas d'un goût :

    - ``HINCRBY`` sur une valeur non numérique rend « hash value is not
      an integer ». Sans ce contrôle, la faute attendrait la première
      écriture EN PRODUCTION — le dev tourne en mémoire, où additionner
      deux chaînes lève ailleurs et autrement ;
    - ``HINCRBY`` sur un champ ABSENT compte à partir de 0. Un compteur
      dont le défaut serait 10 verrait donc son premier « ajoute 1 »
      écrire 1 là où l'app affiche 11, et l'écart ne se rattraperait
      jamais. Le rattraper au commit demanderait au backend de connaître
      les défauts de chaque état.

    Un total qui commence ailleurs qu'à zéro n'est de toute façon pas un
    total : c'est une valeur de départ, donc un choix.
    """
    if fld.type_ is not None and fld.type_ not in _ADDABLE_TYPES:
        raise TypeError(
            f"{cls_name}.{attr_name} est déclaré `merge=\"add\"` mais son "
            f"type est {getattr(fld.type_, '__name__', fld.type_)!r}. "
            f"Le magasin ADDITIONNE : seuls `int` et `float` peuvent "
            f"l'être. Pour une liste, il n'y a pas encore d'opération — "
            f"il te faut ton propre verrou."
        )
    depart = fld.default if fld.default is not MISSING else 0
    if depart:
        raise TypeError(
            f"{cls_name}.{attr_name} est déclaré `merge=\"add\"` et vaut "
            f"{depart!r} par défaut. Un total part de zéro : le magasin "
            f"compte à partir de 0 quand la ligne n'existe pas encore, "
            f"donc un autre défaut se perdrait au premier incrément. Mets "
            f"0, ou retire `merge` si cette valeur est un point de départ "
            f"et non un total."
        )


def _body_annotations(namespace: dict[str, Any]) -> dict[str, Any]:
    """Les annotations du corps de classe, où que Python les ait rangées.

    Deux endroits, selon la version et selon le module :

    - ``__annotations__`` dans le namespace — sur Python 3.12/3.13, et
      partout où le module porte ``from __future__ import annotations`` ;
    - une FONCTION, ``__annotate_func__`` — sur Python 3.14 sans ce
      ``__future__``, où PEP 649 ne matérialise plus les annotations à la
      création de la classe.

    Ne lire que le premier ne levait pas : ça rendait un dict vide, donc
    une classe d'état **sans aucun champ**. Les lectures marchaient encore
    (des attributs ordinaires), rien n'était jamais persisté, et aucune
    erreur nulle part — l'action répondait 204 et l'écran ne bougeait pas.
    C'est ce qui obligeait toute app à écrire ``from __future__ import
    annotations`` en tête de chaque module déclarant un état, sous peine
    de panne muette. Cette fonction supprime l'exigence.

    ``Format.STRING`` rend du texte, exactement comme le ``__future__`` :
    l'étape 5 de la métaclasse résout tout en vrais types, et une
    référence avant ne doit surtout pas lever ici.
    """
    annotations = namespace.get("__annotations__")
    if annotations is not None:
        return annotations
    annotate = namespace.get("__annotate_func__")
    if annotate is None:
        return {}
    # Import local : ``annotationlib`` n'existe qu'à partir de 3.14, et on
    # n'arrive ici que sur 3.14 — ``__annotate_func__`` n'existe pas avant.
    import annotationlib

    return annotationlib.call_annotate_function(
        annotate, annotationlib.Format.STRING
    )


class _StateMeta(type):
    """Metaclass for :class:`State`.

    Responsibilities :

    1. **Refuser une déclaration nue.** ``count: int = 0`` lève, avec la
       phrase qui dit d'écrire ``field(default=0)``. Une seule forme :
       c'est le seul endroit où une option de champ peut se poser.
    2. **Laisser passer ce qui n'est pas un champ** : un nom préfixé
       ``_``, et une annotation ``ClassVar`` — qui est précisément la
       façon standard de dire « ceci n'est pas un champ d'instance ».
    3. **Aggregate validators and computed declarations.** Class-body
       declarations are merged with what the parents already exposed, so
       inheritance composes correctly.
    4. **Drop class-level kwargs.** ``class X(Base, scope="session")``
       passes ``scope="session"`` to the metaclass — we keep them out of
       :py:meth:`type.__new__` (which doesn't accept kwargs) and let
       ``__init_subclass__`` on concrete scopes consume them.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> _StateMeta:
        annotations: dict[str, Any] = _body_annotations(namespace)

        # ── 1. Pre-scan the body for already-declared decorators ────────
        body_validators: dict[str | None, list[Validator]] = {}
        body_computed: dict[str, ComputedProperty] = {}

        for attr_name, value in namespace.items():
            if isinstance(value, Validator):
                body_validators.setdefault(value.target, []).append(value)
            elif isinstance(value, ComputedProperty):
                body_computed[attr_name] = value

        # ── 2. Wrap plain defaults as Fields ───────────────────────────
        for attr_name, ann_type in annotations.items():
            if attr_name.startswith("_"):
                continue  # private — leave alone

            existing = namespace.get(attr_name, _NOT_PROVIDED)

            if isinstance(existing, Field):
                # Capture the annotation but don't replace the descriptor.
                if existing.type_ is None:
                    existing.type_ = ann_type
                # ── Ce que le champ PARENT disait de lui ────────────
                #
                # Redéclarer un champ pour en changer le DÉFAUT ne doit
                # pas lui faire perdre ce qu'il est par ailleurs. Le cas
                # mesuré (2026-08-29) : ``DatatableState.sort_key`` porte
                # ``url="tri"``, une app la redéclare pour trier par nom
                # au départ — et son URL cessait silencieusement de
                # porter le tri. Une surcharge de valeur n'est pas une
                # renonciation au vocabulaire.
                if existing.url is None:
                    for base in bases:
                        parent = getattr(base, attr_name, None)
                        if isinstance(parent, Field) and parent.url:
                            existing.url = parent.url
                            break
                continue
            if isinstance(existing, ComputedProperty | Validator):
                # Decorated declarations are already first-class descriptors.
                continue

            if _is_class_var(ann_type):
                # Une constante de classe n'est PAS un champ, et le dire
                # est le rôle de ``ClassVar``. Avant ce test, elle était
                # promue comme les autres : persistée, diffée, et envoyée
                # au navigateur sur un ``ClientState``.
                continue

            _refuse_a_bare_declaration(name, attr_name, existing)

        # ── 3. Build the class. Forward kwargs to ``type.__new__`` so
        # they propagate to ``__init_subclass__`` of the parent chain
        # (PEP 487). ``type.__new__`` itself ignores unknown kwargs.
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # ── 4. Merge inherited registries with what the body added ─────
        merged_validators: dict[str | None, list[Validator]] = {}
        merged_computed: dict[str, ComputedProperty] = {}

        # Walk MRO in reverse so deeper bases lose to shallower overrides.
        for base in reversed(cls.__mro__[1:]):  # skip cls itself
            for target, vlist in getattr(base, "__validators__", {}).items():
                merged_validators.setdefault(target, []).extend(vlist)
            merged_computed.update(getattr(base, "__computed__", {}))

        for target, vlist in body_validators.items():
            merged_validators.setdefault(target, []).extend(vlist)
        merged_computed.update(body_computed)

        cls.__validators__ = merged_validators
        cls.__computed__ = merged_computed

        # ── 5. Resolve string annotations into real types ──────────────
        # ``from __future__ import annotations`` (PEP 563) and PEP 649
        # both make annotations show up as strings on the class. Resolve
        # them once so descriptors carry the actual ``type`` object.
        try:
            resolved = typing.get_type_hints(cls)
        except (NameError, TypeError):
            # Forward references that can't be resolved at definition time
            # leave the descriptor's ``type_`` as the unresolved string.
            resolved = {}

        for attr_name, attr in vars(cls).items():
            if not isinstance(attr, Field):
                continue
            if attr_name in resolved:
                attr.type_ = resolved[attr_name]
            if attr.merge == "add":
                _refuse_an_impossible_sum(name, attr_name, attr)
            # HORS du `if` : tout champ doit pouvoir arriver au magasin,
            # additif ou non. Ce contrôle a vécu dedans le temps d'une
            # écriture, où il ne voyait que les compteurs — c'est-à-dire
            # les seuls champs dont le type était DÉJÀ garanti numérique.
            _refuse_an_unstorable_type(name, attr_name, attr)

        return cls

    def __init__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        # Forward kwargs to ``type.__init__`` so they reach
        # ``__init_subclass__`` of the parent chain. ``type.__init__`` in
        # CPython 3.6+ tolerates extra keyword arguments (PEP 487) and
        # routes them to ``__init_subclass__``.
        super().__init__(name, bases, namespace, **kwargs)

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Intercept ``MyState(...)`` to consult the active registry.

        Inside a request scope, the registry caches one instance per
        ``(class, key)`` pair so multiple ``MyState()`` calls return the
        same object. Outside a registry scope (tests, scripts), this
        falls through to a vanilla constructor.

        We import :func:`current_registry` lazily — ``registry.py``
        imports from this module too, and the cycle would otherwise
        explode at module load.
        """
        from bretzel.state.registry import current_registry

        registry = current_registry()
        if registry is None:
            return super().__call__(*args, **kwargs)

        key = kwargs.get("key", "default")
        cached = registry.get_cached(cls, key)
        if cached is not None:
            return cached

        # ServerState : hydrate from the backend, whatever it is. Le
        # backend mémoire se lit directement (``load_sync``) ; un
        # backend qui ne lit qu'en ``await`` (Redis) est atteint par le
        # pont thread → boucle du registre. ``None`` ici veut donc dire
        # « rien de stocké », plus « pas hydratable » : on tombe alors
        # sur les valeurs par défaut, ce qui est la bonne réponse.
        #
        # ⚠️ Depuis un corps d'app ``async def`` — donc sur la boucle,
        # où le pont ne peut pas attendre — ``try_sync_resolve`` LÈVE
        # au lieu de rendre des défauts que le commit écraserait
        # ensuite. Le geste à écrire là-bas est ``await MonEtat.load()``.
        from bretzel.state.scopes.client import ClientState
        from bretzel.state.scopes.server import ServerState

        if issubclass(cls, ServerState):
            hydrated = registry.try_sync_resolve(cls, key)
            if hydrated is not None:
                return hydrated

        instance = super().__call__(*args, **kwargs)
        registry.register(instance, key)

        # ClientState picks up inbound client-side values automatically
        # so handlers see what the browser most-recently sent.
        if isinstance(instance, ClientState):
            registry.hydrate_client(instance)

        return instance


# ───────────────────────────────────────────────────────────────────────────
# Abstract State
# ───────────────────────────────────────────────────────────────────────────


class State(metaclass=_StateMeta):
    """Abstract parent of all typed-state classes.

    Concrete scopes live in :mod:`bretzel.state.scopes`. Direct
    instantiation of :class:`State` is allowed for tests but yields no
    persistence behaviour — registry resolution and backend save / load
    are scope-specific.
    """

    # Class-level registries populated by the metaclass. Declared here so
    # both static checkers and runtime introspection see them on every
    # subclass even if it has no validators / computed of its own.
    __validators__: ClassVar[dict[str | None, list[Validator]]] = {}
    __computed__: ClassVar[dict[str, ComputedProperty]] = {}

    def __init__(self, *, key: str = "default") -> None:
        self._key: str = key
        self._dirty: bool = False

    # ── Introspection helpers ────────────────────────────────────────────

    @classmethod
    def _all_fields(cls) -> dict[str, Field]:
        """Walk the MRO and collect every :class:`Field` descriptor.

        Cached on the class on first call. Layers above (registry,
        client_bridge) iterate over this to drive serialization.
        """
        cached = cls.__dict__.get("__bz_field_cache__")
        if cached is not None:
            return cached  # type: ignore[no-any-return]

        result: dict[str, Field] = {}
        for klass in reversed(cls.__mro__):
            for attr_name, attr in klass.__dict__.items():
                if isinstance(attr, Field):
                    result[attr_name] = attr

        # Stash on the class itself (not on a parent's dict).
        type.__setattr__(cls, "__bz_field_cache__", result)
        return result

    def _iter_field_names(self) -> Iterator[str]:
        """Yield every field name declared on this instance's class."""
        yield from type(self)._all_fields().keys()

    def _field_values(self) -> dict[str, Any]:
        """Effective value of every declared field — its default when unset —
        read straight from storage WITHOUT materialising ``default_factory``
        into ``__dict__``.

        This is the snapshot surface the registry diffs to detect mutations,
        including in-place ones (``state.items.append(...)``) that never go
        through :meth:`~bretzel.state.fields.descriptor.Field.__set__`.
        Reading from storage (not ``getattr``) keeps it side-effect-free ;
        falling back to the field default means a lazily-read default never
        looks like a change. Required fields with no value and no default are
        omitted (they appear in the map iff explicitly set).
        """
        out: dict[str, Any] = {}
        for name, fld in type(self)._all_fields().items():
            storage_key = fld._storage_key
            if storage_key in self.__dict__:
                out[name] = self.__dict__[storage_key]
            elif fld.default_factory is not None:
                out[name] = fld.default_factory()
            elif fld.default is not MISSING:
                out[name] = fld.default
        return out

    # ── Form-validation errors ───────────────────────────────────────────

    @property
    def errors(self) -> dict[str, str]:
        """Field-name → message map of validation errors.

        Populated when this state is hydrated from a form submission by
        the action dispatcher's ``def handler(form: MyState)`` path : each
        validator that rejects a submitted value lands its message here
        (the assignment itself is rolled back, so the field keeps its
        prior value). Empty when the submission was valid or the state
        wasn't form-hydrated.

        The handler checks it and decides what to do ; the form zone
        declares ``deps=[MyForm]`` so it re-renders automatically once a
        validator writes here — no manual call ::

            def save(form: MyForm) -> None:
                if form.errors:
                    return               # zone re-renders : form_fields show messages
                ...                      # valid : proceed

        A ``form_field`` displays a field's message via
        ``error=form.errors.get("<field>")``. ``"_"``-prefixed key holds
        whole-form (cross-field) errors.
        """
        return self.__dict__.get("_bz_errors", {})

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly snapshot of the instance.

        Only fields with **explicitly stored** values are included — the
        defaults are recoverable by the receiving end via
        le registre. Computed properties are excluded ; they are
        derived, not state.
        """
        result: dict[str, Any] = {}
        for name, field in type(self)._all_fields().items():
            if field.has_value(self):
                value = self.__dict__.get(field._storage_key, MISSING)
                if value is MISSING:
                    continue
                result[name] = value
        return result

    def _apply_fields(self, data: dict[str, Any]) -> None:
        """Overwrite every declared field present in ``data`` on this instance.

        Unknown keys are silently ignored — letting an old persisted payload
        survive a removed field. Each assignment goes through
        ``Field.__set__`` (coercion + validators). The single source for the
        "hydrate from a dict" loop, partagé par les chemins de résolution
        du registre et celui du magasin client ; l'appelant fait ensuite
        sa propre remise à zéro de ``_dirty`` et son inscription.

        C'est le point d'entrée interne unique pour hydrater une instance
        existante depuis un dictionnaire.
        """
        fields = type(self)._all_fields()
        for name, value in data.items():
            if name in fields:
                setattr(self, name, value)

    # ── Equality / repr ──────────────────────────────────────────────────

    def __repr__(self) -> str:
        body = ", ".join(f"{n}={getattr(self, n)!r}" for n in self._iter_field_names())
        return f"{type(self).__name__}(key={self._key!r}, {body})"

"""Unit tests for ``bretzel.state.base`` — metaclass + abstract State."""

from __future__ import annotations

import pytest

from bretzel.state.base import State
from bretzel.state.fields.computed import ComputedProperty, computed
from bretzel.state.fields.descriptor import Field, field
from bretzel.state.fields.validator import Validator, validator

# ───────────────────────────────────────────────────────────────────────────
# Metaclass — annotation wrapping
# ───────────────────────────────────────────────────────────────────────────


class TestAnnotationWrapping:
    def test_plain_default_becomes_field(self) -> None:
        class S(State):
            count: int = field(default=0)
            name: str = field(default='alice')

        assert isinstance(S.__dict__["count"], Field)
        assert isinstance(S.__dict__["name"], Field)
        assert S.__dict__["count"].default == 0
        assert S.__dict__["count"].type_ is int

    def test_no_default_becomes_required_field(self) -> None:
        class S(State):
            name: str = field()

        assert isinstance(S.__dict__["name"], Field)
        # No default → reading without setting raises.
        s = S()
        with pytest.raises(AttributeError):
            _ = s.name

    def test_explicit_field_preserved(self) -> None:
        class S(State):
            items: list[int] = field(default_factory=list)

        descriptor = S.__dict__["items"]
        assert isinstance(descriptor, Field)
        assert descriptor.default_factory is list
        # Annotation captured even when the user wrote field(...).
        assert descriptor.type_ == list[int]

    def test_mutable_default_rejected(self) -> None:
        # Le refus vit dans ``field()`` depuis que tout champ y passe :
        # il n'y a plus de chemin « défaut nu » où le poser.
        with pytest.raises(ValueError, match="default_factory=list"):
            field(default=[])

    def test_underscore_attr_not_wrapped(self) -> None:
        class S(State):
            _internal: int = 0

        # Private annotations are not converted to Field.
        assert "_internal" in vars(S)
        assert not isinstance(S.__dict__["_internal"], Field)


# ───────────────────────────────────────────────────────────────────────────
# Metaclass — collection of validators / computed
# ───────────────────────────────────────────────────────────────────────────


class TestRegistries:
    def test_validators_collected_by_target(self) -> None:
        class S(State):
            x: int = field(default=0)

            @validator("x")
            def check(self, v: int) -> int:
                return max(v, 0)

        assert "x" in S.__validators__
        assert isinstance(S.__validators__["x"][0], Validator)

    def test_whole_instance_validator_keyed_by_none(self) -> None:
        class S(State):
            x: int = field(default=0)

            @validator
            def invariant(self) -> None:
                pass

        assert None in S.__validators__
        assert isinstance(S.__validators__[None][0], Validator)

    def test_computed_collected_by_name(self) -> None:
        class S(State):
            x: int = field(default=0)

            @computed
            def doubled(self) -> int:
                return self.x * 2

        assert "doubled" in S.__computed__
        assert isinstance(S.__computed__["doubled"], ComputedProperty)

    def test_inheritance_merges_registries(self) -> None:
        class Parent(State):
            x: int = field(default=0)

            @validator("x")
            def parent_check(self, v: int) -> int:
                return v

            @computed
            def parent_calc(self) -> int:
                return self.x

        class Child(Parent):
            y: int = field(default=0)

            @validator("y")
            def child_check(self, v: int) -> int:
                return v

            @computed
            def child_calc(self) -> int:
                return self.y

        assert "x" in Child.__validators__
        assert "y" in Child.__validators__
        assert "parent_calc" in Child.__computed__
        assert "child_calc" in Child.__computed__


# ───────────────────────────────────────────────────────────────────────────
# Class kwargs — propagated to __init_subclass__ via PEP 487
# ───────────────────────────────────────────────────────────────────────────


class TestClassKwargs:
    def test_kwargs_reach_init_subclass(self) -> None:
        # Concrete scopes consume kwargs like ``scope=`` / ``persist=`` via
        # their own ``__init_subclass__``. The metaclass must forward them
        # so they reach that hook (PEP 487).
        seen: dict[str, object] = {}

        class Captures(State):
            def __init_subclass__(cls, *, marker: str = "", **kwargs: object) -> None:
                super().__init_subclass__(**kwargs)
                seen["marker"] = marker

        class S(Captures, marker="hello"):
            x: int = field(default=0)

        assert seen["marker"] == "hello"
        # Field machinery still works alongside the kwarg flow.
        assert isinstance(S.__dict__["x"], Field)


# ───────────────────────────────────────────────────────────────────────────
# Instance behaviour
# ───────────────────────────────────────────────────────────────────────────


class TestInstance:
    def test_default_key(self) -> None:
        class S(State):
            x: int = field(default=0)

        s = S()
        assert s._key == "default"

    def test_custom_key(self) -> None:
        class S(State):
            x: int = field(default=0)

        s = S(key="basket")
        assert s._key == "basket"

    def test_dirty_starts_false(self) -> None:
        class S(State):
            x: int = field(default=0)

        assert S()._dirty is False

    def test_dirty_after_set(self) -> None:
        class S(State):
            x: int = field(default=0)

        s = S()
        s.x = 1
        assert s._dirty is True

    def test_field_storage_isolated_between_instances(self) -> None:
        class S(State):
            x: int = field(default=0)

        a, b = S(), S()
        a.x = 99
        assert b.x == 0


# ───────────────────────────────────────────────────────────────────────────
# Field discovery + serialisation
# ───────────────────────────────────────────────────────────────────────────


class TestFieldDiscovery:
    def test_all_fields_walks_mro(self) -> None:
        class P(State):
            x: int = field(default=0)

        class C(P):
            y: int = field(default=0)

        names = list(C._all_fields().keys())
        assert "x" in names
        assert "y" in names

    def test_field_cache_per_class(self) -> None:
        class P(State):
            x: int = field(default=0)

        class C(P):
            y: int = field(default=0)

        # First call populates the cache on C, not on P.
        C._all_fields()
        assert "__bz_field_cache__" in C.__dict__
        # Cache is recomputed fresh per class.
        assert set(C.__dict__["__bz_field_cache__"].keys()) == {"x", "y"}


class TestSerialisation:
    def test_to_dict_includes_only_set_values(self) -> None:
        class S(State):
            x: int = field(default=0)
            y: int = field(default=0)

        s = S()
        s.x = 5
        # Only `x` was explicitly set ; defaults stay implicit.
        assert s.to_dict() == {"x": 5}

    def test_to_dict_includes_factory_materialised(self) -> None:
        class S(State):
            items: list[int] = field(default_factory=list)

        s = S()
        # Touching `items` materialises the factory default → snapshot includes it.
        s.items.append(1)
        assert s.to_dict() == {"items": [1]}

    def test_hydrating_from_a_dict_restores_state(self) -> None:
        """``_apply_fields`` — le seul point d'entrée depuis le 2026-09-06.

        ``State.from_dict`` faisait ces trois pas et a été SUPPRIMÉE :
        elle construisait par ``cls(key=key)``, que la métaclasse
        intercepte, donc elle rendait l'instance cachée de la requête et
        l'écrasait au lieu d'en fabriquer une neuve.
        """
        class S(State):
            x: int = field(default=0)
            y: str = field(default='')

        s = S(key="default")
        s._apply_fields({"x": 5, "y": "hello"})
        s._dirty = False  # hydrater n'est pas une mutation d'utilisateur
        assert s.x == 5
        assert s.y == "hello"
        assert s._dirty is False

    def test_hydrating_ignores_unknown_keys(self) -> None:
        """Un ancien payload survit au retrait d'un champ."""
        class S(State):
            x: int = field(default=0)

        s = S(key="default")
        s._apply_fields({"x": 1, "removed_field": "ignored"})
        assert s.x == 1

    def test_a_state_carries_the_key_it_was_built_with(self) -> None:
        class S(State):
            x: int = field(default=0)

        assert S(key="basket")._key == "basket"

    def test_apply_fields_sets_known_ignores_unknown(self) -> None:
        # The single hydrate-from-dict loop shared by from_dict + the
        # registry's resolve / client-payload paths.
        class S(State):
            x: int = field(default=0)
            y: str = field(default='')

        s = S()
        s._apply_fields({"x": 7, "y": "hi", "gone": "ignored"})
        assert (s.x, s.y) == (7, "hi")
        assert not hasattr(s, "gone")


# ───────────────────────────────────────────────────────────────────────────
# Repr
# ───────────────────────────────────────────────────────────────────────────


class TestRepr:
    def test_repr_includes_fields(self) -> None:
        class S(State):
            x: int = field(default=0)

        s = S(key="basket")
        s.x = 5
        out = repr(s)
        assert "S(" in out
        assert "key='basket'" in out
        assert "x=5" in out

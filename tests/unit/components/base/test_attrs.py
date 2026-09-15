"""Unit tests for ``bretzel.components.base.attrs``."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import (
    ComponentUsageError,
    is_passthrough_attr,
    normalize_attr_name,
    split_kwargs,
)

# ───────────────────────────────────────────────────────────────────────────
# normalize_attr_name
# ───────────────────────────────────────────────────────────────────────────


class TestNormalize:
    @pytest.mark.parametrize(
        ("py", "expected"),
        [
            ("aria_label", "aria-label"),
            ("data_testid", "data-testid"),
            ("role", "role"),
            ("class_", "class"),
            ("for_", "for"),
            ("aria-label", "aria-label"),  # already dashed
            (":disabled", ":disabled"),  # raw alpine — passthrough
            ("@click", "@click"),
            ("hx-get", "hx-get"),
        ],
    )
    def test_cases(self, py: str, expected: str) -> None:
        assert normalize_attr_name(py) == expected


class TestHtmxPassthrough:
    """``hx-*`` passe verbatim. Les préfixes Alpine, eux, sont REFUSÉS —
    cf. :class:`TestDeadAlpinePrefixes`."""

    @pytest.mark.parametrize("name", ["hx-get", "hx-target", "hx-post"])
    def test_recognised(self, name: str) -> None:
        assert is_passthrough_attr(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "color",
            "aria_label",
            "data_x",
            "id",
            # Ne sont PLUS du passthrough depuis le 2026-07-29 : Alpine est
            # sorti en V3, ces attributs partaient dans le DOM sans que rien
            # ne les lise. Ils lèvent maintenant (classe ci-dessous).
            ":disabled",
            "@click",
            "x-data",
        ],
    )
    def test_rejected(self, name: str) -> None:
        assert is_passthrough_attr(name) is False


class TestDeadAlpinePrefixes:
    """Le refus bruyant sur ``:`` / ``@`` / ``x-``.

    Le moteur de directives V3 ne scanne que ``bz-attr:`` et ``bz-on:``
    (``02_directives.js``). Un attribut Alpine était donc émis dans le DOM,
    valide, et jamais lu : zéro erreur, zéro warning, zéro effet.

    ⚠️ Retirer les préfixes de ``_PASSTHROUGH_PREFIXES`` ne suffisait PAS —
    ``normalize_attr_name`` rend tel quel tout nom contenant ``-``/``:``/``@``,
    donc le catch-all ``raw_html`` émettait le même attribut. C'est le refus
    qui est le fix.
    """

    @pytest.mark.parametrize(
        "name", [":disabled", ":class", "@click", "@mouseenter", "x-data", "x-show"]
    )
    def test_raises(self, name: str) -> None:
        cls = _stub_component_class()
        with pytest.raises(ComponentUsageError, match="Alpine"):
            split_kwargs(cls, {name: "whatever"})

    @pytest.mark.parametrize(
        ("name", "expected_hint"),
        [
            ("@click", "bz-on:click"),
            (":disabled", "bz-attr:disabled"),
            ("x-show", "bz-show"),
        ],
    )
    def test_message_points_at_the_bz_equivalent(self, name: str, expected_hint: str) -> None:
        """Un refus qui ne dit pas quoi écrire à la place est un mur."""
        cls = _stub_component_class()
        with pytest.raises(ComponentUsageError) as exc:
            split_kwargs(cls, {name: "whatever"})
        assert expected_hint in str(exc.value)

    @pytest.mark.parametrize("name", ["hx-get", "bz-show", "bz-on:click", "data-x"])
    def test_leaves_the_living_dialects_alone(self, name: str) -> None:
        cls = _stub_component_class()
        split_kwargs(cls, {name: "whatever"})  # ne lève pas


# ───────────────────────────────────────────────────────────────────────────
# split_kwargs
# ───────────────────────────────────────────────────────────────────────────


def _stub_component_class(
    *,
    reactive_props: tuple[str, ...] = (),
    events: tuple[str, ...] = (),
    slots: tuple[str, ...] = (),
) -> type:
    return type(
        "Stub",
        (),
        {
            "__reactive_props__": dict.fromkeys(reactive_props, object()),
            "EVENTS": events,
            "NAMED_SLOTS": slots,
        },
    )


class TestSplitKwargs:
    def test_buckets_correctly(self) -> None:
        cls = _stub_component_class(
            reactive_props=("color", "disabled"),
            events=("click",),
            slots=("icon",),
        )
        kwargs = {
            "color": "primary",
            "disabled": True,
            "icon": object(),
            "on_click": lambda: None,
            "aria_label": "save",
            # Le bucket passthrough ne porte plus que du ``hx-*`` : les
            # préfixes Alpine qui étaient ici (``:data-active``,
            # ``@mouseenter``) lèvent depuis le 2026-07-29.
            "hx-get": "/rows",
            "hx-target": "#list",
        }
        reactive, slots, events, passthrough, raw_html = split_kwargs(cls, kwargs)
        assert set(reactive) == {"color", "disabled"}
        assert set(slots) == {"icon"}
        assert set(events) == {"on_click"}
        assert set(passthrough) == {"hx-get", "hx-target"}
        # ``aria_label`` is normalised to ``aria-label`` in raw_html.
        assert "aria-label" in raw_html

    def test_unknown_event_raises(self) -> None:
        cls = _stub_component_class(events=("click",))
        with pytest.raises(ComponentUsageError, match="on_focus"):
            split_kwargs(cls, {"on_focus": lambda: None})

    def test_an_undeclared_raw_kwarg_is_refused(self) -> None:
        """Le cinquième seau refuse, comme les quatre autres.

        ⚠️ Ce test asseyait le contrat INVERSE jusqu'au 2026-08-16 :
        « ``foo=...`` is just an HTML attr », et il vérifiait que le kwarg
        atterrissait dans ``raw_html``. C'était exact, et c'était le
        problème — 44 kwargs morts mesurés sur ``examples/``, dont
        ``ui.input(label=…)`` sur 22 sites qui rendaient
        ``<input label="…">`` sans afficher de libellé.
        """
        cls = _stub_component_class(slots=("icon",))
        with pytest.raises(ComponentUsageError, match="foo"):
            split_kwargs(cls, {"foo": "bar"})

    def test_a_declared_raw_escape_still_passes(self) -> None:
        """Le refus ne ferme pas l'échappatoire, il la rend explicite."""
        cls = _stub_component_class(slots=("icon",))
        _, slots, _, _, raw_html = split_kwargs(
            cls, {"aria_label": "Fermer", "data_testid": "x", "role": "alert"}
        )
        assert raw_html == {
            "aria-label": "Fermer",
            "data-testid": "x",
            "role": "alert",
        }
        assert slots == {}

    def test_empty_kwargs(self) -> None:
        cls = _stub_component_class()
        result = split_kwargs(cls, {})
        assert all(b == {} for b in result)

    def test_does_not_mutate_input(self) -> None:
        cls = _stub_component_class(reactive_props=("color",))
        kwargs = {"color": "primary", "data_x": "y"}
        original = dict(kwargs)
        split_kwargs(cls, kwargs)
        assert kwargs == original

"""Unit tests for :class:`bretzel.components.layout.carousel.Carousel`."""

from __future__ import annotations

import pytest

from bretzel.components.base.attrs import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.layout.carousel import Carousel
from bretzel.components.primitives.text import Text
from bretzel.core.serialize import serialize
from bretzel.state.scopes.client import ClientBinding


# Module-level handler — encode_handler_id needs an addressable qualname.
def _change_handler() -> None:
    pass


def _build(*, slides: int = 5, **kwargs):
    with Carousel(**kwargs) as c:
        for i in range(slides):
            Text(f"slide {i}")
    return c


def _html(**kwargs) -> str:
    """Construire ET rendre dans le MÊME contexte : la construction d'un
    composant en a besoin autant que son render."""
    with render_isolated():
        return serialize(_build(**kwargs).render())


class TestStructure:
    def test_root_carries_the_shared_scope(self) -> None:
        out = _html()
        assert "$bz.carousel.scope" in out
        # Le bz-data ne porte QUE des données : les méthodes vivent une
        # seule fois dans le scope partagé.
        head = out.split("bz-data=")[1].split("bz-init=")[0]
        assert "goTo(" not in head
        assert "scrollTo" not in head

    def test_track_is_a_snap_container(self) -> None:
        out = _html()
        # Le moteur EST le CSS : sans ces trois classes il n'y a ni
        # défilement ni aimantation, et le runtime n'y peut rien.
        assert "overflow-x-auto" in out
        assert "snap-x" in out
        assert "snap-mandatory" in out
        assert out.count("snap-start") == 5

    def test_every_child_becomes_a_slide(self) -> None:
        out = _html(slides=3)
        assert out.count("snap-start") == 3
        for i in range(3):
            assert f"slide {i}" in out

    def test_track_is_captured_for_the_scope(self) -> None:
        out = _html()
        # Une méthode de scope n'a pas ``$refs`` — la capture doit se
        # faire en contexte de directive, sinon toute la géométrie est
        # aveugle.
        assert 'bz-ref="bztrack"' in out
        assert "_track = $refs.bztrack" in out

    def test_arrows_are_anchored_on_the_viewport_not_the_root(self) -> None:
        out = _html(slides=5)
        # Régression : les flèches étaient posées sur la ROOT, dont la
        # hauteur comprend la rangée de puces — leur ``top-1/2`` tombait
        # donc 10 px sous le centre visuel de la piste (mesuré). Elles
        # doivent vivre dans le conteneur ``relative`` qui n'enveloppe
        # QUE la piste.
        viewport = out.split('aria-label="Previous slide"')[0]
        assert viewport.rindex('class="relative"') > viewport.rindex(
            "bz-data="
        ), "la flèche doit être précédée du viewport, pas de la root"
        # Et la root n'est plus positionnée : plus rien ne s'y ancre.
        head = out[: out.index("<div", 1)]
        assert "relative" not in head

    def test_track_hides_its_scrollbar_via_the_css_hook(self) -> None:
        out = _html()
        # ``bz-no-scrollbar`` est un hook du CSS framework. La variante
        # Tailwind arbitraire équivalente NE COMPILE PAS — mesuré :
        # ``scrollbar-width`` calculait « thin » (le ``*`` global du
        # thème) au lieu de « none ». Même choix que Sidebar avec
        # ``bz-rail-scroll``, dont le commentaire dit déjà « CSS hook
        # (not a Tailwind utility) ».
        assert "bz-no-scrollbar" in out
        assert "scrollbar-width:none" not in out
        assert "webkit-scrollbar" not in out

    def test_scroll_listener_carries_no_modifier(self) -> None:
        out = _html()
        # ``bz-on:`` passe son suffixe VERBATIM à ``addEventListener`` :
        # un ``.passive`` écouterait un événement nommé « scroll.passive »
        # et le pont position→état serait mort en silence. Payé ici même
        # (cf. traps.md § « bz-on: n'a AUCUN modificateur »).
        assert 'bz-on:scroll="' in out
        assert "bz-on:scroll." not in out


class TestDerivedControls:
    def test_arrows_appear_when_there_is_somewhere_to_go(self) -> None:
        out = _html(slides=4)
        assert 'aria-label="Previous slide"' in out
        assert 'aria-label="Next slide"' in out

    def test_no_controls_for_a_single_slide(self) -> None:
        out = _html(slides=1)
        assert "Previous slide" not in out
        assert "Go to slide" not in out

    def test_no_controls_when_everything_fits(self) -> None:
        # 3 slides visibles sur 3 : rien à faire défiler.
        out = _html(slides=3, per_view=3)
        assert "Previous slide" not in out
        assert "Go to slide" not in out

    def test_arrows_disable_from_the_real_geometry(self) -> None:
        out = _html(slides=5)
        # Les bornes viennent du navigateur, PAS d'un calcul de
        # per_view — c'est ce qui rend le responsive gratuit.
        assert 'bz-attr:disabled="_atStart()"' in out
        assert 'bz-attr:disabled="_atEnd()"' in out

    def test_dots_only_when_per_view_is_one(self) -> None:
        assert "Go to slide 1" in _html(slides=6, per_view=1)
        # Une puce dit « il y a N slides, tu es à la k-ième » : avec 3
        # visibles sur 6, elle n'a plus de référent.
        assert "Go to slide 1" not in _html(slides=6, per_view=3)

    def test_dots_hide_at_breakpoints_where_per_view_grows(self) -> None:
        out = _html(slides=6, per_view={"base": 1, "md": 3})
        assert "Go to slide 1" in out
        # La décision reste en CSS : le serveur ne sait pas quel
        # breakpoint est actif.
        assert "md:hidden" in out

    def test_active_dot_is_ssr_rendered(self) -> None:
        out = _html(slides=4, value=2)
        # Anti-flash : la puce active est juste au premier paint.
        assert 'data-selected="true"' in out
        assert 'bz-attr:data-selected' in out


class TestPerView:
    @pytest.mark.parametrize(
        "per_view,expected",
        [(1, "basis-full"), (2, "basis-1/2"), (3, "basis-1/3"),
         (4, "basis-1/4")],
    )
    def test_per_view_sets_the_slide_width(self, per_view, expected) -> None:
        assert expected in _html(per_view=per_view)

    def test_responsive_per_view_prefixes_every_breakpoint(self) -> None:
        out = _html(per_view={"base": 1, "md": 3})
        assert "basis-full" in out
        assert "md:basis-1/3" in out

    @pytest.mark.parametrize("base_key", ["base", "xs", "default", ""])
    def test_every_base_key_spelling_decides_the_dots(
        self, base_key: str
    ) -> None:
        """Régression : les quatre orthographes de « pas de préfixe » que
        ``responsive_classes`` accepte doivent TOUTES décider des puces.

        La liste avait été recopiée à la main et avait dérivé dans les
        deux sens — un ``DEFAULT`` majuscule inventé, un ``default``
        oublié. Conséquence mesurée : ``per_view={"default": 3}`` rendait
        une puce par slide en en montrant trois, l'état exact que la
        docstring du module déclare impossible.
        """
        assert "Go to slide 1" not in _html(
            slides=6, per_view={base_key: 3, "lg": 4}
        ), (
            f"per_view={{{base_key!r}: 3}} montre 3 slides — aucune puce "
            f"ne doit être rendue"
        )
        # L'autre versant : à 1 en base, les puces existent, et SEUL le
        # vrai breakpoint doit gagner un ``:hidden``. Lu sur la classe de
        # la rangée de puces, pas sur tout le HTML — le masquage de la
        # scrollbar y porte lui aussi un ``:hidden``.
        out = _html(slides=6, per_view={base_key: 1, "lg": 3})
        dots_class = out.split('aria-label="Choose slide"')[0]
        dots_class = dots_class[dots_class.rindex('class="'):]
        assert "lg:hidden" in dots_class
        assert f"{base_key}:hidden" not in dots_class or base_key == ""

    def test_string_per_view_is_a_verbatim_escape_hatch(self) -> None:
        assert "basis-[200px]" in _html(per_view="basis-[200px]")

    def test_unknown_breakpoint_raises(self) -> None:
        with render_isolated(), pytest.raises(ComponentUsageError):
            _build(per_view={"phablet": 2}).render()

    def test_a_dict_on_a_non_graded_prop_raises(self) -> None:
        # Sans cette garde, le dict meurt plus loin sur « unhashable
        # type: 'dict' », qui ne dit rien de l'erreur réelle.
        with render_isolated(), pytest.raises(ComponentUsageError):
            Carousel(gap={"base": "sm"})


class TestAutoplay:
    def test_no_autoplay_no_timer_and_no_flag(self) -> None:
        out = _html()
        assert "$bz._tick" not in out
        # Pas d'autoplay = pas de drapeau d'arrêt à porter.
        assert "still" not in out

    def test_autoplay_reuses_the_interval_timer(self) -> None:
        out = _html(autoplay=5)
        # Le timer de ``ui.interval``, idempotent aux morphs : l'autoplay
        # n'ajoute AUCUN timer au runtime.
        assert "$bz._tick($el, !still, 5000)" in out
        assert 'bz-on:tick="next()"' in out

    def test_autoplay_seconds_become_milliseconds(self) -> None:
        assert "$bz._tick($el, !still, 1500)" in _html(autoplay=1.5)

    def test_still_is_a_declared_signal(self) -> None:
        out = _html(autoplay=2)
        # Un champ posé à la volée ne relancerait jamais l'effet, donc la
        # rotation ne s'arrêterait jamais.
        assert "still: false," in out.split("bz-data=")[1]

    def test_every_gesture_stops_the_rotation(self) -> None:
        out = _html(autoplay=2)
        # Sans modificateur, ici aussi — cf.
        # ``test_scroll_listener_carries_no_modifier``.
        assert "bz-on:pointerdown" in out
        assert "bz-on:wheel" in out
        assert out.count("_touch()") >= 3   # piste + les deux flèches


class TestValueModes:
    def test_literal_value_has_no_server_sync(self) -> None:
        assert "_serverSync" not in _html(value=1)

    def test_binding_mode_has_no_local_signal(self) -> None:
        binding = ClientBinding(class_name="Gal", instance_key="default",
                                field_name="slide", value=0)
        out = _html(value=binding)
        assert "value:" not in out
        assert "get current()" not in out
        assert "$bz.state.Gal.default.slide" in out

    def test_string_value_is_coerced(self) -> None:
        assert "value: 2," in _html(value="2")

    def test_garbage_value_falls_back_to_zero(self) -> None:
        assert "value: 0," in _html(value="nope")

    def test_binding_on_a_non_bindable_prop_raises(self) -> None:
        binding = ClientBinding(class_name="Gal", instance_key="default",
                                field_name="n", value=2)
        with render_isolated(), pytest.raises(ComponentUsageError):
            Carousel(per_view=binding)


class TestFormIntegration:
    def test_no_name_no_hidden_input(self) -> None:
        assert 'type="hidden"' not in _html()

    def test_explicit_name_emits_the_carrier(self) -> None:
        out = _html(value=2, name="slide")
        assert 'type="hidden"' in out
        assert 'name="slide"' in out
        assert 'value="2"' in out

    def test_change_handler_is_relocated_onto_the_input(self) -> None:
        out = _html(on_change=_change_handler)
        assert 'type="hidden"' in out
        assert "hx-post" not in out.split("<input")[0]
        assert "hx-post" in out.split("<input")[1]


class TestImperative:
    def test_root_carries_the_three_receivers(self) -> None:
        out = _html()
        assert 'bz-on:bz-set="goTo($event.detail.value)"' in out
        assert 'bz-on:bz-next="next()"' in out
        assert 'bz-on:bz-prev="prev()"' in out

    def test_methods_return_client_expression_strings(self) -> None:
        with render_isolated():
            gal = _build()
            assert isinstance(gal.next(), str)
            assert isinstance(gal.prev(), str)
            assert isinstance(gal.set(2), str)

    def test_set_writes_through_the_binding(self) -> None:
        binding = ClientBinding(class_name="Gal", instance_key="default",
                                field_name="slide", value=0)
        with render_isolated():
            assert "$bz.state.Gal.default.slide" in _build(
                value=binding
            ).set(2)

    def test_next_dispatches_even_with_a_binding(self) -> None:
        # La destination dépend de la géométrie VIVANTE (combien de
        # slides tiennent à l'écran au breakpoint courant), que le
        # serveur ne connaît pas au rendu.
        binding = ClientBinding(class_name="Gal", instance_key="default",
                                field_name="slide", value=0)
        with render_isolated():
            gal = _build(value=binding)
            assert "bz-next" in gal.next()
            assert "bz-prev" in gal.prev()

    def test_imperative_forces_identity(self) -> None:
        assert "bz-id=" in _html()


class TestAxes:
    @pytest.mark.parametrize(
        "left,right",
        [("xs", "sm"), ("sm", "md"), ("md", "lg"), ("lg", "xl")],
    )
    def test_sizes_are_distinct(self, left: str, right: str) -> None:
        assert _html(size=left) != _html(size=right)

    @pytest.mark.parametrize("color", ["primary", "success", "error"])
    def test_color_reaches_the_active_dot(self, color: str) -> None:
        assert "data-[selected=true]:bg-(--bz-solid)" in _html(color=color)
        assert f"bz-c-{color}" in _html(color=color)

    @pytest.mark.parametrize(
        "gap,expected",
        [("none", "gap-0"), ("sm", "gap-2"), ("md", "gap-4"),
         ("xl", "gap-8")],
    )
    def test_gap_reaches_the_track(self, gap: str, expected: str) -> None:
        assert expected in _html(gap=gap)


class TestA11y:
    def test_root_announces_the_carousel(self) -> None:
        out = _html()
        # Sur la ROOT et pas sur la piste : c'est elle qui contient
        # AUSSI les contrôles.
        head = out[: out.index("<div", 1)]
        assert 'role="group"' in head
        assert 'aria-roledescription="carousel"' in head

    def test_dots_do_not_fake_a_tablist(self) -> None:
        # Déclarer la moitié du motif ARIA « carousel à onglets »
        # annoncerait une structure qui n'existe pas.
        out = _html(slides=4)
        assert 'role="tablist"' not in out
        assert 'role="tab"' not in out

    def test_controls_are_real_buttons(self) -> None:
        out = _html(slides=4)
        assert out.count('type="button"') == 2 + 4   # flèches + puces


class TestEmpty:
    def test_no_slides_renders_an_empty_track(self) -> None:
        out = _html(slides=0)
        assert "snap-start" not in out
        assert "Previous slide" not in out

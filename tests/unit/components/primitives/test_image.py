"""``Image`` — la racine EST l'``<img>``, et ``alt`` n'est pas négociable.

Ce qui est figé ici, c'est le **contrat**, pas la chaîne de classes : un
test qui épingle `"block max-w-full bg-muted/30"` rougirait sur un
refactor correct du thème.
"""

from __future__ import annotations

import pytest

from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.image.image import Image
from bretzel.components.primitives.image.theme import IMAGE_THEME
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class ImgState(ClientState, persist="memory"):
    """Un état client, pour fabriquer de vraies ``ClientBinding``."""

    value: str = field(default="/x.png")


def render(**kwargs) -> str:
    with render_isolated():
        return serialize(Image(**kwargs).render())


class TestRootShape:
    def test_root_is_the_img_itself(self) -> None:
        """Pas de wrapper. C'est LE choix de design : sans lui, la boîte
        de chargement demanderait un second élément."""
        out = render(src="/a.png", alt="A")
        assert out.startswith("<img ")
        assert "<div" not in out

    def test_src_and_alt_reach_the_attributes(self) -> None:
        out = render(src="/photo.jpg", alt="Un chat")
        assert 'src="/photo.jpg"' in out
        assert 'alt="Un chat"' in out

    def test_lazy_and_async_by_default(self) -> None:
        out = render(src="/a.png", alt="A")
        assert 'loading="lazy"' in out
        assert 'decoding="async"' in out

    def test_attrs_override_the_defaults(self) -> None:
        """Le cas réel est l'image d'en-tête, que le lazy retarde au
        détriment du LCP — l'échappatoire doit gagner."""
        out = render(src="/hero.jpg", alt="Héros",
                     attrs={"loading": "eager"})
        assert 'loading="eager"' in out
        assert 'loading="lazy"' not in out


class TestAltIsMandatory:
    def test_missing_alt_raises_at_call_time(self) -> None:
        """Le seul kwarg d'a11y obligatoire du dépôt. Un alt manquant ne
        se voit ni à l'écran ni dans un HTML relu en diagonale."""
        with pytest.raises(TypeError):
            Image("/a.png")  # type: ignore[call-arg]

    def test_empty_alt_is_allowed_and_emitted(self) -> None:
        """``alt=""`` fait IGNORER l'image par le lecteur d'écran ;
        omettre l'attribut lui fait annoncer l'URL. Les deux ne sont pas
        équivalents, donc l'attribut vide doit être ÉMIS."""
        out = render(src="/deco.png", alt="")
        assert 'alt=""' in out

    def test_alt_is_escaped(self) -> None:
        out = render(src="/a.png", alt="<script>alert(1)</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out


class TestRatioAndFit:
    @pytest.mark.parametrize("ratio", ["square", "video", "portrait", "wide"])
    def test_each_ratio_emits_its_own_classes(self, ratio: str) -> None:
        out = render(src="/a.png", alt="A", ratio=ratio)
        for token in IMAGE_THEME["ratios"][ratio].split():
            assert token in out

    def test_ratios_are_pairwise_distinct(self) -> None:
        """Deux ``ratio=`` ne doivent pas rendre la même chose — sinon la
        prop ment. Même esprit que ``test_sizes_are_distinct``."""
        rendered = {
            r: render(src="/a.png", alt="A", ratio=r)
            for r in IMAGE_THEME["ratios"]
        }
        assert len(set(rendered.values())) == len(rendered)

    def test_no_ratio_emits_no_aspect_class(self) -> None:
        """Sans ratio, l'image garde sa taille naturelle."""
        out = render(src="/a.png", alt="A")
        assert "aspect-" not in out

    def test_fit_defaults_to_cover(self) -> None:
        assert "object-cover" in render(src="/a.png", alt="A")

    def test_fit_contain_replaces_cover(self) -> None:
        out = render(src="/a.png", alt="A", fit="contain")
        assert "object-contain" in out
        assert "object-cover" not in out


class TestTheFallbackIsTheBackground:
    def test_root_carries_a_background(self) -> None:
        """Le fond N'EST PAS décoratif : c'est à la fois le skeleton de
        chargement et le fallback d'URL cassée. S'il disparaît, les deux
        comportements disparaissent en silence — d'où ce test malgré la
        règle « fige le contrat, pas la chaîne »."""
        assert "bg-" in IMAGE_THEME["slots"]["root"]
        assert "bg-" in render(src="/a.png", alt="A")

    def test_a_broken_url_still_renders_the_box(self) -> None:
        """Rien de conditionnel côté serveur : la même boîte est émise
        quelle que soit l'URL. C'est ce qui rend le fallback gratuit."""
        good = render(src="/exists.png", alt="A", ratio="video")
        bad = render(src="/nope.png", alt="A", ratio="video")
        assert good.replace("/exists.png", "/nope.png") == bad


class TestNoBindableSurface:
    @pytest.mark.parametrize("prop", ["src", "alt", "ratio", "fit"])
    def test_binding_any_prop_raises(self, prop: str) -> None:
        """``BINDABLE_PROPS = ()`` — une image change au re-rendu serveur,
        pas sous un driver client. Le socle doit LEVER plutôt que de figer
        le SSR en silence."""
        from bretzel.components.base import ComponentUsageError

        with render_isolated(), rendering_scope():
            state = ImgState()
            kwargs: dict = {"src": "/a.png", "alt": "A"}
            kwargs[prop] = state.value
            with pytest.raises(ComponentUsageError, match="not bindable"):
                Image(**kwargs)


class TestEmptySrcIsNeverEmitted:
    """``src=""`` est invalide (la spec veut « a valid non-empty URL ») et
    le navigateur le résout contre l'URL du DOCUMENT — il retélécharge
    donc la page courante en croyant charger le média.

    Trouvé en lisant les logs du serveur de dev : le banc vidéo tirait des
    dizaines de requêtes par chargement. Invisible autrement — rien ne
    casse à l'écran, la page est juste chargée deux fois."""

    def test_no_src_omits_the_attribute(self) -> None:
        assert "src=" not in render(alt='x')

    def test_a_real_src_is_still_emitted(self) -> None:
        assert 'src="/vrai.png"' in render(src="/vrai.png", alt='x')

"""``Iframe`` — le titre obligatoire et les trois états du sandbox."""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.iframe.iframe import SANDBOX_BASELINE, Iframe
from bretzel.components.primitives.iframe.theme import IFRAME_THEME
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class FrameState(ClientState, persist="memory"):
    value: str = field(default="https://x.fr")


def render(**kwargs) -> str:
    with render_isolated():
        return serialize(Iframe(**kwargs).render())


class TestTitleIsMandatory:
    def test_missing_title_raises_at_call_time(self) -> None:
        """Un lecteur d'écran annonce les cadres par leur titre. Sans lui
        l'utilisateur entend « cadre », sans savoir si c'est une carte ou
        un formulaire de paiement — et ça ne se voit pas à l'écran."""
        with pytest.raises(TypeError):
            Iframe("https://x.fr")  # type: ignore[call-arg]

    def test_title_reaches_the_attribute(self) -> None:
        assert 'title="Carte"' in render(src="https://x.fr", title="Carte")

    def test_title_is_escaped(self) -> None:
        out = render(src="https://x.fr", title='<script>alert(1)</script>')
        assert "<script>" not in out


class TestTheSandboxDefault:
    def test_baseline_is_applied_when_nothing_is_said(self) -> None:
        out = render(src="https://x.fr", title="T")
        assert f'sandbox="{SANDBOX_BASELINE}"' in out

    def test_the_baseline_withholds_the_dangerous_two(self) -> None:
        """Le point n'est pas ce que la liste autorise, c'est ce qu'elle
        tait : sans ``allow-top-navigation`` le document embarqué ne peut
        pas changer la page sous vos pieds, et sans ``allow-downloads`` il
        ne peut pas déclencher un téléchargement. Les deux vecteurs qui
        transforment un embed en hameçonnage."""
        assert "allow-top-navigation" not in SANDBOX_BASELINE
        assert "allow-downloads" not in SANDBOX_BASELINE

    def test_the_baseline_keeps_ordinary_embeds_working(self) -> None:
        """Un défaut que tout le monde désactive au premier essai
        n'apprendrait qu'une chose : à le désactiver. Carte, lecteur et
        widget de paiement ont besoin de ces deux-là."""
        assert "allow-scripts" in SANDBOX_BASELINE
        assert "allow-same-origin" in SANDBOX_BASELINE

    def test_an_explicit_list_replaces_the_baseline(self) -> None:
        out = render(src="https://x.fr", title="T", sandbox="allow-scripts")
        assert 'sandbox="allow-scripts"' in out
        assert SANDBOX_BASELINE not in out

    def test_empty_string_is_the_maximal_sandbox_and_is_emitted(self) -> None:
        """``sandbox=""`` n'est pas « pas de sandbox » — c'est TOUT refusé.
        Il doit donc être émis, jamais confondu avec un attribut absent."""
        assert 'sandbox=""' in render(src="https://x.fr", title="T", sandbox="")

    def test_none_removes_the_attribute_entirely(self) -> None:
        """L'échappatoire : aucune restriction. Il faut l'écrire pour
        l'obtenir — c'est la différence avec le web nu, où c'est gratuit."""
        assert "sandbox" not in render(src="https://x.fr", title="T",
                                       sandbox=None)


class TestRootShape:
    def test_root_is_the_iframe_itself(self) -> None:
        out = render(src="https://x.fr", title="T")
        assert out.startswith("<iframe ")
        assert "<div" not in out

    def test_lazy_by_default(self) -> None:
        assert 'loading="lazy"' in render(src="https://x.fr", title="T")

    def test_attrs_can_override_loading(self) -> None:
        out = render(src="https://x.fr", title="T",
                     attrs={"loading": "eager"})
        assert 'loading="eager"' in out
        assert 'loading="lazy"' not in out

    def test_no_src_omits_the_attribute(self) -> None:
        """Un ``src=""`` est résolu contre l'URL du document : le cadre
        chargerait LA PAGE COURANTE dans lui-même, récursivement."""
        assert "src=" not in render(title="T")


class TestRatio:
    @pytest.mark.parametrize("ratio", ["square", "video", "portrait", "wide"])
    def test_each_ratio_emits_its_classes(self, ratio: str) -> None:
        out = render(src="https://x.fr", title="T", ratio=ratio)
        for token in IFRAME_THEME["ratios"][ratio].split():
            assert token in out

    def test_ratios_are_pairwise_distinct(self) -> None:
        rendered = {
            r: render(src="https://x.fr", title="T", ratio=r)
            for r in IFRAME_THEME["ratios"]
        }
        assert len(set(rendered.values())) == len(rendered)


class TestNoBindableSurface:
    @pytest.mark.parametrize("prop", ["src", "title", "ratio"])
    def test_binding_raises(self, prop: str) -> None:
        """Laisser un driver client réécrire le ``src`` d'un cadre
        sandboxé serait un moyen commode de le pointer ailleurs."""
        with render_isolated(), rendering_scope():
            state = FrameState()
            kwargs: dict = {"src": "https://x.fr", "title": "T"}
            kwargs[prop] = state.value
            with pytest.raises(ComponentUsageError, match="not bindable"):
                Iframe(**kwargs)

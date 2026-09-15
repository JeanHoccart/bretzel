"""``Audio`` — et surtout : il n'hérite PAS de la garde de la vidéo."""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.audio.audio import Audio
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class SoundState(ClientState, persist="memory"):
    value: str = field(default="/x.mp3")


def render(**kwargs) -> str:
    with render_isolated():
        return serialize(Audio(**kwargs).render())


class TestRootShape:
    def test_root_is_the_audio_itself(self) -> None:
        out = render(src="/a.mp3")
        assert out.startswith("<audio ")
        assert "<div" not in out

    def test_controls_on_by_default(self) -> None:
        """Un ``<audio>`` sans contrôles est invisible ET inaudible. Le
        défaut de la plateforme est un piège pour tout le monde sauf celui
        qui pilote la lecture en JS."""
        assert "controls" in render(src="/a.mp3")

    def test_controls_can_be_turned_off(self) -> None:
        assert "controls" not in render(src="/a.mp3", controls=False)

    def test_no_src_omits_the_attribute(self) -> None:
        assert "src=" not in render()

    def test_loop_and_muted_reach_the_attributes(self) -> None:
        out = render(src="/a.mp3", loop=True, muted=True)
        assert "loop" in out
        assert "muted" in out


class TestNoAutoplayGuard:
    def test_autoplay_does_not_force_muted(self) -> None:
        """LA différence avec ``ui.video``, et elle est délibérée.

        Sur une vidéo, forcer le silence SAUVE la lecture automatique :
        l'image reste, et c'était l'essentiel. Sur du son, le silence
        supprime tout ce que la lecture apportait — on livrerait un
        lecteur qui tourne pour rien.
        """
        out = render(src="/a.mp3", autoplay=True)
        assert "autoplay" in out
        assert "muted" not in out

    def test_muted_is_still_available_on_purpose(self) -> None:
        out = render(src="/a.mp3", autoplay=True, muted=True)
        assert "autoplay" in out
        assert "muted" in out


class TestNoRatio:
    def test_ratio_is_not_a_prop(self) -> None:
        """Un lecteur audio a une hauteur FIXE, connue avant chargement :
        il ne provoque aucun saut de page, donc il n'y a rien à réserver.
        Le kwarg part dans ``**kwargs`` comme attribut brut plutôt que
        d'être silencieusement ignoré — mais aucune classe de ratio n'est
        émise."""
        assert "aspect-" not in render(src="/a.mp3")


class TestNoBindableSurface:
    def test_binding_src_raises(self) -> None:
        with render_isolated(), rendering_scope():
            state = SoundState()
            with pytest.raises(ComponentUsageError, match="not bindable"):
                Audio(src=state.value)

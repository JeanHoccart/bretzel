"""``Video`` — la garde autoplay et le playsinline non-négociable.

Le contrat, pas la chaîne de classes.
"""

from __future__ import annotations

import pytest

from bretzel.components.base import ComponentUsageError
from bretzel.components.base.testing import render_isolated
from bretzel.components.primitives.video.theme import VIDEO_THEME
from bretzel.components.primitives.video.track import track
from bretzel.components.primitives.video.video import Video
from bretzel.core.serialize import serialize
from bretzel.state import ClientState, field
from bretzel.state.scopes.client import rendering_scope


class VidState(ClientState, persist="memory"):
    value: str = field(default="/x.mp4")


def render(**kwargs) -> str:
    with render_isolated():
        return serialize(Video(**kwargs).render())


class TestRootShape:
    def test_root_is_the_video_itself(self) -> None:
        out = render(src="/a.mp4")
        assert out.startswith("<video ")
        assert "<div" not in out

    def test_src_and_poster_reach_the_attributes(self) -> None:
        out = render(src="/a.mp4", poster="/p.jpg")
        assert 'src="/a.mp4"' in out
        assert 'poster="/p.jpg"' in out

    def test_no_poster_emits_no_attribute(self) -> None:
        """Un ``poster=""`` vide afficherait un cadre noir au lieu de la
        première image — l'attribut absent est le bon défaut."""
        assert "poster" not in render(src="/a.mp4")

    def test_controls_on_by_default(self) -> None:
        """Une vidéo sans contrôles ni autoplay est une vidéo que
        personne ne peut lire."""
        assert "controls" in render(src="/a.mp4")

    def test_controls_can_be_turned_off(self) -> None:
        assert "controls" not in render(src="/a.mp4", controls=False)


class TestTheAutoplayGuard:
    def test_autoplay_forces_muted(self) -> None:
        """LE piège que ce composant existe pour absorber : tous les
        navigateurs bloquent une lecture auto non muette, et la vidéo ne
        démarre alors PAS — sans erreur, sans log, sans indice visuel."""
        out = render(src="/a.mp4", autoplay=True)
        assert "autoplay" in out
        assert "muted" in out

    def test_muted_alone_does_not_imply_autoplay(self) -> None:
        """La garde va dans UN sens seulement — une vidéo muette qu'on
        lance à la main est un cas parfaitement normal."""
        out = render(src="/a.mp4", muted=True)
        assert "muted" in out
        assert "autoplay" not in out

    def test_explicit_muted_false_with_autoplay_is_still_muted(self) -> None:
        """L'utilisateur qui écrit ``muted=False, autoplay=True`` demande
        quelque chose que le navigateur refusera. On l'emporte sur son
        intention plutôt que de livrer une vidéo inerte."""
        out = render(src="/a.mp4", autoplay=True, muted=False)
        assert "muted" in out


class TestPlaysinline:
    def test_always_emitted(self) -> None:
        """Sans lui, iOS sort la vidéo du flux et la passe en plein écran
        dès la lecture. Un réglage dont la bonne valeur est toujours la
        même n'est pas un choix à exposer."""
        assert "playsinline" in render(src="/a.mp4")
        assert "playsinline" in render(src="/a.mp4", controls=False)
        assert "playsinline" in render(src="/a.mp4", autoplay=True)

    def test_an_explicit_false_is_overridden(self) -> None:
        """``playsinline`` n'est pas une prop, mais ``**kwargs`` l'accepte
        comme attribut HTML brut — le socle absorbe tout attribut inconnu.
        Le composant le REPOSE après, donc l'intention contraire est
        écrasée plutôt que respectée.

        C'est un choix, et il est assumé : le seul effet d'un
        ``playsinline`` absent est qu'iOS confisque l'écran à la lecture.
        Personne ne veut ça dans une application — et celui qui l'écrit
        le découvrirait sur un iPhone, en production, où il ne teste pas.
        """
        out = render(src="/a.mp4", attrs={"playsinline": False})
        assert "playsinline" in out


class TestRatioAndFit:
    @pytest.mark.parametrize("ratio", ["square", "video", "portrait", "wide"])
    def test_each_ratio_emits_its_classes(self, ratio: str) -> None:
        out = render(src="/a.mp4", ratio=ratio)
        for token in VIDEO_THEME["ratios"][ratio].split():
            assert token in out

    def test_ratios_are_pairwise_distinct(self) -> None:
        rendered = {
            r: render(src="/a.mp4", ratio=r) for r in VIDEO_THEME["ratios"]
        }
        assert len(set(rendered.values())) == len(rendered)

    def test_fit_defaults_to_contain_unlike_image(self) -> None:
        """À l'inverse d'``ui.image`` : recadrer une photo est anodin,
        recadrer une vidéo coupe l'action. Le letterboxing est ce que
        fait tout lecteur."""
        assert "object-contain" in render(src="/a.mp4")
        assert "object-cover" not in render(src="/a.mp4")

    def test_root_carries_a_background(self) -> None:
        """Le fond est la boîte d'attente : une vidéo ne connaît ses
        dimensions qu'après un aller-retour réseau."""
        assert "bg-" in render(src="/a.mp4")


class TestNoBindableSurface:
    @pytest.mark.parametrize("prop", ["src", "poster", "ratio"])
    def test_binding_raises(self, prop: str) -> None:
        with render_isolated(), rendering_scope():
            state = VidState()
            kwargs: dict = {"src": "/a.mp4"}
            kwargs[prop] = state.value
            with pytest.raises(ComponentUsageError, match="not bindable"):
                Video(**kwargs)


class TestEmptySrcIsNeverEmitted:
    """``src=""`` est invalide (la spec veut « a valid non-empty URL ») et
    le navigateur le résout contre l'URL du DOCUMENT — il retélécharge
    donc la page courante en croyant charger le média.

    Trouvé en lisant les logs du serveur de dev : le banc vidéo tirait des
    dizaines de requêtes par chargement. Invisible autrement — rien ne
    casse à l'écran, la page est juste chargée deux fois."""

    def test_no_src_omits_the_attribute(self) -> None:
        assert "src=" not in render()

    def test_a_real_src_is_still_emitted(self) -> None:
        assert 'src="/vrai.mp4"' in render(src="/vrai.mp4")


class TestTracks:
    """``tracks=`` — le contrat du descripteur et celui de l'émission.

    Le probe ``tests/probes/probe_video_tracks.py`` prouve l'autre
    moitié : que Chromium ANALYSE vraiment le WebVTT. Ici on ne juge que
    ce que Python écrit, et ça reste nécessaire — un attribut booléen mal
    émis ne se voit qu'à l'écran, et seulement chez qui n'attendait pas
    de sous-titres.
    """

    def test_no_track_leaves_the_video_childless(self) -> None:
        assert "<track" not in render(src="/a.mp4")

    def test_each_track_carries_its_four_attributes(self) -> None:
        out = render(src="/a.mp4",
                     tracks=[track("/fr.vtt", srclang="fr", label="Français")])
        assert ('<track kind="captions" src="/fr.vtt" srclang="fr" '
                'label="Français"/>') in out

    def test_the_declared_order_is_the_rendered_order(self) -> None:
        """Le navigateur choisit selon l'ordre du DOCUMENT : une piste qui
        remonte change ce que voit quelqu'un qui n'a rien choisi."""
        out = render(src="/a.mp4", tracks=[
            track("/1.vtt", srclang="fr", label="Un"),
            track("/2.vtt", srclang="en", label="Deux"),
        ])
        assert out.index('label="Un"') < out.index('label="Deux"')

    def test_default_is_emitted_bare_or_not_at_all(self) -> None:
        """``default`` est un booléen HTML : ``default="false"`` ACTIVE la
        piste. Il ne peut donc apparaître qu'en attribut nu."""
        avec = render(src="/a.mp4", tracks=[
            track("/fr.vtt", srclang="fr", label="FR", default=True)])
        assert " default/>" in avec
        sans = render(src="/a.mp4", tracks=[
            track("/fr.vtt", srclang="fr", label="FR")])
        assert "default" not in sans

    @pytest.mark.parametrize("champ", ["src", "srclang", "label"])
    def test_the_three_required_fields_reject_the_empty_string(
        self, champ: str,
    ) -> None:
        kwargs = {"src": "/fr.vtt", "srclang": "fr", "label": "FR"}
        kwargs[champ] = "   "
        with pytest.raises(ComponentUsageError, match=champ):
            track(**kwargs)

    def test_metadata_is_refused(self) -> None:
        """Le seul ``kind`` qui ne s'adresse qu'à du JS — et ce composant
        a tranché au cadrage qu'il n'est pas un lecteur."""
        with pytest.raises(ComponentUsageError, match="metadata"):
            track("/x.vtt", srclang="fr", label="FR", kind="metadata")

    def test_two_defaults_of_the_same_kind_raise(self) -> None:
        with render_isolated(), pytest.raises(
            ComponentUsageError, match="default=True",
        ):
            Video(src="/a.mp4", tracks=[
                track("/1.vtt", srclang="fr", label="Un", default=True),
                track("/2.vtt", srclang="en", label="Deux", default=True),
            ])

    def test_one_default_per_kind_stays_licit(self) -> None:
        """Le versant qui compte : la règle est PAR ``kind``, pas globale.
        Un sous-titre par défaut ET un chapitrage par défaut se
        cohabitent, et le HTML les autorise tous les deux."""
        out = render(src="/a.mp4", tracks=[
            track("/fr.vtt", srclang="fr", label="FR", default=True),
            track("/ch.vtt", srclang="fr", label="Chapitres",
                  kind="chapters", default=True),
        ])
        assert out.count(" default/>") == 2

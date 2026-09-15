"""``Audio`` test bench — court, parce que le composant l'est.

Six cartes. Ce banc en a longtemps eu quatre, en plaidant que « le
gabarit est un guide, pas un quota » — et l'argument avait l'air bon
jusqu'à ce qu'on regarde CE QUI manquait : *Edge cases* et *A11y*, sur un
composant dont le seul vrai sujet est justement l'accessibilité (des
contrôles atteignables, une transcription que le composant ne fournit
pas). Ce n'était pas de la retenue, c'étaient les deux cartes les plus
dues. La gate ``test_a_component_page_carries_its_cards`` les exige
maintenant.

Ce qui compte, ici, tient dans la carte 2 : **la garde autoplay de
``ui.video`` ne se transporte PAS à l'audio**, et c'est une décision, pas
un oubli.

⚠️ Hors ligne. La source est un WAV silencieux généré en ``data:`` —
le lecteur est fonctionnel, il n'y a juste rien à entendre.
"""

import base64
import struct

from bretzel import refreshable, ui
from bretzel.render import serialize_html
from bretzel.state import PageState, field

from examples.playground.features.inspection import emitted_html_block


PATH = "/audio"


def silent_wav(seconds: float = 0.25, rate: int = 8000) -> str:
    """Un WAV silencieux en ``data:`` — une source audio hors ligne.

    Généré plutôt que collé : 2,7 ko de base64 en dur seraient illisibles
    au diff, et personne ne saurait ce qu'ils contiennent. Ici on voit que
    c'est du silence.
    """
    n = int(rate * seconds)
    # 0x80 = le point milieu du PCM 8 bits non signé, donc du silence.
    body = bytes([0x80]) * n
    header = (
        b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate, 1, 8)
        + b"data" + struct.pack("<I", n)
    )
    return "data:audio/wav;base64," + base64.b64encode(header + body).decode()


SILENT = silent_wav()


class AudioPlayground(PageState):
    """État du banc serveur — un champ par prop + par échappatoire."""

    controls: str = field(default="on")
    autoplay: str = field(default="off")
    loop: str = field(default="off")
    muted: str = field(default="off")
    classes: str = field(default="")
    custom_id: str = field(default="")
    visible: str = field(default="on")


ON_OFF = [("on", "True"), ("off", "False")]


def server_changed(state: AudioPlayground) -> None:
    pass


def build_preview(state: AudioPlayground):
    kwargs: dict = {
        "controls": state.controls == "on",
        "autoplay": state.autoplay == "on",
        "loop": state.loop == "on",
        "muted": state.muted == "on",
    }
    if state.classes:
        kwargs["classes"] = state.classes
    if state.custom_id:
        kwargs["id"] = state.custom_id
    if state.visible == "off":
        kwargs["visible"] = False
    return ui.audio(SILENT, **kwargs)


def control(label: str):
    block = ui.vstack(gap="xs")
    with block:
        ui.text(label, color="muted", size="xs")
    return block


@refreshable(deps=[AudioPlayground])
def server_panel() -> None:
    state = AudioPlayground()

    with ui.grid(cols={"base": 1, "sm": 2, "md": 3}, gap="md"):
        with control("controls"):
            ui.select(value=state.controls, options=ON_OFF,
                      on_change=server_changed)
        with control("autoplay (ne force PAS muted)"):
            ui.select(value=state.autoplay, options=ON_OFF,
                      on_change=server_changed)
        with control("muted"):
            ui.select(value=state.muted, options=ON_OFF,
                      on_change=server_changed)
        with control("loop"):
            ui.select(value=state.loop, options=ON_OFF,
                      on_change=server_changed)
        with control("classes"):
            ui.input(value=state.classes, placeholder="rounded-lg",
                     on_change=server_changed)
        with control("id"):
            ui.input(value=state.custom_id, placeholder="my-audio",
                     on_change=server_changed)
        with control("visible"):
            ui.select(value=state.visible,
                      options=[("on", "True (défaut)"),
                               ("off", "False (pas de rendu)")],
                      on_change=server_changed)

    ui.divider()

    with ui.vstack(classes="max-w-sm"):
        build_preview(state)

    ui.divider()

    emitted_html_block(
        "Emitted HTML",
        serialize_html(build_preview(state)),
    )


def page() -> None:
    with ui.container():
        with ui.vstack():
            ui.heading("Audio", level=1)
            ui.text(
                "Le plus mince de la famille média, et il l'assume : pas "
                "de ratio (un lecteur audio a une hauteur fixe, donc aucun "
                "saut de page à éviter), pas de poster, pas de thème — la "
                "barre est dessinée par le navigateur. Il existe pour la "
                "symétrie de la famille, et pour un défaut qui compte : "
                "controls=True.",
                color="muted",
            )
            ui.text(
                "La source de cette page est un WAV silencieux généré en "
                "data: — hors ligne, et le lecteur est fonctionnel.",
                color="muted", size="sm",
            )

            # ── Carte 1 — Reference ─────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Reference", level=2)

                    ui.heading("Avec contrôles (le défaut)", level=3)
                    ui.text(
                        "Sans eux, un élément audio est invisible ET "
                        "inaudible. Le défaut de la plateforme (pas de "
                        "contrôles) est un piège pour tout le monde sauf "
                        "celui qui pilote la lecture en JS.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio(src=SILENT, controls=True)

                    ui.heading("Chaque paramètre, en appel littéral",
                               level=3)
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio(src=SILENT, controls=True, loop=True,
                                 muted=True, autoplay=False)

            # ── Carte 2 — La garde qui ne se transporte pas ─────────
            with ui.card():
                with ui.vstack():
                    ui.heading("La garde qui ne se transporte pas",
                               level=2)
                    ui.text(
                        "ui.video force muted dès qu'on demande autoplay, "
                        "parce que les navigateurs bloquent la lecture "
                        "automatique sonore. Forcer le silence y SAUVE la "
                        "lecture : l'image reste, et c'était l'essentiel.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "ui.audio ne le fait pas, et ce n'est pas un "
                        "oubli. Sur du son, le silence supprime tout ce "
                        "que la lecture apportait — on livrerait un "
                        "lecteur qui tourne pour rien. La lecture "
                        "automatique reste de toute façon bloquée tant "
                        "que l'utilisateur n'a pas interagi avec la "
                        "page ; aucun attribut ne contourne cette "
                        "politique navigateur.",
                        color="muted", size="sm",
                    )
                    with ui.grid(cols={"base": 1, "sm": 2}, gap="md"):
                        with ui.vstack(gap="xs"):
                            ui.text("ui.video(autoplay=True) →",
                                    size="xs", color="muted")
                            ui.code(
                                serialize_html(
                                    ui.video(autoplay=True, ratio="video")
                                ),
                                lang="html",
                            )
                        with ui.vstack(gap="xs"):
                            ui.text("ui.audio(autoplay=True) →",
                                    size="xs", color="muted")
                            ui.code(
                                serialize_html(ui.audio(autoplay=True)),
                                lang="html",
                            )

            # ── Carte 3 — Edge cases ────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Edge cases", level=2)

                    ui.heading("controls=False — l'élément DISPARAÎT",
                               level=3)
                    ui.text(
                        "Ce n'est pas « un lecteur sans boutons » : un "
                        "<audio> sans contrôles a une hauteur nulle, "
                        "donc la ligne ci-dessous est vide. La "
                        "combinaison reste légitime — une piste pilotée "
                        "en JS — mais elle ne se voit qu'ici.",
                        color="muted", size="xs",
                    )
                    with ui.container(
                        classes="p-2 rounded-lg border border-text/10"
                    ):
                        ui.audio(src=SILENT, controls=False)

                    ui.heading("Source absente", level=3)
                    ui.text(
                        "Le lecteur se dessine quand même, avec sa durée "
                        "à zéro. Le composant ne remplace pas une source "
                        "manquante — il n'a rien à mettre à la place.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio()

                    ui.heading("Source illisible", level=3)
                    ui.text(
                        "Un data: tronqué : le navigateur rend un "
                        "lecteur inerte. Aucune erreur ne remonte au "
                        "serveur — c'est un échec purement client.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(classes="max-w-sm"):
                        ui.audio(src="data:audio/wav;base64,UklGRg==")

                    ui.heading("autoplay + loop + muted ensemble",
                               level=3)
                    ui.text(
                        "Les trois cohabitent sans que le composant "
                        "n'arbitre. Le HTML émis le montre : ni garde, "
                        "ni réécriture.",
                        color="muted", size="xs",
                    )
                    ui.code(
                        serialize_html(
                            ui.audio(SILENT, autoplay=True, loop=True,
                                     muted=True)
                        ),
                        lang="html",
                    )

            # ── Carte 4 — Composability ─────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Composability", level=2)

                    ui.heading("Dans une carte — un épisode", level=3)
                    with ui.card():
                        with ui.vstack(gap="sm"):
                            ui.heading("Épisode 12", level=4)
                            ui.audio(src=SILENT)
                            ui.text("34 min", color="muted", size="sm")

                    ui.heading("Dans une cellule de grille contrainte",
                               level=3)
                    ui.text(
                        "Le lecteur natif prend sinon une largeur "
                        "arbitraire ; le slot racine pose w-full pour "
                        "qu'il s'accorde à sa colonne.",
                        color="muted", size="xs",
                    )
                    with ui.grid(cols={"base": 2}, gap="sm"):
                        ui.audio(src=SILENT)
                        ui.audio(src=SILENT)

            # ── Carte 5 — A11y ──────────────────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("A11y", level=2)
                    ui.text(
                        "controls=True par défaut EST la décision "
                        "d'accessibilité de ce composant, et sa seule "
                        "raison d'exister à côté de la balise native. "
                        "Sans contrôles, il n'y a rien à tabuler et rien "
                        "à annoncer : l'élément est là et personne ne "
                        "peut le jouer.",
                        color="muted", size="sm",
                    )
                    ui.text(
                        "Les contrôles rendus sont ceux du navigateur — "
                        "déjà étiquetés, déjà au clavier, déjà annoncés "
                        "dans la langue du système. C'est aussi la "
                        "raison de ne pas les redessiner : une barre "
                        "maison devrait réimplémenter tout ça, clavier "
                        "compris, pour gagner un arrondi.",
                        color="muted", size="sm",
                    )

                    ui.heading("Ce que le composant ne fournit PAS",
                               level=3)
                    ui.text(
                        "Pas de transcription, et aucun moyen d'en "
                        "attacher une : ui.audio est une feuille, il "
                        "n'accepte aucun enfant, donc aucun "
                        "<track kind=\"captions\"> ne peut y entrer. Un "
                        "<audio> seul est inaccessible à qui n'entend "
                        "pas — la transcription se pose À CÔTÉ, en "
                        "texte réel. C'est une limite déclarée, "
                        "consignée dans .claude/work/todo.md.",
                        color="muted", size="xs",
                    )
                    with ui.vstack(gap="sm", classes="max-w-sm"):
                        ui.audio(src=SILENT)
                        ui.text(
                            "Transcription — « Bienvenue dans "
                            "l'épisode 12. Aujourd'hui, l'état typé. »",
                            color="muted", size="sm",
                        )

            # ── Carte 6 — Server playground ─────────────────────────
            with ui.card():
                with ui.vstack():
                    ui.heading("Server playground", level=2)
                    ui.text(
                        "Mettez autoplay à True et vérifiez dans le HTML "
                        "émis que muted n'apparaît PAS — c'est la "
                        "différence avec ui.video.",
                        color="muted", size="sm",
                    )
                    server_panel()

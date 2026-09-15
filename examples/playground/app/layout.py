"""The application shell : sidebar on the left, page in the outlet.

Même squelette que ``examples/flat/features/shell.py`` (la référence qui
rend correctement) : ``h-screen`` en flux, ``sidebar_title`` +
``sidebar_footer`` + ``sidebar_footer_item``, et le contenu décalé sous
la top-bar mobile via ``max-md:pt-[5.5rem]``.
"""

from bretzel import ui
from bretzel.theme import ColorScheme

#: Les trois modes, dans l'ordre où on les lit.
THEME_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("light", "Thème clair", "sun"),
    ("dark", "Thème sombre", "moon"),
    ("system", "Thème système", "monitor"),
)

from examples.playground.app.nav import NAV


def shell() -> None:
    # ``ui.viewport`` porte le cadre — plein écran, hors du flux, régions
    # en ligne et jamais de défilement propre. Les trente lignes de
    # commentaire qui vivaient ici (pourquoi `fixed inset-0` et pas
    # `h-screen`, pourquoi `align="stretch"`, pourquoi le contexte
    # d'empilement est sans danger) sont dans le thème du composant :
    # `bretzel/components/layout/viewport/theme.py`. Elles étaient
    # recopiées dans neuf coques, chacune libre de dériver.
    with ui.viewport():
        with ui.sidebar(collapsible="rail"):
            # ``sidebar_title`` owns the header : logo + titre + toggle
            # collapse (et la top-bar mobile auto). Plus de ``hstack``
            # manuel, plus de ``pr-12`` ni de ``group-data-[open=false]``.
            ui.sidebar_title(
                "Bretzel · Playground",
                icon=ui.icon("shapes", color="primary", size="lg"),
            )
            for section, items in NAV:
                with ui.sidebar_section(label=section):
                    for label, path, icon in items:
                        ui.sidebar_item(label, icon=icon, href=path)
            # ``sidebar_footer`` : ligne épinglée en bas qui ouvre un
            # popover au clic. Ses enfants sont des ``sidebar_footer_item``
            # (même API que ``dropdown_item`` : ils se referment au pick).
            # Le toggle de thème vit ici (le nouveau header n'a pas de slot
            # pour des actions libres). ``ColorScheme`` est framework-owned
            # (l'app ne l'instancie jamais) ; ``ColorScheme.toggle()`` est
            # une expression client pure — zéro aller-retour serveur.
            with ui.sidebar_footer(
                name="Jean Hoccart",
                subtitle="jean.hoccart@gmail.com",
            ):
                # Trois entrées et non un bascule : ``system`` est un
                # état à part entière — « suis mon OS » — et un toggle à
                # deux positions ne sait pas l'exprimer. C'est ce que
                # fait déjà le CRM, et c'est plus fluide : on choisit,
                # on ne devine pas dans quel sens ça va basculer.
                for value, label, icon in THEME_ITEMS:
                    ui.sidebar_footer_item(
                        label=label,
                        icon_left=icon,
                        on_click=ColorScheme.set(value),
                    )
                # Le lien croisé, symétrique de celui de la doc.
                # ``sidebar_title`` ramène déjà à ``/``, donc une entrée
                # « Accueil » ne servirait à rien. Port en dur : la cible
                # est un AUTRE serveur.
                ui.sidebar_footer_item(
                    label="Docs", icon_left="book-open",
                    href="http://localhost:8006/",
                )
        # La RÉGION : les pages enfants se rendent ICI (outlet_shell).
        # ``min-h-0`` laisse le flex enfant rétrécir sous sa hauteur de
        # contenu pour que ``overflow-y-auto`` déclenche une scrollbar au
        # lieu de pousser le panneau au-delà du viewport.
        # ``max-md:pt-[5.5rem]`` décale le contenu sous la top-bar mobile
        # (``position: fixed``, h-14 = 3.5rem, frostée ``bg-surface/80``) —
        # 5.5rem = 3.5rem (barre) + 2rem de respiration. Desktop (md+) :
        # pas de barre, le ``p-8`` reprend la main. Même ligne que flat.
        with ui.pane(gap="none", padding="lg",
                     classes="max-md:pt-[5.5rem]"):
            ui.outlet()

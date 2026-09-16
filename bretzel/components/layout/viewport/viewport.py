"""``Viewport`` — le cadre qui prend l'écran et ne défile jamais.

Une boîte de la taille exacte de la fenêtre, **hors du flux du
document**. Elle ne défile pas parce qu'elle ne dépasse jamais ; ce sont
ses régions (:class:`~bretzel.components.layout.pane.Pane`) qui défilent.

Le modèle qu'elle déclare
--------------------------
Écrire ``ui.viewport()``, c'est choisir le modèle « document gelé,
boîtes intérieures qui défilent » — celui des outils (VS Code, Slack) —
plutôt que « chrome fixe, document qui défile » — celui des pages web
(Mantine ``AppShell``, shadcn ``Sidebar``). Bretzel garde le second par
DÉFAUT : une page sans coque défile normalement, sans que personne
n'écrive quoi que ce soit. Le premier s'obtient ici, explicitement.

C'est la réponse de Quasar au même problème : layout fenêtre par défaut,
mode ``container`` sur demande.

Ce que le modèle gelé donne, et ce qu'il coûte
------------------------------------------------
Il donne N régions à défilement **indépendant** — un maître-détail, des
colonnes de kanban, un fil de messages à côté d'une liste — et un repli
de barre latérale absorbé par flexbox, sans canal à câbler entre la
barre et le contenu.

Il coûte une chaîne de hauteurs continue de la racine à la région, et
c'est un coût SILENCIEUX : un maillon manquant ne lève pas, il clippe
ou il fait grandir. Cf. la docstring de ``Pane``.

Où on l'écrit
--------------
Deux formes, et il n'y en a pas de troisième : une coque d'application
(huit dans ``examples/``), et une page plein écran sans layout —
``examples/crm/features/login.py``, qui n'a ni barre ni outlet parce que
personne n'est encore connecté pour y avoir droit.

Une page de connexion doit pouvoir défiler sur un petit téléphone : ça
ne demande AUCUNE prop, ça se compose — un ``Viewport`` qui ne défile
pas, contenant un ``Pane`` qui défile.

"""

from __future__ import annotations

from typing import Any, ClassVar

from bretzel.components.base import reactive_prop
from bretzel.components.layout.flex.flex import Flex
from bretzel.components.layout.viewport.theme import VIEWPORT_THEME


class Viewport(Flex):
    """Render a full-screen frame whose regions scroll independently."""

    THEME: ClassVar[dict[str, Any]] = VIEWPORT_THEME
    THEME_KEY: ClassVar[str] = "viewport"
    #: « Je suis un cadre gelé. » Lu par duck-typing, comme
    #: ``IS_TRANSPARENT_WRAPPER`` juste à côté : le lecteur est
    #: ``base/_wiring.check_sticky_bar_placement``, qui juge la place des
    #: barres ``sticky`` une fois l'arbre bâti. Un ``isinstance`` ferait
    #: la même chose ici — l'import ``base → layout`` serait acyclique —
    #: mais un marqueur reste la convention du dépôt pour une question
    #: posée à un ARBRE d'objets hétérogènes.
    IS_FROZEN_FRAME: ClassVar[bool] = True

    #: ``row`` — la forme dominante (barre latérale à gauche, contenu à
    #: droite : huit sites sur neuf). ``col`` sert la coque mobile, barre
    #: du haut puis contenu. Les deux **co-occurrent dans la même app** :
    #: une app de démo depuis retirée avait les deux coques, choisies
    #: par ``if Screen().is_mobile``. C'est ce qui fait gagner sa place à la
    #: prop là où ``ui.vstack`` / ``ui.hstack`` ont perdu la leur.
    direction: Any = reactive_prop(default="row", emit_attr=False)
    #: ``stretch`` — les régions d'un cadre remplissent l'axe transverse.
    #: Le défaut ``center`` de ``ui.hstack`` réduisait le panneau droit à
    #: la hauteur de son contenu et privait l'outlet de tout conteneur de
    #: défilement ; les coques écrivaient donc ``align="stretch"`` à la
    #: main, avec le commentaire qui explique pourquoi.
    align: str = reactive_prop(default="stretch", emit_attr=False)
    #: ``none`` — un cadre juxtapose des régions, il ne les espace pas.
    #: Les neuf sites écrivaient ``gap="none"``.
    gap: Any = reactive_prop(default="none", emit_attr=False)

    def __init__(
        self,
        *,
        direction: str | dict | None = None,
        align: str | None = None,
        gap: str | dict | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            direction=direction, align=align, gap=gap, **kwargs
        )

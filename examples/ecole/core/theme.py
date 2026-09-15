"""core/theme — le seul vrai global de l'app.

**La densité vient du framework**, et l'app n'a rien à demander : c'est
le DÉFAUT livré depuis le 2026-09-13. Ce fichier ne décide que des
COULEURS.

L'échelle a été écrite à la main dans un ``core/preset.py`` le
2026-09-12, sur jugement de l'utilisateur devant l'écran (*« regarde,
kanban est plus compact par défaut »*) — d'abord en recopiant les 300
lignes du kanban, puis en déplaçant deux jetons de Tailwind. Le second
essai était le bon, et il est devenu l'échelle livrée : deux apps qui
écrivent la même correction, c'est un manque du framework, pas une
préférence d'app.

**Les couleurs : calmes, et pas de noir pur.** Une grille d'emploi du
temps est un MUR de cartes colorées, et à cette densité un fond très
sombre sous une teinte saturée fatigue en dix secondes. Le fond sombre
est donc un gris légèrement chaud, le texte descend du blanc pur, et
l'accent est un vert-bleu sourd qui laisse le rouge et l'ambre dire ce
qu'ils ont à dire — ce sont eux qui portent l'information (une heure à
nature, un jour sans classe, une note refusée).

**Le clair est un papier, pas un écran** : ``#f6f5f2``, parce que l'app
se regarde à côté de copies.

⚠️ **La taille de base à 19 px a été RETIRÉE le 2026-09-12**, sur
jugement de l'utilisateur devant l'écran : *« c'est trop gros »*. EF-U3
demandait *« rien ne s'affiche sous 19 px — la tablette est un poste de
travail, pas une consultation »*, et c'était appliqué en déplaçant la
racine typographique. Le résultat tenait l'exigence à la lettre et
ratait son intention : sur un écran de bureau, une app 19 % plus grande
ne se lit pas mieux, elle montre moins — la semaine sortait de l'écran.

Le besoin derrière EF-U3 reste vrai et reste à traiter là où il se pose :
sur la tablette, où le navigateur a son propre réglage de taille. Ce qui
a changé, c'est qu'il est maintenant EXPRIMABLE — ``Theme(text={…})``
prend l'échelle entière, sans recopier un slot de composant.

Ce qui reste vrai est gaté :
``tests/consistency/test_ecole_never_sets_a_text_size.py`` tient que
l'app ne décide aucune taille de texte — c'est ce qui laisse au thème la
seule autorité sur la densité.
"""

from bretzel.theme import Theme

#: Ce qui VOLE pendant un glisser, et ce que la chaise d'origine devient.
#:
#: Le runtime fait déjà ce que font Sortable.js et le ``DragOverlay`` de
#: dnd-kit : le vrai nœud reste dans le flux, marqué
#: ``data-bz-dragging``, et un clone anonyme classé ``.bz-drag-preview``
#: suit le pointeur. Le défaut est un clone **au 1 pour 1** — donc, sur
#: un plan de classe, la même grande carte deux fois, superposées. Vu à
#: l'écran : *« c'est assez déroutant de voir toute la carte prendre la
#: place. »*
#:
#: Ce que font les autres, et ce qu'on copie ici : **ce qui vole est plus
#: petit que l'original**. Trello, Linear et Notion font voler une carte
#: compacte et laissent un emplacement vide derrière ; les agendas
#: laissent la CIBLE porter l'information. Sur une grille de créneaux
#: fixes, c'est la seconde qui compte — d'où la chaise d'origine vidée
#: plutôt que grisée.
#:
#: ⚠️ **Aucune API touchée**, et c'est le sujet de l'essai : le clone
#: porte une classe connue, l'original un état de thème. Une app peut
#: donc redessiner les deux sans rien demander au framework. Ce que ça ne
#: donne pas : le CHOIX de ce qui vole. On cache des morceaux du clone au
#: lieu de déclarer une représentation — donc ce bloc connaît la
#: structure de ``vignette_assise`` (avatar, prénom, nom, icônes) et
#: casserait si elle changeait d'ordre. C'est la limite de l'essai, pas
#: une fatalité.
APERCU_DE_GLISSER = """
/* La pastille qui suit le doigt : l'avatar et le prénom, rien d'autre. */
.bz-drag-preview {
  width: auto !important;
  height: auto !important;
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-surface-foreground);
  border: 1px solid var(--bz-stroke-strong, rgb(128 128 128 / 0.35));
  box-shadow: 0 10px 24px -8px rgb(0 0 0 / 0.45);
  padding: 0.25rem 0.75rem 0.25rem 0.25rem;
  opacity: 1;
}
/* La vignette passe en rangée : avatar puis prénom, côte à côte. */
.bz-drag-preview > * {
  flex-direction: row !important;
  align-items: center !important;
  gap: 0.5rem !important;
  padding: 0 !important;
}
/* Le nom de famille et la rangée d'icônes ne volent pas. */
.bz-drag-preview > * > :nth-child(n+3) {
  display: none !important;
}
"""

#: Le vert-bleu d'accent. Sourd exprès : il sert à dire « ceci est un
#: cours », c'est-à-dire le cas ORDINAIRE, qui ne doit pas crier.
ACCENT = "#2f7d6b"

THEME = Theme(
    css=APERCU_DE_GLISSER,
    # La chaise d'origine se VIDE au lieu de griser : sur une grille de
    # créneaux, ce qui informe c'est la place libérée et la cible visée,
    # pas une copie pâle sous celle qui vole. Le défaut du framework
    # (`opacity-30 grayscale`) est bon pour une LISTE, où l'élément
    # quitte le flux — ici il reste dans sa chaise.
    components={
        "draggable": {
            "slots": {"dragging": "data-[bz-dragging=true]:opacity-0"},
        },
    },
    semantic={
        "primary": ACCENT,
        "secondary": "#7a6a9c",
        # Un papier, pas un écran.
        "background": "#f6f5f2",
        "surface": "#ffffff",
        "interface": "#ecebe7",
        "text": "#1f2328",
        "muted": "#5f6874",
    },
    semantic_dark={
        "primary": "#5fb3a1",
        "secondary": "#a892d4",
        # Un gris légèrement chaud, pas un quasi-noir : voir la docstring.
        "background": "#15181c",
        "surface": "#1c2026",
        "interface": "#272c34",
        # Un blanc cassé : le blanc pur sur fond sombre bave.
        "text": "#e6e8ea",
        "muted": "#9aa3ad",
    },
)

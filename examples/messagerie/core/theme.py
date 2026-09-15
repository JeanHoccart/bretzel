"""Le seul vrai global : le thème.

L'échelle vient du framework — contrôles à 30 px, texte médian à 14 px,
c'est le DÉFAUT livré depuis le 2026-09-13. Trois panneaux dans un document gelé — la densité EST ce
qui rend la vue à trois colonnes lisible.

Ne reste ici que ce que le framework ne peut pas décider : la teinte.
"""

from bretzel.theme import Theme

THEME = Theme(semantic={"primary": "#4f46e5"})  # indigo

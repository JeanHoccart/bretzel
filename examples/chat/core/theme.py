"""Le seul vrai global : le thème.

L'échelle vient du framework — contrôles à 30 px, texte médian à 14 px,
c'est le DÉFAUT livré depuis le 2026-09-13. Une messagerie instantanée est une liste dense qui défile.

Ne reste ici que ce que le framework ne peut pas décider : la teinte.
"""

from bretzel.theme import Theme

THEME = Theme(semantic={"primary": "#0ea5e9"})  # cyan

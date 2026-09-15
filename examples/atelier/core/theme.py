"""Le seul global visuel : le thème.

L'échelle d'un outil est celle du framework depuis le 2026-09-13, donc
cette app n'a rien à demander — et c'est elle qui en a le plus besoin de
tout le dépôt : une lecture par tâche, c'est un tableau de phases, de
compteurs et de commandes rejouées.

Ne reste ici que la teinte. Un instrument de mesure n'est ni un succès ni
une erreur, donc ni vert ni rouge — ce sont les VERDICTS qui ont le droit
de colorer (une tâche en aller-retour, un outil en échec).
"""

from bretzel.theme import Theme

THEME = Theme(semantic={"primary": "#b45309"})  # amber

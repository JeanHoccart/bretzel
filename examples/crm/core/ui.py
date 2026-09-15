"""core/ui — les briques d'interface partagées PAR l'app.

Un seul habitant pour l'instant : la carte KPI. Elle vivait en cinq copies —
quatre identiques et une divergente — avant d'être remontée ici, ce qui est
exactement l'histoire d'``examples/mad/core/ui.py``, dont la docstring dit
qu'il existe « parce que la carte KPI vivait en double ».

Ce n'est pas un fourre-tout : s'il grossit, c'est qu'il contient une feature
qu'on n'a pas nommée (cf. ``app-structure.md`` § 6).
"""

from __future__ import annotations

from bretzel import ui


def kpi(label: str, value: str, icon: str, color: str) -> None:
    """La carte chiffre-clé de l'app : pastille d'icône, libellé, valeur.

    Un seul gabarit pour les cinq rangées qui en posent (comptes, fiche
    compte, activités, rapports) — sinon deux rangées de KPI voisines
    s'affichent à des hauteurs et des graisses différentes, sans raison.
    """
    with ui.card(padding="md"):
        with ui.hstack(gap="md", align="center"):
            with ui.flex(align="center", justify="center",
                         classes="w-10 h-10 rounded-lg bg-text/5 shrink-0"):
                ui.icon(icon, color=color)
            with ui.vstack(gap="none"):
                ui.text(label, color="muted", size="xs")
                ui.heading(value, level=3, size="lg")

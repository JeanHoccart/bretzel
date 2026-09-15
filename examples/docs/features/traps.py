"""RÉFÉRENCE — Pièges.

Les gotchas condensés — surtout les échecs *silencieux*, ceux qui ne
crashent pas mais ne marchent juste pas. Chaque piège : le symptôme, la
cause, le fix.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell

PATH = "/traps"

# (titre, symptôme, fix)  — les pièges silencieux d'abord.
_TRAPS: list[tuple[str, str, str]] = [
    (
        "PEP 649 — les champs de State ne s'enregistrent pas",
        "Un State a l'air correct mais ses champs sont vides / le re-render "
        "ne part pas. Aucune erreur.",
        "Mettre `from __future__ import annotations` EN PREMIER dans tout "
        "fichier qui déclare un State. Sans lui, les annotations ne sont pas "
        "évaluées comme attendu et la métaclasse ne voit pas les champs.",
    ),
    (
        "Binding lu hors d'une render scope",
        "`state.field.set(...)` ne produit rien d'utile ; le binding se "
        "comporte comme une valeur brute.",
        "Lire un champ de ClientState ne renvoie un `ClientBinding` QUE dans "
        "une render scope (`@page` / `@refreshable`). Dans un handler, c'est "
        "la valeur brute. Piloter l'état depuis un handler → muter, pas binder.",
    ),
    (
        "@validator qui ne retourne rien",
        "Le champ vaut `None` après écriture.",
        "Un `@validator(\"champ\")` reçoit `(self, value)` et DOIT `return` la "
        "valeur (transformée ou non). `def _n(self, v): v.strip()` écrit "
        "`None` — il manque le `return`.",
    ),
    (
        "Passer un ClientBinding à un prop non-bindable",
        "`ComponentUsageError` à la construction (celui-là est bruyant, tant "
        "mieux).",
        "Seuls les props listés dans `BINDABLE_PROPS` acceptent un binding. "
        "Pour du dynamique sur variant/size/color → conditional render côté "
        "serveur (`color=\"error\" if failed else \"success\"`). Voir le "
        "Catalogue pour la liste par composant.",
    ),
    (
        "for natif au lieu de ui.each sur des composants à état",
        "Après un re-render/réordonnancement, des overlays ouverts se ferment, "
        "des checkbox perdent leur état.",
        "Itérer avec `ui.each(items, key=\"id\")` dès que le corps produit des "
        "composants stateful : la key stabilise l'identité à travers le morph. "
        "Un `for` Python suffit pour du statique (`ui.text` × N).",
    ),
    (
        "Prop bindable dont l'attribut n'agit pas sur le root",
        "Le binding existe mais l'UI ne réagit pas (ex. `disabled` sur un "
        "wrapper `<div>`, `src` sur un `<span>`).",
        "L'attribut doit atterrir sur le bon élément carrier. Déclarer "
        "`BINDABLE_CARRIERS = {prop: \"bz-ref\"}` (ou `forward_binding`) pour "
        "forwarder la directive sur l'enfant qui porte vraiment l'attribut.",
    ),
    (
        "Écrire name= / @click / hx-post à la main",
        "Ça marche, mais c'est l'escape hatch — pas l'idiome.",
        "Le `name` est auto-dérivé du binding (`AUTONAME_FROM`). Les actions "
        "passent par `on_<event>=` (callable serveur ou string cliente). Si tu "
        "écris du `hx-` en dur, c'est probablement un primitive runtime qui "
        "manque.",
    ),
]


@page(PATH, layout=shell, title="Pièges")
def traps_page() -> None:
    with ui.container(width="lg"):
        with ui.vstack(gap="lg"):
            ui.heading("Pièges", level=1, size="3xl")
            ui.text(
                "Les gotchas condensés — surtout les échecs silencieux, ceux "
                "qui ne crashent pas mais ne marchent juste pas.",
                color="muted", size="lg",
            )

            for title, symptom, fix in _TRAPS:
                with ui.card():
                    with ui.vstack(gap="sm"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.icon("triangle-alert", color="warning")
                            ui.heading(title, level=3)
                        with ui.hstack(align="baseline", gap="sm", wrap=True):
                            ui.badge("Symptôme", color="error", variant="soft")
                            ui.text(symptom, color="muted", size="sm")
                        with ui.hstack(align="baseline", gap="sm", wrap=True):
                            ui.badge("Fix", color="success", variant="soft")
                            ui.text(fix, color="muted", size="sm")

"""REFERENCE — Traps.

The gotchas condensed — above all the *silent* failures, the ones that do
not crash but simply do not work. Each trap: the symptom, the cause, the
fix.
"""

from __future__ import annotations

from bretzel import page, ui

from examples.docs.features.shell import shell
from examples.docs.lib.i18n import tr

PATH = "/traps"

# (title, symptom, fix) — the silent traps first.
_TRAPS: list[tuple[str, str, str]] = [
    (
        tr('PEP 649 — State fields do not register',
           "PEP 649 — les champs de State ne s'enregistrent pas"),
        tr('A State looks correct but its fields are empty / the re-render '
           'does not fire. No error at all.',
           "Un State a l'air correct mais ses champs sont vides / le re-"
           'render ne part pas. Aucune erreur.'),
        tr('Put `from __future__ import annotations` FIRST in every file that'
           ' declares a State. Without it, the annotations are not evaluated '
           'as expected and the metaclass does not see the fields.',
           'Mettre `from __future__ import annotations` EN PREMIER dans tout '
           'fichier qui déclare un State. Sans lui, les annotations ne sont '
           'pas évaluées comme attendu et la métaclasse ne voit pas les '
           'champs.'),
    ),
    (
        tr('A binding read outside a render scope',
           "Binding lu hors d'une render scope"),
        tr('`state.field.set(...)` produces nothing useful; the binding '
           'behaves like a raw value.',
           "`state.field.set(...)` ne produit rien d'utile ; le binding se "
           'comporte comme une valeur brute.'),
        tr('Reading a ClientState field returns a `ClientBinding` ONLY inside'
           ' a render scope (`@page` / `@refreshable`). Inside a handler, it '
           'is the raw value. Driving the state from a handler → mutate, do '
           'not bind.',
           'Lire un champ de ClientState ne renvoie un `ClientBinding` QUE '
           'dans une render scope (`@page` / `@refreshable`). Dans un '
           "handler, c'est la valeur brute. Piloter l'état depuis un handler "
           '→ muter, pas binder.'),
    ),
    (
        tr('@validator returning nothing',
           '@validator qui ne retourne rien'),
        tr('The field is `None` after writing.',
           'Le champ vaut `None` après écriture.'),
        tr('A `@validator("field")` receives `(self, value)` and MUST '
           '`return` the value (transformed or not). `def _n(self, v): '
           'v.strip()` writes `None` — the `return` is missing.',
           'Un `@validator("champ")` reçoit `(self, value)` et DOIT `return` '
           'la valeur (transformée ou non). `def _n(self, v): v.strip()` '
           'écrit `None` — il manque le `return`.'),
    ),
    (
        tr('Passing a ClientBinding to a non-bindable prop',
           'Passer un ClientBinding à un prop non-bindable'),
        tr('`ComponentUsageError` at construction (that one is loud, and '
           'good).',
           '`ComponentUsageError` à la construction (celui-là est bruyant, '
           'tant mieux).'),
        tr('Only the props listed in `BINDABLE_PROPS` accept a binding. For '
           'something dynamic on variant/size/color → a conditional render on'
           ' the server (`color="error" if failed else "success"`). See the '
           'Catalogue for the per-component list.',
           'Seuls les props listés dans `BINDABLE_PROPS` acceptent un '
           'binding. Pour du dynamique sur variant/size/color → conditional '
           'render côté serveur (`color="error" if failed else "success"`). '
           'Voir le Catalogue pour la liste par composant.'),
    ),
    (
        tr('a native for instead of ui.each on stateful components',
           'for natif au lieu de ui.each sur des composants à état'),
        tr('After a re-render/reorder, open overlays close, checkboxes lose '
           'their state.',
           'Après un re-render/réordonnancement, des overlays ouverts se '
           'ferment, des checkbox perdent leur état.'),
        tr('Iterate with `ui.each(items, key="id")` as soon as the body '
           'produces stateful components: the key stabilises identity across '
           'the morph. A Python `for` is enough for static content (`ui.text`'
           ' × N).',
           'Itérer avec `ui.each(items, key="id")` dès que le corps produit '
           "des composants stateful : la key stabilise l'identité à travers "
           'le morph. Un `for` Python suffit pour du statique (`ui.text` × '
           'N).'),
    ),
    (
        tr('A bindable prop whose attribute does not act on the root',
           "Prop bindable dont l'attribut n'agit pas sur le root"),
        tr('The binding exists but the UI does not react (e.g. `disabled` on '
           'a `<div>` wrapper, `src` on a `<span>`).',
           "Le binding existe mais l'UI ne réagit pas (ex. `disabled` sur un "
           'wrapper `<div>`, `src` sur un `<span>`).'),
        tr('The attribute must land on the right carrier element. Declare '
           '`BINDABLE_CARRIERS = {prop: "bz-ref"}` (or `forward_binding`) to '
           'forward the directive onto the child that really carries the '
           'attribute.',
           "L'attribut doit atterrir sur le bon élément carrier. Déclarer "
           '`BINDABLE_CARRIERS = {prop: "bz-ref"}` (ou `forward_binding`) '
           "pour forwarder la directive sur l'enfant qui porte vraiment "
           "l'attribut."),
    ),
    (
        tr('Writing name= / @click / hx-post by hand',
           'Écrire name= / @click / hx-post à la main'),
        tr('It works, but it is the escape hatch — not the idiom.',
           "Ça marche, mais c'est l'escape hatch — pas l'idiome."),
        tr('The `name` is auto-derived from the binding (`AUTONAME_FROM`). '
           'Actions go through `on_<event>=` (a server callable or a client '
           'string). If you find yourself writing raw `hx-`, it is probably a'
           ' runtime primitive that is missing.',
           'Le `name` est auto-dérivé du binding (`AUTONAME_FROM`). Les '
           'actions passent par `on_<event>=` (callable serveur ou string '
           "cliente). Si tu écris du `hx-` en dur, c'est probablement un "
           'primitive runtime qui manque.'),
    ),
]


@page(PATH, layout=shell, title=tr('Traps',
                                   'Pièges'))
def traps_page() -> None:
    with ui.container(width="xl"):
        with ui.vstack(gap="lg"):
            ui.heading(tr('Traps',
                          'Pièges'), level=1, size="3xl")
            ui.text(
                tr('The gotchas, condensed — above all the silent failures, '
                   'the ones that do not crash but simply do not work.',
                   'Les gotchas condensés — surtout les échecs silencieux, '
                   'ceux qui ne crashent pas mais ne marchent juste pas.'),
                color="muted", size="lg",
            )

            for title, symptom, fix in _TRAPS:
                with ui.card():
                    with ui.vstack(gap="sm"):
                        with ui.hstack(align="center", gap="sm"):
                            ui.icon("triangle-alert", color="warning")
                            ui.heading(title, level=3)
                        with ui.hstack(align="baseline", gap="sm", wrap=True):
                            ui.badge(tr('Symptom',
                                        'Symptôme'), color="error", variant="soft")
                            ui.text(symptom, color="muted", size="sm")
                        with ui.hstack(align="baseline", gap="sm", wrap=True):
                            ui.badge("Fix", color="success", variant="soft")
                            ui.text(fix, color="muted", size="sm")

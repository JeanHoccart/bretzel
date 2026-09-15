"""Drift gate — la surface bindable de chaque composant est FIGÉE ici.

Ce fichier est le **miroir machine** de la règle « driver client, sinon
serveur »
(`.claude/bretzel/client-reactive-surface.md` § *La règle*, figée
2026-07-16).

Le code (`Component.BINDABLE_PROPS`) reste la source de vérité ; ce
snapshot le verrouille : **changer la surface bindable d'un composant
fait rougir ce gate**, ce qui force à (1) le vouloir explicitement et
(2) l'inscrire ici, à côté des autres.

⚠️ **La deuxième moitié de cette phrase a changé le 2026-08-16.** Elle
disait « et mettre à jour le funnel EN MÊME TEMPS » : la matrice était
recopiée à la main dans `kwarg-routing.md`, et ce gate ne faisait que le
RAPPELER — il ne vérifiait pas que la recopie était juste. Un rappel
manuel est un délai avant dérive, pas une garantie (14 composants
manquaient au moment de la mise au clair, cf. audit 2026-07-16). La
matrice est désormais dérivée à la demande par ``bretzel describe``, donc il
n'y a plus rien à recopier.

Pourquoi un snapshot plutôt qu'une dérivation depuis la règle : la règle
tranche des cas-limites au jugement (min/max câblés sur date mais bakés
statiques sur slider ; status live mais src non). Un snapshot capture le
verdict humain ; le diff force à re-justifier tout écart.

Contrat de maintenance : tu ajoutes / retires une prop d'un
`BINDABLE_PROPS` → mets à jour `_EXPECTED` ici (le funnel se régénère),
dans le même commit. Un nouveau composant `ui.foo` → ajoute sa ligne
(le gale bidirectionnel ci-dessous te le rappellera).
"""

from __future__ import annotations

import pytest

from tests.consistency._discovery import public_component_classes

#: Pas de détecteur à rendre aveugle — cf.
#: ``test_a_prohibition_gate_is_mutation_tested``.
MUTATION_NOT_APPLICABLE = (
    "compare un instantané figé aux classes VIVANTES ; une comparaison d'ensembles ne peut pas cesser de reconnaître — si la découverte tombe, `test_the_sweep_is_not_vacuous` rougit"
)

# Verdict figé par composant (règle « driver client, sinon serveur »).
# Comparé en set : l'ORDRE dans BINDABLE_PROPS n'est pas sémantique.
_EXPECTED: dict[str, frozenset[str]] = {
    # ── Actions ──────────────────────────────────────────────────────
    # ``href`` depuis le 2026-08-23 — même raison que chez Link, dont
    # il partage le rôle : la destination peut dépendre de l'état.
    "Button": frozenset({"label", "disabled", "loading", "href"}),
    "IconButton": frozenset({"disabled", "loading"}),
    "Link": frozenset({"label", "href"}),
    # ── Inputs ───────────────────────────────────────────────────────
    # ``min`` / ``max`` restent ∅ contrairement à la famille date : la
    # règle ne les y admet en one-way que pour la contrainte croisée
    # client-side d'un range (``fin.min = début``), qui n'existe pas sur
    # une heure isolée.
    "TimePicker": frozenset({"value", "disabled"}),
    # ``value`` a un driver CLIENT : le panneau écrit la couleur
    # choisie sans repasser par le serveur, et le champ est
    # éditable. ``swatches`` n'existe pas (cf. la docstring du
    # composant) et ``size`` / ``color`` sont design-time.
    "ColorPicker": frozenset({"value", "disabled"}),
    # Même verdict que TimePicker, et pour la même raison : min/max
    # ne sont one-way que sur la contrainte croisée d'un RANGE.
    "MonthPicker": frozenset({"value", "disabled"}),
    "WeekPicker": frozenset({"value", "disabled"}),
    "Input": frozenset({"value", "disabled", "readonly"}),
    "Textarea": frozenset({"value", "disabled", "readonly"}),
    "NumberInput": frozenset({"value", "disabled"}),
    "Checkbox": frozenset({"checked", "disabled"}),
    "Switch": frozenset({"checked", "disabled"}),
    "Radio": frozenset({"disabled"}),
    "RadioGroup": frozenset({"value", "disabled"}),
    "Select": frozenset({"value", "disabled"}),
    "Combobox": frozenset({"value", "disabled"}),
    "ToggleGroup": frozenset({"value", "disabled"}),
    "ToggleButton": frozenset({"disabled"}),
    "Slider": frozenset({"value", "disabled"}),  # min/max bakés statiques → ∅
    "DatePicker": frozenset({"value", "min", "max", "disabled"}),
    "DateRangePicker": frozenset({"value", "min", "max", "disabled"}),
    "Calendar": frozenset({"value", "month", "min", "max", "disabled"}),
    "FileUpload": frozenset({"disabled"}),  # multiple/accept/required coupés
    # La data-URL du tracé : le CLIENT l'écrit (il dessine), donc ⇄
    # two-way — et l'invariant ``TWO_WAY_PROPS ⊆ BINDABLE_PROPS``
    # l'impose dès lors que la prop est form-bound. ``placeholder`` /
    # ``clear_label`` sont du texte design-time, ``disabled`` un flag
    # d'affordance → ∅. ⚠️ Y lier un ``ClientState`` se paie (le
    # snapshot part ENTIER à chaque POST, et un PNG pèse) — c'est un
    # avertissement de docstring, pas une interdiction d'API.
    "SignaturePad": frozenset({"value"}),
    "Form": frozenset(),
    "FormField": frozenset({"error", "hint"}),
    # ── Overlay ──────────────────────────────────────────────────────
    "Dialog": frozenset({"open"}),
    "Drawer": frozenset({"open"}),
    "Dropdown": frozenset({"open"}),
    "Popover": frozenset({"open"}),
    "DropdownItem": frozenset({"disabled"}),
    "Tooltip": frozenset({"text"}),
    # ── Navigation ───────────────────────────────────────────────────
    "Tabs": frozenset({"value"}),
    "Tab": frozenset(),
    "TabPanel": frozenset(),
    # L'index courant EST édité en cliquant une pastille → two-way.
    # ``orientation`` / ``clickable`` / ``size`` / ``color`` sont de la
    # config de design : aucun driver client, donc ∅.
    "Stepper": frozenset({"value"}),
    # ``status`` / ``disabled`` sont design-time : le statut se DÉRIVE de
    # l'index du parent, une binding par étape voudrait dire N bindings
    # pour la même information.
    "Step": frozenset(),
    "StepPanel": frozenset(),
    "Pagination": frozenset({"value", "disabled"}),  # total_pages coupé
    "Sidebar": frozenset({"open"}),
    "SidebarItem": frozenset({"active", "badge", "disabled"}),
    "SidebarFooterItem": frozenset({"disabled"}),
    "SidebarSection": frozenset(),
    "SidebarTitle": frozenset(),
    # Rien a lier : le declencheur ne PORTE aucun etat, il en commande un
    # autre. Ce qui se lie, c'est le ``open`` de la barre qu'il pilote.
    "SidebarTrigger": frozenset(),
    "SidebarFooter": frozenset(),
    "BottomBar": frozenset(),
    "BottomBarItem": frozenset({"active", "badge", "disabled"}),
    "Navbar": frozenset(),
    "NavbarItem": frozenset({"active", "badge", "disabled"}),
    "NavbarSection": frozenset(),
    "Breadcrumb": frozenset(),
    # Porteur de métadonnées : c'est ``Breadcrumb`` qui rend le segment
    # (lui seul sait lequel est le dernier), donc rien à piloter côté
    # client — même surface que ``Tab`` et ``Step``.
    "BreadcrumbItem": frozenset(),
    # ── Feedback ─────────────────────────────────────────────────────
    "Alert": frozenset({"title", "message"}),  # dismissible coupé
    "Banner": frozenset({"title", "message"}),  # dismissible coupé
    "Badge": frozenset({"label"}),  # dismissible coupé
    "Avatar": frozenset({"status"}),  # src/initials coupés
    "Progress": frozenset({"value", "label"}),
    "EmptyState": frozenset({"title", "description"}),
    "Skeleton": frozenset(),
    # ── Data ─────────────────────────────────────────────────────────
    "Table": frozenset(),
    # Toute la requête (tri / page / recherche) vit dans un DatatableState
    # serveur : un clic mute l'état, le @refreshable englobant re-rend avec
    # la requête cuite. Aucun driver client → aucune prop bindable.
    "Datatable": frozenset(),
    # `value` = le nœud sélectionné. Le pilote client est le clic sur un
    # nœud, donc le premier temps du test de la règle répond oui : « la
    # sélection → ⇄ two-way ».
    #
    # `focus`, lui, reste STATIQUE et c'est le même test qui le dit :
    # resserrer change les nœuds DESSINÉS, donc le placement — que seul
    # le serveur calcule. Aucun pilote client ne peut le produire.
    "Diagram": frozenset({"value"}),
    "Tree": frozenset({"value"}),
    "TreeNode": frozenset(),
    "Accordion": frozenset({"value"}),
    "AccordionItem": frozenset(),
    # ── Charts (data via @refreshable) ───────────────────────────────
    "BarChart": frozenset(),
    "LineChart": frozenset(),
    "PieChart": frozenset(),
    "ScatterChart": frozenset(),
    "Sparkline": frozenset(),
    # ── Primitives ───────────────────────────────────────────────────
    "Heading": frozenset({"text"}),
    "Text": frozenset({"text"}),
    "Icon": frozenset({"name"}),
    "Code": frozenset({"text"}),
    # Aucune, et c'est une décision de SÉCURITÉ, pas une omission : une
    # binding path sur du balisage brut ferait écrire du HTML au runtime
    # depuis l'état client — un puits à XSS piloté par le client. Le
    # constructeur lève plutôt que de dégrader.
    "Html": frozenset(),
    # Aucune : ``src`` change quand les données du serveur changent (donc
    # au re-rendu d'un ``@refreshable``), jamais sous un driver client —
    # même raisonnement que ``Avatar.src``, qui est design-time pour la
    # même raison. ``ratio`` / ``fit`` / ``alt`` sont des décisions de
    # rendu, pas des valeurs qui vivent.
    "Image": frozenset(),
    # Aucune, même raison qu'``Image`` : une source média change au
    # re-rendu serveur, jamais sous un driver client.
    "Video": frozenset(),
    # Une URL d'embed change au re-rendu serveur ; et laisser un driver
    # client réécrire le ``src`` d'un cadre sandboxé serait un moyen
    # commode de le pointer ailleurs.
    "Iframe": frozenset(),
    "Audio": frozenset(),
    "Divider": frozenset({"label"}),
    "Spinner": frozenset(),
    "Markdown": frozenset(),
    # ── Layout ───────────────────────────────────────────────────────
    # Seul composant de layout à porter un état : l'index de la slide
    # courante EST édité par l'utilisateur en faisant défiler la piste
    # → ⇄ two-way. ``per_view`` / ``autoplay`` / ``gap`` sont de la
    # config de design, aucun driver client → ∅.
    "Carousel": frozenset({"value"}),
    # La famille DnD ne porte AUCUNE valeur : une zone reçoit des
    # événements, un item est déplacé. Ce qui bouge — l'ordre de la
    # liste — est de l'état SERVEUR, muté par le handler ``on_move``.
    # Le seul état client est le geste lui-même, qui vit dans le
    # runtime et ne dure pas au-delà du drop → ∅ des deux côtés.
    "Dropzone": frozenset(),
    "Draggable": frozenset(),
    # Le partage des panneaux EST édité par l'utilisateur, en tirant une
    # poignée — driver client au sens strict de la règle → ⇄ two-way.
    # ``orientation`` / ``disabled`` / ``size`` sont de la config de
    # design, et ``min_size`` (sur le panneau) une contrainte : aucun
    # driver client, donc ∅ des deux côtés.
    "Resizable": frozenset({"sizes"}),
    "ResizablePanel": frozenset(),
    "Card": frozenset(),
    "Container": frozenset(),
    "Flex": frozenset(),
    "VStack": frozenset(),
    "HStack": frozenset(),
    "Grid": frozenset(),
    # Les deux régions du modèle « écran gelé » : de la disposition pure,
    # rien qu'un driver client aurait à piloter.
    "Viewport": frozenset(),
    "Pane": frozenset(),
    # ── Meta ─────────────────────────────────────────────────────────
    "Outlet": frozenset(),
    "Title": frozenset(),
    "MetaTag": frozenset(),
    "Interval": frozenset(),
    "Fragment": frozenset(),
}

_LIVE = {c.__name__: c for c in public_component_classes()}


def test_no_component_is_missing_from_the_snapshot() -> None:
    """Un nouveau ``ui.foo`` doit gagner une ligne ici (verdict explicite)."""
    missing = sorted(set(_LIVE) - set(_EXPECTED))
    assert not missing, (
        f"{missing} sont exposés sur `ui` mais absents de `_EXPECTED` — "
        f"décide leur surface bindable (règle « driver client, sinon "
        f"serveur »), ajoute la ligne ici — le funnel se régénère seul."
    )


def test_snapshot_has_no_stale_entries() -> None:
    """Une ligne qui ne correspond plus à aucun composant = à retirer."""
    stale = sorted(set(_EXPECTED) - set(_LIVE))
    assert not stale, (
        f"{stale} sont dans `_EXPECTED` mais n'existent plus sur `ui` — "
        f"composant renommé/retiré : nettoie la ligne ici."
    )


@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_bindable_surface_matches_snapshot(name: str) -> None:
    cls = _LIVE.get(name)
    if cls is None:
        pytest.skip(f"{name} absent — couvert par test_snapshot_has_no_stale_entries")
    actual = frozenset(getattr(cls, "BINDABLE_PROPS", ()) or ())
    assert actual == _EXPECTED[name], (
        f"{name}.BINDABLE_PROPS = {sorted(actual)} ≠ snapshot figé "
        f"{sorted(_EXPECTED[name])}.\n"
        f"Si le changement est VOULU : applique la règle « driver client, "
        f"sinon serveur » (client-reactive-surface.md § La règle), mets à "
        f"jour `_EXPECTED` ici (la matrice du funnel se régénère) dans le "
        f"même commit. Sinon, c'est une dérive à corriger dans le composant."
    )


def test_the_sweep_is_not_vacuous() -> None:
    """Plancher : la surface vivante est bien découverte.

    Les deux tests d'écart (manquant / périmé) comparent l'instantané à
    ``_LIVE``. Si la découverte rendait zéro classe, ils seraient verts
    tous les deux en ayant comparé le vide au vide.
    """
    assert len(_LIVE) >= 90, (
        f"seulement {len(_LIVE)} composants publics découverts (97 le "
        f"2026-08-19) — l'instantané ne compare plus rien."
    )

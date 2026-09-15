"""Gate : le vocabulaire HTMX brut d'un composant est une liste FERMÉE.

Le charter (CLAUDE.md, principe 2) dit que la frontière transport est
runtime-only : un composant déclare un handler ``on_<event>=`` et compose
en directives ``bz-*``, et ``action_attrs`` pose le ``hx-post`` pour lui.
Quelques composants pilotent malgré tout le swap engine directement — et
le charter ajoute qu'« un nouveau composant qui en aurait besoin doit
d'abord pousser l'usage dans un helper runtime ou un primitive Bretzel ».

Cette phrase n'était gardée par rien. Deux conséquences, mesurées le
2026-08-08 :

- la liste écrite dans CLAUDE.md nommait cinq composants ; il y en avait
  **treize**, dont six jamais mentionnés (combobox, calendar,
  file_upload, number_input, toggle_group, et les deux ``_wiring``) ;
- ``ui.datatable`` a introduit ``hx-preserve`` — **un mot de vocabulaire
  neuf**, qui n'existe nulle part ailleurs dans le dépôt — sans que la
  discussion prévue par le charter ait lieu, parce que rien ne l'a
  déclenchée.

Ce que la gate fait : figer le couple (fichier, attributs). Ajouter un
``hx-`` quelque part la fait rougir, ce qui force à répondre à la
question du charter — helper partagé, ou exception assumée et inscrite
ici avec sa raison. Elle ne juge pas le code : elle rend le choix
visible.

L'égalité est stricte dans les deux sens. Retirer un usage sans retirer
son entrée rougit aussi, sinon la liste pourrit et finit par autoriser
plus que la réalité — le défaut même qu'elle corrige.
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict

from tests.consistency._discovery import COMPONENTS_DIR, parsed_sources

#: Un littéral qui EST un nom d'attribut HTMX. On lit l'AST plutôt que le
#: texte : une mention en commentaire ou en docstring décrit, elle
#: n'émet pas, et la confondre avec du code rendrait la gate
#: ininterprétable (c'est la moitié des occurrences).
_HX_ATTR = re.compile(r"hx-[a-z-]+")

#: L'état du 2026-08-08, fichier par fichier, avec ce que chacun pilote.
#:
#: Les deux premiers sont le SOCLE du transport : c'est ``action_attrs``
#: qui pose le ``hx-post`` d'un ``on_<event>=``, et ``_wiring`` qui le
#: relocalise sur le bon porteur. Ils ne sont pas des exceptions, ils
#: sont l'implémentation de la règle.
_ALLOWED: dict[str, set[str]] = {
    # ── Socle transport ────────────────────────────────────────────────
    "base/events.py": {"hx-post", "hx-swap", "hx-target", "hx-trigger",
                       "hx-vals"},
    "base/_wiring.py": {"hx-post", "hx-swap", "hx-target", "hx-trigger",
                        "hx-vals"},
    "inputs/_wiring.py": {"hx-post", "hx-vals"},
    # Nav partielle boostée (sidebar + navbar passent par là).
    "navigation/_wiring.py": {"hx-get", "hx-push-url", "hx-swap",
                              "hx-target"},
    # ── Composants qui pilotent le swap engine ─────────────────────────
    # ``ui.table`` est SORTI de cette liste le 2026-09-06. Il y était
    # pour une garde que ``action_attrs`` « ne savait pas exprimer » —
    # sauf que le routeur partagé, lui, la connaissait déjà : il
    # l'appliquait à sa part CLIENTE et pas à la sienne. La garde est
    # remontée dans ``item_action_attrs``, et le composant n'écrit plus
    # une ligne d'HTMX.
    # ``ui.diagram`` est SORTI de cette liste le 2026-09-07, pour la
    # même raison que ``ui.table`` la veille : la garde d'enfant
    # interactif vit maintenant dans ``item_action_attrs``, et les deux
    # composants l'appellent au lieu de la recopier. Ils n'écrivent plus
    # une ligne d'HTMX. Les deux entrées disaient « ``action_attrs`` ne
    # sait pas exprimer ce filtre » — c'était vrai du niveau du dessous,
    # et faux du routeur qu'ils auraient dû appeler.
    # Le champ caché du panneau porte la valeur : une <div> ne poste
    # aucun descendant, d'où le ``hx-include``.
    "inputs/combobox/combobox.py": {"hx-include", "hx-post", "hx-trigger"},
    "inputs/radio/radio.py": {"hx-include", "hx-post"},
    # Ces quatre LISENT le bundle déjà posé pour le router (``hx-trigger``
    # dit quel event le handler écoute) — ils n'en écrivent pas.
    "inputs/calendar/calendar.py": {"hx-post", "hx-trigger"},
    "inputs/file_upload/file_upload.py": {"hx-post", "hx-trigger"},
    "inputs/number_input/number_input.py": {"hx-trigger"},
    "inputs/toggle_group/toggle_group.py": {"hx-trigger"},
    # Les DEUX mots de transport d'un formulaire, tous deux DÉRIVÉS — ni
    # l'un ni l'autre n'est une prop, donc aucun appelant ne les écrit :
    #
    #   hx-boost    : un <form> boosté serait navigué par htmx au lieu
    #                 d'être posté ;
    #   hx-encoding : un formulaire qui CONTIENT un fichier doit s'encoder
    #                 en multipart, sinon htmx URL-encode le corps et le
    #                 fichier disparaît sans un mot (mesuré le 2026-08-19 :
    #                 le mode formulaire de ``ui.file_upload`` était
    #                 entièrement muet). Le formulaire rend ses enfants
    #                 avant de composer ses attributs, donc il le SAIT — la
    #                 discussion que cette gate déclenche a eu lieu, et la
    #                 réponse est « pas de primitive » : il n'y a qu'un
    #                 ``ui.form`` dans le catalogue, et un helper appelé
    #                 depuis un seul site n'est pas un helper.
    "inputs/form/form.py": {"hx-boost", "hx-encoding"},
    # ⚠️ Les DEUX seuls mots hors du vocabulaire commun, tous deux
    # arrivés avec le datatable (août 2026) et tous deux sans passer par
    # la discussion que le charter prévoit — c'est ce qui a produit cette
    # gate. Le troisième arrivant devra, lui, trancher pour de bon :
    # ``preserve_shell()`` est un primitive qui manque, pas une
    # particularité de table.
    #
    #   hx-preserve : garder VIVANTE la barre d'outils quand aucun de ses
    #                 octets ne peut avoir changé (35 Ko sur 79 par clic
    #                 de pagination) ;
    #   hx-boost    : un téléchargement CSV est une navigation nue, htmx
    #                 essaierait de le swapper dans la page.
    "data/datatable/datatable.py": {"hx-boost", "hx-preserve"},
    # ``ui.link(download=True)`` — 2026-09-02. MÊME usage que la ligne
    # au-dessus, et c'est précisément pourquoi il entre ici plutôt que
    # de rester chez le datatable : un lien qui porte un FICHIER doit
    # dire à htmx de ne pas l'intercepter, sinon la coque va chercher
    # la cible en XHR et l'injecte dans le document — le CSV remplace
    # la page au lieu de se télécharger, sans erreur ni requête
    # échouée (mesuré sur `/meta` : ``resource_type: 'xhr'``).
    #
    # La gate a fait son travail en rougissant : elle a forcé à
    # constater que le datatable neutralisait ce mécanisme À LA MAIN
    # depuis des mois, et que le remède devait donc remonter dans un
    # primitive plutôt que d'être recopié une deuxième fois. C'est ce
    # qu'elle demande dans son message, et c'est ce qui a été fait.
    "actions/link/link.py": {"hx-boost"},
}


#: Plancher du balayage composants — meme valeur que ``_SWEEP_FLOOR``,
#: qui garde deja les gates d'interdiction de ce repertoire.
_COMPONENTS_FLOOR = 180


def _actual() -> dict[str, set[str]]:
    """``{chemin relatif: attributs hx- écrits en littéral}``."""
    found: dict[str, set[str]] = defaultdict(set)
    for source in parsed_sources(COMPONENTS_DIR, floor=_COMPONENTS_FLOOR):
        path, tree = source.path, source.tree
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _HX_ATTR.fullmatch(node.value):
                    rel = path.relative_to(COMPONENTS_DIR).as_posix()
                    found[rel].add(node.value)
    return dict(found)


def test_no_component_speaks_htmx_off_the_list() -> None:
    actual = _actual()
    new_files = sorted(set(actual) - set(_ALLOWED))
    assert not new_files, (
        f"{new_files} écrivent des attributs HTMX bruts sans figurer dans "
        f"l'allowlist. CLAUDE.md principe 2 : la frontière transport est "
        f"runtime-only, et un composant qui doit piloter le swap engine "
        f"lui-même « doit d'abord pousser l'usage dans un helper runtime "
        f"ou un primitive Bretzel ». Fais ce choix, puis inscris "
        f"l'exception ici AVEC SA RAISON."
    )
    widened = {
        name: sorted(attrs - _ALLOWED[name])
        for name, attrs in actual.items()
        if attrs - _ALLOWED[name]
    }
    assert not widened, (
        f"vocabulaire HTMX élargi sans discussion : {widened}. Même "
        f"question que ci-dessus — un mot neuf (``hx-preserve`` en est un) "
        f"mérite un primitive partagé plutôt qu'une ligne de plus."
    )


def test_the_allowlist_has_not_rotted() -> None:
    """Le sens inverse : une exception soldée doit SORTIR de la liste.

    Sans ça la liste autorise progressivement plus que la réalité, et le
    jour où quelqu'un réintroduit l'usage elle ne dit rien — exactement le
    défaut de la liste en prose de CLAUDE.md, qui nommait cinq fichiers
    pour treize.
    """
    actual = _actual()
    stale_files = sorted(set(_ALLOWED) - set(actual))
    assert not stale_files, (
        f"{stale_files} ne parlent plus HTMX brut — retire leur entrée de "
        f"`_ALLOWED`."
    )
    narrowed = {
        name: sorted(attrs - actual[name])
        for name, attrs in _ALLOWED.items()
        if name in actual and attrs - actual[name]
    }
    assert not narrowed, (
        f"ces attributs ne sont plus émis : {narrowed}. Retire-les de "
        f"`_ALLOWED` pour que la liste continue de décrire le réel."
    )


def test_the_sweep_is_not_vacuous() -> None:
    actual = _actual()
    assert len(actual) >= 10, (
        f"{len(actual)} fichier(s) trouvé(s) — le balayage AST ne lit plus "
        f"les composants, la gate est aveugle."
    )


def test_the_detector_still_bites() -> None:
    """Mutation : un attribut ``hx-*`` est encore reconnu.

    L'allowlist gèle QUI pilote le swap engine à la main. Si la regex
    cessait de matcher, l'allowlist ne verrait plus personne — et le
    prochain composant qui invente un mot de vocabulaire HTMX
    (``hx-preserve`` l'a fait) passerait sans que la décision soit prise.
    """
    for offending in ("hx-post", "hx-preserve", "hx-swap-oob", "hx-include"):
        assert _HX_ATTR.fullmatch(offending), f"{offending!r} devrait être vu"
    for licit in ("bz-on:click", "hxpost", "data-hx"):
        assert not _HX_ATTR.fullmatch(licit), f"{licit!r} : faux positif"

"""Gate : un composant n'émet que des ``bz-*`` que le runtime interprète.

Le moteur de directives est **générique**. Ses treize entrées — plus
``bz-id``, l'identité de scope — nomment des mécanismes de liaison
(``bz-show``, ``bz-attr:``, ``bz-effect``…), jamais un composant. C'est
ce qui fait que ``runtime.js`` reste un runtime et ne devient pas un
registre de widgets, et c'est l'invariant que cette gate tient.

Elle ferme une dette **ouverte depuis l'audit du 2026-07-13** : cet audit
avait trouvé 0 dérive fonctionnelle et conclu « il manque une gate qui
vérifie que les composants n'émettent que les 13 directives ». Six
semaines plus tard, personne ne l'avait écrite — et rien n'aurait
signalé qu'un composant se mette à poser un attribut que le runtime
ignore.

**Le mode d'échec est muet dans les deux sens.** Un ``bz-`` inventé ne
lève pas, ne s'affiche pas, ne casse aucun test : il part sur le fil et
rien ne le lit. Et l'inverse est aussi vrai — une directive retirée du
runtime laisserait des attributs orphelins dans vingt composants sans
qu'aucun ne rougisse.

⚠️ **Quatre familles distinctes partagent le préfixe ``bz-``**, et les
confondre fait paraître le dépôt sale alors qu'il ne l'est pas (mesuré :
un balayage naïf des sources remonte 32 faux positifs) :

1. les **directives** — les seules que cette gate surveille ;
2. les **événements** de l'API impérative (``bz-set``, ``bz-next``,
   ``bz-open``, ``bz-dropdown-pick``…), qui n'atteignent le DOM que sous
   ``bz-on:bz-set``, donc via une directive canonique ;
3. les **classes marqueur** (``bz-datatable``, ``bz-combobox``,
   ``bz-html``, ``bz-bar-axes``…) — des valeurs de ``class=``, pas des
   noms d'attributs ;
4. ``bz-calendar``, un custom element.

Seule la première est un nom d'ATTRIBUT — d'où une gate qui lit les
attributs du HTML RENDU plutôt que les chaînes des sources.

**La liste de référence n'est pas écrite ici.** Elle est extraite de
``bretzel/runtime/_src/*.js`` — de ce que le runtime APPELLE
(``getAttribute``, ``hasAttribute``, ``startsWith``, ``===``), pas de sa
prose. Une liste recopiée dériverait, et c'est précisément la classe de
faute que ce dépôt répare partout ailleurs.
"""

from __future__ import annotations

import re

import pytest

from tests.consistency._discovery import (
    assert_runtime_sweep_is_not_vacuous,
    assert_sweep_is_not_vacuous,
    public_component_classes,
    rendered_html_of,
    runtime_slabs,
    strip_js_comments,
    ui_name_of,
)

#: Preuve de morsure : ``test_the_two_discoveries_still_bite`` fabrique
#: les deux dérives (un attribut inconnu, une directive disparue du
#: runtime) et vérifie que la comparaison les sépare du cas licite.
MUTATION_PROOF = "test_the_two_discoveries_still_bite"

#: Ce que le runtime FAIT d'un nom, pas ce qu'il en dit. Deux gardes,
#: parce qu'une seule suffit rarement : ``strip_js_comments`` ôte la
#: prose — ces modules commentent abondamment les mécanismes qu'ils
#: implémentent, **y compris ceux qu'on vient de retirer** — et le motif
#: ci-dessous ne reconnaît que des APPELS. Sans ça, la liste de référence
#: enflerait et la gate accepterait un nom que rien n'interprète.
_READS = re.compile(
    r'(?:startsWith|hasAttribute|getAttribute|removeAttribute)'
    r'\(\s*"(bz-[a-z0-9:-]+)"'
    r'|===\s*"(bz-[a-z0-9:-]+)"'
)

#: Le nom d'un attribut dans le HTML sérialisé.
_ATTR = re.compile(r'\s(bz-[a-z0-9:_-]+)=')

#: Les composants qui ne se construisent pas hors d'un vrai rendu. Table
#: NOMMÉE, pas un plafond chiffré : « pas plus d'un » laisserait passer
#: « un qui sort, un qui rentre ».
#:
#: ``rendered_html_of`` ne rend ``None`` que pour un composant que la
#: table partagée DÉCLARE avoir besoin d'un contexte ; toute autre erreur
#: remonte. C'est ce qui empêche un composant de sortir du balayage sans
#: que personne ne le sache.
ABSTENTIONS = {
    "link": "exige un contexte parent (déclaré dans CONSTRUCT)",
}


def runtime_vocabulary() -> dict[str, set[str]]:
    """``{nom lu par le runtime: fichiers où il est lu}``.

    Les deux entrées à deux-points (``bz-on:`` / ``bz-attr:``) sont des
    PRÉFIXES : le runtime les teste avec ``startsWith`` puis lit
    l'argument qui suit.

    ``runtime_slabs`` plutôt qu'un ``glob`` maison : trois gates
    écrivaient ce chemin à la main, et une copie devient silencieusement
    vacuoise le jour où ``_src/`` bouge.

    ⚠️ Et la lecture **lève** — pas d'``errors="replace"``. Un module
    illisible doit faire rougir, pas sortir du balayage en silence :
    c'est ce que ``test_no_gate_swallows_a_file`` exige, et il m'a
    attrapé ici.
    """
    out: dict[str, set[str]] = {}
    for path in runtime_slabs():
        text = strip_js_comments(path.read_text(encoding="utf8"))
        for match in _READS.finditer(text):
            name = match.group(1) or match.group(2)
            out.setdefault(name, set()).add(path.name)
    return out


def emitted_names() -> dict[str, set[str]]:
    """``{nom d'attribut bz-*: composants qui l'émettent}``."""
    out: dict[str, set[str]] = {}
    for cls in public_component_classes():
        html = rendered_html_of(cls)
        if html is None:
            continue
        for name in _ATTR.findall(html):
            out.setdefault(name, set()).add(ui_name_of(cls))
    return out


def unknown_names(
    emitted: dict[str, set[str]], vocabulary: dict[str, set[str]]
) -> dict[str, set[str]]:
    """Ceux qu'aucune entrée du runtime ne réclame."""
    exact = {n for n in vocabulary if not n.endswith(":")}
    prefixes = tuple(n for n in vocabulary if n.endswith(":"))
    return {
        name: who
        for name, who in emitted.items()
        if name not in exact and not name.startswith(prefixes)
    }


VOCABULARY = runtime_vocabulary()
EMITTED = emitted_names()


# ── Les planchers ─────────────────────────────────────────────────────
#
# Deux découvertes, donc deux planchers. Chacun lit la découverte de
# CETTE gate, pas une source fraîche : un plancher qui recompte depuis
# son propre balayage reste vert quand on débranche celui de la gate.


def test_the_runtime_vocabulary_is_not_vacuous() -> None:
    assert_runtime_sweep_is_not_vacuous()
    assert len(VOCABULARY) >= 12, sorted(VOCABULARY)
    # Les deux formes doivent être reconnues. Sans les préfixes, chaque
    # événement et chaque attribut réactif du dépôt serait compté comme
    # inconnu ; sans les exacts, la moitié du moteur sort de la
    # référence.
    assert any(n.endswith(":") for n in VOCABULARY), (
        "aucun PRÉFIXE lu — ``bz-on:`` / ``bz-attr:`` sont sortis de "
        "l'extraction"
    )
    assert {"bz-data", "bz-show", "bz-effect"} <= set(VOCABULARY)


def test_the_component_sweep_is_not_vacuous() -> None:
    assert_sweep_is_not_vacuous()
    rendered = [
        c for c in public_component_classes() if rendered_html_of(c) is not None
    ]
    assert len(rendered) >= 90, len(rendered)
    assert len(EMITTED) >= 40, sorted(EMITTED)


def test_abstentions_are_declared() -> None:
    """Ni un composant qui sort du balayage en silence, ni une entrée qui
    pourrit parce qu'il y est rentré."""
    measured = {
        ui_name_of(c)
        for c in public_component_classes()
        if rendered_html_of(c) is None
    }
    assert measured == set(ABSTENTIONS), (
        f"abstentions mesurées {sorted(measured)}, déclarées "
        f"{sorted(ABSTENTIONS)}. Un composant qui cesse de se construire "
        f"sort du balayage sans rien casser."
    )


# ── L'interdiction ────────────────────────────────────────────────────


def test_no_component_emits_an_uninterpreted_directive() -> None:
    unknown = unknown_names(EMITTED, VOCABULARY)
    assert not unknown, (
        "Attribut(s) ``bz-*`` qu'aucune entrée du runtime ne lit :\n"
        + "\n".join(f"  {n}  ← {sorted(w)}" for n, w in sorted(unknown.items()))
        + "\n\nUn tel attribut part sur le fil et rien ne l'interprète : "
        "il ne lève pas, ne s'affiche pas, et ne casse aucun test. Soit "
        "c'est une faute de frappe, soit le runtime doit apprendre à le "
        "lire — et alors c'est une décision de VOCABULAIRE, pas un "
        "détail de composant (cf. l'en-tête)."
    )


@pytest.mark.parametrize("name", sorted(VOCABULARY))
def test_every_runtime_entry_is_still_used(name: str) -> None:
    """Le versant inverse : une directive que PLUS AUCUN composant n'émet.

    Ce n'est pas une faute en soi — c'est le signe qu'une primitive est
    morte, ou qu'un composant a cessé de l'émettre sans qu'on le veuille.
    Dans les deux cas quelqu'un doit trancher, plutôt que la laisser
    pourrir jusqu'au prochain audit.

    ⚠️ L'exemption est NOMMÉE et **tenue à un seul nom**. Elle en
    comptait deux à la première écriture : j'y avais mis ``bz-for`` en
    le croyant sans emploi, sur la foi d'une note de
    ``client-reactive-surface.md`` § B.3 — or les gabarits de pastilles
    de Combobox et Select l'émettent, et le balayage le voit. Une
    exemption de trop est une directive qui cesse d'être surveillée.
    """
    # ``bz-if`` : primitive du runtime que le dépôt n'utilise nulle part
    # (vérifié le 2026-08-28 — zéro occurrence dans ``bretzel/components/``).
    # C'est cohérent avec le modèle : le serveur re-rend, donc une branche
    # conditionnelle se décide en Python, pas dans le DOM. Elle reste comme
    # échappatoire. Si elle trouve un emploi, RETIRE-LA d'ici.
    unused_by_design = {"bz-if"}
    if name in unused_by_design:
        return
    if name.endswith(":"):
        used = any(n.startswith(name) for n in EMITTED)
    else:
        used = name in EMITTED
    assert used, (
        f"{name} est lu par le runtime mais plus aucun composant ne "
        f"l'émet. Soit c'est du code mort côté runtime, soit un composant "
        f"a cessé de l'émettre — dans les deux cas quelqu'un doit "
        f"trancher plutôt que le laisser pourrir."
    )


# ── La preuve de morsure ──────────────────────────────────────────────


def test_the_two_discoveries_still_bite() -> None:
    """Les deux dérives fabriquées, plus le versant licite."""
    vocab = {"bz-show": {"x.js"}, "bz-on:": {"x.js"}}

    # ① un attribut qu'aucune entrée ne réclame
    assert unknown_names({"bz-option": {"combobox"}}, vocab) == {
        "bz-option": {"combobox"}
    }
    # ② une directive disparue du runtime rend orphelin ce qui l'émettait
    assert unknown_names({"bz-effect": {"dialog"}}, vocab) == {
        "bz-effect": {"dialog"}
    }
    # ③ le versant LICITE — il compte autant : sans lui, un détecteur qui
    #    rougirait sur TOUT passerait les deux assertions du dessus.
    assert (
        unknown_names(
            {"bz-show": {"a"}, "bz-on:click": {"b"}, "bz-on:bz-set": {"c"}},
            vocab,
        )
        == {}
    )

    # Contrôle POSITIF sur le vrai corpus : l'extraction reconnaît bien ce
    # que le runtime lit, au lieu de rendre une liste vide qui rendrait
    # l'interdiction verte par arithmétique.
    assert "bz-on:" in VOCABULARY and "bz-id" in VOCABULARY
    assert any(n.startswith("bz-on:") for n in EMITTED)

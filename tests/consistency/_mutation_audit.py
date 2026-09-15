"""Harnais de mutation — est-ce que les gates MORDENT ?

    py -m tests.consistency._mutation_audit            # tout
    py -m tests.consistency._mutation_audit slot       # filtre par substring

Le problème
-----------
Une gate verte prouve deux choses très différentes : « l'invariant tient »
ou « la gate ne regarde rien ». Ce dépôt a livré **trois** gates du second
genre, chacune verte pendant des mois :

- une cherchait le préfixe ``x-bz-prop:``, mort depuis le rebrand ``bz-`` ;
- ``test_palette_color_is_prefixed`` lisait ``_reactive_props`` au lieu de
  ``__reactive_props__`` : 0 composant sélectionné sur 76 ;
- ``test_bool_attr_is_single_sourced`` est née aveugle au dialecte
  concurrent qu'elle prétendait unifier.

Lire la regex d'une gate ne suffit pas. **Introduire la violation qu'elle
prétend interdire, et vérifier qu'elle rougit** — c'est la seule preuve.

Ce que la table apporte en plus
--------------------------------
Chaque entrée dit, en une ligne de code exécutable, **ce que la gate
interdit vraiment**. C'est de la documentation qu'on ne peut pas laisser
mentir : si la mutation cesse de faire rougir, soit la gate a régressé,
soit ce n'est plus ce qu'elle garde.

⚠️ Sécurité
-----------
Les mutations de fichier sont défaites en ``try/finally`` par restauration
du contenu SAUVEGARDÉ — jamais par ``git checkout``, qui détruirait du
travail non commité (erreur faite 5 fois sur ce dépôt). Le harnais refuse
de tourner si l'arbre a des modifications non commitées.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPONENTS = REPO / "bretzel" / "components"

# ⚠️ La console Windows est en cp1252 : un libellé contenant « → » tuait le
# run à la 16ᵉ mutation sur un UnicodeEncodeError — les six verdicts
# suivants et le résumé n'étaient jamais imprimés. Un harnais dont la
# sortie peut mourir en route ne rapporte pas ce qu'il a mesuré.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class Mutation:
    """Une violation à introduire, et la gate qui doit la voir."""

    gate: str
    """Nom du fichier de gate, sans le chemin."""

    what: str
    """Ce que la gate est censée interdire — en français, lisible."""

    target: Path
    """Fichier à muter."""

    mutate: Callable[[str], str]
    """Prend le contenu original, rend le contenu muté."""


def _append(snippet: str) -> Callable[[str], str]:
    return lambda src: src + snippet


def _replace(old: str, new: str) -> Callable[[str], str]:
    """Remplacement AGNOSTIQUE aux fins de ligne.

    ⚠️ Depuis que ``_read`` est byte-exact (``newline=""``), le contenu
    garde ses ``\\r\\n`` sur Windows — un motif écrit avec ``\\n`` dans
    cette table ne matcherait donc plus rien. On essaie les deux formes
    plutôt que d'imposer aux specs de connaître la plateforme.
    """

    def apply(src: str) -> str:
        for candidate, repl in ((old, new), (old.replace("\n", "\r\n"),
                                             new.replace("\n", "\r\n"))):
            if candidate in src:
                return src.replace(candidate, repl, 1)
        raise AssertionError(f"motif de mutation introuvable : {old!r}")

    return apply


CARD = COMPONENTS / "layout" / "card" / "card.py"
BUTTON = COMPONENTS / "actions" / "button" / "button.py"
COMPONENT = COMPONENTS / "base" / "component.py"
WIRING = COMPONENTS / "base" / "_wiring.py"


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        gate="test_no_alpine_dialect_survives.py",
        what="un composant écrit un attribut au dialecte Alpine mort",
        target=CARD,
        mutate=_append('\n\n_ZZ_MUT = {"@click": "a", "x-show": "b"}\n'),
    ),
    Mutation(
        gate="test_no_classvar_restates_the_default.py",
        what="un composant redéclare un défaut du socle",
        target=CARD,
        mutate=_replace(
            'THEME_KEY: ClassVar[str] = "card"',
            'THEME_KEY: ClassVar[str] = "card"\n    IS_CONTAINER: ClassVar[bool] = True',
        ),
    ),
    Mutation(
        gate="test_server_action_routing_is_shared.py",
        what="un composant route le bundle d'action serveur à la main",
        target=CARD,
        mutate=_append(
            "\n\nSERVER_ACTION_ATTRS = ()\n\n\ndef _zz_mut(root_attrs):\n"
            "    for ev_attr in SERVER_ACTION_ATTRS:\n"
            "        root_attrs.pop(ev_attr, None)\n"
        ),
    ),
    Mutation(
        gate="test_hidden_carrier_skeleton_is_shared.py",
        what="un composant écrit le squelette du porteur caché à la main",
        target=CARD,
        mutate=_append('\n\n_ZZ_MUT = {"type": "hidden", "bz-ref": "bzhidden"}\n'),
    ),
    Mutation(
        gate="test_bz_data_carries_data_not_code.py",
        what="un bz-data embarque un algorithme au lieu de données",
        target=CARD,
        mutate=_replace(
            'attrs = self.emit_attrs()',
            'attrs = self.emit_attrs()\n        attrs["bz-data"] = ('
            '"{zzRange() { const out = []; for (let i = 0; i < 10; i++) '
            '{ out.push(i * 2); } return out.filter(x => x > 2); }}")',
        ),
    ),
    Mutation(
        gate="test_bz_data_carries_data_not_code.py",
        what="un bz-data émet un littéral Python (True) dans du JS",
        target=CARD,
        mutate=_replace(
            'attrs = self.emit_attrs()',
            'attrs = self.emit_attrs()\n        '
            'attrs["bz-data"] = "{zz: True}"',
        ),
    ),
    Mutation(
        gate="test_component_contracts.py",
        what="ICON_SLOTS déclare un slot hors de NAMED_SLOTS",
        target=BUTTON,
        mutate=_replace(
            'ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon_left", "icon_right")',
            'ICON_SLOTS: ClassVar[tuple[str, ...]] = ("icon_left", "icon_right", "zz_ghost")',
        ),
    ),
    Mutation(
        gate="test_render_is_universals_wrapped.py",
        what="un composant échappe au wrap métaclasse",
        target=COMPONENT,
        mutate=_replace(
            "            def wrapped_render(self, _orig=original_render):",
            "            if name == 'Card':\n"
            "                return super().__new__(mcls, name, bases, namespace)\n"
            "            def wrapped_render(self, _orig=original_render):",
        ),
    ),
    Mutation(
        gate="test_attr_precedence_is_one_contract.py",
        what="les classes brutes cessent de composer avec classes=",
        target=COMPONENT,
        mutate=_replace(
            "    raw_cls = component._raw_class_str",
            "    raw_cls = \"\"  # ZZ MUTATION",
        ),
    ),
    Mutation(
        gate="test_root_slot_override_universal.py",
        what="slots={'root'} cesse d'être appliqué au wrap",
        target=COMPONENT,
        mutate=_replace(
            "    root_slot = (component._user_slots or {}).get(\"root\")",
            "    root_slot = None  # ZZ MUTATION",
        ),
    ),
    Mutation(
        gate="test_dismiss_scope_owns_its_panel.py",
        what="un scope de dismiss perd son bz-ref=bzpanel",
        target=COMPONENTS / "inputs" / "calendar" / "calendar.py",
        mutate=_replace('                "bz-ref": "bzpanel",\n', ""),
    ),
    Mutation(
        gate="test_bool_attr_is_single_sourced.py",
        what="un composant réintroduit le dialecte .toString()",
        target=CARD,
        mutate=_append('\n\n_ZZ_MUT = f"bz-attr:data-a=\\"(open).toString()\\""\n'),
    ),
    # ── Gates PRÉEXISTANTES ───────────────────────────────────────────
    # Celles-ci ne sont pas de moi : c'est là qu'est le risque réel, et
    # c'est pour elles que le harnais existe.
    Mutation(
        gate="test_reactive_classes_universal.py",
        what="classes=<ClientBinding> cesse d'atteindre le vrai root",
        target=COMPONENT,
        mutate=_replace(
            "    if component._classes_binding is not None and isinstance(node, Element):",
            "    if False and component._classes_binding is not None:  # ZZ MUTATION",
        ),
    ),
    Mutation(
        gate="test_no_manual_user_class_append.py",
        what="un composant ré-append classes= à la main (doublon)",
        target=CARD,
        mutate=_replace(
            'attrs = self.emit_attrs()',
            'attrs = self.emit_attrs()\n        '
            'parts.append(self._user_classes_str())',
        ),
    ),
    Mutation(
        gate="test_two_way_props.py",
        what="TWO_WAY_PROPS cesse d'être un sous-ensemble de BINDABLE_PROPS",
        target=COMPONENTS / "inputs" / "switch" / "switch.py",
        mutate=_replace(
            'BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("checked", "disabled")',
            'BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ("disabled",)',
        ),
    ),
    Mutation(
        gate="test_slot_never_orphans.py",
        what="un slot Component n'est plus détaché → rendu deux fois",
        target=COMPONENT,
        mutate=_replace(
            "    def adopt_slot(",
            "    def adopt_slot_ZZ_DISABLED(",
        ),
    ),
    Mutation(
        # ⚠️ Spec corrigé : la première version mutait ``_needs_identity``,
        # qui n'a RIEN à voir — cette gate garde le séparateur ``::`` du
        # wire-id entre les deux encodeurs. Verdict MUETTE au premier run,
        # donc, alors que la gate allait très bien. Un verdict MUETTE se
        # triage toujours : le spec est faux au moins aussi souvent que la
        # gate.
        gate="test_wire_id.py",
        what="les deux encodeurs de wire-id divergent sur le séparateur",
        target=COMPONENTS / "base" / "events.py",
        mutate=_replace(
            "_ACTION_ID_SEPARATOR = WIRE_ID_SEP",
            '_ACTION_ID_SEPARATOR = "##"  # ZZ MUTATION',
        ),
    ),
    Mutation(
        gate="test_theme_reads_are_resolved.py",
        what="un composant lit cls.THEME au lieu du thème résolu",
        target=CARD,
        mutate=_replace(
            "        theme = self._resolved_theme()",
            "        theme = self.THEME  # ZZ MUTATION",
        ),
    ),
    Mutation(
        # ⚠️ Spec corrigé : la première version ajoutait une méthode NO-OP,
        # qui ne changeait évidemment aucune taille. Le MUETTE était de moi.
        gate="test_size_reaches_slots.py",
        what="un slot hors table sizes gèle une taille",
        target=COMPONENTS / "actions" / "button" / "theme.py",
        # ⚠️ Le slot muté doit vivre dans ``theme["slots"]`` — la gate lit
        # là, pas à la racine du thème. Première version posée au mauvais
        # niveau : verdict MUETTE alors que la gate allait bien.
        mutate=_replace('"slots": {', '"slots": {\n        "zz_frozen": "h-10 px-4",'),
    ),
    Mutation(
        gate="test_sizes_are_distinct.py",
        what="deux tailles produisent les mêmes classes",
        target=COMPONENTS / "actions" / "button" / "theme.py",
        # ⚠️ 2ᵉ correction du même spec : insérer ``"xl"`` AVANT l'entrée
        # existante ne mutait rien — en littéral de dict Python, c'est la
        # DERNIÈRE occurrence d'une clé qui gagne. Il faut écraser
        # l'entrée réelle pour que ``xl`` et ``sm`` deviennent identiques.
        mutate=_replace(
            '"xl": "h-14 px-8 text-base gap-2.5",',
            '"xl": "h-8 px-3 text-sm gap-1.5",  # ZZ MUTATION',
        ),
    ),
    Mutation(
        gate="test_escape_attr_result_is_quoted.py",
        what="un escape_attr() n'est plus posé entre guillemets",
        target=WIRING,
        mutate=_append(
            '\n\ndef _zz_mut(v):\n    return f"data-x={escape_attr(v)}"\n'
        ),
    ),
    Mutation(
        gate="test_single_bretzel_error.py",
        what="une seconde hiérarchie d'erreur apparaît",
        target=CARD,
        mutate=_append("\n\nclass BretzelError(Exception):\n    pass\n"),
    ),
    Mutation(
        # ⚠️ Spec corrigé : la première version concaténait des chaînes.
        # Cette gate est un AST qui cherche un ``ast.JoinedStr`` — une VRAIE
        # f-string — précisément pour ne pas flagger la docstring de
        # ``path_of``, qui montre le motif comme contre-exemple. Elle
        # ignorait donc ma concaténation, à raison.
        gate="test_client_path_single_source.py",
        what="un composant reconstruit un chemin client en f-string",
        target=CARD,
        mutate=_replace(
            "        theme = self._resolved_theme()",
            "        theme = self._resolved_theme()\n        "
            '_zz = f"$bz.state.{self.id}"  # ZZ MUTATION',
        ),
    ),
)


def _read(path: Path) -> str:
    """Lecture BYTE-EXACTE — ``newline=""`` désactive la traduction des
    fins de ligne, donc ``_write(_read(p))`` ne modifie pas le fichier."""
    return path.read_text(encoding="utf8", newline="")


def _write(path: Path, content: str) -> None:
    """Écriture byte-exacte.

    ⚠️ Sans ``newline=""``, Python traduit ``\\n`` en ``\\r\\n`` sur
    Windows : le harnais restaurait un contenu IDENTIQUE mais avec des
    fins de ligne différentes, et laissait donc le fichier « modifié » aux
    yeux de git. Trouvé au premier run réel — la promesse de restauration
    n'était pas tenue à l'octet près.
    """
    with path.open("w", encoding="utf8", newline="") as fh:
        fh.write(content)


def _dirty_tree() -> list[str]:
    out = subprocess.run(
        ["git", "status", "--short"], cwd=REPO, capture_output=True, text=True
    ).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def _run_gate(gate: str) -> bool:
    """``True`` si la gate PASSE."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"tests/consistency/{gate}", "-q",
         "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return proc.returncode == 0


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else ""

    dirty = _dirty_tree()
    if dirty:
        print("REFUS : l'arbre a des modifications non commitées.")
        print("  Les mutations écrivent dans des fichiers réels ; une")
        print("  interruption laisserait ton travail dans un état douteux.")
        for ln in dirty[:10]:
            print(f"    {ln}")
        return 2

    selected = [m for m in MUTATIONS if needle in m.gate or needle in m.what]
    print(f"Harnais de mutation — {len(selected)} mutation(s)\n")

    mute, alive, broken = [], [], []
    for m in selected:
        original = _read(m.target)
        try:
            mutated = m.mutate(original)
        except AssertionError as exc:
            # Un spec dont le motif a bougé est un BUG DE LA TABLE, pas un
            # verdict sur la gate. Il se rapporte, il n'interrompt pas
            # l'audit — sinon une seule entrée périmée masque les 21
            # autres résultats (arrivé au premier run).
            broken.append((m, str(exc)))
            print(f"  [SPEC   ] {m.gate}")
            print(f"           {m.what}")
            print(f"           motif de mutation périmé — {exc}")
            continue
        try:
            _write(m.target, mutated)
            passed = _run_gate(m.gate)
        finally:
            # Restauration par CONTENU SAUVEGARDÉ, jamais git checkout,
            # et BYTE-EXACTE (cf. ``_write``).
            _write(m.target, original)

        verdict = "MUETTE" if passed else "mord"
        (mute if passed else alive).append(m)
        print(f"  [{verdict:6}] {m.gate}")
        print(f"           {m.what}")

    print(f"\n  mordent : {len(alive)} / {len(selected)}")
    if mute:
        print("\n  ⚠️ GATES MUETTES — elles laissent passer ce qu'elles")
        print("     prétendent interdire :")
        for m in mute:
            print(f"       {m.gate} — {m.what}")
    return 1 if (mute or broken) else 0


if __name__ == "__main__":
    raise SystemExit(main())

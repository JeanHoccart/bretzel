# API impérative des composants

Les méthodes d'instance pilotent un composant depuis une expression cliente :

```python
dialog = ui.dialog()
ui.button("Ouvrir", on_click=dialog.open())
```

Elles retournent une chaîne JavaScript consommable par un `on_*`. Elles ne
lisent jamais l'état du composant. Pour partager ou relire une valeur, fournir
un `ClientBinding` à la construction reste la source de vérité.

## Deux chemins d'écriture

Avec un binding, la méthode écrit dans ce binding. Sans binding, elle émet une
commande DOM vers l'instance :

```python
checkbox = ui.checkbox(checked=form.accepted)
ui.button("Accepter", on_click=checkbox.set(True))

dialog = ui.dialog()
ui.button("Ouvrir", on_click=dialog.open())
```

Le composant reçoit automatiquement un `id` stable lorsqu'une commande le
requiert. `_dispatch_command()` encode la valeur éventuelle dans
`CustomEvent.detail.value`.

## Inventaire actuel

`IMPERATIVE` sur chaque classe est la source de vérité. Utiliser
`bretzel describe <composant>` pour obtenir ses méthodes actuelles. Une liste
recopiée ici dériverait dès l'ajout d'une commande.

## Collision avec une prop

Une méthode comme `open()` ne peut pas remplacer le descripteur de la prop
`open=` sur la classe. Les composants concernés installent donc la méthode sur
l'instance (`self.open = self._imperative_open`). Les méthodes sans collision,
comme `Input.set()`, restent des méthodes de classe ordinaires. `IMPERATIVE`
doit énumérer les deux formes.

## Ajouter une commande

1. Implémenter la commande avec `_dispatch_command()` ou écrire dans le binding.
2. Ajouter son nom dans `IMPERATIVE`.
3. Faire écouter l'événement par le carrier réel du composant.
4. Tester le chemin avec binding et le chemin local lorsqu'ils existent.
5. Vérifier la fiche avec `bretzel describe <composant>`.

Les gates `test_imperative_classvar_is_complete.py` et
`test_imperative_methods_emit_valid_js.py` vérifient que la déclaration et les
méthodes restent cohérentes.

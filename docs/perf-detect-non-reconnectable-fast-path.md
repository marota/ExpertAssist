# Fast path pour `detect_non_reconnectable_lines` (upstream)

## Contexte

Le profilage de `setup_environment_configs_pypowsybl` sur la grille
PyPSA-EUR France 400 kV (113 MB .xiidm) a identifié
`env.network_manager.detect_non_reconnectable_lines()` comme le plus
gros contributeur du temps de `/api/config` : **2 856 ms sur 7 084 ms
(~40 %)** du total env setup.

## Cause racine

La fonction `expert_op4grid_recommender.utils.helpers_pypowsybl.detect_non_reconnectable_lines`
annonçait un "fast path global" (~0.6 s), mais son **check de
colonnes était incorrect** pour les versions actuelles de pypowsybl :

- Cherchait `connectable_id` + `node_id` dans `get_terminals()` →
  ces colonnes ne sont **pas populées** par pypowsybl.
- Cherchait `node1_id` + `node2_id` dans `get_switches()` → pypowsybl
  expose `node1` / `node2` (**sans suffixe `_id`**) quand
  `all_attributes=True` est demandé.

Conséquence : le fast path était du **dead code**. Toutes les invocations
tombaient sur le fallback qui appelle
`network.get_node_breaker_topology(vl_id)` **par voltage level impacté**
— **2 094 appels** sur France 400 kV pour ~255 non-reconnectables
détectés.

## Correction upstream (`expert_op4grid_recommender == 0.2.0.post2`)

Commit amont : `0fb4e62f`

### Changement clé

Au lieu d'utiliser `get_terminals()` (qui n'expose pas les colonnes
nécessaires), utiliser :

- `get_lines(all_attributes=True)` → expose `node1` / `node2` par
  endpoint de ligne
- `get_2_windings_transformers(all_attributes=True)` → idem pour trafos
- `get_switches(all_attributes=True)` → expose `node1` / `node2` des
  switches

Le `connectable_map` est bâti directement depuis ces colonnes en un seul
batch, sans passer par `get_node_breaker_topology()`.

### Fallback préservé

Si aucune colonne `node1` / `node2` n'est présente (grille purement
bus-breaker) OU si le fast path produit une `connectable_map` vide
(cas pathologique NaN partout), le code retombe sur l'ancien chemin
per-VL — préserve la compat rétrograde.

### Tests upstream ajoutés

`tests/test_detect_non_reconnectable_fast_path.py` (6 tests) :

- Détection correcte d'une ligne isolée des deux côtés (fast path).
- Non-détection quand un disconnector reste fermé (reconnectable).
- Ignore les lignes connectées des deux côtés.
- Fallback déclenché quand les colonnes `node*` manquent sur les
  switches (bus-breaker).
- Short-circuit quand aucun élément n'est déconnecté.
- Fallback déclenché quand le fast path produit un `connectable_map`
  vide (NaN partout).

Le test d'intégration existant (`test_environment_detection::test_non_reconnectable_detection_with_date`)
passe sur la petite grille node-breaker réelle — valide la correction
numérique avec physique réelle.

## Mesure sur la grille France 400 kV

| | Avant | Après | Δ |
|---|---|---|---|
| `detect_non_reconnectable_lines` | 3 239 ms | **683 ms** | **−2 556 ms** (**−78 %**) |
| 255 non-reconnectables détectés | ✓ | ✓ (0 diff) | — |
| Total env setup | 7 084 ms | 4 924 ms | **−2 160 ms** (−30 %) |

## Impact projeté sur Load Study

| | v10 | v13 attendu |
|---|---|---|
| `/api/config` | 15 966 ms | **~13.7 s** (−2.2 s) |
| 4 XHRs parallèles | ~1.4 s (slowest) | ~1.4 s (inchangé) |
| **Fin dernier XHR** | 17 384 ms | **~15.2 s** (−2.2 s) |
| **Load Study v6 → v13** | −28 % | **~−37 %** |

À confirmer avec trace v13.

## Pourquoi ça n'a pas été détecté plus tôt

Le profilage détaillé (étape par étape) n'était pas en place. Les
timings globaux montraient "env setup prend 6-10 s" sans breakdown
— facile de supposer que c'est tout de grid2op. Une fois le script
`profile_env_setup.py` écrit, `detect_non_reconnectable_lines` a
ressorti comme poste dominant et le fast path cassé a été identifié
en lisant son code.

## Dépendance

Co-Study4Grid requiert maintenant `expert_op4grid_recommender >= 0.2.0.post2`.

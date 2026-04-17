# Detection non-reconnectable lines différée en arrière-plan

## Contexte

L'analyse v10 a identifié `env.network_manager.detect_non_reconnectable_lines()`
comme le plus gros contributeur au temps de `/api/config` sur grandes grilles :
**2-10 s** sur France 400 kV. Cette détection est un walk topologique
(énumération des switches) sans load-flow ni mutation d'état. Son résultat
(typiquement 0-10 IDs de lignes) est consommé uniquement par
`run_analysis_step1` pour filtrer les actions de reconnexion inutiles.

## Observation clé

Entre la réponse `/api/config` et le premier `/api/run-analysis-step1`,
l'utilisateur passe :
- ~3-5 s à attendre le rendu client (Paint/Layout/Raster du SVG)
- **~5-15 s à inspecter le diagramme + choisir un contingency**

Soit **~8-20 s de temps serveur idle** pendant lequel la détection peut
tourner silencieusement. Couvre très largement les 2-10 s nécessaires.

## Design

### Upstream (`expert_op4grid_recommender >= 0.2.0.post2`)

`setup_environment_configs_pypowsybl()` gagne un paramètre
`skip_non_reconnectable_detection: bool = False`. Quand `True`, le bloc de
détection est sauté. Le résultat retourné contient uniquement la liste
CSV + `DELETED_LINE_NAME`. L'appel bas-niveau
`env.network_manager.detect_non_reconnectable_lines()` reste disponible
pour que le caller fasse la détection lui-même en arrière-plan.

Compat : défaut `False` → comportement identique aux 3 callers upstream.

### Co-Study4Grid

**Nouvelle méthode `prefetch_non_reconnectable_lines_async()`** sur
`RecommenderService` :

```python
def prefetch_non_reconnectable_lines_async(self):
    """Spawn a worker that runs the topology detection and merges the
    result into `_cached_env_context['lines_non_reconnectable']`."""
    # ... threading.Thread + daemon=True + swallow exceptions ...
```

**Nouveau drain `_drain_pending_non_reconnectable_detection(timeout=60)`** :
join le worker thread si encore vivant.

**`update_config`** :
- Passe `skip_non_reconnectable_detection=True` à l'upstream helper
- Appelle `self.prefetch_non_reconnectable_lines_async()` juste après
  la population de `_cached_env_context`

**Gardes variant-state** (`_ensure_n_state_ready`, `_ensure_n1_state_ready`) :
- Ajout de `self._drain_pending_non_reconnectable_detection()` après le
  drain du NAD prefetch
- Conserve l'invariant « après la garde, aucun thread background ne
  touche au Network partagé »

**`reset()`** :
- Drain le worker avant de zapper `_cached_env_context`, sinon un worker
  en vol écrit ses résultats dans le contexte de la PROCHAINE étude

## Timeline attendue

```
T=0            T=~14s (apres drop 2-10s) T=~14-20s                    T=~20-30s
│              │                         │                            │
│  /api/config │   rend diagramme        │   detect_non_reco worker   │   user picks contingency
│  (sans       │   (frontend render      │   tourne invisible         │   /api/run-analysis-step1
│  detect)     │   ~3-5s)                │   (2-10s)                  │   drain worker → use merged list
│              │                         │                            │
│              │   user inspects ~5-15s  │                            │
│              │                         │                            │
└──────────────┴─────────────────────────┴────────────────────────────┘
   gain:        worker finit typiquement bien avant step1,             step1 invariant : liste complete
   -2 à -10s    invisible à l'utilisateur                               (worker déjà terminé)
```

## Cas dégradés

### User fire step1 avant fin du worker

La garde `_ensure_n_state_ready()` appelle le drain (timeout 60 s) avant
de positionner le variant N. L'utilisateur attend au pire quelques
secondes — jamais plus que le coût qu'on a déjà économisé sur
`/api/config`. Net neutre dans ce pire cas.

### Worker crash (bug pypowsybl, fichier corrompu…)

`_worker` encapsulé dans `try/except`. Log un warning puis set l'event.
`_cached_env_context['lines_non_reconnectable']` conserve la liste CSV
(non vide si `non_reconnectable_lines.csv` est fourni). Analyse downstream
continue avec couverture légèrement dégradée des actions de reconnexion.

### Reset pendant run

`reset()` appelle `_drain_pending_non_reconnectable_detection()` AVANT
d'effacer `_cached_env_context`. Le worker termine (timeout 60 s) puis
`reset` continue. Pas de leak dans la nouvelle étude.

## Gain attendu

| Segment | v10 | v12 attendu |
|---|---|---|
| `/api/config` | 15 966 ms | **~8-14 s** (−2 à −10 s selon grille) |
| `/api/network-diagram` | 352 ms | ~350 ms (inchangé, cache NAD) |
| **Fin dernier XHR** | 17 384 ms | **~10-16 s** |

Le gain varie avec la grille : petite (~2 s détection) économise peu ;
France 400 kV (~10 s détection) gagne massivement.

## Invariants (testés)

**Upstream** (`tests/test_environment_pypowsybl.py`, 2 nouveaux tests) :
- `test_setup_environment_configs_runs_detection_by_default` — défaut
  conserve le comportement historique.
- `test_setup_environment_configs_skips_detection_when_flag_set` — avec
  le flag, `detect_non_reconnectable_lines()` n'est pas appelée.

**Co-Study4Grid**
(`test_recommender_service.py::TestPrefetchNonReconnectableLines`, 6 tests) :
- `test_noop_when_env_context_missing` — gracieux si pas d'env.
- `test_worker_merges_detected_lines_into_context` — merge correct.
- `test_worker_is_idempotent_on_duplicate_detection` — pas de doublon.
- `test_worker_swallows_exceptions_and_keeps_csv_list` — fail-safe.
- `test_ensure_n_state_ready_drains_the_worker` — garde draine.
- `test_reset_drains_the_worker_before_clearing_state` — pas de leak.

`TestUpdateConfigSharesNetworkWithGrid2op::test_update_config_injects_preloaded_network_into_upstream`
enrichi pour asserter également `skip_non_reconnectable_detection=True`.

## Ce qui n'est PAS changé

- **L'algorithme de détection lui-même** est inchangé (même méthode,
  même résultat).
- **`run_analysis_step1`** : aucune modif côté code d'analyse — il lit
  `lines_non_reconnectable` comme avant. La garde variant-state
  s'assure que la liste est complète.
- **Le NAD prefetch** : orthogonal, tourne en parallèle pendant
  `setup_environment_configs_pypowsybl` comme avant.
- **Endpoints HTTP** : aucun changement d'API.
- **Frontend** : aucun changement.

## Fichiers modifiés

### Upstream (`expert_op4grid_recommender`, commit `fc9a5bff`)

| Fichier | Changement |
|---|---|
| `expert_op4grid_recommender/environment_pypowsybl.py` | Paramètre `skip_non_reconnectable_detection: bool = False` sur `setup_environment_configs_pypowsybl`. Bloc de détection encapsulé dans `if not skip_non_reconnectable_detection:`. |
| `tests/test_environment_pypowsybl.py` | 2 nouveaux tests. |
| `pyproject.toml` | 0.2.0.post1 → 0.2.0.post2. |

### Co-Study4Grid

| Fichier | Changement |
|---|---|
| `expert_backend/services/recommender_service.py` | Nouveaux fields state `_non_reconnectable_detection_*`, méthodes `prefetch_non_reconnectable_lines_async()` et `_drain_pending_non_reconnectable_detection()`. `update_config` passe `skip=True` à l'upstream + spawn le worker. `_ensure_n_state_ready` / `_ensure_n1_state_ready` / `reset` drainent le worker. |
| `expert_backend/tests/test_recommender_service.py` | Nouvelle classe `TestPrefetchNonReconnectableLines` (6 tests). `TestUpdateConfigSharesNetworkWithGrid2op` enrichi pour asserter `skip=True`. |

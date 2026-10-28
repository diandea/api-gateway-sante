# Tests et résultats attendus

Trois niveaux de vérification : les tests unitaires (sans service démarré), les tests de bout
en bout à travers Kong (pile démarrée) et les sept scénarios de démonstration manuels.
Les sorties ci-dessous ont été obtenues dans la VM Vagrant le 21 octobre 2026.

---

## 1. Tests unitaires — `pytest -v tests/`

Résultat attendu : **`28 passed`** (un avertissement de dépréciation de Starlette est sans effet).
Pour l'agrégateur, les trois API sont simulées par un faux transport HTTP (`httpx.MockTransport`).

### `tests/test_services.py` — les 3 API isolément (10 tests)

| Test | Vérifie que… |
|---|---|
| `test_structure_existante` | `GET /structures/1` renvoie 200 et le code `CHU-YO` |
| `test_structure_inexistante_renvoie_404` | une structure inconnue renvoie 404 `STRUCTURE_NOT_FOUND` |
| `test_filtre_par_region` | le filtre `region=Centre` renvoie 3 structures |
| `test_stats_patients` | la structure 1 a 25 patients, répartis par sexe |
| `test_structure_sans_patient_donne_un_zero_reel` | la structure 5 renvoie 200 avec `total = 0` |
| `test_indicateurs_derniere_periode_par_defaut` | sans `periode`, la dernière (`2026-09`) est renvoyée |
| `test_null_metier_accompagne_de_sa_raison` | structure 4 : `null` justifié par `NON_APPLICABLE`, `deces = 0` |
| `test_structure_sans_indicateur_renvoie_404` | structure 5 : 404 `INDICATORS_NOT_FOUND` |
| `test_correlation_id_renvoye_ou_genere` | l'en-tête `X-Correlation-ID` est renvoyé, ou un UUID est créé |
| `test_mode_chaos_error` | en mode `error`, le service répond 500 mais `/health` reste à 200 |

### `tests/test_aggregator.py` — le composant d'agrégation (13 tests)

| Test | Situation simulée | Résultat attendu |
|---|---|---|
| `test_reponse_complete` | les 3 API répondent | 200, `COMPLET`, 3 sections `DISPONIBLE` |
| `test_valeurs_reellement_nulles_conservees` | `total = 0`, `deces = 0`, `null` métier | `COMPLET`, valeurs conservées, aucune erreur |
| `test_indicateurs_absents_ne_sont_pas_une_panne` | indicateurs : 404 | `COMPLET`, indicateurs `ABSENT` |
| `test_erreur_partielle_service_en_erreur_500` | patients : 500 | 200, `PARTIEL`, `UPSTREAM_ERROR` |
| `test_reponse_invalide` | indicateurs : HTML au lieu de JSON | `INVALID_RESPONSE` |
| `test_delai_depasse` | indicateurs : 5 s | `TIMEOUT`, réponse en moins de 1 s (délai réduit à 0,5 s) |
| `test_budget_global` | patients lent, budget global dépassé | `TIMEOUT` « Budget global » |
| `test_appels_en_parallele` | 3 API à 0,3 s chacune | réponse en moins de 0,7 s (et non 0,9 s) |
| `test_service_secondaire_injoignable` | indicateurs : connexion refusée | `PARTIEL`, `SERVICE_UNREACHABLE` |
| `test_tous_les_secondaires_indisponibles` | indicateurs et patients en panne | 200, structure `DISPONIBLE` |
| `test_service_principal_indisponible_503` | structures : connexion refusée | 503, `PRIMARY_SOURCE_UNAVAILABLE` |
| `test_structure_inexistante_404` | structures : 404 | 404, `STRUCTURE_NOT_FOUND` |
| `test_correlation_id_propage_aux_trois_services` | en-tête `demo-42` | identifiant reçu par les 3 API et renvoyé au client |

### `tests/test_contracts.py` — contrats d'API (5 tests)

| Test | Vérifie que… |
|---|---|
| `test_contrat_a_jour[structures \| patients \| indicateurs \| aggregator]` | chaque fichier de `contracts/` correspond exactement au code |
| `test_endpoint_dashboard_dans_le_contrat` | le contrat de l'agrégateur expose `/api/v1/dashboard/structures/{structure_id}` |

---

## 2. Tests de bout en bout — `bash tests/e2e_kong.sh`

À lancer pile démarrée. Le script passe par Kong (port 8000), provoque lui-même les pannes,
puis remet chaque service en état normal. Sortie attendue :

```text
1) Réponse complète — GET /dashboard/structures/1
  ✔ HTTP 200
  ✔ statut_agregation = COMPLET
  ✔ 3 sources DISPONIBLE
2) Données réellement nulles — structure 5 (aucun patient, aucun indicateur)
  ✔ HTTP 200 et COMPLET
  ✔ patients.total = 0 (zéro réel)
  ✔ indicateurs ABSENT (≠ INDISPONIBLE)
3) Structure inexistante — GET /dashboard/structures/999
  ✔ HTTP 404
4) Erreur partielle — API patients en erreur 500
  ✔ HTTP 200 et PARTIEL
  ✔ patients INDISPONIBLE / UPSTREAM_ERROR
5) Délai dépassé — API indicateurs lente (5 s)
  ✔ indicateurs TIMEOUT
  ✔ réponse en moins de 3 s
6) Indisponibilité — API indicateurs arrêtée
  ✔ PARTIEL / SERVICE_UNREACHABLE
7) Service principal arrêté — API structures arrêtée
  ✔ HTTP 503
8) Identifiant de corrélation généré par Kong (aucun en-tête envoyé)
  ✔ en-tête X-Correlation-ID présent
     -> <uuid>

Résultat : 14 réussis, 0 échoués
```

---

## 3. Scénarios de démonstration

Commandes à taper dans la VM (`vagrant ssh`, puis `cd /vagrant`) ou sur la machine (option A).
Dans un second terminal, `docker compose logs -f --tail 0 aggregator` affiche les journaux en direct.

| # | Commande | Résultat attendu (obtenu le 21/10/2026) |
|---|---|---|
| 1 | `curl -s localhost:8001/services \| jq '.data[].name'` | `structures-service`, `indicateurs-service`, `patients-service`, `aggregator-service` |
| 2 | `curl -s localhost:8000/api/v1/dashboard/structures/1 \| jq` | `COMPLET` ; 3 sources `DISPONIBLE` en 45 à 57 ms chacune |
| 3a | `curl -s localhost:8000/api/v1/dashboard/structures/4 \| jq '.indicateurs'` | `deces: 0` ; `taux_occupation_lits: null` avec `NON_APPLICABLE` |
| 3b | `curl -s localhost:8000/api/v1/dashboard/structures/5 \| jq '{statut_agregation, total_patients: .patients.donnees.total, indicateurs}'` | `COMPLET`, `total_patients: 0`, indicateurs `ABSENT` (`INDICATORS_NOT_FOUND`) |
| 4 | `_chaos` `error` sur le port 9002, puis `… /structures/1 \| jq '{statut_agregation, patients}'` | `PARTIEL`, patients `UPSTREAM_ERROR` « Le service a répondu HTTP 500 » |
| 5 | `_chaos` `slow` 5 s sur le port 9003, puis `time curl … /structures/1` | `PARTIEL`, indicateurs `TIMEOUT` ; `real 0m2.045s` |
| 6a | `docker compose stop indicateurs`, puis `… /structures/1` | `PARTIEL`, indicateurs `SERVICE_UNREACHABLE` |
| 6b | `docker compose stop structures`, puis `curl -si … \| head -n 1` | `HTTP/1.1 503 Service Unavailable`, `PRIMARY_SOURCE_UNAVAILABLE` |
| 7 | `curl -s -H "X-Correlation-ID: demo-jury" …` puis `docker compose logs \| grep demo-jury` | une ligne `kong`, 5 lignes `aggregator`, une ligne pour chacune des 3 API |

Après les scénarios 4 et 5 : renvoyer `{"mode":"normal"}` au même port. Après le scénario 6 :
`docker compose start indicateurs` et `docker compose start structures`.

Exemple complet du scénario 2 :

```json
{
  "structure_id": 1,
  "statut_agregation": "COMPLET",
  "correlation_id": "3d52870e-cb6f-4011-9fc7-c94f9893f91f",
  "structure":   { "statut": "DISPONIBLE", "donnees": { "code": "CHU-YO", "capacite_lits": 750, "...": "..." } },
  "indicateurs": { "statut": "DISPONIBLE", "donnees": { "periode": "2026-09", "consultations": 9655, "deces": 41, "...": "..." } },
  "patients":    { "statut": "DISPONIBLE", "donnees": { "total": 25, "par_sexe": { "F": 11, "M": 14 }, "...": "..." } },
  "sources": [
    { "service": "structures",  "statut": "DISPONIBLE", "http_status": 200, "duree_ms": 46.6 },
    { "service": "indicateurs", "statut": "DISPONIBLE", "http_status": 200, "duree_ms": 45.4 },
    { "service": "patients",    "statut": "DISPONIBLE", "http_status": 200, "duree_ms": 57.3 }
  ]
}
```

Les durées varient d'une machine à l'autre ; les statuts et les codes doivent être identiques.

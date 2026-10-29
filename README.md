# API Gateway d'agrégation — Système de santé

Projet du cours **Composants et services web** (Master 1, Université Joseph KI-ZERBO) — exercice 23.

Kong expose un point d'entrée unique devant trois API indépendantes (structures sanitaires,
patients fictifs, indicateurs agrégés) et un composant d'agrégation. Un seul appel,
`GET /api/v1/dashboard/structures/{id}`, renvoie la fiche d'une structure, ses indicateurs
et le résumé de ses patients. Si un service est lent ou en panne, la réponse reste utile et
indique précisément ce qui manque.

**Auteurs :** [DIANDE Abdou Nassiro, OUEDRAOGO Wend-Kouni Basile, OUEDRAOGO Sanata, WANDAOGO Salif, TIONON Filwende Michael] · **Enseignant :** [KY Fadel Oumar]

---

## Sommaire

1. [Architecture](#1-architecture)
2. [Contenu du dépôt](#2-contenu-du-dépôt)
3. [Prérequis](#3-prérequis)
4. [Installation](#4-installation)
5. [Vérifier l'installation](#5-vérifier-linstallation)
6. [Utilisation](#6-utilisation)
7. [Bases de données de test](#7-bases-de-données-de-test)
8. [Contrats d'API](#8-contrats-dapi)
9. [Configuration](#9-configuration)
10. [Tests et résultats attendus](#10-tests-et-résultats-attendus)
11. [Intégration continue](#11-intégration-continue)
12. [Documents du projet](#12-documents-du-projet)

---

## 1. Architecture

```
                    ┌──────────────────── Docker Compose ────────────────────────┐
                    │                                                            │
 Client ──► :8000   │  Kong 3.9 (DB-less)                                        │
 (curl, Postman)    │   ├─ /api/v1/dashboard   ──► aggregator ──┬──► structures  │
                    │   ├─ /api/v1/structures  ──► structures   ├──► indicateurs │
                    │   ├─ /api/v1/patients    ──► patients     └──► patients    │
                    │   └─ /api/v1/indicateurs ──► indicateurs   (en parallèle)  │
                    │  plugins : correlation-id · file-log (JSON) · rate-limiting │
                    └────────────────────────────────────────────────────────────┘
```

| Composant | Rôle | Technologie |
|---|---|---|
| **Kong** | Point d'entrée unique : routage, identifiant de corrélation, journaux, limitation de débit | Kong Gateway 3.9, mode DB-less |
| **aggregator** | Appelle les 3 API en parallèle et compose une réponse unique ; gère les erreurs partielles | Python 3.12, FastAPI, httpx |
| **structures** | Référentiel des structures sanitaires | Python 3.12, FastAPI |
| **patients** | Patients fictifs et statistiques par structure | Python 3.12, FastAPI |
| **indicateurs** | Indicateurs mensuels agrégés par structure | Python 3.12, FastAPI |

### Gestion des erreurs partielles

Chaque section de la réponse porte un `statut`, ce qui distingue une donnée **réellement nulle**
d'une donnée **indisponible** :

| Statut | Signification | `donnees` |
|---|---|---|
| `DISPONIBLE` | Le service a répondu ; un `0` ou un `null` dans les données est une vraie valeur | la réponse du service |
| `ABSENT` | Le service a répondu 404 : il n'existe rien | `null` + `motif` |
| `INDISPONIBLE` | Le service n'a pas pu répondre | `null` + `erreur.code` (`TIMEOUT`, `SERVICE_UNREACHABLE`, `UPSTREAM_ERROR`, `INVALID_RESPONSE`) |

| Situation | HTTP | `statut_agregation` |
|---|---|---|
| Les 3 sections DISPONIBLE ou ABSENT | 200 | `COMPLET` |
| Indicateurs et/ou patients INDISPONIBLE | 200 | `PARTIEL` |
| Structure inconnue | 404 | `ECHEC` |
| API structures indisponible | 503 | `ECHEC` |

**Délais emboîtés :** 2 s par appel de l'agrégateur, 3 s de budget global, 5 s de `read_timeout` dans Kong.
**Traçabilité :** l'en-tête `X-Correlation-ID` (créé par Kong) est propagé à tous les services et
présent dans chaque ligne de journal JSON.

---

## 2. Contenu du dépôt

```
api-gateway-sante/
├── aggregator/main.py             composant d'agrégation (endpoint dashboard)
├── services/
│   ├── structures/main.py         API 1 — structures sanitaires
│   ├── patients/main.py           API 2 — patients fictifs
│   └── indicateurs/main.py        API 3 — indicateurs agrégés
├── common/
│   ├── observability.py           journaux JSON, corrélation, /health, mode chaos
│   └── data.py                    chargement des bases de test
├── data/                          bases de test (JSON), montées en volume
├── scripts/
│   ├── init_data.py               création et initialisation des bases
│   └── export_openapi.py          export des contrats d'API
├── contracts/                     contrats OpenAPI 3 des 4 services
├── kong/kong.yml                  configuration déclarative de Kong
├── tests/
│   ├── test_services.py           tests unitaires des 3 API
│   ├── test_aggregator.py         tests unitaires de l'agrégateur
│   ├── test_contracts.py          cohérence code / contrats
│   └── e2e_kong.sh                tests de bout en bout à travers Kong
├── .github/workflows/ci.yml       intégration continue (GitHub Actions)
├── docs/
│   ├── INSTALLATION.md            installation de Docker, Vagrant, VirtualBox, Git
│   ├── RESULTATS_ATTENDUS.md      résultats attendus des tests et de la démonstration
│   ├── Procedure de test en local.txt   procédure de test en local
│   ├── Groupe4_Présentation_API_Gateway_agregation_sante.pptx   présentation
│   └── Groupe4_Rapport_API_Gateway_agregation_sante.pdf         rapport
├── Dockerfile                     image commune des 4 services Python
├── docker-compose.yml             les 5 conteneurs, leurs volumes et leur réseau
├── Vagrantfile                    VM Ubuntu 22.04 prête à l'emploi (option B)
├── requirements.txt               dépendances (versions figées)
└── requirements-dev.txt           dépendances de test
```

---

## 3. Prérequis

Deux façons d'installer le projet. Choisissez-en une.

| | Option A — Docker Compose | Option B — VM Vagrant |
|---|---|---|
| Pour qui | Machine qui a déjà Docker, ou Linux | Machine neuve, Windows ou macOS sans Docker |
| Logiciels | Git, Docker Engine ≥ 24 avec Compose v2 (ou Docker Desktop) | Git, VirtualBox 7, Vagrant ≥ 2.3 |
| Pour les tests | Python ≥ 3.10, `jq`, un shell bash (Linux, macOS, WSL) | rien de plus : tout est installé dans la VM |
| Ressources | 2 Go de RAM libres, 3 Go de disque | 4 Go de RAM libres, 10 Go de disque, virtualisation activée dans le BIOS |
| Réseau | Accès Internet au premier lancement (images Docker, paquets Python) | idem |

Ports utilisés sur la machine : **8000** (Kong), **8001** (administration Kong), **9000** (agrégateur),
**9001–9003** (accès direct aux API, tests uniquement). Ils doivent être libres.

La procédure d'installation de chaque outil (Docker, VirtualBox, Vagrant, Git) est décrite
séparément dans **[docs/INSTALLATION.md](docs/INSTALLATION.md)**.

---

## 4. Installation

### Option A — Docker Compose

```bash
git clone https://github.com/diandea/api-gateway-sante.git
cd api-gateway-sante
docker compose up -d --build --wait
```

`--wait` rend la main quand les 5 conteneurs sont `healthy` (environ 1 à 2 minutes la première fois).

### Option B — VM Vagrant (machine neuve)

Dans PowerShell (Windows) ou un terminal (macOS, Linux) :

```bash
git clone https://github.com/diandea/api-gateway-sante.git
cd api-gateway-sante
vagrant up
```

Le premier `vagrant up` (environ 10 minutes) crée une VM Ubuntu 22.04, y installe Docker, `jq`
et les dépendances de test, vérifie les bases puis démarre les 5 conteneurs. Pour travailler
dans la VM :

```bash
vagrant ssh
cd /vagrant
```

Les conteneurs redémarrent seuls après un redémarrage de la VM (`restart: unless-stopped`).
Commandes utiles : `vagrant halt` (arrêter), `vagrant up` (relancer), `vagrant destroy` (supprimer).

---

## 5. Vérifier l'installation

```bash
docker compose ps                                              # 5 conteneurs "Up (healthy)"
curl -s localhost:8001/services | jq '.data[].name'            # 4 services déclarés dans Kong
curl -s localhost:8000/api/v1/dashboard/structures/1 | jq '.statut_agregation'   # "COMPLET"
```

---

## 6. Utilisation

Toutes les requêtes passent par Kong sur le port **8000**.

| Méthode et chemin | Description |
|---|---|
| `GET /api/v1/dashboard/structures/{id}` | **Tableau de bord** : structure + indicateurs + patients |
| `GET /api/v1/structures` | Liste des structures (filtres `region`, `type`) |
| `GET /api/v1/structures/{id}` | Une structure |
| `GET /api/v1/patients` | Liste des patients (filtres `structure_id`, `statut`, `limit`) |
| `GET /api/v1/patients/{id}` | Un patient |
| `GET /api/v1/patients/stats?structure_id={id}` | Statistiques des patients d'une structure |
| `GET /api/v1/indicateurs` | Tous les indicateurs (filtre `periode`) |
| `GET /api/v1/indicateurs/structures/{id}` | Indicateurs d'une structure (dernière période, ou `periode=AAAA-MM`) |

Documentation interactive (Swagger) de l'agrégateur : <http://localhost:9000/docs>.

### Simuler des pannes

Chaque API accepte `POST /_chaos` en accès direct (ports 9001 à 9003) :

```bash
curl -X POST localhost:9003/_chaos -H 'Content-Type: application/json' -d '{"mode":"slow","delay":5}'  # lente
curl -X POST localhost:9002/_chaos -H 'Content-Type: application/json' -d '{"mode":"error"}'            # erreur 500
curl -X POST localhost:9002/_chaos -H 'Content-Type: application/json' -d '{"mode":"normal"}'           # retour à la normale
docker compose stop indicateurs      # vraie panne ; relancer avec : docker compose start indicateurs
```

### Suivre une requête

```bash
curl -s -H "X-Correlation-ID: demo-jury" localhost:8000/api/v1/dashboard/structures/1 > /dev/null
docker compose logs | grep demo-jury       # la requête dans Kong, l'agrégateur et les 3 API
```

---

## 7. Bases de données de test

Chaque API a sa propre base : un fichier JSON dans `data/`, monté **en lecture seule** dans
son conteneur (volume). Toutes les données sont **fictives**.

| Fichier | API | Contenu |
|---|---|---|
| `data/structures.json` | structures | 5 structures (CHU, CHR, CMA, 2 CSPS) |
| `data/patients.json` | patients | 58 patients générés (graine fixe) |
| `data/indicateurs.json` | indicateurs | 8 lignes : août et septembre 2026, structures 1 à 4 |

Cas de test volontaires : la **structure 4** a `deces = 0` (zéro réel) et des indicateurs
d'hospitalisation à `null` justifiés (`NON_APPLICABLE`) ; la **structure 5** n'a ni patient
ni indicateur publié ; la **structure 999** n'existe pas.

```bash
python3 scripts/init_data.py            # (re)crée les 3 bases et vérifie leur cohérence
python3 scripts/init_data.py --check    # vérifie sans rien écrire
docker compose restart structures patients indicateurs   # recharger après modification
```

---

## 8. Contrats d'API

Les contrats **OpenAPI 3** des quatre services sont dans `contracts/` :
`structures.openapi.json`, `patients.openapi.json`, `indicateurs.openapi.json`,
`aggregator.openapi.json`. Ils s'ouvrent dans <https://editor.swagger.io>, Postman ou Insomnia.

Ils sont générés depuis le code (`python3 scripts/export_openapi.py`) ; le test
`tests/test_contracts.py` échoue si le code et les contrats divergent.

---

## 9. Configuration

| Fichier | Rôle |
|---|---|
| `kong/kong.yml` | Services, routes et plugins de Kong (`correlation-id`, `file-log`, `rate-limiting`) |
| `docker-compose.yml` | Conteneurs, ports, volumes, variables d'environnement |
| `Vagrantfile` | VM : box Ubuntu 22.04, 3 Go de RAM, ports redirigés 8000, 8001, 9000 |

Variables d'environnement de l'agrégateur (dans `docker-compose.yml`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `STRUCTURES_URL`, `PATIENTS_URL`, `INDICATEURS_URL` | `http://<service>:8000` | Adresses des API |
| `UPSTREAM_TIMEOUT` | `2.0` | Délai maximal par appel (s) |
| `GLOBAL_TIMEOUT` | `3.0` | Budget total de l'agrégation (s), inférieur au `read_timeout` de Kong (5 s) |

Variable des 3 API : `DATA_DIR` (`/app/data`), dossier des bases.

---

## 10. Tests et résultats attendus

```bash
pip install -r requirements-dev.txt     # une fois (déjà fait dans la VM)
pytest -v tests/                        # 28 tests unitaires — aucun service à démarrer
bash tests/e2e_kong.sh                  # 14 vérifications à travers Kong — pile démarrée
```

Résultat attendu : **`28 passed`** puis **`Résultat : 14 réussis, 0 échoués`**.

Le détail de chaque test, des sept scénarios de démonstration et des sorties attendues est dans
**[docs/RESULTATS_ATTENDUS.md](docs/RESULTATS_ATTENDUS.md)**.

---

## 11. Intégration continue

`.github/workflows/ci.yml` s'exécute sur GitHub à chaque `push` : vérification des bases,
tests unitaires et contrats, puis démarrage de toute la pile avec Docker Compose et tests
de bout en bout à travers Kong. Le résultat est visible dans l'onglet **Actions** du dépôt.

---

## 12. Documents du projet

- [Présentation de la soutenance](docs/Groupe4_Présentation_API_Gateway_agregation_sante.pptx) — `docs/Groupe4_Présentation_API_Gateway_agregation_sante.pptx`
- [Rapport du projet](docs/Groupe4_Rapport_API_Gateway_agregation_sante.pdf) — `docs/Groupe4_Rapport_API_Gateway_agregation_sante.pdf` (conception, guide de démonstration, sorties obtenues)
- [Procédure de test en local](<docs/Procedure de test en local.txt>) — `docs/Procedure de test en local.txt`
- [Installation des outils](docs/INSTALLATION.md) et [résultats attendus](docs/RESULTATS_ATTENDUS.md)

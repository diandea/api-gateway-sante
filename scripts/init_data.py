"""
Création et initialisation des bases de données de test (données FICTIVES).

Chaque API possède sa propre base, un fichier JSON dans data/ :
    data/structures.json   -> API Structures sanitaires
    data/patients.json     -> API Patients fictifs
    data/indicateurs.json  -> API Indicateurs agrégés

Ce script est la source de vérité : il (re)crée les trois fichiers, puis
vérifie leur cohérence (identifiants uniques, structure_id existants).
La graine aléatoire est fixe : le résultat est identique à chaque exécution.

Usage :
    python3 scripts/init_data.py            # (re)crée data/
    python3 scripts/init_data.py --check    # vérifie sans rien écrire

Les fichiers sont montés en volume dans les conteneurs (docker-compose.yml) :
après une régénération, `docker compose restart structures patients indicateurs`
suffit pour recharger les données.
"""

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------------------
# Base 1 — Structures sanitaires
# ---------------------------------------------------------------------------
STRUCTURES = [
    {"id": 1, "code": "CHU-YO", "nom": "Centre Hospitalier Universitaire Yalgado Ouédraogo",
     "type": "CHU", "region": "Centre", "district": "Baskuy", "ville": "Ouagadougou",
     "capacite_lits": 750, "telephone": "+226 25 00 00 01", "statut": "public"},
    {"id": 2, "code": "CHR-KDG", "nom": "Centre Hospitalier Régional de Koudougou",
     "type": "CHR", "region": "Centre-Ouest", "district": "Koudougou", "ville": "Koudougou",
     "capacite_lits": 280, "telephone": "+226 25 00 00 02", "statut": "public"},
    {"id": 3, "code": "CMA-PSY", "nom": "Centre Médical avec Antenne chirurgicale de Pissy",
     "type": "CMA", "region": "Centre", "district": "Boulmiougou", "ville": "Ouagadougou",
     "capacite_lits": 60, "telephone": "+226 25 00 00 03", "statut": "public"},
    {"id": 4, "code": "CSPS-TGH", "nom": "Centre de Santé et de Promotion Sociale de Tanghin",
     "type": "CSPS", "region": "Centre", "district": "Nongr-Massom", "ville": "Ouagadougou",
     "capacite_lits": 0, "telephone": "+226 25 00 00 04", "statut": "public"},
    # Cas de test : structure récente, sans patient ni indicateur publié.
    {"id": 5, "code": "CSPS-NEW", "nom": "CSPS de Saaba (ouverture récente)",
     "type": "CSPS", "region": "Plateau-Central", "district": "Saaba", "ville": "Saaba",
     "capacite_lits": 0, "telephone": None, "statut": "public"},
]

# ---------------------------------------------------------------------------
# Base 2 — Indicateurs mensuels agrégés
# Cas de test : structure 4 (CSPS) -> deces = 0 (zéro réel) et indicateurs
# d'hospitalisation à null (non applicables) ; structure 5 -> aucune ligne.
# ---------------------------------------------------------------------------
_IND_COLS = ["structure_id", "periode", "consultations", "hospitalisations", "accouchements",
             "deces", "cas_paludisme", "taux_occupation_lits", "duree_moyenne_sejour_jours",
             "taux_couverture_vaccinale"]
_IND_ROWS = [
    (1, "2026-08", 9120, 1840, 410, 37, 2210, 86.4, 6.1, None),
    (1, "2026-09", 9655, 1912, 428, 41, 2540, 89.2, 6.4, None),
    (2, "2026-08", 4310, 702, 233, 12, 1405, 74.0, 4.8, 91.5),
    (2, "2026-09", 4580, 745, 241, 15, 1630, 78.3, 5.0, 92.1),
    (3, "2026-08", 2105, 188, 96, 2, 760, 62.5, 3.2, 88.0),
    (3, "2026-09", 2290, 201, 102, 0, 845, 66.0, 3.4, 89.4),
    (4, "2026-08", 1340, 0, 38, 0, 512, None, None, 95.2),
    (4, "2026-09", 1415, 0, 41, 0, 598, None, None, 96.0),
]
INDICATEURS = [dict(zip(_IND_COLS, row)) for row in _IND_ROWS]

# ---------------------------------------------------------------------------
# Base 3 — Patients fictifs (générés, graine fixe)
# ---------------------------------------------------------------------------
NOMS = ["Ouédraogo", "Sawadogo", "Compaoré", "Kaboré", "Traoré", "Zongo",
        "Ilboudo", "Kinda", "Nikiéma", "Sanou", "Diallo", "Yaméogo", "Somé", "Bationo"]
PRENOMS_F = ["Aminata", "Mariam", "Salimata", "Awa", "Fatimata", "Rasmata", "Adjaratou", "Pauline"]
PRENOMS_M = ["Issouf", "Boukary", "Adama", "Moussa", "Souleymane", "Hamidou", "Ousmane", "Paul"]
MOTIFS = ["Paludisme", "Infection respiratoire", "Consultation prénatale", "Diarrhée",
          "Hypertension", "Traumatisme", "Malnutrition", "Diabète", "Vaccination"]
STATUTS = ["ambulatoire", "hospitalise", "sorti"]
GROUPES = ["O+", "A+", "B+", "AB+", "O-", "A-"]
# Nombre de patients par structure ; la structure 5 n'en a aucun (total = 0 réel).
REPARTITION = {1: 25, 2: 15, 3: 10, 4: 8, 5: 0}
SANS_LITS = {4, 5}  # les CSPS n'hospitalisent pas


def generate_patients() -> list[dict]:
    rng = random.Random(2026)
    patients, n = [], 0
    for structure_id, count in REPARTITION.items():
        for _ in range(count):
            n += 1
            sexe = rng.choice(["F", "M"])
            naissance = date(2026, 1, 1) - timedelta(days=rng.randint(0, 85 * 365))
            statuts = ["ambulatoire", "sorti"] if structure_id in SANS_LITS else STATUTS
            patients.append({
                "id": f"PAT-{n:04d}",
                "nom": rng.choice(NOMS),
                "prenom": rng.choice(PRENOMS_F if sexe == "F" else PRENOMS_M),
                "sexe": sexe,
                "date_naissance": naissance.isoformat(),
                "groupe_sanguin": rng.choice(GROUPES),
                "structure_id": structure_id,
                "motif": rng.choice(MOTIFS),
                "statut": rng.choice(statuts),
                "date_admission": (date(2026, 9, 1) + timedelta(days=rng.randint(0, 45))).isoformat(),
            })
    return patients


# ---------------------------------------------------------------------------
# Vérifications de cohérence
# ---------------------------------------------------------------------------
def check(structures, patients, indicateurs) -> list[str]:
    errors = []
    ids = [s["id"] for s in structures]
    if len(ids) != len(set(ids)):
        errors.append("structures : identifiants en double")
    known = set(ids)
    if len({p["id"] for p in patients}) != len(patients):
        errors.append("patients : identifiants en double")
    for p in patients:
        if p["structure_id"] not in known:
            errors.append(f"patient {p['id']} : structure_id {p['structure_id']} inconnu")
    keys = [(i["structure_id"], i["periode"]) for i in indicateurs]
    if len(keys) != len(set(keys)):
        errors.append("indicateurs : couple (structure_id, periode) en double")
    for i in indicateurs:
        if i["structure_id"] not in known:
            errors.append(f"indicateur {i['periode']} : structure_id {i['structure_id']} inconnu")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--check", action="store_true", help="vérifier data/ sans rien écrire")
    args = parser.parse_args()

    if args.check:
        try:
            bases = {n: json.loads((DATA_DIR / f"{n}.json").read_text(encoding="utf-8"))
                     for n in ("structures", "patients", "indicateurs")}
        except FileNotFoundError as exc:
            print(f"ERREUR : fichier manquant ({exc.filename}). Lancez : python3 scripts/init_data.py")
            return 1
    else:
        bases = {"structures": STRUCTURES, "patients": generate_patients(),
                 "indicateurs": INDICATEURS}
        DATA_DIR.mkdir(exist_ok=True)
        for name, rows in bases.items():
            (DATA_DIR / f"{name}.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    errors = check(bases["structures"], bases["patients"], bases["indicateurs"])
    for name, rows in bases.items():
        print(f"  data/{name}.json : {len(rows)} enregistrements")
    if errors:
        print("ERREURS :\n  " + "\n  ".join(errors))
        return 1
    print("Bases cohérentes." if args.check else "Bases créées et cohérentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

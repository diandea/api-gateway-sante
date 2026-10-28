"""
Chargement des bases de données de test (fichiers JSON).

Emplacement :
  - variable d'environnement DATA_DIR (dans les conteneurs : /app/data,
    monté en volume depuis le dossier data/ du dépôt) ;
  - sinon le dossier data/ à la racine du dépôt (exécution locale, tests).

Les fichiers sont créés par : python3 scripts/init_data.py
"""

import json
import os
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_data(name: str) -> list:
    path = Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)) / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Base introuvable : {path}. Créez-la avec : python3 scripts/init_data.py")
    return json.loads(path.read_text(encoding="utf-8"))

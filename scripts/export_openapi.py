"""
Exporte les contrats d'API (OpenAPI 3) des quatre services dans contracts/.

FastAPI produit le contrat à partir du code ; ce script le fige dans des
fichiers versionnés, consultables sans lancer les services (Swagger Editor,
Postman, Insomnia...). Le test tests/test_contracts.py échoue si le code
et les fichiers ne correspondent plus.

Usage : python3 scripts/export_openapi.py
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SERVICES = {
    "structures": "services/structures/main.py",
    "patients": "services/patients/main.py",
    "indicateurs": "services/indicateurs/main.py",
    "aggregator": "aggregator/main.py",
}
OUT_DIR = ROOT / "contracts"


def build_contract(name: str) -> dict:
    spec = importlib.util.spec_from_file_location(f"{name}_contract", ROOT / SERVICES[name])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app.openapi()


def render(contract: dict) -> str:
    return json.dumps(contract, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for name in SERVICES:
        path = OUT_DIR / f"{name}.openapi.json"
        path.write_text(render(build_contract(name)), encoding="utf-8")
        print(f"  {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

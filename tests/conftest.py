"""Outils communs aux tests : chargement des 4 applications FastAPI."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # pour "from common.observability import ..."


def load_app_module(relative_path: str, module_name: str):
    """Charge un main.py sous un nom unique (les 4 services s'appellent tous main.py)."""
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

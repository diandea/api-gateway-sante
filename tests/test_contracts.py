"""
Vérifie que les contrats d'API publiés dans contracts/ correspondent au code.
En cas d'échec : python3 scripts/export_openapi.py, puis relire le diff.
"""

import importlib.util

import pytest

from conftest import ROOT

spec = importlib.util.spec_from_file_location("export_openapi", ROOT / "scripts/export_openapi.py")
export_openapi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_openapi)


@pytest.mark.parametrize("name", list(export_openapi.SERVICES))
def test_contrat_a_jour(name):
    path = ROOT / "contracts" / f"{name}.openapi.json"
    assert path.exists(), f"Contrat manquant : {path}"
    expected = export_openapi.render(export_openapi.build_contract(name))
    assert path.read_text(encoding="utf-8") == expected, (
        f"{path.name} ne correspond plus au code : lancez scripts/export_openapi.py")


def test_endpoint_dashboard_dans_le_contrat():
    contract = export_openapi.build_contract("aggregator")
    assert "/api/v1/dashboard/structures/{structure_id}" in contract["paths"]

from pathlib import Path


def test_ventas_y_compras_no_insertan_directo_en_libro_diario():
    for ruta in [
        Path("services/ventas_service.py"),
        Path("services/compras_service.py"),
    ]:
        texto = ruta.read_text(encoding="utf-8")
        assert "INSERT INTO libro_diario" not in texto
        assert "Bloqueo definitivo de contabilización directa" in texto
        assert 'return ("SELECT 1", ())' in texto


def test_asientos_propuestos_aceptan_plan_empresa_legacy_imputable_s():
    for ruta in [
        Path("services/ventas_asientos_propuestos_service.py"),
        Path("services/compras_asientos_propuestos_service.py"),
    ]:
        texto = ruta.read_text(encoding="utf-8")
        assert "CAST(imputable AS TEXT)" in texto
        assert "'S'" in texto

from pathlib import Path


def test_bandeja_normaliza_fecha_interna_sin_cambiar_regla_visual():
    for ruta in [
        Path("services/ventas_asientos_propuestos_service.py"),
        Path("services/compras_asientos_propuestos_service.py"),
    ]:
        texto = ruta.read_text(encoding="utf-8")
        assert "def _fecha_bandeja" in texto
        assert "En pantalla se muestra dd/mm/aaaa" in texto
        assert "fecha=_fecha_bandeja(" in texto


def test_bandeja_no_usa_fallback_generico_por_nombre():
    for ruta in [
        Path("services/ventas_asientos_propuestos_service.py"),
        Path("services/compras_asientos_propuestos_service.py"),
    ]:
        texto = ruta.read_text(encoding="utf-8")
        assert "fallback_ventas_por_nombre_legacy" not in texto
        assert "fallback_compras_por_nombre_legacy" not in texto
        assert "def _cuentas_por_nombre_contiene" not in texto


def test_compras_y_ventas_no_vuelven_a_insertar_directo_en_libro_diario():
    for ruta in [
        Path("services/ventas_service.py"),
        Path("services/compras_service.py"),
    ]:
        texto = ruta.read_text(encoding="utf-8")
        assert "INSERT INTO libro_diario" not in texto

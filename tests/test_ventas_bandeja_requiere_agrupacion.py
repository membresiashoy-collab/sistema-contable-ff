from pathlib import Path


def test_ventas_bandeja_requiere_agrupacion_interna():
    texto = Path("services/ventas_asientos_propuestos_service.py").read_text(encoding="utf-8")

    assert "La venta no tiene agrupación interna asignada" in texto
    assert "No alcanza con tener tipo_venta" in texto
    assert "AND COALESCE(v.actividad_venta_id, 0) > 0" in texto
    assert "OR COALESCE(TRIM(v.tipo_venta), '') <> ''" not in texto

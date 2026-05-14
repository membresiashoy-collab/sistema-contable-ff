from pathlib import Path


def test_ventas_ui_integra_generacion_asientos_propuestos():
    texto = Path("modulos/ventas.py").read_text(encoding="utf-8")

    assert "mostrar_generacion_asientos_ventas_importadas" in texto
    assert "mostrar_actividades_ventas_ui" in texto


def test_componente_ventas_asientos_usa_bandeja_y_no_diario_directo():
    texto = Path("modulos/ventas_asientos_componentes.py").read_text(encoding="utf-8")

    assert "listar_ventas_pendientes_asiento" in texto
    assert "generar_asientos_propuestos_ventas_importadas" in texto
    assert "Bandeja" in texto
    assert "No escribe directo en Libro Diario" in texto
    assert "INSERT INTO libro_diario" not in texto


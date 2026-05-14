from pathlib import Path


def test_compras_ui_tiene_accion_para_asientos_propuestos():
    texto = Path("modulos/compras.py").read_text(encoding="utf-8")

    assert "mostrar_generacion_asientos_compras_importadas" in texto
    assert "cargar_csv_compras_arca()" in texto


def test_componente_compras_usa_servicio_de_bandeja_y_no_diario_directo():
    texto = Path("modulos/compras_asientos_componentes.py").read_text(encoding="utf-8")

    assert "listar_compras_pendientes_asiento" in texto
    assert "generar_asientos_propuestos_compras_importadas" in texto
    assert "Bandeja" in texto
    assert "No escribe directo en Libro Diario" in texto
    assert "INSERT INTO libro_diario" not in texto


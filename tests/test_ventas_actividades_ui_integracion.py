from pathlib import Path


def test_ventas_ui_integra_actividades_de_venta():
    texto = Path("modulos/ventas.py").read_text(encoding="utf-8")

    assert "mostrar_actividades_ventas_ui" in texto
    assert "Cargar CSV ARCA" in texto


def test_componente_actividades_no_escribe_libro_diario():
    texto = Path("modulos/ventas_actividades_componentes.py").read_text(encoding="utf-8")

    assert "crear_actividad_venta" in texto
    assert "asignar_actividad_a_ventas" in texto
    assert "Bandeja" in texto
    assert "INSERT INTO libro_diario" not in texto

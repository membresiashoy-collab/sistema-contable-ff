from pathlib import Path


def test_asignacion_pendientes_confirma_transaccion_al_usar_conexion_propia():
    texto = Path("services/ventas_actividades_service.py").read_text(encoding="utf-8")

    assert "def asignar_actividad_a_ventas_pendientes" in texto
    assert "resultado = asignar_actividad_a_ventas(" in texto
    assert "if cerrar:" in texto
    assert "conexion.commit()" in texto
    assert "return resultado" in texto

from pathlib import Path


def test_formato_visual_cuit_estado_empresa() -> None:
    from modulos.inicio_empresa_componentes import _formatear_cuit_visual

    assert _formatear_cuit_visual("20362253837") == "20-36225383-7"
    assert _formatear_cuit_visual("20-36225383-7") == "20-36225383-7"
    assert _formatear_cuit_visual("") == ""


def test_estado_empresa_muestra_cuit_y_no_corte() -> None:
    texto = Path("modulos/inicio_empresa_componentes.py").read_text(encoding="utf-8")

    assert 'col2.metric("CUIT"' in texto
    assert 'col2.metric("CORTE"' not in texto
    assert 'col2.metric("Corte"' not in texto


def test_recomendacion_caja_es_condicional_y_clara() -> None:
    texto = Path("services/empresas_service.py").read_text(encoding="utf-8")

    assert "No hay cajas activas. Si la empresa usará efectivo, cree o inicialice una caja operativa." in texto
    assert "Crear o inicializar una caja para registrar operaciones en efectivo." not in texto

from pathlib import Path


def test_comportamientos_integra_asistente_normalizacion():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "mostrar_asistente_normalizacion_contable_ui" in contenido
    assert "Asistente de normalización" in contenido
    assert "asistente_normalizacion" in contenido


def test_componente_normalizacion_no_usa_st_title():
    contenido = Path("modulos/normalizacion_contable_componentes.py").read_text(encoding="utf-8")

    assert "st.title" not in contenido


def test_core_incluye_clientes_y_proveedores_no_criticos():
    contenido = Path("core/contabilidad_coherencia.py").read_text(encoding="utf-8")

    assert '"CLIENTES"' in contenido
    assert '"PROVEEDORES"' in contenido
    assert 'if codigo not in {"CLIENTES", "PROVEEDORES"}' in contenido
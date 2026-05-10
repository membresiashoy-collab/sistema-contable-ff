from pathlib import Path


def test_contabilidad_integra_control_de_consistencia_contable():
    contenido = Path("modulos/reportes.py").read_text(encoding="utf-8")

    assert "mostrar_diagnostico_coherencia_contable_ui" in contenido
    assert "🧩 Control de consistencia contable" in contenido
    assert "contabilidad_control_consistencia_contable" in contenido


def test_contabilidad_no_expone_nombre_viejo_coherencia_contable():
    contenido = Path("modulos/reportes.py").read_text(encoding="utf-8")

    assert "🧩 Coherencia contable" not in contenido
    assert "contabilidad_coherencia_contable" not in contenido


def test_componente_coherencia_no_usa_st_title():
    contenido = Path("modulos/coherencia_contable_componentes.py").read_text(encoding="utf-8")

    assert "st.title" not in contenido

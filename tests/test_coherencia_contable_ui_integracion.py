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


def test_componente_control_consistencia_usa_lenguaje_contable_visible():
    contenido = Path("modulos/coherencia_contable_componentes.py").read_text(encoding="utf-8")

    assert "🧩 Control de consistencia contable" in contenido
    assert "Alertas y controles detectados" in contenido
    assert "Catálogos técnicos usados por el control" in contenido
    assert "Usos operativos del sistema" in contenido
    assert "Tipos de origen operativo" in contenido
    assert "Descargar control de consistencia Excel" in contenido
    assert "control_consistencia_contable.xlsx" in contenido

    assert "Diagnóstico de coherencia contable" not in contenido
    assert "Comportamientos contables" not in contenido
    assert "\"Comportamientos\"" not in contenido
    assert "Origenes economicos" not in contenido
    assert "diagnostico_coherencia_contable.xlsx" not in contenido


def test_componente_coherencia_no_usa_st_title():
    contenido = Path("modulos/coherencia_contable_componentes.py").read_text(encoding="utf-8")

    assert "st.title" not in contenido

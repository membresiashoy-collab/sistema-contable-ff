from pathlib import Path


def test_contabilidad_integra_diagnostico_coherencia():
    contenido = Path("modulos/reportes.py").read_text(encoding="utf-8")

    assert "mostrar_diagnostico_coherencia_contable_ui" in contenido
    assert "🧩 Coherencia contable" in contenido
    assert "contabilidad_coherencia_contable" in contenido


def test_componente_coherencia_no_usa_st_title():
    contenido = Path("modulos/coherencia_contable_componentes.py").read_text(encoding="utf-8")

    assert "st.title" not in contenido
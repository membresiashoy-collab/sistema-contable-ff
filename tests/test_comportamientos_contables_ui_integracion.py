from pathlib import Path


def test_contabilidad_integra_configuracion_comportamientos():
    contenido = Path("modulos/reportes.py").read_text(encoding="utf-8")

    assert "mostrar_configuracion_comportamientos_contables_ui" in contenido
    assert "⚙️ Comportamientos" in contenido
    assert "contabilidad_comportamientos_contables" in contenido


def test_componente_comportamientos_no_usa_st_title():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "st.title" not in contenido
from pathlib import Path


def test_contabilidad_no_expone_comportamientos_como_pestania_visible():
    contenido = Path("modulos/reportes.py").read_text(encoding="utf-8")

    assert "mostrar_configuracion_comportamientos_contables_ui" not in contenido
    assert "⚙️ Comportamientos" not in contenido
    assert "contabilidad_comportamientos_contables" not in contenido


def test_configuracion_tecnica_de_comportamientos_sigue_existiendo_fuera_de_contabilidad():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "def mostrar_configuracion_comportamientos_contables_ui" in contenido
    assert "mostrar_configuracion_comportamientos_contables" in contenido
    assert "Plan de Cuentas es la fuente de verdad" in contenido
    assert "Uso operativo" in contenido


def test_componente_comportamientos_no_usa_st_title():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "st.title" not in contenido

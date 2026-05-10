from pathlib import Path


def test_configuracion_integra_plan_cuentas_pro():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "Plan de Cuentas PRO" in texto
    assert "Plan de Cuentas es la fuente de verdad" in texto
    assert "guardar_cuenta_plan" in texto
    assert "normalizar_metadata_plan_cuentas" in texto
    assert "comportamiento_contable" in texto
    assert "Uso operativo del sistema" in texto


def test_plan_cuentas_no_usa_st_title_en_modulo():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")
    assert "st.title(" not in texto


def test_configuracion_explica_no_duplicar_comportamientos():
    texto = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "Contabilidad → Uso operativo queda como tablero" in texto
    assert "no como carga duplicada" in texto
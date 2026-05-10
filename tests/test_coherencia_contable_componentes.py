import importlib
import sys
import types

import pandas as pd


def _asegurar_streamlit_stub():
    try:
        import streamlit  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    def _dummy(*args, **kwargs):
        return None

    st = types.ModuleType("streamlit")
    for nombre in (
        "error",
        "warning",
        "success",
        "info",
        "caption",
        "subheader",
        "markdown",
        "write",
        "divider",
        "dataframe",
        "download_button",
        "button",
        "checkbox",
        "multiselect",
        "selectbox",
        "text_input",
        "text_area",
    ):
        setattr(st, nombre, _dummy)
    st.session_state = {}
    st.columns = lambda *args, **kwargs: [types.SimpleNamespace(metric=_dummy) for _ in range(5)]
    st.expander = lambda *args, **kwargs: types.SimpleNamespace(__enter__=lambda self: self, __exit__=lambda self, exc_type, exc, tb: False)
    st.tabs = lambda labels: [types.SimpleNamespace(__enter__=lambda self: self, __exit__=lambda self, exc_type, exc, tb: False) for _ in labels]
    sys.modules["streamlit"] = st


def _importar_modulo():
    _asegurar_streamlit_stub()
    return importlib.import_module("modulos.comportamientos_contables_componentes")


def test_componente_importa_y_expone_ui():
    modulo = _importar_modulo()

    assert hasattr(modulo, "mostrar_configuracion_comportamientos_contables_ui")
    assert callable(modulo.mostrar_configuracion_comportamientos_contables_ui)
    assert hasattr(modulo, "mostrar_configuracion_comportamientos_contables")
    assert callable(modulo.mostrar_configuracion_comportamientos_contables)


def test_dataframes_de_comportamientos_tienen_columnas_esperadas():
    modulo = _importar_modulo()

    cuentas = modulo._cuentas_dataframe([
        {
            "codigo": "1.1.01",
            "nombre": "Caja",
            "comportamiento_contable": "CAJA",
            "imputable": "S",
        }
    ])
    assert set(modulo.COLUMNAS_CUENTAS).issubset(set(cuentas.columns))

    sugerencias = modulo._sugerencias_dataframe([
        {
            "codigo": "1.1.01",
            "nombre": "Caja",
            "comportamiento": "CAJA",
            "confianza": "Alta",
        }
    ])
    assert set(modulo.COLUMNAS_SUGERENCIAS).issubset(set(sugerencias.columns))


def test_vistas_usan_etiquetas_amigables():
    modulo = _importar_modulo()

    df = pd.DataFrame([
        {
            "codigo_cuenta": "1.1.01",
            "nombre_cuenta": "Caja",
            "comportamientos_texto": "CAJA",
            "imputable": "S",
            "requiere_auxiliar": 0,
            "permite_imputacion_operativa": 1,
            "estado_configuracion": "OK",
        }
    ])
    vista = modulo._vista_cuentas(df)

    assert "Código" in vista.columns
    assert "Cuenta" in vista.columns
    assert "Uso operativo" in vista.columns


def test_componente_deja_claro_que_plan_cuentas_es_fuente_de_verdad_y_uso_operativo_secundario():
    from pathlib import Path

    texto = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "Plan de Cuentas es la fuente de verdad" in texto
    assert "Configuración → Plan de Cuentas" in texto
    assert "no como carga duplicada" in texto
    assert "Uso operativo" in texto


def test_ui_acepta_key_prefix_para_integracion_con_reportes():
    import inspect

    modulo = _importar_modulo()
    firma = inspect.signature(modulo.mostrar_configuracion_comportamientos_contables_ui)

    assert "key_prefix" in firma.parameters
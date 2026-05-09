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
            "codigo_cuenta": "11101",
            "nombre_cuenta": "Caja",
            "comportamientos_texto": "CAJA",
            "imputable": True,
        }
    ])
    assert set(modulo.COLUMNAS_CUENTAS).issubset(set(cuentas.columns))

    mapeos = modulo._mapeos_dataframe([
        {
            "id": 1,
            "codigo_cuenta": "11101",
            "cuenta_nombre": "Caja",
            "comportamiento": "CAJA",
        }
    ])
    assert set(modulo.COLUMNAS_MAPEOS).issubset(set(mapeos.columns))

    sugerencias = modulo._sugerencias_dataframe([
        {
            "codigo_cuenta": "11101",
            "nombre_cuenta": "Caja",
            "comportamiento": "CAJA",
        }
    ])
    assert set(modulo.COLUMNAS_SUGERENCIAS).issubset(set(sugerencias.columns))


def test_vistas_usan_etiquetas_amigables():
    modulo = _importar_modulo()

    df = pd.DataFrame([
        {
            "codigo_cuenta": "11101",
            "nombre_cuenta": "Caja",
            "comportamientos_texto": "CAJA",
            "imputable": True,
            "requiere_auxiliar": False,
            "permite_imputacion_operativa": True,
        }
    ])
    vista = modulo._vista_cuentas(df)

    assert "Código" in vista.columns
    assert "Cuenta" in vista.columns
    assert "Comportamiento" in vista.columns
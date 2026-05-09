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

    class _Ctx:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

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
        "text_area",
        "rerun",
    ):
        setattr(st, nombre, _dummy)
    st.session_state = {}
    st.columns = lambda *args, **kwargs: [types.SimpleNamespace(metric=_dummy) for _ in range(5)]
    st.expander = lambda *args, **kwargs: _Ctx()
    st.tabs = lambda labels: [_Ctx() for _ in labels]
    st.data_editor = lambda df, *args, **kwargs: df
    st.column_config = types.SimpleNamespace(CheckboxColumn=lambda *args, **kwargs: None)
    sys.modules["streamlit"] = st


def _importar_modulo():
    _asegurar_streamlit_stub()
    return importlib.import_module("modulos.normalizacion_contable_componentes")


def test_componente_importa_y_expone_ui():
    modulo = _importar_modulo()

    assert hasattr(modulo, "mostrar_asistente_normalizacion_contable_ui")
    assert callable(modulo.mostrar_asistente_normalizacion_contable_ui)
    assert hasattr(modulo, "mostrar_asistente_normalizacion_contable")
    assert callable(modulo.mostrar_asistente_normalizacion_contable)


def test_dataframes_de_normalizacion_tienen_columnas_esperadas():
    modulo = _importar_modulo()

    sugerencias = modulo._sugerencias_dataframe([
        {
            "codigo_cuenta": "11101",
            "nombre_cuenta": "Caja",
            "comportamiento": "CAJA",
            "confianza": "Alta",
            "estado_sugerencia": "PENDIENTE",
        }
    ])
    assert set(modulo.COLUMNAS_SUGERENCIAS_NORMALIZACION).issubset(set(sugerencias.columns))

    asignaciones = modulo._asignaciones_dataframe([
        {
            "id": 1,
            "codigo_cuenta": "11101",
            "cuenta_nombre": "Caja",
            "comportamiento": "CAJA",
        }
    ])
    assert set(modulo.COLUMNAS_ASIGNACIONES_NORMALIZACION).issubset(set(asignaciones.columns))

    historial = modulo._historial_dataframe([
        {
            "fecha_evento": "2026-05-09",
            "evento": "ALTA",
            "codigo_cuenta": "11101",
            "comportamiento": "CAJA",
        }
    ])
    assert set(modulo.COLUMNAS_HISTORIAL_NORMALIZACION).issubset(set(historial.columns))


def test_vistas_usan_etiquetas_amigables():
    modulo = _importar_modulo()

    df = pd.DataFrame([
        {
            "aplicar": True,
            "codigo_cuenta": "11101",
            "nombre_cuenta": "Caja",
            "comportamiento": "CAJA",
            "comportamiento_nombre": "Caja",
            "confianza": "Alta",
            "estado_sugerencia": "PENDIENTE",
            "comportamiento_actual": "",
            "motivo": "Nombre contiene caja",
        }
    ])
    vista = modulo._vista_sugerencias(df)

    assert "Aplicar" in vista.columns
    assert "Código" in vista.columns
    assert "Sugerencia" in vista.columns


def test_opciones_asignaciones_extraen_id():
    modulo = _importar_modulo()
    df = pd.DataFrame([
        {
            "id": 10,
            "codigo_cuenta": "11101",
            "comportamiento": "CAJA",
            "estado": "ACTIVO",
        }
    ])
    opciones = modulo._opciones_asignaciones(df)
    assert opciones[0].startswith("10")
    assert modulo._id_desde_opcion(opciones[0]) == 10
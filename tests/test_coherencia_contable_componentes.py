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
    ):
        setattr(st, nombre, _dummy)
    st.session_state = {}
    st.columns = lambda *args, **kwargs: [types.SimpleNamespace(metric=_dummy) for _ in range(5)]
    st.expander = lambda *args, **kwargs: types.SimpleNamespace(__enter__=lambda self: self, __exit__=lambda self, exc_type, exc, tb: False)
    st.tabs = lambda labels: [types.SimpleNamespace(__enter__=lambda self: self, __exit__=lambda self, exc_type, exc, tb: False) for _ in labels]
    sys.modules["streamlit"] = st


def _importar_modulo():
    _asegurar_streamlit_stub()
    return importlib.import_module("modulos.coherencia_contable_componentes")


def test_componente_coherencia_importa():
    modulo = _importar_modulo()

    assert hasattr(modulo, "mostrar_diagnostico_coherencia_contable_ui")
    assert callable(modulo.mostrar_diagnostico_coherencia_contable_ui)
    assert hasattr(modulo, "mostrar_diagnostico_coherencia_contable")
    assert callable(modulo.mostrar_diagnostico_coherencia_contable)


def test_prepara_dataframe_de_diagnosticos_ordenado():
    modulo = _importar_modulo()

    diagnosticos = [
        {
            "area": "Libro Diario",
            "severidad": "OK",
            "codigo": "OK",
            "titulo": "Todo correcto",
            "detalle": "Sin problemas",
        },
        {
            "area": "Ejercicios",
            "severidad": "ERROR",
            "codigo": "ERR",
            "titulo": "Error crítico",
            "detalle": "Problema",
        },
        {
            "area": "Plan de cuentas",
            "severidad": "ADVERTENCIA",
            "codigo": "WARN",
            "titulo": "Advertencia",
            "detalle": "Revisar",
        },
    ]

    df = modulo._diagnosticos_dataframe(diagnosticos)

    assert list(df["severidad"]) == ["ERROR", "ADVERTENCIA", "OK"]
    assert set(modulo.COLUMNAS_DIAGNOSTICO).issubset(set(df.columns))


def test_filtra_diagnosticos_por_severidad_y_area():
    modulo = _importar_modulo()

    df = pd.DataFrame(
        [
            {"area": "Ejercicios", "severidad": "ERROR", "codigo": "A", "titulo": "A", "detalle": "A"},
            {"area": "Libro Diario", "severidad": "INFO", "codigo": "B", "titulo": "B", "detalle": "B"},
            {"area": "Ejercicios", "severidad": "OK", "codigo": "C", "titulo": "C", "detalle": "C"},
        ]
    )

    filtrado = modulo._filtrar_diagnosticos(df, severidades=["ERROR"], areas=["Ejercicios"])

    assert len(filtrado) == 1
    assert filtrado.iloc[0]["codigo"] == "A"


def test_vista_diagnosticos_usa_etiquetas_amigables():
    modulo = _importar_modulo()

    df = pd.DataFrame(
        [
            {
                "area": "Ejercicios",
                "severidad": "ADVERTENCIA",
                "codigo": "WARN",
                "titulo": "Advertencia",
                "detalle": "Revisar",
                "referencia_tipo": "tabla",
                "referencia_id": 1,
            }
        ]
    )

    vista = modulo._vista_diagnosticos(df)

    assert "Área" in vista.columns
    assert "Diagnóstico" in vista.columns
    assert vista.iloc[0]["Severidad"] == "Advertencia"
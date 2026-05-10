from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pandas as pd


def _importar_modulo():
    importlib.invalidate_caches()
    return importlib.import_module("modulos.comportamientos_contables_componentes")


def test_componente_importa_y_expone_ui_principal():
    modulo = _importar_modulo()

    assert hasattr(modulo, "mostrar_configuracion_comportamientos_contables_ui")
    assert hasattr(modulo, "mostrar_configuracion_comportamientos_contables")


def test_ui_acepta_key_prefix_para_integracion_con_reportes():
    modulo = _importar_modulo()

    firma = inspect.signature(modulo.mostrar_configuracion_comportamientos_contables_ui)
    assert "key_prefix" in firma.parameters


def test_vista_cuentas_usa_terminologia_plan_cuentas_pro():
    modulo = _importar_modulo()

    df = pd.DataFrame(
        [
            {
                "codigo_cuenta": "11101",
                "nombre_cuenta": "Caja",
                "comportamientos_texto": "CAJA",
                "imputable": True,
                "requiere_auxiliar": False,
                "permite_imputacion_operativa": True,
            }
        ]
    )

    vista = modulo._vista_cuentas(df)

    assert "Código" in vista.columns
    assert "Cuenta" in vista.columns
    assert "Uso operativo" in vista.columns
    assert "Comportamiento" not in vista.columns
    assert vista.loc[1, "Uso operativo"] == "CAJA"


def test_textos_visibles_no_reinstalan_comportamiento_como_concepto_central():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "Uso operativo del sistema" in contenido
    assert "Plan de Cuentas" in contenido
    assert "fuente de verdad" in contenido
    assert "Comportamiento contable" not in contenido


def test_componente_no_usa_st_title():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")
    assert "st.title(" not in contenido
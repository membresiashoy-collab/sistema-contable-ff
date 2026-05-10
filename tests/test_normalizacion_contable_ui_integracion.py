from pathlib import Path


def test_uso_operativo_queda_como_tablero_no_fuente_de_verdad():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "El Plan de Cuentas es la fuente de verdad" in contenido
    assert "Configuración → Plan de Cuentas" in contenido
    assert "no como carga duplicada" in contenido
    assert "Uso operativo" in contenido


def test_configuracion_integra_plan_cuentas_pro():
    contenido = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "Plan de Cuentas PRO" in contenido
    assert "comportamiento_contable" in contenido
    assert "permite_imputacion_operativa" in contenido
    assert "requiere_auxiliar" in contenido


def test_no_reintroduce_asignacion_manual_paralela_en_comportamientos():
    contenido = Path("modulos/comportamientos_contables_componentes.py").read_text(encoding="utf-8")

    assert "Asignar manualmente" not in contenido
    assert "Guardar comportamiento" not in contenido
    assert "actualizar_comportamiento_plan_cuentas" not in contenido
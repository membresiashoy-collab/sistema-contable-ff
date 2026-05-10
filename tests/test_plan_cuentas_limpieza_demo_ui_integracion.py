from pathlib import Path


def _codigo_configuracion() -> str:
    return Path("modulos/configuracion.py").read_text(encoding="utf-8")


def test_configuracion_importa_servicio_limpieza_demo_plan():
    codigo = _codigo_configuracion()

    assert "from services.plan_cuentas_limpieza_demo_service import (" in codigo
    assert "CONFIRMACION_LIMPIEZA_DEMO" in codigo
    assert "limpiar_plan_cuentas_demo_desde_maestro" in codigo
    assert "previsualizar_limpieza_plan_cuentas_demo" in codigo


def test_configuracion_expone_tab_limpieza_demo_en_plan_cuentas():
    codigo = _codigo_configuracion()

    assert '"🧹 Limpieza demo"' in codigo
    assert "def _mostrar_limpieza_demo_plan(empresa_id):" in codigo
    assert "_mostrar_limpieza_demo_plan(empresa_id)" in codigo


def test_configuracion_limpieza_demo_exige_confirmacion_fuerte_y_motivo():
    codigo = _codigo_configuracion()

    assert "plan_limpieza_demo_confirmacion" in codigo
    assert "plan_limpieza_demo_motivo" in codigo
    assert "confirmacion == CONFIRMACION_LIMPIEZA_DEMO" in codigo
    assert "Ejecutar limpieza demo y reconstruir desde Plan Maestro FF" in codigo


def test_configuracion_limpieza_demo_muestra_previsualizacion_y_resultado():
    codigo = _codigo_configuracion()

    assert "Previsualización" in codigo
    assert "Catálogo empresa actual" in codigo
    assert "Plan Maestro activo" in codigo
    assert "Cuentas antes" in codigo
    assert "Reconstruidas" in codigo

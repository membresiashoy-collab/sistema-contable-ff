from pathlib import Path


def test_componente_expone_funcion_principal():
    contenido = Path("modulos/socios_cuentas_especificas_componentes.py").read_text(encoding="utf-8")
    assert "def mostrar_socios_cuentas_especificas" in contenido
    assert "Cuentas específicas por socio" in contenido


def test_componente_no_registra_movimientos_operativos():
    contenido = Path("modulos/socios_cuentas_especificas_componentes.py").read_text(encoding="utf-8")
    prohibidos = [
        "registrar_movimiento_banco",
        "registrar_movimiento_caja",
        "crear_asiento_definitivo",
        "conciliar",
    ]
    for prohibido in prohibidos:
        assert prohibido not in contenido


def test_servicio_mantiene_tablas_propias_y_no_toca_caja_banco():
    contenido = Path("services/socios_cuentas_especificas_service.py").read_text(encoding="utf-8")
    assert "socios_cuentas_especificas" in contenido
    assert "socios_cuentas_especificas_eventos" in contenido
    assert "crear_cuenta_empresa_desde_modelo" in contenido
    assert "bancos_cuentas" not in contenido
    assert "tesoreria_cuentas" not in contenido

def test_socios_empresa_pro_conecta_panel_cuentas_especificas():
    contenido = Path("modulos/socios_empresa_componentes.py").read_text(encoding="utf-8")
    assert "from modulos.socios_cuentas_especificas_componentes import mostrar_socios_cuentas_especificas" in contenido
    assert "mostrar_socios_cuentas_especificas(empresa_id=empresa_id)" in contenido

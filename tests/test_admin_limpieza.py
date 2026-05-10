from pathlib import Path
import ast


def leer_archivo(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def obtener_funciones(ruta):
    contenido = leer_archivo(ruta)
    arbol = ast.parse(contenido)

    return {
        nodo.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.FunctionDef)
    }


def test_admin_limpieza_service_existe_y_tiene_funciones_principales():
    funciones = obtener_funciones("services/admin_limpieza_service.py")

    assert "diagnosticar_datos_demo" in funciones
    assert "limpiar_libro_diario_admin" in funciones
    assert "limpiar_cobranzas_recibos_admin" in funciones
    assert "limpiar_pagos_ordenes_admin" in funciones
    assert "limpiar_banco_demo_admin" in funciones
    assert "limpiar_demo_operativa_admin" in funciones


def test_admin_limpieza_incluye_circuito_completo_recibos_y_pagos():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "cobranzas" in contenido
    assert "cobranzas_imputaciones" in contenido
    assert "cobranzas_retenciones" in contenido
    assert "pagos" in contenido
    assert "pagos_imputaciones" in contenido
    assert "pagos_retenciones" in contenido
    assert "cuenta_corriente_clientes" in contenido
    assert "cuenta_corriente_proveedores" in contenido
    assert "libro_diario" in contenido
    assert "tesoreria_operaciones" in contenido
    assert "tesoreria_operaciones_componentes" in contenido


def test_admin_limpieza_incluye_caja_real_no_cajas():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "caja_movimientos" in contenido
    assert "caja_asientos" in contenido
    assert "caja_auditoria" in contenido
    assert "caja_arqueos" in contenido
    assert "cajas_movimientos" not in contenido


def test_admin_limpieza_borra_por_referencia_y_tesoreria():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "COBRANZA_EFECTIVO" in contenido
    assert "PAGO_EFECTIVO" in contenido
    assert "numero_recibo" in contenido
    assert "numero_orden_pago" in contenido
    assert "tesoreria_operacion_id" in contenido
    assert "_obtener_caja_movimiento_ids" in contenido


def test_admin_limpieza_incluye_conciliaciones_y_banco():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "bancos_conciliaciones" in contenido
    assert "bancos_conciliaciones_detalle" in contenido
    assert "bancos_movimientos" in contenido
    assert "bancos_importaciones" in contenido
    assert "bancos_grupos_fiscales" in contenido


def test_admin_limpieza_integral_incluye_iva_banco_fiscal_y_cierres():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "iva_movimientos_fiscales" in contenido
    assert "iva_movimientos_fiscales_eventos" in contenido
    assert "iva_cierres_periodos" in contenido
    assert "iva_cierres_periodos_eventos" in contenido
    assert "iva_cierres_pagos" in contenido
    assert "iva_cierres_asientos_propuestos" in contenido
    assert "bancos_grupos_fiscales" in contenido


def test_admin_limpieza_integral_incluye_bandeja_y_asientos_propuestos():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "asientos_propuestos" in contenido
    assert "asientos_propuestos_detalle" in contenido
    assert "asientos_propuestos_eventos" in contenido
    assert "asientos_bandeja_eventos" in contenido
    assert "asientos_bandeja_lotes" in contenido


def test_admin_limpieza_diagnostico_muestra_tablas_operativas_nuevas():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "TABLAS_DIAGNOSTICO_DEMO_OPERATIVO" in contenido
    assert "TABLAS_LIMPIEZA_DEMO_OPERATIVA" in contenido
    assert "bancos_grupos_fiscales" in contenido
    assert "iva_movimientos_fiscales" in contenido
    assert "asientos_bandeja_lotes" in contenido


def test_admin_limpieza_tiene_backup_confirmacion_fuerte_y_control_fk():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert "backup_base_datos" in contenido
    assert "LIMPIAR DIARIO" in contenido
    assert "BORRAR RECIBOS" in contenido
    assert "BORRAR ORDENES" in contenido
    assert "BORRAR BANCO" in contenido
    assert "LIMPIAR DEMO" in contenido
    assert "PRAGMA foreign_key_check" in contenido
    assert "_validar_integridad_fk" in contenido


def test_admin_limpieza_no_borra_configuracion_base():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert '"usuarios"' not in contenido
    assert '"empresas"' not in contenido
    assert '"plan_cuentas"' not in contenido
    assert '"tesoreria_cuentas"' not in contenido
    assert '"tesoreria_medios_pago"' not in contenido
    assert '"categorias_compra"' not in contenido
    assert '"proveedores_configuracion"' not in contenido
    assert '"clientes_configuracion"' not in contenido


def test_admin_limpieza_operativa_no_reinicia_inicio_societario():
    contenido = leer_archivo("services/admin_limpieza_service.py")

    assert '"ejercicios_contables"' not in contenido
    assert '"socios_empresa"' not in contenido
    assert '"capital_social_empresa"' not in contenido
    assert '"capital_suscripciones"' not in contenido
    assert '"capital_integraciones"' not in contenido
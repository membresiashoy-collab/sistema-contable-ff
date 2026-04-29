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


def test_caja_service_existe_y_tiene_funciones_clave():
    funciones = obtener_funciones("services/cajas_service.py")

    assert "inicializar_cajas" in funciones
    assert "crear_caja" in funciones
    assert "listar_cajas" in funciones
    assert "obtener_saldos_cajas" in funciones
    assert "registrar_movimiento_manual_caja" in funciones
    assert "registrar_deposito_caja_a_banco" in funciones
    assert "registrar_retiro_banco_a_caja" in funciones
    assert "registrar_transferencia_interna" in funciones
    assert "registrar_arqueo_caja" in funciones
    assert "anular_movimiento_caja" in funciones
    assert "listar_operaciones_tesoreria_caja" in funciones
    assert "listar_asientos_caja" in funciones


def test_caja_migracion_crea_tablas_principales():
    contenido = leer_archivo("migrations/010_caja_mvp.sql")

    assert "CREATE TABLE IF NOT EXISTS caja_movimientos" in contenido
    assert "CREATE TABLE IF NOT EXISTS caja_arqueos" in contenido
    assert "CREATE TABLE IF NOT EXISTS caja_asientos" in contenido
    assert "CREATE TABLE IF NOT EXISTS caja_auditoria" in contenido


def test_caja_ui_existe_y_tiene_pantallas_principales():
    contenido = leer_archivo("modulos/caja.py")

    assert "def mostrar_caja" in contenido
    assert "Cajas configurables" in contenido
    assert "Movimientos manuales de caja" in contenido
    assert "Transferencias internas" in contenido
    assert "Arqueos de caja" in contenido
    assert "Anulación de movimientos de caja" in contenido


def test_caja_evitar_confundir_deposito_con_cobranza():
    contenido_service = leer_archivo("services/cajas_service.py")
    contenido_ui = leer_archivo("modulos/caja.py")

    assert "No debe registrarse como nueva cobranza" in contenido_service
    assert "No se trata como cobranza nueva" in contenido_ui
    assert "DEPOSITO_CAJA_BANCO" in contenido_service
    assert "estado_conciliacion_destino = \"PENDIENTE\"" in contenido_service


def test_caja_arqueo_genera_diferencias_controladas():
    contenido = leer_archivo("services/cajas_service.py")

    assert "AJUSTE_ARQUEO_SOBRANTE" in contenido
    assert "AJUSTE_ARQUEO_FALTANTE" in contenido
    assert "CUENTA_SOBRANTES_CAJA" in contenido
    assert "CUENTA_FALTANTES_CAJA" in contenido
    assert "_crear_asiento_doble" in contenido


def test_caja_anulacion_es_logica_y_con_motivo():
    contenido = leer_archivo("services/cajas_service.py")

    assert "motivo_anulacion" in contenido
    assert "fecha_anulacion" in contenido
    assert "estado = 'ANULADO'" in contenido
    assert "DELETE FROM caja_movimientos" not in contenido.upper()
    assert "DELETE FROM caja_arqueos" not in contenido.upper()


def test_caja_integra_tesoreria_operaciones():
    contenido = leer_archivo("services/cajas_service.py")

    assert "_insertar_tesoreria_operacion" in contenido
    assert "tesoreria_operaciones" in contenido
    assert "origen_modulo" in contenido
    assert "CAJA" in contenido
    assert "PENDIENTE" in contenido
    assert "NO_CONCILIABLE" in contenido


def test_main_tiene_modulo_caja_independiente():
    contenido = leer_archivo("main.py")

    assert '"Caja": {' in contenido
    assert '"modulo": "modulos.caja"' in contenido
    assert '"funcion": "mostrar_caja"' in contenido
    assert "inicializar_cajas" in contenido


def test_aliases_de_compatibilidad_existen():
    contenido_service_alias = leer_archivo("services/caja_service.py")
    contenido_modulo_alias = leer_archivo("modulos/cajas.py")

    assert "from services.cajas_service import *" in contenido_service_alias
    assert "from modulos.caja import mostrar_caja" in contenido_modulo_alias
    assert "def mostrar_cajas" in contenido_modulo_alias
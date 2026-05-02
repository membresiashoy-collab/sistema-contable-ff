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


def test_conciliacion_service_existe_y_tiene_funciones_clave():
    funciones = obtener_funciones("services/conciliacion_service.py")

    assert "inicializar_conciliacion" in funciones
    assert "obtener_resumen_conciliacion" in funciones
    assert "obtener_movimientos_bancarios_pendientes" in funciones
    assert "obtener_operaciones_tesoreria_pendientes" in funciones
    assert "generar_sugerencias_conciliacion" in funciones
    assert "confirmar_conciliacion_tesoreria" in funciones
    assert "desconciliar_conciliacion_tesoreria" in funciones
    assert "obtener_conciliaciones_tesoreria" in funciones


def test_conciliacion_ui_existe_y_usa_service_propio():
    contenido = leer_archivo("modulos/conciliacion.py")

    assert "def mostrar_conciliacion" in contenido
    assert "from services.conciliacion_service import" in contenido
    assert "Sugerencias automáticas" in contenido
    assert "Conciliación manual" in contenido
    assert "Conciliaciones confirmadas" in contenido
    assert "Desconciliar" in contenido


def test_main_integra_conciliacion_como_modulo_independiente():
    contenido = leer_archivo("main.py")

    assert '"Conciliación"' in contenido
    assert '"modulo": "modulos.conciliacion"' in contenido
    assert '"funcion": "mostrar_conciliacion"' in contenido
    assert '"services.conciliacion_service"' in contenido
    assert '"modulos.conciliacion"' in contenido


def test_conciliacion_no_es_parche_en_bancos():
    contenido_bancos = leer_archivo("modulos/bancos.py")
    contenido_conciliacion = leer_archivo("modulos/conciliacion.py")

    assert "mostrar_conciliacion" not in contenido_bancos
    assert "mostrar_conciliacion" in contenido_conciliacion


def test_conciliacion_no_toca_caja_visual():
    contenido_service = leer_archivo("services/conciliacion_service.py")
    contenido_ui = leer_archivo("modulos/conciliacion.py")

    assert "modulos.caja" not in contenido_service
    assert "modulos.caja" not in contenido_ui
    assert "services.cajas_service" not in contenido_service
    assert "services.cajas_service" not in contenido_ui


def test_conciliacion_usa_banco_y_tesoreria_como_fuentes():
    contenido = leer_archivo("services/conciliacion_service.py")

    assert "bancos_movimientos" in contenido
    assert "bancos_conciliaciones" in contenido
    assert "bancos_conciliaciones_detalle" in contenido
    assert "tesoreria_operaciones" in contenido
    assert "tesoreria_auditoria" in contenido


def test_conciliacion_no_borra_movimientos_ni_operaciones_base():
    contenido = leer_archivo("services/conciliacion_service.py").lower()

    assert "delete from bancos_movimientos" not in contenido
    assert "delete from tesoreria_operaciones" not in contenido
    assert "delete from tesoreria_operaciones_componentes" not in contenido
    assert "delete from cuenta_corriente_clientes" not in contenido
    assert "delete from cuenta_corriente_proveedores" not in contenido


def test_desconciliacion_es_controlada_y_no_borrado_fisico():
    contenido = leer_archivo("services/conciliacion_service.py")

    assert "DESCONCILIAR" in contenido
    assert "estado = 'ANULADA'" in contenido
    assert "motivo" in contenido
    assert "importe_revertido" in contenido


def test_sugerencias_tienen_scoring_y_confianza():
    contenido = leer_archivo("services/conciliacion_service.py")

    assert "_puntuar_sugerencia" in contenido
    assert "score" in contenido
    assert "confianza" in contenido
    assert "diferencia_importe" in contenido
    assert "diferencia_dias" in contenido
    assert "referencia_externa" in contenido


def test_conciliacion_actualiza_estados_banco_y_tesoreria():
    contenido = leer_archivo("services/conciliacion_service.py")

    assert "_actualizar_estado_banco" in contenido
    assert "_actualizar_estado_tesoreria" in contenido
    assert "estado_conciliacion = 'CONCILIADA'" in contenido
    assert "estado_conciliacion = ?" in contenido
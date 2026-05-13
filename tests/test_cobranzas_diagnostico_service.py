import sqlite3

from services.cobranzas_diagnostico_service import (
    CASOS_COBRANZA_REQUERIDOS,
    diagnosticar_cobranzas,
    exportar_diagnostico_cobranzas_como_texto,
    obtener_resumen_diagnostico_cobranzas,
)


def crear_base_minima(tmp_path):
    db_path = tmp_path / "cobranzas_test.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE cobranzas (
                id INTEGER PRIMARY KEY,
                cliente TEXT,
                cuit TEXT,
                importe_recibido REAL,
                importe_retenciones REAL,
                asiento_id INTEGER
            )
            """
        )
        conn.execute("CREATE TABLE cobranzas_imputaciones (id INTEGER PRIMARY KEY, cobranza_id INTEGER, importe_imputado REAL)")
        conn.execute("CREATE TABLE cobranzas_retenciones (id INTEGER PRIMARY KEY, cobranza_id INTEGER, tipo TEXT, importe REAL)")
        conn.execute("CREATE TABLE cobranzas_auditoria (id INTEGER PRIMARY KEY, entidad TEXT, evento TEXT)")
        conn.execute("CREATE TABLE cuenta_corriente_clientes (id INTEGER PRIMARY KEY, cliente TEXT, debe REAL, haber REAL)")
        conn.execute("CREATE TABLE tesoreria_operaciones (id INTEGER PRIMARY KEY, tercero_nombre TEXT, importe REAL)")
        conn.execute("CREATE TABLE tesoreria_operaciones_componentes (id INTEGER PRIMARY KEY, operacion_id INTEGER, importe REAL)")
        conn.execute("CREATE TABLE ventas_comprobantes (id INTEGER PRIMARY KEY, cliente TEXT, total REAL)")
        conn.execute("CREATE TABLE clientes_configuracion (id INTEGER PRIMARY KEY, nombre TEXT)")
        conn.execute("CREATE TABLE cuentas_tesoreria (id INTEGER PRIMARY KEY, nombre TEXT)")
        conn.execute("CREATE TABLE caja_movimientos (id INTEGER PRIMARY KEY, referencia TEXT)")
        conn.execute("CREATE TABLE asientos_propuestos (id INTEGER PRIMARY KEY, origen TEXT)")
        conn.execute(
            """
            CREATE TABLE plan_cuentas_empresa (
                id INTEGER PRIMARY KEY,
                codigo TEXT,
                nombre TEXT,
                activa INTEGER
            )
            """
        )
        conn.executemany(
            "INSERT INTO plan_cuentas_empresa (codigo, nombre, activa) VALUES (?, ?, ?)",
            [
                ("1.2.01", "DEUDORES POR VENTAS", 1),
                ("2.1.10", "ANTICIPOS DE CLIENTES", 1),
                ("1.3.04", "RETENCIONES IVA SUFRIDAS", 1),
                ("1.3.05", "RETENCIONES IIBB SUFRIDAS", 1),
                ("1.3.06", "RETENCIONES GANANCIAS SUFRIDAS", 1),
                ("2.1.11", "SALDOS A FAVOR DE CLIENTES", 1),
                ("5.1.99", "DIFERENCIAS DE COBRO", 1),
            ],
        )
        conn.commit()

    return db_path


def crear_archivos_codigo(tmp_path):
    service_path = tmp_path / "cobranzas_service.py"
    ui_path = tmp_path / "cobranzas.py"

    service_path.write_text(
        """
from services import tesoreria_service, cajas_service


def _proximo_asiento_cur(cur):
    cur.execute("SELECT MAX(id_asiento) FROM libro_diario")


def _insertar_libro_diario(cur):
    cur.execute("INSERT INTO libro_diario (cuenta) VALUES (?)")


def _insertar_cuenta_corriente_cliente(cur):
    cur.execute("INSERT INTO cuenta_corriente_clientes (cliente) VALUES (?)")


def _insertar_operacion_tesoreria_cobranza(cur):
    cur.execute("INSERT INTO tesoreria_operaciones (tercero_nombre) VALUES (?)")
    cur.execute("INSERT INTO tesoreria_operaciones_componentes (operacion_id) VALUES (?)")


def _registrar_auditoria(cur):
    cur.execute("INSERT INTO cobranzas_auditoria (evento) VALUES (?)")


def _construir_fingerprint_cobranza():
    return "fingerprint"


def registrar_cobranza(imputaciones=None, retenciones=None):
    imputaciones_normalizadas = imputaciones or []
    retenciones_normalizadas = retenciones or []
    importe_retenciones = 0
    cur.execute("INSERT INTO cobranzas_imputaciones (cobranza_id) VALUES (?)")
    cur.execute("INSERT INTO cobranzas_retenciones (cobranza_id) VALUES (?)")
    cajas_service.registrar_cobranza_efectivo_en_caja_cur()
    tipo_cuenta = "CAJA"


def anular_cobranza():
    asiento_reverso = 1
    motivo_anulacion = "error"
    cur.execute("UPDATE cobranzas SET anulada = 1")
    cajas_service.anular_movimientos_caja_por_referencia_cur()
""",
        encoding="utf-8",
    )

    ui_path.write_text(
        """
def mostrar_registrar_cobranza():
    obtener_clientes_con_saldo_pendiente()
    cliente = "Cliente | Saldo"
    obtener_comprobantes_pendientes_cliente()
    titulo = "Comprobantes pendientes"
    editor = "cobranzas_editor_pendientes"
    medio = "Medio de pago"
    _filtrar_cuentas_por_medio()
    _mostrar_impacto_cobranza()
    ret_iibb = "Retención IIBB"
    ret_ganancias = "Retención Ganancias"
    ret_iva = "Retención IVA"
    retenciones_total = 0
    boton = "Anular cobranza"
    motivo = "Motivo de anulación"
    permitir_conciliada = True
""",
        encoding="utf-8",
    )

    return service_path, ui_path


def test_diagnostico_detecta_impactos_directos_y_estado_revision(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_cobranzas(
        db_path=db_path,
        archivo_servicio_cobranzas=service_path,
        archivo_ui_cobranzas=ui_path,
    )

    assert diagnostico["estado"] == "REQUIERE_REVISION"

    impactos = diagnostico["impactos_directos"]
    assert impactos["libro_diario"]["detectado"] is True
    assert impactos["cuenta_corriente_clientes"]["detectado"] is True
    assert impactos["tesoreria_operaciones"]["detectado"] is True
    assert impactos["tesoreria_operaciones_componentes"]["detectado"] is True
    assert impactos["caja"]["detectado"] is True
    assert impactos["imputaciones"]["detectado"] is True
    assert impactos["retenciones"]["detectado"] is True
    assert impactos["auditoria"]["detectado"] is True
    assert impactos["anulacion"]["detectado"] is True

    codigos = {h["codigo"] for h in diagnostico["hallazgos"]}
    assert "COBRANZAS_ASIENTO_DIRECTO_LIBRO_DIARIO" in codigos
    assert "COBRANZAS_IMPACTA_CUENTA_CORRIENTE_CLIENTES" in codigos
    assert "COBRANZAS_IMPACTA_TESORERIA" in codigos


def test_diagnostico_detecta_capacidades_ui(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_cobranzas(
        db_path=db_path,
        archivo_servicio_cobranzas=service_path,
        archivo_ui_cobranzas=ui_path,
    )

    capacidades = diagnostico["capacidades_ui"]

    assert capacidades["seleccion_cliente_con_saldo"]["detectado"] is True
    assert capacidades["seleccion_comprobantes_pendientes"]["detectado"] is True
    assert capacidades["medios_pago_y_cuentas_compatibles"]["detectado"] is True
    assert capacidades["retenciones_ui"]["detectado"] is True
    assert capacidades["anulacion_ui"]["detectado"] is True


def test_diagnostico_evalua_casos_requeridos(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_cobranzas(
        db_path=db_path,
        archivo_servicio_cobranzas=service_path,
        archivo_ui_cobranzas=ui_path,
    )

    casos = {caso["codigo"]: caso for caso in diagnostico["casos_requeridos"]}

    assert len(CASOS_COBRANZA_REQUERIDOS) == 7
    assert casos["COBRANZA_FACTURA_TOTAL"]["estado"] == "SOPORTADO_BASE"
    assert casos["COBRANZA_FACTURA_PARCIAL"]["estado"] == "SOPORTADO_BASE"
    assert casos["RETENCIONES_SUFRIDAS"]["estado"] == "SOPORTADO_BASE"
    assert casos["ANULACION_COBRANZA"]["estado"] == "SOPORTADO_BASE"
    assert casos["ANTICIPO_CLIENTE"]["estado"] == "REQUIERE_REVISION"
    assert casos["SALDO_A_FAVOR_CLIENTE"]["estado"] == "REQUIERE_REVISION"
    assert casos["DIFERENCIA_COBRO"]["estado"] == "REQUIERE_REVISION"


def test_diagnostico_plan_empresa_detecta_usos_contables(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_cobranzas(
        db_path=db_path,
        archivo_servicio_cobranzas=service_path,
        archivo_ui_cobranzas=ui_path,
    )

    usos = diagnostico["plan_empresa"]["usos_detectados"]

    assert usos["deudores_por_ventas"] is True
    assert usos["anticipos_de_clientes"] is True
    assert usos["retenciones_iva_sufridas"] is True
    assert usos["retenciones_iibb_sufridas"] is True
    assert usos["retenciones_ganancias_sufridas"] is True
    assert usos["saldos_a_favor_clientes"] is True
    assert usos["diferencias_cobro"] is True


def test_diagnostico_detecta_tablas_estructurales_pendientes(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_cobranzas(
        db_path=db_path,
        archivo_servicio_cobranzas=service_path,
        archivo_ui_cobranzas=ui_path,
    )

    assert diagnostico["tablas"]["clientes"]["existe"] is False
    assert diagnostico["tablas"]["recibos_emitidos"]["existe"] is False
    assert diagnostico["tablas"]["cobranzas_anticipos_clientes"]["existe"] is False

    codigos = {h["codigo"] for h in diagnostico["hallazgos"]}
    assert "COBRANZAS_TABLA_ESTRUCTURAL_PENDIENTE_CLIENTES" in codigos
    assert "COBRANZAS_TABLA_ESTRUCTURAL_PENDIENTE_RECIBOS_EMITIDOS" in codigos


def test_resumen_y_exportacion_texto_funcionan(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_cobranzas(
        db_path=db_path,
        archivo_servicio_cobranzas=service_path,
        archivo_ui_cobranzas=ui_path,
    )

    resumen = obtener_resumen_diagnostico_cobranzas(diagnostico)
    texto = exportar_diagnostico_cobranzas_como_texto(diagnostico)

    assert resumen["estado"] == "REQUIERE_REVISION"
    assert "libro_diario" in resumen["impactos_directos_detectados"]
    assert "retenciones" in resumen["impactos_directos_detectados"]
    assert "retenciones_ui" in resumen["capacidades_ui_detectadas"]
    assert resumen["casos_requeridos_total"] == 7

    assert "Cobranzas PRO v1" in texto
    assert "COBRANZA_FACTURA_TOTAL" in texto
    assert "COBRANZAS_ASIENTO_DIRECTO_LIBRO_DIARIO" in texto


def test_base_inexistente_devuelve_sin_base(tmp_path):
    db_path = tmp_path / "no_existe.db"
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_cobranzas(
        db_path=db_path,
        archivo_servicio_cobranzas=service_path,
        archivo_ui_cobranzas=ui_path,
    )

    resumen = obtener_resumen_diagnostico_cobranzas(diagnostico)

    assert diagnostico["estado"] == "SIN_BASE"
    assert resumen["hallazgos_criticos"] == 1
    assert diagnostico["hallazgos"][0]["codigo"] == "COBRANZAS_DB_NO_ENCONTRADA"

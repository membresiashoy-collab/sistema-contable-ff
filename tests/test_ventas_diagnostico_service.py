import sqlite3

from services.ventas_diagnostico_service import (
    TIPOS_VENTA_REQUERIDOS,
    diagnosticar_ventas,
    exportar_diagnostico_ventas_como_texto,
    obtener_resumen_diagnostico_ventas,
)


def crear_base_minima(tmp_path):
    db_path = tmp_path / "ventas_test.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE ventas_comprobantes (
                id INTEGER PRIMARY KEY,
                fecha TEXT,
                cliente TEXT,
                cuit TEXT,
                neto REAL,
                iva REAL,
                total REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE cuenta_corriente_clientes (
                id INTEGER PRIMARY KEY,
                fecha TEXT,
                cliente TEXT,
                cuit TEXT,
                tipo TEXT,
                numero TEXT,
                debe REAL,
                haber REAL,
                saldo REAL
            )
            """
        )
        conn.execute("CREATE TABLE clientes_configuracion (id INTEGER PRIMARY KEY, nombre TEXT)")
        conn.execute("CREATE TABLE cobranzas (id INTEGER PRIMARY KEY, cliente TEXT, total REAL)")
        conn.execute("CREATE TABLE cobranzas_imputaciones (id INTEGER PRIMARY KEY, cobranza_id INTEGER)")
        conn.execute("CREATE TABLE cobranzas_retenciones (id INTEGER PRIMARY KEY, cobranza_id INTEGER)")
        conn.execute("CREATE TABLE iva_movimientos_fiscales (id INTEGER PRIMARY KEY, concepto TEXT, importe REAL)")
        conn.execute("CREATE TABLE mapeos_contables_empresa (id INTEGER PRIMARY KEY, uso_operativo TEXT)")
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
                ("4.1.01", "VENTAS DE MERCADERIAS", 1),
                ("4.1.02", "VENTAS DE SERVICIOS", 1),
                ("2.1.01", "IVA DEBITO FISCAL", 1),
                ("2.1.10", "ANTICIPOS DE CLIENTES", 1),
            ],
        )
        conn.commit()

    return db_path


def crear_archivos_codigo(tmp_path):
    service_path = tmp_path / "ventas_service.py"
    ui_path = tmp_path / "ventas.py"

    contenido_service = """
def op_insert_libro_diario():
    sql = "INSERT INTO libro_diario (cuenta) VALUES (?)"
    cuenta_1 = "DEUDORES POR VENTAS"
    cuenta_2 = "VENTAS"
    cuenta_3 = "IVA DEBITO FISCAL"
    return sql, cuenta_1, cuenta_2, cuenta_3


def op_insert_venta():
    sql = "INSERT INTO ventas_comprobantes (cliente) VALUES (?)"
    return sql


def op_insert_cta_cte_cliente():
    sql = "INSERT INTO cuenta_corriente_clientes (cliente) VALUES (?)"
    return sql


def op_insert_comprobante_procesado():
    sql = "INSERT INTO comprobantes_procesados (modulo) VALUES ('VENTAS')"
    return sql
"""

    contenido_ui = """
def mostrar_ventas():
    return "Carga CSV ARCA/AFIP, genera asientos contables y cuenta corriente clientes."
"""

    service_path.write_text(contenido_service, encoding="utf-8")
    ui_path.write_text(contenido_ui, encoding="utf-8")

    return service_path, ui_path


def test_diagnostico_detecta_hardcodes_e_impactos_directos(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_ventas(
        db_path=db_path,
        archivo_servicio_ventas=service_path,
        archivo_ui_ventas=ui_path,
    )

    assert diagnostico["estado"] == "REQUIERE_REVISION"

    cuentas = {item["cuenta"] for item in diagnostico["hardcodes_contables"]}
    assert "DEUDORES POR VENTAS" in cuentas
    assert "VENTAS" in cuentas
    assert "IVA DEBITO FISCAL" in cuentas

    assert diagnostico["impactos_directos"]["libro_diario"]["detectado"] is True
    assert diagnostico["impactos_directos"]["ventas_comprobantes"]["detectado"] is True
    assert diagnostico["impactos_directos"]["cuenta_corriente_clientes"]["detectado"] is True
    assert diagnostico["impactos_directos"]["comprobantes_procesados"]["detectado"] is True

    codigos = {h["codigo"] for h in diagnostico["hallazgos"]}
    assert "VENTAS_CUENTAS_HARDCODEADAS" in codigos
    assert "VENTAS_ASIENTO_DIRECTO_LIBRO_DIARIO" in codigos


def test_diagnostico_incluye_tipos_de_venta_requeridos(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_ventas(
        db_path=db_path,
        archivo_servicio_ventas=service_path,
        archivo_ui_ventas=ui_path,
    )

    codigos = {tipo["codigo"] for tipo in diagnostico["tipos_venta_requeridos"]}

    assert len(TIPOS_VENTA_REQUERIDOS) >= 10
    assert "VENTA_MERCADERIAS" in codigos
    assert "VENTA_SERVICIOS" in codigos
    assert "VENTA_BIEN_USO" in codigos
    assert "VENTA_EXENTA" in codigos
    assert "VENTA_NO_GRAVADA" in codigos
    assert "EXPORTACION_BIENES" in codigos
    assert "EXPORTACION_SERVICIOS" in codigos
    assert "NOTA_CREDITO" in codigos
    assert "NOTA_DEBITO" in codigos
    assert "ANTICIPO_CLIENTE" in codigos


def test_diagnostico_detecta_tablas_estructurales_pendientes(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_ventas(
        db_path=db_path,
        archivo_servicio_ventas=service_path,
        archivo_ui_ventas=ui_path,
    )

    assert diagnostico["tablas"]["ventas_detalle"]["existe"] is False
    assert diagnostico["tablas"]["ventas_items"]["existe"] is False
    assert diagnostico["tablas"]["clientes"]["existe"] is False
    assert diagnostico["tablas"]["ventas_clientes"]["existe"] is False
    assert diagnostico["tablas"]["recibos_emitidos"]["existe"] is False

    codigos = {h["codigo"] for h in diagnostico["hallazgos"]}
    assert "VENTAS_TABLA_ESTRUCTURAL_PENDIENTE_VENTAS_DETALLE" in codigos
    assert "VENTAS_TABLA_ESTRUCTURAL_PENDIENTE_CLIENTES" in codigos


def test_diagnostico_plan_empresa_detecta_usos_sensibles(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_ventas(
        db_path=db_path,
        archivo_servicio_ventas=service_path,
        archivo_ui_ventas=ui_path,
    )

    plan = diagnostico["plan_empresa"]

    assert plan["existe"] is True
    assert plan["registros"] == 5
    assert plan["usos_detectados"]["deudores_por_ventas"] is True
    assert plan["usos_detectados"]["ventas_mercaderias"] is True
    assert plan["usos_detectados"]["ventas_servicios"] is True
    assert plan["usos_detectados"]["iva_debito_fiscal"] is True
    assert plan["usos_detectados"]["anticipos_de_clientes"] is True


def test_resumen_y_exportacion_texto_funcionan(tmp_path):
    db_path = crear_base_minima(tmp_path)
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_ventas(
        db_path=db_path,
        archivo_servicio_ventas=service_path,
        archivo_ui_ventas=ui_path,
    )

    resumen = obtener_resumen_diagnostico_ventas(diagnostico)
    texto = exportar_diagnostico_ventas_como_texto(diagnostico)

    assert resumen["estado"] == "REQUIERE_REVISION"
    assert resumen["hardcodes_contables"] >= 3
    assert "libro_diario" in resumen["impactos_directos_detectados"]

    assert "Ventas PRO v1" in texto
    assert "VENTA_MERCADERIAS" in texto
    assert "VENTAS_CUENTAS_HARDCODEADAS" in texto


def test_diagnostico_base_inexistente_devuelve_critico(tmp_path):
    db_path = tmp_path / "no_existe.db"
    service_path, ui_path = crear_archivos_codigo(tmp_path)

    diagnostico = diagnosticar_ventas(
        db_path=db_path,
        archivo_servicio_ventas=service_path,
        archivo_ui_ventas=ui_path,
    )

    assert diagnostico["estado"] == "SIN_BASE"
    assert diagnostico["hallazgos"][0]["codigo"] == "VENTAS_DB_NO_ENCONTRADA"

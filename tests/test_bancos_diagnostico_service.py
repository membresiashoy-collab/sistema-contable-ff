import sqlite3

from services.bancos_diagnostico_service import diagnosticar_banco_caja, diagnosticar_bancos


def _crear_conexion_base():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            imputable INTEGER,
            estado TEXT,
            uso_operativo_sistema TEXT,
            cuenta_maestro_id INTEGER
        );

        CREATE TABLE bancos_cuentas (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            banco TEXT,
            nombre_cuenta TEXT,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT
        );

        CREATE TABLE bancos_importaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            nombre_archivo TEXT,
            banco TEXT,
            nombre_cuenta TEXT,
            procesados INTEGER,
            duplicados INTEGER,
            saldo_inicial_extracto REAL,
            saldo_final_extracto REAL,
            saldo_final_calculado REAL,
            diferencia_saldo REAL,
            fecha_carga TEXT
        );

        CREATE TABLE bancos_movimientos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            importacion_id INTEGER,
            banco TEXT,
            nombre_cuenta TEXT,
            fecha TEXT,
            referencia TEXT,
            causal TEXT,
            concepto TEXT,
            importe REAL,
            debito REAL,
            credito REAL,
            saldo REAL,
            importe_conciliado REAL,
            importe_pendiente REAL,
            porcentaje_conciliado REAL,
            tipo_movimiento_sugerido TEXT,
            cuenta_debe_codigo TEXT,
            cuenta_debe_nombre TEXT,
            cuenta_haber_codigo TEXT,
            cuenta_haber_nombre TEXT,
            tratamiento_fiscal TEXT,
            alicuota_iva_sugerida REAL,
            estado_conciliacion TEXT,
            estado_contable TEXT,
            clave_movimiento TEXT
        );

        CREATE TABLE bancos_grupos_fiscales (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            importacion_id INTEGER,
            movimiento_banco_id INTEGER,
            fecha TEXT,
            banco TEXT,
            nombre_cuenta TEXT,
            iva_credito_21 REAL,
            iva_credito_105 REAL,
            iva_sin_base REAL,
            percepcion_iva REAL,
            percepcion_iibb REAL,
            total_banco REAL,
            estado_revision TEXT
        );

        CREATE TABLE bancos_asientos_propuestos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            movimiento_banco_id INTEGER,
            conciliacion_id INTEGER,
            fecha TEXT,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            debe REAL,
            haber REAL,
            glosa TEXT,
            estado TEXT
        );

        CREATE TABLE bancos_conciliaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            movimiento_banco_id INTEGER,
            fecha TEXT,
            tipo_conciliacion TEXT,
            estado TEXT,
            importe_total REAL,
            importe_imputado REAL,
            importe_pendiente REAL,
            porcentaje_conciliado REAL
        );

        CREATE TABLE bancos_conciliaciones_detalle (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            conciliacion_id INTEGER,
            movimiento_banco_id INTEGER,
            tipo_imputacion TEXT,
            entidad_tabla TEXT,
            entidad_id INTEGER,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            importe_imputado REAL,
            saldo_anterior REAL,
            saldo_posterior REAL
        );
        """
    )
    con.commit()
    return con


def test_diagnostico_detecta_tablas_faltantes_sin_inicializar():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row

    resultado = diagnosticar_bancos(conexion=con)

    assert resultado["solo_lectura"] is True
    assert resultado["estado"] == "CRITICO"
    assert resultado["resumen"]["tablas_detectadas"] == 0
    assert any(alerta["codigo"] == "BANCO_CAJA_TABLA_INEXISTENTE" for alerta in resultado["alertas"])


def test_diagnostico_detecta_cuenta_bancaria_sin_cuenta_contable():
    con = _crear_conexion_base()
    con.execute(
        "INSERT INTO bancos_cuentas (empresa_id, banco, nombre_cuenta, cuenta_contable_codigo, cuenta_contable_nombre) VALUES (1, 'Macro', 'Principal', '', '')"
    )
    con.commit()

    resultado = diagnosticar_bancos(conexion=con)

    assert resultado["resumen"]["cuentas_bancarias_sin_cuenta_contable"] == 1
    assert any(alerta["codigo"] == "BANCO_CAJA_CUENTA_SIN_CUENTA_CONTABLE" for alerta in resultado["alertas"])


def test_diagnostico_valida_cuenta_plan_inactiva_y_no_imputable():
    con = _crear_conexion_base()
    con.execute(
        "INSERT INTO plan_cuentas_empresa (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema) VALUES (1, '1.1.02', 'Banco modelo', 0, 'INACTIVA', 'BANCO')"
    )
    con.execute(
        "INSERT INTO bancos_cuentas (empresa_id, banco, nombre_cuenta, cuenta_contable_codigo, cuenta_contable_nombre) VALUES (1, 'Macro', 'Principal', '1.1.02', 'Banco modelo')"
    )
    con.commit()

    resultado = diagnosticar_bancos(conexion=con)

    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
    assert "BANCO_CAJA_CUENTA_PLAN_INACTIVA" in codigos
    assert "BANCO_CAJA_CUENTA_PLAN_NO_IMPUTABLE" in codigos
    assert resultado["resumen"]["cuentas_bancarias_con_plan_incompatible"] == 1


def test_diagnostico_detecta_importacion_con_diferencia_de_saldo():
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_importaciones
        (empresa_id, nombre_archivo, banco, nombre_cuenta, procesados, duplicados, saldo_inicial_extracto, saldo_final_extracto, saldo_final_calculado, diferencia_saldo)
        VALUES (1, 'extracto.csv', 'Macro', 'Principal', 10, 0, 100, 200, 180, 20)
        """
    )
    con.commit()

    resultado = diagnosticar_bancos(conexion=con)

    assert resultado["resumen"]["importaciones_con_diferencia_saldo"] == 1
    assert resultado["importaciones"]["con_diferencia_saldo"][0]["diferencia_saldo"] == 20


def test_diagnostico_detecta_movimiento_pendiente_inconsistente_y_sin_clave():
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_movimientos
        (empresa_id, importacion_id, banco, nombre_cuenta, fecha, concepto, importe, debito, credito, importe_conciliado, importe_pendiente,
         tipo_movimiento_sugerido, estado_conciliacion, estado_contable, clave_movimiento)
        VALUES (1, 1, 'Macro', 'Principal', '2026-05-01', 'Pago proveedor', -100, 100, 0, 20, 90, 'PAGO_POSIBLE', 'PENDIENTE', 'NO_CONTABILIZADO', '')
        """
    )
    con.commit()

    resultado = diagnosticar_bancos(conexion=con)

    assert resultado["resumen"]["movimientos_sin_clave"] == 1
    assert resultado["resumen"]["movimientos_con_saldo_pendiente_inconsistente"] == 1
    assert resultado["movimientos"]["saldo_pendiente_inconsistente"][0]["pendiente_calculado"] == 80


def test_diagnostico_detecta_movimientos_duplicados_por_clave():
    con = _crear_conexion_base()
    for concepto in ("Comision", "Comision repetida"):
        con.execute(
            """
            INSERT INTO bancos_movimientos
            (empresa_id, banco, nombre_cuenta, fecha, concepto, importe, debito, credito, importe_conciliado, importe_pendiente,
             tipo_movimiento_sugerido, estado_conciliacion, estado_contable, clave_movimiento)
            VALUES (1, 'Macro', 'Principal', '2026-05-01', ?, -10, 10, 0, 0, 10, 'GASTO_BANCARIO_GRAVADO', 'PENDIENTE', 'NO_CONTABILIZADO', 'CLAVE-1')
            """,
            (concepto,),
        )
    con.commit()

    resultado = diagnosticar_bancos(conexion=con)

    assert resultado["resumen"]["movimientos_duplicados_potenciales"] == 2
    assert resultado["movimientos"]["duplicados_potenciales"][0]["cantidad"] == 2


def test_diagnostico_detecta_asiento_desbalanceado():
    con = _crear_conexion_base()
    con.execute(
        "INSERT INTO bancos_asientos_propuestos (empresa_id, movimiento_banco_id, debe, haber, estado) VALUES (1, 10, 100, 0, 'PROPUESTO')"
    )
    con.execute(
        "INSERT INTO bancos_asientos_propuestos (empresa_id, movimiento_banco_id, debe, haber, estado) VALUES (1, 10, 0, 90, 'PROPUESTO')"
    )
    con.commit()

    resultado = diagnosticar_bancos(conexion=con)

    assert resultado["resumen"]["asientos_propuestos_desbalanceados"] == 1
    assert resultado["asientos_propuestos"]["desbalanceados_por_movimiento"][0]["diferencia"] == 10


def test_diagnostico_detecta_conciliacion_activa_sin_detalle_y_alias():
    con = _crear_conexion_base()
    con.execute(
        "INSERT INTO bancos_conciliaciones (empresa_id, movimiento_banco_id, tipo_conciliacion, estado, importe_total, importe_imputado) VALUES (1, 1, 'COBRO_CLIENTE', 'CONFIRMADA', 100, 100)"
    )
    con.commit()

    resultado = diagnosticar_banco_caja(conexion=con)

    assert resultado["resumen"]["conciliaciones_activas_sin_detalle"] == 1
    assert any(alerta["codigo"] == "BANCO_CAJA_CONCILIACION_ACTIVA_SIN_DETALLE" for alerta in resultado["alertas"])

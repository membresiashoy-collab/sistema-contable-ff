import sqlite3

from services.cajas_diagnostico_service import diagnosticar_cajas


def crear_schema_caja(conn):
    conn.executescript(
        """
        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            tipo_cuenta TEXT,
            nombre TEXT,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT,
            activo INTEGER
        );
        CREATE TABLE tesoreria_medios_pago (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            tipo TEXT,
            activo INTEGER
        );
        CREATE TABLE caja_movimientos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            fecha TEXT,
            tipo_movimiento TEXT,
            caja_id_origen INTEGER,
            caja_id_destino INTEGER,
            importe REAL,
            estado TEXT,
            tesoreria_operacion_id INTEGER
        );
        CREATE TABLE caja_arqueos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            caja_id INTEGER,
            diferencia REAL,
            estado TEXT,
            movimiento_ajuste_id INTEGER
        );
        CREATE TABLE caja_asientos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            movimiento_caja_id INTEGER,
            arqueo_id INTEGER,
            debe REAL,
            haber REAL,
            estado TEXT
        );
        CREATE TABLE caja_auditoria (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            accion TEXT,
            motivo TEXT
        );
        CREATE TABLE tesoreria_operaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            origen_modulo TEXT
        );
        """
    )


def test_diagnostico_cajas_es_solo_lectura():
    conn = sqlite3.connect(":memory:")
    crear_schema_caja(conn)
    conn.execute(
        "INSERT INTO tesoreria_cuentas (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, activo) VALUES (1, 'CAJA', 'Caja principal', '1.1.01.01', 1)"
    )
    conn.execute(
        "INSERT INTO tesoreria_medios_pago (empresa_id, codigo, nombre, tipo, activo) VALUES (1, 'EFECTIVO', 'Efectivo', 'EFECTIVO', 1)"
    )
    antes = conn.total_changes
    resultado = diagnosticar_cajas(conn, empresa_id=1)
    despues = conn.total_changes
    assert resultado["solo_lectura"] is True
    assert resultado["acciones_realizadas"] == []
    assert antes == despues


def test_diagnostico_detecta_caja_activa_sin_cuenta_contable():
    conn = sqlite3.connect(":memory:")
    crear_schema_caja(conn)
    conn.execute(
        "INSERT INTO tesoreria_cuentas (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, activo) VALUES (1, 'CAJA', 'Caja sin cuenta', NULL, 1)"
    )
    conn.execute(
        "INSERT INTO tesoreria_medios_pago (empresa_id, codigo, nombre, tipo, activo) VALUES (1, 'EFECTIVO', 'Efectivo', 'EFECTIVO', 1)"
    )
    resultado = diagnosticar_cajas(conn, empresa_id=1)
    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert resultado["estado"] == "REQUIERE_REVISION"
    assert "CAJA_CUENTAS_SIN_CUENTA_CONTABLE" in codigos


def test_diagnostico_detecta_movimiento_importe_invalido():
    conn = sqlite3.connect(":memory:")
    crear_schema_caja(conn)
    conn.execute(
        "INSERT INTO tesoreria_cuentas (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, activo) VALUES (1, 'CAJA', 'Caja principal', '1.1.01.01', 1)"
    )
    conn.execute(
        "INSERT INTO tesoreria_medios_pago (empresa_id, codigo, nombre, tipo, activo) VALUES (1, 'EFECTIVO', 'Efectivo', 'EFECTIVO', 1)"
    )
    conn.execute(
        "INSERT INTO caja_movimientos (empresa_id, fecha, tipo_movimiento, caja_id_origen, importe, estado) VALUES (1, '2026-01-01', 'INGRESO', 1, 0, 'ACTIVO')"
    )
    resultado = diagnosticar_cajas(conn, empresa_id=1)
    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert "CAJA_MOVIMIENTOS_IMPORTE_INVALIDO" in codigos


def test_diagnostico_critico_si_faltan_tablas_base():
    conn = sqlite3.connect(":memory:")
    resultado = diagnosticar_cajas(conn, empresa_id=1)
    assert resultado["estado"] == "CRITICO"
    assert any(a["nivel"] == "CRITICO" for a in resultado["alertas"])


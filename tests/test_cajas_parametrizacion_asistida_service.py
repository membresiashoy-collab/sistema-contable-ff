import sqlite3

from services.cajas_parametrizacion_asistida_service import generar_parametrizacion_asistida_cajas


def crear_schema_param_caja(conn):
    conn.executescript(
        """
        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            tipo_cuenta TEXT,
            nombre TEXT,
            cuenta_contable_codigo TEXT,
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
            tipo_movimiento TEXT,
            importe REAL,
            estado TEXT
        );
        CREATE TABLE caja_arqueos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            diferencia REAL,
            estado TEXT
        );
        CREATE TABLE cobranzas (id INTEGER PRIMARY KEY, empresa_id INTEGER);
        CREATE TABLE pagos (id INTEGER PRIMARY KEY, empresa_id INTEGER);
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            activo INTEGER
        );
        CREATE TABLE mapeos_contables_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            uso_operativo TEXT,
            cuenta_codigo TEXT,
            activo INTEGER
        );
        """
    )
    conn.execute("INSERT INTO plan_cuentas_empresa (empresa_id, codigo, nombre, activo) VALUES (1, '1.1.01.01', 'Caja', 1)")
    conn.execute("INSERT INTO plan_cuentas_empresa (empresa_id, codigo, nombre, activo) VALUES (1, '6.2.01', 'Diferencias de caja', 1)")
    conn.execute("INSERT INTO plan_cuentas_empresa (empresa_id, codigo, nombre, activo) VALUES (1, '5.2.01', 'Sobrantes de caja', 1)")


def test_parametrizacion_caja_genera_matriz_de_solo_lectura():
    conn = sqlite3.connect(":memory:")
    crear_schema_param_caja(conn)
    antes = conn.total_changes
    resultado = generar_parametrizacion_asistida_cajas(conn, empresa_id=1)
    despues = conn.total_changes
    assert resultado["solo_lectura"] is True
    assert resultado["acciones_realizadas"] == []
    assert antes == despues
    assert resultado["resumen"]["casos_total"] == len(resultado["matriz"])


def test_parametrizacion_caja_detecta_mapeo_activo_configurado():
    conn = sqlite3.connect(":memory:")
    crear_schema_param_caja(conn)
    conn.execute(
        "INSERT INTO mapeos_contables_empresa (empresa_id, uso_operativo, cuenta_codigo, activo) VALUES (1, 'CAJA_EFECTIVO', '1.1.01.01', 1)"
    )
    resultado = generar_parametrizacion_asistida_cajas(conn, empresa_id=1)
    caja_efectivo = next(c for c in resultado["matriz"] if c["codigo"] == "CAJA_EFECTIVO")
    assert caja_efectivo["estado"] == "CONFIGURADO"
    assert caja_efectivo["mapeo_activo_detectado"] is True


def test_parametrizacion_caja_sugiere_si_no_hay_mapeo():
    conn = sqlite3.connect(":memory:")
    crear_schema_param_caja(conn)
    resultado = generar_parametrizacion_asistida_cajas(conn, empresa_id=1)
    estados = {c["estado"] for c in resultado["matriz"]}
    assert "SUGERIDO" in estados
    assert resultado["estado"] in {"REQUIERE_PARAMETRIZACION", "ESTRUCTURA_INCOMPLETA"}


def test_parametrizacion_caja_marca_estructura_incompleta_sin_tablas():
    conn = sqlite3.connect(":memory:")
    resultado = generar_parametrizacion_asistida_cajas(conn, empresa_id=1)
    assert resultado["resumen"]["estructura_incompleta"] > 0
    assert any(c["estado"] == "ESTRUCTURA_INCOMPLETA" for c in resultado["matriz"])


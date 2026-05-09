import sqlite3

from services.coherencia_contable_service import (
    diagnosticar_comportamientos_configurados,
    diagnosticar_nucleo_coherencia,
)
from services.comportamientos_contables_service import guardar_comportamiento_cuenta


def nueva_conexion():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def crear_plan_operativo(conn):
    conn.executescript(
        """
        CREATE TABLE plan_cuentas (
            codigo TEXT,
            nombre TEXT,
            empresa_id INTEGER DEFAULT 1,
            imputable INTEGER DEFAULT 1
        );
        INSERT INTO plan_cuentas (codigo, nombre, empresa_id, imputable) VALUES
        ('11101', 'Caja', 1, 1),
        ('11102', 'Banco Nación cuenta corriente', 1, 1),
        ('11201', 'IVA Crédito Fiscal', 1, 1),
        ('21101', 'IVA Débito Fiscal', 1, 1),
        ('31101', 'Capital Social', 1, 1),
        ('11301', 'Socios por integración', 1, 1),
        ('51101', 'Gastos varios', 1, 1);
        """
    )


def configurar_comportamientos_basicos(conn):
    for codigo, comportamiento in (
        ('11101', 'CAJA'),
        ('11102', 'BANCO'),
        ('11201', 'IVA_CREDITO'),
        ('21101', 'IVA_DEBITO'),
        ('31101', 'CAPITAL_SOCIAL'),
        ('11301', 'SOCIOS_INTEGRACION'),
    ):
        resultado = guardar_comportamiento_cuenta(
            empresa_id=1,
            codigo_cuenta=codigo,
            comportamiento=comportamiento,
            usuario='tester',
            conn=conn,
        )
        assert resultado['ok'] is True


def test_diagnostico_detecta_tesoreria_sin_comportamiento_configurado():
    conn = nueva_conexion()
    crear_plan_operativo(conn)
    conn.executescript(
        """
        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            tipo_cuenta TEXT,
            nombre TEXT,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT,
            activo INTEGER DEFAULT 1
        );
        INSERT INTO tesoreria_cuentas
        (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
        (1, 'CAJA', 'Caja principal', '11101', 'Caja', 1),
        (1, 'BANCO', 'Banco Nación', '11102', 'Banco Nación cuenta corriente', 1);
        """
    )

    diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)
    codigos = {item['codigo'] for item in diagnosticos}

    assert 'COMPORTAMIENTOS_SIN_CONFIGURACION' in codigos


def test_diagnostico_baja_advertencias_de_tesoreria_cuando_el_mapa_esta_configurado():
    conn = nueva_conexion()
    crear_plan_operativo(conn)
    configurar_comportamientos_basicos(conn)
    conn.executescript(
        """
        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            tipo_cuenta TEXT,
            nombre TEXT,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT,
            activo INTEGER DEFAULT 1
        );
        INSERT INTO tesoreria_cuentas
        (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
        (1, 'CAJA', 'Caja principal', '11101', 'Caja', 1),
        (1, 'BANCO', 'Banco Nación', '11102', 'Banco Nación cuenta corriente', 1);
        """
    )

    diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)
    codigos = {item['codigo'] for item in diagnosticos}

    assert 'TESORERIA_CAJAS_SIN_COMPORTAMIENTO_CAJA' not in codigos
    assert 'TESORERIA_BANCOS_SIN_COMPORTAMIENTO_BANCO' not in codigos
    assert 'COMPORTAMIENTOS_OPERATIVOS_OK' in codigos


def test_diagnostico_detecta_capital_e_iva_con_cuentas_no_mapeadas():
    conn = nueva_conexion()
    crear_plan_operativo(conn)
    guardar_comportamiento_cuenta(
        empresa_id=1,
        codigo_cuenta='11101',
        comportamiento='CAJA',
        usuario='tester',
        conn=conn,
    )
    conn.executescript(
        """
        CREATE TABLE capital_social_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'PROPUESTO',
            cuenta_capital_codigo TEXT,
            cuenta_capital_nombre TEXT,
            cuenta_socios_integracion_codigo TEXT,
            cuenta_socios_integracion_nombre TEXT
        );
        INSERT INTO capital_social_empresa
        (empresa_id, estado, cuenta_capital_codigo, cuenta_capital_nombre, cuenta_socios_integracion_codigo, cuenta_socios_integracion_nombre)
        VALUES
        (1, 'PROPUESTO', '31101', 'Capital Social', '11301', 'Socios por integración');

        CREATE TABLE iva_cierres_asientos_propuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'PROPUESTO',
            cuenta_codigo TEXT,
            cuenta_nombre TEXT
        );
        INSERT INTO iva_cierres_asientos_propuestos
        (empresa_id, estado, cuenta_codigo, cuenta_nombre)
        VALUES
        (1, 'PROPUESTO', '11201', 'IVA Crédito Fiscal'),
        (1, 'PROPUESTO', '21101', 'IVA Débito Fiscal');
        """
    )

    diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)
    codigos = {item['codigo'] for item in diagnosticos}

    assert 'CAPITAL_CUENTA_CAPITAL_SIN_COMPORTAMIENTO' in codigos
    assert 'CAPITAL_CUENTA_SOCIOS_SIN_COMPORTAMIENTO' in codigos
    assert 'IVA_CUENTA_CREDITO_SIN_COMPORTAMIENTO' in codigos
    assert 'IVA_CUENTA_DEBITO_SIN_COMPORTAMIENTO' in codigos


def test_diagnostico_nucleo_incluye_revision_de_comportamientos_operativos():
    conn = nueva_conexion()
    conn.executescript(
        """
        CREATE TABLE ejercicios_contables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            es_actual INTEGER,
            estado TEXT
        );
        INSERT INTO ejercicios_contables (empresa_id, fecha_inicio, fecha_fin, es_actual, estado)
        VALUES (1, '2025-01-01', '2025-12-31', 1, 'ABIERTO');

        CREATE TABLE plan_cuentas (
            codigo TEXT,
            nombre TEXT,
            empresa_id INTEGER DEFAULT 1,
            imputable INTEGER DEFAULT 1
        );
        INSERT INTO plan_cuentas (codigo, nombre, empresa_id, imputable) VALUES
        ('11101', 'Caja', 1, 1),
        ('11102', 'Banco Nación cuenta corriente', 1, 1);

        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            tipo_cuenta TEXT,
            nombre TEXT,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT,
            activo INTEGER DEFAULT 1
        );
        INSERT INTO tesoreria_cuentas
        (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
        (1, 'CAJA', 'Caja principal', '11101', 'Caja', 1);
        """
    )

    diagnosticos = diagnosticar_nucleo_coherencia(empresa_id=1, conn=conn)
    codigos = {item['codigo'] for item in diagnosticos}

    assert 'COMPORTAMIENTOS_SIN_CONFIGURACION' in codigos
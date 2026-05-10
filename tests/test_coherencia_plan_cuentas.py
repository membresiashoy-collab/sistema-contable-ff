import sqlite3

from services.coherencia_contable_service import (
    diagnosticar_asientos_propuestos_plan_cuentas,
    diagnosticar_comportamientos_configurados,
    diagnosticar_nucleo_coherencia,
    diagnosticar_plan_cuentas,
    diagnosticar_vinculacion_plan_maestro,
)
from services.plan_cuentas_service import asegurar_estructura_plan_cuentas, guardar_cuenta_plan


def nueva_conexion():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def cargar_plan_basico(conn):
    asegurar_estructura_plan_cuentas(conn)
    guardar_cuenta_plan(empresa_id=1, codigo="1.1.01", nombre="CAJA", imputable="S", comportamiento_contable="CAJA", conn=conn)
    guardar_cuenta_plan(empresa_id=1, codigo="1.1.02", nombre="BANCO CUENTA CORRIENTE", imputable="S", comportamiento_contable="BANCO", conn=conn)
    guardar_cuenta_plan(empresa_id=1, codigo="1.3.01", nombre="IVA CREDITO FISCAL", imputable="S", comportamiento_contable="IVA_CREDITO", conn=conn)
    guardar_cuenta_plan(empresa_id=1, codigo="2.2.01", nombre="IVA DEBITO FISCAL", imputable="S", comportamiento_contable="IVA_DEBITO", conn=conn)
    guardar_cuenta_plan(empresa_id=1, codigo="3.1.01", nombre="CAPITAL SOCIAL", imputable="S", comportamiento_contable="CAPITAL_SOCIAL", conn=conn)


def test_diagnostico_plan_cuentas_usa_plan_como_fuente_de_verdad():
    conn = nueva_conexion()
    cargar_plan_basico(conn)
    # Tabla histórica contaminada: no debe reemplazar la fuente principal plan_cuentas.
    conn.execute(
        """
        INSERT INTO contabilidad_cuentas_comportamiento
        (empresa_id, codigo_cuenta, cuenta_nombre, comportamiento, activo, estado, origen)
        VALUES (1, '1', 'ACTIVO', 'IVA_DEBITO', 1, 'ACTIVO', 'MANUAL')
        """
    )

    diagnosticos = diagnosticar_plan_cuentas(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}

    assert "PLAN_CUENTA_NO_IMPUTABLE_CON_COMPORTAMIENTO" not in codigos
    assert any(item["severidad"] in {"OK", "INFO", "ADVERTENCIA"} for item in diagnosticos)


def test_diagnostico_comportamientos_lee_comportamientos_del_plan():
    conn = nueva_conexion()
    cargar_plan_basico(conn)
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
        VALUES (1, 'CAJA', 'Caja principal', '1.1.01', 'CAJA', 1),
               (1, 'BANCO', 'Banco principal', '1.1.02', 'BANCO CUENTA CORRIENTE', 1);
        """
    )

    diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}

    assert "TESORERIA_CAJAS_SIN_COMPORTAMIENTO_CAJA" not in codigos
    assert "TESORERIA_BANCOS_SIN_COMPORTAMIENTO_BANCO" not in codigos


def test_diagnostico_detecta_cuentas_empresa_heredadas_y_vinculos_maestro():
    conn = nueva_conexion()
    conn.executescript(
        """
        CREATE TABLE plan_cuentas_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            estado TEXT DEFAULT 'ACTIVA'
        );

        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            cuenta_maestro_id INTEGER,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            imputable INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA'
        );

        INSERT INTO plan_cuentas_maestro (id, codigo, nombre, estado) VALUES
        (1, '1.1.01', 'Caja', 'ACTIVA'),
        (2, '1.1.02', 'Banco cuenta corriente', 'ACTIVA'),
        (3, '1', 'Activo', 'ACTIVA');

        INSERT INTO plan_cuentas_empresa
        (empresa_id, cuenta_maestro_id, codigo, nombre, imputable, estado)
        VALUES
        (1, 1, '1.1.01', 'Caja', 1, 'ACTIVA'),
        (1, NULL, '1.1.02', 'Banco cuenta corriente heredada', 1, 'ACTIVA'),
        (1, NULL, '1', 'Activo heredado', 0, 'ACTIVA'),
        (1, NULL, '9.9.99', 'Cuenta heredada sin vínculo', 1, 'ACTIVA'),
        (1, NULL, '9', 'Agrupadora heredada sin vínculo', 0, 'ACTIVA'),
        (1, 999, '1.1.03', 'Cuenta con vínculo roto', 1, 'ACTIVA');
        """
    )

    diagnosticos = diagnosticar_vinculacion_plan_maestro(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}

    assert "PLAN_CUENTAS_EMPRESA_IMPUTABLES_HEREDADAS_PENDIENTES" in codigos
    assert "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_HEREDADAS_PENDIENTES" in codigos
    assert "PLAN_CUENTAS_EMPRESA_IMPUTABLES_SIN_VINCULO_MAESTRO" in codigos
    assert "PLAN_CUENTAS_EMPRESA_AGRUPADORAS_SIN_VINCULO_MAESTRO" in codigos
    assert "PLAN_CUENTAS_EMPRESA_VINCULO_INCONSISTENTE" in codigos

    severidades = {item["codigo"]: item["severidad"] for item in diagnosticos}
    assert severidades["PLAN_CUENTAS_EMPRESA_IMPUTABLES_SIN_VINCULO_MAESTRO"] == "ADVERTENCIA"
    assert severidades["PLAN_CUENTAS_EMPRESA_AGRUPADORAS_SIN_VINCULO_MAESTRO"] == "INFO"


def test_diagnostico_detecta_propuestas_con_cuentas_no_reconocidas_o_no_imputables():
    conn = nueva_conexion()
    conn.executescript(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            cuenta_maestro_id INTEGER,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            imputable INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA'
        );

        CREATE TABLE asientos_propuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'PROPUESTO'
        );

        CREATE TABLE asientos_propuestos_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asiento_propuesto_id INTEGER,
            renglon INTEGER,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0
        );

        INSERT INTO plan_cuentas_empresa
        (empresa_id, codigo, nombre, imputable, estado)
        VALUES
        (1, '1.1.01', 'Caja', 1, 'ACTIVA'),
        (1, '1', 'Activo', 0, 'ACTIVA');

        INSERT INTO asientos_propuestos (id, empresa_id, estado)
        VALUES (1, 1, 'PROPUESTO');

        INSERT INTO asientos_propuestos_detalle
        (asiento_propuesto_id, renglon, cuenta_codigo, cuenta_nombre, debe, haber)
        VALUES
        (1, 1, '9.9.99', 'Cuenta inexistente', 100, 0),
        (1, 2, '1', 'Activo', 0, 100);
        """
    )

    diagnosticos = diagnosticar_asientos_propuestos_plan_cuentas(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}

    assert "ASIENTOS_PROPUESTOS_CUENTA_NO_RECONOCIDA" in codigos
    assert "ASIENTOS_PROPUESTOS_CUENTA_NO_IMPUTABLE" in codigos


def test_nucleo_incluye_controles_plan_maestro_y_bandeja_asientos():
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

        CREATE TABLE plan_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            imputable INTEGER,
            comportamiento_contable TEXT
        );

        CREATE TABLE plan_cuentas_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            estado TEXT DEFAULT 'ACTIVA'
        );

        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            cuenta_maestro_id INTEGER,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            imputable INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA'
        );

        CREATE TABLE asientos_propuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'PROPUESTO'
        );

        CREATE TABLE asientos_propuestos_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asiento_propuesto_id INTEGER,
            renglon INTEGER,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0
        );

        CREATE TABLE libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            fecha TEXT,
            origen TEXT,
            origen_tabla TEXT,
            origen_id INTEGER
        );

        INSERT INTO ejercicios_contables (empresa_id, fecha_inicio, fecha_fin, es_actual, estado)
        VALUES (1, '2025-01-01', '2025-12-31', 1, 'ABIERTO');

        INSERT INTO plan_cuentas (empresa_id, codigo, nombre, imputable, comportamiento_contable)
        VALUES
        (1, '11101', 'Caja', 1, 'CAJA'),
        (1, '11102', 'Banco', 1, 'BANCO'),
        (1, '11201', 'IVA crédito fiscal', 1, 'IVA_CREDITO'),
        (1, '21101', 'IVA débito fiscal', 1, 'IVA_DEBITO'),
        (1, '31101', 'Capital social', 1, 'CAPITAL_SOCIAL'),
        (1, '11301', 'Socios por integración', 1, 'SOCIOS_INTEGRACION'),
        (1, '31201', 'Aportes irrevocables', 1, 'APORTE_IRREVOCABLE'),
        (1, '21301', 'Préstamos de socios', 1, 'PRESTAMO_SOCIO'),
        (1, '11302', 'Cuenta particular socios', 1, 'CUENTA_PARTICULAR_SOCIO'),
        (1, '51101', 'Sueldos y jornales', 1, 'SUELDOS_GASTO'),
        (1, '21201', 'Sueldos a pagar', 1, 'SUELDOS_A_PAGAR'),
        (1, '51102', 'Cargas sociales', 1, 'CARGAS_SOCIALES_GASTO'),
        (1, '21202', 'Cargas sociales a pagar', 1, 'CARGAS_SOCIALES_A_PAGAR'),
        (1, '21203', 'ART a pagar', 1, 'ART_A_PAGAR'),
        (1, '21204', 'Obra social a pagar', 1, 'OBRA_SOCIAL_A_PAGAR'),
        (1, '21205', 'Sindicato a pagar', 1, 'SINDICATO_A_PAGAR');

        INSERT INTO plan_cuentas_maestro (id, codigo, nombre, estado)
        VALUES (1, '1.1.01', 'Caja', 'ACTIVA');

        INSERT INTO plan_cuentas_empresa
        (empresa_id, cuenta_maestro_id, codigo, nombre, imputable, estado)
        VALUES
        (1, 1, '1.1.01', 'Caja', 1, 'ACTIVA'),
        (1, NULL, '9.9.99', 'Cuenta heredada sin vínculo', 1, 'ACTIVA');

        INSERT INTO asientos_propuestos (id, empresa_id, estado)
        VALUES (1, 1, 'PROPUESTO');

        INSERT INTO asientos_propuestos_detalle
        (asiento_propuesto_id, renglon, cuenta_codigo, cuenta_nombre, debe, haber)
        VALUES
        (1, 1, '8.8.88', 'Cuenta inexistente', 100, 0);

        INSERT INTO libro_diario (empresa_id, fecha, origen, origen_tabla, origen_id)
        VALUES (1, '2025-05-10', 'MANUAL', NULL, NULL);
        """
    )

    diagnosticos = diagnosticar_nucleo_coherencia(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in diagnosticos}

    assert "PLAN_CUENTAS_EMPRESA_IMPUTABLES_SIN_VINCULO_MAESTRO" in codigos
    assert "ASIENTOS_PROPUESTOS_CUENTA_NO_RECONOCIDA" in codigos
    assert "LIBRO_ASIENTOS_TRAZABILIDAD_HISTORICA_INCOMPLETA" in codigos
import sqlite3

from services.coherencia_contable_service import diagnosticar_plan_cuentas, diagnosticar_comportamientos_configurados
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
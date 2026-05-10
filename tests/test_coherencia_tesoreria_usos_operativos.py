import sqlite3

from services.coherencia_contable_service import diagnosticar_comportamientos_configurados


def _crear_base_minima():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            imputable INTEGER NOT NULL DEFAULT 1,
            estado TEXT NOT NULL DEFAULT 'ACTIVA',
            uso_operativo_sistema TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            tipo_cuenta TEXT NOT NULL,
            nombre TEXT NOT NULL,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT,
            activo INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    return conn


def _codigos(diagnosticos):
    return {item.get("codigo") for item in diagnosticos}


def test_tesoreria_reconoce_banco_cuenta_corriente_como_banco():
    conn = _crear_base_minima()
    try:
        conn.execute(
            """
            INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema)
            VALUES (1, '1.1.02.4', 'Banco Macro Cta. Cte.', 1, 'ACTIVA', 'BANCO_CUENTA_CORRIENTE')
            """
        )
        conn.execute(
            """
            INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
            VALUES (1, 'BANCO', 'Banco principal', '1.1.02.4', 'Banco Macro Cta. Cte.', 1)
            """
        )
        conn.commit()

        diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)

        assert "TESORERIA_BANCOS_SIN_COMPORTAMIENTO_BANCO" not in _codigos(diagnosticos)
        assert "TESORERIA_CUENTAS_SIN_CUENTA_CONTABLE" not in _codigos(diagnosticos)
    finally:
        conn.close()


def test_tesoreria_reconoce_caja_general_como_caja():
    conn = _crear_base_minima()
    try:
        conn.execute(
            """
            INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema)
            VALUES (1, '1.1.01.01', 'Caja', 1, 'ACTIVA', 'CAJA_GENERAL')
            """
        )
        conn.execute(
            """
            INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
            VALUES (1, 'CAJA', 'Caja principal', '1.1.01.01', 'Caja', 1)
            """
        )
        conn.commit()

        diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)

        assert "TESORERIA_CAJAS_SIN_COMPORTAMIENTO_CAJA" not in _codigos(diagnosticos)
        assert "TESORERIA_CUENTAS_SIN_CUENTA_CONTABLE" not in _codigos(diagnosticos)
    finally:
        conn.close()


def test_tesoreria_advierte_banco_con_cuenta_sin_uso_operativo_banco():
    conn = _crear_base_minima()
    try:
        conn.execute(
            """
            INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema)
            VALUES (1, '1.1.02.4', 'Banco Macro Cta. Cte.', 1, 'ACTIVA', NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
            VALUES (1, 'BANCO', 'Banco principal', '1.1.02.4', 'Banco Macro Cta. Cte.', 1)
            """
        )
        conn.commit()

        diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)

        assert "TESORERIA_BANCOS_SIN_COMPORTAMIENTO_BANCO" in _codigos(diagnosticos)
    finally:
        conn.close()
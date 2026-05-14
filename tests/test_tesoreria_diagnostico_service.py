import sqlite3

from services.tesoreria_diagnostico_service import diagnosticar_tesoreria


def _crear_conexion_base():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            estado TEXT,
            imputable INTEGER,
            uso_operativo_sistema TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            tipo_cuenta TEXT,
            nombre TEXT,
            entidad TEXT,
            numero_cuenta TEXT,
            moneda TEXT,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT,
            activo INTEGER
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE tesoreria_medios_pago (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            tipo_cuenta TEXT,
            activo INTEGER
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE tesoreria_operaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            fecha TEXT,
            tipo_operacion TEXT,
            descripcion TEXT,
            cuenta_tesoreria_id INTEGER,
            medio_pago_id INTEGER,
            importe REAL,
            estado TEXT,
            estado_conciliacion TEXT,
            importe_conciliado REAL,
            fingerprint TEXT,
            origen_modulo TEXT,
            asiento_id INTEGER,
            motivo_anulacion TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE tesoreria_operaciones_componentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            operacion_id INTEGER,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT,
            debe REAL,
            haber REAL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE tesoreria_auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER,
            accion TEXT,
            entidad TEXT,
            entidad_id INTEGER
        )
        """
    )

    con.commit()
    return con


def test_diagnostico_no_escribe_en_tablas_operativas():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema)
        VALUES
            (1, '1.1.02.01', 'Banco Macro Cta. Cte.', 'ACTIVA', 1, 'BANCO_CUENTA_CORRIENTE')
        """
    )
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
            (1, 'BANCO', 'Banco principal', '1.1.02.01', 'Banco Macro Cta. Cte.', 1)
        """
    )
    cur.execute(
        """
        INSERT INTO tesoreria_medios_pago
            (empresa_id, codigo, nombre, tipo_cuenta, activo)
        VALUES
            (1, 'TRANSFERENCIA', 'Transferencia bancaria', 'BANCO', 1)
        """
    )
    cur.execute(
        """
        INSERT INTO tesoreria_operaciones
            (empresa_id, fecha, tipo_operacion, descripcion, cuenta_tesoreria_id, medio_pago_id,
             importe, estado, estado_conciliacion, fingerprint, origen_modulo)
        VALUES
            (1, '2026-05-01', 'COBRANZA', 'Cobranza prueba', 1, 1, 1000, 'CONFIRMADA',
             'CONCILIADA', 'fp-1', 'COBRANZAS')
        """
    )
    cur.execute(
        """
        INSERT INTO tesoreria_operaciones_componentes
            (empresa_id, operacion_id, cuenta_contable_codigo, cuenta_contable_nombre, debe, haber)
        VALUES
            (1, 1, '1.1.02.01', 'Banco Macro Cta. Cte.', 1000, 0)
        """
    )
    con.commit()

    antes = {
        tabla: cur.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in (
            "tesoreria_cuentas",
            "tesoreria_medios_pago",
            "tesoreria_operaciones",
            "tesoreria_operaciones_componentes",
            "tesoreria_auditoria",
        )
    }

    resultado = diagnosticar_tesoreria(empresa_id=1, conexion=con)

    despues = {
        tabla: cur.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in antes
    }

    assert resultado["solo_lectura"] is True
    assert antes == despues
    assert resultado["resumen"]["cuentas_tesoreria"] == 1
    assert resultado["resumen"]["operaciones"] == 1


def test_diagnostico_detecta_tablas_faltantes_sin_inicializar():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row

    resultado = diagnosticar_tesoreria(empresa_id=1, conexion=con)

    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["estado"] == "CRITICO"
    assert "TESORERIA_TABLA_INEXISTENTE" in codigos
    assert resultado["resumen"]["tablas_detectadas"] == 0


def test_diagnostico_detecta_cuenta_activa_sin_cuenta_contable():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, activo)
        VALUES
            (1, 'CAJA', 'Caja principal', '', 1)
        """
    )
    con.commit()

    resultado = diagnosticar_tesoreria(empresa_id=1, conexion=con)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["estado"] == "REQUIERE_REVISION"
    assert resultado["resumen"]["cuentas_sin_cuenta_contable"] == 1
    assert "TESORERIA_CUENTA_SIN_CUENTA_CONTABLE" in codigos


def test_diagnostico_detecta_cuenta_vinculada_a_plan_no_imputable_o_inactivo():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema)
        VALUES
            (1, '1.1', 'Caja y bancos', 'ACTIVA', 0, 'BANCO')
        """
    )
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
            (1, 'BANCO', 'Banco principal', '1.1', 'Caja y bancos', 1)
        """
    )
    con.commit()

    resultado = diagnosticar_tesoreria(empresa_id=1, conexion=con)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["resumen"]["cuentas_con_plan_incompatible"] == 1
    assert "TESORERIA_CUENTA_CONTABLE_NO_IMPUTABLE" in codigos


def test_diagnostico_detecta_operaciones_pendientes_sin_componentes_sin_fingerprint_y_sin_origen():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO tesoreria_operaciones
            (empresa_id, fecha, tipo_operacion, descripcion, importe, estado, estado_conciliacion)
        VALUES
            (1, '2026-05-01', 'PAGO', 'Pago prueba', 500, 'CONFIRMADA', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = diagnosticar_tesoreria(empresa_id=1, conexion=con)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["resumen"]["operaciones_pendientes_conciliacion"] == 1
    assert resultado["resumen"]["operaciones_sin_componentes"] == 1
    assert resultado["resumen"]["operaciones_sin_fingerprint"] == 1
    assert "TESORERIA_OPERACION_SIN_COMPONENTES" in codigos
    assert "TESORERIA_OPERACION_SIN_FINGERPRINT" in codigos
    assert "TESORERIA_OPERACION_SIN_ORIGEN" in codigos


def test_diagnostico_detecta_operacion_anulada_sin_motivo():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO tesoreria_operaciones
            (empresa_id, fecha, tipo_operacion, descripcion, importe, estado, estado_conciliacion, fingerprint)
        VALUES
            (1, '2026-05-01', 'CAJA', 'Anulación prueba', 200, 'ANULADA', 'PENDIENTE', 'fp-anulada')
        """
    )
    con.commit()

    resultado = diagnosticar_tesoreria(empresa_id=1, conexion=con)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["resumen"]["operaciones_anuladas"] == 1
    assert "TESORERIA_OPERACION_ANULADA_SIN_MOTIVO" in codigos


def test_diagnostico_detecta_duplicidad_por_fingerprint():
    con = _crear_conexion_base()
    cur = con.cursor()
    for descripcion in ("Movimiento A", "Movimiento B"):
        cur.execute(
            """
            INSERT INTO tesoreria_operaciones
                (empresa_id, fecha, tipo_operacion, descripcion, importe, estado, estado_conciliacion, fingerprint, origen_modulo)
            VALUES
                (1, '2026-05-01', 'COBRANZA', ?, 100, 'CONFIRMADA', 'CONCILIADA', 'fp-duplicado', 'COBRANZAS')
            """,
            (descripcion,),
        )
    con.commit()

    resultado = diagnosticar_tesoreria(empresa_id=1, conexion=con)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["resumen"]["operaciones_duplicadas_potenciales"] == 2
    assert "TESORERIA_OPERACION_DUPLICADA_POTENCIAL" in codigos
    assert resultado["operaciones"]["duplicadas_potenciales"][0]["cantidad"] == 2


def test_diagnostico_separa_empresas():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, activo)
        VALUES
            (1, 'CAJA', 'Caja empresa 1', '', 1),
            (2, 'BANCO', 'Banco empresa 2', '', 1)
        """
    )
    con.commit()

    resultado = diagnosticar_tesoreria(empresa_id=2, conexion=con)

    assert resultado["empresa_id"] == 2
    assert resultado["resumen"]["cuentas_tesoreria"] == 1
    assert resultado["cuentas_tesoreria"][0]["nombre"] == "Banco empresa 2"

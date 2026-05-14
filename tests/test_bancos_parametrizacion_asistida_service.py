import sqlite3

from services.bancos_parametrizacion_asistida_service import (
    generar_parametrizacion_asistida_bancos,
    parametrizar_banco_caja_asistido,
)


def _crear_conexion_base():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT,
            imputable INTEGER,
            estado TEXT,
            uso_operativo_sistema TEXT,
            cuenta_maestro_id INTEGER,
            es_cuenta_modelo INTEGER,
            es_cuenta_especifica_empresa INTEGER
        );

        CREATE TABLE bancos_cuentas (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            banco TEXT,
            nombre_cuenta TEXT,
            cuenta_contable_codigo TEXT,
            cuenta_contable_nombre TEXT
        );

        CREATE TABLE bancos_movimientos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            banco TEXT,
            nombre_cuenta TEXT,
            fecha TEXT,
            referencia TEXT,
            causal TEXT,
            concepto TEXT,
            importe REAL,
            debito REAL,
            credito REAL,
            importe_conciliado REAL,
            importe_pendiente REAL,
            tipo_movimiento_sugerido TEXT,
            cuenta_debe_codigo TEXT,
            cuenta_debe_nombre TEXT,
            cuenta_haber_codigo TEXT,
            cuenta_haber_nombre TEXT,
            tratamiento_fiscal TEXT,
            estado_conciliacion TEXT,
            estado_contable TEXT,
            clave_movimiento TEXT
        );

        CREATE TABLE bancos_reglas_clasificacion (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            patron TEXT,
            tipo_movimiento TEXT,
            cuenta_debe_codigo TEXT,
            cuenta_debe_nombre TEXT,
            cuenta_haber_codigo TEXT,
            cuenta_haber_nombre TEXT,
            tratamiento_fiscal TEXT,
            alicuota_iva REAL,
            automatizar_asiento INTEGER
        );

        CREATE TABLE bancos_grupos_fiscales (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
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
        """
    )
    return con


def _insertar_plan_minimo(con):
    cuentas = [
        ("1.1.02.001", "Banco Macro Cta Cte", "BANCO_CUENTA_CORRIENTE"),
        ("1.1.01.001", "Caja principal", "CAJA"),
        ("1.3.01", "IVA crédito fiscal", "IVA_CREDITO_FISCAL"),
        ("1.3.02", "Percepciones IVA", "PERCEPCION_IVA"),
        ("1.3.03", "Percepciones IIBB", "PERCEPCION_IIBB"),
        ("2.1.01", "Proveedores", "PROVEEDORES"),
        ("1.2.01", "Clientes deudores", "DEUDORES_POR_VENTAS"),
        ("6.1.06", "Gastos y comisiones bancarias", "GASTOS_BANCARIOS"),
        ("2.2.01", "IVA saldo a pagar", "IVA_SALDO_A_PAGAR"),
        ("1.6.02", "Cuenta particular socios", "CUENTA_PARTICULAR_SOCIOS"),
    ]
    for i, (codigo, nombre, uso) in enumerate(cuentas, start=1):
        con.execute(
            """
            INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema, cuenta_maestro_id, es_cuenta_modelo, es_cuenta_especifica_empresa)
            VALUES (1, ?, ?, 1, 'ACTIVA', ?, ?, 0, 1)
            """,
            (codigo, nombre, uso, i),
        )
    con.commit()


def test_parametrizacion_es_solo_lectura_y_devuelve_estado():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)

    resultado = generar_parametrizacion_asistida_bancos(conexion=con)

    assert resultado["solo_lectura"] is True
    assert resultado["plan_cuentas"]["cuentas_leidas"] >= 1
    assert resultado["estado"] in {"OK", "REQUIERE_PARAMETRIZACION", "CRITICO"}


def test_sugiere_vinculacion_de_cuenta_bancaria_sin_cuenta_contable():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)
    con.execute(
        "INSERT INTO bancos_cuentas (empresa_id, banco, nombre_cuenta, cuenta_contable_codigo, cuenta_contable_nombre) VALUES (1, 'Banco Macro', 'Cuenta corriente principal', '', '')"
    )
    con.commit()

    resultado = generar_parametrizacion_asistida_bancos(conexion=con)
    sugerencia = resultado["cuentas_bancarias"][0]

    assert sugerencia["accion_sugerida"] == "SUGERIR_VINCULACION"
    assert sugerencia["cuenta_sugerida"]["codigo"] == "1.1.02.001"
    assert sugerencia["confianza"] == "ALTA"


def test_mantiene_cuenta_bancaria_ya_vinculada_a_mejor_sugerencia():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)
    con.execute(
        "INSERT INTO bancos_cuentas (empresa_id, banco, nombre_cuenta, cuenta_contable_codigo, cuenta_contable_nombre) VALUES (1, 'Banco Macro', 'Cuenta corriente principal', '1.1.02.001', 'Banco Macro Cta Cte')"
    )
    con.commit()

    resultado = parametrizar_banco_caja_asistido(conexion=con)
    sugerencia = resultado["cuentas_bancarias"][0]

    assert sugerencia["accion_sugerida"] == "MANTENER"
    assert sugerencia["confianza"] == "ALTA"


def test_sugiere_tipo_movimiento_gasto_bancario_gravado():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)
    con.execute(
        """
        INSERT INTO bancos_movimientos
        (empresa_id, banco, nombre_cuenta, fecha, concepto, importe, debito, credito, importe_pendiente, tipo_movimiento_sugerido, estado_conciliacion)
        VALUES (1, 'Macro', 'Principal', '2026-05-01', 'Comisión bancaria', -121, 121, 0, 121, 'GASTO_BANCARIO_GRAVADO', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = generar_parametrizacion_asistida_bancos(conexion=con)
    tipo = resultado["tipos_movimiento"][0]

    assert tipo["tipo_movimiento"] == "GASTO_BANCARIO_GRAVADO"
    assert tipo["debe_sugerido"]["codigo"] == "6.1.06"
    assert tipo["haber_sugerido"]["codigo"] == "1.1.02.001"
    assert tipo["confianza"] == "ALTA"


def test_sugiere_iva_credito_fiscal_bancario():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)
    con.execute(
        """
        INSERT INTO bancos_movimientos
        (empresa_id, banco, nombre_cuenta, fecha, concepto, importe, debito, credito, importe_pendiente, tipo_movimiento_sugerido, estado_conciliacion)
        VALUES (1, 'Macro', 'Principal', '2026-05-01', 'IVA básico comisión', -21, 21, 0, 21, 'IVA_CREDITO_FISCAL_BANCARIO', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = generar_parametrizacion_asistida_bancos(conexion=con)
    tipo = resultado["tipos_movimiento"][0]
    mov = resultado["movimientos_muestra"][0]

    assert tipo["requiere_iva"] is True
    assert tipo["debe_sugerido"]["codigo"] == "1.3.01"
    assert mov["tratamiento_fiscal_sugerido"] == "IVA_CREDITO_FISCAL"


def test_tipo_desconocido_queda_para_revision_manual():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)
    con.execute(
        """
        INSERT INTO bancos_movimientos
        (empresa_id, banco, nombre_cuenta, fecha, concepto, importe, debito, credito, importe_pendiente, tipo_movimiento_sugerido, estado_conciliacion)
        VALUES (1, 'Macro', 'Principal', '2026-05-01', 'Movimiento raro', -50, 50, 0, 50, 'TIPO_NUEVO', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = generar_parametrizacion_asistida_bancos(conexion=con)
    tipo = resultado["tipos_movimiento"][0]

    assert tipo["accion_sugerida"] == "CLASIFICAR_MANUALMENTE"
    assert resultado["estado"] == "REQUIERE_PARAMETRIZACION"


def test_detecta_grupo_fiscal_pendiente_para_decision_iva():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)
    con.execute(
        """
        INSERT INTO bancos_grupos_fiscales
        (empresa_id, fecha, banco, nombre_cuenta, iva_credito_21, percepcion_iva, total_banco, estado_revision)
        VALUES (1, '2026-05-01', 'Macro', 'Principal', 21, 5, 126, 'PENDIENTE')
        """
    )
    con.commit()

    resultado = generar_parametrizacion_asistida_bancos(conexion=con)

    assert resultado["resumen"]["grupos_fiscales_pendientes"] == 1
    assert resultado["fiscal"]["grupos_pendientes"][0]["accion_sugerida"] == "DECIDIR_EN_CONTROL_FISCAL_BANCARIO"


def test_respeta_limite_de_muestra_movimientos():
    con = _crear_conexion_base()
    _insertar_plan_minimo(con)
    for i in range(5):
        con.execute(
            """
            INSERT INTO bancos_movimientos
            (empresa_id, banco, nombre_cuenta, fecha, concepto, importe, debito, credito, importe_pendiente, tipo_movimiento_sugerido, estado_conciliacion)
            VALUES (1, 'Macro', 'Principal', '2026-05-01', ?, -10, 10, 0, 10, 'GASTO_BANCARIO_GRAVADO', 'PENDIENTE')
            """,
            (f"Comisión {i}",),
        )
    con.commit()

    resultado = generar_parametrizacion_asistida_bancos(conexion=con, limite_movimientos=2)

    assert resultado["resumen"]["movimientos_analizados"] == 2
    assert len(resultado["movimientos_muestra"]) == 2

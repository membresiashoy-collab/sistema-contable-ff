import sqlite3

from services.tesoreria_parametrizacion_asistida_service import analizar_parametrizacion_tesoreria


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
            uso_operativo_sistema TEXT,
            banco_nombre TEXT,
            numero_cuenta TEXT
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

    con.commit()
    return con


def _insertar_plan_basico(cur):
    cur.execute(
        """
        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema, banco_nombre, numero_cuenta)
        VALUES
            (1, '1.1.01.01', 'Caja principal', 'ACTIVA', 1, 'CAJA_GENERAL', '', ''),
            (1, '1.1.02.01', 'Banco Macro Cta. Cte.', 'ACTIVA', 1, 'BANCO_CUENTA_CORRIENTE', 'Macro', '123'),
            (1, '1.1.03.01', 'Mercado Pago billetera virtual', 'ACTIVA', 1, 'BILLETERA_VIRTUAL', '', ''),
            (1, '1.1.04.01', 'Tarjetas a cobrar', 'ACTIVA', 1, 'TARJETA_COBROS', '', ''),
            (1, '1.1.05.01', 'Cheques y valores a depositar', 'ACTIVA', 1, 'VALORES_A_DEPOSITAR', '', ''),
            (1, '2.1.01', 'Proveedores', 'ACTIVA', 1, 'PROVEEDORES', '', ''),
            (1, '1.1', 'Caja y bancos agrupadora', 'ACTIVA', 0, 'BANCO', '', '')
        """
    )


def test_parametrizacion_es_solo_lectura_y_sugiere_cuenta_banco_con_confianza_alta():
    con = _crear_conexion_base()
    cur = con.cursor()
    _insertar_plan_basico(cur)
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, entidad, numero_cuenta, moneda, cuenta_contable_codigo, activo)
        VALUES
            (1, 'BANCO', 'Banco principal Macro', 'Macro', '123', 'ARS', '', 1)
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
    con.commit()

    antes = {
        tabla: cur.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in ("plan_cuentas_empresa", "tesoreria_cuentas", "tesoreria_medios_pago")
    }

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con)

    despues = {
        tabla: cur.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in antes
    }

    assert resultado["solo_lectura"] is True
    assert antes == despues
    assert resultado["resumen"]["cuentas_sin_vinculo"] == 1
    assert resultado["resumen"]["cuentas_con_sugerencia_alta"] == 1
    assert resultado["cuentas"][0]["sugerencia"]["codigo"] == "1.1.02.01"
    assert resultado["cuentas"][0]["sugerencia"]["confianza"] == "ALTA"


def test_parametrizacion_no_sugiere_proveedores_para_cuenta_banco():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema)
        VALUES
            (1, '2.1.01', 'Proveedores a pagar', 'ACTIVA', 1, 'PROVEEDORES')
        """
    )
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, activo)
        VALUES
            (1, 'BANCO', 'Banco principal', '', 1)
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con)

    assert resultado["resumen"]["cuentas_sin_sugerencia"] == 1
    assert resultado["cuentas"][0]["sugerencia"]["confianza"] == "NULA"
    assert resultado["cuentas"][0]["sugerencia"]["codigo"] == ""


def test_parametrizacion_detecta_vinculo_existente_ok():
    con = _crear_conexion_base()
    cur = con.cursor()
    _insertar_plan_basico(cur)
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
            (1, 'CAJA', 'Caja principal', '1.1.01.01', 'Caja principal', 1)
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con)

    assert resultado["resumen"]["cuentas_ya_vinculadas"] == 1
    assert resultado["cuentas"][0]["diagnostico"] == "VINCULADA_OK"
    assert resultado["cuentas"][0]["requiere_revision"] is False


def test_parametrizacion_detecta_vinculo_a_cuenta_no_imputable():
    con = _crear_conexion_base()
    cur = con.cursor()
    _insertar_plan_basico(cur)
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
            (1, 'BANCO', 'Banco principal', '1.1', 'Caja y bancos agrupadora', 1)
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con, incluir_inactivas=True)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["resumen"]["cuentas_vinculadas_requieren_revision"] == 1
    assert resultado["cuentas"][0]["diagnostico"] == "VINCULO_REVISAR"
    assert "TESORERIA_PARAM_VINCULO_NO_IMPUTABLE" in codigos


def test_parametrizacion_sugiere_tipos_de_medios_pago_y_detecta_revision():
    con = _crear_conexion_base()
    cur = con.cursor()
    _insertar_plan_basico(cur)
    cur.execute(
        """
        INSERT INTO tesoreria_medios_pago
            (empresa_id, codigo, nombre, tipo_cuenta, activo)
        VALUES
            (1, 'EFECTIVO', 'Efectivo', 'BANCO', 1),
            (1, 'ECHEQ', 'E-Cheq', 'VALORES', 1),
            (1, 'BILLETERA', 'Billetera virtual', 'BILLETERA', 1)
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con)
    medios = {medio["codigo"]: medio for medio in resultado["medios_pago"]}

    assert medios["EFECTIVO"]["tipo_cuenta_sugerido"] == "CAJA"
    assert medios["EFECTIVO"]["requiere_revision"] is True
    assert medios["ECHEQ"]["diagnostico"] == "OK"
    assert resultado["resumen"]["medios_pago_requieren_revision"] == 1


def test_parametrizacion_detecta_tablas_faltantes_sin_inicializar():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert resultado["estado"] == "CRITICO"
    assert "TESORERIA_PARAM_TABLA_INEXISTENTE" in codigos
    assert resultado["solo_lectura"] is True


def test_parametrizacion_arma_matriz_por_tipo_cuenta():
    con = _crear_conexion_base()
    cur = con.cursor()
    _insertar_plan_basico(cur)
    cur.execute(
        """
        INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
        VALUES
            (1, 'CAJA', 'Caja principal', '1.1.01.01', 'Caja principal', 1),
            (1, 'BILLETERA', 'Mercado Pago', '', '', 1)
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con)

    assert resultado["matriz_por_tipo_cuenta"]["CAJA"]["vinculadas_ok"] == 1
    assert resultado["matriz_por_tipo_cuenta"]["BILLETERA"]["sin_vinculo"] == 1
    assert resultado["matriz_por_tipo_cuenta"]["BILLETERA"]["sugerencias_alta"] == 1


def test_parametrizacion_detecta_medio_pago_duplicado():
    con = _crear_conexion_base()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO tesoreria_medios_pago
            (empresa_id, codigo, nombre, tipo_cuenta, activo)
        VALUES
            (1, 'TRANSFERENCIA', 'Transferencia bancaria', 'BANCO', 1),
            (1, 'TRANSFERENCIA', 'Transferencia duplicada', 'BANCO', 1)
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_tesoreria(empresa_id=1, conexion=con)
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}

    assert "TESORERIA_PARAM_MEDIO_PAGO_DUPLICADO" in codigos

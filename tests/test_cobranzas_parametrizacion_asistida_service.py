import sqlite3

from services.cobranzas_parametrizacion_asistida_service import (
    PARAMETRIZACIONES_COBRANZAS,
    exportar_parametrizacion_cobranzas_como_texto,
    generar_parametrizacion_asistida_cobranzas,
    obtener_resumen_parametrizacion_cobranzas,
)


def crear_base_plan_parcial(tmp_path):
    db_path = tmp_path / "cobranzas_param_test.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE plan_cuentas_empresa (
                id INTEGER PRIMARY KEY,
                codigo TEXT,
                nombre TEXT,
                activa INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE mapeos_contables_empresa (
                id INTEGER PRIMARY KEY,
                uso_operativo TEXT,
                cuenta_id INTEGER
            )
            """
        )
        conn.executemany(
            "INSERT INTO plan_cuentas_empresa (codigo, nombre, activa) VALUES (?, ?, ?)",
            [
                ("1.1.01", "CAJA PRINCIPAL", 1),
                ("1.1.02", "BANCO MACRO CTA CTE", 1),
                ("1.1.03", "VALORES A DEPOSITAR", 1),
                ("1.2.01", "DEUDORES POR VENTAS", 1),
                ("2.1.10", "ANTICIPOS DE CLIENTES", 1),
                ("1.3.04", "RETENCIONES IVA SUFRIDAS", 1),
                ("1.3.05", "RETENCIONES IIBB SUFRIDAS", 1),
                ("1.3.06", "RETENCIONES GANANCIAS SUFRIDAS", 1),
                ("5.1.99", "DIFERENCIAS DE COBRO", 1),
            ],
        )
        conn.commit()

    return db_path


def crear_base_plan_completo(tmp_path):
    db_path = tmp_path / "cobranzas_param_completo.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE plan_cuentas_empresa (
                id INTEGER PRIMARY KEY,
                codigo TEXT,
                nombre TEXT,
                activa INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE mapeos_contables_empresa (
                id INTEGER PRIMARY KEY,
                uso_operativo TEXT,
                cuenta_id INTEGER
            )
            """
        )
        conn.executemany(
            "INSERT INTO plan_cuentas_empresa (codigo, nombre, activa) VALUES (?, ?, ?)",
            [
                ("1.1.01", "CAJA PRINCIPAL", 1),
                ("1.1.02", "BANCO MACRO CTA CTE", 1),
                ("1.1.03", "VALORES A DEPOSITAR", 1),
                ("1.1.04", "TARJETAS A COBRAR", 1),
                ("1.2.01", "DEUDORES POR VENTAS", 1),
                ("2.1.10", "ANTICIPOS DE CLIENTES", 1),
                ("2.1.11", "SALDOS A FAVOR DE CLIENTES", 1),
                ("1.3.04", "RETENCIONES IVA SUFRIDAS", 1),
                ("1.3.05", "RETENCIONES IIBB SUFRIDAS", 1),
                ("1.3.06", "RETENCIONES GANANCIAS SUFRIDAS", 1),
                ("5.1.99", "DIFERENCIAS DE COBRO", 1),
                ("1.2.99", "CUENTA PUENTE COBRANZAS", 1),
                ("5.2.10", "GASTOS BANCARIOS", 1),
            ],
        )
        conn.commit()

    return db_path


def test_parametrizacion_v2a_genera_matriz_cobranzas(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)

    codigos = {item["codigo"] for item in matriz["parametrizaciones"]}

    assert len(PARAMETRIZACIONES_COBRANZAS) == 10
    assert "COBRANZA_FACTURA_TOTAL" in codigos
    assert "COBRANZA_FACTURA_PARCIAL" in codigos
    assert "ANTICIPO_CLIENTE" in codigos
    assert "SALDO_A_FAVOR_CLIENTE" in codigos
    assert "RETENCION_IVA_SUFRIDA" in codigos
    assert "RETENCION_IIBB_SUFRIDA" in codigos
    assert "RETENCION_GANANCIAS_SUFRIDA" in codigos
    assert "DIFERENCIA_COBRO" in codigos
    assert "COBRO_NO_IDENTIFICADO" in codigos
    assert "ANULACION_COBRANZA" in codigos


def test_parametrizacion_detecta_sugeridos_e_incompletos(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)
    por_codigo = {item["codigo"]: item for item in matriz["parametrizaciones"]}

    assert matriz["estado"] == "REQUIERE_PARAMETRIZACION"

    assert por_codigo["COBRANZA_FACTURA_TOTAL"]["estado"] == "SUGERIDO"
    assert por_codigo["COBRANZA_FACTURA_PARCIAL"]["estado"] == "SUGERIDO"
    assert por_codigo["ANTICIPO_CLIENTE"]["estado"] == "SUGERIDO"
    assert por_codigo["RETENCION_IVA_SUFRIDA"]["estado"] == "SUGERIDO"
    assert por_codigo["RETENCION_IIBB_SUFRIDA"]["estado"] == "SUGERIDO"
    assert por_codigo["RETENCION_GANANCIAS_SUFRIDA"]["estado"] == "SUGERIDO"

    assert por_codigo["SALDO_A_FAVOR_CLIENTE"]["estado"] == "INCOMPLETO"
    assert "saldos_a_favor_clientes" in por_codigo["SALDO_A_FAVOR_CLIENTE"]["faltantes_obligatorios"]


def test_parametrizacion_plan_completo_queda_sin_incompletos(tmp_path):
    db_path = crear_base_plan_completo(tmp_path)

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)
    resumen = obtener_resumen_parametrizacion_cobranzas(matriz)

    assert matriz["estado"] in {"OK_PARAMETRIZACION_ASISTIDA", "REQUIERE_REVISION"}
    assert resumen["parametrizaciones_incompletas"] == 0

    por_codigo = {item["codigo"]: item for item in matriz["parametrizaciones"]}
    assert por_codigo["SALDO_A_FAVOR_CLIENTE"]["estado"] == "SUGERIDO"
    assert por_codigo["COBRO_NO_IDENTIFICADO"]["estado"] == "SUGERIDO"
    assert por_codigo["DIFERENCIA_COBRO"]["estado"] == "SUGERIDO"


def test_parametrizacion_detecta_alternativas_de_medio_de_cobro(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)
    cobro_total = next(item for item in matriz["parametrizaciones"] if item["codigo"] == "COBRANZA_FACTURA_TOTAL")
    grupo = next(alt for alt in cobro_total["alternativas"] if alt["rol"] == "medio_cobro")

    assert grupo["detectado"] is True

    opciones_detectadas = [op["uso"] for op in grupo["opciones"] if op["detectado"]]
    assert "caja_efectivo" in opciones_detectadas
    assert "bancos" in opciones_detectadas
    assert "valores_a_depositar" in opciones_detectadas


def test_parametrizacion_prioriza_plan_empresa_y_confianza_alta(tmp_path):
    db_path = tmp_path / "prioridad.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE plan_cuentas_empresa (
                id INTEGER PRIMARY KEY,
                codigo TEXT,
                nombre TEXT,
                activa INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE plan_cuentas_maestro (
                id INTEGER PRIMARY KEY,
                codigo TEXT,
                nombre TEXT,
                activa INTEGER
            )
            """
        )
        conn.execute("CREATE TABLE mapeos_contables_empresa (id INTEGER PRIMARY KEY, uso_operativo TEXT)")
        conn.execute(
            "INSERT INTO plan_cuentas_empresa (codigo, nombre, activa) VALUES (?, ?, ?)",
            ("1.2.01", "DEUDORES POR VENTAS", 1),
        )
        conn.execute(
            "INSERT INTO plan_cuentas_maestro (codigo, nombre, activa) VALUES (?, ?, ?)",
            ("1.2.99", "DEUDORES POR VENTAS", 1),
        )
        conn.execute(
            "INSERT INTO plan_cuentas_empresa (codigo, nombre, activa) VALUES (?, ?, ?)",
            ("1.1.01", "CAJA PRINCIPAL", 1),
        )
        conn.commit()

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)
    cobro_total = next(item for item in matriz["parametrizaciones"] if item["codigo"] == "COBRANZA_FACTURA_TOTAL")
    cliente = next(comp for comp in cobro_total["componentes"] if comp["uso"] == "deudores_por_ventas")

    assert cliente["detectado"] is True
    assert cliente["confianza"] == "ALTA"
    assert cliente["sugerencias"][0]["fuente"] == "Plan Empresa"


def test_parametrizacion_es_solo_lectura_no_crea_mapeos(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    with sqlite3.connect(db_path) as conn:
        tablas_antes = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        mapeos_antes = conn.execute("SELECT COUNT(*) FROM mapeos_contables_empresa").fetchone()[0]

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        tablas_despues = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        mapeos_despues = conn.execute("SELECT COUNT(*) FROM mapeos_contables_empresa").fetchone()[0]

    assert matriz["solo_lectura"] is True
    assert tablas_despues == tablas_antes
    assert mapeos_despues == mapeos_antes == 0


def test_exportacion_texto_y_resumen_funcionan(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)
    resumen = obtener_resumen_parametrizacion_cobranzas(matriz)
    texto = exportar_parametrizacion_cobranzas_como_texto(matriz)

    assert resumen["estado"] == "REQUIERE_PARAMETRIZACION"
    assert resumen["parametrizaciones_total"] == 10
    assert resumen["parametrizaciones_incompletas"] > 0

    assert "Cobranzas PRO v2A" in texto
    assert "COBRANZA_FACTURA_TOTAL" in texto
    assert "COBRANZAS_PARAM_INCOMPLETAS" in texto


def test_base_inexistente_devuelve_sin_base(tmp_path):
    db_path = tmp_path / "no_existe.db"

    matriz = generar_parametrizacion_asistida_cobranzas(db_path=db_path)
    resumen = obtener_resumen_parametrizacion_cobranzas(matriz)

    assert matriz["estado"] == "SIN_BASE"
    assert resumen["hallazgos_criticos"] == 1
    assert matriz["hallazgos"][0]["codigo"] == "COBRANZAS_PARAM_DB_NO_ENCONTRADA"

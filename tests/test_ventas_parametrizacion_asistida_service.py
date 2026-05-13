import sqlite3

from services.ventas_parametrizacion_asistida_service import (
    TIPOS_VENTA_PARAMETRIZABLES,
    exportar_parametrizacion_ventas_como_texto,
    generar_parametrizacion_asistida_ventas,
    obtener_resumen_parametrizacion_ventas,
)


def crear_base_plan_parcial(tmp_path):
    db_path = tmp_path / "ventas_param_test.db"

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
                ("1.2.01", "DEUDORES POR VENTAS", 1),
                ("4.1.01", "VENTAS DE MERCADERIAS", 1),
                ("4.1.02", "VENTAS DE SERVICIOS", 1),
                ("2.1.01", "IVA DEBITO FISCAL", 1),
                ("2.1.10", "ANTICIPOS DE CLIENTES", 1),
                ("4.1.09", "DEVOLUCIONES SOBRE VENTAS", 1),
                ("4.1.10", "INTERESES POR FINANCIACION DE VENTAS", 1),
            ],
        )
        conn.commit()

    return db_path


def crear_base_plan_completo(tmp_path):
    db_path = tmp_path / "ventas_param_completo.db"

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
                ("1.2.01", "DEUDORES POR VENTAS", 1),
                ("1.2.02", "CLIENTES DEL EXTERIOR", 1),
                ("4.1.01", "VENTAS DE MERCADERIAS", 1),
                ("4.1.02", "VENTAS DE SERVICIOS", 1),
                ("4.1.03", "VENTAS EXENTAS", 1),
                ("4.1.04", "VENTAS NO GRAVADAS", 1),
                ("4.1.05", "EXPORTACION DE BIENES", 1),
                ("4.1.06", "EXPORTACION DE SERVICIOS", 1),
                ("2.1.01", "IVA DEBITO FISCAL", 1),
                ("2.1.10", "ANTICIPOS DE CLIENTES", 1),
                ("2.1.11", "SALDOS A FAVOR DE CLIENTES", 1),
                ("5.1.20", "RESULTADO POR VENTA DE BIENES DE USO", 1),
                ("4.1.09", "DEVOLUCIONES SOBRE VENTAS", 1),
                ("4.1.10", "INTERESES POR FINANCIACION DE VENTAS", 1),
            ],
        )
        conn.commit()

    return db_path


def test_parametrizacion_v2a_genera_matriz_de_tipos_de_venta(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    matriz = generar_parametrizacion_asistida_ventas(db_path=db_path)

    codigos = {tipo["codigo"] for tipo in matriz["tipos_venta"]}

    assert len(TIPOS_VENTA_PARAMETRIZABLES) == 10
    assert "VENTA_MERCADERIAS" in codigos
    assert "VENTA_SERVICIOS" in codigos
    assert "VENTA_BIEN_USO" in codigos
    assert "VENTA_EXENTA" in codigos
    assert "VENTA_NO_GRAVADA" in codigos
    assert "EXPORTACION_BIENES" in codigos
    assert "EXPORTACION_SERVICIOS" in codigos
    assert "NOTA_CREDITO" in codigos
    assert "NOTA_DEBITO" in codigos
    assert "ANTICIPO_CLIENTE" in codigos


def test_parametrizacion_detecta_sugeridos_e_incompletos(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    matriz = generar_parametrizacion_asistida_ventas(db_path=db_path)
    por_codigo = {tipo["codigo"]: tipo for tipo in matriz["tipos_venta"]}

    assert matriz["estado"] == "REQUIERE_PARAMETRIZACION"

    assert por_codigo["VENTA_MERCADERIAS"]["estado"] == "SUGERIDO"
    assert por_codigo["VENTA_SERVICIOS"]["estado"] == "SUGERIDO"
    assert por_codigo["ANTICIPO_CLIENTE"]["estado"] == "SUGERIDO"

    assert por_codigo["VENTA_EXENTA"]["estado"] == "INCOMPLETO"
    assert "ventas_exentas" in por_codigo["VENTA_EXENTA"]["faltantes_obligatorios"]

    assert por_codigo["EXPORTACION_SERVICIOS"]["estado"] == "INCOMPLETO"
    assert "deudores_exterior" in por_codigo["EXPORTACION_SERVICIOS"]["faltantes_obligatorios"]
    assert "exportacion_servicios" in por_codigo["EXPORTACION_SERVICIOS"]["faltantes_obligatorios"]


def test_parametrizacion_plan_completo_queda_sin_incompletos(tmp_path):
    db_path = crear_base_plan_completo(tmp_path)

    matriz = generar_parametrizacion_asistida_ventas(db_path=db_path)
    resumen = obtener_resumen_parametrizacion_ventas(matriz)

    assert matriz["estado"] in {"OK_PARAMETRIZACION_ASISTIDA", "REQUIERE_REVISION"}
    assert resumen["tipos_incompletos"] == 0

    por_codigo = {tipo["codigo"]: tipo for tipo in matriz["tipos_venta"]}
    assert por_codigo["EXPORTACION_BIENES"]["estado"] == "SUGERIDO"
    assert por_codigo["VENTA_NO_GRAVADA"]["estado"] == "SUGERIDO"
    assert por_codigo["VENTA_BIEN_USO"]["estado"] == "SUGERIDO"


def test_parametrizacion_prioriza_plan_empresa_y_confianza_alta(tmp_path):
    db_path = crear_base_plan_completo(tmp_path)

    matriz = generar_parametrizacion_asistida_ventas(db_path=db_path)
    venta_servicios = next(tipo for tipo in matriz["tipos_venta"] if tipo["codigo"] == "VENTA_SERVICIOS")
    ingreso = next(comp for comp in venta_servicios["componentes"] if comp["uso"] == "ventas_servicios")

    assert ingreso["detectado"] is True
    assert ingreso["confianza"] == "ALTA"
    assert ingreso["sugerencias"][0]["fuente"] == "Plan Empresa"
    assert "VENTAS DE SERVICIOS" in ingreso["sugerencias"][0]["nombre"]


def test_parametrizacion_es_solo_lectura_no_crea_mapeos(tmp_path):
    db_path = crear_base_plan_parcial(tmp_path)

    with sqlite3.connect(db_path) as conn:
        tablas_antes = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        mapeos_antes = conn.execute("SELECT COUNT(*) FROM mapeos_contables_empresa").fetchone()[0]

    matriz = generar_parametrizacion_asistida_ventas(db_path=db_path)

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

    matriz = generar_parametrizacion_asistida_ventas(db_path=db_path)
    resumen = obtener_resumen_parametrizacion_ventas(matriz)
    texto = exportar_parametrizacion_ventas_como_texto(matriz)

    assert resumen["estado"] == "REQUIERE_PARAMETRIZACION"
    assert resumen["tipos_venta_total"] == 10
    assert resumen["tipos_incompletos"] > 0

    assert "Ventas PRO v2A" in texto
    assert "VENTA_MERCADERIAS" in texto
    assert "VENTAS_PARAM_TIPOS_INCOMPLETOS" in texto


def test_base_inexistente_devuelve_sin_base(tmp_path):
    db_path = tmp_path / "no_existe.db"

    matriz = generar_parametrizacion_asistida_ventas(db_path=db_path)
    resumen = obtener_resumen_parametrizacion_ventas(matriz)

    assert matriz["estado"] == "SIN_BASE"
    assert resumen["hallazgos_criticos"] == 1
    assert matriz["hallazgos"][0]["codigo"] == "VENTAS_PARAM_DB_NO_ENCONTRADA"

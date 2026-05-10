from pathlib import Path
import sqlite3

from services.plan_cuentas_maestro_service import (
    aplicar_migracion_021,
    listar_eventos_operativos,
    listar_mapeos_empresa,
    listar_plan_empresa,
    listar_usos_operativos,
    migrar_configuracion_contable_actual,
    migrar_plan_actual_a_plan_empresa,
    sanear_mapeos_contables_migrados,
    uso_operativo_desde_comportamiento,
    validar_estructura_maestro,
)


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _crear_plan_actual_minimo(conn):
    conn.executescript(
        """
        CREATE TABLE plan_cuentas (
            codigo TEXT,
            nombre TEXT,
            empresa_id INTEGER DEFAULT 1,
            comportamiento_contable TEXT,
            requiere_auxiliar INTEGER NOT NULL DEFAULT 0,
            permite_imputacion_operativa INTEGER NOT NULL DEFAULT 1,
            modulo_origen_preferido TEXT
        );

        CREATE TABLE plan_cuentas_detallado (
            cuenta TEXT PRIMARY KEY,
            detalle TEXT,
            imputable TEXT,
            ajustable TEXT,
            tipo TEXT,
            madre TEXT,
            nivel INTEGER,
            orden INTEGER,
            empresa_id INTEGER DEFAULT 1
        );

        CREATE TABLE categorias_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            tipo_categoria TEXT,
            activo INTEGER DEFAULT 1,
            empresa_id INTEGER DEFAULT 1
        );

        CREATE TABLE conceptos_fiscales_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concepto TEXT UNIQUE,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            tratamiento TEXT,
            activo INTEGER DEFAULT 1,
            empresa_id INTEGER DEFAULT 1
        );
        """
    )

    cuentas = [
        ("1", "ACTIVO", 1, None, 0, 0, None, "N", "N", "A", "", 1, 10),
        ("1.1", "CAJA Y BANCOS", 1, None, 0, 0, None, "N", "N", "A", "1", 2, 20),
        ("1.1.01", "CAJA", 1, "CAJA", 0, 1, "CAJA", "S", "N", "A", "1.1", 3, 30),
        ("1.1.02", "BANCO CUENTA CORRIENTE", 1, "BANCO", 0, 1, "BANCO", "S", "N", "A", "1.1", 3, 40),
        ("1.1.03", "MERCADO PAGO / BILLETERAS VIRTUALES", 1, "BANCO", 0, 1, "BANCO", "S", "N", "A", "1.1", 3, 45),
        ("1.2.01", "DEUDORES POR VENTAS", 1, "CLIENTES", 0, 1, "VENTAS", "S", "N", "A", "1.2", 3, 70),
        ("1.3.01", "IVA CREDITO FISCAL", 1, "IVA_CREDITO", 0, 1, "IVA", "S", "N", "A", "1.3", 3, 90),
        ("1.6.01", "ANTICIPOS A PROVEEDORES", 1, "PROVEEDORES", 0, 1, "COMPRAS", "S", "N", "A", "1.6", 3, 120),
        ("2.1.01", "PROVEEDORES", 1, "PROVEEDORES", 0, 1, "COMPRAS", "S", "N", "P", "2.1", 3, 320),
        ("2.1.02", "ANTICIPOS DE CLIENTES", 1, "CLIENTES", 0, 1, "VENTAS", "S", "N", "P", "2.1", 3, 330),
        ("2.2.01", "IVA DEBITO FISCAL", 1, "IVA_DEBITO", 0, 1, "IVA", "S", "N", "P", "2.2", 3, 340),
        ("2.2.02", "IVA A PAGAR", 1, "IVA_DEBITO", 0, 1, "IVA", "S", "N", "P", "2.2", 3, 350),
        ("6.1.15", "IMPUESTOS, TASAS Y CONTRIBUCIONES", 1, "CARGAS_SOCIALES_GASTO", 0, 1, "COMPRAS", "S", "N", "R", "6.1", 3, 850),
        ("6.1.18", "CARGAS SOCIALES", 1, "CARGAS_SOCIALES_GASTO", 0, 1, "SUELDOS", "S", "N", "R", "6.1", 3, 880),
        ("3.1.01", "CAPITAL SOCIAL", 1, "CAPITAL_SOCIAL", 0, 1, "CONTABILIDAD", "S", "N", "PN", "3.1", 3, 500),
        ("6.1.01", "COMPRAS / MERCADERIAS", 1, None, 0, 1, "COMPRAS", "S", "N", "R", "6.1", 3, 900),
    ]

    for codigo, nombre, empresa_id, comp, req_aux, permite, modulo, imputable, ajustable, tipo, madre, nivel, orden in cuentas:
        conn.execute(
            """
            INSERT INTO plan_cuentas
            (codigo, nombre, empresa_id, comportamiento_contable,
             requiere_auxiliar, permite_imputacion_operativa, modulo_origen_preferido)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre, empresa_id, comp, req_aux, permite, modulo),
        )
        conn.execute(
            """
            INSERT INTO plan_cuentas_detallado
            (cuenta, detalle, imputable, ajustable, tipo, madre, nivel, orden, empresa_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre, imputable, ajustable, tipo, madre, nivel, orden, empresa_id),
        )

    conn.execute(
        """
        INSERT INTO categorias_compra
        (categoria, cuenta_codigo, cuenta_nombre, cuenta_proveedor_codigo,
         cuenta_proveedor_nombre, tipo_categoria, activo, empresa_id)
        VALUES
        ('MERCADERIAS', '6.1.01', 'COMPRAS / MERCADERIAS', '2.1.01', 'PROVEEDORES', 'BIENES', 1, 1),
        ('MERCADERIAS PARA REVENTA', '1.5.01', 'MERCADERIAS', '2.1.01', 'PROVEEDORES', 'BIENES_CAMBIO', 1, 1)
        """
    )

    conn.execute(
        """
        INSERT INTO conceptos_fiscales_compra
        (concepto, cuenta_codigo, cuenta_nombre, tratamiento, activo, empresa_id)
        VALUES
        ('IVA_CREDITO_FISCAL', '1.3.01', 'IVA CREDITO FISCAL', 'CREDITO_FISCAL', 1, 1),
        ('IVA_NO_COMPUTABLE', '6.1.20', 'IVA NO COMPUTABLE / MAYOR COSTO', 'MAYOR_COSTO_GASTO', 1, 1),
        ('PERCEPCION_IIBB', '1.3.03', 'PERCEPCIONES IIBB', 'PERCEPCION_COMPUTABLE', 1, 1)
        """
    )

    conn.commit()


def test_aplicar_migracion_021_crea_estructura_base():
    conn = _conn()

    resultado = aplicar_migracion_021(conn=conn)
    assert resultado["ok"] is True

    validacion = validar_estructura_maestro(conn=conn)
    assert validacion["ok"] is True
    assert validacion["tablas"]["usos_operativos_contables"]["filas"] >= 60
    assert validacion["tablas"]["eventos_operativos_contables"]["filas"] >= 10
    assert validacion["tablas"]["reglas_contables"]["filas"] >= 5


def test_mapear_comportamiento_viejo_a_uso_operativo_nuevo():
    conn = _conn()
    aplicar_migracion_021(conn=conn)

    assert uso_operativo_desde_comportamiento("CAJA", conn=conn) == "CAJA_GENERAL"
    assert uso_operativo_desde_comportamiento("BANCO", conn=conn) == "BANCO_CUENTA_CORRIENTE"
    assert uso_operativo_desde_comportamiento("IVA_CREDITO", conn=conn) == "IVA_CREDITO_FISCAL"
    assert uso_operativo_desde_comportamiento("PROVEEDORES", conn=conn) == "PROVEEDORES_CC"
    assert uso_operativo_desde_comportamiento("CAPITAL_SOCIAL", conn=conn) == "CAPITAL_SOCIAL"


def test_migrar_plan_actual_a_plan_empresa_sin_borrar_plan_viejo():
    conn = _conn()
    _crear_plan_actual_minimo(conn)
    aplicar_migracion_021(conn=conn)

    resultado = migrar_plan_actual_a_plan_empresa(
        empresa_id=1,
        usuario="pytest",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["cuentas_migradas"] >= 8

    plan_empresa = listar_plan_empresa(empresa_id=1, conn=conn)
    codigos = {item["codigo"] for item in plan_empresa}
    assert "1.1.01" in codigos
    assert "1.1.02" in codigos
    assert "1.3.01" in codigos
    assert "2.1.01" in codigos

    caja = next(item for item in plan_empresa if item["codigo"] == "1.1.01")
    banco = next(item for item in plan_empresa if item["codigo"] == "1.1.02")
    billetera = next(item for item in plan_empresa if item["codigo"] == "1.1.03")
    iva = next(item for item in plan_empresa if item["codigo"] == "1.3.01")
    anticipo_proveedor = next(item for item in plan_empresa if item["codigo"] == "1.6.01")
    anticipo_cliente = next(item for item in plan_empresa if item["codigo"] == "2.1.02")
    iva_pagar = next(item for item in plan_empresa if item["codigo"] == "2.2.02")
    impuestos = next(item for item in plan_empresa if item["codigo"] == "6.1.15")
    cargas = next(item for item in plan_empresa if item["codigo"] == "6.1.18")

    assert caja["uso_operativo_sistema"] == "CAJA_GENERAL"
    assert banco["uso_operativo_sistema"] == "BANCO_CUENTA_CORRIENTE"
    assert billetera["uso_operativo_sistema"] == "BILLETERA_VIRTUAL"
    assert iva["uso_operativo_sistema"] == "IVA_CREDITO_FISCAL"
    assert anticipo_proveedor["uso_operativo_sistema"] == "ANTICIPOS_PROVEEDORES"
    assert anticipo_cliente["uso_operativo_sistema"] == "ANTICIPOS_CLIENTES"
    assert iva_pagar["uso_operativo_sistema"] == "IVA_SALDO_A_PAGAR"
    assert impuestos["uso_operativo_sistema"] == "IMPUESTOS_TASAS_CONTRIBUCIONES"
    assert cargas["uso_operativo_sistema"] == "CARGAS_SOCIALES_GASTO"

    total_plan_viejo = conn.execute("SELECT COUNT(*) FROM plan_cuentas").fetchone()[0]
    assert total_plan_viejo >= 8


def test_migrar_configuracion_contable_actual_copia_categorias_y_conceptos():
    conn = _conn()
    _crear_plan_actual_minimo(conn)
    aplicar_migracion_021(conn=conn)

    resultado = migrar_configuracion_contable_actual(
        empresa_id=1,
        usuario="pytest",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["plan"]["cuentas_migradas"] >= 8
    assert resultado["categorias"]["migradas"] == 2
    assert resultado["conceptos_fiscales"]["migrados"] == 3

    categorias = conn.execute("SELECT COUNT(*) FROM categorias_compra_config").fetchone()[0]
    conceptos = conn.execute("SELECT COUNT(*) FROM conceptos_fiscales_compra_config").fetchone()[0]
    auditoria_config = conn.execute("SELECT COUNT(*) FROM auditoria_configuracion_contable").fetchone()[0]

    assert categorias == 2
    assert conceptos == 3
    assert auditoria_config >= 5

    mapeos = listar_mapeos_empresa(empresa_id=1, conn=conn)
    usos_mapeados = {item["uso_operativo_codigo"] for item in mapeos}
    assert "CAJA_GENERAL" in usos_mapeados
    assert "BANCO_CUENTA_CORRIENTE" in usos_mapeados
    assert "IVA_CREDITO_FISCAL" in usos_mapeados


def test_sanear_mapeos_corrige_etiquetas_viejas_demasiado_genericas():
    conn = _conn()
    _crear_plan_actual_minimo(conn)
    aplicar_migracion_021(conn=conn)

    resultado_plan = migrar_plan_actual_a_plan_empresa(
        empresa_id=1,
        usuario="pytest",
        conn=conn,
    )
    assert resultado_plan["ok"] is True

    # Simula contaminación histórica: una billetera quedó mapeada como banco.
    billetera = conn.execute(
        """
        SELECT id
        FROM plan_cuentas_empresa
        WHERE codigo = '1.1.03'
        LIMIT 1
        """
    ).fetchone()
    banco_uso = conn.execute(
        """
        SELECT id
        FROM usos_operativos_contables
        WHERE codigo = 'BANCO_CUENTA_CORRIENTE'
        LIMIT 1
        """
    ).fetchone()

    conn.execute(
        """
        UPDATE plan_cuentas_empresa
           SET uso_operativo_sistema = 'BANCO_CUENTA_CORRIENTE'
         WHERE id = ?
        """,
        (int(billetera["id"]),),
    )
    conn.execute(
        """
        INSERT INTO mapeos_contables_empresa
        (empresa_id, uso_operativo_id, cuenta_empresa_id, estado, motivo)
        VALUES (1, ?, ?, 'ACTIVO', 'mapeo errado simulado')
        """,
        (int(banco_uso["id"]), int(billetera["id"])),
    )
    conn.commit()

    saneamiento = sanear_mapeos_contables_migrados(
        empresa_id=1,
        usuario="pytest",
        conn=conn,
    )

    assert saneamiento["ok"] is True
    assert saneamiento["cuentas_corregidas"] >= 1
    assert saneamiento["mapeos_inactivados"] >= 1

    cuenta = conn.execute(
        """
        SELECT uso_operativo_sistema
        FROM plan_cuentas_empresa
        WHERE codigo = '1.1.03'
        LIMIT 1
        """
    ).fetchone()
    assert cuenta["uso_operativo_sistema"] == "BILLETERA_VIRTUAL"

    mapeos_activos = conn.execute(
        """
        SELECT u.codigo
        FROM mapeos_contables_empresa m
        JOIN usos_operativos_contables u ON u.id = m.uso_operativo_id
        WHERE m.cuenta_empresa_id = ?
          AND m.estado = 'ACTIVO'
        ORDER BY u.codigo
        """,
        (int(billetera["id"]),),
    ).fetchall()
    assert [row["codigo"] for row in mapeos_activos] == ["BILLETERA_VIRTUAL"]



def test_migracion_logica_es_idempotente_y_no_duplica_configuraciones():
    conn = _conn()
    _crear_plan_actual_minimo(conn)
    aplicar_migracion_021(conn=conn)

    primera = migrar_configuracion_contable_actual(
        empresa_id=1,
        usuario="pytest",
        conn=conn,
    )
    segunda = migrar_configuracion_contable_actual(
        empresa_id=1,
        usuario="pytest",
        conn=conn,
    )

    assert primera["ok"] is True
    assert segunda["ok"] is True

    categorias = conn.execute("SELECT COUNT(*) FROM categorias_compra_config").fetchone()[0]
    conceptos = conn.execute("SELECT COUNT(*) FROM conceptos_fiscales_compra_config").fetchone()[0]

    assert categorias == 2
    assert conceptos == 3
    assert segunda["categorias"]["migradas"] == 0
    assert segunda["categorias"]["actualizadas"] == 2
    assert segunda["conceptos_fiscales"]["migrados"] == 0
    assert segunda["conceptos_fiscales"]["actualizados"] == 3

    plan_empresa = conn.execute(
        "SELECT COUNT(*) FROM plan_cuentas_empresa WHERE empresa_id = 1"
    ).fetchone()[0]
    assert plan_empresa >= 9

    mapeos = listar_mapeos_empresa(empresa_id=1, conn=conn)
    usos_mapeados = {item["uso_operativo_codigo"] for item in mapeos}
    assert "CAPITAL_SOCIAL" in usos_mapeados
    assert "BILLETERA_VIRTUAL" in usos_mapeados
    assert "ANTICIPOS_CLIENTES" in usos_mapeados
    assert "ANTICIPOS_PROVEEDORES" in usos_mapeados
    assert "IVA_SALDO_A_PAGAR" in usos_mapeados
    assert "IMPUESTOS_TASAS_CONTRIBUCIONES" in usos_mapeados



def test_listados_base_tienen_usos_y_eventos():
    conn = _conn()
    aplicar_migracion_021(conn=conn)

    usos = listar_usos_operativos(conn=conn)
    eventos = listar_eventos_operativos(conn=conn)

    codigos_usos = {item["codigo"] for item in usos}
    codigos_eventos = {item["codigo"] for item in eventos}

    assert "CAJA_GENERAL" in codigos_usos
    assert "PROVEEDORES_CC" in codigos_usos
    assert "CAPITAL_SOCIAL" in codigos_usos
    assert "IMPUESTOS_TASAS_CONTRIBUCIONES" in codigos_usos
    assert "COMPRA_FACTURA_GRAVADA" in codigos_eventos
    assert "IVA_CIERRE_MENSUAL" in codigos_eventos
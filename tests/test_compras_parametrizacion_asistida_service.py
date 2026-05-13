import sqlite3

import services.compras_diagnostico_service as servicio


def _conn_base():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            codigo TEXT,
            nombre TEXT,
            estado TEXT DEFAULT 'ACTIVA',
            imputable INTEGER DEFAULT 1,
            uso_operativo_sistema TEXT,
            cuenta_maestro_id INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE categorias_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            categoria TEXT,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            tipo_categoria TEXT,
            activo INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE categorias_compra_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            categoria TEXT,
            descripcion TEXT,
            tipo_categoria TEXT,
            tratamiento_contable TEXT,
            uso_operativo_principal_id INTEGER,
            uso_operativo_contrapartida_id INTEGER,
            cuenta_sugerida_id INTEGER,
            cuenta_contrapartida_sugerida_id INTEGER,
            requiere_auxiliar INTEGER DEFAULT 0,
            requiere_revision INTEGER DEFAULT 0,
            afecta_inventario INTEGER DEFAULT 0,
            afecta_bienes_uso INTEGER DEFAULT 0,
            afecta_resultado INTEGER DEFAULT 0,
            afecta_iva INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE conceptos_fiscales_compra (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            concepto TEXT,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            tratamiento TEXT,
            activo INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE conceptos_fiscales_compra_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            concepto TEXT,
            descripcion TEXT,
            tratamiento_fiscal TEXT,
            uso_operativo_id INTEGER,
            cuenta_sugerida_id INTEGER,
            afecta_iva INTEGER DEFAULT 0,
            afecta_iibb INTEGER DEFAULT 0,
            afecta_ganancias INTEGER DEFAULT 0,
            computable INTEGER DEFAULT 0,
            mayor_costo INTEGER DEFAULT 0,
            informativo INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'ACTIVO'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE compras_comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            categoria_compra TEXT,
            cuenta_principal_codigo TEXT,
            cuenta_proveedor_codigo TEXT,
            total REAL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def test_detecta_categoria_legacy_sin_config_ff():
    conn = _conn_base()
    conn.execute(
        "INSERT INTO categorias_compra (empresa_id, categoria, activo) VALUES (1, 'INSUMOS VARIOS', 1)"
    )
    conn.commit()

    resultado = servicio.diagnosticar_configuracion_compras(
        empresa_id=1,
        conn=conn,
        ruta_compras_service=None,
    )

    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert resultado["ok"] is True
    assert "COMPRA_CATEGORIA_LEGACY_SIN_CONFIG_FF" in codigos


def test_detecta_categoria_config_sin_cuenta_plan_empresa():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO categorias_compra_config
        (empresa_id, categoria, tratamiento_contable, afecta_resultado, afecta_iva, estado)
        VALUES (1, 'SERVICIOS CONTRATADOS', 'GASTO', 1, 1, 'ACTIVA')
        """
    )
    conn.commit()

    resultado = servicio.diagnosticar_configuracion_compras(
        empresa_id=1,
        conn=conn,
        ruta_compras_service=None,
    )

    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert "COMPRA_CATEGORIA_CONFIG_SIN_CUENTA_PLAN_EMPRESA" in codigos
    assert resultado["resumen"]["categorias_sin_cuenta_plan_empresa"] == 1


def test_controla_bienes_de_cambio_y_cmv_futuro():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO plan_cuentas_empresa (id, empresa_id, codigo, nombre, estado, imputable)
        VALUES (10, 1, '1.1.30.01', 'Mercaderías de reventa', 'ACTIVA', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO categorias_compra_config
        (empresa_id, categoria, descripcion, tratamiento_contable, cuenta_sugerida_id,
         afecta_inventario, afecta_resultado, afecta_iva, estado)
        VALUES (1, 'Mercadería para reventa', 'Compra de bienes de cambio', 'BIENES_DE_CAMBIO', 10,
                1, 0, 1, 'ACTIVA')
        """
    )
    conn.commit()

    resultado = servicio.diagnosticar_configuracion_compras(
        empresa_id=1,
        conn=conn,
        ruta_compras_service=None,
    )

    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert resultado["resumen"]["categorias_bienes_de_cambio"] == 1
    assert "COMPRA_BIENES_CAMBIO_REQUIERE_CMV_FUTURO" in codigos
    assert "COMPRA_BIENES_CAMBIO_IMPUTA_RESULTADO_DIRECTO" not in codigos


def test_detecta_bienes_de_cambio_imputados_a_resultado_directo():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO plan_cuentas_empresa (id, empresa_id, codigo, nombre, estado, imputable)
        VALUES (10, 1, '6.2.01.01', 'Costo de mercadería vendida', 'ACTIVA', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO categorias_compra_config
        (empresa_id, categoria, descripcion, tratamiento_contable, cuenta_sugerida_id,
         afecta_inventario, afecta_resultado, afecta_iva, estado)
        VALUES (1, 'Mercadería para reventa', 'Compra de bienes de cambio', 'BIENES_DE_CAMBIO', 10,
                1, 1, 1, 'ACTIVA')
        """
    )
    conn.commit()

    resultado = servicio.diagnosticar_configuracion_compras(
        empresa_id=1,
        conn=conn,
        ruta_compras_service=None,
    )

    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert "COMPRA_BIENES_CAMBIO_IMPUTA_RESULTADO_DIRECTO" in codigos


def test_detecta_concepto_fiscal_config_sin_cuenta_si_no_es_informativo():
    conn = _conn_base()
    conn.execute(
        """
        INSERT INTO conceptos_fiscales_compra_config
        (empresa_id, concepto, tratamiento_fiscal, afecta_iva, computable, informativo, estado)
        VALUES (1, 'IVA CREDITO FISCAL', 'CREDITO_FISCAL', 1, 1, 0, 'ACTIVO')
        """
    )
    conn.commit()

    resultado = servicio.diagnosticar_configuracion_compras(
        empresa_id=1,
        conn=conn,
        ruta_compras_service=None,
    )

    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert "COMPRA_CONCEPTO_FISCAL_CONFIG_SIN_CUENTA_PLAN_EMPRESA" in codigos
    assert resultado["resumen"]["conceptos_fiscales_sin_cuenta_plan_empresa"] == 1


def test_no_modifica_datos_operativos():
    conn = _conn_base()
    conn.execute(
        "INSERT INTO compras_comprobantes (empresa_id, categoria_compra, total) VALUES (1, '', 100)"
    )
    conn.commit()
    antes = conn.execute("SELECT COUNT(*) FROM compras_comprobantes").fetchone()[0]

    resultado = servicio.diagnosticar_configuracion_compras(
        empresa_id=1,
        conn=conn,
        ruta_compras_service=None,
    )
    despues = conn.execute("SELECT COUNT(*) FROM compras_comprobantes").fetchone()[0]

    assert resultado["ok"] is True
    assert antes == despues == 1
    assert resultado["resumen"]["compras_sin_categoria"] == 1
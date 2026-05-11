from __future__ import annotations

import sqlite3

from services.socios_control_vinculos_service import (
    controlar_vinculos_socios,
    listar_alertas_control_vinculos_socios,
    listar_detalle_control_vinculos_por_socio,
    resumir_control_vinculos_socios,
)
from services.socios_matriz_contable_service import actualizar_vinculo_matriz_contable


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE empresas (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            razon_social TEXT,
            tipo_sujeto TEXT,
            tipo_societario TEXT,
            cuit TEXT,
            estado TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO empresas
        (id, nombre, razon_social, tipo_sujeto, tipo_societario, cuit, estado)
        VALUES (1, 'Empresa Demo', 'Empresa Demo SA', 'PERSONA_JURIDICA_SOCIEDAD', 'SA', '20362253837', 'ACTIVA')
        """
    )

    conn.execute(
        """
        CREATE TABLE socios_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            nombre TEXT,
            cuit TEXT,
            tipo_socio TEXT,
            rol_relacion TEXT,
            condicion_fiscal TEXT,
            proveedor_vinculado_referencia TEXT,
            cuenta_particular_habilitada INTEGER,
            cuenta_particular_codigo TEXT,
            cuenta_particular_nombre TEXT,
            admite_prestamos INTEGER,
            admite_retiros INTEGER,
            admite_reintegros INTEGER,
            admite_honorarios INTEGER,
            admite_facturas_proveedor INTEGER,
            estado TEXT DEFAULT 'ACTIVO'
        )
        """
    )

    conn.execute(
        """
        INSERT INTO socios_empresa
        (
            empresa_id, nombre, cuit, tipo_socio, rol_relacion, condicion_fiscal,
            proveedor_vinculado_referencia, cuenta_particular_habilitada,
            cuenta_particular_codigo, cuenta_particular_nombre,
            admite_prestamos, admite_retiros, admite_reintegros,
            admite_honorarios, admite_facturas_proveedor, estado
        )
        VALUES
        (1, 'Socio Control', '', 'SOCIO', 'SOCIO', 'NO_INFORMADA', '',
         1, 'SOCIO-0001', 'Cuenta particular - Socio Control',
         1, 1, 1, 1, 1, 'ACTIVO')
        """
    )

    conn.execute(
        """
        CREATE TABLE plan_cuentas_maestro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_plan_id INTEGER DEFAULT 1,
            codigo TEXT,
            nombre TEXT,
            elemento TEXT,
            rubro TEXT,
            cuenta TEXT,
            subcuenta TEXT,
            imputable INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA',
            saldo_normal TEXT,
            uso_operativo_sistema TEXT,
            modulo_sugerido TEXT,
            orden INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            codigo TEXT,
            nombre TEXT,
            imputable INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA',
            uso_operativo_sistema TEXT,
            cuenta_maestro_id INTEGER,
            orden INTEGER DEFAULT 0
        )
        """
    )

    cuentas = [
        ("3.1.01", "Capital social", "PATRIMONIO_NETO", "Capital", "Capital social", "", 1, "ACTIVA", "ACREEDOR", "CAPITAL_SOCIAL", "CAPITAL", 10),
        ("1.4.01", "Socios por integración", "ACTIVO", "Otros créditos", "Socios por integración", "", 1, "ACTIVA", "DEUDOR", "SOCIOS_INTEGRACION", "CAPITAL", 20),
        ("2.5.01", "Préstamos de socios", "PASIVO", "Otras deudas", "Préstamos de socios", "", 1, "ACTIVA", "ACREEDOR", "PRESTAMO_SOCIO", "SOCIOS", 30),
        ("3.9.01", "Cuenta particular socios", "PATRIMONIO_NETO", "Cuentas particulares", "Cuenta particular socios", "", 1, "ACTIVA", "SEGUN_NATURALEZA", "CUENTA_PARTICULAR_SOCIO", "SOCIOS", 40),
        ("6.1.01", "Honorarios profesionales", "RESULTADO", "Gastos", "Honorarios", "", 1, "ACTIVA", "DEUDOR", "", "COMPRAS", 50),
        ("2.1.01", "Proveedores vinculados", "PASIVO", "Deudas comerciales", "Proveedores vinculados", "", 1, "ACTIVA", "ACREEDOR", "PROVEEDORES", "COMPRAS", 60),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_maestro
        (codigo, nombre, elemento, rubro, cuenta, subcuenta, imputable, estado,
         saldo_normal, uso_operativo_sistema, modulo_sugerido, orden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        cuentas,
    )
    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
        (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema, cuenta_maestro_id, orden)
        VALUES (1, ?, ?, 1, 'ACTIVA', ?, NULL, ?)
        """,
        [(c[0], c[1], c[9], c[11]) for c in cuentas],
    )

    conn.commit()
    return conn


def test_control_detecta_alertas_si_matriz_no_esta_configurada() -> None:
    conn = _conn()

    resultado = controlar_vinculos_socios(empresa_id=1, conn=conn)

    assert resultado["ok"] is True
    assert resultado["registra_movimientos"] is False
    assert resultado["genera_asientos"] is False
    assert resultado["total_socios"] == 1
    assert resultado["total_alertas"] > 0

    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
    assert "SOCIEDAD_MATRIZ_CAPITAL_INCOMPLETA" in codigos
    assert "SOCIO_PRESTAMO_SOCIO_EMPRESA_SIN_MATRIZ_CONFIGURADA" in codigos
    assert "SOCIO_HONORARIOS_SIN_PROVEEDOR_VINCULADO" in codigos


def test_control_reduce_alertas_cuando_se_configura_matriz_base() -> None:
    conn = _conn()

    inicial = controlar_vinculos_socios(empresa_id=1, conn=conn)
    total_inicial = int(inicial["total_alertas"])

    actualizar_vinculo_matriz_contable(
        empresa_id=1,
        tipo_vinculo="CAPITAL_SUSCRIPTO",
        cuenta_maestro_principal_codigo="3.1.01",
        cuenta_empresa_principal_codigo="3.1.01",
        cuenta_maestro_contrapartida_codigo="1.4.01",
        cuenta_empresa_contrapartida_codigo="1.4.01",
        usuario="tester",
        conn=conn,
    )
    actualizar_vinculo_matriz_contable(
        empresa_id=1,
        tipo_vinculo="INTEGRACION_CAPITAL",
        cuenta_maestro_principal_codigo="1.4.01",
        cuenta_empresa_principal_codigo="1.4.01",
        usuario="tester",
        conn=conn,
    )
    actualizar_vinculo_matriz_contable(
        empresa_id=1,
        tipo_vinculo="PRESTAMO_SOCIO_EMPRESA",
        cuenta_maestro_principal_codigo="2.5.01",
        cuenta_empresa_principal_codigo="2.5.01",
        usuario="tester",
        conn=conn,
    )

    posterior = controlar_vinculos_socios(empresa_id=1, conn=conn)
    codigos = {alerta["codigo"] for alerta in posterior["alertas"]}

    assert posterior["total_alertas"] < total_inicial
    assert "SOCIEDAD_MATRIZ_CAPITAL_INCOMPLETA" not in codigos
    assert "SOCIO_PRESTAMO_SOCIO_EMPRESA_SIN_MATRIZ_CONFIGURADA" not in codigos


def test_control_devuelve_dataframes_para_ui() -> None:
    conn = _conn()

    alertas = listar_alertas_control_vinculos_socios(empresa_id=1, conn=conn)
    detalle = listar_detalle_control_vinculos_por_socio(empresa_id=1, conn=conn)
    resumen = resumir_control_vinculos_socios(empresa_id=1, conn=conn)

    assert not alertas.empty
    assert not detalle.empty
    assert resumen["ok"] is True
    assert resumen["registra_movimientos"] is False
    assert resumen["genera_asientos"] is False


def test_control_no_falla_sin_tabla_socios() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    resultado = controlar_vinculos_socios(empresa_id=1, conn=conn)

    assert resultado["ok"] is True
    assert resultado["total_socios"] == 0
    assert resultado["registra_movimientos"] is False
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
    assert "SOCIOS_SIN_SOCIOS_ACTIVOS" in codigos
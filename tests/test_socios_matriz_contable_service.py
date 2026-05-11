from __future__ import annotations

import sqlite3

from services.socios_matriz_contable_service import (
    actualizar_vinculo_matriz_contable,
    asegurar_estructura_matriz_contable_socios,
    diagnosticar_matriz_contable_socios,
    listar_candidatas_matriz_contable,
    listar_matriz_contable_socios,
    obtener_vinculo_matriz_contable,
    restaurar_vinculo_matriz_contable,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

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

    cuentas_maestro = [
        ("3.1.01", "Capital social", "PATRIMONIO_NETO", "Capital", "Capital", "", 1, "ACTIVA", "ACREEDOR", "CAPITAL_SOCIAL", "CAPITAL", 10),
        ("1.4.01", "Socios por integración", "ACTIVO", "Otros créditos", "Socios por integración", "", 1, "ACTIVA", "DEUDOR", "SOCIOS_INTEGRACION", "CAPITAL", 20),
        ("2.5.01", "Préstamos de socios", "PASIVO", "Otras deudas", "Préstamos de socios", "", 1, "ACTIVA", "ACREEDOR", "PRESTAMO_SOCIO", "SOCIOS", 30),
        ("2.1.01", "Proveedores", "PASIVO", "Deudas comerciales", "Proveedores", "", 1, "ACTIVA", "ACREEDOR", "PROVEEDORES", "COMPRAS", 40),
        ("6.1.01", "Honorarios profesionales", "RESULTADO", "Gastos", "Honorarios", "", 1, "ACTIVA", "DEUDOR", "", "COMPRAS", 50),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_maestro
        (codigo, nombre, elemento, rubro, cuenta, subcuenta, imputable, estado, saldo_normal,
         uso_operativo_sistema, modulo_sugerido, orden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        cuentas_maestro,
    )

    cuentas_empresa = [
        (1, "3.1.01", "Capital social", 1, "ACTIVA", "CAPITAL_SOCIAL", 1, 10),
        (1, "1.4.01", "Socios por integración", 1, "ACTIVA", "SOCIOS_INTEGRACION", 2, 20),
        (1, "2.5.01", "Préstamos de socios", 1, "ACTIVA", "PRESTAMO_SOCIO", 3, 30),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
        (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema, cuenta_maestro_id, orden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        cuentas_empresa,
    )

    conn.commit()
    return conn


def test_crea_y_siembra_matriz_base() -> None:
    conn = _conn()

    asegurar_estructura_matriz_contable_socios(empresa_id=1, conn=conn)
    matriz = listar_matriz_contable_socios(empresa_id=1, conn=conn)

    assert not matriz.empty
    assert len(matriz) >= 9
    assert "CAPITAL_SUSCRIPTO" in set(matriz["tipo_vinculo"])
    assert "DEVOLUCION_PRESTAMO_SOCIO" in set(matriz["tipo_vinculo"])
    assert set(matriz["estado_configuracion_calculado"]) == {"PENDIENTE_CUENTA_CONTABLE"}


def test_actualiza_vinculo_con_plan_maestro_y_cuenta_empresa() -> None:
    conn = _conn()

    resultado = actualizar_vinculo_matriz_contable(
        empresa_id=1,
        tipo_vinculo="CAPITAL_SUSCRIPTO",
        cuenta_maestro_principal_codigo="3.1.01",
        cuenta_empresa_principal_codigo="3.1.01",
        cuenta_maestro_contrapartida_codigo="1.4.01",
        cuenta_empresa_contrapartida_codigo="1.4.01",
        observaciones="Configuración inicial de capital.",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True
    vinculo = obtener_vinculo_matriz_contable("CAPITAL_SUSCRIPTO", empresa_id=1, conn=conn)
    assert vinculo["cuenta_empresa_principal_nombre"] == "Capital social"
    assert vinculo["cuenta_maestro_contrapartida_nombre"] == "Socios por integración"
    assert vinculo["estado_configuracion_calculado"] == "CONFIGURADA_CON_CUENTA_EMPRESA"

    diagnostico = diagnosticar_matriz_contable_socios(empresa_id=1, conn=conn)
    assert diagnostico["configuradas"] == 1
    assert diagnostico["pendientes"] >= 1


def test_rechaza_cuentas_inexistentes() -> None:
    conn = _conn()

    resultado = actualizar_vinculo_matriz_contable(
        empresa_id=1,
        tipo_vinculo="PRESTAMO_SOCIO_EMPRESA",
        cuenta_maestro_principal_codigo="9.9.99",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is False
    assert "Plan Maestro" in resultado["mensaje"]


def test_lista_candidatas_por_tipo_de_vinculo() -> None:
    conn = _conn()

    candidatas = listar_candidatas_matriz_contable(
        tipo_vinculo="PRESTAMO_SOCIO_EMPRESA",
        empresa_id=1,
        conn=conn,
    )

    assert not candidatas["maestro"].empty
    assert not candidatas["empresa"].empty
    assert "2.5.01" in set(candidatas["maestro"]["codigo"])
    assert "2.5.01" in set(candidatas["empresa"]["codigo"])


def test_restaurar_vinculo_vuelve_a_pendiente_con_evento() -> None:
    conn = _conn()

    actualizar_vinculo_matriz_contable(
        empresa_id=1,
        tipo_vinculo="CAPITAL_SUSCRIPTO",
        cuenta_maestro_principal_codigo="3.1.01",
        cuenta_empresa_principal_codigo="3.1.01",
        usuario="tester",
        conn=conn,
    )

    resultado = restaurar_vinculo_matriz_contable(
        empresa_id=1,
        tipo_vinculo="CAPITAL_SUSCRIPTO",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True
    vinculo = obtener_vinculo_matriz_contable("CAPITAL_SUSCRIPTO", empresa_id=1, conn=conn)
    assert vinculo["cuenta_empresa_principal_codigo"] in {"", None}
    assert vinculo["estado_configuracion_calculado"] == "PENDIENTE_CUENTA_CONTABLE"

    eventos = conn.execute(
        """
        SELECT evento
        FROM socios_matriz_contable_eventos
        WHERE tipo_vinculo = 'CAPITAL_SUSCRIPTO'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    assert eventos["evento"] == "MATRIZ_RESTAURADA"

def test_lista_candidatas_tolera_campos_nulos_en_plan_empresa_y_maestro() -> None:
    conn = _conn()

    conn.execute(
        "INSERT INTO plan_cuentas_maestro "
        "(codigo, nombre, elemento, rubro, cuenta, subcuenta, imputable, estado, saldo_normal, "
        "uso_operativo_sistema, modulo_sugerido, orden) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "2.5.02",
            "Deudas con socios",
            None,
            None,
            None,
            None,
            1,
            "ACTIVA",
            None,
            None,
            None,
            60,
        ),
    )

    conn.execute(
        "INSERT INTO plan_cuentas_empresa "
        "(empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema, cuenta_maestro_id, orden) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "2.5.02",
            "Deudas con socios",
            1,
            "ACTIVA",
            None,
            None,
            60,
        ),
    )

    conn.execute(
        "UPDATE plan_cuentas_maestro "
        "SET elemento = NULL, rubro = NULL, cuenta = NULL, subcuenta = NULL, "
        "saldo_normal = NULL, uso_operativo_sistema = NULL, modulo_sugerido = NULL "
        "WHERE codigo = '2.5.01'"
    )
    conn.execute(
        "UPDATE plan_cuentas_empresa "
        "SET uso_operativo_sistema = NULL, cuenta_maestro_id = NULL "
        "WHERE codigo = '2.5.01'"
    )
    conn.commit()

    candidatas = listar_candidatas_matriz_contable(
        tipo_vinculo="PRESTAMO_SOCIO_EMPRESA",
        empresa_id=1,
        conn=conn,
    )

    assert not candidatas["maestro"].empty
    assert not candidatas["empresa"].empty
    assert "2.5.01" in set(candidatas["maestro"]["codigo"])
    assert "2.5.01" in set(candidatas["empresa"]["codigo"])


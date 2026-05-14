from __future__ import annotations

import sqlite3

import pytest

from services import ventas_asientos_propuestos_service as svc


def _conn_base() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE plan_cuentas_empresa (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER DEFAULT 1,
            codigo TEXT,
            nombre TEXT,
            imputable INTEGER DEFAULT 1,
            estado TEXT DEFAULT 'ACTIVA',
            uso_operativo_sistema TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE ventas_comprobantes (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER DEFAULT 1,
            fecha TEXT,
            codigo TEXT,
            tipo TEXT,
            punto_venta TEXT,
            numero TEXT,
            cliente TEXT,
            cuit TEXT,
            neto REAL DEFAULT 0,
            iva REAL DEFAULT 0,
            total REAL DEFAULT 0,
            archivo TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE asientos_origen (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER DEFAULT 1,
            tipo_origen TEXT,
            referencia TEXT,
            estado TEXT,
            asiento_propuesto_id INTEGER
        )
    """)
    cuentas = [
        (1, 1, "1.1.30.01", "Deudores por Ventas", 1, "ACTIVA", "CLIENTES_CC"),
        (2, 1, "4.1.01.01", "Ventas de Mercaderías", 1, "ACTIVA", "VENTAS_MERCADERIAS"),
        (3, 1, "4.1.02.01", "Ventas de Servicios", 1, "ACTIVA", "VENTAS_SERVICIOS"),
        (4, 1, "4.1.03.01", "Ventas Exentas", 1, "ACTIVA", "VENTAS_EXENTAS"),
        (5, 1, "2.1.40.01", "IVA Débito Fiscal", 1, "ACTIVA", "IVA_DEBITO_FISCAL"),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
            (id, empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        cuentas,
    )
    return conn


def _crear_actividad(conn: sqlite3.Connection, *, actividad_id=1, tipo="VENTA_MERCADERIAS", tratamiento="GRAVADO", cuenta_codigo=""):
    from services.ventas_actividades_service import asegurar_estructura_ventas_actividades

    asegurar_estructura_ventas_actividades(conn)
    conn.execute(
        """
        INSERT INTO ventas_actividades_empresa
            (id, empresa_id, codigo, nombre, tipo_venta, tratamiento_iva, cuenta_ventas_codigo, activo)
        VALUES (?, 1, ?, ?, ?, ?, ?, 1)
        """,
        (actividad_id, tipo, f"Actividad {tipo}", tipo, tratamiento, cuenta_codigo),
    )


def _crear_venta(conn: sqlite3.Connection, *, venta_id=10, codigo="001", tipo="Factura A", actividad_id=1):
    conn.execute(
        """
        INSERT INTO ventas_comprobantes
            (id, empresa_id, fecha, codigo, tipo, punto_venta, numero, cliente, neto, iva, total,
             actividad_venta_id, actividad_venta_codigo, actividad_venta_nombre, tipo_venta, tratamiento_iva_venta)
        VALUES
            (?, 1, '2026-05-14', ?, ?, '0001', '00000001', 'Cliente SA', 1000, 210, 1210,
             ?, 'ACT', 'Actividad', 'VENTA_MERCADERIAS', 'GRAVADO')
        """,
        (venta_id, codigo, tipo, actividad_id),
    )


def test_prepara_asiento_venta_con_actividad_balanceado():
    conn = _conn_base()
    _crear_actividad(conn)
    _crear_venta(conn)

    venta = svc._leer_venta(conn, 10, 1)
    resultado = svc.preparar_lineas_asiento_venta(venta, empresa_id=1, conn=conn)

    assert resultado["ok"] is True
    assert resultado["total_debe"] == 1210
    assert resultado["total_haber"] == 1210
    lineas = resultado["lineas"]
    assert lineas[0]["cuenta_codigo"] == "1.1.30.01"
    assert lineas[0]["debe"] == 1210
    assert any(l["cuenta_codigo"] == "4.1.01.01" and l["haber"] == 1000 for l in lineas)
    assert any(l["cuenta_codigo"] == "2.1.40.01" and l["haber"] == 210 for l in lineas)


def test_prepara_asiento_venta_exenta_sin_iva_debito():
    conn = _conn_base()
    _crear_actividad(conn, actividad_id=2, tipo="VENTA_EXENTA", tratamiento="EXENTO")
    _crear_venta(conn, venta_id=20, actividad_id=2)
    conn.execute("""
        UPDATE ventas_comprobantes
        SET tipo_venta = 'VENTA_EXENTA',
            tratamiento_iva_venta = 'EXENTO',
            actividad_venta_id = 2,
            iva = 0,
            neto = 1000,
            total = 1000
        WHERE id = 20
    """)

    venta = svc._leer_venta(conn, 20, 1)
    resultado = svc.preparar_lineas_asiento_venta(venta, empresa_id=1, conn=conn)

    assert resultado["ok"] is True
    assert resultado["total_debe"] == 1000
    assert resultado["total_haber"] == 1000
    assert not any(l["cuenta_codigo"] == "2.1.40.01" for l in resultado["lineas"])


def test_prepara_asiento_nota_credito_revierte_sentido():
    conn = _conn_base()
    _crear_actividad(conn)
    _crear_venta(conn, venta_id=30, codigo="003", tipo="Nota de Crédito A")

    venta = svc._leer_venta(conn, 30, 1)
    resultado = svc.preparar_lineas_asiento_venta(venta, empresa_id=1, conn=conn)

    assert resultado["ok"] is True
    assert resultado["es_nota_credito"] is True
    lineas = resultado["lineas"]
    assert any(l["cuenta_codigo"] == "1.1.30.01" and l["haber"] == 1210 for l in lineas)
    assert any(l["cuenta_codigo"] == "4.1.01.01" and l["debe"] == 1000 for l in lineas)
    assert any(l["cuenta_codigo"] == "2.1.40.01" and l["debe"] == 210 for l in lineas)


def test_lista_ventas_pendientes_exige_actividad_y_evitar_duplicados():
    conn = _conn_base()
    _crear_actividad(conn)
    _crear_venta(conn, venta_id=1)
    _crear_venta(conn, venta_id=2)
    conn.execute("""
        INSERT INTO ventas_comprobantes
            (id, empresa_id, fecha, codigo, tipo, numero, cliente, neto, iva, total)
        VALUES
            (3, 1, '2026-05-14', '001', 'Factura A', '3', 'Sin actividad', 300, 63, 363)
    """)
    conn.execute("""
        INSERT INTO asientos_origen
            (empresa_id, tipo_origen, referencia, estado, asiento_propuesto_id)
        VALUES
            (1, 'VENTA_ARCA', 'VENTA:1:1', 'PROPUESTO', 99)
    """)

    pendientes = svc.listar_ventas_pendientes_asiento(empresa_id=1, conn=conn)

    assert pendientes["id"].tolist() == [2]


def test_generar_asiento_propuesto_venta_usa_crear_asiento_origen(monkeypatch):
    conn = _conn_base()
    _crear_actividad(conn)
    _crear_venta(conn, venta_id=5)

    llamadas = {}

    def fake_crear_asiento_origen(**kwargs):
        llamadas.update(kwargs)
        return {"ok": True, "asiento_origen_id": 7, "asiento_propuesto_id": 8}

    monkeypatch.setattr(svc, "crear_asiento_origen", fake_crear_asiento_origen)

    resultado = svc.generar_asiento_propuesto_venta(5, empresa_id=1, usuario="tester", conn=conn)

    assert resultado["ok"] is True
    assert resultado["estado"] == "GENERADO"
    assert resultado["asiento_propuesto_id"] == 8
    assert llamadas["tipo_origen"] == "VENTA_ARCA"
    assert llamadas["referencia"] == "VENTA:1:5"
    assert llamadas["generar_propuesta"] is True
    assert llamadas["lineas"][0]["cuenta_codigo"] == "1.1.30.01"


def test_error_si_venta_no_tiene_actividad():
    conn = _conn_base()
    conn.execute("""
        INSERT INTO ventas_comprobantes
            (id, empresa_id, fecha, codigo, tipo, numero, cliente, neto, iva, total)
        VALUES
            (5, 1, '2026-05-14', '001', 'Factura A', '5', 'Cliente SA', 1000, 210, 1210)
    """)
    venta = svc._leer_venta(conn, 5, 1)

    with pytest.raises(svc.ErrorContableVentas):
        svc.preparar_lineas_asiento_venta(venta, empresa_id=1, conn=conn)


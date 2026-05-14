from __future__ import annotations

import sqlite3

import pytest

from services import compras_asientos_propuestos_service as svc


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
        CREATE TABLE usos_operativos_contables (
            id INTEGER PRIMARY KEY,
            codigo TEXT,
            activo INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE categorias_compra_config (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER DEFAULT 1,
            categoria TEXT,
            uso_operativo_principal_id INTEGER,
            cuenta_sugerida_id INTEGER,
            estado TEXT DEFAULT 'ACTIVA'
        )
    """)
    conn.execute("""
        CREATE TABLE categorias_compra (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER DEFAULT 1,
            categoria TEXT,
            cuenta_codigo TEXT,
            cuenta_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            activo INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE compras_comprobantes (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER DEFAULT 1,
            fecha TEXT,
            tipo TEXT,
            punto_venta TEXT,
            numero TEXT,
            proveedor TEXT,
            cuit TEXT,
            categoria_compra TEXT,
            cuenta_principal_codigo TEXT,
            cuenta_principal_nombre TEXT,
            cuenta_proveedor_codigo TEXT,
            cuenta_proveedor_nombre TEXT,
            neto REAL DEFAULT 0,
            iva REAL DEFAULT 0,
            total REAL DEFAULT 0,
            importe_no_gravado REAL DEFAULT 0,
            importe_exento REAL DEFAULT 0,
            iva_total REAL DEFAULT 0,
            credito_fiscal_computable REAL DEFAULT 0,
            iva_computable_sistema REAL DEFAULT 0,
            iva_no_computable_sistema REAL DEFAULT 0,
            iva_no_computable REAL DEFAULT 0,
            percepcion_iva REAL DEFAULT 0,
            percepcion_iibb REAL DEFAULT 0,
            percepcion_otros_imp_nac REAL DEFAULT 0,
            impuestos_municipales REAL DEFAULT 0,
            impuestos_internos REAL DEFAULT 0,
            otros_tributos REAL DEFAULT 0
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
        (1, 1, "6.1.11.10", "Papeles, Útiles y Gastos de Escritorio", 1, "ACTIVA", "SERVICIOS_CONTRATADOS"),
        (2, 1, "1.1.40.09", "IVA Crédito Fiscal", 1, "ACTIVA", "IVA_CREDITO_FISCAL"),
        (3, 1, "1.1.40.30", "Percepciones IVA", 1, "ACTIVA", "PERCEPCION_IVA"),
        (4, 1, "1.1.40.32", "Percepciones IIBB", 1, "ACTIVA", "PERCEPCION_IIBB"),
        (5, 1, "2.1.20.01", "Proveedores", 1, "ACTIVA", "PROVEEDORES"),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
            (id, empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        cuentas,
    )
    conn.execute("INSERT INTO usos_operativos_contables (id, codigo, activo) VALUES (42, 'SERVICIOS_CONTRATADOS', 1)")
    conn.execute("""
        INSERT INTO categorias_compra_config
            (empresa_id, categoria, uso_operativo_principal_id, cuenta_sugerida_id, estado)
        VALUES (1, 'LIBRERIA Y UTILES', 42, NULL, 'ACTIVA')
    """)
    return conn


def test_prepara_asiento_compra_balanceado_con_plan_empresa():
    conn = _conn_base()
    compra = {
        "id": 10,
        "empresa_id": 1,
        "fecha": "2026-05-14",
        "tipo": "Factura A",
        "punto_venta": "0001",
        "numero": "00000001",
        "proveedor": "Proveedor SA",
        "categoria_compra": "LIBRERIA Y UTILES",
        "neto": 1000,
        "iva_total": 210,
        "credito_fiscal_computable": 210,
        "percepcion_iva": 30,
        "percepcion_iibb": 20,
        "total": 1260,
    }

    resultado = svc.preparar_lineas_asiento_compra(compra, empresa_id=1, conn=conn)

    assert resultado["ok"] is True
    assert resultado["total_debe"] == 1260
    assert resultado["total_haber"] == 1260
    codigos = {linea["cuenta_codigo"] for linea in resultado["lineas"]}
    assert "6.1.11.10" in codigos
    assert "1.1.40.09" in codigos
    assert "1.1.40.30" in codigos
    assert "1.1.40.32" in codigos
    assert "2.1.20.01" in codigos


def test_lista_compras_pendientes_sin_duplicar_asiento_existente():
    conn = _conn_base()
    conn.execute("""
        INSERT INTO compras_comprobantes
            (id, empresa_id, fecha, tipo, numero, proveedor, categoria_compra, neto, iva_total, credito_fiscal_computable, total)
        VALUES
            (1, 1, '2026-05-14', 'Factura A', '1', 'A', 'LIBRERIA Y UTILES', 100, 21, 21, 121),
            (2, 1, '2026-05-14', 'Factura A', '2', 'B', 'LIBRERIA Y UTILES', 200, 42, 42, 242)
    """)
    conn.execute("""
        INSERT INTO asientos_origen
            (empresa_id, tipo_origen, referencia, estado, asiento_propuesto_id)
        VALUES
            (1, 'COMPRA_ARCA', 'COMPRA:1:1', 'PROPUESTO', 99)
    """)

    pendientes = svc.listar_compras_pendientes_asiento(empresa_id=1, conn=conn)

    assert pendientes["id"].tolist() == [2]


def test_generar_asiento_propuesto_compra_usa_crear_asiento_origen(monkeypatch):
    conn = _conn_base()
    conn.execute("""
        INSERT INTO compras_comprobantes
            (id, empresa_id, fecha, tipo, punto_venta, numero, proveedor, categoria_compra, neto, iva_total, credito_fiscal_computable, total)
        VALUES
            (5, 1, '2026-05-14', 'Factura A', '0001', '00000005', 'Proveedor SA', 'LIBRERIA Y UTILES', 1000, 210, 210, 1210)
    """)

    llamadas = {}

    def fake_crear_asiento_origen(**kwargs):
        llamadas.update(kwargs)
        return {"ok": True, "asiento_origen_id": 7, "asiento_propuesto_id": 8}

    monkeypatch.setattr(svc, "crear_asiento_origen", fake_crear_asiento_origen)

    resultado = svc.generar_asiento_propuesto_compra(5, empresa_id=1, usuario="tester", conn=conn)

    assert resultado["ok"] is True
    assert resultado["estado"] == "GENERADO"
    assert resultado["asiento_propuesto_id"] == 8
    assert llamadas["tipo_origen"] == "COMPRA_ARCA"
    assert llamadas["referencia"] == "COMPRA:1:5"
    assert llamadas["generar_propuesta"] is True
    assert llamadas["lineas"][0]["cuenta_codigo"] == "6.1.11.10"


def test_error_si_categoria_no_resuelve_plan_empresa():
    conn = _conn_base()
    compra = {
        "id": 10,
        "empresa_id": 1,
        "fecha": "2026-05-14",
        "tipo": "Factura A",
        "proveedor": "Proveedor SA",
        "categoria_compra": "CATEGORIA INEXISTENTE",
        "neto": 1000,
        "iva_total": 210,
        "credito_fiscal_computable": 210,
        "total": 1210,
    }

    with pytest.raises(svc.ErrorContableCompras):
        svc.preparar_lineas_asiento_compra(compra, empresa_id=1, conn=conn)
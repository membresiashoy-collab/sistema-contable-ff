import sqlite3

from services import ventas_actividades_service as actividades
from services import ventas_asientos_propuestos_service as asientos


def _crear_schema(conn):
    conn.execute(
        """
        CREATE TABLE ventas_comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            fecha TEXT,
            codigo TEXT,
            tipo TEXT,
            punto_venta TEXT,
            numero TEXT,
            cliente TEXT,
            cuit TEXT,
            neto REAL,
            iva REAL,
            total REAL,
            archivo TEXT
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
            estado TEXT DEFAULT 'ACTIVA',
            imputable INTEGER DEFAULT 1,
            uso_operativo_sistema TEXT
        )
        """
    )
    cuentas = [
        (1, "1.1.03.01", "Deudores por Ventas", "ACTIVA", 1, "DEUDORES_POR_VENTAS"),
        (1, "2.1.02.01", "IVA Débito Fiscal", "ACTIVA", 1, "IVA_DEBITO_FISCAL"),
        (1, "4.1.01.01", "Ventas de Mercaderías", "ACTIVA", 1, "VENTAS_MERCADERIAS"),
        (1, "4.1.02.01", "Ventas de Servicios", "ACTIVA", 1, "VENTAS_SERVICIOS"),
    ]
    conn.executemany(
        """
        INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, estado, imputable, uso_operativo_sistema)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        cuentas,
    )


def test_agrupacion_interna_no_define_cuenta_contable():
    conn = sqlite3.connect(":memory:")
    _crear_schema(conn)

    agrupacion = actividades.crear_actividad_venta(
        empresa_id=1,
        codigo="CUBIERTAS",
        nombre="Cubiertas",
        tipo_venta="VENTA_MERCADERIAS",
        tratamiento_iva="GRAVADO",
        cuenta_ventas_codigo="4.9.99.99",
        cuenta_ventas_nombre="Cuenta que no debe usarse",
        conn=conn,
    )

    fila_agrupacion = conn.execute(
        "SELECT cuenta_ventas_codigo, cuenta_ventas_nombre FROM ventas_actividades_empresa WHERE id = ?",
        (agrupacion["actividad_id"],),
    ).fetchone()
    assert fila_agrupacion == ("", "")

    conn.execute(
        """
        INSERT INTO ventas_comprobantes
            (empresa_id, fecha, codigo, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo)
        VALUES (1, '2025-08-01', '001', 'FACTURA', '00001', '00000001', 'Cliente Uno', '20111111112', 1000, 210, 1210, 'ventas.csv')
        """
    )
    venta_id = conn.execute("SELECT id FROM ventas_comprobantes").fetchone()[0]

    actividades.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[venta_id],
        actividad_id=agrupacion["actividad_id"],
        conn=conn,
    )

    preparado = asientos.preparar_lineas_asiento_venta(
        {k: v for k, v in zip([c[1] for c in conn.execute("PRAGMA table_info(ventas_comprobantes)")], conn.execute("SELECT * FROM ventas_comprobantes WHERE id=?", (venta_id,)).fetchone())},
        empresa_id=1,
        conn=conn,
    )

    assert preparado["ok"] is True
    assert preparado["cuenta_ventas_resuelta"]["nombre"] == "Ventas de Mercaderías"
    assert preparado["cuenta_ventas_resuelta"]["nombre"] != "Cubiertas"
    assert any("Cubiertas" in linea["glosa"] for linea in preparado["lineas"])
    assert round(preparado["total_debe"] - preparado["total_haber"], 2) == 0
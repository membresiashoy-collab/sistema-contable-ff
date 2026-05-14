from __future__ import annotations

import sqlite3

from services import ventas_actividades_service as svc


def _conn_base() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE ventas_comprobantes (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER DEFAULT 1,
            fecha TEXT,
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
    """)
    conn.executemany(
        """
        INSERT INTO ventas_comprobantes
            (id, empresa_id, fecha, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo)
        VALUES (?, 1, '2026-05-14', 'Factura A', '0001', ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "00000001", "Cliente A", "20111111112", 1000, 210, 1210, "ventas_mayo.csv"),
            (2, "00000002", "Cliente B", "20222222223", 2000, 420, 2420, "ventas_mayo.csv"),
            (3, "00000003", "Cliente C", "20333333334", 3000, 630, 3630, "ventas_junio.csv"),
        ],
    )
    return conn


def test_asegura_estructura_y_siembra_actividades_base():
    conn = _conn_base()

    estructura = svc.asegurar_estructura_ventas_actividades(conn)
    siembra = svc.sembrar_actividades_base(empresa_id=1, conn=conn)

    assert estructura["ok"] is True
    assert siembra["ok"] is True
    columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(ventas_comprobantes)").fetchall()}
    assert "actividad_venta_id" in columnas
    assert "actividad_venta_codigo" in columnas
    assert "tipo_venta" in columnas
    assert "tratamiento_iva_venta" in columnas

    actividades = svc.listar_actividades_venta(empresa_id=1, conn=conn)
    assert "Venta de mercaderías / bienes" in actividades["nombre"].tolist()


def test_crea_actividad_y_asigna_a_ventas():
    conn = _conn_base()
    actividad = svc.crear_actividad_venta(
        empresa_id=1,
        codigo="SERV_PROF",
        nombre="Servicios profesionales",
        tipo_venta="VENTA_SERVICIOS",
        tratamiento_iva="GRAVADO",
        usuario="tester",
        conn=conn,
    )

    resultado = svc.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[1, 2],
        actividad_id=actividad["actividad_id"],
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["ventas_actualizadas"] == 2

    filas = conn.execute(
        """
        SELECT id, actividad_venta_codigo, actividad_venta_nombre, tipo_venta, tratamiento_iva_venta
        FROM ventas_comprobantes
        ORDER BY id
        """
    ).fetchall()

    assert filas[0][1:] == ("SERV_PROF", "Servicios profesionales", "VENTA_SERVICIOS", "GRAVADO")
    assert filas[1][1:] == ("SERV_PROF", "Servicios profesionales", "VENTA_SERVICIOS", "GRAVADO")
    assert filas[2][1] is None


def test_lista_ventas_sin_actividad_filtrando_archivo():
    conn = _conn_base()
    actividad = svc.crear_actividad_venta(
        empresa_id=1,
        codigo="MERCA",
        nombre="Mercaderías",
        tipo_venta="VENTA_MERCADERIAS",
        tratamiento_iva="GRAVADO",
        conn=conn,
    )
    svc.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[1],
        actividad_id=actividad["actividad_id"],
        conn=conn,
    )

    pendientes = svc.listar_ventas_sin_actividad(
        empresa_id=1,
        archivo="ventas_mayo.csv",
        conn=conn,
    )

    assert pendientes["id"].tolist() == [2]


def test_asigna_actividad_a_todas_las_pendientes_de_un_archivo():
    conn = _conn_base()
    actividad = svc.crear_actividad_venta(
        empresa_id=1,
        codigo="EXPO_SERV",
        nombre="Exportación de servicios",
        tipo_venta="EXPORTACION_SERVICIOS",
        tratamiento_iva="EXPORTACION",
        conn=conn,
    )

    resultado = svc.asignar_actividad_a_ventas_pendientes(
        empresa_id=1,
        actividad_id=actividad["actividad_id"],
        archivo="ventas_mayo.csv",
        usuario="tester",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["ventas_actualizadas"] == 2

    resumen = svc.obtener_resumen_actividades_ventas(empresa_id=1, conn=conn)
    assert resumen["total"] == 3
    assert resumen["con_actividad"] == 2
    assert resumen["sin_actividad"] == 1
    assert resumen["por_actividad"]["Exportación de servicios"] == 2
    assert resumen["por_actividad"]["SIN_ACTIVIDAD"] == 1


import sqlite3

from services import ventas_actividades_service as svc


def _conn_base():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE ventas_comprobantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        """
    )
    conn.execute(
        """
        CREATE TABLE asientos_origen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            tipo_origen TEXT,
            referencia TEXT,
            estado TEXT
        )
        """
    )
    ventas = [
        (1, "2026-05-01", "FACTURA", "00001", "00000001", "Cliente A", "201", 1000, 210, 1210, "ventas_mayo.csv"),
        (1, "2026-05-02", "FACTURA", "00001", "00000002", "Cliente B", "202", 2000, 420, 2420, "ventas_mayo.csv"),
        (1, "2026-05-03", "FACTURA", "00001", "00000003", "Cliente C", "203", 3000, 630, 3630, "ventas_mayo.csv"),
    ]
    conn.executemany(
        """
        INSERT INTO ventas_comprobantes
            (empresa_id, fecha, tipo, punto_venta, numero, cliente, cuit, neto, iva, total, archivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ventas,
    )
    svc.asegurar_estructura_ventas_actividades(conn)
    return conn


def _crear_agrupacion(conn, codigo, nombre, tipo="VENTA_MERCADERIAS", tratamiento="GRAVADO"):
    return svc.crear_actividad_venta(
        empresa_id=1,
        codigo=codigo,
        nombre=nombre,
        tipo_venta=tipo,
        tratamiento_iva=tratamiento,
        conn=conn,
    )


def _insertar_asiento_venta(conn, venta_id):
    conn.execute(
        """
        INSERT INTO asientos_origen (empresa_id, tipo_origen, referencia, estado)
        VALUES (?, ?, ?, ?)
        """,
        (1, svc.ORIGEN_VENTA, f"VENTA:1:{venta_id}", "PENDIENTE"),
    )


def test_editar_nombre_y_codigo_actualiza_ventas_asociadas_sin_usar_cuentas():
    conn = _conn_base()
    agrupacion = _crear_agrupacion(conn, "CUBERITA", "Cuberita")

    svc.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[1, 2],
        actividad_id=agrupacion["actividad_id"],
        conn=conn,
    )

    resultado = svc.editar_agrupacion_venta(
        empresa_id=1,
        actividad_id=agrupacion["actividad_id"],
        codigo="CUBIERTAS",
        nombre="Cubiertas",
        tipo_venta="VENTA_MERCADERIAS",
        tratamiento_iva="GRAVADO",
        descripcion="Corrección de nombre",
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["ventas_actualizadas"] == 2

    fila = conn.execute(
        """
        SELECT codigo, nombre, cuenta_ventas_codigo, cuenta_ventas_nombre
        FROM ventas_actividades_empresa
        WHERE id = ?
        """,
        (agrupacion["actividad_id"],),
    ).fetchone()
    assert fila == ("CUBIERTAS", "Cubiertas", "", "")

    ventas = conn.execute(
        """
        SELECT actividad_venta_codigo, actividad_venta_nombre
        FROM ventas_comprobantes
        WHERE id IN (1, 2)
        ORDER BY id
        """
    ).fetchall()
    assert ventas == [("CUBIERTAS", "Cubiertas"), ("CUBIERTAS", "Cubiertas")]


def test_reasignar_bloquea_solo_comprobante_con_asiento_propuesto():
    conn = _conn_base()
    movimiento = _crear_agrupacion(conn, "MOV_SUELO", "Movimiento de suelo")
    cubiertas = _crear_agrupacion(conn, "CUBIERTAS", "Cubiertas")

    svc.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[1, 2, 3],
        actividad_id=movimiento["actividad_id"],
        conn=conn,
    )
    _insertar_asiento_venta(conn, 2)

    resultado = svc.reasignar_agrupacion_ventas(
        empresa_id=1,
        venta_ids=[1, 2],
        actividad_id=cubiertas["actividad_id"],
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["estado"] == "ACTUALIZADO_PARCIAL"
    assert resultado["ventas_actualizadas"] == 1
    assert resultado["ventas_bloqueadas"] == [2]

    ventas = conn.execute(
        """
        SELECT id, actividad_venta_codigo, actividad_venta_nombre
        FROM ventas_comprobantes
        WHERE id IN (1, 2, 3)
        ORDER BY id
        """
    ).fetchall()

    assert ventas == [
        (1, "CUBIERTAS", "Cubiertas"),
        (2, "MOV_SUELO", "Movimiento de suelo"),
        (3, "MOV_SUELO", "Movimiento de suelo"),
    ]


def test_desasignar_bloquea_solo_comprobante_con_asiento_propuesto():
    conn = _conn_base()
    agrupacion = _crear_agrupacion(conn, "MOV_SUELO", "Movimiento de suelo")

    svc.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[1, 2],
        actividad_id=agrupacion["actividad_id"],
        conn=conn,
    )
    _insertar_asiento_venta(conn, 2)

    resultado = svc.desasignar_agrupacion_ventas(
        empresa_id=1,
        venta_ids=[1, 2],
        conn=conn,
    )

    assert resultado["ok"] is True
    assert resultado["ventas_actualizadas"] == 1
    assert resultado["ventas_bloqueadas"] == [2]

    ventas = conn.execute(
        """
        SELECT id, COALESCE(actividad_venta_codigo, ''), COALESCE(actividad_venta_nombre, '')
        FROM ventas_comprobantes
        WHERE id IN (1, 2)
        ORDER BY id
        """
    ).fetchall()

    assert ventas == [
        (1, "", ""),
        (2, "MOV_SUELO", "Movimiento de suelo"),
    ]


def test_editar_tipo_fiscal_bloquea_si_venta_asociada_tiene_asiento_propuesto():
    conn = _conn_base()
    agrupacion = _crear_agrupacion(conn, "CUBIERTAS", "Cubiertas")

    svc.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[1],
        actividad_id=agrupacion["actividad_id"],
        conn=conn,
    )
    _insertar_asiento_venta(conn, 1)

    resultado = svc.editar_agrupacion_venta(
        empresa_id=1,
        actividad_id=agrupacion["actividad_id"],
        codigo="CUBIERTAS",
        nombre="Cubiertas",
        tipo_venta="VENTA_SERVICIOS",
        tratamiento_iva="GRAVADO",
        conn=conn,
    )

    assert resultado["ok"] is False
    assert resultado["estado"] == "BLOQUEADO_ASIENTOS_PROPUESTOS"
    assert resultado["ventas_bloqueadas"] == [1]

    tipo = conn.execute(
        "SELECT tipo_venta FROM ventas_comprobantes WHERE id = 1"
    ).fetchone()[0]
    assert tipo == "VENTA_MERCADERIAS"


def test_desactivar_y_reactivar_agrupacion_sin_borrar_historia():
    conn = _conn_base()
    agrupacion = _crear_agrupacion(conn, "CUBIERTAS", "Cubiertas")

    svc.asignar_actividad_a_ventas(
        empresa_id=1,
        venta_ids=[1],
        actividad_id=agrupacion["actividad_id"],
        conn=conn,
    )

    desactivada = svc.desactivar_agrupacion_venta(
        empresa_id=1,
        actividad_id=agrupacion["actividad_id"],
        conn=conn,
    )
    assert desactivada["ok"] is True

    activas = svc.listar_actividades_venta(empresa_id=1, solo_activas=True, conn=conn)
    assert "CUBIERTAS" not in activas["codigo"].tolist()

    venta = conn.execute(
        "SELECT actividad_venta_codigo, actividad_venta_nombre FROM ventas_comprobantes WHERE id = 1"
    ).fetchone()
    assert venta == ("CUBIERTAS", "Cubiertas")

    reactivada = svc.reactivar_agrupacion_venta(
        empresa_id=1,
        actividad_id=agrupacion["actividad_id"],
        conn=conn,
    )
    assert reactivada["ok"] is True

    activas = svc.listar_actividades_venta(empresa_id=1, solo_activas=True, conn=conn)
    assert "CUBIERTAS" in activas["codigo"].tolist()
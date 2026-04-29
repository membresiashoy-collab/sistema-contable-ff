import pandas as pd
import pytest

import database
from services import pagos_service
from services import tesoreria_service


@pytest.fixture()
def db_temporal(tmp_path, monkeypatch):
    db_path = tmp_path / "pagos_test.sqlite"

    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    monkeypatch.setattr(database, "DB_ENGINE", "sqlite")

    conn = database.conectar()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cuenta_corriente_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            fecha TEXT,
            proveedor TEXT,
            cuit TEXT,
            tipo TEXT,
            numero TEXT,
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0,
            saldo REAL DEFAULT 0,
            origen TEXT,
            archivo TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            id_asiento INTEGER,
            fecha TEXT,
            cuenta TEXT,
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0,
            glosa TEXT,
            origen TEXT,
            archivo TEXT,
            origen_tabla TEXT,
            origen_id INTEGER,
            comprobante_clave TEXT,
            estado TEXT DEFAULT 'CONTABILIZADO',
            usuario_creacion INTEGER,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    pagos_service.inicializar_pagos()

    return db_path


def _insertar_deuda_proveedor(importe=1000):
    conn = database.conectar()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO cuenta_corriente_proveedores
        (
            empresa_id,
            fecha,
            proveedor,
            cuit,
            tipo,
            numero,
            debe,
            haber,
            saldo,
            origen,
            archivo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "2026-01-01",
            "Proveedor Demo",
            "30777777778",
            "FACTURA",
            "0001-00000001",
            0,
            importe,
            0,
            "COMPRAS",
            "compras.csv",
        ),
    )

    conn.commit()
    conn.close()


def _leer_sql(sql, params=()):
    conn = database.conectar()

    try:
        return pd.read_sql_query(sql, conn, params=params)

    finally:
        conn.close()


def test_obtener_proveedores_con_saldo_pendiente(db_temporal):
    _insertar_deuda_proveedor(importe=1000)

    control = _leer_sql("""
        SELECT proveedor, cuit, debe, haber
        FROM cuenta_corriente_proveedores
    """)

    assert len(control) == 1
    assert round(float(control.iloc[0]["haber"]), 2) == 1000.00

    proveedores = pagos_service.obtener_proveedores_con_saldo_pendiente(empresa_id=1)

    assert not proveedores.empty
    assert proveedores.iloc[0]["proveedor"] == "Proveedor Demo"
    assert round(float(proveedores.iloc[0]["saldo"]), 2) == 1000.00


def test_registrar_pago_transferencia_cancela_cuenta_corriente_y_genera_asiento(db_temporal):
    _insertar_deuda_proveedor(importe=1000)

    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="BANCO",
        nombre="Banco Demo",
        cuenta_contable_nombre="Banco Demo",
    )

    pendientes = pagos_service.obtener_comprobantes_pendientes_proveedor(
        empresa_id=1,
        proveedor="Proveedor Demo",
        cuit="30777777778",
    )

    assert len(pendientes) == 1

    resultado = pagos_service.registrar_pago(
        empresa_id=1,
        fecha_pago="2026-01-10",
        fecha_contable="2026-01-10",
        proveedor="Proveedor Demo",
        cuit="30777777778",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        medio_pago_codigo="TRANSFERENCIA",
        importe_pagado=1000,
        referencia_externa="OP-1",
        descripcion="Pago transferencia proveedor demo",
        imputaciones=[
            {
                "cuenta_corriente_id": int(pendientes.iloc[0]["cuenta_corriente_id"]),
                "tipo_comprobante": "FACTURA",
                "numero_comprobante": "0001-00000001",
                "importe_imputado": 1000,
            }
        ],
        retenciones=[],
        usuario_id=1,
    )

    assert resultado["ok"] is True
    assert resultado["creada"] is True
    assert resultado["numero_orden_pago"].startswith("OP-")
    assert resultado["asiento_id"] == 1
    assert resultado["tesoreria_operacion_id"] is not None

    saldo = _leer_sql(
        """
        SELECT ROUND(SUM(haber - debe), 2) AS saldo
        FROM cuenta_corriente_proveedores
        WHERE empresa_id = 1
          AND cuit = '30777777778'
        """
    ).iloc[0]["saldo"]

    diario = _leer_sql(
        """
        SELECT cuenta, debe, haber
        FROM libro_diario
        ORDER BY id
        """
    )

    tesoreria = _leer_sql(
        """
        SELECT tipo_operacion, importe, estado_conciliacion
        FROM tesoreria_operaciones
        """
    )

    assert round(float(saldo), 2) == 0.00
    assert len(diario) == 2
    assert round(float(diario["debe"].sum()), 2) == 1000.00
    assert round(float(diario["haber"].sum()), 2) == 1000.00
    assert tesoreria.iloc[0]["tipo_operacion"] == "PAGO"
    assert round(float(tesoreria.iloc[0]["importe"]), 2) == -1000.00
    assert tesoreria.iloc[0]["estado_conciliacion"] == "PENDIENTE"


def test_registrar_pago_con_retencion_cancela_total_factura(db_temporal):
    _insertar_deuda_proveedor(importe=1000)

    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="BANCO",
        nombre="Banco Demo",
        cuenta_contable_nombre="Banco Demo",
    )

    resultado = pagos_service.registrar_pago(
        empresa_id=1,
        fecha_pago="2026-01-11",
        fecha_contable="2026-01-11",
        proveedor="Proveedor Demo",
        cuit="30777777778",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        medio_pago_codigo="TRANSFERENCIA",
        importe_pagado=950,
        referencia_externa="TRX-1",
        descripcion="Pago con retención Ganancias",
        imputaciones=[
            {
                "tipo_comprobante": "FACTURA",
                "numero_comprobante": "0001-00000001",
                "importe_imputado": 1000,
            }
        ],
        retenciones=[
            {
                "tipo_retencion": "GANANCIAS",
                "descripcion": "Retención Ganancias practicada",
                "importe": 50,
            }
        ],
        usuario_id=1,
    )

    assert resultado["ok"] is True
    assert resultado["importe_pagado"] == 950
    assert resultado["importe_retenciones"] == 50
    assert resultado["importe_total_aplicado"] == 1000

    saldo = _leer_sql(
        """
        SELECT ROUND(SUM(haber - debe), 2) AS saldo
        FROM cuenta_corriente_proveedores
        WHERE empresa_id = 1
          AND cuit = '30777777778'
        """
    ).iloc[0]["saldo"]

    diario = _leer_sql(
        """
        SELECT cuenta, debe, haber
        FROM libro_diario
        ORDER BY id
        """
    )

    assert round(float(saldo), 2) == 0.00
    assert len(diario) == 3
    assert round(float(diario["debe"].sum()), 2) == 1000.00
    assert round(float(diario["haber"].sum()), 2) == 1000.00


def test_anular_pago_genera_reverso_y_reabre_saldo(db_temporal):
    _insertar_deuda_proveedor(importe=1000)

    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="BANCO",
        nombre="Banco Demo",
        cuenta_contable_nombre="Banco Demo",
    )

    resultado = pagos_service.registrar_pago(
        empresa_id=1,
        fecha_pago="2026-01-12",
        fecha_contable="2026-01-12",
        proveedor="Proveedor Demo",
        cuit="30777777778",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        medio_pago_codigo="TRANSFERENCIA",
        importe_pagado=1000,
        referencia_externa="OP-2",
        descripcion="Pago a anular",
        imputaciones=[
            {
                "tipo_comprobante": "FACTURA",
                "numero_comprobante": "0001-00000001",
                "importe_imputado": 1000,
            }
        ],
        retenciones=[],
        usuario_id=1,
    )

    anulacion_sin_motivo = pagos_service.anular_pago(
        resultado["pago_id"],
        empresa_id=1,
        motivo="",
    )

    assert anulacion_sin_motivo["ok"] is False

    anulacion = pagos_service.anular_pago(
        resultado["pago_id"],
        empresa_id=1,
        usuario_id=1,
        motivo="Error humano de carga",
    )

    assert anulacion["ok"] is True
    assert anulacion["anulado"] is True
    assert anulacion["asiento_reverso"] == 2

    saldo = _leer_sql(
        """
        SELECT ROUND(SUM(haber - debe), 2) AS saldo
        FROM cuenta_corriente_proveedores
        WHERE empresa_id = 1
          AND cuit = '30777777778'
        """
    ).iloc[0]["saldo"]

    estado = _leer_sql(
        """
        SELECT estado
        FROM pagos
        WHERE id = ?
        """,
        params=(resultado["pago_id"],),
    ).iloc[0]["estado"]

    assert round(float(saldo), 2) == 1000.00
    assert estado == "ANULADO"
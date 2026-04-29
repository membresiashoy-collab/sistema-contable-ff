import sqlite3

import pandas as pd
import pytest

import database
from services import cobranzas_service
from services import tesoreria_service


@pytest.fixture()
def db_temporal(tmp_path, monkeypatch):
    db_path = tmp_path / "cobranzas_test.sqlite"

    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    monkeypatch.setattr(database, "DB_ENGINE", "sqlite")

    conn = database.conectar()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cuenta_corriente_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER DEFAULT 1,
            fecha TEXT,
            cliente TEXT,
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

    cobranzas_service.inicializar_cobranzas()

    return db_path


def _insertar_deuda_cliente(importe=1000):
    conn = database.conectar()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO cuenta_corriente_clientes
        (
            empresa_id,
            fecha,
            cliente,
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
            "Cliente Demo",
            "20111111112",
            "FACTURA",
            "0001-00000001",
            importe,
            0,
            0,
            "VENTAS",
            "ventas.csv",
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


def test_obtener_clientes_con_saldo_pendiente(db_temporal):
    _insertar_deuda_cliente(importe=1000)

    control = _leer_sql("""
        SELECT cliente, cuit, debe, haber
        FROM cuenta_corriente_clientes
    """)

    assert len(control) == 1
    assert round(float(control.iloc[0]["debe"]), 2) == 1000.00

    clientes = cobranzas_service.obtener_clientes_con_saldo_pendiente(empresa_id=1)

    assert not clientes.empty
    assert clientes.iloc[0]["cliente"] == "Cliente Demo"
    assert round(float(clientes.iloc[0]["saldo"]), 2) == 1000.00


def test_registrar_cobranza_efectivo_cancela_cuenta_corriente_y_genera_asiento(db_temporal):
    _insertar_deuda_cliente(importe=1000)

    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="CAJA",
        nombre="Caja principal",
        cuenta_contable_nombre="Caja principal",
    )

    pendientes = cobranzas_service.obtener_comprobantes_pendientes_cliente(
        empresa_id=1,
        cliente="Cliente Demo",
        cuit="20111111112",
    )

    assert len(pendientes) == 1

    resultado = cobranzas_service.registrar_cobranza(
        empresa_id=1,
        fecha_cobranza="2026-01-10",
        fecha_contable="2026-01-10",
        cliente="Cliente Demo",
        cuit="20111111112",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        medio_pago_codigo="EFECTIVO",
        importe_recibido=1000,
        referencia_externa="REC-1",
        descripcion="Cobranza efectivo cliente demo",
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
    assert resultado["numero_recibo"].startswith("RC-")
    assert resultado["asiento_id"] == 1
    assert resultado["tesoreria_operacion_id"] is not None

    saldo = _leer_sql(
        """
        SELECT ROUND(SUM(debe - haber), 2) AS saldo
        FROM cuenta_corriente_clientes
        WHERE empresa_id = 1
          AND cuit = '20111111112'
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
    assert tesoreria.iloc[0]["tipo_operacion"] == "COBRANZA"
    assert round(float(tesoreria.iloc[0]["importe"]), 2) == 1000.00
    assert tesoreria.iloc[0]["estado_conciliacion"] == "PENDIENTE"


def test_registrar_cobranza_con_retencion_cancela_total_factura(db_temporal):
    _insertar_deuda_cliente(importe=1000)

    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="BANCO",
        nombre="Banco Demo",
        cuenta_contable_nombre="Banco Demo",
    )

    resultado = cobranzas_service.registrar_cobranza(
        empresa_id=1,
        fecha_cobranza="2026-01-11",
        fecha_contable="2026-01-11",
        cliente="Cliente Demo",
        cuit="20111111112",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        medio_pago_codigo="TRANSFERENCIA",
        importe_recibido=950,
        referencia_externa="TRX-1",
        descripcion="Cobranza con retención IIBB",
        imputaciones=[
            {
                "tipo_comprobante": "FACTURA",
                "numero_comprobante": "0001-00000001",
                "importe_imputado": 1000,
            }
        ],
        retenciones=[
            {
                "tipo_retencion": "IIBB",
                "descripcion": "Retención IIBB sufrida",
                "importe": 50,
            }
        ],
        usuario_id=1,
    )

    assert resultado["ok"] is True
    assert resultado["importe_recibido"] == 950
    assert resultado["importe_retenciones"] == 50
    assert resultado["importe_total_aplicado"] == 1000

    saldo = _leer_sql(
        """
        SELECT ROUND(SUM(debe - haber), 2) AS saldo
        FROM cuenta_corriente_clientes
        WHERE empresa_id = 1
          AND cuit = '20111111112'
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


def test_anular_cobranza_genera_reverso_y_reabre_saldo(db_temporal):
    _insertar_deuda_cliente(importe=1000)

    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="CAJA",
        nombre="Caja principal",
        cuenta_contable_nombre="Caja principal",
    )

    resultado = cobranzas_service.registrar_cobranza(
        empresa_id=1,
        fecha_cobranza="2026-01-12",
        fecha_contable="2026-01-12",
        cliente="Cliente Demo",
        cuit="20111111112",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        medio_pago_codigo="EFECTIVO",
        importe_recibido=1000,
        referencia_externa="REC-2",
        descripcion="Cobranza a anular",
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

    anulacion_sin_motivo = cobranzas_service.anular_cobranza(
        resultado["cobranza_id"],
        empresa_id=1,
        motivo="",
    )

    assert anulacion_sin_motivo["ok"] is False

    anulacion = cobranzas_service.anular_cobranza(
        resultado["cobranza_id"],
        empresa_id=1,
        usuario_id=1,
        motivo="Error humano de carga",
    )

    assert anulacion["ok"] is True
    assert anulacion["anulada"] is True
    assert anulacion["asiento_reverso"] == 2

    saldo = _leer_sql(
        """
        SELECT ROUND(SUM(debe - haber), 2) AS saldo
        FROM cuenta_corriente_clientes
        WHERE empresa_id = 1
          AND cuit = '20111111112'
        """
    ).iloc[0]["saldo"]

    estado = _leer_sql(
        """
        SELECT estado
        FROM cobranzas
        WHERE id = ?
        """,
        params=(resultado["cobranza_id"],),
    ).iloc[0]["estado"]

    assert round(float(saldo), 2) == 1000.00
    assert estado == "ANULADA"
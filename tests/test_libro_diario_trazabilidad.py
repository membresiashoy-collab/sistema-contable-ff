import sqlite3
from pathlib import Path

import pandas as pd

import database
from services.libro_diario_trazabilidad_service import (
    TIPO_CONTROLADO_BANDEJA,
    TIPO_DIRECTO_HISTORICO,
    TIPO_REVERSO_BANDEJA,
    listar_trazabilidad_libro_diario,
    obtener_detalle_asiento_libro_diario,
    obtener_resumen_trazabilidad_libro_diario,
)


def _preparar_db_temporal(monkeypatch, tmp_path):
    db_path = tmp_path / "test_trazabilidad.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS asientos_propuestos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            ejercicio_id INTEGER,
            fecha TEXT NOT NULL,
            origen TEXT NOT NULL,
            origen_tabla TEXT,
            origen_id INTEGER,
            tipo_asiento TEXT NOT NULL,
            referencia TEXT,
            descripcion TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'PROPUESTO',
            total_debe REAL NOT NULL DEFAULT 0,
            total_haber REAL NOT NULL DEFAULT 0,
            diferencia REAL NOT NULL DEFAULT 0,
            id_asiento_libro_diario INTEGER,
            id_asiento_reversion_libro_diario INTEGER,
            fecha_contabilizacion TIMESTAMP,
            fecha_reversion TIMESTAMP,
            usuario_contabilizacion TEXT,
            usuario_reversion TEXT,
            lote_contabilizacion_id INTEGER,
            lote_reversion_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS asientos_bandeja_lotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            accion TEXT NOT NULL,
            estado TEXT NOT NULL,
            cantidad_solicitada INTEGER NOT NULL DEFAULT 0,
            cantidad_procesada INTEGER NOT NULL DEFAULT 0,
            cantidad_error INTEGER NOT NULL DEFAULT 0,
            total_debe REAL NOT NULL DEFAULT 0,
            total_haber REAL NOT NULL DEFAULT 0,
            diferencia REAL NOT NULL DEFAULT 0,
            detalle TEXT,
            usuario TEXT,
            fecha_lote TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS asientos_bandeja_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL DEFAULT 1,
            fuente TEXT NOT NULL,
            fuente_id INTEGER,
            fuente_clave TEXT NOT NULL,
            evento TEXT NOT NULL,
            detalle TEXT,
            usuario TEXT,
            fecha_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    conn.commit()
    conn.close()
    return db_path


def _insertar_linea(conn, id_asiento, cuenta, debe, haber, **kwargs):
    conn.execute(
        """
        INSERT INTO libro_diario
        (id_asiento, fecha, cuenta, debe, haber, glosa, origen, archivo, empresa_id,
         origen_tabla, origen_id, comprobante_clave, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id_asiento,
            kwargs.get("fecha", "2026-01-10"),
            cuenta,
            debe,
            haber,
            kwargs.get("glosa", "Prueba"),
            kwargs.get("origen", ""),
            kwargs.get("archivo", ""),
            kwargs.get("empresa_id", 1),
            kwargs.get("origen_tabla", ""),
            kwargs.get("origen_id", None),
            kwargs.get("comprobante_clave", ""),
            kwargs.get("estado", "CONTABILIZADO"),
        ),
    )


def test_clasifica_asiento_directo_historico(monkeypatch, tmp_path):
    db_path = _preparar_db_temporal(monkeypatch, tmp_path)

    conn = sqlite3.connect(db_path)
    _insertar_linea(conn, 1, "Caja", 1000, 0)
    _insertar_linea(conn, 1, "Capital", 0, 1000)
    conn.commit()
    conn.close()

    df = listar_trazabilidad_libro_diario(empresa_id=1)

    assert len(df) == 1
    assert df.iloc[0]["id_asiento"] == 1
    assert df.iloc[0]["tipo_trazabilidad"] == TIPO_DIRECTO_HISTORICO
    assert df.iloc[0]["cuadrado"] is True or bool(df.iloc[0]["cuadrado"]) is True


def test_detecta_asiento_controlado_por_bandeja_y_lote(monkeypatch, tmp_path):
    db_path = _preparar_db_temporal(monkeypatch, tmp_path)

    conn = sqlite3.connect(db_path)
    _insertar_linea(conn, 2, "IVA a pagar", 500, 0, origen="IVA_CIERRE", comprobante_clave="CENTRAL:10")
    _insertar_linea(conn, 2, "IVA débito fiscal", 0, 500, origen="IVA_CIERRE", comprobante_clave="CENTRAL:10")

    conn.execute(
        """
        INSERT INTO asientos_bandeja_lotes
        (id, empresa_id, accion, estado, cantidad_solicitada, cantidad_procesada, total_debe, total_haber, usuario)
        VALUES (1, 1, 'CONTABILIZACION_MASIVA', 'FINALIZADO', 1, 1, 500, 500, 'tester')
        """
    )

    conn.execute(
        """
        INSERT INTO asientos_propuestos
        (id, empresa_id, fecha, origen, origen_tabla, origen_id, tipo_asiento, referencia,
         descripcion, estado, total_debe, total_haber, diferencia, id_asiento_libro_diario,
         lote_contabilizacion_id)
        VALUES (10, 1, '2026-01-10', 'IVA_CIERRE', 'iva_cierres', 7, 'CIERRE_IVA',
                'Cierre enero', 'Cierre IVA enero', 'CONTABILIZADO', 500, 500, 0, 2, 1)
        """
    )

    conn.commit()
    conn.close()

    df = listar_trazabilidad_libro_diario(empresa_id=1)
    fila = df[df["id_asiento"] == 2].iloc[0]

    assert fila["tipo_trazabilidad"] == TIPO_CONTROLADO_BANDEJA
    assert fila["fuente_propuesta"] == "CENTRAL"
    assert fila["fuente_clave"] == "CENTRAL:10"
    assert int(fila["lote_id"]) == 1
    assert fila["lote_estado"] == "FINALIZADO"


def test_detecta_reverso_de_bandeja(monkeypatch, tmp_path):
    db_path = _preparar_db_temporal(monkeypatch, tmp_path)

    conn = sqlite3.connect(db_path)
    _insertar_linea(conn, 3, "Banco", 200, 0, origen="REVERSO_APERTURA", comprobante_clave="REVERSO:CENTRAL:11")
    _insertar_linea(conn, 3, "Capital", 0, 200, origen="REVERSO_APERTURA", comprobante_clave="REVERSO:CENTRAL:11")

    conn.execute(
        """
        INSERT INTO asientos_propuestos
        (id, empresa_id, fecha, origen, origen_tabla, origen_id, tipo_asiento, referencia,
         descripcion, estado, total_debe, total_haber, diferencia,
         id_asiento_libro_diario, id_asiento_reversion_libro_diario)
        VALUES (11, 1, '2026-01-10', 'APERTURA', 'asientos_origen', 3, 'APERTURA',
                'Apertura', 'Asiento apertura', 'REVERSADO', 200, 200, 0, 2, 3)
        """
    )

    conn.commit()
    conn.close()

    df = listar_trazabilidad_libro_diario(empresa_id=1)
    fila = df[df["id_asiento"] == 3].iloc[0]

    assert fila["tipo_trazabilidad"] == TIPO_REVERSO_BANDEJA
    assert fila["fuente_clave"] == "CENTRAL:11"
    assert int(fila["id_asiento_referenciado"]) == 2


def test_resumen_detecta_descuadre_y_detalle(monkeypatch, tmp_path):
    db_path = _preparar_db_temporal(monkeypatch, tmp_path)

    conn = sqlite3.connect(db_path)
    _insertar_linea(conn, 4, "Caja", 100, 0)
    _insertar_linea(conn, 4, "Ventas", 0, 90)
    conn.commit()
    conn.close()

    resumen = obtener_resumen_trazabilidad_libro_diario(empresa_id=1)
    detalle = obtener_detalle_asiento_libro_diario(empresa_id=1, id_asiento=4)

    assert resumen["total_asientos"] == 1
    assert resumen["descuadrados"] == 1
    assert detalle["ok"] is True
    assert isinstance(detalle["detalle"], pd.DataFrame)
    assert len(detalle["detalle"]) == 2
    assert round(float(detalle["resumen"]["diferencia"]), 2) == 10.0
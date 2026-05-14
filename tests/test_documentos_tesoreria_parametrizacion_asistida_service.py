import sqlite3

from services.documentos_tesoreria_parametrizacion_asistida_service import (
    generar_parametrizacion_asistida_documentos_tesoreria,
)


def crear_schema_param_documentos(conn):
    conn.executescript(
        """
        CREATE TABLE cobranzas (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            numero_recibo TEXT,
            fecha_cobranza TEXT,
            importe_recibido REAL,
            estado TEXT,
            tesoreria_operacion_id INTEGER,
            motivo_anulacion TEXT,
            fecha_anulacion TEXT
        );
        CREATE TABLE pagos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            numero_orden_pago TEXT,
            fecha_pago TEXT,
            importe_pagado REAL,
            estado TEXT,
            tesoreria_operacion_id INTEGER,
            motivo_anulacion TEXT,
            fecha_anulacion TEXT
        );
        CREATE TABLE tesoreria_operaciones (id INTEGER PRIMARY KEY, empresa_id INTEGER);
        CREATE TABLE cobranzas_imputaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            cobranza_id INTEGER,
            cuenta_corriente_id INTEGER,
            importe_imputado REAL
        );
        CREATE TABLE pagos_imputaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            pago_id INTEGER,
            cuenta_corriente_id INTEGER,
            importe_imputado REAL
        );
        CREATE TABLE cobranzas_retenciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            cobranza_id INTEGER,
            tipo_retencion TEXT,
            importe REAL
        );
        CREATE TABLE pagos_retenciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            pago_id INTEGER,
            tipo_retencion TEXT,
            importe REAL
        );
        """
    )


def test_parametrizacion_documentos_es_solo_lectura():
    conn = sqlite3.connect(":memory:")
    crear_schema_param_documentos(conn)
    antes = conn.total_changes
    resultado = generar_parametrizacion_asistida_documentos_tesoreria(conn, empresa_id=1)
    despues = conn.total_changes
    assert resultado["solo_lectura"] is True
    assert resultado["acciones_realizadas"] == []
    assert antes == despues


def test_parametrizacion_documentos_contiene_recibo_y_orden_pago():
    conn = sqlite3.connect(":memory:")
    crear_schema_param_documentos(conn)
    resultado = generar_parametrizacion_asistida_documentos_tesoreria(conn, empresa_id=1)
    codigos = {c["codigo"] for c in resultado["matriz"]}
    assert "RECIBO_COBRANZA" in codigos
    assert "ORDEN_PAGO_PAGO" in codigos
    assert resultado["resumen"]["casos_total"] == len(resultado["matriz"])


def test_parametrizacion_documentos_detecta_soporte_de_trazabilidad():
    conn = sqlite3.connect(":memory:")
    crear_schema_param_documentos(conn)
    resultado = generar_parametrizacion_asistida_documentos_tesoreria(conn, empresa_id=1)
    trazabilidad = next(c for c in resultado["matriz"] if c["codigo"] == "TRAZABILIDAD_TESORERIA")
    assert trazabilidad["soporte_estructural"] is True
    assert trazabilidad["estado"] == "SUGERIDO"


def test_parametrizacion_documentos_marca_estructura_incompleta_sin_tablas():
    conn = sqlite3.connect(":memory:")
    resultado = generar_parametrizacion_asistida_documentos_tesoreria(conn, empresa_id=1)
    assert resultado["resumen"]["estructura_incompleta"] > 0
    assert any(c["estado"] == "ESTRUCTURA_INCOMPLETA" for c in resultado["matriz"])


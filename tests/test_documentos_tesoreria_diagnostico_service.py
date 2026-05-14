import sqlite3

from services.documentos_tesoreria_diagnostico_service import diagnosticar_documentos_tesoreria


def crear_schema_documentos(conn):
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
            asiento_id INTEGER,
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
            asiento_id INTEGER,
            motivo_anulacion TEXT,
            fecha_anulacion TEXT
        );
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
        CREATE TABLE tesoreria_operaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER
        );
        """
    )


def test_diagnostico_documentos_es_solo_lectura():
    conn = sqlite3.connect(":memory:")
    crear_schema_documentos(conn)
    antes = conn.total_changes
    resultado = diagnosticar_documentos_tesoreria(conn, empresa_id=1)
    despues = conn.total_changes
    assert resultado["solo_lectura"] is True
    assert resultado["acciones_realizadas"] == []
    assert antes == despues


def test_diagnostico_documentos_base_limpia_sin_advertencias():
    conn = sqlite3.connect(":memory:")
    crear_schema_documentos(conn)
    resultado = diagnosticar_documentos_tesoreria(conn, empresa_id=1)
    assert resultado["estado"] == "OK"
    assert any(a["codigo"] == "DOC_TESORERIA_SIN_DOCUMENTOS" for a in resultado["alertas"])


def test_diagnostico_detecta_recibo_sin_numero():
    conn = sqlite3.connect(":memory:")
    crear_schema_documentos(conn)
    conn.execute(
        "INSERT INTO cobranzas (empresa_id, numero_recibo, fecha_cobranza, importe_recibido, estado, tesoreria_operacion_id) VALUES (1, '', '2026-01-01', 100, 'ACTIVO', 1)"
    )
    resultado = diagnosticar_documentos_tesoreria(conn, empresa_id=1)
    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert resultado["estado"] == "REQUIERE_REVISION"
    assert "DOC_TESORERIA_RECIBOS_SIN_NUMERO" in codigos


def test_diagnostico_detecta_orden_pago_duplicada():
    conn = sqlite3.connect(":memory:")
    crear_schema_documentos(conn)
    conn.execute(
        "INSERT INTO pagos (empresa_id, numero_orden_pago, fecha_pago, importe_pagado, estado, tesoreria_operacion_id) VALUES (1, 'OP-1', '2026-01-01', 100, 'ACTIVO', 1)"
    )
    conn.execute(
        "INSERT INTO pagos (empresa_id, numero_orden_pago, fecha_pago, importe_pagado, estado, tesoreria_operacion_id) VALUES (1, 'OP-1', '2026-01-02', 200, 'ACTIVO', 2)"
    )
    resultado = diagnosticar_documentos_tesoreria(conn, empresa_id=1)
    codigos = {a["codigo"] for a in resultado["alertas"]}
    assert "DOC_TESORERIA_ORDENES_PAGO_NUMERO_DUPLICADO" in codigos


def test_diagnostico_documentos_critico_si_faltan_tablas():
    conn = sqlite3.connect(":memory:")
    resultado = diagnosticar_documentos_tesoreria(conn, empresa_id=1)
    assert resultado["estado"] == "CRITICO"
    assert any(a["nivel"] == "CRITICO" for a in resultado["alertas"])


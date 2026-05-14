from __future__ import annotations

import sqlite3

from services.conciliacion_diagnostico_service import (
    diagnosticar_conciliacion,
    obtener_alertas_conciliacion,
    obtener_resumen_conciliacion_diagnostico,
)


def _crear_conexion_base() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE bancos_movimientos (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            banco TEXT,
            nombre_cuenta TEXT,
            fecha TEXT,
            concepto TEXT,
            referencia TEXT,
            importe REAL,
            importe_conciliado REAL,
            importe_pendiente REAL,
            estado_conciliacion TEXT
        );

        CREATE TABLE tesoreria_operaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            tipo_operacion TEXT,
            subtipo TEXT,
            fecha_operacion TEXT,
            cuenta_tesoreria_id INTEGER,
            tercero_nombre TEXT,
            tercero_cuit TEXT,
            descripcion TEXT,
            referencia_externa TEXT,
            importe REAL,
            importe_conciliado REAL,
            importe_pendiente REAL,
            estado TEXT,
            estado_conciliacion TEXT,
            motivo_anulacion TEXT
        );

        CREATE TABLE bancos_conciliaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            movimiento_banco_id INTEGER,
            fecha TEXT,
            tipo_conciliacion TEXT,
            estado TEXT,
            importe_total REAL,
            importe_imputado REAL,
            importe_pendiente REAL,
            observacion TEXT
        );

        CREATE TABLE bancos_conciliaciones_detalle (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            conciliacion_id INTEGER,
            movimiento_banco_id INTEGER,
            entidad_tabla TEXT,
            entidad_id INTEGER,
            comprobante TEXT,
            importe_imputado REAL
        );
        """
    )
    return con


def test_diagnostico_es_solo_lectura_y_no_crea_tablas() -> None:
    con = sqlite3.connect(":memory:")
    antes = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]

    resultado = diagnosticar_conciliacion(conexion=con)

    despues = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    assert antes == despues == 0
    assert resultado["solo_lectura"] is True
    assert resultado["estado"] == "CRITICO"
    assert resultado["resumen"]["tablas_requeridas_detectadas"] == 0
    assert any(alerta["codigo"] == "CONCILIACION_TABLA_REQUERIDA_INEXISTENTE" for alerta in resultado["alertas"])


def test_detecta_movimientos_y_operaciones_pendientes() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_movimientos
        (id, empresa_id, banco, nombre_cuenta, fecha, concepto, referencia, importe, importe_conciliado, importe_pendiente, estado_conciliacion)
        VALUES (1, 1, 'Macro', 'Cta Cte', '2026-01-10', 'Transferencia cliente', 'TRX001', 1000, 0, 1000, 'PENDIENTE')
        """
    )
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
        (id, empresa_id, tipo_operacion, fecha_operacion, descripcion, referencia_externa, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES (10, 1, 'COBRANZA', '2026-01-10', 'Cobranza cliente', 'TRX001', 1000, 0, 1000, 'CONFIRMADA', 'PENDIENTE')
        """
    )

    resultado = diagnosticar_conciliacion(conexion=con)

    assert resultado["resumen"]["movimientos_bancarios_pendientes"] == 1
    assert resultado["resumen"]["operaciones_tesoreria_pendientes"] == 1
    assert resultado["resumen"]["posibles_pares_por_importe_signo"] == 1
    assert resultado["bancos"]["pendientes"][0]["id"] == 1
    assert resultado["tesoreria"]["pendientes"][0]["id"] == 10


def test_detecta_conciliacion_activa_sin_detalle() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_conciliaciones
        (id, empresa_id, movimiento_banco_id, fecha, tipo_conciliacion, estado, importe_total, importe_imputado, importe_pendiente, observacion)
        VALUES (5, 1, 1, '2026-01-10', 'TESORERIA_OPERACION', 'CONFIRMADA', 1000, 1000, 0, 'ok')
        """
    )

    resultado = diagnosticar_conciliacion(conexion=con)

    assert resultado["estado"] == "CRITICO"
    assert resultado["resumen"]["conciliaciones_sin_detalle"] == 1
    assert any(alerta["codigo"] == "CONCILIACION_ACTIVA_SIN_DETALLE" for alerta in resultado["alertas"])


def test_detecta_detalle_huerfano_y_referencias_inexistentes() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_conciliaciones_detalle
        (id, empresa_id, conciliacion_id, movimiento_banco_id, entidad_tabla, entidad_id, comprobante, importe_imputado)
        VALUES (20, 1, 999, 888, 'tesoreria_operaciones', 777, 'TES-777', 500)
        """
    )

    resultado = diagnosticar_conciliacion(conexion=con)

    assert resultado["resumen"]["detalles_sin_conciliacion"] == 1
    assert resultado["resumen"]["detalles_sin_movimiento_banco"] == 1
    assert resultado["resumen"]["detalles_sin_operacion_tesoreria"] == 1
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
    assert "CONCILIACION_DETALLE_SIN_CABECERA" in codigos
    assert "CONCILIACION_DETALLE_SIN_MOVIMIENTO_BANCO" in codigos
    assert "CONCILIACION_DETALLE_SIN_OPERACION_TESORERIA" in codigos


def test_detecta_estados_desconocidos() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_movimientos
        (id, empresa_id, banco, fecha, importe, importe_conciliado, importe_pendiente, estado_conciliacion)
        VALUES (1, 1, 'Macro', '2026-01-10', 100, 0, 100, 'RARO')
        """
    )
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
        (id, empresa_id, tipo_operacion, fecha_operacion, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES (2, 1, 'COBRANZA', '2026-01-10', 100, 0, 100, 'CONFIRMADA', 'EXTRAÑO')
        """
    )

    resultado = diagnosticar_conciliacion(conexion=con)

    assert resultado["resumen"]["movimientos_bancarios_estado_desconocido"] == 1
    assert resultado["resumen"]["operaciones_tesoreria_estado_desconocido"] == 1
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
    assert "CONCILIACION_BANCO_ESTADO_DESCONOCIDO" in codigos
    assert "CONCILIACION_TESORERIA_ESTADO_CONCILIACION_DESCONOCIDO" in codigos


def test_detecta_conciliados_con_pendiente_inconsistente() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_movimientos
        (id, empresa_id, banco, fecha, importe, importe_conciliado, importe_pendiente, estado_conciliacion)
        VALUES (1, 1, 'Macro', '2026-01-10', 1000, 500, 500, 'CONCILIADO')
        """
    )
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
        (id, empresa_id, tipo_operacion, fecha_operacion, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES (2, 1, 'COBRANZA', '2026-01-10', 1000, 500, 500, 'CONFIRMADA', 'CONCILIADA')
        """
    )

    resultado = diagnosticar_conciliacion(conexion=con)

    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
    assert "CONCILIACION_BANCO_CONCILIADO_CON_PENDIENTE" in codigos
    assert "CONCILIACION_TESORERIA_CONCILIADA_CON_PENDIENTE" in codigos
    assert resultado["estado"] == "CRITICO"


def test_operacion_anulada_sin_motivo_genera_advertencia() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
        (id, empresa_id, tipo_operacion, fecha_operacion, importe, estado, estado_conciliacion, motivo_anulacion)
        VALUES (2, 1, 'PAGO', '2026-01-10', -100, 'ANULADA', 'PENDIENTE', '')
        """
    )

    resultado = diagnosticar_conciliacion(conexion=con)

    assert resultado["resumen"]["operaciones_tesoreria_anuladas"] == 1
    assert any(alerta["codigo"] == "CONCILIACION_TESORERIA_ANULADA_SIN_MOTIVO" for alerta in resultado["alertas"])


def test_helpers_resumen_y_alertas() -> None:
    con = _crear_conexion_base()
    resumen = obtener_resumen_conciliacion_diagnostico(conexion=con)
    alertas = obtener_alertas_conciliacion(conexion=con)

    assert isinstance(resumen, dict)
    assert isinstance(alertas, list)
    assert resumen["tablas_requeridas_detectadas"] == 4

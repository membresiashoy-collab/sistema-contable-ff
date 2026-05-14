from __future__ import annotations

import sqlite3

from services.conciliacion_parametrizacion_asistida_service import (
    analizar_parametrizacion_conciliacion,
    obtener_alertas_parametrizacion_conciliacion,
    obtener_resumen_parametrizacion_conciliacion,
    obtener_sugerencias_conciliacion_asistida,
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
            causal TEXT,
            importe REAL,
            importe_conciliado REAL,
            importe_pendiente REAL,
            estado_conciliacion TEXT
        );

        CREATE TABLE tesoreria_cuentas (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            tipo_cuenta TEXT,
            nombre TEXT
        );

        CREATE TABLE tesoreria_medios_pago (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            codigo TEXT,
            nombre TEXT
        );

        CREATE TABLE tesoreria_operaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            tipo_operacion TEXT,
            subtipo TEXT,
            origen_modulo TEXT,
            fecha_operacion TEXT,
            cuenta_tesoreria_id INTEGER,
            medio_pago_id INTEGER,
            tercero_nombre TEXT,
            tercero_cuit TEXT,
            descripcion TEXT,
            referencia_externa TEXT,
            importe REAL,
            importe_conciliado REAL,
            importe_pendiente REAL,
            estado TEXT,
            estado_conciliacion TEXT
        );

        CREATE TABLE bancos_conciliaciones (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            movimiento_banco_id INTEGER,
            tipo_conciliacion TEXT,
            estado TEXT
        );

        CREATE TABLE bancos_conciliaciones_detalle (
            id INTEGER PRIMARY KEY,
            empresa_id INTEGER,
            conciliacion_id INTEGER,
            movimiento_banco_id INTEGER,
            entidad_tabla TEXT,
            entidad_id INTEGER,
            importe_imputado REAL
        );
        """
    )
    return con


def _insertar_par_base(con: sqlite3.Connection) -> None:
    con.execute(
        """
        INSERT INTO bancos_movimientos
            (id, empresa_id, banco, nombre_cuenta, fecha, concepto, referencia, importe, importe_conciliado, importe_pendiente, estado_conciliacion)
        VALUES
            (1, 1, 'Macro', 'Cta Cte', '2026-01-10', 'Transferencia cliente Gomez TRX001', 'TRX001', 1000, 0, 1000, 'PENDIENTE')
        """
    )
    con.execute("INSERT INTO tesoreria_cuentas (id, empresa_id, tipo_cuenta, nombre) VALUES (1, 1, 'BANCO', 'Banco Macro')")
    con.execute("INSERT INTO tesoreria_medios_pago (id, empresa_id, codigo, nombre) VALUES (1, 1, 'TRANSFERENCIA', 'Transferencia bancaria')")
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
            (id, empresa_id, tipo_operacion, origen_modulo, fecha_operacion, cuenta_tesoreria_id, medio_pago_id, tercero_nombre, tercero_cuit, descripcion, referencia_externa, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES
            (10, 1, 'COBRANZA', 'COBRANZAS', '2026-01-10', 1, 1, 'Gomez SRL', '30711111119', 'Cobranza cliente Gomez TRX001', 'TRX001', 1000, 0, 1000, 'CONFIRMADA', 'PENDIENTE')
        """
    )
    con.commit()


def test_parametrizacion_es_solo_lectura_y_genera_sugerencia_alta() -> None:
    con = _crear_conexion_base()
    _insertar_par_base(con)
    antes = {
        tabla: con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in ("bancos_movimientos", "tesoreria_operaciones", "bancos_conciliaciones", "bancos_conciliaciones_detalle")
    }

    resultado = analizar_parametrizacion_conciliacion(conexion=con, tolerancia_importe=0.01)

    despues = {
        tabla: con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        for tabla in antes
    }
    assert antes == despues
    assert resultado["solo_lectura"] is True
    assert resultado["resumen"]["sugerencias"] == 1
    assert resultado["resumen"]["sugerencias_alta"] == 1
    sugerencia = resultado["sugerencias"][0]
    assert sugerencia["movimiento_banco_id"] == 1
    assert sugerencia["operacion_tesoreria_id"] == 10
    assert sugerencia["confianza"] == "ALTA"
    assert sugerencia["accion_sugerida"] == "SUGERIR_CONCILIACION_ASISTIDA"


def test_no_sugiere_si_el_signo_financiero_no_coincide() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_movimientos
            (id, empresa_id, fecha, concepto, referencia, importe, importe_conciliado, importe_pendiente, estado_conciliacion)
        VALUES (1, 1, '2026-01-10', 'Debito pago', 'PAG001', -500, 0, 500, 'PENDIENTE')
        """
    )
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
            (id, empresa_id, tipo_operacion, fecha_operacion, descripcion, referencia_externa, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES (10, 1, 'COBRANZA', '2026-01-10', 'Cobranza', 'PAG001', 500, 0, 500, 'CONFIRMADA', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_conciliacion(conexion=con)

    assert resultado["resumen"]["sugerencias"] == 0
    assert resultado["resumen"]["pares_descartados_signo"] == 1
    assert resultado["resumen"]["movimientos_sin_sugerencia"] == 1


def test_no_sugiere_si_el_importe_excede_tolerancia() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_movimientos
            (id, empresa_id, fecha, concepto, referencia, importe, importe_conciliado, importe_pendiente, estado_conciliacion)
        VALUES (1, 1, '2026-01-10', 'Transferencia', 'TRX001', 1000, 0, 1000, 'PENDIENTE')
        """
    )
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
            (id, empresa_id, tipo_operacion, fecha_operacion, descripcion, referencia_externa, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES (10, 1, 'COBRANZA', '2026-01-10', 'Cobranza', 'TRX001', 900, 0, 900, 'CONFIRMADA', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_conciliacion(conexion=con, tolerancia_importe=1.0)

    assert resultado["resumen"]["sugerencias"] == 0
    assert resultado["resumen"]["pares_descartados_importe"] == 1


def test_detecta_sugerencias_ambiguas() -> None:
    con = _crear_conexion_base()
    _insertar_par_base(con)
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
            (id, empresa_id, tipo_operacion, origen_modulo, fecha_operacion, tercero_nombre, descripcion, referencia_externa, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES
            (11, 1, 'COBRANZA', 'COBRANZAS', '2026-01-10', 'Gomez SRL', 'Cobranza cliente Gomez TRX001 duplicada', 'TRX001', 1000, 0, 1000, 'CONFIRMADA', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_conciliacion(conexion=con, tolerancia_importe=0.01)

    assert resultado["resumen"]["sugerencias"] == 2
    assert resultado["resumen"]["sugerencias_ambiguas"] == 2
    assert all(sug["accion_sugerida"] == "REVISAR_CANDIDATOS_AMBIGUOS" for sug in resultado["sugerencias"])
    assert any(alerta["codigo"] == "CONCILIACION_PARAM_SUGERENCIAS_AMBIGUAS" for alerta in resultado["alertas"])


def test_detecta_par_con_conciliacion_activa_y_no_lo_sugiere_para_aceptacion() -> None:
    con = _crear_conexion_base()
    _insertar_par_base(con)
    con.execute(
        """
        INSERT INTO bancos_conciliaciones
            (id, empresa_id, movimiento_banco_id, tipo_conciliacion, estado)
        VALUES (100, 1, 1, 'TESORERIA_OPERACION', 'PARCIAL')
        """
    )
    con.execute(
        """
        INSERT INTO bancos_conciliaciones_detalle
            (id, empresa_id, conciliacion_id, movimiento_banco_id, entidad_tabla, entidad_id, importe_imputado)
        VALUES (101, 1, 100, 1, 'tesoreria_operaciones', 10, 500)
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_conciliacion(conexion=con, tolerancia_importe=0.01)

    assert resultado["resumen"]["sugerencias_con_par_activo"] == 1
    assert resultado["sugerencias"][0]["par_conciliacion_activa"] is True
    assert resultado["sugerencias"][0]["accion_sugerida"] == "NO_SUGERIR_PAR_YA_CONCILIADO"
    assert any(alerta["codigo"] == "CONCILIACION_PARAM_PAR_YA_ACTIVO" for alerta in resultado["alertas"])


def test_ignora_movimientos_y_operaciones_ya_conciliadas_o_anuladas() -> None:
    con = _crear_conexion_base()
    con.execute(
        """
        INSERT INTO bancos_movimientos
            (id, empresa_id, fecha, concepto, referencia, importe, importe_conciliado, importe_pendiente, estado_conciliacion)
        VALUES (1, 1, '2026-01-10', 'Transferencia', 'TRX001', 1000, 1000, 0, 'CONCILIADO')
        """
    )
    con.execute(
        """
        INSERT INTO tesoreria_operaciones
            (id, empresa_id, tipo_operacion, fecha_operacion, descripcion, referencia_externa, importe, importe_conciliado, importe_pendiente, estado, estado_conciliacion)
        VALUES (10, 1, 'COBRANZA', '2026-01-10', 'Cobranza', 'TRX001', 1000, 0, 1000, 'ANULADA', 'PENDIENTE')
        """
    )
    con.commit()

    resultado = analizar_parametrizacion_conciliacion(conexion=con)

    assert resultado["resumen"]["movimientos_bancarios_pendientes"] == 0
    assert resultado["resumen"]["operaciones_tesoreria_pendientes"] == 0
    assert resultado["resumen"]["sugerencias"] == 0


def test_detecta_tablas_requeridas_faltantes_sin_inicializar() -> None:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    antes = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]

    resultado = analizar_parametrizacion_conciliacion(conexion=con)

    despues = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    codigos = {alerta["codigo"] for alerta in resultado["alertas"]}
    assert antes == despues == 0
    assert resultado["estado"] == "CRITICO"
    assert "CONCILIACION_PARAM_TABLA_REQUERIDA_INEXISTENTE" in codigos
    assert resultado["solo_lectura"] is True


def test_helpers_resumen_alertas_y_sugerencias() -> None:
    con = _crear_conexion_base()
    _insertar_par_base(con)

    resumen = obtener_resumen_parametrizacion_conciliacion(conexion=con)
    alertas = obtener_alertas_parametrizacion_conciliacion(conexion=con)
    sugerencias = obtener_sugerencias_conciliacion_asistida(conexion=con)

    assert isinstance(resumen, dict)
    assert isinstance(alertas, list)
    assert isinstance(sugerencias, list)
    assert resumen["sugerencias"] == 1
    assert sugerencias[0]["confianza"] == "ALTA"

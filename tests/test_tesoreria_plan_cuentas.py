import sqlite3

import pandas as pd

import services.tesoreria_service as tesoreria_service
from services.coherencia_contable_service import diagnosticar_comportamientos_configurados


# ======================================================
# HELPERS
# ======================================================

def _instalar_db_temporal(monkeypatch, tmp_path):
    db_path = tmp_path / "tesoreria_plan_ff.sqlite"

    def conectar_test():
        return sqlite3.connect(db_path)

    def ejecutar_query_test(sql, params=(), fetch=False):
        conn = conectar_test()
        try:
            if fetch:
                return pd.read_sql_query(sql, conn, params=params)

            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur

        finally:
            conn.close()

    monkeypatch.setattr(tesoreria_service, "conectar", conectar_test)
    monkeypatch.setattr(tesoreria_service, "ejecutar_query", ejecutar_query_test)
    monkeypatch.setattr(tesoreria_service, "inicializar_tesoreria", lambda: True)

    conn = conectar_test()
    try:
        conn.executescript(
            """
            CREATE TABLE tesoreria_cuentas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                tipo_cuenta TEXT NOT NULL,
                nombre TEXT NOT NULL,
                entidad TEXT,
                numero_cuenta TEXT,
                moneda TEXT DEFAULT 'ARS',
                cuenta_contable_codigo TEXT,
                cuenta_contable_nombre TEXT,
                activo INTEGER DEFAULT 1,
                observacion TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT
            );

            CREATE TABLE tesoreria_auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                usuario_id INTEGER,
                accion TEXT,
                entidad TEXT,
                entidad_id TEXT,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                motivo TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE plan_cuentas_empresa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER NOT NULL DEFAULT 1,
                codigo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                imputable INTEGER NOT NULL DEFAULT 1,
                estado TEXT NOT NULL DEFAULT 'ACTIVA',
                cuenta_maestro_id INTEGER,
                uso_operativo_sistema TEXT
            );

            CREATE TABLE plan_cuentas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER,
                codigo TEXT,
                nombre TEXT,
                comportamiento_contable TEXT,
                activo INTEGER DEFAULT 1
            );
            """
        )
        conn.commit()

    finally:
        conn.close()

    return db_path


def _insertar_cuenta_tesoreria(db_path, tipo_cuenta, nombre, codigo="", cuenta_nombre=""):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
            VALUES (1, ?, ?, ?, ?, 1)
            """,
            (tipo_cuenta, nombre, codigo, cuenta_nombre),
        )
        conn.commit()
        return int(cur.lastrowid)

    finally:
        conn.close()


def _insertar_cuenta_plan(db_path, codigo, nombre, uso, imputable=1, estado="ACTIVA"):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO plan_cuentas_empresa
            (empresa_id, codigo, nombre, imputable, estado, uso_operativo_sistema)
            VALUES (1, ?, ?, ?, ?, ?)
            """,
            (codigo, nombre, imputable, estado, uso),
        )
        cur.execute(
            """
            INSERT INTO plan_cuentas
            (empresa_id, codigo, nombre, comportamiento_contable, activo)
            VALUES (1, ?, ?, ?, 1)
            """,
            (
                codigo,
                nombre,
                "CAJA" if uso in {"CAJA", "CAJA_GENERAL"} else "BANCO",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)

    finally:
        conn.close()


# ======================================================
# TESTS
# ======================================================

def test_vincular_cuenta_tesoreria_a_plan_empresa_actualiza_codigo_nombre_y_audita(monkeypatch, tmp_path):
    db_path = _instalar_db_temporal(monkeypatch, tmp_path)
    cuenta_tesoreria_id = _insertar_cuenta_tesoreria(db_path, "CAJA", "Caja principal")
    _insertar_cuenta_plan(db_path, "1.1.01.01", "Caja", "CAJA_GENERAL")

    resultado = tesoreria_service.vincular_cuenta_tesoreria_a_plan_empresa(
        cuenta_tesoreria_id=cuenta_tesoreria_id,
        empresa_id=1,
        cuenta_codigo="1.1.01.01",
        usuario_id=7,
        motivo="Vinculación inicial de Caja principal al Plan Maestro FF.",
    )

    assert resultado["ok"] is True
    assert resultado["actualizada"] is True
    assert resultado["cuenta_contable_codigo"] == "1.1.01.01"
    assert resultado["cuenta_contable_nombre"] == "Caja"

    cuenta = tesoreria_service.obtener_cuenta_tesoreria(cuenta_tesoreria_id, empresa_id=1)
    assert cuenta["cuenta_contable_codigo"] == "1.1.01.01"
    assert cuenta["cuenta_contable_nombre"] == "Caja"

    conn = sqlite3.connect(db_path)
    try:
        auditorias = conn.execute(
            """
            SELECT accion, entidad, entidad_id, motivo
            FROM tesoreria_auditoria
            WHERE entidad = 'tesoreria_cuentas'
            """
        ).fetchall()
    finally:
        conn.close()

    assert len(auditorias) == 1
    assert auditorias[0][0] == "VINCULAR_CUENTA_CONTABLE"
    assert auditorias[0][1] == "tesoreria_cuentas"
    assert auditorias[0][2] == str(cuenta_tesoreria_id)
    assert "Plan Maestro FF" in auditorias[0][3]


def test_no_permite_vincular_tesoreria_a_cuenta_no_imputable(monkeypatch, tmp_path):
    db_path = _instalar_db_temporal(monkeypatch, tmp_path)
    cuenta_tesoreria_id = _insertar_cuenta_tesoreria(db_path, "BANCO", "Banco principal")
    _insertar_cuenta_plan(db_path, "1.1.02", "Banco cuenta corriente", "BANCO_CUENTA_CORRIENTE", imputable=0)

    resultado = tesoreria_service.vincular_cuenta_tesoreria_a_plan_empresa(
        cuenta_tesoreria_id=cuenta_tesoreria_id,
        empresa_id=1,
        cuenta_codigo="1.1.02",
        motivo="Intento de vincular cuenta agrupadora.",
    )

    assert resultado["ok"] is False
    assert "no es imputable" in resultado["mensaje"]

    cuenta = tesoreria_service.obtener_cuenta_tesoreria(cuenta_tesoreria_id, empresa_id=1)
    assert cuenta["cuenta_contable_codigo"] in (None, "")


def test_listar_cuentas_tesoreria_sin_cuenta_contable_solo_devuelve_activas_sin_codigo(monkeypatch, tmp_path):
    db_path = _instalar_db_temporal(monkeypatch, tmp_path)
    _insertar_cuenta_tesoreria(db_path, "CAJA", "Caja principal")
    _insertar_cuenta_tesoreria(db_path, "BANCO", "Banco principal", "1.1.02", "Banco cuenta corriente")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO tesoreria_cuentas
            (empresa_id, tipo_cuenta, nombre, cuenta_contable_codigo, cuenta_contable_nombre, activo)
            VALUES (1, 'CAJA', 'Caja vieja inactiva', '', '', 0)
            """
        )
        conn.commit()
    finally:
        conn.close()

    pendientes = tesoreria_service.listar_cuentas_tesoreria_sin_cuenta_contable(empresa_id=1)

    assert list(pendientes["nombre"]) == ["Caja principal"]


def test_vinculacion_cierra_alerta_tesoreria_sin_cuenta_contable_en_control_consistencia(monkeypatch, tmp_path):
    db_path = _instalar_db_temporal(monkeypatch, tmp_path)
    caja_id = _insertar_cuenta_tesoreria(db_path, "CAJA", "Caja principal")
    banco_id = _insertar_cuenta_tesoreria(db_path, "BANCO", "Banco principal")

    _insertar_cuenta_plan(db_path, "1.1.01.01", "Caja", "CAJA_GENERAL")
    _insertar_cuenta_plan(db_path, "1.1.02.01", "Banco Macro Cta. Cte.", "BANCO_CUENTA_CORRIENTE")

    resultado_caja = tesoreria_service.vincular_cuenta_tesoreria_a_plan_empresa(
        cuenta_tesoreria_id=caja_id,
        empresa_id=1,
        cuenta_codigo="1.1.01.01",
        motivo="Vincular Caja principal al Plan Maestro FF.",
    )
    resultado_banco = tesoreria_service.vincular_cuenta_tesoreria_a_plan_empresa(
        cuenta_tesoreria_id=banco_id,
        empresa_id=1,
        cuenta_codigo="1.1.02.01",
        motivo="Vincular Banco principal al Plan Maestro FF.",
    )

    assert resultado_caja["ok"] is True
    assert resultado_banco["ok"] is True

    conn = sqlite3.connect(db_path)
    try:
        diagnosticos = diagnosticar_comportamientos_configurados(empresa_id=1, conn=conn)
    finally:
        conn.close()

    codigos = {item["codigo"] for item in diagnosticos}

    assert "TESORERIA_CUENTAS_SIN_CUENTA_CONTABLE" not in codigos
    assert "TESORERIA_CAJAS_SIN_COMPORTAMIENTO_CAJA" not in codigos
    assert "TESORERIA_BANCOS_SIN_COMPORTAMIENTO_BANCO" not in codigos
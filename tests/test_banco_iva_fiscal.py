import sqlite3

import pandas as pd

import services.bancos_operaciones_service as bancos_ops
import services.iva_movimientos_fiscales_service as iva_movs


# ======================================================
# Helpers de base temporal
# ======================================================

def _patch_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_banco_iva_fiscal.db"

    def conectar_test():
        return sqlite3.connect(db_path)

    def ejecutar_query_test(query, params=(), fetch=False):
        conn = conectar_test()

        try:
            if fetch:
                return pd.read_sql_query(query, conn, params=params)

            cur = conn.cursor()
            cur.execute(query, params or ())
            conn.commit()
            return pd.DataFrame()

        finally:
            conn.close()

    monkeypatch.setattr(iva_movs, "conectar", conectar_test)
    monkeypatch.setattr(iva_movs, "ejecutar_query", ejecutar_query_test)
    monkeypatch.setattr(bancos_ops, "conectar", conectar_test)
    monkeypatch.setattr(bancos_ops, "ejecutar_query", ejecutar_query_test)

    return db_path


def _crear_tablas_banco_minimas():
    conn = bancos_ops.conectar()

    try:
        conn.execute(
            """
            CREATE TABLE bancos_grupos_fiscales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id INTEGER DEFAULT 1,
                importacion_id INTEGER,
                movimiento_banco_id INTEGER,
                fecha TEXT,
                referencia TEXT,
                causal TEXT,
                banco TEXT,
                nombre_cuenta TEXT,
                concepto TEXT,
                base_gasto_bancario REAL DEFAULT 0,
                iva_credito_21 REAL DEFAULT 0,
                iva_credito_105 REAL DEFAULT 0,
                iva_sin_base REAL DEFAULT 0,
                percepcion_iva REAL DEFAULT 0,
                percepcion_iibb REAL DEFAULT 0,
                impuesto_debitos_creditos REAL DEFAULT 0,
                total_banco REAL DEFAULT 0,
                alicuota_detectada TEXT,
                confianza TEXT,
                estado_revision TEXT,
                motivo TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insertar_grupo_fiscal_bancario(
    fecha="2026-05-10",
    iva_credito_21=210.0,
    percepcion_iva=50.0,
    percepcion_iibb=30.0,
    impuesto_debitos_creditos=15.0,
):
    conn = bancos_ops.conectar()

    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bancos_grupos_fiscales
            (
                empresa_id,
                importacion_id,
                movimiento_banco_id,
                fecha,
                referencia,
                causal,
                banco,
                nombre_cuenta,
                concepto,
                base_gasto_bancario,
                iva_credito_21,
                iva_credito_105,
                iva_sin_base,
                percepcion_iva,
                percepcion_iibb,
                impuesto_debitos_creditos,
                total_banco,
                alicuota_detectada,
                confianza,
                estado_revision,
                motivo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                10,
                100,
                fecha,
                "REF-001",
                "COMISION",
                "Banco Macro",
                "Cuenta corriente principal",
                "COMISION PAQUETE BANCO",
                1000.0,
                iva_credito_21,
                0.0,
                0.0,
                percepcion_iva,
                percepcion_iibb,
                impuesto_debitos_creditos,
                1290.0,
                "21%",
                "Alta",
                "PROPUESTO",
                "Grupo fiscal de prueba",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def _setup(monkeypatch, tmp_path):
    _patch_db(monkeypatch, tmp_path)
    iva_movs.asegurar_estructura_iva_movimientos_fiscales()
    _crear_tablas_banco_minimas()


# ======================================================
# Tests
# ======================================================

def test_preview_banco_iva_detecta_conceptos_fiscales(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    grupo_id = _insertar_grupo_fiscal_bancario()

    preview = bancos_ops.obtener_vista_previa_movimientos_fiscales_banco_iva(empresa_id=1)

    assert not preview.empty
    assert set(preview["tipo_concepto"].tolist()) == {
        "IVA_CREDITO",
        "PERCEPCION_IVA",
        "PERCEPCION_IIBB_INFORMATIVA",
        "OTRO",
    }
    assert set(preview["grupo_fiscal_id"].astype(int).tolist()) == {grupo_id}
    assert preview["ya_generado_iva"].eq(False).all()


def test_generar_confirmado_no_incluido_no_impacta_posicion_iva(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    grupo_id = _insertar_grupo_fiscal_bancario()

    selecciones = [
        {"grupo_fiscal_id": grupo_id, "tipo_concepto": "IVA_CREDITO"},
        {"grupo_fiscal_id": grupo_id, "tipo_concepto": "PERCEPCION_IVA"},
    ]

    resultado = bancos_ops.generar_movimientos_fiscales_banco_iva(
        empresa_id=1,
        selecciones=selecciones,
        estado="CONFIRMADO",
        incluido_en_posicion=False,
        motivo_no_inclusion="No declarado en Portal IVA del período.",
        usuario="tester",
    )

    assert resultado["ok"] is True
    assert resultado["creados"] == 2

    impacto = iva_movs.obtener_impacto_posicion_iva_periodo(
        empresa_id=1,
        anio=2026,
        mes=5,
    )

    assert impacto["credito_fiscal_computable_adicional"] == 0.0
    assert impacto["percepcion_iva_adicional"] == 0.0

    movimientos = iva_movs.listar_movimientos_fiscales(
        empresa_id=1,
        anio=2026,
        mes=5,
        incluir_anulados=True,
    )

    assert len(movimientos) == 2
    assert movimientos["estado"].eq("CONFIRMADO").all()
    assert movimientos["incluido_en_posicion"].astype(int).eq(0).all()


def test_generar_confirmado_incluido_impacta_posicion_iva(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    grupo_id = _insertar_grupo_fiscal_bancario()

    resultado = bancos_ops.generar_movimientos_fiscales_banco_iva(
        empresa_id=1,
        selecciones=[
            {"grupo_fiscal_id": grupo_id, "tipo_concepto": "IVA_CREDITO"},
            {"grupo_fiscal_id": grupo_id, "tipo_concepto": "PERCEPCION_IVA"},
        ],
        estado="CONFIRMADO",
        incluido_en_posicion=True,
        incluido_en_portal_iva=True,
        motivo_no_inclusion="Incluido y declarado en Portal IVA.",
        usuario="tester",
    )

    assert resultado["ok"] is True
    assert resultado["creados"] == 2

    impacto = iva_movs.obtener_impacto_posicion_iva_periodo(
        empresa_id=1,
        anio=2026,
        mes=5,
    )

    assert impacto["credito_fiscal_computable_adicional"] == 210.0
    assert impacto["percepcion_iva_adicional"] == 50.0


def test_no_duplica_mismo_grupo_y_tipo_concepto(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    grupo_id = _insertar_grupo_fiscal_bancario()

    seleccion = [{"grupo_fiscal_id": grupo_id, "tipo_concepto": "IVA_CREDITO"}]

    primero = bancos_ops.generar_movimientos_fiscales_banco_iva(
        empresa_id=1,
        selecciones=seleccion,
        estado="CONFIRMADO",
        incluido_en_posicion=True,
        usuario="tester",
    )

    segundo = bancos_ops.generar_movimientos_fiscales_banco_iva(
        empresa_id=1,
        selecciones=seleccion,
        estado="CONFIRMADO",
        incluido_en_posicion=True,
        usuario="tester",
    )

    assert primero["ok"] is True
    assert primero["creados"] == 1
    assert segundo["ok"] is True
    assert segundo["creados"] == 0
    assert segundo["omitidos"] == 1

    movimientos = iva_movs.listar_movimientos_fiscales(
        empresa_id=1,
        anio=2026,
        mes=5,
        tipo_concepto="IVA_CREDITO",
        incluir_anulados=True,
    )

    assert len(movimientos) == 1
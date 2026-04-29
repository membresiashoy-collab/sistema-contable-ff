import sqlite3

import pandas as pd
import pytest

from services import tesoreria_service


@pytest.fixture()
def db_temporal(tmp_path, monkeypatch):
    db_path = tmp_path / "tesoreria_test.sqlite"

    def conectar_temporal():
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def ejecutar_query_temporal(sql, params=(), fetch=False):
        conn = conectar_temporal()

        try:
            if fetch:
                return pd.read_sql_query(sql, conn, params=params)

            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur

        finally:
            conn.close()

    monkeypatch.setattr(tesoreria_service, "conectar", conectar_temporal)
    monkeypatch.setattr(tesoreria_service, "ejecutar_query", ejecutar_query_temporal)

    tesoreria_service.inicializar_tesoreria()

    return db_path


def test_crear_cuenta_tesoreria_y_medios_basicos(db_temporal):
    resultado = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="CAJA",
        nombre="Caja principal",
        moneda="ARS",
        cuenta_contable_codigo="1.1.1.01",
        cuenta_contable_nombre="Caja",
    )

    assert resultado["ok"] is True
    assert resultado["creada"] is True
    assert resultado["cuenta_id"] > 0

    repetida = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="CAJA",
        nombre="Caja principal",
        moneda="ARS",
    )

    assert repetida["ok"] is True
    assert repetida["creada"] is False
    assert repetida["cuenta_id"] == resultado["cuenta_id"]

    medios = tesoreria_service.asegurar_medios_pago_basicos(empresa_id=1)

    assert not medios.empty
    assert "EFECTIVO" in medios["codigo"].tolist()
    assert "TRANSFERENCIA" in medios["codigo"].tolist()


def test_registrar_operacion_cobranza_pendiente_conciliacion(db_temporal):
    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="CAJA",
        nombre="Caja principal",
    )

    medio_id = tesoreria_service.obtener_medio_pago_id(
        empresa_id=1,
        codigo="EFECTIVO",
    )

    resultado = tesoreria_service.registrar_operacion_tesoreria(
        empresa_id=1,
        tipo_operacion="COBRANZA",
        subtipo="COBRO_CLIENTE",
        fecha_operacion="2026-01-10",
        fecha_contable="2026-01-10",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        medio_pago_id=medio_id,
        tercero_tipo="CLIENTE",
        tercero_nombre="Cliente Demo",
        tercero_cuit="20111111112",
        descripcion="Cobranza en efectivo de cliente",
        referencia_externa="REC-0001",
        importe=1000,
        origen_modulo="COBRANZAS",
        origen_tabla="cobranzas",
        origen_id=1,
    )

    assert resultado["ok"] is True
    assert resultado["creada"] is True
    assert resultado["duplicada"] is False

    operacion = tesoreria_service.obtener_operacion_tesoreria(
        resultado["operacion_id"],
        empresa_id=1,
    )

    assert operacion["tipo_operacion"] == "COBRANZA"
    assert operacion["estado"] == "CONFIRMADA"
    assert operacion["estado_conciliacion"] == "PENDIENTE"
    assert round(float(operacion["importe_pendiente"]), 2) == 1000.00

    pendientes = tesoreria_service.listar_operaciones_pendientes_conciliacion(
        empresa_id=1,
        cuenta_tesoreria_id=cuenta["cuenta_id"],
    )

    assert len(pendientes) == 1


def test_evitar_duplicado_por_fingerprint(db_temporal):
    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="BANCO",
        nombre="Banco Macro - Cuenta corriente principal",
    )

    fingerprint = "operacion-unica-demo"

    primera = tesoreria_service.registrar_operacion_tesoreria(
        empresa_id=1,
        tipo_operacion="PAGO",
        fecha_operacion="2026-01-11",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        tercero_tipo="PROVEEDOR",
        tercero_nombre="Proveedor Demo",
        tercero_cuit="30777777778",
        descripcion="Pago proveedor",
        referencia_externa="OP-0001",
        importe=-5000,
        origen_modulo="PAGOS",
        origen_tabla="pagos",
        origen_id=10,
        fingerprint=fingerprint,
    )

    segunda = tesoreria_service.registrar_operacion_tesoreria(
        empresa_id=1,
        tipo_operacion="PAGO",
        fecha_operacion="2026-01-11",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        tercero_tipo="PROVEEDOR",
        tercero_nombre="Proveedor Demo",
        tercero_cuit="30777777778",
        descripcion="Pago proveedor repetido",
        referencia_externa="OP-0001",
        importe=-5000,
        origen_modulo="PAGOS",
        origen_tabla="pagos",
        origen_id=10,
        fingerprint=fingerprint,
    )

    assert primera["creada"] is True
    assert segunda["creada"] is False
    assert segunda["duplicada"] is True
    assert segunda["operacion_id"] == primera["operacion_id"]


def test_anular_operacion_con_motivo(db_temporal):
    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="CAJA",
        nombre="Caja principal",
    )

    resultado = tesoreria_service.registrar_operacion_tesoreria(
        empresa_id=1,
        tipo_operacion="CAJA",
        subtipo="EGRESO_CAJA",
        fecha_operacion="2026-01-12",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        descripcion="Egreso de caja cargado por error",
        importe=-250,
        origen_modulo="CAJA",
    )

    sin_motivo = tesoreria_service.anular_operacion_tesoreria(
        resultado["operacion_id"],
        empresa_id=1,
        motivo="",
    )

    assert sin_motivo["ok"] is False

    anulacion = tesoreria_service.anular_operacion_tesoreria(
        resultado["operacion_id"],
        empresa_id=1,
        motivo="Error humano de carga",
    )

    assert anulacion["ok"] is True
    assert anulacion["anulada"] is True

    operacion = tesoreria_service.obtener_operacion_tesoreria(
        resultado["operacion_id"],
        empresa_id=1,
    )

    assert operacion["estado"] == "ANULADA"
    assert operacion["motivo_anulacion"] == "Error humano de carga"


def test_no_anular_conciliada_sin_permiso_administrador(db_temporal):
    cuenta = tesoreria_service.crear_cuenta_tesoreria(
        empresa_id=1,
        tipo_cuenta="BANCO",
        nombre="Banco Demo",
    )

    resultado = tesoreria_service.registrar_operacion_tesoreria(
        empresa_id=1,
        tipo_operacion="COBRANZA",
        fecha_operacion="2026-01-13",
        cuenta_tesoreria_id=cuenta["cuenta_id"],
        descripcion="Cobranza conciliada",
        importe=1500,
        origen_modulo="COBRANZAS",
    )

    conciliacion = tesoreria_service.actualizar_estado_conciliacion_operacion(
        resultado["operacion_id"],
        empresa_id=1,
        importe_conciliado=1500,
    )

    assert conciliacion["ok"] is True
    assert conciliacion["estado_conciliacion"] == "CONCILIADA"

    anulacion = tesoreria_service.anular_operacion_tesoreria(
        resultado["operacion_id"],
        empresa_id=1,
        motivo="Intento de anulación sin desconciliar",
        permitir_conciliada=False,
    )

    assert anulacion["ok"] is False

    anulacion_admin = tesoreria_service.anular_operacion_tesoreria(
        resultado["operacion_id"],
        empresa_id=1,
        motivo="Anulación autorizada por administrador",
        permitir_conciliada=True,
    )

    assert anulacion_admin["ok"] is True
    assert anulacion_admin["anulada"] is True
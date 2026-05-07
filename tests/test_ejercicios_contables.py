import importlib

import pytest

import config
import database


def preparar_db_temporal(monkeypatch, tmp_path):
    ruta = tmp_path / "test_sistema_contable.db"

    monkeypatch.setattr(config, "DB_PATH", str(ruta), raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(ruta), raising=False)

    database.init_db()

    from services import ejercicios_contables_service as svc
    svc.migrar_ejercicios_contables()

    return svc


def test_crear_ejercicio_contable_valido(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    resultado = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
        usuario="tester",
    )

    assert resultado["ok"] is True
    assert resultado["ejercicio_id"] > 0

    ejercicios = svc.listar_ejercicios_contables(empresa_id=1)
    assert len(ejercicios) == 1
    assert ejercicios.iloc[0]["nombre"] == "Ejercicio 2025"
    assert ejercicios.iloc[0]["estado"] == "ABIERTO"


def test_no_permite_solapamiento_de_ejercicios(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    primero = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
    )

    assert primero["ok"] is True

    solapado = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-06-01",
        fecha_cierre="2026-05-31",
        nombre="Ejercicio solapado",
    )

    assert solapado["ok"] is False
    assert "superpone" in solapado["mensaje"]


def test_permite_ejercicios_consecutivos(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    primero = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
    )

    segundo = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2026-01-01",
        fecha_cierre="2026-12-31",
        nombre="Ejercicio 2026",
    )

    assert primero["ok"] is True
    assert segundo["ok"] is True

    ejercicios = svc.listar_ejercicios_contables(empresa_id=1)
    assert len(ejercicios) == 2


def test_obtener_ejercicio_para_fecha(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
    )

    ejercicio = svc.obtener_ejercicio_para_fecha(1, "2025-08-15")

    assert ejercicio is not None
    assert ejercicio["nombre"] == "Ejercicio 2025"

    fuera = svc.obtener_ejercicio_para_fecha(1, "2026-01-15")
    assert fuera is None


def test_cierre_bloquea_fechas_del_ejercicio(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    creado = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
    )

    ejercicio_id = creado["ejercicio_id"]

    cierre = svc.cerrar_ejercicio_contable(
        ejercicio_id=ejercicio_id,
        motivo="Cierre aprobado",
        usuario="tester",
    )

    assert cierre["ok"] is True
    assert cierre["ejercicio"]["estado"] == "CERRADO"
    assert cierre["ejercicio"]["bloqueo_hasta"] == "2025-12-31"

    validacion = svc.validar_fecha_operativa_contable(1, "2025-06-30")
    assert validacion["ok"] is False
    assert validacion["bloqueada"] is True


def test_reapertura_habilita_fechas(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    creado = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
    )

    ejercicio_id = creado["ejercicio_id"]

    svc.cerrar_ejercicio_contable(
        ejercicio_id=ejercicio_id,
        motivo="Cierre aprobado",
        usuario="tester",
    )

    reapertura = svc.reabrir_ejercicio_contable(
        ejercicio_id=ejercicio_id,
        motivo="Corrección posterior",
        usuario="tester",
    )

    assert reapertura["ok"] is True
    assert reapertura["ejercicio"]["estado"] == "REABIERTO"
    assert reapertura["ejercicio"]["bloqueo_hasta"] is None

    validacion = svc.validar_fecha_operativa_contable(1, "2025-06-30")
    assert validacion["ok"] is True
    assert validacion["bloqueada"] is False


def test_anular_ejercicio_sin_movimientos(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    creado = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
    )

    anulacion = svc.anular_ejercicio_contable(
        ejercicio_id=creado["ejercicio_id"],
        motivo="Carga errónea de ejercicio",
        usuario="tester",
    )

    assert anulacion["ok"] is True
    assert anulacion["ejercicio"]["estado"] == "ANULADO"

    ejercicios = svc.listar_ejercicios_contables(empresa_id=1)
    assert ejercicios.empty


def test_rango_filtro_periodo(monkeypatch, tmp_path):
    svc = preparar_db_temporal(monkeypatch, tmp_path)

    creado = svc.crear_ejercicio_contable(
        empresa_id=1,
        fecha_inicio="2025-01-01",
        fecha_cierre="2025-12-31",
        nombre="Ejercicio 2025",
    )

    rango = svc.obtener_rango_filtro_periodo(
        empresa_id=1,
        modo="EJERCICIO",
        ejercicio_id=creado["ejercicio_id"],
    )

    assert rango["ok"] is True
    assert rango["fecha_desde"] == "2025-01-01"
    assert rango["fecha_hasta"] == "2025-12-31"

    manual = svc.obtener_rango_filtro_periodo(
        empresa_id=1,
        modo="RANGO_MANUAL",
        fecha_desde="2025-03-01",
        fecha_hasta="2025-03-31",
    )

    assert manual["ok"] is True
    assert manual["fecha_desde"] == "2025-03-01"
    assert manual["fecha_hasta"] == "2025-03-31"
import pytest

import database
from services import iva_movimientos_fiscales_service as iva_mov_fiscales


@pytest.fixture()
def db_temporal(tmp_path, monkeypatch):
    """
    Aísla las pruebas en una base SQLite temporal.

    No usa la base real del proyecto.
    No modifica datos reales.
    """
    db_path = tmp_path / "test_iva_movimientos_fiscales.db"

    monkeypatch.setattr(database, "DB_PATH", str(db_path), raising=False)

    iva_mov_fiscales.asegurar_estructura_iva_movimientos_fiscales()

    yield db_path


def test_estructura_iva_movimientos_fiscales_se_crea(db_temporal):
    assert iva_mov_fiscales.estructura_iva_movimientos_fiscales_existe() is True

    movimientos = iva_mov_fiscales.listar_movimientos_fiscales(
        empresa_id=1,
        incluir_anulados=True,
    )

    assert movimientos.empty


def test_registrar_movimiento_confirmado_impacta_en_totales_periodo(db_temporal):
    movimiento = iva_mov_fiscales.registrar_movimiento_fiscal(
        empresa_id=1,
        fecha="15/12/2025",
        origen="BANCO",
        tipo_concepto="IVA_CREDITO",
        descripcion="Comisión bancaria con IVA computable",
        contraparte="Banco de prueba",
        cuit="30000000007",
        neto_gravado=1000,
        credito_fiscal_computable=210,
        percepcion_iva=50,
        total=1260,
        estado=iva_mov_fiscales.ESTADO_CONFIRMADO,
        usuario="pytest",
    )

    assert movimiento is not None
    assert movimiento["estado"] == iva_mov_fiscales.ESTADO_CONFIRMADO
    assert movimiento["origen"] == "BANCO"
    assert movimiento["tipo_concepto"] == "IVA_CREDITO"
    assert movimiento["anio"] == 2025
    assert movimiento["mes"] == 12
    assert movimiento["periodo"] == "2025-12"
    assert movimiento["credito_fiscal_computable"] == 210
    assert movimiento["percepcion_iva"] == 50

    totales = iva_mov_fiscales.obtener_totales_movimientos_fiscales_periodo(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert totales["cantidad_movimientos_fiscales"] == 1
    assert totales["neto_gravado"] == 1000
    assert totales["credito_fiscal_computable"] == 210
    assert totales["percepcion_iva"] == 50
    assert totales["total"] == 1260

    impacto = iva_mov_fiscales.obtener_impacto_posicion_iva_periodo(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert impacto["cantidad_movimientos_fiscales"] == 1
    assert impacto["credito_fiscal_computable_adicional"] == 210
    assert impacto["percepcion_iva_adicional"] == 50
    assert impacto["deducciones_saldo_preliminar"] == 50


def test_movimiento_borrador_no_impacta_hasta_confirmarse(db_temporal):
    movimiento = iva_mov_fiscales.registrar_movimiento_fiscal(
        empresa_id=1,
        fecha="20/12/2025",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Ajuste técnico de débito fiscal en borrador",
        iva_debito=100,
        estado=iva_mov_fiscales.ESTADO_BORRADOR,
        usuario="pytest",
    )

    assert movimiento["estado"] == iva_mov_fiscales.ESTADO_BORRADOR

    totales_confirmados = iva_mov_fiscales.obtener_totales_movimientos_fiscales_periodo(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert totales_confirmados["cantidad_movimientos_fiscales"] == 0
    assert totales_confirmados["iva_debito"] == 0

    totales_con_borradores = iva_mov_fiscales.obtener_totales_movimientos_fiscales_periodo(
        empresa_id=1,
        anio=2025,
        mes=12,
        incluir_borradores=True,
    )

    assert totales_con_borradores["cantidad_movimientos_fiscales"] == 1
    assert totales_con_borradores["iva_debito"] == 100

    confirmado = iva_mov_fiscales.confirmar_movimiento_fiscal(
        movimiento_id=movimiento["id"],
        usuario="pytest",
    )

    assert confirmado["estado"] == iva_mov_fiscales.ESTADO_CONFIRMADO

    totales_confirmados_post = iva_mov_fiscales.obtener_totales_movimientos_fiscales_periodo(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert totales_confirmados_post["cantidad_movimientos_fiscales"] == 1
    assert totales_confirmados_post["iva_debito"] == 100


def test_anular_movimiento_no_borra_y_deja_de_impactar(db_temporal):
    movimiento = iva_mov_fiscales.registrar_movimiento_fiscal(
        empresa_id=1,
        fecha="22/12/2025",
        origen="RETENCION",
        tipo_concepto="RETENCION_IVA",
        descripcion="Retención IVA sufrida",
        retencion_iva=80,
        estado=iva_mov_fiscales.ESTADO_CONFIRMADO,
        usuario="pytest",
    )

    totales_antes = iva_mov_fiscales.obtener_totales_movimientos_fiscales_periodo(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert totales_antes["cantidad_movimientos_fiscales"] == 1
    assert totales_antes["retencion_iva"] == 80

    anulado = iva_mov_fiscales.anular_movimiento_fiscal(
        movimiento_id=movimiento["id"],
        motivo="Prueba de anulación lógica",
        usuario="pytest",
    )

    assert anulado["estado"] == iva_mov_fiscales.ESTADO_ANULADO
    assert anulado["motivo_anulacion"] == "Prueba de anulación lógica"

    totales_despues = iva_mov_fiscales.obtener_totales_movimientos_fiscales_periodo(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert totales_despues["cantidad_movimientos_fiscales"] == 0
    assert totales_despues["retencion_iva"] == 0

    listado_sin_anulados = iva_mov_fiscales.listar_movimientos_fiscales(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert listado_sin_anulados.empty

    listado_con_anulados = iva_mov_fiscales.listar_movimientos_fiscales(
        empresa_id=1,
        anio=2025,
        mes=12,
        incluir_anulados=True,
    )

    assert len(listado_con_anulados) == 1
    assert listado_con_anulados.iloc[0]["estado"] == iva_mov_fiscales.ESTADO_ANULADO

    eventos = iva_mov_fiscales.listar_eventos_movimiento(movimiento["id"])
    eventos_lista = eventos["evento"].tolist()

    assert "CREACION" in eventos_lista
    assert "CONFIRMACION" in eventos_lista
    assert "ANULACION" in eventos_lista


def test_resumen_por_origen_y_tipo_concepto(db_temporal):
    iva_mov_fiscales.registrar_movimiento_fiscal(
        empresa_id=1,
        fecha="01/12/2025",
        origen="BANCO",
        tipo_concepto="IVA_CREDITO",
        descripcion="Comisión bancaria 1",
        credito_fiscal_computable=21,
        usuario="pytest",
    )

    iva_mov_fiscales.registrar_movimiento_fiscal(
        empresa_id=1,
        fecha="02/12/2025",
        origen="BANCO",
        tipo_concepto="IVA_CREDITO",
        descripcion="Comisión bancaria 2",
        credito_fiscal_computable=42,
        usuario="pytest",
    )

    iva_mov_fiscales.registrar_movimiento_fiscal(
        empresa_id=1,
        fecha="03/12/2025",
        origen="PERCEPCION",
        tipo_concepto="PERCEPCION_IVA",
        descripcion="Percepción IVA adicional",
        percepcion_iva=30,
        usuario="pytest",
    )

    resumen = iva_mov_fiscales.obtener_resumen_movimientos_fiscales_por_origen(
        empresa_id=1,
        anio=2025,
        mes=12,
    )

    assert len(resumen) == 2

    banco = resumen[
        (resumen["origen"] == "BANCO")
        & (resumen["tipo_concepto"] == "IVA_CREDITO")
    ].iloc[0]

    percepcion = resumen[
        (resumen["origen"] == "PERCEPCION")
        & (resumen["tipo_concepto"] == "PERCEPCION_IVA")
    ].iloc[0]

    assert banco["cantidad"] == 2
    assert banco["credito_fiscal_computable"] == 63

    assert percepcion["cantidad"] == 1
    assert percepcion["percepcion_iva"] == 30


def test_validaciones_de_campos_obligatorios_y_catalogos(db_temporal):
    with pytest.raises(ValueError):
        iva_mov_fiscales.registrar_movimiento_fiscal(
            empresa_id=1,
            fecha="01/12/2025",
            origen="ORIGEN_INVALIDO",
            tipo_concepto="IVA_CREDITO",
            descripcion="Origen inválido",
        )

    with pytest.raises(ValueError):
        iva_mov_fiscales.registrar_movimiento_fiscal(
            empresa_id=1,
            fecha="01/12/2025",
            origen="MANUAL",
            tipo_concepto="TIPO_INVALIDO",
            descripcion="Tipo inválido",
        )

    with pytest.raises(ValueError):
        iva_mov_fiscales.registrar_movimiento_fiscal(
            empresa_id=1,
            fecha="01/12/2025",
            origen="MANUAL",
            tipo_concepto="IVA_CREDITO",
            descripcion="",
        )

    with pytest.raises(ValueError):
        iva_mov_fiscales.registrar_movimiento_fiscal(
            empresa_id=1,
            fecha="01/12/2025",
            origen="MANUAL",
            tipo_concepto="IVA_CREDITO",
            descripcion="Mes inválido",
            anio=2025,
            mes=13,
        )


def test_validar_movimiento_fiscal_dict_devuelve_alertas_control(db_temporal):
    alertas_credito = iva_mov_fiscales.validar_movimiento_fiscal_dict({
        "tipo_concepto": "IVA_CREDITO",
        "credito_fiscal_computable": 0,
    })

    assert any(
        alerta["titulo"] == "Tipo IVA crédito sin importe"
        for alerta in alertas_credito
    )

    alertas_sin_importe = iva_mov_fiscales.validar_movimiento_fiscal_dict({
        "tipo_concepto": "OTRO",
    })

    assert any(
        alerta["titulo"] == "Movimiento fiscal sin impacto IVA"
        for alerta in alertas_sin_importe
    )
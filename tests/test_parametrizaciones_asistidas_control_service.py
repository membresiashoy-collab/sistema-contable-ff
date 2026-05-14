import sqlite3

import pytest

from services.parametrizaciones_asistidas_control_service import (
    ACCION_ACEPTAR,
    ESTADO_ACTIVA,
    ESTADO_DESACTIVADA,
    aceptar_parametrizacion_asistida,
    construir_clave_parametrizacion,
    desactivar_parametrizacion_asistida,
    editar_parametrizacion_asistida,
    exportar_decisiones_parametrizacion_como_texto,
    inicializar_parametrizaciones_asistidas_control,
    listar_decisiones_parametrizacion,
    listar_eventos_decision,
    obtener_decision_parametrizacion,
    obtener_resumen_decisiones_parametrizacion,
    reactivar_parametrizacion_asistida,
)


def _conn():
    return sqlite3.connect(":memory:")


def test_inicializar_crea_tablas_control():
    conn = _conn()

    inicializar_parametrizaciones_asistidas_control(conn)

    tablas = {
        fila[0]
        for fila in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "parametrizaciones_asistidas_decisiones" in tablas
    assert "parametrizaciones_asistidas_eventos" in tablas


def test_aceptar_parametrizacion_crea_decision_activa_y_evento():
    conn = _conn()

    decision = aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Tesoreria",
        clave_parametrizacion="TESORERIA:CUENTA:CAJA_PRINCIPAL",
        tipo_parametrizacion="CUENTA_TESORERIA",
        cuenta_codigo="1.1.01.01",
        cuenta_nombre="Caja principal",
        valor_sugerido={"uso": "CAJA"},
        confianza="ALTA",
        usuario_id=7,
    )

    assert decision["estado_decision"] == ESTADO_ACTIVA
    assert decision["accion_ultima"] == ACCION_ACEPTAR
    assert decision["activo"] == 1
    assert decision["valor_decidido"] == {"uso": "CAJA"}

    eventos = listar_eventos_decision(conn, decision_id=decision["id"])
    assert len(eventos) == 1
    assert eventos[0]["accion"] == ACCION_ACEPTAR
    assert eventos[0]["estado_nuevo"] == ESTADO_ACTIVA


def test_editar_parametrizacion_exige_motivo():
    conn = _conn()

    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Compras",
        clave_parametrizacion="COMPRAS:CATEGORIA:INSUMOS",
        valor_sugerido={"cuenta": "Gastos"},
    )

    with pytest.raises(ValueError, match="requiere motivo"):
        editar_parametrizacion_asistida(
            conn,
            empresa_id=1,
            modulo="Compras",
            clave_parametrizacion="COMPRAS:CATEGORIA:INSUMOS",
            motivo="",
            valor_decidido={"cuenta": "Bienes de cambio"},
        )


def test_editar_parametrizacion_actualiza_version_y_conserva_historial():
    conn = _conn()

    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Compras",
        clave_parametrizacion="COMPRAS:CATEGORIA:INSUMOS",
        valor_sugerido={"cuenta": "Gastos"},
    )

    decision = editar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Compras",
        clave_parametrizacion="COMPRAS:CATEGORIA:INSUMOS",
        motivo="Corresponde activar como bien de cambio por actividad del cliente.",
        cuenta_codigo="1.1.04.01",
        cuenta_nombre="Mercaderias",
        valor_sugerido={"cuenta": "Gastos"},
        valor_decidido={"cuenta": "Bienes de cambio"},
        usuario_id=2,
    )

    assert decision["version"] == 2
    assert decision["estado_decision"] == ESTADO_ACTIVA
    assert decision["cuenta_codigo"] == "1.1.04.01"
    assert decision["requiere_revision"] == 1

    eventos = listar_eventos_decision(conn, decision_id=decision["id"])
    assert [evento["accion"] for evento in eventos] == ["ACEPTAR", "EDITAR"]


def test_desactivar_parametrizacion_exige_motivo_y_no_borra_decision():
    conn = _conn()

    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Caja",
        clave_parametrizacion="CAJA:ARQUEO:SOBRANTE",
        valor_sugerido={"cuenta": "Sobrante de caja"},
    )

    with pytest.raises(ValueError, match="requiere motivo"):
        desactivar_parametrizacion_asistida(
            conn,
            empresa_id=1,
            modulo="Caja",
            clave_parametrizacion="CAJA:ARQUEO:SOBRANTE",
            motivo="",
        )

    decision = desactivar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Caja",
        clave_parametrizacion="CAJA:ARQUEO:SOBRANTE",
        motivo="No aplica a esta empresa por control externo de arqueos.",
    )

    assert decision["estado_decision"] == ESTADO_DESACTIVADA
    assert decision["activo"] == 0

    recuperada = obtener_decision_parametrizacion(
        conn,
        empresa_id=1,
        modulo="Caja",
        clave_parametrizacion="CAJA:ARQUEO:SOBRANTE",
    )
    assert recuperada["id"] == decision["id"]


def test_reactivar_parametrizacion_exige_motivo_y_reabre_decision():
    conn = _conn()

    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Caja",
        clave_parametrizacion="CAJA:ARQUEO:FALTANTE",
        valor_sugerido={"cuenta": "Faltante de caja"},
    )
    desactivar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Caja",
        clave_parametrizacion="CAJA:ARQUEO:FALTANTE",
        motivo="Prueba de baja controlada.",
    )

    with pytest.raises(ValueError, match="requiere motivo"):
        reactivar_parametrizacion_asistida(
            conn,
            empresa_id=1,
            modulo="Caja",
            clave_parametrizacion="CAJA:ARQUEO:FALTANTE",
            motivo="",
        )

    decision = reactivar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Caja",
        clave_parametrizacion="CAJA:ARQUEO:FALTANTE",
        motivo="La empresa vuelve a utilizar arqueos internos.",
    )

    assert decision["estado_decision"] == ESTADO_ACTIVA
    assert decision["activo"] == 1
    assert decision["version"] == 3


def test_listar_y_resumir_decisiones_por_modulo():
    conn = _conn()

    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Ventas",
        clave_parametrizacion="VENTAS:TIPO:SERVICIOS",
        valor_sugerido={"cuenta": "Ventas de servicios"},
    )
    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Pagos",
        clave_parametrizacion="PAGOS:RETENCION:IIBB",
        valor_sugerido={"cuenta": "Retenciones IIBB a depositar"},
    )
    desactivar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Pagos",
        clave_parametrizacion="PAGOS:RETENCION:IIBB",
        motivo="No corresponde a la jurisdiccion del cliente.",
    )

    ventas = listar_decisiones_parametrizacion(conn, empresa_id=1, modulo="Ventas")
    assert len(ventas) == 1
    assert ventas[0]["modulo"] == "VENTAS"

    activas = listar_decisiones_parametrizacion(conn, empresa_id=1, solo_activas=True)
    assert len(activas) == 1

    resumen = obtener_resumen_decisiones_parametrizacion(conn, empresa_id=1)
    assert resumen["total_decisiones"] == 2
    assert resumen["activas"] == 1
    assert resumen["desactivadas"] == 1
    assert resumen["por_modulo"]["PAGOS"]["desactivadas"] == 1


def test_actualizar_misma_clave_no_duplica_decision():
    conn = _conn()

    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Banco Caja",
        clave_parametrizacion="BANCO_CAJA:FISCAL:IVA_DEBITO",
        valor_sugerido={"cuenta": "IVA debito fiscal"},
    )
    editar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Banco Caja",
        clave_parametrizacion="BANCO_CAJA:FISCAL:IVA_DEBITO",
        motivo="Se corrige denominacion de cuenta.",
        valor_decidido={"cuenta": "IVA debito fiscal operativo"},
    )

    decisiones = listar_decisiones_parametrizacion(conn, empresa_id=1, modulo="Banco Caja")
    assert len(decisiones) == 1
    assert decisiones[0]["version"] == 2

    eventos = listar_eventos_decision(conn, decision_id=decisiones[0]["id"])
    assert len(eventos) == 2


def test_construir_clave_parametrizacion_normaliza_componentes():
    clave = construir_clave_parametrizacion("Banco Caja", "Movimiento Fiscal", "iva debito")
    assert clave == "BANCO_CAJA:MOVIMIENTO_FISCAL:IVA_DEBITO"


def test_exportar_decisiones_como_texto():
    conn = _conn()

    aceptar_parametrizacion_asistida(
        conn,
        empresa_id=1,
        modulo="Documentos Tesoreria",
        clave_parametrizacion="DOCUMENTOS:RECIBO:NUMERACION",
        cuenta_codigo=None,
        cuenta_nombre=None,
        valor_sugerido={"control": "numeracion"},
    )

    texto = exportar_decisiones_parametrizacion_como_texto(conn, empresa_id=1)

    assert "PARAMETRIZACION PRO v2B" in texto
    assert "DOCUMENTOS_TESORERIA" in texto
    assert "DOCUMENTOS:RECIBO:NUMERACION" in texto


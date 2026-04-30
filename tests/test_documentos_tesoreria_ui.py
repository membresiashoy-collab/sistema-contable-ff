from pathlib import Path


def leer(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def test_documentos_emitidos_no_esta_como_modulo_lateral():
    contenido = leer("main.py")

    assert '"Documentos emitidos":' not in contenido
    assert "'Documentos emitidos':" not in contenido
    assert "modulos.documentos_tesoreria" not in contenido
    assert "mostrar_documentos_tesoreria" not in contenido


def test_cobranzas_tiene_pestana_recibos_emitidos():
    contenido = leer("modulos/cobranzas.py")

    assert "Recibos emitidos" in contenido
    assert "mostrar_recibos_emitidos_integrado" in contenido
    assert "tab_recibos_emitidos" in contenido


def test_pagos_tiene_pestana_ordenes_pago():
    contenido = leer("modulos/pagos.py")

    assert "Órdenes de pago" in contenido
    assert "mostrar_ordenes_pago_emitidas_integrado" in contenido
    assert "tab_ordenes_pago_emitidas" in contenido


def test_componentes_documentos_tesoreria_tienen_anulacion_controlada():
    contenido = leer("modulos/documentos_tesoreria_componentes.py")

    assert "Anular recibo por error humano" in contenido
    assert "Anular orden de pago por error humano" in contenido
    assert "Motivo obligatorio" in contenido
    assert "Confirmo que quiero anular" in contenido
    assert "anular_cobranza" in contenido
    assert "anular_pago" in contenido
    assert "permitir_conciliada" in contenido
    assert "permitir_conciliado" in contenido


def test_componentes_documentos_tesoreria_no_borran_fisicamente():
    contenido = leer("modulos/documentos_tesoreria_componentes.py").lower()

    assert "delete from cobranzas" not in contenido
    assert "delete from pagos" not in contenido
    assert "drop table" not in contenido
    assert "truncate" not in contenido
    assert "no borra físicamente" in contenido


def test_componentes_documentos_tesoreria_no_tocan_caja_directamente():
    contenido = leer("modulos/documentos_tesoreria_componentes.py")

    assert "mostrar_recibos_emitidos_integrado" in contenido
    assert "mostrar_ordenes_pago_emitidas_integrado" in contenido
    assert "cajas_service" not in contenido
    assert "registrar_cobranza_efectivo_en_caja" not in contenido
    assert "registrar_pago_efectivo_en_caja" not in contenido
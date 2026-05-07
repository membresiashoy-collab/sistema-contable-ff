import importlib

import pytest


def _setup_db(monkeypatch, tmp_path):
    import database

    db_path = tmp_path / "test_iva_cierre.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path), raising=False)

    import services.iva_movimientos_fiscales_service as iva_movs
    import services.iva_service as iva_service
    import services.iva_cierre_service as iva_cierre

    importlib.reload(iva_movs)
    importlib.reload(iva_service)
    importlib.reload(iva_cierre)

    return db_path, iva_movs, iva_service, iva_cierre


def test_cerrar_periodo_sin_movimientos_crea_foto_controlada(monkeypatch, tmp_path):
    _, _, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    resultado = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=12,
        usuario="pytest",
        observacion="Cierre de prueba sin movimientos.",
    )

    assert resultado["ok"] is True
    assert resultado["cierre"]["estado"] == iva_cierre.ESTADO_CIERRE_CERRADO
    assert resultado["cierre"]["periodo"] == "2025-12"
    assert resultado["cierre"]["saldo_preliminar_periodo"] == 0
    assert resultado["cierre"]["resultado_saldo"] == iva_cierre.RESULTADO_CERO
    assert resultado["cierre"]["estado_pago"] == iva_cierre.ESTADO_PAGO_NO_APLICA

    cierre = iva_cierre.obtener_cierre_periodo(empresa_id=1, anio=2025, mes=12)
    assert cierre["estado"] == iva_cierre.ESTADO_CIERRE_CERRADO
    assert cierre["usuario_cierre"] == "pytest"

    eventos = iva_cierre.listar_eventos_cierre(
        empresa_id=1,
        anio=2025,
        mes=12,
    )
    assert not eventos.empty
    assert "CIERRE" in eventos["evento"].tolist()


def test_no_permite_cerrar_dos_veces_sin_reapertura(monkeypatch, tmp_path):
    _, _, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    primero = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=11,
        usuario="pytest",
    )

    segundo = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=11,
        usuario="pytest",
    )

    assert primero["ok"] is True
    assert segundo["ok"] is False
    assert "ya está cerrado" in segundo["mensaje"]


def test_reabrir_periodo_y_volver_a_cerrar(monkeypatch, tmp_path):
    _, _, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    cierre = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=10,
        usuario="pytest",
    )
    assert cierre["ok"] is True

    reapertura = iva_cierre.reabrir_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=10,
        usuario="pytest",
        motivo="Corrección de prueba.",
    )
    assert reapertura["ok"] is True
    assert reapertura["cierre"]["estado"] == iva_cierre.ESTADO_CIERRE_REABIERTO

    nuevo_cierre = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=10,
        usuario="pytest",
        observacion="Nuevo cierre luego de reapertura.",
    )
    assert nuevo_cierre["ok"] is True
    assert nuevo_cierre["cierre"]["estado"] == iva_cierre.ESTADO_CIERRE_CERRADO

    eventos = iva_cierre.listar_eventos_cierre(
        empresa_id=1,
        anio=2025,
        mes=10,
    )
    assert len(eventos) >= 3
    assert set(eventos["evento"].tolist()) >= {"CIERRE", "REAPERTURA"}


def test_movimientos_fiscales_en_borrador_bloquean_cierre_salvo_confirmacion(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=9,
        fecha="2025-09-15",
        origen="MANUAL",
        tipo_concepto="PERCEPCION_IVA",
        descripcion="Percepción IVA pendiente de revisión",
        percepcion_iva=150,
        total=150,
        estado=iva_movs.ESTADO_BORRADOR,
        usuario="pytest",
    )

    bloqueado = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=9,
        usuario="pytest",
        observacion="Intento sin permitir pendientes.",
    )

    assert bloqueado["ok"] is False
    assert bloqueado.get("bloqueos")

    permitido = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=9,
        usuario="pytest",
        observacion="Cierre permitido con pendiente informado.",
        permitir_con_pendientes=True,
    )

    assert permitido["ok"] is True
    assert permitido["cierre"]["estado"] == iva_cierre.ESTADO_CIERRE_CERRADO


def test_cierre_con_saldo_a_pagar_genera_obligacion_y_asiento(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=8,
        fecha="2025-08-31",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito fiscal adicional de prueba",
        iva_debito=1000,
        total=1000,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    resultado = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=8,
        usuario="pytest",
        observacion="Cierre con saldo a pagar.",
    )

    assert resultado["ok"] is True
    cierre = resultado["cierre"]
    assert cierre["resultado_saldo"] == iva_cierre.RESULTADO_A_PAGAR
    assert cierre["saldo_a_pagar"] == 1000
    assert cierre["saldo_pendiente_pago"] == 1000
    assert cierre["estado_pago"] == iva_cierre.ESTADO_PAGO_PENDIENTE

    asientos = iva_cierre.listar_asientos_cierre(
        cierre_id=cierre["id"],
        empresa_id=1,
        tipo_asiento=iva_cierre.TIPO_ASIENTO_LIQUIDACION,
    )
    assert not asientos.empty
    assert round(asientos["debe"].sum(), 2) == round(asientos["haber"].sum(), 2)


def test_registrar_pago_iva_actualiza_estado_y_genera_asiento_pago(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=7,
        fecha="2025-07-31",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito fiscal adicional de prueba",
        iva_debito=1200,
        total=1200,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    cierre_resultado = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=7,
        usuario="pytest",
    )
    assert cierre_resultado["ok"] is True

    pago = iva_cierre.registrar_pago_iva(
        empresa_id=1,
        anio=2025,
        mes=7,
        fecha_pago="2025-08-18",
        importe=1200,
        medio_pago="BANCO",
        referencia="VEP prueba",
        usuario="pytest",
    )

    assert pago["ok"] is True
    assert pago["cierre"]["importe_pagado"] == 1200
    assert pago["cierre"]["saldo_pendiente_pago"] == 0
    assert pago["cierre"]["estado_pago"] == iva_cierre.ESTADO_PAGO_PAGADO

    pagos = iva_cierre.listar_pagos_cierre(
        cierre_id=pago["cierre"]["id"],
        empresa_id=1,
    )
    assert len(pagos) == 1

    asientos_pago = iva_cierre.listar_asientos_cierre(
        cierre_id=pago["cierre"]["id"],
        empresa_id=1,
        tipo_asiento=iva_cierre.TIPO_ASIENTO_PAGO,
    )
    assert not asientos_pago.empty
    assert round(asientos_pago["debe"].sum(), 2) == round(asientos_pago["haber"].sum(), 2)


def test_saldo_a_favor_no_permite_registrar_pago(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=6,
        fecha="2025-06-30",
        origen="MANUAL",
        tipo_concepto="IVA_CREDITO",
        descripcion="Crédito fiscal adicional de prueba",
        credito_fiscal_computable=500,
        total=500,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    cierre = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=6,
        usuario="pytest",
    )

    assert cierre["ok"] is True
    assert cierre["cierre"]["resultado_saldo"] == iva_cierre.RESULTADO_A_FAVOR
    assert cierre["cierre"]["saldo_a_favor"] == 500
    assert cierre["cierre"]["estado_pago"] == iva_cierre.ESTADO_PAGO_NO_APLICA

    pago = iva_cierre.registrar_pago_iva(
        empresa_id=1,
        anio=2025,
        mes=6,
        fecha_pago="2025-07-15",
        importe=100,
        medio_pago="BANCO",
        usuario="pytest",
    )
    assert pago["ok"] is False
    assert "no tiene saldo IVA a pagar" in pago["mensaje"]
def test_cierre_original_con_saldo_tecnico_a_favor_traslada_al_periodo_siguiente(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=5,
        fecha="2025-05-31",
        origen="MANUAL",
        tipo_concepto="IVA_CREDITO",
        descripcion="Crédito fiscal para traslado",
        credito_fiscal_computable=800,
        total=800,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    cierre = iva_cierre.cerrar_periodo_iva(empresa_id=1, anio=2025, mes=5, usuario="pytest")

    assert cierre["ok"] is True
    assert cierre["cierre"]["version_etiqueta"] == "Original"
    assert cierre["cierre"]["saldo_tecnico_a_favor_trasladable"] == 800
    assert cierre["cierre"]["saldo_trasladado_al_siguiente"] == 800

    movs_junio = iva_movs.listar_movimientos_fiscales(empresa_id=1, anio=2025, mes=6, incluir_anulados=False)
    assert not movs_junio.empty
    assert "SALDO_TECNICO_ANTERIOR" in movs_junio["tipo_concepto"].tolist()
    assert round(movs_junio["saldo_tecnico_anterior"].sum(), 2) == 800


def test_rectificativa_conserva_original_y_queda_vigente(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=4,
        fecha="2025-04-30",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito original",
        iva_debito=1000,
        total=1000,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    original = iva_cierre.cerrar_periodo_iva(empresa_id=1, anio=2025, mes=4, usuario="pytest")
    assert original["ok"] is True

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=4,
        fecha="2025-04-30",
        origen="MANUAL",
        tipo_concepto="IVA_CREDITO",
        descripcion="Crédito agregado por rectificativa",
        credito_fiscal_computable=200,
        total=200,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    rect = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=4,
        usuario="pytest",
        generar_rectificativa=True,
        motivo_rectificativa="Comprobante de compra omitido.",
    )

    assert rect["ok"] is True
    assert rect["cierre"]["version_etiqueta"] == "Rectificativa 1"
    assert rect["cierre"]["numero_rectificativa"] == 1
    assert rect["cierre"]["es_version_vigente"] == 1

    versiones = iva_cierre.listar_versiones_periodo(empresa_id=1, anio=2025, mes=4)
    assert len(versiones) == 2
    assert versiones["version_etiqueta"].tolist() == ["Original", "Rectificativa 1"]
    assert versiones["es_version_vigente"].tolist() == [0, 1]


def test_rectificativa_reduce_saldo_trasladado_y_marca_periodo_siguiente(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=3,
        fecha="2025-03-31",
        origen="MANUAL",
        tipo_concepto="IVA_CREDITO",
        descripcion="Crédito fiscal original",
        credito_fiscal_computable=1000,
        total=1000,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    original = iva_cierre.cerrar_periodo_iva(empresa_id=1, anio=2025, mes=3, usuario="pytest")
    assert original["ok"] is True
    assert original["cierre"]["saldo_trasladado_al_siguiente"] == 1000

    # Cerrar abril para que la rectificativa de marzo tenga un período posterior que marcar.
    cierre_abril = iva_cierre.cerrar_periodo_iva(empresa_id=1, anio=2025, mes=4, usuario="pytest", permitir_salto_cronologico=True)
    assert cierre_abril["ok"] is True

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=3,
        fecha="2025-03-31",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito agregado por rectificativa",
        iva_debito=300,
        total=300,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    rect = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=3,
        usuario="pytest",
        generar_rectificativa=True,
        motivo_rectificativa="Se incorporó débito fiscal omitido.",
    )

    assert rect["ok"] is True
    cierre_rect = rect["cierre"]
    assert cierre_rect["version_etiqueta"] == "Rectificativa 1"
    assert cierre_rect["saldo_trasladado_original"] == 1000
    assert cierre_rect["saldo_trasladado_rectificado"] == 700
    assert cierre_rect["diferencia_saldo_trasladado"] == 300
    assert rect["impacto_rectificativa"]["tipo_impacto"] == "REDUCE_SALDO_TRASLADADO"

    abril = iva_cierre.obtener_cierre_periodo(empresa_id=1, anio=2025, mes=4)
    assert abril["requiere_revision_por_rectificativa"] == 1
    assert "300" in abril["motivo_revision"]


def test_cierre_deja_obligacion_pendiente_y_consultable_para_asistente(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=2,
        fecha="2025-02-28",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito fiscal para obligación pendiente",
        iva_debito=1500,
        total=1500,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    cierre = iva_cierre.cerrar_periodo_iva(
        empresa_id=1,
        anio=2025,
        mes=2,
        usuario="pytest",
        observacion="Cierre sin pago inmediato.",
    )

    assert cierre["ok"] is True
    assert cierre["cierre"]["saldo_a_pagar"] == 1500
    assert cierre["cierre"]["importe_pagado"] == 0
    assert cierre["cierre"]["saldo_pendiente_pago"] == 1500
    assert cierre["cierre"]["estado_pago"] == iva_cierre.ESTADO_PAGO_PENDIENTE

    obligaciones = iva_cierre.listar_obligaciones_iva_pendientes(empresa_id=1)
    assert len(obligaciones) == 1
    assert obligaciones.iloc[0]["periodo"] == "2025-02"
    assert obligaciones.iloc[0]["concepto"] == "IVA mensual"
    assert obligaciones.iloc[0]["saldo_pendiente_pago"] == 1500

    resumen = iva_cierre.obtener_resumen_deuda_fiscal_iva(empresa_id=1)
    assert resumen["cantidad_obligaciones"] == 1
    assert resumen["total_pendiente"] == 1500
    assert resumen["periodos"] == ["2025-02"]


def test_obligaciones_pendientes_excluyen_periodos_pagados(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=1,
        fecha="2025-01-31",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito fiscal a pagar completo",
        iva_debito=900,
        total=900,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )

    cierre = iva_cierre.cerrar_periodo_iva(empresa_id=1, anio=2025, mes=1, usuario="pytest")
    assert cierre["ok"] is True

    pago = iva_cierre.registrar_pago_iva(
        empresa_id=1,
        anio=2025,
        mes=1,
        fecha_pago="2025-02-15",
        importe=900,
        medio_pago="BANCO",
        referencia="VEP pagado",
        usuario="pytest",
    )
    assert pago["ok"] is True
    assert pago["cierre"]["estado_pago"] == iva_cierre.ESTADO_PAGO_PAGADO

    obligaciones = iva_cierre.listar_obligaciones_iva_pendientes(empresa_id=1)
    assert obligaciones.empty

    resumen = iva_cierre.obtener_resumen_deuda_fiscal_iva(empresa_id=1)
    assert resumen["cantidad_obligaciones"] == 0
    assert resumen["total_pendiente"] == 0


def test_corregir_datos_administrativos_pago_no_modifica_saldo_ni_asiento(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=11,
        fecha="2025-11-30",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito fiscal para pago administrativo",
        iva_debito=1000,
        total=1000,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )
    cierre = iva_cierre.cerrar_periodo_iva(empresa_id=1, anio=2025, mes=11, usuario="pytest")
    assert cierre["ok"] is True
    pago = iva_cierre.registrar_pago_iva(
        empresa_id=1,
        anio=2025,
        mes=11,
        fecha_pago="2025-12-18",
        importe=600,
        medio_pago="BANCO",
        referencia="VEP MAL",
        observacion="obs vieja",
        usuario="pytest",
    )
    assert pago["ok"] is True
    pago_id = pago["pago_id"]
    cierre_id = pago["cierre"]["id"]

    asientos_antes = iva_cierre.listar_asientos_cierre(cierre_id=cierre_id, empresa_id=1, tipo_asiento=iva_cierre.TIPO_ASIENTO_PAGO)
    assert not asientos_antes.empty

    corregido = iva_cierre.actualizar_datos_administrativos_pago_iva(
        pago_id=pago_id,
        empresa_id=1,
        referencia="VEP CORRECTO",
        observacion="obs corregida",
        motivo="Corrección de número de VEP.",
        usuario="pytest",
    )
    assert corregido["ok"] is True
    assert corregido["cierre"]["importe_pagado"] == 600
    assert corregido["cierre"]["saldo_pendiente_pago"] == 400

    pagos = iva_cierre.listar_pagos_cierre(cierre_id=cierre_id, empresa_id=1)
    assert len(pagos) == 1
    assert pagos.iloc[0]["referencia"] == "VEP CORRECTO"
    assert pagos.iloc[0]["observacion"] == "obs corregida"

    asientos_despues = iva_cierre.listar_asientos_cierre(cierre_id=cierre_id, empresa_id=1, tipo_asiento=iva_cierre.TIPO_ASIENTO_PAGO)
    assert len(asientos_despues) == len(asientos_antes)
    assert round(asientos_despues["debe"].sum(), 2) == round(asientos_antes["debe"].sum(), 2)


def test_rectificar_pago_con_impacto_recalcula_saldo_y_asiento(monkeypatch, tmp_path):
    _, iva_movs, _, iva_cierre = _setup_db(monkeypatch, tmp_path)

    iva_movs.registrar_movimiento_fiscal(
        empresa_id=1,
        anio=2025,
        mes=12,
        fecha="2025-12-31",
        origen="MANUAL",
        tipo_concepto="IVA_DEBITO",
        descripcion="Débito fiscal para rectificar pago",
        iva_debito=1000,
        total=1000,
        estado=iva_movs.ESTADO_CONFIRMADO,
        incluido_en_posicion=True,
        usuario="pytest",
    )
    cierre = iva_cierre.cerrar_periodo_iva(empresa_id=1, anio=2025, mes=12, usuario="pytest")
    assert cierre["ok"] is True
    pago = iva_cierre.registrar_pago_iva(
        empresa_id=1,
        anio=2025,
        mes=12,
        fecha_pago="2026-01-18",
        importe=1000,
        medio_pago="BANCO",
        referencia="VEP original",
        usuario="pytest",
    )
    assert pago["ok"] is True
    pago_id = pago["pago_id"]
    cierre_id = pago["cierre"]["id"]

    rectificado = iva_cierre.rectificar_pago_iva(
        pago_id=pago_id,
        empresa_id=1,
        fecha_pago="2026-01-19",
        importe=700,
        medio_pago="TRANSFERENCIA",
        referencia="VEP rectificado",
        observacion="Importe corregido",
        motivo="El importe original estaba mal cargado.",
        usuario="pytest",
    )
    assert rectificado["ok"] is True
    assert rectificado["pago_original_id"] == pago_id
    assert rectificado["cierre"]["importe_pagado"] == 700
    assert rectificado["cierre"]["saldo_pendiente_pago"] == 300
    assert rectificado["cierre"]["estado_pago"] == iva_cierre.ESTADO_PAGO_PARCIAL

    pagos_vigentes = iva_cierre.listar_pagos_cierre(cierre_id=cierre_id, empresa_id=1)
    assert len(pagos_vigentes) == 1
    assert pagos_vigentes.iloc[0]["importe"] == 700
    assert pagos_vigentes.iloc[0]["pago_original_id"] == pago_id

    pagos_historial = iva_cierre.listar_pagos_cierre(cierre_id=cierre_id, empresa_id=1, incluir_anulados=True)
    assert set(pagos_historial["estado"].tolist()) >= {iva_cierre.ESTADO_PAGO_REGISTRADO, iva_cierre.ESTADO_PAGO_RECTIFICADO}

    asientos_pago = iva_cierre.listar_asientos_cierre(cierre_id=cierre_id, empresa_id=1, tipo_asiento=iva_cierre.TIPO_ASIENTO_PAGO)
    asientos_vigentes = asientos_pago[asientos_pago["estado"] == "PROPUESTO"]
    assert round(asientos_vigentes["debe"].sum(), 2) == 700
    assert round(asientos_vigentes["haber"].sum(), 2) == 700
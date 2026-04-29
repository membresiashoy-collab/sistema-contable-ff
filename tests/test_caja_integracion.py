from pathlib import Path


def leer(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def test_caja_tiene_tipos_automaticos_de_cobranzas_y_pagos():
    contenido = leer("services/cajas_service.py")

    assert "COBRANZA_EFECTIVO" in contenido
    assert "PAGO_EFECTIVO" in contenido
    assert "registrar_cobranza_efectivo_en_caja_cur" in contenido
    assert "registrar_pago_efectivo_en_caja_cur" in contenido
    assert "No genera asiento en caja_asientos" in contenido


def test_cobranzas_efectivo_impacta_caja_y_no_efectivo_no_usa_caja():
    contenido = leer("services/cobranzas_service.py")

    assert "from services import tesoreria_service, cajas_service" in contenido
    assert "medio_pago_codigo == \"EFECTIVO\"" in contenido
    assert "registrar_cobranza_efectivo_en_caja_cur" in contenido
    assert "El medio de pago EFECTIVO debe usar una cuenta tipo CAJA." in contenido
    assert "Solo las cobranzas en EFECTIVO pueden ingresar a una cuenta tipo CAJA" in contenido


def test_pagos_efectivo_impacta_caja_y_no_efectivo_no_usa_caja():
    contenido = leer("services/pagos_service.py")

    assert "from services import tesoreria_service, cajas_service" in contenido
    assert "medio_pago_codigo == \"EFECTIVO\"" in contenido
    assert "registrar_pago_efectivo_en_caja_cur" in contenido
    assert "El medio de pago EFECTIVO debe salir de una cuenta tipo CAJA." in contenido
    assert "Solo los pagos en EFECTIVO pueden salir de una cuenta tipo CAJA" in contenido


def test_anulaciones_de_cobranzas_y_pagos_anulan_movimientos_de_caja():
    cobranzas = leer("services/cobranzas_service.py")
    pagos = leer("services/pagos_service.py")

    assert "anular_movimientos_caja_por_referencia_cur" in cobranzas
    assert "COBRANZA_EFECTIVO" in cobranzas
    assert "anular_movimientos_caja_por_referencia_cur" in pagos
    assert "PAGO_EFECTIVO" in pagos


def test_inicializar_cajas_no_crea_caja_general_si_ya_existe_otra_caja():
    contenido = leer("services/cajas_service.py")

    assert "cantidad_cajas" in contenido
    assert "if cantidad_cajas == 0" in contenido
    assert "Caja General" in contenido

import importlib


def test_bandeja_asientos_componentes_importa():
    modulo = importlib.import_module("modulos.bandeja_asientos_componentes")

    assert hasattr(modulo, "mostrar_bandeja_asientos_propuestos")
    assert callable(modulo.mostrar_bandeja_asientos_propuestos)


def test_bandeja_asientos_componentes_expone_alias_ui():
    modulo = importlib.import_module("modulos.bandeja_asientos_componentes")

    assert hasattr(modulo, "mostrar_bandeja_asientos_propuestos_ui")
    assert callable(modulo.mostrar_bandeja_asientos_propuestos_ui)


def test_bandeja_formatea_claves_de_origen():
    modulo = importlib.import_module("modulos.bandeja_asientos_componentes")

    assert modulo._formatear_fuente_asiento("CENTRAL:12") == "Asiento origen #12"
    assert modulo._formatear_fuente_asiento("IVA:5:0:LIQUIDACION_IVA") == "IVA cierre #5 · LIQUIDACION_IVA"
    assert modulo._formatear_fuente_asiento("IVA:5:9:PAGO_IVA") == "IVA pago #9 · PAGO_IVA"


def test_bandeja_expone_acciones_masivas():
    modulo = importlib.import_module("modulos.bandeja_asientos_componentes")

    assert hasattr(modulo, "_mostrar_acciones_masivas")
    assert callable(modulo._mostrar_acciones_masivas)
    assert hasattr(modulo, "_mostrar_resultado_prevalidacion")
    assert callable(modulo._mostrar_resultado_prevalidacion)


def test_bandeja_expone_lotes_recientes():
    modulo = importlib.import_module("modulos.bandeja_asientos_componentes")

    assert hasattr(modulo, "_mostrar_lotes_recientes")
    assert callable(modulo._mostrar_lotes_recientes)
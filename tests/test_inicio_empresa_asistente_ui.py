from pathlib import Path


def test_componente_expone_funcion_principal():
    from modulos.inicio_empresa_componentes import mostrar_estado_empresa_operativa_adaptativo

    assert callable(mostrar_estado_empresa_operativa_adaptativo)


def test_contador_requisitos_separa_bloqueantes_y_recomendados():
    from modulos.inicio_empresa_componentes import _contar_requisitos

    requisitos = [
        {"ok": True, "bloqueante": True},
        {"ok": False, "bloqueante": True},
        {"ok": False, "bloqueante": False, "recomendado": True},
        {"ok": False, "bloqueante": False},
    ]

    conteo = _contar_requisitos(requisitos)

    assert conteo["pendientes"] == 3
    assert conteo["bloqueantes"] == 1
    assert conteo["recomendados"] == 2


def test_componente_deja_explicito_que_persona_humana_no_exige_flujo_societario():
    contenido = Path("modulos/inicio_empresa_componentes.py").read_text(encoding="utf-8")

    assert "persona humana" in contenido.lower()
    assert "No se exige carga de socios" in contenido
    assert "capital social" in contenido
    assert "integración societaria" in contenido


def test_componente_no_importa_modulos_operativos_pesados():
    contenido = Path("modulos/inicio_empresa_componentes.py").read_text(encoding="utf-8")

    prohibidos = [
        "modulos.bancos",
        "modulos.caja",
        "modulos.iva",
        "modulos.ventas",
        "modulos.compras",
        "modulos.cobranzas",
        "modulos.pagos",
        "modulos.conciliacion",
        "services.bancos_service",
        "services.cajas_service",
        "services.iva_service",
    ]

    for prohibido in prohibidos:
        assert prohibido not in contenido


def test_configuracion_delega_estado_operativo_en_componente_adaptativo():
    contenido = Path("modulos/configuracion.py").read_text(encoding="utf-8")

    assert "modulos.inicio_empresa_componentes" in contenido
    assert "mostrar_estado_empresa_operativa_adaptativo" in contenido
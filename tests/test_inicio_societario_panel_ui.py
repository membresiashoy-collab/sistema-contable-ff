from pathlib import Path
import importlib


RAIZ = Path(__file__).resolve().parents[1]


def test_panel_inicio_societario_importa_funcion_principal():
    modulo = importlib.import_module("modulos.inicio_societario_componentes")
    assert hasattr(modulo, "mostrar_panel_inicio_societario")
    assert callable(modulo.mostrar_panel_inicio_societario)


def test_panel_inicio_societario_no_importa_modulos_operativos_pesados():
    fuente = (RAIZ / "modulos" / "inicio_societario_componentes.py").read_text(encoding="utf-8")

    assert "modulos.bancos" not in fuente
    assert "modulos.caja" not in fuente
    assert "services.bancos_service" not in fuente
    assert "services.cajas_service" not in fuente


def test_panel_inicio_societario_usa_servicio_capital_social():
    fuente = (RAIZ / "modulos" / "inicio_societario_componentes.py").read_text(encoding="utf-8")

    funciones_requeridas = [
        "listar_socios_empresa",
        "crear_socio_empresa",
        "listar_capital_social_empresa",
        "configurar_capital_social_inicial",
        "listar_pendientes_integracion_por_socio",
        "listar_movimientos_tesoreria_disponibles_para_integracion",
        "registrar_integracion_capital_desde_tesoreria",
        "anular_integracion_capital",
        "obtener_resumen_capital_socios",
        "listar_eventos_capital",
    ]

    for funcion in funciones_requeridas:
        assert funcion in fuente


def test_panel_resuelve_empresa_id_desde_perfil():
    modulo = importlib.import_module("modulos.inicio_societario_componentes")

    assert modulo._empresa_id_desde_perfil(empresa_id=7) == 7
    assert modulo._empresa_id_desde_perfil(perfil={"empresa_id": 8}) == 8
    assert modulo._empresa_id_desde_perfil(perfil={"empresa": {"id": 9}}) == 9


def test_inicio_empresa_conecta_panel_societario_sin_absorber_logica():
    fuente = (RAIZ / "modulos" / "inicio_empresa_componentes.py").read_text(encoding="utf-8")

    assert "mostrar_panel_inicio_societario" in fuente
    assert "from modulos.inicio_societario_componentes import mostrar_panel_inicio_societario" in fuente

    tramo_sociedad = fuente[
        fuente.index("def _mostrar_tarjeta_sociedad"):
        fuente.index("def _mostrar_tarjeta_otro_ente")
    ]

    assert "mostrar_panel_inicio_societario(" in tramo_sociedad
    assert "listar_movimientos_tesoreria_disponibles_para_integracion" not in tramo_sociedad
    assert "registrar_integracion_capital_desde_tesoreria" not in tramo_sociedad
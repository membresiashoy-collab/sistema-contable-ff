from pathlib import Path
import importlib


RAIZ = Path(__file__).resolve().parents[1]


def test_servicio_expone_baja_logica_controlada_de_socio():
    servicio = importlib.import_module("services.capital_social_service")
    assert hasattr(servicio, "dar_baja_socio_empresa")
    assert callable(servicio.dar_baja_socio_empresa)


def test_baja_logica_no_borra_fisicamente_socios():
    fuente = (RAIZ / "services" / "capital_social_service.py").read_text(encoding="utf-8")
    tramo = fuente[
        fuente.index("def dar_baja_socio_empresa"):
        fuente.index("def listar_capital_social_empresa")
    ]

    assert "DELETE FROM socios_empresa" not in tramo
    assert "UPDATE socios_empresa" in tramo
    assert "estado = 'BAJA'" in tramo or 'estado = "BAJA"' in tramo
    assert "fecha_baja = CURRENT_TIMESTAMP" in tramo
    assert "motivo_baja" in tramo


def test_baja_logica_exige_motivo_y_registra_evento():
    fuente = (RAIZ / "services" / "capital_social_service.py").read_text(encoding="utf-8")
    tramo = fuente[
        fuente.index("def dar_baja_socio_empresa"):
        fuente.index("def listar_capital_social_empresa")
    ]

    assert "motivo_limpio" in tramo
    assert "motivo" in tramo.lower()
    assert "_registrar_evento" in tramo
    assert "BAJA_SOCIO" in tramo


def test_baja_logica_controla_vinculos_societarios_activos():
    fuente = (RAIZ / "services" / "capital_social_service.py").read_text(encoding="utf-8")
    tramo = fuente[
        fuente.index("def dar_baja_socio_empresa"):
        fuente.index("def listar_capital_social_empresa")
    ]

    assert "capital_suscripciones" in tramo
    assert "capital_integraciones" in tramo
    assert "permitir_con_vinculos" in tramo


def test_panel_societario_integra_gestion_controlada_sin_tocar_modulos_operativos():
    fuente = (RAIZ / "modulos" / "inicio_societario_componentes.py").read_text(encoding="utf-8")

    assert "dar_baja_socio_empresa" in fuente
    assert "_mostrar_gestion_controlada_socios" in fuente
    assert "Gestión controlada de socios" in fuente
    assert "modulos.bancos" not in fuente
    assert "modulos.caja" not in fuente
    assert "services.bancos_service" not in fuente
    assert "services.cajas_service" not in fuente
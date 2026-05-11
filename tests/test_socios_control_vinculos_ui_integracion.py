from pathlib import Path


def test_componente_control_vinculos_socios_importa_funcion() -> None:
    from modulos.socios_control_vinculos_componentes import mostrar_control_normativo_vinculos_socios

    assert callable(mostrar_control_normativo_vinculos_socios)


def test_componente_control_vinculos_socios_no_promete_registracion() -> None:
    texto = Path("modulos/socios_control_vinculos_componentes.py").read_text(encoding="utf-8")

    assert "No registra operaciones" in texto
    assert "no genera asientos" in texto.lower() or "no genera asientos definitivos" in texto.lower()
    assert "Caja/Banco" in texto


def test_servicio_control_vinculos_socios_declara_que_no_registra_movimientos() -> None:
    texto = Path("services/socios_control_vinculos_service.py").read_text(encoding="utf-8")

    assert '"registra_movimientos": False' in texto
    assert '"genera_asientos": False' in texto
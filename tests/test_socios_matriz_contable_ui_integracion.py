from __future__ import annotations

from pathlib import Path


def test_componente_matriz_contable_no_usa_titulo_global() -> None:
    fuente = Path("modulos/socios_matriz_contable_componentes.py").read_text(encoding="utf-8")

    assert "st.title(" not in fuente
    assert "def mostrar_matriz_contable_socios" in fuente
    assert "Matriz contable de vínculos con socios" in fuente
    assert "No registra operaciones" in fuente or "No registra Caja/Banco" in fuente


def test_componente_matriz_contable_usa_servicio_propio() -> None:
    fuente = Path("modulos/socios_matriz_contable_componentes.py").read_text(encoding="utf-8")

    assert "from services.socios_matriz_contable_service import" in fuente
    assert "listar_matriz_contable_socios" in fuente
    assert "actualizar_vinculo_matriz_contable" in fuente
    assert "restaurar_vinculo_matriz_contable" in fuente


def test_socios_empresa_conecta_matriz_con_minimo_acoplamiento() -> None:
    fuente = Path("modulos/socios_empresa_componentes.py").read_text(encoding="utf-8")

    assert "mostrar_matriz_contable_socios" in fuente
    assert "modulos.socios_matriz_contable_componentes" in fuente
    assert "Ficha integral y cuenta particular" in fuente
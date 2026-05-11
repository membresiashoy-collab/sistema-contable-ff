from pathlib import Path


def test_componente_socios_pro_tiene_panel_integral_sin_title():
    fuente = Path("modulos/socios_empresa_componentes.py").read_text(encoding="utf-8")

    assert "def mostrar_socios_empresa_pro" in fuente
    assert "Ficha integral y cuenta particular" in fuente
    assert "st.title(" not in fuente
    assert "actualizar_ficha_integral_socio" in fuente
    assert "preparar_cuenta_particular_socio" in fuente


def test_componente_socios_pro_no_registra_operaciones_reales():
    fuente = Path("modulos/socios_empresa_componentes.py").read_text(encoding="utf-8").lower()

    assert "registrar movimiento" not in fuente
    assert "generar asiento definitivo" not in fuente
    assert "conciliar" not in fuente


def test_inicio_societario_conecta_panel_socios_pro():
    fuente = Path("modulos/inicio_societario_componentes.py").read_text(encoding="utf-8")

    assert "from modulos.socios_empresa_componentes import mostrar_socios_empresa_pro" in fuente
    assert "mostrar_socios_empresa_pro(empresa_id=empresa_id_resuelto" in fuente
from pathlib import Path


def test_vinculos_economicos_opcionales_no_vienen_habilitados_por_defecto_en_servicio():
    fuente = Path("services/socios_empresa_service.py").read_text(encoding="utf-8")

    assert "admite_prestamos = COALESCE(admite_prestamos, 0)" in fuente
    assert "admite_retiros = COALESCE(admite_retiros, 0)" in fuente
    assert "admite_reintegros = COALESCE(admite_reintegros, 0)" in fuente
    assert "admite_honorarios = COALESCE(admite_honorarios, 0)" in fuente
    assert "admite_facturas_proveedor = COALESCE(admite_facturas_proveedor, 0)" in fuente

    assert "admite_prestamos: bool = False" in fuente
    assert "admite_retiros: bool = False" in fuente
    assert "admite_reintegros: bool = False" in fuente
    assert "admite_honorarios: bool = False" in fuente
    assert "admite_facturas_proveedor: bool = False" in fuente


def test_vinculos_economicos_opcionales_no_vienen_tildados_por_defecto_en_ui():
    fuente = Path("modulos/socios_empresa_componentes.py").read_text(encoding="utf-8")

    assert 'ficha.get("admite_prestamos", 0)' in fuente
    assert 'ficha.get("admite_retiros", 0)' in fuente
    assert 'ficha.get("admite_reintegros", 0)' in fuente
    assert 'ficha.get("admite_honorarios", 0)' in fuente
    assert 'ficha.get("admite_facturas_proveedor", 0)' in fuente


def test_panel_cuentas_especificas_sigue_conectado():
    fuente = Path("modulos/socios_empresa_componentes.py").read_text(encoding="utf-8")

    assert "mostrar_matriz_contable_socios" in fuente
    assert "mostrar_socios_cuentas_especificas(empresa_id=empresa_id)" in fuente
    assert "mostrar_control_normativo_vinculos_socios" in fuente

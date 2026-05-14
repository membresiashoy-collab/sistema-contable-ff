from pathlib import Path
import ast


COMPONENTE = Path("modulos/centro_control_contable_componentes.py")
REPORTES = Path("modulos/reportes.py")


def _funciones_publicas(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }


def test_componente_centro_control_existe_y_expone_funcion_ui():
    assert COMPONENTE.exists()
    funciones = _funciones_publicas(COMPONENTE)
    assert "mostrar_centro_control_contable_ui" in funciones


def test_componente_no_importa_servicios_operativos():
    texto = COMPONENTE.read_text(encoding="utf-8")

    prohibidos = [
        "services.compras_service",
        "services.ventas_service",
        "services.cobranzas_service",
        "services.pagos_service",
        "services.tesoreria_service",
        "services.conciliacion_service",
        "services.bancos_service",
        "services.bancos_operaciones_service",
        "services.cajas_service",
        "services.documentos_tesoreria_service",
        "services.asientos_propuestos_service",
    ]

    for prohibido in prohibidos:
        assert prohibido not in texto


def test_reportes_importa_y_conecta_centro_control():
    texto = REPORTES.read_text(encoding="utf-8")

    assert (
        "from modulos.centro_control_contable_componentes import "
        "mostrar_centro_control_contable_ui"
    ) in texto
    assert "🧭 Centro de Control" in texto
    assert "mostrar_centro_control_contable_ui(" in texto


def test_reportes_mantiene_mostrar_diario_y_tabs():
    texto = REPORTES.read_text(encoding="utf-8")

    assert "def mostrar_diario()" in texto
    assert "st.tabs([" in texto
    assert "tab11" in texto

from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def _leer(ruta):
    return (ROOT / ruta).read_text(encoding="utf-8")


def _funcion(ruta, nombre):
    texto = _leer(ruta)
    arbol = ast.parse(texto)

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nombre:
            return ast.get_source_segment(texto, nodo)

    raise AssertionError(f"No se encontró la función {nombre} en {ruta}")


def test_seguridad_service_crea_y_edita_tipo_sujeto():
    crear = _funcion("services/seguridad_service.py", "crear_empresa")
    editar = _funcion("services/seguridad_service.py", "actualizar_empresa")
    obtener = _funcion("services/seguridad_service.py", "obtener_empresas")

    assert "tipo_sujeto" in crear
    assert "tipo_sujeto" in editar
    assert "tipo_sujeto" in obtener
    assert "_normalizar_tipo_sujeto_seguridad" in crear
    assert "_normalizar_tipo_sujeto_seguridad" in editar
    assert "Cambio de tipo de sujeto" in editar
    assert "COALESCE(tipo_sujeto" in obtener


def test_seguridad_ui_tiene_selector_tipo_sujeto_en_alta_y_edicion():
    crear = _funcion("modulos/seguridad.py", "mostrar_crear_empresa")
    editar = _funcion("modulos/seguridad.py", "mostrar_editar_empresa")

    assert "Tipo de sujeto *" in crear
    assert "Tipo de sujeto *" in editar
    assert "st.selectbox" in crear
    assert "st.selectbox" in editar
    assert "tipo_sujeto=tipo_sujeto" in crear
    assert "tipo_sujeto=tipo_sujeto" in editar
    assert "Persona humana" in crear
    assert "no requiere socios" in crear


def test_configuracion_muestra_inicio_empresa_y_documentacion_opcional():
    from pathlib import Path

    estado = _funcion("modulos/configuracion.py", "mostrar_estado_empresa_operativa")
    componente = Path("modulos/inicio_empresa_componentes.py").read_text(encoding="utf-8")

    assert "mostrar_estado_empresa_operativa_adaptativo" in estado
    assert "Inicio de empresa" in componente
    assert "Documentación respaldatoria opcional" in componente
    assert "documentacion_respaldo_listar" in componente

def test_no_se_tocan_modulos_operativos_en_esta_integracion():
    archivos_modificados_esperados = {
        "services/seguridad_service.py",
        "modulos/seguridad.py",
        "modulos/configuracion.py",
        "tests/test_inicio_empresa_ui_integracion.py",
    }

    assert "modulos/caja.py" not in archivos_modificados_esperados
    assert "modulos/bancos.py" not in archivos_modificados_esperados
    assert "services/cajas_service.py" not in archivos_modificados_esperados
    assert "services/bancos_service.py" not in archivos_modificados_esperados

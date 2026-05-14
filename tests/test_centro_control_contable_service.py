from types import ModuleType
import sys

from services.centro_control_contable_service import (
    ESTADO_ADVERTENCIA,
    ESTADO_CRITICO,
    ESTADO_ERROR,
    ESTADO_NO_DISPONIBLE,
    ESTADO_OK,
    ESTADO_REQUIERE_PARAMETRIZACION,
    FuncionModulo,
    ModuloCentroControl,
    exportar_centro_control_como_texto,
    generar_centro_control_contable,
    obtener_modulos_centro_control,
    obtener_resumen_centro_control,
)


def _registrar_modulo_falso(monkeypatch, nombre_modulo, **funciones):
    modulo = ModuleType(nombre_modulo)
    for nombre, funcion in funciones.items():
        setattr(modulo, nombre, funcion)
    monkeypatch.setitem(sys.modules, nombre_modulo, modulo)
    return modulo


def test_catalogo_incluye_modulos_operativos_principales():
    catalogo = obtener_modulos_centro_control()
    codigos = {item["codigo"] for item in catalogo}

    assert "COMPRAS" in codigos
    assert "VENTAS" in codigos
    assert "COBRANZAS" in codigos
    assert "PAGOS" in codigos
    assert "TESORERIA" in codigos
    assert "CONCILIACION" in codigos
    assert "BANCO_CAJA" in codigos
    assert "CAJA" in codigos
    assert "DOCUMENTOS_TESORERIA" in codigos


def test_generar_centro_control_con_modulo_ok(monkeypatch):
    _registrar_modulo_falso(
        monkeypatch,
        "fake.diagnostico_ok",
        diagnosticar=lambda empresa_id=None: {"estado": "OK", "items": [1]},
    )
    _registrar_modulo_falso(
        monkeypatch,
        "fake.param_ok",
        parametrizar=lambda empresa_id=None: {"estado": "OK", "sugerencias": []},
    )

    modulos = (
        ModuloCentroControl(
            codigo="FAKE",
            nombre="Falso",
            diagnostico=FuncionModulo("fake.diagnostico_ok", "diagnosticar"),
            parametrizacion=FuncionModulo("fake.param_ok", "parametrizar"),
        ),
    )

    resultado = generar_centro_control_contable(empresa_id=1, modulos=modulos)

    assert resultado["estado_general"] == ESTADO_OK
    assert resultado["totales"]["ok"] == 1
    assert resultado["alcance"]["solo_lectura"] is True
    assert resultado["alcance"]["genera_asientos"] is False


def test_prioriza_estado_requiere_parametrizacion(monkeypatch):
    _registrar_modulo_falso(
        monkeypatch,
        "fake.diagnostico_advertencia",
        diagnosticar=lambda empresa_id=None: {"estado": "ADVERTENCIA", "alertas": ["a"]},
    )
    _registrar_modulo_falso(
        monkeypatch,
        "fake.param_incompleta",
        parametrizar=lambda empresa_id=None: {"estado": "REQUIERE_PARAMETRIZACION", "incompletos": ["x"]},
    )

    modulos = (
        ModuloCentroControl(
            codigo="FAKE",
            nombre="Falso",
            diagnostico=FuncionModulo("fake.diagnostico_advertencia", "diagnosticar"),
            parametrizacion=FuncionModulo("fake.param_incompleta", "parametrizar"),
        ),
    )

    resultado = generar_centro_control_contable(empresa_id=1, modulos=modulos)

    assert resultado["estado_general"] == ESTADO_REQUIERE_PARAMETRIZACION
    assert resultado["totales"]["requieren_parametrizacion"] == 1
    assert resultado["totales"]["pendientes"] == 1


def test_estado_critico_domina_el_resultado_general(monkeypatch):
    _registrar_modulo_falso(
        monkeypatch,
        "fake.diagnostico_critico",
        diagnosticar=lambda empresa_id=None: {"criticos": ["falta cuenta"], "estado": "CRITICO"},
    )
    _registrar_modulo_falso(
        monkeypatch,
        "fake.param_ok2",
        parametrizar=lambda empresa_id=None: {"estado": "OK"},
    )

    modulos = (
        ModuloCentroControl(
            codigo="FAKE",
            nombre="Falso",
            diagnostico=FuncionModulo("fake.diagnostico_critico", "diagnosticar"),
            parametrizacion=FuncionModulo("fake.param_ok2", "parametrizar"),
        ),
    )

    resultado = generar_centro_control_contable(empresa_id=1, modulos=modulos)

    assert resultado["estado_general"] == ESTADO_CRITICO
    assert resultado["ok"] is False
    assert resultado["totales"]["criticos"] == 1
    assert resultado["totales"]["alertas_criticas"] == 1


def test_servicio_no_disponible_no_rompe_centro_control():
    modulos = (
        ModuloCentroControl(
            codigo="FALTANTE",
            nombre="Faltante",
            diagnostico=FuncionModulo("fake.modulo_inexistente", "diagnosticar"),
            parametrizacion=FuncionModulo("fake.modulo_inexistente", "parametrizar"),
        ),
    )

    resultado = generar_centro_control_contable(empresa_id=1, modulos=modulos)

    assert resultado["estado_general"] == ESTADO_NO_DISPONIBLE
    assert resultado["totales"]["no_disponibles"] == 1
    assert resultado["modulos"][0]["diagnostico"]["ok"] is False


def test_error_de_servicio_queda_reportado(monkeypatch):
    def explotar(empresa_id=None):
        raise RuntimeError("fallo controlado")

    _registrar_modulo_falso(monkeypatch, "fake.error", diagnosticar=explotar)
    _registrar_modulo_falso(
        monkeypatch,
        "fake.param_ok3",
        parametrizar=lambda empresa_id=None: {"estado": "OK"},
    )

    modulos = (
        ModuloCentroControl(
            codigo="ERROR",
            nombre="Error",
            diagnostico=FuncionModulo("fake.error", "diagnosticar"),
            parametrizacion=FuncionModulo("fake.param_ok3", "parametrizar"),
        ),
    )

    resultado = generar_centro_control_contable(empresa_id=1, modulos=modulos)

    assert resultado["estado_general"] == ESTADO_ERROR
    assert resultado["totales"]["errores"] == 1
    assert "fallo controlado" in resultado["modulos"][0]["diagnostico"]["mensaje"]


def test_llama_funciones_con_conn_y_empresa_id(monkeypatch):
    llamadas = {}

    def diagnosticar(conn=None, empresa_id=None):
        llamadas["conn"] = conn
        llamadas["empresa_id"] = empresa_id
        return {"estado": "OK"}

    _registrar_modulo_falso(monkeypatch, "fake.con_conn", diagnosticar=diagnosticar)
    _registrar_modulo_falso(
        monkeypatch,
        "fake.param_conn",
        parametrizar=lambda conn=None, empresa_id=None: {"estado": "OK"},
    )

    modulos = (
        ModuloCentroControl(
            codigo="CONN",
            nombre="Con conexión",
            diagnostico=FuncionModulo("fake.con_conn", "diagnosticar"),
            parametrizacion=FuncionModulo("fake.param_conn", "parametrizar"),
        ),
    )

    conn = object()
    generar_centro_control_contable(conn=conn, empresa_id=99, modulos=modulos)

    assert llamadas["conn"] is conn
    assert llamadas["empresa_id"] == 99


def test_resumen_y_exportacion_textual(monkeypatch):
    _registrar_modulo_falso(
        monkeypatch,
        "fake.diagnostico_texto",
        diagnosticar=lambda empresa_id=None: {"estado": "OK", "mensaje": "diagnóstico listo"},
    )
    _registrar_modulo_falso(
        monkeypatch,
        "fake.param_texto",
        parametrizar=lambda empresa_id=None: {"estado": "ADVERTENCIA", "mensaje": "revisar sugerencias"},
    )
    modulos = (
        ModuloCentroControl(
            codigo="TXT",
            nombre="Texto",
            diagnostico=FuncionModulo("fake.diagnostico_texto", "diagnosticar"),
            parametrizacion=FuncionModulo("fake.param_texto", "parametrizar"),
        ),
    )

    resultado = generar_centro_control_contable(empresa_id=7, modulos=modulos)
    resumen = obtener_resumen_centro_control(resultado)
    texto = exportar_centro_control_como_texto(resultado)

    assert resumen["empresa_id"] == 7
    assert resumen["modulos"][0]["parametrizacion_estado"] == ESTADO_ADVERTENCIA
    assert "CENTRO DE CONTROL CONTABLE PRO" in texto
    assert "Texto [TXT]" in texto
    assert "revisar sugerencias" in texto


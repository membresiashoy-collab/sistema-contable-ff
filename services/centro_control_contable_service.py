from __future__ import annotations

"""Centro de Control Contable PRO.

Servicio integrador de solo lectura para consolidar diagnósticos y
parametrizaciones asistidas existentes por módulo.

Alcance de esta etapa:
- no registra movimientos;
- no acepta ni edita parametrizaciones;
- no modifica servicios operativos;
- no genera asientos;
- no toca Libro Diario, Bandeja ni migraciones.
"""

from dataclasses import dataclass
from datetime import datetime
import importlib
import inspect
import traceback
from typing import Any, Callable


ESTADO_OK = "OK"
ESTADO_SIN_DATOS = "SIN_DATOS"
ESTADO_ADVERTENCIA = "ADVERTENCIA"
ESTADO_REQUIERE_REVISION = "REQUIERE_REVISION"
ESTADO_REQUIERE_PARAMETRIZACION = "REQUIERE_PARAMETRIZACION"
ESTADO_CRITICO = "CRITICO"
ESTADO_ERROR = "ERROR"
ESTADO_NO_DISPONIBLE = "NO_DISPONIBLE"

_PRIORIDAD_ESTADOS = {
    ESTADO_ERROR: 90,
    ESTADO_CRITICO: 80,
    ESTADO_REQUIERE_PARAMETRIZACION: 70,
    ESTADO_REQUIERE_REVISION: 60,
    ESTADO_ADVERTENCIA: 50,
    ESTADO_SIN_DATOS: 20,
    ESTADO_NO_DISPONIBLE: 10,
    ESTADO_OK: 0,
}

_SINONIMOS_ESTADOS = {
    "OK": ESTADO_OK,
    "CORRECTO": ESTADO_OK,
    "COMPLETO": ESTADO_OK,
    "LISTO": ESTADO_OK,
    "SIN_DATOS": ESTADO_SIN_DATOS,
    "SIN DATOS": ESTADO_SIN_DATOS,
    "ADVERTENCIA": ESTADO_ADVERTENCIA,
    "WARNING": ESTADO_ADVERTENCIA,
    "REQUIERE_REVISION": ESTADO_REQUIERE_REVISION,
    "REQUIERE REVISION": ESTADO_REQUIERE_REVISION,
    "REQUIERE_REVISIÓN": ESTADO_REQUIERE_REVISION,
    "REQUIERE REVISIÓN": ESTADO_REQUIERE_REVISION,
    "REVISION": ESTADO_REQUIERE_REVISION,
    "REVISIÓN": ESTADO_REQUIERE_REVISION,
    "REQUIERE_PARAMETRIZACION": ESTADO_REQUIERE_PARAMETRIZACION,
    "REQUIERE PARAMETRIZACION": ESTADO_REQUIERE_PARAMETRIZACION,
    "REQUIERE_PARAMETRIZACIÓN": ESTADO_REQUIERE_PARAMETRIZACION,
    "REQUIERE PARAMETRIZACIÓN": ESTADO_REQUIERE_PARAMETRIZACION,
    "PARAMETRIZACION": ESTADO_REQUIERE_PARAMETRIZACION,
    "PARAMETRIZACIÓN": ESTADO_REQUIERE_PARAMETRIZACION,
    "INCOMPLETO": ESTADO_REQUIERE_PARAMETRIZACION,
    "INCOMPLETA": ESTADO_REQUIERE_PARAMETRIZACION,
    "CRITICO": ESTADO_CRITICO,
    "CRÍTICO": ESTADO_CRITICO,
    "ERROR": ESTADO_ERROR,
    "NO_DISPONIBLE": ESTADO_NO_DISPONIBLE,
    "NO DISPONIBLE": ESTADO_NO_DISPONIBLE,
}


@dataclass(frozen=True)
class FuncionModulo:
    modulo: str
    funcion: str


@dataclass(frozen=True)
class ModuloCentroControl:
    codigo: str
    nombre: str
    diagnostico: FuncionModulo | None = None
    parametrizacion: FuncionModulo | None = None


MODULOS_CENTRO_CONTROL: tuple[ModuloCentroControl, ...] = (
    ModuloCentroControl(
        codigo="COMPRAS",
        nombre="Compras",
        diagnostico=FuncionModulo("services.compras_diagnostico_service", "diagnosticar_compras_pro"),
        parametrizacion=FuncionModulo(
            "services.compras_parametrizacion_asistida_service",
            "diagnosticar_parametrizacion_asistida_compras",
        ),
    ),
    ModuloCentroControl(
        codigo="VENTAS",
        nombre="Ventas",
        diagnostico=FuncionModulo("services.ventas_diagnostico_service", "diagnosticar_ventas"),
        parametrizacion=FuncionModulo(
            "services.ventas_parametrizacion_asistida_service",
            "generar_parametrizacion_asistida_ventas",
        ),
    ),
    ModuloCentroControl(
        codigo="COBRANZAS",
        nombre="Cobranzas",
        diagnostico=FuncionModulo("services.cobranzas_diagnostico_service", "diagnosticar_cobranzas"),
        parametrizacion=FuncionModulo(
            "services.cobranzas_parametrizacion_asistida_service",
            "generar_parametrizacion_asistida_cobranzas",
        ),
    ),
    ModuloCentroControl(
        codigo="PAGOS",
        nombre="Pagos",
        diagnostico=FuncionModulo("services.pagos_diagnostico_service", "diagnosticar_pagos"),
        parametrizacion=FuncionModulo(
            "services.pagos_parametrizacion_asistida_service",
            "obtener_parametrizacion_asistida_pagos",
        ),
    ),
    ModuloCentroControl(
        codigo="TESORERIA",
        nombre="Tesorería",
        diagnostico=FuncionModulo("services.tesoreria_diagnostico_service", "diagnosticar_tesoreria"),
        parametrizacion=FuncionModulo(
            "services.tesoreria_parametrizacion_asistida_service",
            "analizar_parametrizacion_tesoreria",
        ),
    ),
    ModuloCentroControl(
        codigo="CONCILIACION",
        nombre="Conciliación",
        diagnostico=FuncionModulo("services.conciliacion_diagnostico_service", "diagnosticar_conciliacion"),
        parametrizacion=FuncionModulo(
            "services.conciliacion_parametrizacion_asistida_service",
            "analizar_parametrizacion_conciliacion",
        ),
    ),
    ModuloCentroControl(
        codigo="BANCO_CAJA",
        nombre="Banco/Caja",
        diagnostico=FuncionModulo("services.bancos_diagnostico_service", "diagnosticar_banco_caja"),
        parametrizacion=FuncionModulo(
            "services.bancos_parametrizacion_asistida_service",
            "parametrizar_banco_caja_asistido",
        ),
    ),
    ModuloCentroControl(
        codigo="CAJA",
        nombre="Caja",
        diagnostico=FuncionModulo("services.cajas_diagnostico_service", "diagnosticar_cajas"),
        parametrizacion=FuncionModulo(
            "services.cajas_parametrizacion_asistida_service",
            "generar_parametrizacion_asistida_cajas",
        ),
    ),
    ModuloCentroControl(
        codigo="DOCUMENTOS_TESORERIA",
        nombre="Documentos de Tesorería",
        diagnostico=FuncionModulo(
            "services.documentos_tesoreria_diagnostico_service",
            "diagnosticar_documentos_tesoreria",
        ),
        parametrizacion=FuncionModulo(
            "services.documentos_tesoreria_parametrizacion_asistida_service",
            "generar_parametrizacion_asistida_documentos_tesoreria",
        ),
    ),
)


def _normalizar_estado(valor: Any) -> str:
    if valor is None:
        return ESTADO_OK
    texto = str(valor).strip().upper()
    texto = texto.replace("-", "_")
    texto = "_".join(texto.split())
    if texto in _SINONIMOS_ESTADOS:
        return _SINONIMOS_ESTADOS[texto]
    texto_espacios = texto.replace("_", " ")
    return _SINONIMOS_ESTADOS.get(texto_espacios, texto or ESTADO_OK)


def _peor_estado(estados: list[str] | tuple[str, ...]) -> str:
    if not estados:
        return ESTADO_OK
    return max(estados, key=lambda e: _PRIORIDAD_ESTADOS.get(_normalizar_estado(e), 40))


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _cantidad(valor: Any) -> int:
    if valor is None:
        return 0
    if isinstance(valor, dict):
        return len(valor)
    if isinstance(valor, (list, tuple, set)):
        return len(valor)
    if _es_numero(valor):
        return int(valor)
    return 1 if valor else 0


def _buscar_valor(diccionario: dict[str, Any], claves: tuple[str, ...]) -> Any:
    for clave in claves:
        if clave in diccionario:
            return diccionario.get(clave)
    claves_lower = {str(k).lower(): k for k in diccionario.keys()}
    for clave in claves:
        encontrada = claves_lower.get(clave.lower())
        if encontrada is not None:
            return diccionario.get(encontrada)
    return None


def _contar_por_claves(resultado: Any, claves: tuple[str, ...]) -> int:
    if not isinstance(resultado, dict):
        return 0
    valor = _buscar_valor(resultado, claves)
    return _cantidad(valor)


def _inferir_estado_desde_resultado(resultado: Any) -> str:
    if not isinstance(resultado, dict):
        if isinstance(resultado, (list, tuple, set)) and len(resultado) == 0:
            return ESTADO_SIN_DATOS
        return ESTADO_OK

    estado = _buscar_valor(
        resultado,
        (
            "estado",
            "estado_general",
            "estado_modulo",
            "nivel",
            "severidad",
            "status",
            "resultado",
        ),
    )
    if estado:
        return _normalizar_estado(estado)

    if _contar_por_claves(resultado, ("criticos", "críticos", "errores_criticos", "alertas_criticas")):
        return ESTADO_CRITICO
    if _contar_por_claves(resultado, ("incompletos", "pendientes", "faltantes", "sin_parametrizar")):
        return ESTADO_REQUIERE_PARAMETRIZACION
    if _contar_por_claves(resultado, ("advertencias", "alertas", "observaciones")):
        return ESTADO_ADVERTENCIA
    if _contar_por_claves(resultado, ("items", "matriz", "parametrizaciones", "sugerencias", "modulos")) == 0:
        return ESTADO_SIN_DATOS
    return ESTADO_OK


def _resumir_resultado(resultado: Any, incluir_detalle: bool = False) -> dict[str, Any]:
    estado = _inferir_estado_desde_resultado(resultado)
    resumen: dict[str, Any] = {
        "ok": True,
        "estado": estado,
        "criticos": 0,
        "advertencias": 0,
        "pendientes": 0,
        "sugerencias": 0,
        "items": 0,
        "mensaje": "",
    }

    if isinstance(resultado, dict):
        resumen["criticos"] = _contar_por_claves(
            resultado,
            ("criticos", "críticos", "errores_criticos", "alertas_criticas"),
        )
        resumen["advertencias"] = _contar_por_claves(
            resultado,
            ("advertencias", "alertas", "observaciones", "warnings"),
        )
        resumen["pendientes"] = _contar_por_claves(
            resultado,
            ("pendientes", "incompletos", "faltantes", "sin_parametrizar", "requiere_accion"),
        )
        resumen["sugerencias"] = _contar_por_claves(
            resultado,
            ("sugerencias", "sugeridos", "parametrizaciones_sugeridas"),
        )
        resumen["items"] = _contar_por_claves(
            resultado,
            (
                "items",
                "matriz",
                "parametrizaciones",
                "parametrizaciones_asistidas",
                "diagnosticos",
                "modulos",
                "filas",
                "detalle",
            ),
        )
        mensaje = _buscar_valor(resultado, ("mensaje", "descripcion", "descripción", "resumen"))
        if mensaje and not isinstance(mensaje, (list, tuple, dict, set)):
            resumen["mensaje"] = str(mensaje)
    elif isinstance(resultado, (list, tuple, set)):
        resumen["items"] = len(resultado)

    if incluir_detalle:
        resumen["detalle"] = resultado

    return resumen


def _resolver_funcion(funcion_modulo: FuncionModulo | None) -> tuple[Callable[..., Any] | None, str | None]:
    if funcion_modulo is None:
        return None, "Función no configurada"
    try:
        modulo = importlib.import_module(funcion_modulo.modulo)
    except Exception as exc:  # pragma: no cover - el detalle se verifica con tests de servicio
        return None, f"No se pudo importar {funcion_modulo.modulo}: {exc}"
    funcion = getattr(modulo, funcion_modulo.funcion, None)
    if not callable(funcion):
        return None, f"No se encontró función {funcion_modulo.funcion} en {funcion_modulo.modulo}"
    return funcion, None


def _llamar_funcion_servicio(
    funcion: Callable[..., Any],
    *,
    conn: Any = None,
    empresa_id: int | None = None,
    usuario_id: int | None = None,
) -> Any:
    """Llama servicios heterogéneos sin acoplar el centro de control a sus firmas.

    Los servicios existentes fueron creados en etapas separadas y no todos usan
    exactamente el mismo nombre de parámetros. Esta función resuelve los casos
    esperados con introspección y deja fallbacks seguros.
    """

    firma = inspect.signature(funcion)
    kwargs: dict[str, Any] = {}
    desconocidos_requeridos: list[str] = []

    for nombre, parametro in firma.parameters.items():
        if parametro.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        nombre_normalizado = nombre.lower()
        if nombre_normalizado in {"conn", "conexion", "connection", "db", "db_conn"}:
            kwargs[nombre] = conn
        elif nombre_normalizado in {"empresa_id", "id_empresa"}:
            kwargs[nombre] = empresa_id
        elif nombre_normalizado in {"usuario_id", "user_id", "id_usuario"}:
            kwargs[nombre] = usuario_id
        elif parametro.default is inspect._empty:
            desconocidos_requeridos.append(nombre)

    if not desconocidos_requeridos:
        return funcion(**kwargs)

    intentos: list[tuple[Any, ...]] = []
    if conn is not None and empresa_id is not None:
        intentos.append((conn, empresa_id))
    if empresa_id is not None:
        intentos.append((empresa_id,))
    if conn is not None:
        intentos.append((conn,))
    intentos.append(())

    ultimo_error: Exception | None = None
    for args in intentos:
        try:
            return funcion(*args)
        except TypeError as exc:
            ultimo_error = exc
            continue
    if ultimo_error:
        raise ultimo_error
    return funcion()


def _ejecutar_bloque(
    funcion_modulo: FuncionModulo | None,
    *,
    conn: Any = None,
    empresa_id: int | None = None,
    usuario_id: int | None = None,
    incluir_detalle: bool = False,
) -> dict[str, Any]:
    funcion, error = _resolver_funcion(funcion_modulo)
    if error:
        return {
            "ok": False,
            "estado": ESTADO_NO_DISPONIBLE,
            "criticos": 0,
            "advertencias": 0,
            "pendientes": 0,
            "sugerencias": 0,
            "items": 0,
            "mensaje": error,
        }

    try:
        resultado = _llamar_funcion_servicio(
            funcion,
            conn=conn,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
        )
        return _resumir_resultado(resultado, incluir_detalle=incluir_detalle)
    except Exception as exc:
        return {
            "ok": False,
            "estado": ESTADO_ERROR,
            "criticos": 1,
            "advertencias": 0,
            "pendientes": 0,
            "sugerencias": 0,
            "items": 0,
            "mensaje": f"Error ejecutando servicio: {exc}",
            "traceback": traceback.format_exc(limit=5),
        }


def obtener_modulos_centro_control() -> list[dict[str, Any]]:
    """Devuelve el catálogo de módulos incluidos en el centro de control."""
    return [
        {
            "codigo": modulo.codigo,
            "nombre": modulo.nombre,
            "diagnostico": None if modulo.diagnostico is None else modulo.diagnostico.funcion,
            "parametrizacion": None if modulo.parametrizacion is None else modulo.parametrizacion.funcion,
        }
        for modulo in MODULOS_CENTRO_CONTROL
    ]


def generar_centro_control_contable(
    *,
    conn: Any = None,
    empresa_id: int | None = 1,
    usuario_id: int | None = None,
    incluir_detalle: bool = False,
    modulos: tuple[ModuloCentroControl, ...] | list[ModuloCentroControl] | None = None,
) -> dict[str, Any]:
    """Consolida diagnósticos y parametrizaciones asistidas existentes.

    Este servicio es de solo lectura. No persiste datos, no crea asientos y no
    invoca funciones operativas de registración.
    """

    especificaciones = list(modulos or MODULOS_CENTRO_CONTROL)
    salida_modulos: list[dict[str, Any]] = []

    for modulo in especificaciones:
        diagnostico = _ejecutar_bloque(
            modulo.diagnostico,
            conn=conn,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            incluir_detalle=incluir_detalle,
        )
        parametrizacion = _ejecutar_bloque(
            modulo.parametrizacion,
            conn=conn,
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            incluir_detalle=incluir_detalle,
        )
        estado_modulo = _peor_estado([diagnostico["estado"], parametrizacion["estado"]])
        salida_modulos.append(
            {
                "codigo": modulo.codigo,
                "nombre": modulo.nombre,
                "estado": estado_modulo,
                "diagnostico": diagnostico,
                "parametrizacion": parametrizacion,
            }
        )

    estados_modulos = [m["estado"] for m in salida_modulos]
    estado_general = _peor_estado(estados_modulos)

    totales = {
        "modulos": len(salida_modulos),
        "ok": sum(1 for m in salida_modulos if m["estado"] == ESTADO_OK),
        "sin_datos": sum(1 for m in salida_modulos if m["estado"] == ESTADO_SIN_DATOS),
        "advertencias": sum(1 for m in salida_modulos if m["estado"] == ESTADO_ADVERTENCIA),
        "requieren_revision": sum(1 for m in salida_modulos if m["estado"] == ESTADO_REQUIERE_REVISION),
        "requieren_parametrizacion": sum(
            1 for m in salida_modulos if m["estado"] == ESTADO_REQUIERE_PARAMETRIZACION
        ),
        "criticos": sum(1 for m in salida_modulos if m["estado"] == ESTADO_CRITICO),
        "errores": sum(1 for m in salida_modulos if m["estado"] == ESTADO_ERROR),
        "no_disponibles": sum(1 for m in salida_modulos if m["estado"] == ESTADO_NO_DISPONIBLE),
        "alertas_criticas": sum(
            m["diagnostico"].get("criticos", 0) + m["parametrizacion"].get("criticos", 0)
            for m in salida_modulos
        ),
        "alertas_advertencias": sum(
            m["diagnostico"].get("advertencias", 0) + m["parametrizacion"].get("advertencias", 0)
            for m in salida_modulos
        ),
        "pendientes": sum(
            m["diagnostico"].get("pendientes", 0) + m["parametrizacion"].get("pendientes", 0)
            for m in salida_modulos
        ),
        "sugerencias": sum(
            m["diagnostico"].get("sugerencias", 0) + m["parametrizacion"].get("sugerencias", 0)
            for m in salida_modulos
        ),
    }

    return {
        "ok": estado_general not in {ESTADO_ERROR, ESTADO_CRITICO},
        "empresa_id": empresa_id,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "estado_general": estado_general,
        "totales": totales,
        "modulos": salida_modulos,
        "alcance": {
            "solo_lectura": True,
            "registra_movimientos": False,
            "acepta_parametrizaciones": False,
            "genera_asientos": False,
            "toca_servicios_operativos": False,
        },
    }


def obtener_resumen_centro_control(centro_control: dict[str, Any]) -> dict[str, Any]:
    """Devuelve un resumen compacto para UI o reportes."""
    return {
        "empresa_id": centro_control.get("empresa_id"),
        "estado_general": centro_control.get("estado_general"),
        "totales": centro_control.get("totales", {}),
        "modulos": [
            {
                "codigo": modulo.get("codigo"),
                "nombre": modulo.get("nombre"),
                "estado": modulo.get("estado"),
                "diagnostico_estado": modulo.get("diagnostico", {}).get("estado"),
                "parametrizacion_estado": modulo.get("parametrizacion", {}).get("estado"),
            }
            for modulo in centro_control.get("modulos", [])
        ],
    }


def exportar_centro_control_como_texto(centro_control: dict[str, Any]) -> str:
    """Genera una salida textual simple para auditoría o soporte."""
    lineas = [
        "CENTRO DE CONTROL CONTABLE PRO",
        f"Empresa: {centro_control.get('empresa_id')}",
        f"Fecha: {centro_control.get('fecha_generacion')}",
        f"Estado general: {centro_control.get('estado_general')}",
        "",
        "Totales:",
    ]
    for clave, valor in centro_control.get("totales", {}).items():
        lineas.append(f"- {clave}: {valor}")

    lineas.append("")
    lineas.append("Módulos:")
    for modulo in centro_control.get("modulos", []):
        lineas.append(f"- {modulo.get('nombre')} [{modulo.get('codigo')}]: {modulo.get('estado')}")
        diag = modulo.get("diagnostico", {})
        par = modulo.get("parametrizacion", {})
        lineas.append(f"  Diagnóstico: {diag.get('estado')} | {diag.get('mensaje', '')}")
        lineas.append(f"  Parametrización: {par.get('estado')} | {par.get('mensaje', '')}")
    return "\n".join(lineas)

